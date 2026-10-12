-- Cataloghi soltanto: nessuna riga applicativa di production.
SELECT current_database() AS database, inet_server_addr() AS server_address,
       inet_server_port() AS server_port, current_setting('server_version') AS version;
SELECT nspname FROM pg_namespace
WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema' ORDER BY 1;
SELECT table_schema, table_name, column_name, data_type, udt_name,
       is_nullable, column_default, is_identity, identity_generation,
       is_generated, generation_expression
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;
SELECT n.nspname, c.relname, con.conname, pg_get_constraintdef(con.oid)
FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT LIKE 'pg_%' ORDER BY 1, 2, 3;
SELECT schemaname, tablename, indexname, indexdef FROM pg_indexes
WHERE schemaname NOT LIKE 'pg_%' ORDER BY 1, 2, 3;
-- Non legge last_value o valori correnti delle sequence.
SELECT sequence_schema, sequence_name, data_type, start_value, minimum_value,
       maximum_value, increment, cycle_option
FROM information_schema.sequences ORDER BY 1, 2;
SELECT n.nspname, t.typname, e.enumlabel, e.enumsortorder
FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
JOIN pg_enum e ON e.enumtypid = t.oid ORDER BY 1, 2, 4;
SELECT extname, extversion FROM pg_extension ORDER BY 1;
SELECT n.nspname, c.relname, c.relkind, c.relrowsecurity, c.relforcerowsecurity
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
ORDER BY 1, 2;
