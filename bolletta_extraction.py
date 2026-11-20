"""Dedicated ScaleDown entity extraction and normalization for energy bills."""
import json
import re
import sys
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from scaledown_provider import ScaleDownError, ScaleDownResponseError, extract_pdf


BOLLETTA_ENTITIES = {
    "cliente": "Intestatario effettivo della fornitura: nome e cognome oppure ragione sociale. lo si trova anche come -Intestatario contratto- potrebbe pure mancare in alcune bollette. in quel caso prendere il cliente di reapito, di solito in alto a sinistra della prima pagina Non usare il fornitore di energia.",
    "indirizzo": "Indirizzo completo del punto di fornitura, si trova di solito nella seconda pagina in alto, sotto la scritta 'indirizzo di fornitura o simili ' distinto dall'indirizzo di recapito quando possibile.",
    "pod": "Codice POD per energia elettrica oppure PDR per gas. spesso sotto o accanto la scritta 'POD (punto di prelievo)' di solito si trova nella seconda pagina. Restituisci il codice della fornitura corrente.",
    "kwh_totali": "Consumo totale fatturato nel solo periodo: kWh per Luce o Smc per Gas. Non sommare storico, letture, periodi diversi, ricalcoli duplicati o pubblicità.",
    "mesi_bolletta": "Numero di mesi coperti dal periodo fatturato. Ricavalo dalle date reali: gennaio-febbraio vale 2, un solo mese vale 1. potresti trovare anche dal - al in quel caso fai la differenza dei mesi. Non assumere automaticamente due mesi.",
    "spesa_vendita_energia": "Importo totale del periodo in euro della sola vendita energia per consumi. Priorità 1: sottovoce di cui spesa per la vendita. Priorità 2: equivalente specifico della componente commerciale. Priorità 3: voce generale solo se esclusivamente vendita e senza scomposizione più precisa. Mai totale fattura, totale quota consumi composto, prezzo unitario, rete, oneri o quota fissa. Il controllo vendita più rete/oneri circa uguale al totale serve solo a disambiguare; non calcolare per sottrazione.",
    "quota_fissa_vendita": "Importo effettivo della sola quota fissa commerciale di vendita, CCV/PCV o equivalente, preso dalla colonna Importi o Totale. Non confonderlo con il prezzo unitario espresso in euro/mese. Escludi rete e oneri. Restituisci l'importo così scritto, senza conversioni.",
    "periodicita_quota_fissa": "Periodicità dell'importo effettivamente restituito in quota_fissa_vendita: Mensile se l'importo estratto è il prezzo unitario di un solo mese, Totale periodo se proviene dalla colonna Importi/Totale e copre tutto il periodo fatturato, Annuale solo se l'importo estratto è annuo. Non dedurla dall'unità euro/mese mostrata accanto a un prezzo unitario diverso. Ometti se non determinabile.",
    "tipo_fornitura": "Identifica Luce oppure Gas dall'oggetto della fornitura, POD/PDR e unità di consumo; ignora offerte alternative pubblicizzate.",
    "tipologia_cliente": "Identifica Residenziale oppure Business dalla tipologia contrattuale o d'uso. Domestico è Residenziale; altri usi, non domestico o impresa sono Business. Non usare semplicemente la presenza di dati aziendali.",
    "potenza_kw": "Potenza contrattualmente impegnata in kW. Non usare potenza disponibile, picchi o potenza misurata.",
}

