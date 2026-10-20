"""Stripe Billing integration with tenant-scoped ownership and webhook idempotency."""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import stripe

from database_service import ConfigurationError, _connection


ALLOWED_PLANS = {"START", "TOP"}
LIVE_SUBSCRIPTION_STATUSES = {"active", "trialing", "past_due", "unpaid", "paused"}
API_VERSION = "2026-08-26.dahlia"
CHECKOUT_CONFIGURATION_PREFIX = "tax-v1-"


class BillingError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} non configurato")
    return value


def _settings() -> dict[str, Any]:
    mode = os.getenv("STRIPE_MODE", "test").strip().lower()
    if mode not in {"test", "live"}:
        raise ConfigurationError("STRIPE_MODE deve essere test o live")
    grace_raw = os.getenv("STRIPE_PAYMENT_GRACE_DAYS", "7")
    try:
        grace_days = int(grace_raw)
    except ValueError as error:
        raise ConfigurationError("STRIPE_PAYMENT_GRACE_DAYS non valido") from error
    if not 0 <= grace_days <= 90:
        raise ConfigurationError("STRIPE_PAYMENT_GRACE_DAYS deve essere tra 0 e 90")
    return {
        "secret_key": _required_env("STRIPE_SECRET_KEY"),
        "webhook_secret": _required_env("STRIPE_WEBHOOK_SECRET"),
        "frontend_url": _required_env("NET_BILLY_FRONTEND_URL").rstrip("/"),
        "prices": {
            "START": _required_env("STRIPE_START_PRICE_ID"),
            "TOP": _required_env("STRIPE_TOP_PRICE_ID"),
        },
        "mode": mode,
        "grace_days": grace_days,
    }


def _stripe_client(settings: dict[str, Any] | None = None):
    settings = settings or _settings()
    return stripe.StripeClient(settings["secret_key"], stripe_version=API_VERSION)


def _create(resource, params: dict[str, Any], idempotency_key: str | None = None):
    options = {"idempotency_key": idempotency_key} if idempotency_key else None
    if options:
        return resource.create(params, options)
    return resource.create(params)


def _as_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "to_dict_recursive"):
        return obj.to_dict_recursive()
    return dict(obj)


def _lock_tenant(cur, tenant_id: str) -> None:
    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"billing:{tenant_id}",))


def _customer_for_tenant(cur, client, tenant_id: str, email: str, tenant_name: str) -> str:
    cur.execute("SELECT stripe_customer_id FROM billing_customers WHERE tenant_id = %s", (tenant_id,))
    row = cur.fetchone()
    if row:
        return row["stripe_customer_id"]
    customer = _create(
        client.v1.customers,
        {"email": email, "name": tenant_name},
        f"net-billy-customer-{tenant_id}",
    )
    customer_id = _as_dict(customer)["id"]
    cur.execute(
        """INSERT INTO billing_customers (tenant_id, stripe_customer_id)
           VALUES (%s, %s)
           ON CONFLICT (tenant_id) DO NOTHING
           RETURNING stripe_customer_id""",
        (tenant_id, customer_id),
    )
    inserted = cur.fetchone()
    if inserted:
        return inserted["stripe_customer_id"]
    cur.execute("SELECT stripe_customer_id FROM billing_customers WHERE tenant_id = %s", (tenant_id,))
    return cur.fetchone()["stripe_customer_id"]


