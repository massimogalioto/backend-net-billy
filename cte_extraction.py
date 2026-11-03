"""Dedicated ScaleDown entity extraction and normalization for CTE PDFs."""
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from cte_notes import format_cte_notes
from cte_validity import normalize_cte_validity
from scaledown_provider import ScaleDownResponseError, extract_pdf


CTE_ENTITIES = {
    "tipo_fornitura": "Identifica l'oggetto dell'offerta: Luce oppure Gas. Usa il prodotto offerto, POD/kWh/PUN per Luce e PDR/Smc/PSV per Gas; ignora riferimenti normativi non pertinenti. Se ambiguo non inventare.",
    "tipologia_cliente": "Identifica il cliente ammesso: Residenziale oppure Business. Domestico equivale a Residenziale; non domestico, impresa, professionista, condominio o microimpresa equivalgono a Business. Non usare la partita IVA del fornitore.",
    "tariffa": "Identifica Fisso oppure Variabile per il periodo iniziale. PUN, PUN Index GME e PSV sono Variabile anche con spread zero. Non usare le condizioni di rinnovo; se mista o ambigua non inventare.",
    "fornitore": "Società che vende energia al cliente, non distributore o gestore di rete.",
    "nome_offerta": "Denominazione commerciale esatta dell'offerta.",
    "prezzo_energia_iniziale": "Prezzo unitario iniziale della sola componente energia. Escludi rinnovi, trasporto, oneri, IVA e imposte. Restituisci il testo numerico senza calcoli.",
    "unita_prezzo_energia": "Unità originale associata al prezzo energia iniziale, per esempio €/kWh o €/Smc.",
    "prezzo_energia_rinnovo": "Prezzo previsto esclusivamente dopo il periodo iniziale; non confonderlo con il prezzo iniziale.",
    "spread": "Maggiorazione unitaria iniziale applicata a PUN o PSV. Non usare spread di rinnovo e non confondere con altri corrispettivi.",
    "unita_spread": "Unità originale dello spread iniziale.",
    "quota_commercializzazione": "Corrispettivo fisso commerciale di vendita CCV, PCV o equivalente. Escludi quote regolate, rete e oneri. Restituisci l'importo senza conversioni.",
    "periodicita_quota_commercializzazione": "Periodicità esplicita della quota commerciale: Mensile oppure Annuale. Se assente ometti il campo.",
    "valid_from": "Data esplicita di inizio della validità commerciale, non data documento o decorrenza cliente.",
    "valid_until": "Ultima data esplicita di adesione all'offerta, non durata contratto o scadenza del prezzo.",
    "vincoli": "Condizioni obbligatorie per aderire all'offerta.",
    "recesso_anticipato": "Penali, costi, recupero sconti e condizioni esplicite di recesso anticipato.",
    "fatturazione": "Periodicità esplicita di emissione delle fatture, per esempio Mensile o Bimestrale.",
    "min_power_kw": "Potenza minima ammessa dall'offerta in kW, solo se esplicita.",
    "max_power_kw": "Potenza massima ammessa dall'offerta in kW, solo se esplicita.",
    "condizioni_particolari": "Sconti, domiciliazione, bolletta digitale, limiti e altre condizioni rilevanti non già estratte.",
    "dispacciamento_importo": "Corrispettivo di dispacciamento esplicitamente quantificato; non estrarre un semplice riferimento normativo.",
    "dispacciamento_unita": "Unità originale del corrispettivo di dispacciamento quantificato.",
    "dispacciamento_riferimento_arera": "Riferimento ARERA sul dispacciamento quando non è indicato un importo numerico.",
}


class CTERawExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tipo_fornitura: Literal["Luce", "Gas", "Non determinabile"] = "Non determinabile"
    tipologia_cliente: Literal["Residenziale", "Business", "Non determinabile"] = "Non determinabile"
    tariffa: Literal["Fisso", "Variabile", "Non determinabile"] = "Non determinabile"
    fornitore: str | None = None
    nome_offerta: str | None = None
    prezzo_energia_iniziale: str | None = None
    unita_prezzo_energia: str | None = None
    prezzo_energia_rinnovo: str | None = None
    spread: str | None = None
    unita_spread: str | None = None
    quota_commercializzazione: str | None = None
    periodicita_quota_commercializzazione: Literal["Mensile", "Annuale"] | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    vincoli: str | None = None
    recesso_anticipato: str | None = None
    fatturazione: Literal["Mensile", "Bimestrale", "Non indicata"] = "Non indicata"
    min_power_kw: str | None = None
    max_power_kw: str | None = None
    condizioni_particolari: str | None = None
    dispacciamento_importo: str | None = None
    dispacciamento_unita: str | None = None
    dispacciamento_riferimento_arera: str | None = None


_ALIASES = {
    "tipo_fornitura": {"luce": "Luce", "energia elettrica": "Luce", "gas": "Gas", "gas naturale": "Gas", "non determinabile": "Non determinabile"},
    "tipologia_cliente": {"residenziale": "Residenziale", "domestico": "Residenziale", "business": "Business", "impresa": "Business", "non determinabile": "Non determinabile"},
    "tariffa": {"fisso": "Fisso", "prezzo fisso": "Fisso", "variabile": "Variabile", "prezzo indicizzato": "Variabile", "non determinabile": "Non determinabile"},
    "periodicita_quota_commercializzazione": {"mensile": "Mensile", "ogni mese": "Mensile", "annuale": "Annuale", "annuo": "Annuale"},
    "fatturazione": {"mensile": "Mensile", "ogni mese": "Mensile", "bimestrale": "Bimestrale", "non indicata": "Non indicata"},
}


