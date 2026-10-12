-- Candidato condizionale: esaminare PRIMA inspect_schema.sql e il DDL reale.
-- Non ricostruisce la tabella. Il wrapper imposta net_billy.target dopo conferma.
-- Eseguire solo tramite procedure.py seed (transazione unica, ON_ERROR_STOP).
DO $$
DECLARE r record;
BEGIN
  IF current_setting('net_billy.target', true) IS DISTINCT FROM 'staging' THEN
    RAISE EXCEPTION 'Destinazione staging non confermata';
  END IF;
  IF to_regclass('public.plans') IS NULL THEN RAISE EXCEPTION 'plans mancante'; END IF;
  FOR r IN SELECT * FROM (VALUES
      ('code','text'), ('name','text'), ('monthly_price','numeric'),
      ('max_active_cte','integer'), ('max_monthly_comparisons','integer'),
      ('active','boolean')) AS required(col, kind) LOOP
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns c
      WHERE c.table_schema = 'public' AND c.table_name = 'plans' AND c.column_name = r.col
        AND ((r.kind = 'text' AND c.data_type IN ('text','character varying'))
          OR (r.kind = 'integer' AND c.data_type IN ('smallint','integer','bigint'))
          OR c.data_type = r.kind)
        AND c.is_generated = 'NEVER' AND c.is_identity = 'NO'
    ) THEN RAISE EXCEPTION 'Colonna plans.% assente o incompatibile: riesaminare DDL', r.col; END IF;
  END LOOP;
  IF EXISTS (SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'plans'
        AND column_name NOT IN ('code','name','monthly_price','max_active_cte','max_monthly_comparisons','active')
        AND is_nullable = 'NO' AND column_default IS NULL
        AND is_identity = 'NO' AND is_generated = 'NEVER') THEN
    RAISE EXCEPTION 'plans richiede ulteriori colonne senza default: riesaminare DDL';
  END IF;
END $$;
LOCK TABLE public.plans IN EXCLUSIVE MODE;
DO $$
BEGIN
  IF EXISTS (SELECT lower(code) FROM public.plans GROUP BY lower(code) HAVING count(*) > 1) THEN
    RAISE EXCEPTION 'Codici piano duplicati';
  END IF;
  IF EXISTS (SELECT 1 FROM public.plans p
      JOIN (VALUES ('FREE',0.00::numeric,2,4),('START',14.99,20,120),('TOP',45.00,100,300))
        AS e(code,price,cte,comparisons) ON lower(p.code) = lower(e.code)
      WHERE p.code IS DISTINCT FROM e.code OR p.monthly_price IS DISTINCT FROM e.price
         OR p.max_active_cte IS DISTINCT FROM e.cte
         OR p.max_monthly_comparisons IS DISTINCT FROM e.comparisons
         OR p.active IS DISTINCT FROM true) THEN
    RAISE EXCEPTION 'Piano esistente differente: nessuna modifica automatica';
  END IF;
END $$;
INSERT INTO public.plans (code, name, monthly_price, max_active_cte, max_monthly_comparisons, active)
SELECT e.code, e.name, e.price, e.cte, e.comparisons, true
FROM (VALUES ('FREE','NET BILLY FREE',0.00::numeric,2,4),
             ('START','NET BILLY START',14.99,20,120),
             ('TOP','NET BILLY TOP',45.00,100,300)) AS e(code,name,price,cte,comparisons)
WHERE NOT EXISTS (SELECT 1 FROM public.plans p WHERE p.code = e.code);