def create_checkout(tenant_id: str, email: str, tenant_name: str, plan_code: str,
                    *, client=None) -> dict[str, str]:
    plan_code = plan_code.strip().upper()
    if plan_code not in ALLOWED_PLANS:
        raise BillingError("Piano acquistabile non valido")
    settings = _settings()
    client = client or _stripe_client(settings)
    with _connection() as conn, conn.cursor() as cur:
        _lock_tenant(cur, tenant_id)
        cur.execute(
            """SELECT stripe_subscription_id FROM billing_subscriptions
               WHERE tenant_id = %s AND stripe_status = ANY(%s)""",
            (tenant_id, list(LIVE_SUBSCRIPTION_STATUSES)),
        )
        if cur.fetchone():
            raise BillingError("Esiste gia un abbonamento Stripe per questo account", 409)
        cur.execute(
            """SELECT stripe_checkout_session_id, checkout_url, status FROM billing_checkout_sessions
               WHERE tenant_id = %s AND requested_plan_code = %s
                 AND status IN ('open', 'complete') AND expires_at > NOW()
                 AND idempotency_key LIKE %s
               ORDER BY created_at DESC LIMIT 1""",
            (tenant_id, plan_code, f"{CHECKOUT_CONFIGURATION_PREFIX}%"),
        )
        existing = cur.fetchone()
        if existing:
            if existing["status"] == "complete":
                raise BillingError("Checkout gia completato; attendere la sincronizzazione", 409)
            return {"checkout_url": existing["checkout_url"]}
        customer_id = _customer_for_tenant(cur, client, tenant_id, email, tenant_name)
        attempt_id = f"{CHECKOUT_CONFIGURATION_PREFIX}{secrets.token_urlsafe(24)}"
        session = _create(
            client.v1.checkout.sessions,
            {
                "mode": "subscription",
                "customer": customer_id,
                "automatic_tax": {"enabled": True},
                "billing_address_collection": "required",
                "customer_update": {"address": "auto", "name": "auto"},
                "tax_id_collection": {"enabled": True},
                "line_items": [{"price": settings["prices"][plan_code], "quantity": 1}],
                "success_url": f"{settings['frontend_url']}/dashboard?checkout=success",
                "cancel_url": f"{settings['frontend_url']}/dashboard?checkout=cancelled",
                "client_reference_id": attempt_id,
                "subscription_data": {"metadata": {"net_billy_checkout": attempt_id}},
                "integration_identifier": f"netbilly_{secrets.token_hex(4)}",
            },
            f"net-billy-checkout-{attempt_id}",
        )
        data = _as_dict(session)
        expires_at = datetime.fromtimestamp(data["expires_at"], timezone.utc)
        cur.execute(
            """INSERT INTO billing_checkout_sessions
               (tenant_id, requested_plan_code, stripe_checkout_session_id,
                idempotency_key, checkout_url, status, expires_at)
               VALUES (%s, %s, %s, %s, %s, 'open', %s)""",
            (tenant_id, plan_code, data["id"], attempt_id, data["url"], expires_at),
        )
        return {"checkout_url": data["url"]}


def create_portal(tenant_id: str, *, client=None) -> dict[str, str]:
    settings = _settings()
    client = client or _stripe_client(settings)
    with _connection() as conn, conn.cursor() as cur:
        _lock_tenant(cur, tenant_id)
        cur.execute("SELECT stripe_customer_id FROM billing_customers WHERE tenant_id = %s", (tenant_id,))
        row = cur.fetchone()
        if not row:
            raise BillingError("Account di fatturazione non ancora disponibile", 404)
        session = _create(client.v1.billing_portal.sessions, {
            "customer": row["stripe_customer_id"],
            "return_url": f"{settings['frontend_url']}/dashboard",
        })
        return {"portal_url": _as_dict(session)["url"]}