def _entity_values(entities: list[dict]) -> dict:
    selected: dict[str, tuple[float, str]] = {}
    for entity in entities:
        field = entity["type"].strip()
        if field not in CTE_ENTITIES:
            continue
        text = entity["text"].strip()
        if not text:
            continue
        confidence = float(entity["confidence"]) if entity.get("confidence") is not None else -1.0
        if field not in selected or confidence > selected[field][0]:
            selected[field] = (confidence, text)
    return {field: value for field, (_confidence, value) in selected.items()}


def _choice(value, aliases: dict[str, str], missing):
    if value is None:
        return missing
    key = " ".join(value.split()).casefold()
    if not key:
        return missing
    return aliases.get(key, missing)


def _normalize_choices(values: dict) -> dict:
    normalized = dict(values)
    for field, missing in (("tipo_fornitura", "Non determinabile"), ("tipologia_cliente", "Non determinabile"),
                           ("tariffa", "Non determinabile"), ("periodicita_quota_commercializzazione", None),
                           ("fatturazione", "Non indicata")):
        normalized[field] = _choice(normalized.get(field), _ALIASES[field], missing)
    return normalized


def _number(value):
    if value is None or value == "":
        return None
    text = re.sub(r"[^0-9,.-]", "", str(value).strip().replace("\u00a0", "").replace(" ", ""))
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    elif not text.startswith(("0.", "-0.")) and re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "")
    try:
        return float(text)
    except ValueError:
        return None


def _positive_number(value):
    number = _number(value)
    return number if number is not None and number >= 0 else None


def _economic_value(value, unit, supply_type):
    number = _number(value)
    if number is None:
        return None
    unit_text = f"{unit or ''} {value or ''}".casefold().replace(" ", "")
    if supply_type == "Luce":
        if "mwh" in unit_text:
            return number / 1000
        return number if "kwh" in unit_text else None
    if supply_type == "Gas":
        return number if "smc" in unit_text else None
    return None


def _date(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _text(value):
    cleaned = str(value or "").strip()
    return cleaned or None


def _validation_error(error: ValidationError, duration_ms):
    validation_errors = tuple(sorted({
        (".".join(str(part) for part in item["loc"]), str(item["type"])) for item in error.errors()
    }))
    raise ScaleDownResponseError(
        "Dati ScaleDown non conformi al contratto CTE", category="validation", duration_ms=duration_ms,
        invalid_fields=tuple(field for field, _kind in validation_errors), validation_errors=validation_errors,
    ) from error


def extract_cte(file_bytes: bytes) -> dict:
    entities = extract_pdf(file_bytes, CTE_ENTITIES)
    try:
        raw = CTERawExtraction.model_validate(_normalize_choices(_entity_values(entities)))
    except ValidationError as error:
        _validation_error(error, getattr(entities, "duration_ms", None))
    data = raw.model_dump()
    fixed_cost = _number(data["quota_commercializzazione"])
    if fixed_cost is not None and data["periodicita_quota_commercializzazione"] == "Annuale":
        fixed_cost /= 12
    validity = normalize_cte_validity({"valid_from": _date(data["valid_from"]), "valid_until": _date(data["valid_until"])})
    extra = []
    if _text(data["condizioni_particolari"]):
        extra.append(_text(data["condizioni_particolari"]))
    if _text(data["prezzo_energia_rinnovo"]):
        extra.append(f"Prezzo rinnovo: {_text(data['prezzo_energia_rinnovo'])}")
    if _text(data["dispacciamento_importo"]):
        unit = f" {_text(data['dispacciamento_unita'])}" if _text(data["dispacciamento_unita"]) else ""
        extra.append(f"Dispacciamento: {_text(data['dispacciamento_importo'])}{unit}")
    elif _text(data["dispacciamento_riferimento_arera"]):
        extra.append(f"Dispacciamento ARERA: {_text(data['dispacciamento_riferimento_arera'])}")
    other_notes = "; ".join(extra) or None
    return {
        "fornitore": _text(data["fornitore"]), "nome_offerta": _text(data["nome_offerta"]),
        "tipologia_cliente": data["tipologia_cliente"], "tariffa": data["tariffa"],
        "prezzo_kwh": _economic_value(data["prezzo_energia_iniziale"], data["unita_prezzo_energia"], data["tipo_fornitura"])
        if data["tariffa"] == "Fisso" else None,
        "spread": _economic_value(data["spread"], data["unita_spread"], data["tipo_fornitura"])
        if data["tariffa"] == "Variabile" else None,
        "costo_fisso": fixed_cost, **validity, "vincoli": _text(data["vincoli"]),
        "tipo_fornitura": data["tipo_fornitura"], "min_power_kw": _positive_number(data["min_power_kw"]),
        "max_power_kw": _positive_number(data["max_power_kw"]), "fatturazione": data["fatturazione"],
        "recesso_anticipato": _text(data["recesso_anticipato"]) or "Non indicato",
        "altre_note": other_notes,
        "notes": format_cte_notes(data["fatturazione"], data["recesso_anticipato"], other_notes, data["vincoli"]),
    }
