"""Authenticated billing endpoints and public signed Stripe webhook."""
import os
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from auth_service import CurrentUser, current_user
from billing_service import (BillingError, billing_status, construct_event,
                             create_checkout, create_portal, process_event)
from database_service import ConfigurationError

router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutInput(BaseModel):
    plan: str


def _canonical_origin(value: str) -> str:
    parsed = urlsplit(value.strip())
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def require_billing_origin(origin: str | None = Header(default=None)) -> None:
    allowed = {os.getenv("NET_BILLY_FRONTEND_URL", "")}
    allowed.update(os.getenv("AUTH_ALLOWED_ORIGINS", "").split(","))
    allowed = {_canonical_origin(value) for value in allowed if value.strip()}
    if not origin or _canonical_origin(origin) not in allowed:
        raise HTTPException(status_code=403, detail="Origin non autorizzata")


def _raise_public(error: Exception):
    if isinstance(error, BillingError):
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    if isinstance(error, ConfigurationError):
        raise HTTPException(status_code=503, detail=str(error)) from error
    raise error


@router.post("/checkout", dependencies=[Depends(require_billing_origin)])
def checkout(payload: CheckoutInput, user: CurrentUser = Depends(current_user)):
    try:
        return create_checkout(user.tenant_id, user.email, user.tenant_name, payload.plan)
    except (BillingError, ConfigurationError) as error:
        _raise_public(error)


@router.get("/status")
def status(user: CurrentUser = Depends(current_user)):
    try:
        return billing_status(user.tenant_id)
    except (BillingError, ConfigurationError) as error:
        _raise_public(error)


@router.post("/portal", dependencies=[Depends(require_billing_origin)])
def portal(user: CurrentUser = Depends(current_user)):
    try:
        return create_portal(user.tenant_id)
    except (BillingError, ConfigurationError) as error:
        _raise_public(error)


@router.post("/webhook")
async def webhook(request: Request, stripe_signature: str | None = Header(default=None, alias="Stripe-Signature")):
    payload = await request.body()
    try:
        event = construct_event(payload, stripe_signature)
        processed = process_event(event)
        return {"received": True, "duplicate": not processed}
    except BillingError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    except ConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
