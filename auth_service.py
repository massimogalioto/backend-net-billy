"""Cookie session authentication and trusted tenant resolution."""
import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Cookie, Depends, HTTPException, Response
from psycopg.errors import UniqueViolation

from database_service import _connection

SESSION_COOKIE = "net_billy_session"
_hasher = PasswordHasher()


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    name: str
    tenant_id: str
    tenant_name: str
    plan_code: str | None
    plan_name: str | None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def _expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=int(os.getenv("SESSION_TTL_HOURS", "12")))


def _cookie_options() -> dict:
    return {"httponly": True, "secure": True, "samesite": "none", "path": "/", "max_age": int(os.getenv("SESSION_TTL_HOURS", "12")) * 3600}


def create_session(user_id: str) -> str:
    """Create an opaque session, storing only its SHA-256 digest in PostgreSQL."""
    token = secrets.token_urlsafe(48)
    with _connection() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                    (hashlib.sha256(token.encode()).hexdigest(), user_id, _expiry()))
    return token


def login(email: str, password: str) -> tuple[CurrentUser, str]:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT u.id, u.email, u.first_name, u.last_name, u.password_hash, u.tenant_id,
                              t.company_name, p.code AS plan_code, p.name AS plan_name
                       FROM users u JOIN tenants t ON t.id = u.tenant_id
                       LEFT JOIN subscriptions s ON s.tenant_id = u.tenant_id
                         AND s.status IN ('active', 'trial', 'demo')
                       LEFT JOIN plans p ON p.id = s.plan_id
                       WHERE lower(u.email) = lower(%s) AND u.is_active = TRUE AND t.status = 'active'
                       ORDER BY s.created_at DESC NULLS LAST LIMIT 1""", (email.strip(),))
        row = cur.fetchone()
        if not row or not verify_password(row["password_hash"], password):
            raise HTTPException(status_code=401, detail="Email o password non validi")
        cur.execute("UPDATE users SET last_login_at = NOW() WHERE id = %s", (row["id"],))
        user = _row_to_user(row)
    return user, create_session(user.id)


def register(*, company_name: str, name: str, email: str, password: str) -> tuple[CurrentUser, str]:
    """Create tenant, operator and FREE subscription in one database transaction."""
    normalized_email = email.strip().lower()
    first_name, _, last_name = name.strip().partition(" ")
    try:
        with _connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE lower(email) = lower(%s)", (normalized_email,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Email già registrata")
            cur.execute("SELECT id, code, name FROM plans WHERE code = 'FREE' AND active = TRUE")
            plan = cur.fetchone()
            if not plan:
                raise ConfigurationError("Piano FREE non configurato")
            cur.execute("INSERT INTO tenants (company_name, email, status) VALUES (%s, %s, 'active') RETURNING id, company_name",
                        (company_name.strip(), normalized_email))
            tenant = cur.fetchone()
            cur.execute("""INSERT INTO users
                           (tenant_id, first_name, last_name, email, password_hash, role, is_active, email_verified)
                           VALUES (%s, %s, %s, %s, %s, 'operator', TRUE, FALSE)
                           RETURNING id, email, first_name, last_name, tenant_id""",
                        (tenant["id"], first_name, last_name, normalized_email, hash_password(password)))
            created = cur.fetchone()
            cur.execute("""INSERT INTO subscriptions
                           (tenant_id, plan_id, status, started_at, created_at, updated_at)
                           VALUES (%s, %s, 'active', NOW(), NOW(), NOW())""",
                        (tenant["id"], plan["id"]))
            user = CurrentUser(id=str(created["id"]), email=created["email"],
                               name=" ".join(item for item in (created["first_name"], created["last_name"]) if item),
                               tenant_id=str(tenant["id"]), tenant_name=tenant["company_name"],
                               plan_code=plan["code"], plan_name=plan["name"])
    except UniqueViolation as error:
        raise HTTPException(status_code=409, detail="Email già registrata") from error
    return user, create_session(user.id)


def _row_to_user(row) -> CurrentUser:
    return CurrentUser(id=str(row["id"]), email=row["email"],
                       name=" ".join(item for item in (row["first_name"], row["last_name"]) if item),
                       tenant_id=str(row["tenant_id"]), tenant_name=row["company_name"],
                       plan_code=row.get("plan_code"), plan_name=row.get("plan_name"))


def current_user(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> CurrentUser:
    if not session_token:
        raise HTTPException(status_code=401, detail="Autenticazione richiesta")
    with _connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT u.id, u.email, u.first_name, u.last_name, u.tenant_id, t.company_name,
                              p.code AS plan_code, p.name AS plan_name
                       FROM auth_sessions a JOIN users u ON u.id = a.user_id
                       JOIN tenants t ON t.id = u.tenant_id
                       LEFT JOIN subscriptions s ON s.tenant_id = u.tenant_id
                         AND s.status IN ('active', 'trial', 'demo')
                       LEFT JOIN plans p ON p.id = s.plan_id
                       WHERE a.token_hash = %s AND a.revoked_at IS NULL AND a.expires_at > NOW()
                         AND u.is_active = TRUE AND t.status = 'active'
                       ORDER BY s.created_at DESC NULLS LAST LIMIT 1""",
                    (hashlib.sha256(session_token.encode()).hexdigest(),))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Autenticazione richiesta")
    return _row_to_user(row)


def logout(response: Response, session_token: str | None) -> None:
    if session_token:
        with _connection() as conn, conn.cursor() as cur:
            cur.execute("UPDATE auth_sessions SET revoked_at = NOW() WHERE token_hash = %s",
                        (hashlib.sha256(session_token.encode()).hexdigest(),))
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="none")


def auth_payload(user: CurrentUser) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name,
            "tenant": {"id": user.tenant_id, "name": user.tenant_name},
            "plan": {"code": user.plan_code, "name": user.plan_name}}


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, **_cookie_options())
