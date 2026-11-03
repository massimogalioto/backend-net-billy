import unittest
from unittest.mock import patch

import bolletta_extraction as bill
from scaledown_provider import ScaleDownEntities


def entities(**values):
    return ScaleDownEntities([
        {"type": field, "text": str(value), "confidence": 0.9, "start": 0, "end": 1, "context": None}
        for field, value in values.items()
    ], 30)


class BollettaExtractionTests(unittest.TestCase):
    def extract(self, result):
        with patch.object(bill, "extract_pdf", return_value=result) as provider:
            extracted = bill.extract_bolletta(b"%PDF-original")
        provider.assert_called_once_with(b"%PDF-original", bill.BOLLETTA_ENTITIES)
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
        result = self.extract(entities(kwh_totali="1.234 kWh"))
        self.assertEqual(result["kwh_totali"], 1234.0)

    def test_duplicates_keep_first_legacy_match_and_missing_values_stay_null(self):
        result = ScaleDownEntities([
            {"type": "pod", "text": "LOW", "confidence": 0.1},
            {"type": "pod", "text": "PDR-HIGH", "confidence": 0.9},
        ], 5)
        extracted = self.extract(result)
        self.assertEqual(extracted["pod"], "LOW")
        self.assertIsNone(extracted["kwh_totali"])
        self.assertIsNone(extracted["quota_fissa_vendita"])

    def test_unknown_classification_stays_missing_for_required_field_validation(self):
        result = self.extract(entities(tipo_fornitura="Misto", tipologia_cliente="Residenziale"))
        self.assertIsNone(result["tipo_fornitura"])
        self.assertEqual(result["tipologia_cliente"], "Residenziale")


if __name__ == "__main__":
    unittest.main()
