import io
import sqlite3
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import database_service as database
import import_market_prices as cli


class MonthImportTests(unittest.TestCase):
    def run_month(self, month="2026-10", fail=None):
        output, errors = io.StringIO(), io.StringIO()
        def imported(day, client):
            if day == fail:
                raise RuntimeError("GME unavailable")
            return dict(market="PUN", reference_date=day, observations=24,
                        value_eur_mwh=Decimal("150"), value_eur_kwh=Decimal("0.15"), action="update")
        with patch.object(cli, "default_target_date", return_value=date(2026, 10, 5)), patch.object(
            cli, "GmeMarketClient", return_value=Mock()
        ), patch.object(cli, "import_pun_date", side_effect=imported) as importer, redirect_stdout(output), redirect_stderr(errors):
            code = cli.main(["--month", month])
        return code, importer, output.getvalue(), errors.getvalue()

    def test_current_month_imports_only_completed_days(self):
        code, importer, output, _ = self.run_month()
        self.assertEqual(code, 0)
        self.assertEqual([call.args[0] for call in importer.call_args_list], [date(2026, 10, day) for day in range(1, 6)])
        for expected in ("month=2026-10", "days_requested=5", "success=5", "failed=0", "observations=24", "[DB] action=update"):
            self.assertIn(expected, output)

    def test_past_month_imports_every_day(self):
        code, importer, output, _ = self.run_month("2026-09")
        self.assertEqual(code, 0)
        self.assertEqual([call.args[0] for call in importer.call_args_list], [date(2026, 9, day) for day in range(1, 31)])
        self.assertIn("days_requested=30", output)

    def test_mutually_exclusive_date_and_month(self):
        with redirect_stderr(io.StringIO()) as errors, self.assertRaises(SystemExit) as exc:
            cli.parse_args(["--date", "2026-10-01", "--month", "2026-10"])
        self.assertEqual(exc.exception.code, 2)
        self.assertIn("not allowed", errors.getvalue())

    def test_invalid_months_are_clear_argument_errors(self):
        for value in ("2026-13", "2026-00", "2026-1", "2026-10-01", "invalid", "0000-01"):
            with self.subTest(value=value), redirect_stderr(io.StringIO()) as errors, self.assertRaises(SystemExit) as exc:
                cli.parse_args(["--month", value])
            self.assertEqual(exc.exception.code, 2)
            self.assertIn("mese non valido", errors.getvalue())

    def test_one_failure_does_not_stop_other_days(self):
        code, importer, output, errors = self.run_month(fail=date(2026, 10, 2))
        self.assertEqual(code, 1)
        self.assertEqual(importer.call_count, 5)
        self.assertIn("success=4", output)
        self.assertIn("failed=1", output)
        self.assertIn("failed_dates=2026-10-02", errors)
        self.assertIn("reference_date=2026-10-05", output)

    def test_future_month_fails_without_gme_calls(self):
        code, importer, _, errors = self.run_month("2026-11")
        self.assertEqual(code, 1)
        importer.assert_not_called()
        self.assertIn("mese futuro", errors)

    def test_calendar_leap_year_first_day_and_year_boundary(self):
        self.assertEqual(len(cli.month_days(date(2024, 2, 1), date(2026, 10, 6))), 29)
        self.assertEqual(cli.month_days(date(2026, 10, 1), date(2026, 10, 1)), [])
        self.assertEqual(len(cli.month_days(date(2025, 12, 1), date(2026, 1, 1))), 31)

    def test_no_arguments_preserves_daily_cron(self):
        result = dict(market="PUN", reference_date=date(2026, 10, 5), observations=24,
                      value_eur_mwh=150, value_eur_kwh=0.15, action="update")
        with patch.object(cli, "default_target_date", return_value=date(2026, 10, 5)), patch.object(cli, "GmeMarketClient", return_value="client"), patch.object(cli, "import_pun_date", return_value=result) as importer, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main([]), 0)
        importer.assert_called_once_with(date(2026, 10, 5), "client")
        self.assertIn("[CRON] status=success", output.getvalue())

    def test_month_backfill_updates_real_counts_through_existing_upsert(self):
        # Execute the existing UPSERT using SQLite; only PostgreSQL's xmax
        # RETURNING diagnostic is replaced, not the INSERT/UPDATE expression.
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.row_factory = sqlite3.Row
        conn.create_function("NOW", 0, lambda: "2026-10-06")
        conn.execute("CREATE TABLE market_prices (market TEXT, reference_date TEXT, value_eur_mwh NUMERIC, value_eur_kwh NUMERIC, source TEXT, observation_count INTEGER, updated_at TEXT, UNIQUE(market, reference_date))")
        for day in range(1, 6):
            conn.execute("INSERT INTO market_prices (market, reference_date) VALUES ('PUN', ?)", (f"2026-10-{day:02}",))
        context = MagicMock()
        cur = context.__enter__.return_value.cursor.return_value.__enter__.return_value
        def execute(sql, params):
            adapted = sql.replace("%s", "?").replace("RETURNING (xmax = 0) AS inserted", "RETURNING 0 AS inserted")
            result = conn.execute(adapted, tuple(str(v) if isinstance(v, (Decimal, date)) else v for v in params))
            cur.fetchone.return_value = dict(result.fetchone())
        cur.execute.side_effect = execute
        expected = [23, 24, 25, 24, 23]
        client = Mock()
        client.request_pun_hourly.side_effect = lambda day: [
            {"FlowDate": day.strftime("%Y%m%d"), "Zone": "PUN", "Hour": hour, "Period": "1", "Price": "150"}
            for hour in range(1, expected[day.day - 1] + 1)]
        with patch.object(database, "_connection", return_value=context), patch.object(cli, "default_target_date", return_value=date(2026, 10, 5)), patch.object(cli, "GmeMarketClient", return_value=client), redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["--month", "2026-10"]), 0)
        rows = conn.execute("SELECT observation_count FROM market_prices ORDER BY reference_date").fetchall()
        self.assertEqual([row["observation_count"] for row in rows], expected)
        self.assertEqual(len(rows), 5)


if __name__ == "__main__":
    unittest.main()
