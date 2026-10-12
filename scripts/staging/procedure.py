"""Manual-only staging preparation. No dotenv, Railway CLI or implicit execution."""
import argparse
import getpass
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import warnings

import psycopg
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parent


def require(value, message):
    if not value:
        raise RuntimeError(message)


def connection(label):
    # Prompt hidden: credentials never appear in command arguments or repository.
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        raw = getpass.getpass(f"URL PostgreSQL {label} (input nascosto): ")
    params = conninfo_to_dict(raw)
    allowed = {'host', 'port', 'dbname', 'user', 'password', 'sslmode'}
    require(set(params) <= allowed, 'Parametri URL non supportati; usare URL semplice senza options/service/hostaddr.')
    require(all(params.get(k) for k in ('host', 'dbname', 'user', 'password')), 'URL incompleto.')
    params.setdefault('port', '5432')
    params.setdefault('sslmode', 'require')
    require(params['sslmode'] in ('require', 'verify-ca', 'verify-full'), 'TLS obbligatorio.')
    require(',' not in params['host'] and ',' not in params['port'], 'Endpoint multipli non ammessi.')
    expected = input(f"Da Railway, endpoint {label} atteso (host:porta/database): ").strip()
    endpoint = f"{params['host']}:{params['port']}/{params['dbname']}"
    require(expected == endpoint, 'Endpoint non corrispondente.')
    # No inherited PG* variables: hostaddr/service/options must not redirect calls.
    clean_env = {k: v for k, v in os.environ.items() if not k.upper().startswith('PG')}
    env = dict(clean_env)
    for key, value in params.items():
        env[{'dbname': 'PGDATABASE'}.get(key, 'PG' + key.upper())] = value
    env['PGCONNECT_TIMEOUT'] = '10'
    env['PGOPTIONS'] = '-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=5000'
    # Connect with explicit params; do not inherit process PG variables.
    previous = {k: v for k, v in os.environ.items() if k.upper().startswith('PG')}
    try:
        for k in previous:
            del os.environ[k]
        conn = psycopg.connect(**params, connect_timeout=10,
                               options=env['PGOPTIONS'], autocommit=True)
    finally:
        os.environ.update(previous)
    with conn:
        identity = conn.execute("SELECT current_database(), inet_server_addr()::text, inet_server_port(), current_setting('server_version_num')::int").fetchone()
        require(identity[0] == params['dbname'] and identity[1], 'Identita server non verificabile.')
        print(f"{label}: {endpoint}; server={identity[1]}:{identity[2]}; versione={identity[3]}")
    return params, env, identity, endpoint


def run(command, env, *, sql_input=None):
    require(shutil.which(command[0]), f"Installare {command[0]} e aggiungerlo al PATH.")
    # Do not echo SQL, server errors, connection details or secrets.
    result = subprocess.run(command, env=env, capture_output=True, input=sql_input)
    require(result.returncode == 0, 'Comando PostgreSQL fallito. Nessun dettaglio stampato per evitare esposizione di segreti; verificare localmente con un amministratore.')
    return result.stdout


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def client_major(version, tool):
    # Raw string: single backslashes, no Markdown escaping. Fail on unknown output.
    match = re.fullmatch(
        rf'{re.escape(tool)}[ \t]+\(PostgreSQL\)[ \t]+(?P<major>[0-9]+)(?:\.[0-9]+)*(?:[ \t]+[^\r\n]*)?',
        version.strip(),
    )
    require(match is not None, f'Versione di {tool} non riconosciuta.')
    return int(match.group('major'))


