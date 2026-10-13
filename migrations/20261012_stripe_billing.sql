-- Additive migration for NET BILLY Stripe Billing. Run manually on staging.
-- It does not add Stripe columns to the application entitlement table.
CREATE TABLE billing_customers (
    tenant_id uuid PRIMARY KEY REFERENCES tenants(id),
    stripe_customer_id text NOT NULL UNIQUE,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE billing_subscriptions (
    tenant_id uuid PRIMARY KEY REFERENCES tenants(id),
    stripe_subscription_id text NOT NULL UNIQUE,
    stripe_status text NOT NULL,
    plan_code text,
    current_period_start timestamp with time zone,
    current_period_end timestamp with time zone,
    cancel_at_period_end boolean NOT NULL DEFAULT false,
    payment_grace_until timestamp with time zone,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT billing_subscriptions_plan_code_check
        CHECK (plan_code IS NULL OR plan_code IN ('START', 'TOP'))
);

CREATE TABLE billing_checkout_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    requested_plan_code text NOT NULL,
    stripe_checkout_session_id text NOT NULL UNIQUE,
    idempotency_key text NOT NULL UNIQUE,
    checkout_url text NOT NULL,
    status text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT billing_checkout_sessions_plan_check
        CHECK (requested_plan_code IN ('START', 'TOP')),
    CONSTRAINT billing_checkout_sessions_status_check
        CHECK (status IN ('open', 'complete', 'expired'))
);

CREATE TABLE stripe_webhook_events (
    stripe_event_id text PRIMARY KEY,
    event_type text NOT NULL,
    received_at timestamp with time zone NOT NULL DEFAULT now(),
    processed_at timestamp with time zone
);

CREATE INDEX billing_checkout_sessions_tenant_open_idx
    ON billing_checkout_sessions (tenant_id, created_at DESC)
    WHERE status = 'open';

CREATE INDEX billing_subscriptions_status_idx
    ON billing_subscriptions (stripe_status);

CREATE INDEX stripe_webhook_events_received_at_idx
    ON stripe_webhook_events (received_at);
