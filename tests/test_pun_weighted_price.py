"""Execute the reader's aggregate SQL with SQLite's equivalent month-bound syntax.

These tests exercise the actual SUM/filter expression without a live Railway DB.
"""
from datetime import date
import sqlite3
import unittest
from unittest.mock import patch

import database_service as database
import market_price_service as service


class CursorAdapter:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, sql, params):
        sql = sql.replace("%s + INTERVAL '1 month'", "date(?, '+1 month')").replace("%s", "?")
        self.cursor = self.connection.execute(sql, tuple(value.isoformat() for value in params))

    def fetchone(self):
        return dict(self.cursor.fetchone())


class ConnectionAdapter:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def cursor(self):
        return CursorAdapter(self.connection)


class WeightedPunTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("CREATE TABLE market_prices (market TEXT, reference_date TEXT, value_eur_kwh NUMERIC, disp NUMERIC, observation_count INTEGER)")
        self.addCleanup(self.conn.close)
        context = patch.object(database, "_connection", return_value=ConnectionAdapter(self.conn))
        context.start()
        self.addCleanup(context.stop)

    def add(self, day, price, count, disp=0.02):
        self.conn.execute("INSERT INTO market_prices VALUES ('PUN', ?, ?, ?, ?)", (day, price, disp, count))

    def test_weights_23_24_25_observations_and_preserves_disp(self):
        for day, price, count in (("2026-10-01", 0.1, 23), ("2026-10-02", 0.2, 24), ("2026-10-03", 0.3, 25)):
            self.add(day, price, count)
        result = service.get_prezzo_mercato("Luce", "2026-10-06")
        self.assertAlmostEqual(result["prezzo_medio"], (0.1 * 23 + 0.2 * 24 + 0.3 * 25) / 72)
        self.assertNotAlmostEqual(result["prezzo_medio"], 0.2)
        self.assertAlmostEqual(result["disp"], 0.02)

    def test_excludes_comparison_day_and_future_days(self):
        self.add("2026-10-05", 0.15, 24)
        self.add("2026-10-06", 999, None)
        self.add("2026-10-07", 999, 25)
        self.assertEqual(service.get_prezzo_mercato("Luce", "2026-10-06")["prezzo_medio"], 0.15)

    def test_null_count_errors_instead_of_skipping_row_or_falling_back(self):
        self.add("2026-09-30", 0.1, 24)
        self.add("2026-10-01", 0.2, 24)
        self.add("2026-10-02", 0.3, None)
        with self.assertRaisesRegex(service.MarketPriceError, "2026-10.*observation_count.*Reimportare"):
            service.get_prezzo_mercato("Luce", "2026-10-06")

    def test_previous_month_with_null_count_also_errors(self):
        self.add("2026-09-30", 0.1, None)
        with self.assertRaisesRegex(service.MarketPriceError, "2026-09.*Reimportare"):
            service.get_prezzo_mercato("Luce", "2026-10-06")

    def test_first_day_uses_completed_previous_month(self):
        self.add("2026-09-30", 0.15, 24)
        self.add("2026-10-01", 999, None)
        self.assertEqual(service.get_prezzo_mercato("Luce", "2026-10-01")["prezzo_medio"], 0.15)

    def test_zero_or_invalid_count_and_missing_price_fail(self):
        for price, count in ((0.2, 0), (0.2, 22), (None, 24)):
            self.conn.execute("DELETE FROM market_prices")
            self.add("2026-10-01", price, count)
            with self.assertRaises(service.MarketPriceError):
                service.get_prezzo_mercato("Luce", "2026-10-06")


if __name__ == "__main__":
    unittest.main()