# The same semantic prompt is used for every supplier and layout. Entity names
# and the external JSON contract remain unchanged.
BOLLETTA_ENTITIES.update({
    "kwh_totali": "Consumo totale fatturato nel solo periodo: kWh per Luce o Smc per Gas. Cercalo nel riepilogo, nello scontrino dell'energia, nel dettaglio dei corrispettivi e nelle caratteristiche della fornitura. Mantieni valore e unità originali. Non usare consumo annuo storico, letture, periodi diversi o ricalcoli duplicati.",
    "mesi_bolletta": "Numero di mesi del periodo fatturato, ricavato dalle date reali presenti nelle sezioni pertinenti. Gennaio-febbraio vale 2 e un solo mese vale 1. Non usare l'intervallo del consumo annuo e non assumere automaticamente due mesi.",
    "spesa_vendita_energia": "Importo totale del periodo della sola vendita energia per consumi. Cercalo nel riepilogo, scontrino dell'energia, box offerta, dettaglio corrispettivi o quota consumi e preferisci la sottovoce di vendita specifica. Mai totale fattura, totale vendita comprensivo di quota fissa, quota consumi composta, prezzo unitario, rete od oneri. Mantieni il valore originale; usa relazioni aritmetiche solo per verificare la voce, mai per inventarla o sottrarla.",
    "quota_fissa_vendita": "Importo effettivo della sola quota fissa commerciale di vendita, CCV/PCV o equivalente. Cercalo nel box offerta, dettaglio corrispettivi o quota fissa e potenza e usa la colonna Importi/Totale, non il prezzo unitario euro/mese. Escludi rete, oneri e quota potenza. Restituisci l'importo così scritto senza conversioni e non duplicarlo se è già compreso in un totale vendita.",
    "tipologia_cliente": "Identifica Residenziale oppure Business dalla tipologia contrattuale o d'uso in tutte le sezioni pertinenti. Domestico è Residenziale; Micro Imprese, Altri Usi, non domestico o impresa sono Business. Non presumere la tipologia dalla sola presenza di dati aziendali.",
    "tipo_fornitura": "Identifica Luce oppure Gas dalla fornitura corrente. Energia Elettrica è Luce; Gas Naturale è Gas. Usa POD/PDR e unità di consumo come conferma e ignora offerte pubblicizzate.",
})


class BollettaExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    cliente: str | None = None
    indirizzo: str | None = None
    pod: str | None = None
    kwh_totali: float | None = None
    mesi_bolletta: int | None = None
    spesa_materia_energia: float | None = None
    spesa_vendita_energia: float | None = None
    quota_fissa_vendita: float | None = None
    tipo_fornitura: Literal["Luce", "Gas"] | None = None
    tipologia_cliente: Literal["Residenziale", "Business"] | None = None
    potenza_kw: float | None = None


class BollettaExtractionResult(dict):
    """Internal result metadata; serialized success fields stay unchanged."""

    def __init__(self, values: dict, diagnostic_id: str):
        super().__init__(values)
        self.diagnostic_id = diagnostic_id


_SUPPLY_ALIASES = {"luce": "Luce", "energia elettrica": "Luce", "gas": "Gas", "gas naturale": "Gas"}
_CUSTOMER_ALIASES = {
    "residenziale": "Residenziale", "domestico": "Residenziale", "business": "Business",
    "impresa": "Business", "micro imprese": "Business", "altri usi": "Business",
    "non domestico": "Business",
}
_FIXED_PERIOD_ALIASES = {
    "mensile": "Mensile", "ogni mese": "Mensile", "totale periodo": "Totale periodo",
    "periodo": "Totale periodo", "annuale": "Annuale", "annuo": "Annuale",
}
_REQUIRED_FIELDS = (
    "kwh_totali", "mesi_bolletta", "spesa_vendita_energia", "quota_fissa_vendita",
    "tipo_fornitura", "tipologia_cliente",
)
_FALLBACK_INSTRUCTION = (
    "Recover only the requested missing bill entities from the same PDF without inventing values. "
    "For an ARERA Scontrino dell'energia, use total billed consumption for the billing period, not annual history; "
    "derive months from billing-period dates; use the sales-energy subitem inside Quota per consumi, excluding "
    "network charges and fixed fees; find the sales fixed-fee subitem inside Quota fissa e Quota Potenza and state "
    "whether it is monthly, total-period or annual; classify Micro Imprese, Altri Usi and non-domestic use as "
    "Business; classify Energia Elettrica as Luce and Gas Naturale as Gas. Return no unsupported values."
)


