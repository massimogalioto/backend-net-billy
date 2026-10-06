-- Run once against the existing Railway PostgreSQL database.
ALTER TABLE cte_offers
    ADD COLUMN IF NOT EXISTS min_power_kw NUMERIC NULL,
    ADD COLUMN IF NOT EXISTS max_power_kw NUMERIC NULL;
