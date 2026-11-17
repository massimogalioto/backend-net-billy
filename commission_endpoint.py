from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, condecimal, conint

from auth_service import CurrentUser, current_user
from commission_service import delete_commissions, list_commissions, replace_commissions
from database_service import ConfigurationError

router = APIRouter(prefix="/cte-commissions", tags=["cte-commissions"])


class BandInput(BaseModel):
    min_contracts: conint(strict=True, ge=0)
    max_contracts: conint(strict=True, ge=0) | None = None
    base_amount: condecimal(ge=Decimal("0"), max_digits=12, decimal_places=2)
    sepa_bonus: condecimal(ge=Decimal("0"), max_digits=12, decimal_places=2)


class QueryInput(BaseModel):
    offer_ids: list[str] = Field(min_items=1, max_items=200)


class ReplaceInput(QueryInput):
    bands: list[BandInput] = Field(min_items=1, max_items=50)
    overwrite: bool = False


@router.post("/query")
def query(payload: QueryInput, user: CurrentUser = Depends(current_user)):
    return {"offers": list_commissions(payload.offer_ids, user.tenant_id)}


@router.put("")
def replace(payload: ReplaceInput, user: CurrentUser = Depends(current_user)):
    try:
        ids = replace_commissions(payload.offer_ids, [band.dict() for band in payload.bands],
                                  user.tenant_id, payload.overwrite)
        return {"status": "updated", "offer_ids": ids}
    except FileExistsError as error:
        raise HTTPException(status_code=409, detail={"message": "Conferma la sovrascrittura", "offer_ids": str(error).split(",")}) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/replace")
def replace_post(payload: ReplaceInput, user: CurrentUser = Depends(current_user)):
    return replace(payload, user)


@router.post("/remove")
def remove_post(payload: QueryInput, user: CurrentUser = Depends(current_user)):
    if len(payload.offer_ids) != 1:
        raise HTTPException(status_code=422, detail="Indicare una sola CTE")
    return remove(payload.offer_ids[0], user)


@router.delete("/{offer_id}")
def remove(offer_id: str, user: CurrentUser = Depends(current_user)):
    try:
        return {"status": "deleted", "deleted": delete_commissions(offer_id, user.tenant_id)}
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