def _log_extraction(event: str, **details) -> None:
    print(
        "[ScaleDown][BillExtraction] " + json.dumps(
            {"event": event, **details}, ensure_ascii=False, separators=(",", ":")
        ),
        file=sys.stderr, flush=True,
    )


def _entity_values(entities: list[dict]) -> tuple[dict, list[str]]:
    selected: dict[str, str] = {}
    unknown: set[str] = set()
    for entity in entities:
        field = entity["type"].strip()
        if field not in BOLLETTA_ENTITIES:
            if re.fullmatch(r"[A-Za-z0-9_]{1,100}", field):
                unknown.add(field)
            continue
        text = entity["text"].strip()
        if text and field not in selected:
            selected[field] = text
    return selected, sorted(unknown)


def _number(value):
    if value is None:
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


def _nonnegative(value):
    number = _number(value)
    return number if number is not None and number >= 0 else None


def _choice(value, aliases):
    if value is None:
        return None
    return aliases.get(" ".join(value.split()).casefold())


def _text(value):
    cleaned = str(value or "").strip()
    return cleaned or None


def _validation_error(error: ValidationError, duration_ms):
    validation_errors = tuple(sorted({
        (".".join(str(part) for part in item["loc"]), str(item["type"])) for item in error.errors()
    }))
    raise ScaleDownResponseError(
        "Dati ScaleDown non conformi al contratto bolletta", category="validation", duration_ms=duration_ms,
        invalid_fields=tuple(field for field, _kind in validation_errors), validation_errors=validation_errors,
    ) from error


def _normalize_entities(entities: list[dict]) -> tuple[dict, list[tuple[str, str]], list[str]]:
    values, unknown = _entity_values(entities)
    invalid: list[tuple[str, str]] = []
    months_number = _number(values.get("mesi_bolletta"))
    months = int(months_number) if months_number is not None and months_number > 0 and months_number.is_integer() else None
    if values.get("mesi_bolletta") is not None and months is None:
        invalid.append(("mesi_bolletta", "invalid_period"))
    sales = _nonnegative(values.get("spesa_vendita_energia"))
    matter = sales
    fixed_cost = _nonnegative(values.get("quota_fissa_vendita"))
    fixed_period = _choice(values.get("periodicita_quota_fissa"), _FIXED_PERIOD_ALIASES)
    for field in ("kwh_totali", "spesa_vendita_energia", "quota_fissa_vendita", "potenza_kw"):
        if values.get(field) is not None and _nonnegative(values[field]) is None:
            invalid.append((field, "invalid_number"))
    for field, aliases in (("tipo_fornitura", _SUPPLY_ALIASES), ("tipologia_cliente", _CUSTOMER_ALIASES)):
        if values.get(field) is not None and _choice(values[field], aliases) is None:
            invalid.append((field, "unknown_classification"))
    if values.get("periodicita_quota_fissa") is not None and fixed_period is None:
        invalid.append(("periodicita_quota_fissa", "unknown_periodicity"))
    elif fixed_cost is not None and values.get("periodicita_quota_fissa") is None:
        invalid.append(("periodicita_quota_fissa", "missing_periodicity"))
    if fixed_cost is not None:
        if fixed_period == "Totale periodo":
            fixed_cost = fixed_cost / months if months else None
        elif fixed_period == "Annuale":
            fixed_cost /= 12
        elif fixed_period != "Mensile":
            fixed_cost = None
    normalized = {
        "cliente": _text(values.get("cliente")), "indirizzo": _text(values.get("indirizzo")),
        "pod": _text(values.get("pod")), "kwh_totali": _nonnegative(values.get("kwh_totali")),
        "mesi_bolletta": months, "spesa_materia_energia": matter, "spesa_vendita_energia": sales,
        "quota_fissa_vendita": fixed_cost,
        "tipo_fornitura": _choice(values.get("tipo_fornitura"), _SUPPLY_ALIASES),
        "tipologia_cliente": _choice(values.get("tipologia_cliente"), _CUSTOMER_ALIASES),
        "potenza_kw": _nonnegative(values.get("potenza_kw")),
    }
    try:
        result = BollettaExtraction.model_validate(normalized).model_dump()
        return result, sorted(set(invalid)), unknown
    except ValidationError as error:
        _validation_error(error, getattr(entities, "duration_ms", None))


