"""Pydantic contracts and ScaleDown schema for CTE extraction."""
from typing import Literal

from pydantic import BaseModel, ConfigDict


Classification = Literal["Luce", "Gas", "Non determinabile"]
CustomerType = Literal["Residenziale", "Business", "Non determinabile"]
TariffType = Literal["Fisso", "Variabile", "Non determinabile"]


class CTERawExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tipo_fornitura: Classification
    tipologia_cliente: CustomerType
    tariffa: TariffType
    fornitore: str | None = None
    nome_offerta: str | None = None
    prezzo_energia_iniziale: str | float | None = None
    unita_prezzo_energia: str | None = None
    prezzo_energia_rinnovo: str | float | None = None
    spread: str | float | None = None
    unita_spread: str | None = None
    quota_commercializzazione: str | float | None = None
    periodicita_quota_commercializzazione: Literal["Mensile", "Annuale"] | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    vincoli: str | None = None
    recesso_anticipato: str | None = None
    fatturazione: Literal["Mensile", "Bimestrale", "Non indicata"] = "Non indicata"
    min_power_kw: str | float | None = None
    max_power_kw: str | float | None = None
    condizioni_particolari: str | None = None
    dispacciamento_importo: str | float | None = None
    dispacciamento_unita: str | None = None
    dispacciamento_riferimento_arera: str | None = None


_CTE_PROPERTIES = {
        "tipo_fornitura": {"type": "string", "enum": ["Luce", "Gas", "Non determinabile"]},
        "tipologia_cliente": {"type": "string", "enum": ["Residenziale", "Business", "Non determinabile"]},
        "tariffa": {"type": "string", "enum": ["Fisso", "Variabile", "Non determinabile"]},
        "fornitore": {"type": "string"}, "nome_offerta": {"type": "string"},
        "prezzo_energia_iniziale": {"type": "string", "description": "Initial energy price only; never a renewal price."},
        "unita_prezzo_energia": {"type": "string", "description": "Exact unit printed in the document."},
        "prezzo_energia_rinnovo": {"type": "string"},
        "spread": {"type": "string", "description": "PUN/PSV spread only."},
        "unita_spread": {"type": "string"}, "quota_commercializzazione": {"type": "string"},
        "periodicita_quota_commercializzazione": {"type": "string", "enum": ["Mensile", "Annuale"]},
        "valid_from": {"type": "string", "description": "Explicit commercial validity start only."},
        "valid_until": {"type": "string", "description": "Explicit subscription or commercial validity end only."},
        "vincoli": {"type": "string"}, "recesso_anticipato": {"type": "string"},
        "fatturazione": {"type": "string", "enum": ["Mensile", "Bimestrale", "Non indicata"]},
        "min_power_kw": {"type": "string"}, "max_power_kw": {"type": "string"},
        "condizioni_particolari": {"type": "string"},
        "dispacciamento_importo": {"type": "string", "description": "Explicit dispatching amount only."},
        "dispacciamento_unita": {"type": "string"},
        "dispacciamento_riferimento_arera": {"type": "string", "description": "ARERA reference when no explicit amount is printed."},
}

CTE_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "cte": {
            "type": "object", "properties": _CTE_PROPERTIES,
            "required": ["tipo_fornitura", "tipologia_cliente", "tariffa"],
        }
    },
    "required": ["cte"],
}

DOCUMENT_SCHEMAS = {"cte": CTE_EXTRACTION_SCHEMA}
