-- Execute manually on Railway BEFORE deploying the updated PUN importer/reader.
ALTER TABLE market_prices
ADD COLUMN IF NOT EXISTS observation_count INTEGER NULL;

-- Identify historical rows requiring GME reimport; do not backfill a synthetic 24.
SELECT reference_date, observation_count
FROM market_prices
WHERE market = 'PUN'
  AND (observation_count IS NULL OR observation_count NOT IN (23, 24, 25))
ORDER BY reference_date;
