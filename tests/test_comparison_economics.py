"""Economic regression tests: no database, AI or third-party packages needed."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


def load_comparison():
    database = types.ModuleType("database_service")
    database.get_offerte = Mock()
    market = types.ModuleType("market_price_service")
    market.get_prezzo_mercato = Mock()
    spec = importlib.util.spec_from_file_location(
        "economic_comparison", Path(__file__).resolve().parents[1] / "confronto.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"database_service": database, "market_price_service": market}):
        spec.loader.exec_module(module)
    return module


comparison = load_comparison()
BILL = dict(kwh_totali=459, mesi_bolletta=2, spesa_materia_energia=127.06,
            spesa_vendita_energia=105.09, quota_fissa_vendita=8.34,
            tipo_fornitura="Luce", tipologia_cliente="Residenziale",
            data_riferimento="2026-10-05")


def offer(name, price, fixed):
    return {"id": name, "fields": {"id_offerta": name, "Nome offerta": name,
            "Tipo tariffa": "Fisso", "Prezzo fisso €/kWh": price,
            "Costo fisso mensile": fixed}}


class EconomicsTests(unittest.TestCase):
    def compare(self, bill=BILL, offers=None, disp=0.038):
        with patch.object(comparison, "get_offerte", return_value=offers or [
            offer("A", 0.149, 12), offer("B", 0.174, 12.11)
        ]), patch.object(comparison, "get_prezzo_mercato", return_value={"prezzo_medio": 0.1, "disp": disp}):
            return comparison.confronta_offerte(bill)

    def test_requested_bill_and_two_fixed_offers(self):
        results = self.compare()
        current_monthly = BILL["spesa_vendita_energia"] / BILL["mesi_bolletta"] + BILL["quota_fissa_vendita"]
        self.assertAlmostEqual(current_monthly, 60.885)
        for result, name, cost, monthly, annual, difference_type in zip(
            results, ("A", "B"), (58.34, 64.76), (2.55, -3.87), (30.59, -46.47),
            ("Risparmio", "Spesa in più"),
        ):
            with self.subTest(offer=name):
                self.assertEqual(result["nome_offerta"], name)
                self.assertAlmostEqual(result["totale_simulato"], cost, places=2)
                self.assertAlmostEqual(-result["differenza_mensile"], monthly, places=2)
                self.assertAlmostEqual(result["risparmio_annuo"], annual, places=2)
                self.assertEqual(result["tipo_differenza"], difference_type)
        # Percentage and annual savings use unrounded amounts.
        self.assertAlmostEqual(results[0]["percentuale"], 4.19, places=2)
        self.assertAlmostEqual(results[1]["percentuale"], 6.36, places=2)
        self.assertNotEqual(results[1]["risparmio_annuo"], -3.87 * 12)

    def test_network_total_does_not_affect_savings(self):
        self.assertEqual(self.compare(), self.compare({**BILL, "spesa_materia_energia": 9999}))

    def test_fixed_offer_adds_market_dispatch(self):
        without_dispatch = self.compare(disp=0)
        with_dispatch = self.compare(disp=0.5)
        expected_delta = 0.5 * (BILL["kwh_totali"] / BILL["mesi_bolletta"])
        for base, dispatched in zip(without_dispatch, with_dispatch):
            self.assertAlmostEqual(
                dispatched["totale_simulato"] - base["totale_simulato"], expected_delta, places=2
            )

    def test_fixed_offer_with_zero_dispatch_has_no_invented_cost(self):
        result = self.compare(offers=[offer("No dispatch", 0.149, 12)], disp=0)[0]
        expected = (0.149 * 1.10) * (BILL["kwh_totali"] / BILL["mesi_bolletta"]) + 12
        self.assertAlmostEqual(result["totale_simulato"], expected, places=2)

    def test_missing_sales_component_cannot_fall_back_to_total(self):
        bill = {key: value for key, value in BILL.items() if key != "spesa_vendita_energia"}
        with self.assertRaises(KeyError):
            self.compare(bill)

    def test_more_expensive_offer_has_negative_annual_savings(self):
        result = self.compare(offers=[offer("Expensive", 0.3, 12)])[0]
        self.assertGreater(result["differenza_mensile"], 0)
        self.assertLess(result["risparmio_annuo"], 0)
        self.assertEqual(result["tipo_differenza"], "Spesa in più")

    def test_variable_offer_keeps_market_price_spread_and_dispatch(self):
        variable = {"id": "Variable", "fields": {"Tipo tariffa": "Variabile",
                    "Spread €/kWh": 0.015, "Costo fisso mensile": 12}}
        result = self.compare(offers=[variable], disp=0.02)[0]
        self.assertAlmostEqual(result["totale_simulato"], 42.98, places=2)

    def test_comparison_exposes_offer_expiry_without_changing_economics(self):
        expiring = offer("Expiry", 0.149, 12)
        expiring["fields"]["valid_until"] = "2026-10-31"
        self.assertEqual(self.compare(offers=[expiring])[0]["valid_until"], "2026-10-31")


if __name__ == "__main__":
    unittest.main()
