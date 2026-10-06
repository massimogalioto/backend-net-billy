"""Monthly PSV display and manual input; market prices are shared, not tenant scoped."""
from datetime import datetime, date
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from database_service import ConfigurationError, get_psv_month_price, upsert_psv_month_price
from market_price_service import previous_month

router = APIRouter()


def current_month() -> date:
    return datetime.now(ZoneInfo("Europe/Rome")).date().replace(day=1)


class PsvInput(BaseModel):
    mese: str = Field(pattern=r"^\d{4}-\d{2}$")
    value_eur_smc: Decimal = Field(ge=0, allow_inf_nan=False)
    disp: Decimal = Field(ge=0, allow_inf_nan=False)


def serialize_price(month: date, row: dict | None) -> dict:
    return {
        "mese": month.strftime("%Y-%m"),
        "value_eur_smc": float(row["value_eur_smc"]) if row and row["value_eur_smc"] is not None else None,
        "disp": float(row["disp"] or 0) if row else None,
        "totale": float(row["value_eur_smc"] + (row["disp"] or 0))
                  if row and row["value_eur_smc"] is not None else None,
    }


@router.get("/market-prices-psv")
def get_psv_prices():
    month = current_month()
    previous = previous_month(month)
    try:
        return {"previous": serialize_price(previous, get_psv_month_price(previous)),
                "current": serialize_price(month, get_psv_month_price(month))}
    except ConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail="Lettura PSV PostgreSQL non disponibile: verificare lo schema market_prices") from error


@router.post("/market-prices-psv")
def save_psv_price(body: PsvInput):
    month = current_month()
    allowed = {month.strftime("%Y-%m"): month,
               previous_month(month).strftime("%Y-%m"): previous_month(month)}
    if body.mese not in allowed:
        raise HTTPException(status_code=422, detail="È consentito inserire il PSV solo del mese corrente o precedente")
    month = allowed[body.mese]
    try:
        action = upsert_psv_month_price(month, body.value_eur_smc, body.disp)
        return {"successo": True, "action": action,
                **serialize_price(month, {"value_eur_smc": body.value_eur_smc, "disp": body.disp})}
    except ConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail="Salvataggio PSV PostgreSQL non disponibile: verificare lo schema market_prices") from error
