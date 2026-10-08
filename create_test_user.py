"""Create or update a demo user without keeping a plaintext password in the repository."""
import argparse
import getpass

from auth_service import hash_password
from database_service import _connection


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--tenant-name", required=True)
    parser.add_argument("--plan", default="START")
    parser.add_argument("--first-name", default="Cliente")
    parser.add_argument("--last-name", default="Demo")
    args = parser.parse_args()
    password = getpass.getpass("Password account demo: ")
    if len(password) < 12:
        raise SystemExit("La password deve contenere almeno 12 caratteri.")
    with _connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM plans WHERE upper(code) = upper(%s) AND active = TRUE", (args.plan,))
        plan = cur.fetchone()
        if not plan:
            raise SystemExit(f"Piano non trovato o non attivo: {args.plan}")
        cur.execute("SELECT id FROM tenants WHERE email = %s OR company_name = %s ORDER BY created_at LIMIT 1", (args.email.lower(), args.tenant_name))
        tenant = cur.fetchone()
        if tenant:
            tenant_id = tenant["id"]
        else:
            cur.execute("INSERT INTO tenants (company_name, email) VALUES (%s, %s) RETURNING id", (args.tenant_name, args.email.lower()))
            tenant_id = cur.fetchone()["id"]
        cur.execute("SELECT id FROM users WHERE lower(email) = lower(%s)", (args.email,))
        user = cur.fetchone()
        password_hash = hash_password(password)
        if user:
            cur.execute("UPDATE users SET tenant_id=%s, first_name=%s, last_name=%s, password_hash=%s, is_active=TRUE WHERE id=%s", (tenant_id, args.first_name, args.last_name, password_hash, user["id"]))
        else:
            cur.execute("INSERT INTO users (tenant_id, first_name, last_name, email, password_hash) VALUES (%s, %s, %s, %s, %s)", (tenant_id, args.first_name, args.last_name, args.email.lower(), password_hash))
        cur.execute("SELECT id FROM subscriptions WHERE tenant_id=%s AND status IN ('active','trial','demo') LIMIT 1", (tenant_id,))
        subscription = cur.fetchone()
        if subscription:
            cur.execute("UPDATE subscriptions SET plan_id=%s, status='demo', updated_at=NOW() WHERE id=%s", (plan["id"], subscription["id"]))
        else:
            cur.execute("INSERT INTO subscriptions (tenant_id, plan_id, status, created_at) VALUES (%s, %s, 'demo', NOW())", (tenant_id, plan["id"]))
    print(f"Utente demo creato/aggiornato: {args.email} (tenant {args.tenant_name}, piano {args.plan})")


if __name__ == "__main__":
    main()