def review_artifact(path, purpose):
    require(path.is_file(), 'Artifact mancante: generarlo prima della revisione.')
    snapshot = path.read_bytes()
    require(snapshot, 'Artifact vuoto: arresto.')
    fingerprint = hashlib.sha256(snapshot).hexdigest()
    print(f'Aprire e revisionare localmente {path}; SHA256: {fingerprint}')
    require(input(f'{purpose} Per confermare la revisione digitare SHA256: ').strip() == fingerprint,
            'Revisione artifact non confermata.')
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['inspect', 'export', 'import', 'seed', 'verify'])
    parser.add_argument('--schema', type=Path)
    args = parser.parse_args()
    require(shutil.which('psql'), 'psql non disponibile nel PATH.')
    if args.action == 'export':
        require(shutil.which('pg_dump'), 'pg_dump non disponibile nel PATH.')
    artifact_dir = ROOT / 'artifacts'
    artifact_dir.mkdir(exist_ok=True)
    prod = connection('production')
    stage = connection('staging')
    require(prod[3] != stage[3], 'Endpoint identici: arresto.')
    require(prod[2][1:3] != stage[2][1:3], 'Stessa istanza server: arresto, anche con database diversi.')
    require(prod[2][3] // 10000 == stage[2][3] // 10000, 'Versioni major differenti: revisione DBA necessaria.')
    for tool in (['psql', 'pg_dump'] if args.action == 'export' else ['psql']):
        version = run([tool, '--version'], prod[1]).decode('utf-8', errors='replace')
        require(client_major(version, tool) == prod[2][3] // 10000,
                f'La major del client {tool} deve corrispondere ai server.')
    # Database identity alone does not prove a Railway environment. Human cross-check mandatory.
    prod_id = input('Da Railway: ID servizio PostgreSQL production: ').strip()
    stage_id = input('Da Railway: ID servizio PostgreSQL staging: ').strip()
    require(prod_id and stage_id and prod_id != stage_id, 'Servizi non distinti.')
    require(input('Confermi di aver verificato progetto, ambienti e servizi in Railway? Scrivi VERIFICATO: ') == 'VERIFICATO', 'Ambienti non confermati.')
    if args.action == 'inspect':
        target = artifact_dir / 'production-catalog.txt'
        require(not target.exists(), 'Report gia presente; conservarlo o spostarlo manualmente.')
        output = run(['psql', '-X', '--no-password', '-v', 'ON_ERROR_STOP=1', '-f', str(ROOT / 'inspect_schema.sql')], prod[1])
        with target.open('xb') as artifact:
            artifact.write(output)
        print('Catalogo generato, riservato e NON ancora approvato:', target)
        print('Revisionarlo localmente prima di export/seed. Puo contenere letterali sensibili; non condividerlo.')
        return
    if args.action == 'export':
        target = artifact_dir / 'production-schema.sql'
        require(not target.exists(), 'Dump gia presente; nessuna sovrascrittura.')
        review_artifact(artifact_dir / 'production-catalog.txt',
                        'Verificare struttura e assenza di segreti nel catalogo gia generato.')
        require(input('DDL verificato: nessun segreto in default/funzioni/FDW/user mapping. Scrivi DDL SENZA SEGRETI: ') == 'DDL SENZA SEGRETI', 'Revisione DDL obbligatoria.')
        foreign_count = run(['psql', '-X', '--no-password', '-At', '-v', 'ON_ERROR_STOP=1', '-c',
                             'SELECT (SELECT count(*) FROM pg_foreign_server) + (SELECT count(*) FROM pg_user_mapping);'], prod[1])
        require(foreign_count.strip() == b'0', 'FDW/user mapping presenti: possibile esportazione credenziali, arresto per revisione DBA.')
        output = run(['pg_dump', '--no-password', '--schema-only', '--no-owner', '--no-acl',
                      '--no-comments', '--no-security-labels', '--no-tablespaces',
                      '--no-publications', '--no-subscriptions', '--lock-wait-timeout=5s'], prod[1])
        with target.open('xb') as artifact:
            artifact.write(output)
        print('Dump locale riservato:', target, 'SHA256:', digest(target))
        return
    if args.action == 'verify':
        output = run(['psql', '-X', '--no-password', '-v', 'ON_ERROR_STOP=1', '-f', str(ROOT / 'verify.sql')], stage[1])
        print(output.decode('utf-8', errors='replace'))
        return
    if args.action == 'import':
        require(args.schema and args.schema.is_file(), 'Specificare --schema con dump gia revisionato.')
        sql_file = args.schema.resolve()
        sql_snapshot = review_artifact(sql_file, 'Verificare il dump prima di qualsiasi importazione.')
        require(input('Dump revisionato: schema soltanto, nessun segreto, estensioni compatibili, nessun reconnect o SQL distruttivo. Scrivi REVISIONATO: ') == 'REVISIONATO', 'Revisione mancante.')
        # Permit public schema and preinstalled extension objects only.
        empty_sql = """SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
          AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass
                          AND d.objid=c.oid AND d.deptype='e');"""
        count = run(['psql', '-X', '--no-password', '-At', '-v', 'ON_ERROR_STOP=1', '-c', empty_sql], stage[1])
        require(count.strip() == b'0', 'Staging contiene oggetti: non ripetere import, nessun reset automatico.')
        extra_sql = """SELECT
          (SELECT count(*) FROM pg_namespace WHERE nspname NOT LIKE 'pg_%'
            AND nspname NOT IN ('public','information_schema')) +
          (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
           WHERE n.nspname='public' AND NOT EXISTS
             (SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.deptype='e')) +
          (SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
           WHERE n.nspname='public' AND NOT EXISTS
             (SELECT 1 FROM pg_depend d WHERE d.classid='pg_type'::regclass AND d.objid=t.oid AND d.deptype='e'));
        """
        extra = run(['psql', '-X', '--no-password', '-At', '-v', 'ON_ERROR_STOP=1', '-c', extra_sql], stage[1])
        require(extra.strip() == b'0', 'Staging contiene schemi/funzioni/tipi: revisione manuale necessaria.')
    else:
        require(args.action == 'seed', 'Azione di scrittura non consentita.')
        sql_file = ROOT / 'seed_plans.sql'
        review_artifact(artifact_dir / 'production-catalog.txt', 'Verificare plans nel catalogo reale.')
        sql_snapshot = review_artifact(sql_file, 'Verificare il seed rispetto al DDL reale.')
        require(input('DDL reale plans e seed_plans.sql verificati (tipi, default, vincoli, trigger, RLS). Scrivi PLANS VERIFICATA: ') == 'PLANS VERIFICATA', 'Struttura plans non verificata.')
    phrase = f"{args.action.upper()} staging {stage[3]} {stage_id}"
    require(input(f"Conferma manuale scrivendo esattamente {phrase}: ") == phrase, 'Scrittura non autorizzata.')
    env = dict(stage[1])
    env['PGOPTIONS'] = '-c default_transaction_read_only=off -c net_billy.target=staging -c lock_timeout=5000 -c statement_timeout=120000'
    # Execute the exact bytes reviewed above, even if the file changes meanwhile.
    run(['psql', '-X', '--no-password', '--single-transaction', '-v', 'ON_ERROR_STOP=1', '-f', '-'],
        env, sql_input=sql_snapshot)
    print('Operazione completata esclusivamente su staging. Eseguire verify.')


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        # Psycopg errors may contain credentials or SQL; never print their text.
        print(str(error) if isinstance(error, RuntimeError) else 'Arresto sicuro: input/connessione/comando non riuscito.', file=sys.stderr)
        sys.exit(1)
