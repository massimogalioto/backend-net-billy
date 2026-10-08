-- Apply manually on Railway before deploying usage/limit enforcement.
CREATE TABLE IF NOT EXISTS comparison_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    user_id uuid NOT NULL REFERENCES users(id),
    supply_type character varying(32),
    created_at timestamp with time zone NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS comparison_events_tenant_created_at_idx
    ON comparison_events (tenant_id, created_at);
