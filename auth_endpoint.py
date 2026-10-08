from fastapi import APIRouter, Cookie, Depends, Response
from pydantic import BaseModel, Field
from auth_service import SESSION_COOKIE, auth_payload, current_user, login, logout, set_session_cookie

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


@router.post("/login")
def auth_login(payload: LoginInput, response: Response):
    user, token = login(payload.email, payload.password)
    set_session_cookie(response, token)
    return auth_payload(user)


@router.post("/logout", status_code=204)
def auth_logout(response: Response, session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    logout(response, session_token)


@router.get("/me")
def auth_me(user=Depends(current_user)):
    return auth_payload(user)
