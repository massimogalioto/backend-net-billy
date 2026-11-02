import base64
import json
import unittest
from unittest.mock import Mock, patch

import requests

import document_extraction
import scaledown_provider
from document_schemas import CTE_EXTRACTION_SCHEMA


def raw(**overrides):
    data = {"tipo_fornitura": "Luce", "tipologia_cliente": "Residenziale", "tariffa": "Fisso"}
    data.update(overrides)
    return data


class ScaleDownProviderTests(unittest.TestCase):
    def response(self, structured):
        response = Mock(ok=True)
        response.json.return_value = {"choices": [{"message": {"content": json.dumps({"structured_result": {"cte": structured}})}}]}
        return response

    def test_sends_original_pdf_in_official_format(self):
        pdf = b"%PDF-original"
        with patch.dict("os.environ", {"SCALEDOWN_API_KEY": "key"}), patch.object(
            scaledown_provider.requests, "post", return_value=self.response(raw())
        ) as post:
            scaledown_provider.extract_pdf(pdf, CTE_EXTRACTION_SCHEMA)
        request = post.call_args.kwargs
        self.assertEqual(base64.b64decode(request["json"]["document"]), pdf)
        self.assertEqual(request["json"]["document_mime_type"], "application/pdf")
        self.assertEqual(request["json"]["model"], "extract")
        self.assertEqual(request["headers"]["x-api-key"], "key")

    def test_timeout_and_http_error_are_wrapped(self):
        with patch.dict("os.environ", {"SCALEDOWN_API_KEY": "key"}), patch.object(
            scaledown_provider.requests, "post", side_effect=requests.Timeout()
        ), self.assertRaises(scaledown_provider.ScaleDownTimeoutError):
            scaledown_provider.extract_pdf(b"pdf", {})
        response = Mock(ok=False, status_code=422)
        with patch.dict("os.environ", {"SCALEDOWN_API_KEY": "key"}), patch.object(
            scaledown_provider.requests, "post", return_value=response
        ), self.assertRaises(scaledown_provider.ScaleDownError):
            scaledown_provider.extract_pdf(b"pdf", {})

    def test_malformed_response_is_rejected(self):
        response = Mock(ok=True)
        response.json.return_value = {"choices": []}
        with patch.dict("os.environ", {"SCALEDOWN_API_KEY": "key"}), patch.object(
            scaledown_provider.requests, "post", return_value=response
        ), self.assertRaises(scaledown_provider.ScaleDownResponseError):
            scaledown_provider.extract_pdf(b"pdf", {})


class DocumentExtractionTests(unittest.TestCase):
    def extract(self, result):
        with patch.object(document_extraction, "extract_pdf", return_value=result):
            return document_extraction.extract_document(b"pdf", "cte", CTE_EXTRACTION_SCHEMA)

    def test_fixed_classification_and_normalization(self):
        result = self.extract(raw(prezzo_energia_iniziale="0,145", prezzo_energia_rinnovo="0,300",
            quota_commercializzazione="120,00 €", periodicita_quota_commercializzazione="Annuale",
            valid_from="01/11/2026", valid_until="30-11-2026", unita_prezzo_energia="€/kWh"))
        self.assertEqual(result["prezzo_kwh"], 0.145)
        self.assertEqual(result["prezzo_energia_rinnovo"], 0.3)
        self.assertEqual(result["costo_fisso"], 10.0)
        self.assertEqual(result["valid_from"], "2026-11-01")
        self.assertEqual(result["valid_until"], "2026-11-30")
        self.assertEqual(result["unita_prezzo_energia"], "€/kWh")

    def test_variable_classification_uses_spread_not_fixed_price(self):
        result = self.extract(raw(tipo_fornitura="Gas", tipologia_cliente="Business", tariffa="Variabile",
                                  prezzo_energia_iniziale="0,8", spread="0,025", unita_spread="€/Smc"))
        self.assertIsNone(result["prezzo_kwh"])
        self.assertEqual(result["spread"], 0.025)
        self.assertEqual(result["unita_spread"], "€/Smc")

    def test_missing_data_remains_null(self):
        result = self.extract(raw())
        for field in ("fornitore", "nome_offerta", "prezzo_kwh", "spread", "costo_fisso", "valid_from", "valid_until"):
            self.assertIsNone(result[field])
        self.assertEqual(result["recesso_anticipato"], "Non indicato")

    def test_schema_validation_rejects_bad_classification(self):
        with patch.object(document_extraction, "extract_pdf", return_value=raw(tariffa="Sconosciuta")), self.assertRaises(
            scaledown_provider.ScaleDownResponseError
        ):
            document_extraction.extract_document(b"pdf", "cte", CTE_EXTRACTION_SCHEMA)


if __name__ == "__main__":
    unittest.main()
