from datetime import date
import sqlite3
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import database_service as database
import cte_archive_endpoint as endpoint


class Adapter:
    def __init__(self, conn): self.conn = conn
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def cursor(self): return self
    def execute(self, sql, params):
        sql = sql.replace("%s::text", "?").replace("%s", "?").replace("CURRENT_DATE", "'2026-10-07'")
        self.result = self.conn.execute(sql, params)
    def fetchall(self): return [dict(row) for row in self.result.fetchall()]


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.addCleanup(self.conn.close)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""CREATE TABLE cte_offers (id TEXT, tenant_id TEXT, supplier TEXT,
          offer_name TEXT, customer_type TEXT, supply_type TEXT, tariff_type TEXT,
          fixed_price_kwh NUMERIC, spread_kwh NUMERIC, monthly_fixed_cost NUMERIC,
          min_power_kw NUMERIC, max_power_kw NUMERIC, valid_from TEXT, valid_until TEXT,
          notes TEXT, source_cte TEXT, pdf_filename TEXT, created_at TEXT, pdf_object_key TEXT)""")
        for id_, tenant, validity, customer, supply in (
            ("future", "tenant-a", "2026-10-31", "Domestico", "Luce"),
            ("today", "tenant-a", "2026-10-07", "Altri usi", "Gas"),
            ("expired", "tenant-a", "2026-10-06", "Domestico", "Gas"),
            ("unlimited", "tenant-a", None, "Condominio", "Luce"),
            ("other-tenant", "tenant-b", None, "Domestico", "Luce"),
        ):
            self.conn.execute("INSERT INTO cte_offers (id, tenant_id, supplier, offer_name, customer_type, supply_type, valid_until, notes, pdf_object_key) VALUES (?, ?, 'Supplier', ?, ?, ?, ?, NULL, 'private/key.pdf')",
                              (id_, tenant, id_, customer, supply, validity))
        self.patch = patch.object(database, "_connection", return_value=Adapter(self.conn))
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.env = patch.dict("os.environ", {"DEFAULT_TENANT_ID": "tenant-a"})
        self.env.start(); self.addCleanup(self.env.stop)
        app = FastAPI(); app.include_router(endpoint.router)
        self.client = TestClient(app)

    def test_future_today_null_visible_expired_and_other_tenant_excluded(self):
        rows = database.list_cte_offers()
        self.assertEqual({row["id"] for row in rows}, {"future", "today", "unlimited"})

    def test_customer_and_supply_filters(self):
        self.assertEqual([row["id"] for row in database.list_cte_offers("Domestico", "Luce")], ["future"])
        self.assertEqual([row["id"] for row in database.list_cte_offers("Altri usi", "Gas")], ["today"])

    def test_historical_switch_does_not_bypass_tenant(self):
        rows = database.list_cte_offers(active_only=False)
        self.assertEqual({row["id"] for row in rows}, {"future", "today", "unlimited", "expired"})

    def test_api_ignores_arbitrary_tenant_and_omits_private_metadata(self):
        response = self.client.get("/cte-offers?tenant_id=tenant-b")
        self.assertEqual(response.status_code, 200)
        for row in response.json()["offers"]:
            self.assertNotEqual(row["id"], "other-tenant")
            self.assertTrue(row["has_pdf"])
            self.assertIsNone(row["notes"])
            self.assertNotIn("tenant_id", row)
            self.assertNotIn("pdf_object_key", row)

    def test_future_start_is_not_an_extra_archive_filter(self):
        self.conn.execute("UPDATE cte_offers SET valid_from = '2027-01-01' WHERE id = 'future'")
        self.assertIn("future", {row["id"] for row in database.list_cte_offers()})


if __name__ == "__main__": unittest.main()
