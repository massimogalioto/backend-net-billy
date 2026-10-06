-- Inspect the live Railway schema BEFORE applying the ALTER TABLE below.
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'market_prices'
ORDER BY ordinal_position;

SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'public.market_prices'::regclass;

SELECT indexname, indexdef FROM pg_indexes
WHERE schemaname = 'public' AND tablename = 'market_prices';

-- Apply if value_eur_smc is missing and/or the PUN columns are still NOT NULL.
-- Existing PUN import already requires UNIQUE (market, reference_date).
-- Check also that any CHECK on market allows both 'PUN' and 'PSV'.
ALTER TABLE market_prices
    ADD COLUMN IF NOT EXISTS value_eur_smc NUMERIC(18, 8),
    ALTER COLUMN value_eur_mwh DROP NOT NULL,
    ALTER COLUMN value_eur_kwh DROP NOT NULL;
