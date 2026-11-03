"""Dedicated ScaleDown entity extraction and normalization for energy bills."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from scaledown_provider import ScaleDownResponseError, extract_pdf


BOLLETTA_ENTITIES = {
    "cliente": "Intestatario effettivo della fornitura: nome e cognome oppure ragione sociale. Non usare il fornitore di energia.",
    "indirizzo": "Indirizzo completo del punto di fornitura, distinto dall'indirizzo di recapito quando possibile.",
    "pod": "Codice POD per energia elettrica oppure PDR per gas. Restituisci il codice della fornitura corrente.",
    "kwh_totali": "Consumo totale fatturato nel solo periodo: kWh per Luce o Smc per Gas. Non sommare storico, letture, periodi diversi, ricalcoli duplicati o pubblicità.",
    "mesi_bolletta": "Numero di mesi coperti dal periodo fatturato. Ricavalo dalle date reali: gennaio-febbraio vale 2, un solo mese vale 1. Non assumere automaticamente due mesi.",
    "spesa_materia_energia": "Importo totale del periodo in euro della sola vendita energia per consumi, uguale a spesa_vendita_energia. Priorità 1: sottovoce 'di cui spesa per la vendita di energia elettrica' o gas. Priorità 2: equivalenti come componente o spesa vendita energia e componente energia del venditore. Priorità 3: usa spesa materia energia o quota consumi solo se identifica esclusivamente la vendita e non esiste una scomposizione più precisa. Escludi rete, trasporto, distribuzione, oneri, imposte e quota fissa. Se vendita più rete/oneri è circa il totale quota consumi, usa la relazione solo per disambiguare, mai per sottrazione. Esempio: totale 127,06 euro, vendita 105,09 euro, rete/oneri 21,97 euro: estrai 105,09, non 127,06 e non il prezzo unitario 0,228954.",
    "spesa_vendita_energia": "Importo totale del periodo in euro della sola vendita energia per consumi, uguale a spesa_materia_energia. Priorità 1: sottovoce di cui spesa per la vendita. Priorità 2: equivalente specifico della componente commerciale. Priorità 3: voce generale solo se esclusivamente vendita e senza scomposizione più precisa. Mai totale fattura, totale quota consumi composto, prezzo unitario, rete, oneri o quota fissa. Il controllo vendita più rete/oneri circa uguale al totale serve solo a disambiguare; non calcolare per sottrazione.",
    "quota_fissa_vendita": "Importo della sola quota fissa commerciale di vendita, CCV/PCV o equivalente. Escludi rete e oneri. Restituisci l'importo esplicito senza conversioni.",
    "periodicita_quota_fissa": "Indica se l'importo della quota fissa commerciale è Mensile, Totale periodo oppure Annuale. Ometti se non determinabile.",
    "tipo_fornitura": "Identifica Luce oppure Gas dall'oggetto della fornitura, POD/PDR e unità di consumo; ignora offerte alternative pubblicizzate.",
    "tipologia_cliente": "Identifica Residenziale oppure Business dalla tipologia contrattuale o d'uso. Domestico è Residenziale; altri usi, non domestico o impresa sono Business. Non usare semplicemente la presenza di dati aziendali.",
    "potenza_kw": "Potenza contrattualmente impegnata in kW. Non usare potenza disponibile, picchi o potenza misurata.",
}


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


_SUPPLY_ALIASES = {"luce": "Luce", "energia elettrica": "Luce", "gas": "Gas", "gas naturale": "Gas"}
_CUSTOMER_ALIASES = {
    "residenziale": "Residenziale", "domestico": "Residenziale", "business": "Business",
    "impresa": "Business", "altri usi": "Business", "non domestico": "Business",
}
_FIXED_PERIOD_ALIASES = {
    "mensile": "Mensile", "ogni mese": "Mensile", "totale periodo": "Totale periodo",
    "periodo": "Totale periodo", "annuale": "Annuale", "annuo": "Annuale",
}


def _entity_values(entities: list[dict]) -> dict:
    selected: dict[str, str] = {}
    for entity in entities:
        field = entity["type"].strip()
        if field not in BOLLETTA_ENTITIES:
            continue
        text = entity["text"].strip()
        if text and field not in selected:
            selected[field] = text
    return selected


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


def extract_bolletta(file_bytes: bytes) -> dict:
    entities = extract_pdf(file_bytes, BOLLETTA_ENTITIES)
    values = _entity_values(entities)
    months_number = _number(values.get("mesi_bolletta"))
    months = int(months_number) if months_number is not None and months_number > 0 and months_number.is_integer() else None
    sales = _nonnegative(values.get("spesa_vendita_energia"))
    matter = _nonnegative(values.get("spesa_materia_energia"))
    if sales is None:
        sales = matter
    if matter is None:
        matter = sales
    fixed_cost = _nonnegative(values.get("quota_fissa_vendita"))
    fixed_period = _choice(values.get("periodicita_quota_fissa"), _FIXED_PERIOD_ALIASES)
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
        return BollettaExtraction.model_validate(normalized).model_dump()
    except ValidationError as error:
        _validation_error(error, getattr(entities, "duration_ms", None))
