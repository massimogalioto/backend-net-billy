-- Additive, one-time migration. Run manually before deploying the feature.
CREATE TABLE IF NOT EXISTS cte_commissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    cte_offer_id UUID NOT NULL REFERENCES cte_offers(id) ON DELETE CASCADE,
    min_contracts INTEGER NOT NULL CHECK (min_contracts >= 0),
    max_contracts INTEGER CHECK (max_contracts IS NULL OR max_contracts >= min_contracts),
    base_amount NUMERIC(12,2) NOT NULL CHECK (base_amount >= 0),
    sepa_bonus NUMERIC(12,2) NOT NULL CHECK (sepa_bonus >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT cte_commissions_unique_range UNIQUE (cte_offer_id, min_contracts, max_contracts)
);

CREATE INDEX IF NOT EXISTS idx_cte_commissions_tenant_offer
    ON cte_commissions (tenant_id, cte_offer_id, min_contracts);

-- PostgreSQL UNIQUE treats NULL values as distinct. This expression also
-- prevents duplicate open-ended ranges for the same CTE.
CREATE UNIQUE INDEX IF NOT EXISTS uq_cte_commissions_range_including_open_end
    ON cte_commissions (cte_offer_id, min_contracts, COALESCE(max_contracts, -1));

-- Prevent a row from linking a tenant to another tenant's CTE, including direct SQL writes.
CREATE OR REPLACE FUNCTION enforce_cte_commission_tenant() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM cte_offers
        WHERE id = NEW.cte_offer_id AND tenant_id = NEW.tenant_id
    ) THEN
        RAISE EXCEPTION 'cte_offer_id does not belong to tenant_id';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cte_commissions_tenant ON cte_commissions;
CREATE TRIGGER trg_cte_commissions_tenant
    BEFORE INSERT OR UPDATE ON cte_commissions
    FOR EACH ROW EXECUTE FUNCTION enforce_cte_commission_tenant();