def billing_status(tenant_id: str) -> dict[str, Any]:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT p.code AS plan_code, p.name AS plan_name, s.status AS plan_status,
                      bs.stripe_status, bs.current_period_end, bs.cancel_at_period_end,
                      bs.payment_grace_until
               FROM subscriptions s JOIN plans p ON p.id = s.plan_id
               LEFT JOIN billing_subscriptions bs ON bs.tenant_id = s.tenant_id
               WHERE s.tenant_id = %s AND s.status = 'active'
               ORDER BY s.created_at DESC LIMIT 1""",
            (tenant_id,),
        )
        row = cur.fetchone()
        if not row:
            raise BillingError("Nessun piano attivo associato all'account", 404)
        return {key: row[key] for key in row}


def construct_event(payload: bytes, signature: str | None) -> dict[str, Any]:
    if not signature:
        raise BillingError("Firma webhook mancante", 400)
    try:
        event = stripe.Webhook.construct_event(payload, signature, _settings()["webhook_secret"])
    except (ValueError, stripe.error.SignatureVerificationError) as error:
        raise BillingError("Firma webhook non valida", 400) from error
    return _as_dict(event)


def _timestamp(value: int | None) -> datetime | None:
    return datetime.fromtimestamp(value, timezone.utc) if value else None


def _plan_for_price(settings: dict[str, Any], price_id: str | None) -> str | None:
    return next((code for code, configured in settings["prices"].items() if configured == price_id), None)


def _subscription_price(subscription: dict[str, Any]) -> str | None:
    items = subscription.get("items", {}).get("data", [])
    if len(items) != 1:
        return None
    price = items[0].get("price") or {}
    return price.get("id") if isinstance(price, dict) else getattr(price, "id", None)


def _subscription_period(subscription: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    """Dahlia exposes billing periods on subscription items; accept older payloads too."""
    start = subscription.get("current_period_start")
    end = subscription.get("current_period_end")
    items = subscription.get("items", {}).get("data", [])
    if items:
        start = start or min((item.get("current_period_start") for item in items
                              if item.get("current_period_start")), default=None)
        end = end or max((item.get("current_period_end") for item in items
                          if item.get("current_period_end")), default=None)
    return _timestamp(start), _timestamp(end)


def _invoice_subscription_id(invoice: dict[str, Any]) -> str | None:
    if invoice.get("subscription"):
        return invoice["subscription"]
    return (invoice.get("parent", {}).get("subscription_details", {}) or {}).get("subscription")


def _set_app_plan(cur, tenant_id: str, plan_code: str,
                  period_start: datetime | None = None, period_end: datetime | None = None) -> None:
    cur.execute("SELECT id FROM plans WHERE code = %s AND active = TRUE", (plan_code,))
    plan = cur.fetchone()
    if not plan:
        raise ConfigurationError(f"Piano {plan_code} non configurato")
    cur.execute(
        "SELECT id FROM subscriptions WHERE tenant_id = %s AND status = 'active' ORDER BY created_at DESC FOR UPDATE",
        (tenant_id,),
    )
    active_rows = cur.fetchall()
    if len(active_rows) > 1:
        raise ConfigurationError("Sono presenti piu subscription applicative attive per il tenant")
    if active_rows:
        selected_id = active_rows[0]["id"]
    else:
        cur.execute("SELECT id FROM subscriptions WHERE tenant_id = %s ORDER BY created_at DESC LIMIT 1 FOR UPDATE", (tenant_id,))
        previous = cur.fetchone()
        selected_id = previous["id"] if previous else None
    if selected_id is None:
        cur.execute(
            """INSERT INTO subscriptions
               (tenant_id, plan_id, status, started_at, current_period_start,
                current_period_end, created_at, updated_at)
               VALUES (%s, %s, 'active', NOW(), %s, %s, NOW(), NOW())""",
            (tenant_id, plan["id"], period_start, period_end),
        )
        return
    cur.execute(
        """UPDATE subscriptions SET plan_id = %s, status = 'active',
                  started_at = COALESCE(started_at, NOW()), current_period_start = %s,
                  current_period_end = %s, updated_at = NOW()
           WHERE id = %s""",
        (plan["id"], period_start, period_end, selected_id),
    )


def _upsert_subscription(cur, tenant_id: str, subscription: dict[str, Any],
                         plan_code: str | None, grace_until: datetime | None = None) -> None:
    period_start, period_end = _subscription_period(subscription)
    cancel_scheduled = bool(
        subscription.get("cancel_at_period_end")
        or subscription.get("cancel_at")
    )
    cur.execute(
        """INSERT INTO billing_subscriptions
           (tenant_id, stripe_subscription_id, stripe_status, plan_code,
            current_period_start, current_period_end, cancel_at_period_end,
            payment_grace_until, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
           ON CONFLICT (tenant_id) DO UPDATE SET
             stripe_subscription_id = EXCLUDED.stripe_subscription_id,
             stripe_status = EXCLUDED.stripe_status, plan_code = EXCLUDED.plan_code,
             current_period_start = EXCLUDED.current_period_start,
             current_period_end = EXCLUDED.current_period_end,
             cancel_at_period_end = EXCLUDED.cancel_at_period_end,
             payment_grace_until = COALESCE(EXCLUDED.payment_grace_until, billing_subscriptions.payment_grace_until),
             updated_at = NOW()""",
        (tenant_id, subscription["id"], subscription.get("status"), plan_code,
         period_start, period_end,
         cancel_scheduled, grace_until),
    )


def _tenant_for_customer(cur, customer_id: str) -> str:
    cur.execute("SELECT tenant_id FROM billing_customers WHERE stripe_customer_id = %s", (customer_id,))
    row = cur.fetchone()
    if not row:
        raise BillingError("Customer Stripe non associato a NET BILLY", 400)
    return str(row["tenant_id"])


def process_event(event: dict[str, Any], *, client=None) -> bool:
    """Process one verified event transactionally. Return False for a duplicate."""
    settings = _settings()
    expected_livemode = settings["mode"] == "live"
    if bool(event.get("livemode", False)) is not expected_livemode:
        raise BillingError("Evento Stripe ricevuto dall'ambiente errato", 400)
    client = client or _stripe_client(settings)
    event_id, event_type = event["id"], event["type"]
    obj = event["data"]["object"]
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO stripe_webhook_events (stripe_event_id, event_type)
               VALUES (%s, %s) ON CONFLICT (stripe_event_id) DO NOTHING RETURNING stripe_event_id""",
            (event_id, event_type),
        )
        if not cur.fetchone():
            return False

        if event_type.startswith("checkout.session."):
            cur.execute(
                """UPDATE billing_checkout_sessions SET status = %s, updated_at = NOW()
                   WHERE stripe_checkout_session_id = %s""",
                ("complete" if obj.get("status") == "complete" else obj.get("status", "expired"), obj["id"]),
            )
        elif event_type.startswith("customer.subscription."):
            tenant_id = _tenant_for_customer(cur, obj["customer"])
            _lock_tenant(cur, tenant_id)
            plan_code = _plan_for_price(settings, _subscription_price(obj))
            _upsert_subscription(cur, tenant_id, obj, plan_code)
            if event_type == "customer.subscription.deleted" or obj.get("status") == "canceled":
                _set_app_plan(cur, tenant_id, "FREE")
            elif obj.get("status") in {"past_due", "unpaid", "paused"}:
                cur.execute("SELECT payment_grace_until FROM billing_subscriptions WHERE tenant_id = %s", (tenant_id,))
                grace = cur.fetchone()
                if grace and grace["payment_grace_until"] and grace["payment_grace_until"] <= datetime.now(timezone.utc):
                    _set_app_plan(cur, tenant_id, "FREE")
        elif event_type in {"invoice.paid", "invoice.payment_failed"}:
            subscription_id = _invoice_subscription_id(obj)
            customer_id = obj.get("customer")
            if not subscription_id or not customer_id:
                cur.execute("UPDATE stripe_webhook_events SET processed_at = NOW() WHERE stripe_event_id = %s", (event_id,))
                return True
            tenant_id = _tenant_for_customer(cur, customer_id)
            _lock_tenant(cur, tenant_id)
            subscription = _as_dict(client.v1.subscriptions.retrieve(subscription_id))
            plan_code = _plan_for_price(settings, _subscription_price(subscription))
            if not plan_code:
                raise BillingError("Price Stripe non riconosciuto", 400)
            if event_type == "invoice.paid":
                period_start, period_end = _subscription_period(subscription)
                _upsert_subscription(cur, tenant_id, subscription, plan_code)
                cur.execute("UPDATE billing_subscriptions SET payment_grace_until = NULL WHERE tenant_id = %s", (tenant_id,))
                _set_app_plan(cur, tenant_id, plan_code, period_start, period_end)
            else:
                cur.execute("SELECT payment_grace_until FROM billing_subscriptions WHERE tenant_id = %s", (tenant_id,))
                row = cur.fetchone()
                grace_until = (row["payment_grace_until"] if row and row["payment_grace_until"] else
                               datetime.now(timezone.utc) + timedelta(days=settings["grace_days"]))
                _upsert_subscription(cur, tenant_id, subscription, plan_code, grace_until)
                if grace_until <= datetime.now(timezone.utc):
                    _set_app_plan(cur, tenant_id, "FREE")

        cur.execute("UPDATE stripe_webhook_events SET processed_at = NOW() WHERE stripe_event_id = %s", (event_id,))
        return True
