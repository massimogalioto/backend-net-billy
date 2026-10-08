import re
from fastapi import APIRouter, Cookie, Depends, Response
from pydantic import BaseModel, Field, validator
from auth_service import SESSION_COOKIE, auth_payload, current_user, login, logout, register, set_session_cookie

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class RegisterInput(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=1024)

    @validator("company_name", "name")
    def required_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Campo obbligatorio")
        return value

    @validator("email")
    def normalized_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Email non valida")
        return value


@router.post("/login")
def auth_login(payload: LoginInput, response: Response):
    user, token = login(payload.email, payload.password)
    set_session_cookie(response, token)
    return auth_payload(user)


@router.post("/register", status_code=201)
def auth_register(payload: RegisterInput, response: Response):
    user, token = register(company_name=payload.company_name, name=payload.name,
                           email=payload.email, password=payload.password)
    set_session_cookie(response, token)
    return auth_payload(user)


@router.post("/logout", status_code=204)
def auth_logout(response: Response, session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    logout(response, session_token)


@router.get("/me")
def auth_me(user=Depends(current_user)):
    return auth_payload(user)
