from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import database_service as database
import market_price_service as service
import market_prices_endpoint as endpoint

MONTH = date(2026, 10, 1)
PREVIOUS = date(2026, 9, 1)


class ReaderTests(unittest.TestCase):
    def test_psv_current_month_keeps_ccr_separate(self):
        with patch.object(service, "get_psv_month_price", return_value={"value_eur_smc": Decimal("0.800"), "disp": Decimal("0.035")}) as read:
            self.assertEqual(service.get_prezzo_mercato("Gas", "2026-10-06"), {"prezzo_medio": 0.8, "disp": 0.035})
        read.assert_called_once_with(MONTH)

    def test_psv_fallback_only_previous_month(self):
        with patch.object(service, "get_psv_month_price", side_effect=[None, {"value_eur_smc": Decimal("0.8"), "disp": Decimal("0.035")}]) as read:
            self.assertEqual(service.get_prezzo_mercato("Gas", "2026-10-06")["prezzo_medio"], 0.8)
        self.assertEqual([call.args[0] for call in read.call_args_list], [MONTH, PREVIOUS])

    def test_missing_psv_fails_without_older_history(self):
        with patch.object(service, "get_psv_month_price", return_value=None) as read:
            with self.assertRaisesRegex(service.MarketPriceError, "2026-10.*2026-09"):
                service.get_prezzo_mercato("Gas", "2026-10-06")
        self.assertEqual(read.call_count, 2)

    def test_pun_current_and_previous_fallback(self):
        for rows, dates in (([{"prezzo_medio": Decimal("0.15"), "disp": Decimal("0.02")}], [MONTH]),
                            ([None, {"prezzo_medio": Decimal("0.15"), "disp": Decimal("0.02")}], [MONTH, PREVIOUS])):
            with patch.object(service, "get_pun_month_price", side_effect=rows) as read:
                self.assertEqual(service.get_prezzo_mercato("Luce", "2026-10-06"), {"prezzo_medio": 0.15, "disp": 0.02})
                self.assertEqual([call.args[0] for call in read.call_args_list], dates)

    def test_pun_missing_and_year_boundary(self):
        with patch.object(service, "get_pun_month_price", return_value=None) as read:
            with self.assertRaisesRegex(service.MarketPriceError, "2026-01.*2025-12"):
                service.get_prezzo_mercato("Luce", "2026-01-06")
            self.assertEqual(read.call_args_list[-1].args[0], date(2025, 12, 1))

    def test_variable_gas_adds_ccr_once(self):
        import confronto
        bill = dict(kwh_totali=100, mesi_bolletta=1, spesa_vendita_energia=100,
                    quota_fissa_vendita=10, tipo_fornitura="Gas", tipologia_cliente="Residenziale", data_riferimento="2026-10-06")
        offer = {"fields": {"Tipo tariffa": "Variabile", "Spread €/kWh": 0.01, "Costo fisso mensile": 12}}
        with patch.object(confronto, "get_offerte", return_value=[offer]), patch.object(service, "get_psv_month_price", return_value={"value_eur_smc": Decimal("0.8"), "disp": Decimal("0.035")}):
            self.assertEqual(confronto.confronta_offerte(bill)[0]["totale_simulato"], 96.5)


class RepositoryTests(unittest.TestCase):
    def cursor(self):
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        return connection, cursor

    def test_psv_query_exact_month_and_upsert(self):
        connection, cursor = self.cursor()
        cursor.fetchone.return_value = {"inserted": False}
        with patch.object(database, "_connection", return_value=connection):
            database.get_psv_month_price(date(2026, 10, 6))
            sql, params = cursor.execute.call_args.args
            self.assertIn("market = 'PSV' AND reference_date = %s", sql)
            self.assertEqual(params, (MONTH,))
            self.assertEqual(database.upsert_psv_month_price(MONTH, Decimal("0.8"), Decimal("0.035")), "update")
            sql, params = cursor.execute.call_args.args
            self.assertIn("ON CONFLICT (market, reference_date)", sql)
            self.assertNotIn("value_eur_kwh", sql)
            self.assertEqual(params, (MONTH, Decimal("0.8"), Decimal("0.035")))

    def test_pun_query_monthly_weighted_average(self):
        connection, cursor = self.cursor()
        cursor.fetchone.return_value = {"days": 0, "invalid_days": 0}
        with patch.object(database, "_connection", return_value=connection):
            database.get_pun_month_price(date(2026, 10, 6))
            sql, params = cursor.execute.call_args.args
            self.assertIn("SUM(value_eur_kwh * observation_count)", sql)
            self.assertIn("NULLIF(SUM(observation_count), 0)", sql)
            self.assertNotIn("AVG(value_eur_kwh)", sql)
            self.assertIn("market = 'PUN'", sql)
            self.assertEqual(params, (MONTH, MONTH, date(2026, 10, 6)))


class EndpointTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(endpoint.router)
        self.client = TestClient(app)
        self.month_patch = patch.object(endpoint, "current_month", return_value=MONTH)
        self.month_patch.start()
        self.addCleanup(self.month_patch.stop)

    def test_list_current_missing_previous_available(self):
        with patch.object(endpoint, "get_psv_month_price", side_effect=[{"value_eur_smc": Decimal("0.8"), "disp": Decimal("0.035")}, None]):
            result = self.client.get("/market-prices-psv")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["previous"]["totale"], 0.835)
        self.assertIsNone(result.json()["current"]["value_eur_smc"])

    def test_post_upsert_current_month(self):
        with patch.object(endpoint, "upsert_psv_month_price", return_value="update") as write:
            result = self.client.post("/market-prices-psv", json={"mese": "2026-10", "value_eur_smc": "0.800", "disp": "0.035"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["totale"], 0.835)
        write.assert_called_once_with(MONTH, Decimal("0.800"), Decimal("0.035"))

    def test_rejects_older_month_future_negative_and_non_finite(self):
        with patch.object(endpoint, "upsert_psv_month_price") as write:
            for values in ({"mese": "2026-08", "value_eur_smc": 0.8, "disp": 0.035},
                           {"mese": "2026-11", "value_eur_smc": 0.8, "disp": 0.035},
                           {"mese": "2026-10", "value_eur_smc": -1, "disp": 0.035},
                           {"mese": "2026-10", "value_eur_smc": "NaN", "disp": 0.035}):
                self.assertEqual(self.client.post("/market-prices-psv", json=values).status_code, 422)
        write.assert_not_called()

    def test_previous_month_and_year_boundary_are_editable(self):
        for today, selected, expected in ((MONTH, "2026-09", PREVIOUS), (date(2026, 1, 1), "2025-12", date(2025, 12, 1))):
            with patch.object(endpoint, "current_month", return_value=today), patch.object(endpoint, "upsert_psv_month_price", return_value="update") as write:
                response = self.client.post("/market-prices-psv", json={"mese": selected, "value_eur_smc": "0.8", "disp": "0.035"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["mese"], selected)
            write.assert_called_once_with(expected, Decimal("0.8"), Decimal("0.035"))

    def test_configuration_error_is_clear(self):
        with patch.object(endpoint, "get_psv_month_price", side_effect=database.ConfigurationError("DATABASE_URL non configurato")):
            result = self.client.get("/market-prices-psv")
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.json()["detail"], "DATABASE_URL non configurato")


if __name__ == "__main__":
    unittest.main()
