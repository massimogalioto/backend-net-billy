-- Additive migration: existing tenants/users/plans/subscriptions are preserved.
CREATE TABLE IF NOT EXISTS auth_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash text NOT NULL UNIQUE,
    user_id uuid NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS auth_sessions_active_token_idx
    ON auth_sessions (token_hash) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS subscriptions_tenant_active_idx
    ON subscriptions (tenant_id, created_at DESC) WHERE status IN ('active', 'trial', 'demo');
