from datetime import date
import math
import re
from pydantic import BaseModel, validator
from fastapi import APIRouter, Depends, HTTPException
from database_service import ConfigurationError, list_cte_offers, update_cte_offer
from auth_service import CurrentUser, current_user
from plan_service import UsageLimitError

router = APIRouter()


@router.get("/cte-offers")
def cte_archive(customer_type: str | None = None, supply_type: str | None = None,
                active_only: bool = True, user: CurrentUser = Depends(current_user)):
    try:
        return {"offers": list_cte_offers(customer_type, supply_type, active_only, tenant_id=user.tenant_id)}
    except ConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail="Archivio CTE non disponibile") from error




class CteOfferPatch(BaseModel):
    supplier: str | None = None
    offer_name: str | None = None
    customer_type: str | None = None
    supply_type: str | None = None
    tariff_type: str | None = None
    fixed_price_kwh: float | None = None
    spread_kwh: float | None = None
    monthly_fixed_cost: float | None = None
    min_power_kw: float | None = None
    max_power_kw: float | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    notes: str | None = None
    source_cte: str | None = None

    class Config:
        extra = "forbid"

    @validator("supplier", "offer_name", "customer_type")
    def required_text(cls, value):
        if value is None or not value.strip():
            raise ValueError("Campo obbligatorio")
        return value.strip()

    @validator("supply_type")
    def supply(cls, value):
        values = {"luce": "Luce", "gas": "Gas"}
        normalized = str(value).strip().lower() if value is not None else ""
        if normalized not in values:
            raise ValueError("Campo obbligatorio o non riconosciuto")
        return values[normalized]

    @validator("tariff_type")
    def tariff(cls, value):
        values = {"fisso": "Fisso", "variabile": "Variabile"}
        if value is None or value.strip().lower() not in values:
            raise ValueError("Tariffa non riconosciuta: Fisso o Variabile")
        return values[value.strip().lower()]

    @validator("fixed_price_kwh", "spread_kwh", "monthly_fixed_cost", "min_power_kw", "max_power_kw")
    def number(cls, value):
        if value is not None and not math.isfinite(value):
            raise ValueError("Numero non valido")
        return value

    @validator("min_power_kw", "max_power_kw")
    def positive_power(cls, value):
        if value is not None and value < 0:
            raise ValueError("Potenza non valida")
        return value

    @validator("valid_from", "valid_until", pre=True)
    def iso_date(cls, value):
        if value is not None and (not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)):
            raise ValueError("Usare YYYY-MM-DD")
        return value


@router.patch("/cte-offers/{offer_id}")
def edit_cte(offer_id: str, payload: CteOfferPatch, user: CurrentUser = Depends(current_user)):
    try:
        if not update_cte_offer(offer_id, payload.dict(exclude_unset=True), tenant_id=user.tenant_id):
            raise HTTPException(status_code=404, detail="CTE non trovata")
        return {"status": "updated", "id": offer_id}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except UsageLimitError as error:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content=error.payload())
    except ConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
