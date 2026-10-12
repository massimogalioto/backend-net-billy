-- Solo staging, dopo import e dopo seed. Fallisce se una tabella attesa manca.
SELECT current_database(), inet_server_addr(), inet_server_port();
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['tenants','users','plans','subscriptions','cte_offers',
                           'market_prices','auth_sessions','comparison_events'] LOOP
    IF to_regclass('public.' || t) IS NULL THEN
      RAISE EXCEPTION 'Tabella mancante: %', t;
    END IF;
  END LOOP;
END $$;
-- Tutte le tabelle applicative, anche quelle non note al repository.
DO $$
DECLARE r record; populated boolean;
BEGIN
  FOR r IN SELECT n.nspname, c.relname FROM pg_class c
           JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE c.relkind IN ('r','p','m') AND n.nspname NOT LIKE 'pg_%'
             AND n.nspname <> 'information_schema'
             AND NOT (n.nspname = 'public' AND c.relname = 'plans') LOOP
    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I.%I)', r.nspname, r.relname) INTO populated;
    IF populated THEN RAISE EXCEPTION 'Tabella non vuota: %.%', r.nspname, r.relname; END IF;
  END LOOP;
END $$;
SELECT code, name, monthly_price, max_active_cte, max_monthly_comparisons, active
FROM public.plans ORDER BY code;
SELECT expected.*, p.id, p.active,
       (p.monthly_price = expected.price AND p.max_active_cte = expected.cte
        AND p.max_monthly_comparisons = expected.comparisons AND p.active) AS matches
FROM (VALUES ('FREE', 0.00::numeric, 2, 4), ('START',14.99,20,120),
             ('TOP',45.00,100,300)) AS expected(code, price, cte, comparisons)
LEFT JOIN public.plans p ON p.code = expected.code ORDER BY expected.code;
DO $$
BEGIN
  -- Lo schema appena importato ha zero piani; dopo seed devono essere esattamente tre.
  IF EXISTS (SELECT 1 FROM public.plans) THEN
    IF (SELECT count(*) FROM public.plans) <> 3 OR EXISTS (
      SELECT 1 FROM (VALUES ('FREE',0.00::numeric,2,4),('START',14.99,20,120),
                           ('TOP',45.00,100,300)) AS e(code,price,cte,comparisons)
      LEFT JOIN public.plans p ON p.code=e.code
      WHERE p.code IS NULL OR p.monthly_price IS DISTINCT FROM e.price
         OR p.max_active_cte IS DISTINCT FROM e.cte
         OR p.max_monthly_comparisons IS DISTINCT FROM e.comparisons
         OR p.active IS DISTINCT FROM true
    ) THEN RAISE EXCEPTION 'Piani non conformi o duplicati'; END IF;
  END IF;
END $$;
