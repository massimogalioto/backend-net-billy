from fastapi import APIRouter, Depends, HTTPException

from auth_service import CurrentUser, current_user
from database_service import ConfigurationError
from plan_service import usage

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/usage")
def account_usage(user: CurrentUser = Depends(current_user)):
    try:
        return usage(user.tenant_id)
    except ConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
