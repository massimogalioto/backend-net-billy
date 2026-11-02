"""Document extraction facade and CTE application normalization."""
import re
from datetime import datetime
from pydantic import ValidationError
from cte_notes import format_cte_notes
from cte_validity import normalize_cte_validity
from document_schemas import CTERawExtraction
from scaledown_provider import ScaleDownResponseError, extract_pdf


def _number(value):
    if value is None or value == "": return None
    if isinstance(value, (int, float)): return float(value)
    text = re.sub(r"[^0-9,.-]", "", str(value).strip().replace("\u00a0", "").replace(" ", ""))
    if not text: return None
    text = text.replace(".", "").replace(",", ".") if "," in text and "." in text else text.replace(",", ".")
    try: return float(text)
    except ValueError: return None


def _iso_date(value):
    if not value: return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try: return datetime.strptime(str(value).strip(), fmt).date().isoformat()
        except ValueError: pass
    return None


def _clean_text(value):
    text = str(value or "").strip()
    return text or None


def _normalize_cte(raw: CTERawExtraction) -> dict:
    data = raw.model_dump()
    monthly_cost = _number(data["quota_commercializzazione"])
    if monthly_cost is not None and data["periodicita_quota_commercializzazione"] == "Annuale": monthly_cost /= 12
    validity = normalize_cte_validity({"valid_from": _iso_date(data["valid_from"]), "valid_until": _iso_date(data["valid_until"])})
    other_notes = _clean_text(data["condizioni_particolari"])
    min_power, max_power = _number(data["min_power_kw"]), _number(data["max_power_kw"])
    return {
        "fornitore": _clean_text(data["fornitore"]), "nome_offerta": _clean_text(data["nome_offerta"]),
        "tipologia_cliente": data["tipologia_cliente"], "tariffa": data["tariffa"],
        "prezzo_kwh": _number(data["prezzo_energia_iniziale"]) if data["tariffa"] == "Fisso" else None,
        "spread": _number(data["spread"]) if data["tariffa"] == "Variabile" else None,
        "costo_fisso": monthly_cost, **validity, "vincoli": _clean_text(data["vincoli"]), "tipo_fornitura": data["tipo_fornitura"],
        "min_power_kw": min_power if min_power is not None and min_power >= 0 else None,
        "max_power_kw": max_power if max_power is not None and max_power >= 0 else None,
        "fatturazione": data["fatturazione"], "recesso_anticipato": _clean_text(data["recesso_anticipato"]) or "Non indicato",
        "altre_note": other_notes, "notes": format_cte_notes(data["fatturazione"], data["recesso_anticipato"], other_notes, data["vincoli"]),
        "unita_prezzo_energia": _clean_text(data["unita_prezzo_energia"]), "unita_spread": _clean_text(data["unita_spread"]),
        "prezzo_energia_rinnovo": _number(data["prezzo_energia_rinnovo"]), "dispacciamento_importo": _number(data["dispacciamento_importo"]),
        "dispacciamento_unita": _clean_text(data["dispacciamento_unita"]),
        "dispacciamento_riferimento_arera": _clean_text(data["dispacciamento_riferimento_arera"]),
    }


def extract_document(file_bytes: bytes, document_type: str, schema: dict) -> dict:
    if document_type != "cte": raise ValueError(f"Tipo documento non supportato: {document_type}")
    provider_result = extract_pdf(file_bytes, schema)
    try: raw = CTERawExtraction.model_validate(provider_result)
    except ValidationError as error:
        invalid_fields = tuple(sorted({".".join(str(part) for part in item["loc"]) for item in error.errors()}))
        raise ScaleDownResponseError(
            "Dati ScaleDown non conformi allo schema CTE", category="validation",
            duration_ms=getattr(provider_result, "duration_ms", None), invalid_fields=invalid_fields,
        ) from error
    return _normalize_cte(raw)
