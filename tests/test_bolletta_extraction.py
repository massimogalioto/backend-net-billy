import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

import bolletta_extraction as bill
from scaledown_provider import ScaleDownEntities, ScaleDownTimeoutError


def entities(**values):
    return ScaleDownEntities([
        {"type": field, "text": str(value), "confidence": 0.9, "start": 0, "end": 1, "context": None}
        for field, value in values.items()
    ], 30)


class BollettaExtractionTests(unittest.TestCase):
    def extract(self, result, expected_calls=1):
        with patch.object(bill, "extract_pdf", return_value=result) as provider:
            extracted = bill.extract_bolletta(b"%PDF-original")
        self.assertEqual(provider.call_count, expected_calls)
        first_call = provider.call_args_list[0]
        self.assertEqual(first_call.args, (b"%PDF-original", bill.BOLLETTA_ENTITIES))
        self.assertEqual(first_call.kwargs["attempt"], 1)
        self.assertRegex(first_call.kwargs["diagnostic_id"], r"^[0-9a-f]{32}$")
        return extracted

    def test_electricity_bill_preserves_legacy_contract_and_monthly_fixed_cost(self):
        result = self.extract(entities(
            cliente="Mario Rossi", indirizzo="Via Roma 1", pod="IT001E123", kwh_totali="459 kWh",
            mesi_bolletta="2", spesa_materia_energia="105,09 €", spesa_vendita_energia="105,09 €",
            quota_fissa_vendita="8,34 €", periodicita_quota_fissa="Mensile",
            tipo_fornitura="Energia elettrica", tipologia_cliente="Domestico", potenza_kw="3,0 kW",
        ))
        self.assertEqual(result, {
            "cliente": "Mario Rossi", "indirizzo": "Via Roma 1", "pod": "IT001E123",
            "kwh_totali": 459.0, "mesi_bolletta": 2, "spesa_materia_energia": 105.09,
            "spesa_vendita_energia": 105.09, "quota_fissa_vendita": 8.34,
            "tipo_fornitura": "Luce", "tipologia_cliente": "Residenziale", "potenza_kw": 3.0,
        })

    def test_gas_bill_period_total_and_annual_fixed_cost_are_normalized(self):
        period = self.extract(entities(
            kwh_totali="120,5 Smc", mesi_bolletta="2", spesa_vendita_energia="80",
            quota_fissa_vendita="24", periodicita_quota_fissa="Totale periodo",
            tipo_fornitura="Gas naturale", tipologia_cliente="Impresa",
        ))
        self.assertEqual(period["kwh_totali"], 120.5)
        self.assertEqual(period["quota_fissa_vendita"], 12.0)
        self.assertEqual(period["tipo_fornitura"], "Gas")
        self.assertEqual(period["tipologia_cliente"], "Business")
        self.assertEqual(period["spesa_materia_energia"], 80.0)
        annual = self.extract(entities(
            kwh_totali="100", mesi_bolletta="1", spesa_materia_energia="40",
            quota_fissa_vendita="120", periodicita_quota_fissa="Annuale",
            tipo_fornitura="Luce", tipologia_cliente="Residenziale",
        ))
        self.assertEqual(annual["quota_fissa_vendita"], 10.0)
        self.assertEqual(annual["spesa_vendita_energia"], 40.0)

    def test_italian_thousands_separator_is_not_read_as_decimal(self):
        result = self.extract(entities(kwh_totali="1.234 kWh"), expected_calls=2)
        self.assertEqual(result["kwh_totali"], 1234.0)

    def test_duplicates_keep_first_legacy_match_and_missing_values_stay_null(self):
        result = ScaleDownEntities([
            {"type": "pod", "text": "LOW", "confidence": 0.1},
            {"type": "pod", "text": "PDR-HIGH", "confidence": 0.9},
        ], 5)
        extracted = self.extract(result, expected_calls=2)
        self.assertEqual(extracted["pod"], "LOW")
        self.assertIsNone(extracted["kwh_totali"])
        self.assertIsNone(extracted["quota_fissa_vendita"])

    def test_unknown_classification_stays_missing_for_required_field_validation(self):
        result = self.extract(entities(tipo_fornitura="Misto", tipologia_cliente="Residenziale"), expected_calls=2)
        self.assertIsNone(result["tipo_fornitura"])
        self.assertEqual(result["tipologia_cliente"], "Residenziale")

    def test_a2a_scontrino_fallback_recovers_expected_values_and_total_period_fixed_cost(self):
        first = entities()
        fallback = entities(
            kwh_totali="299 kWh", mesi_bolletta="2",
            spesa_vendita_energia="86,24 €", spesa_materia_energia="86,24 €",
            quota_fissa_vendita="5,06 €", periodicita_quota_fissa="Totale periodo",
            tipo_fornitura="Energia elettrica", tipologia_cliente="Micro Imprese", potenza_kw="3 kW",
        )
        with patch.object(bill, "extract_pdf", side_effect=[first, fallback]) as provider:
            result = bill.extract_bolletta(b"%PDF-A2A-original")
        self.assertEqual(provider.call_count, 2)
        self.assertEqual(result["kwh_totali"], 299.0)
        self.assertEqual(result["mesi_bolletta"], 2)
        self.assertEqual(result["spesa_vendita_energia"], 86.24)
        self.assertEqual(result["spesa_materia_energia"], 86.24)
        self.assertEqual(result["quota_fissa_vendita"], 2.53)
        self.assertEqual(result["tipo_fornitura"], "Luce")
        self.assertEqual(result["tipologia_cliente"], "Business")
        self.assertEqual(result["potenza_kw"], 3.0)
        fallback_call = provider.call_args_list[1]
        self.assertEqual(fallback_call.args[0], b"%PDF-A2A-original")
        self.assertEqual(set(fallback_call.args[1]), set(bill._REQUIRED_FIELDS) | {
            "spesa_materia_energia", "periodicita_quota_fissa", "potenza_kw",
        })
        self.assertEqual(fallback_call.kwargs["instruction"], bill._FALLBACK_INSTRUCTION)
        self.assertEqual(fallback_call.kwargs["attempt"], 2)

    def test_partial_first_result_is_preserved_and_only_missing_fields_are_merged(self):
        first = entities(
            kwh_totali="299", mesi_bolletta="2", spesa_vendita_energia="86,24",
            quota_fissa_vendita="2,53", periodicita_quota_fissa="Mensile",
            tipo_fornitura="Energia elettrica",
        )
        fallback = entities(
            tipologia_cliente="Altri Usi", spesa_vendita_energia="999,99",
            quota_fissa_vendita="999,99", periodicita_quota_fissa="Mensile",
        )
        with patch.object(bill, "extract_pdf", side_effect=[first, fallback]) as provider:
            result = bill.extract_bolletta(b"%PDF-partial")
        self.assertEqual(provider.call_count, 2)
        self.assertEqual(set(provider.call_args_list[1].args[1]), {"tipologia_cliente", "potenza_kw"})
        self.assertEqual(result["tipologia_cliente"], "Business")
        self.assertEqual(result["spesa_vendita_energia"], 86.24)
        self.assertEqual(result["quota_fissa_vendita"], 2.53)

    def test_failed_fallback_returns_partial_data_and_never_calls_provider_three_times(self):
        with patch.object(bill, "extract_pdf", side_effect=[entities(), entities()]) as provider:
            result = bill.extract_bolletta(b"%PDF-unreadable")
        self.assertEqual(provider.call_count, 2)
        self.assertTrue(all(result[field] is None for field in bill._REQUIRED_FIELDS))

    def test_business_aliases_and_monthly_fixed_cost_do_not_duplicate_amounts(self):
        for customer in ("Micro Imprese", "Altri Usi"):
            with self.subTest(customer=customer):
                result = self.extract(entities(
                    kwh_totali="10", mesi_bolletta="2", spesa_vendita_energia="20",
                    quota_fissa_vendita="2,53", periodicita_quota_fissa="Mensile",
                    tipo_fornitura="Energia elettrica", tipologia_cliente=customer,
                ))
                self.assertEqual(result["tipologia_cliente"], "Business")
                self.assertEqual(result["quota_fissa_vendita"], 2.53)
                self.assertEqual(result["spesa_vendita_energia"], 20.0)

    def test_provider_error_on_first_attempt_is_not_retried(self):
        error = ScaleDownTimeoutError("timeout", category="timeout", duration_ms=1)
        with patch.object(bill, "extract_pdf", side_effect=error) as provider, self.assertRaises(
            ScaleDownTimeoutError
        ):
            bill.extract_bolletta(b"%PDF-timeout")
        self.assertEqual(provider.call_count, 1)

    def test_diagnostics_contain_only_status_field_names_and_call_count(self):
        diagnostic = io.StringIO()
        with patch.object(bill, "extract_pdf", side_effect=[entities(), entities()]), redirect_stderr(diagnostic):
            extracted = bill.extract_bolletta(b"PRIVATE-PDF")
        log = diagnostic.getvalue()
        self.assertIn('"event":"first_completed"', log)
        self.assertIn('"event":"fallback_completed"', log)
        self.assertIn('"calls":2', log)
        self.assertNotIn("PRIVATE-PDF", log)
        self.assertRegex(extracted.diagnostic_id, r"^[0-9a-f]{32}$")

    def test_unknown_entity_names_are_reported_only_when_safe_identifiers(self):
        result = ScaleDownEntities([
            {"type": "legacy_consumption", "text": "secret amount"},
            {"type": "customer name: private", "text": "private person"},
        ], 4)
        diagnostic = io.StringIO()
        with patch.object(bill, "extract_pdf", side_effect=[result, result]), redirect_stderr(diagnostic):
            bill.extract_bolletta(b"PRIVATE-PDF")
        log = diagnostic.getvalue()
        self.assertIn('"diagnostic_code":"UNKNOWN_ENTITIES"', log)
        self.assertIn("legacy_consumption", log)
        self.assertNotIn("customer name: private", log)
        self.assertNotIn("secret amount", log)
        self.assertNotIn("private person", log)

    def test_invalid_number_and_unknown_periodicity_are_diagnostic_not_zero(self):
        result = entities(
            kwh_totali="not-a-number", mesi_bolletta="2", spesa_vendita_energia="20",
            quota_fissa_vendita="5", periodicita_quota_fissa="ogni trimestre",
            tipo_fornitura="Luce", tipologia_cliente="Business",
        )
        diagnostic = io.StringIO()
        with patch.object(bill, "extract_pdf", side_effect=[result, result]), redirect_stderr(diagnostic):
            extracted = bill.extract_bolletta(b"PRIVATE-PDF")
        self.assertIsNone(extracted["kwh_totali"])
        self.assertIsNone(extracted["quota_fissa_vendita"])
        log = diagnostic.getvalue()
        self.assertIn('"reason":"invalid_number"', log)
        self.assertIn('"reason":"unknown_periodicity"', log)
        self.assertNotIn("not-a-number", log)


if __name__ == "__main__":
    unittest.main()
