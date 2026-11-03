import unittest
from unittest.mock import patch

import cte_extraction as cte
from salva_offerta_endpoint import OffertaInput
from scaledown_provider import ScaleDownEntities


def entities(**values):
    return ScaleDownEntities([
        {"type": field, "text": str(value), "confidence": 0.9, "start": 0, "end": 1, "context": None}
        for field, value in values.items()
    ], 20)


class CteExtractionTests(unittest.TestCase):
    def extract(self, result):
        with patch.object(cte, "extract_pdf", return_value=result) as provider:
            extracted = cte.extract_cte(b"%PDF-original")
        provider.assert_called_once_with(b"%PDF-original", cte.CTE_ENTITIES)
        return extracted

    def test_fixed_offer_annual_cost_dates_notes_and_frontend_contract(self):
        result = self.extract(entities(
            tipo_fornitura="Energia elettrica", tipologia_cliente="Domestico", tariffa="Prezzo fisso",
            fornitore="Test Energia", nome_offerta="Casa", prezzo_energia_iniziale="0,145 €/kWh",
            prezzo_energia_rinnovo="0,300 €/kWh", spread="0,999", quota_commercializzazione="120,00 €",
            periodicita_quota_commercializzazione="Annuo", valid_from="01/11/2026", valid_until="30-11-2026",
            fatturazione="Ogni mese", condizioni_particolari="Domiciliazione", min_power_kw="3", max_power_kw="15",
        ))
        self.assertEqual(result["tipo_fornitura"], "Luce")
        self.assertEqual(result["tipologia_cliente"], "Residenziale")
        self.assertEqual(result["tariffa"], "Fisso")
        self.assertEqual(result["prezzo_kwh"], 0.145)
        self.assertIsNone(result["spread"])
        self.assertEqual(result["costo_fisso"], 10.0)
        self.assertEqual((result["valid_from"], result["valid_until"]), ("2026-11-01", "2026-11-30"))
        self.assertIn("Prezzo rinnovo", result["altre_note"])
        self.assertIn("Domiciliazione", result["notes"])
        self.assertEqual(set(result), {
            "fornitore", "nome_offerta", "tipologia_cliente", "tariffa", "prezzo_kwh", "spread",
            "costo_fisso", "valid_from", "valid_until", "vincoli", "tipo_fornitura", "min_power_kw",
            "max_power_kw", "fatturazione", "recesso_anticipato", "altre_note", "notes",
        })
        OffertaInput(**result)

    def test_variable_offer_spread_monthly_cost_and_dispatch_reference(self):
        result = self.extract(entities(
            tipo_fornitura="Gas naturale", tipologia_cliente="Impresa", tariffa="Prezzo indicizzato",
            fornitore="Gas Test", nome_offerta="PSV", prezzo_energia_iniziale="0,8", spread="0,025 €/Smc",
            quota_commercializzazione="12", periodicita_quota_commercializzazione="Mensile",
            dispacciamento_riferimento_arera="Delibera ARERA 123", fatturazione="Bimestrale",
        ))
        self.assertEqual(result["tipo_fornitura"], "Gas")
        self.assertEqual(result["tariffa"], "Variabile")
        self.assertIsNone(result["prezzo_kwh"])
        self.assertEqual(result["spread"], 0.025)
        self.assertEqual(result["costo_fisso"], 12.0)
        self.assertIn("Dispacciamento ARERA", result["altre_note"])

    def test_explicit_mwh_unit_is_converted_and_unknown_unit_is_not_guessed(self):
        converted = self.extract(entities(
            tipo_fornitura="Luce", tariffa="Fisso", prezzo_energia_iniziale="145",
            unita_prezzo_energia="EUR/MWh",
        ))
        self.assertEqual(converted["prezzo_kwh"], 0.145)
        unknown = self.extract(entities(
            tipo_fornitura="Luce", tariffa="Fisso", prezzo_energia_iniziale="145",
            unita_prezzo_energia="EUR",
        ))
        self.assertIsNone(unknown["prezzo_kwh"])

    def test_duplicate_type_uses_highest_confidence_and_missing_stays_null(self):
        result = ScaleDownEntities([
            {"type": "fornitore", "text": "Low", "confidence": 0.2},
            {"type": "fornitore", "text": "High", "confidence": 0.95},
            {"type": "tipo_fornitura", "text": "Luce", "confidence": 0.9},
        ], 10)
        extracted = self.extract(result)
        self.assertEqual(extracted["fornitore"], "High")
        self.assertIsNone(extracted["nome_offerta"])
        self.assertIsNone(extracted["prezzo_kwh"])
        self.assertEqual(extracted["tariffa"], "Non determinabile")

    def test_ambiguous_unknown_classification_becomes_not_determinable(self):
        result = self.extract(entities(
            tipo_fornitura="Luce", tipologia_cliente="Residenziale", tariffa="Mista ambigua",
            fatturazione="Quando necessario",
        ))
        self.assertEqual(result["tariffa"], "Non determinabile")
        self.assertEqual(result["fatturazione"], "Non indicata")


if __name__ == "__main__":
    unittest.main()