def _fallback_entities(missing: list[str]) -> dict[str, str]:
    requested = {field: BOLLETTA_ENTITIES[field] for field in missing}
    if "quota_fissa_vendita" in missing:
        requested["periodicita_quota_fissa"] = BOLLETTA_ENTITIES["periodicita_quota_fissa"]
    return requested


def extract_bolletta(file_bytes: bytes) -> dict:
    diagnostic_id = uuid.uuid4().hex
    try:
        raw_first = extract_pdf(
            file_bytes, BOLLETTA_ENTITIES, diagnostic_id=diagnostic_id, attempt=1
        )
        first_values, invalid, unknown = _normalize_entities(raw_first)
    except ScaleDownError as error:
        error.diagnostic_id = diagnostic_id
        raise
    first = BollettaExtractionResult(first_values, diagnostic_id)
    missing = [field for field in _REQUIRED_FIELDS if first.get(field) is None]
    code = (
        "EMPTY_ENTITIES" if not raw_first else
        "UNKNOWN_ENTITIES" if unknown else
        "INVALID_FIELD" if invalid else
        "MISSING_REQUIRED" if missing else None
    )
    recognized = sorted(set(BOLLETTA_ENTITIES) & {item["type"] for item in raw_first})
    _log_extraction(
        "first_completed", diagnostic_id=diagnostic_id, diagnostic_code=code,
        duration_ms=getattr(raw_first, "duration_ms", None),
        requested_count=len(BOLLETTA_ENTITIES), received_count=len(raw_first),
        entity_names=recognized, unknown_entities=unknown,
        invalid_fields=[{"field": field, "reason": reason} for field, reason in invalid],
        complete=not missing, missing_fields=missing, calls=1,
    )
    if not missing:
        return first

    _log_extraction(
        "fallback_started", diagnostic_id=diagnostic_id,
        missing_fields=missing, calls=2,
    )
    recovery_fields = [*missing]
    if first.get("potenza_kw") is None:
        recovery_fields.append("potenza_kw")
    try:
        requested = _fallback_entities(recovery_fields)
        raw_second = extract_pdf(
            file_bytes, requested, instruction=_FALLBACK_INSTRUCTION,
            diagnostic_id=diagnostic_id, attempt=2,
        )
        second, second_invalid, second_unknown = _normalize_entities(raw_second)
    except ScaleDownError as error:
        error.diagnostic_id = diagnostic_id
        _log_extraction(
            "fallback_error", diagnostic_id=diagnostic_id,
            diagnostic_code=error.diagnostic_code, category=error.category, calls=2,
        )
        raise

    for field in recovery_fields:
        if first.get(field) is None and second.get(field) is not None:
            first[field] = second[field]
    if first.get("spesa_materia_energia") is None and first.get("spesa_vendita_energia") is not None:
        first["spesa_materia_energia"] = first["spesa_vendita_energia"]
    remaining = [field for field in _REQUIRED_FIELDS if first.get(field) is None]
    code = (
        "EMPTY_ENTITIES" if not raw_second else
        "UNKNOWN_ENTITIES" if second_unknown else
        "INVALID_FIELD" if second_invalid else
        "MISSING_REQUIRED" if remaining else None
    )
    _log_extraction(
        "fallback_completed", diagnostic_id=diagnostic_id, diagnostic_code=code,
        duration_ms=getattr(raw_second, "duration_ms", None),
        requested_count=len(requested), received_count=len(raw_second),
        unknown_entities=second_unknown,
        invalid_fields=[{"field": field, "reason": reason} for field, reason in second_invalid],
        complete=not remaining, missing_fields=remaining, calls=2,
    )
    return first
