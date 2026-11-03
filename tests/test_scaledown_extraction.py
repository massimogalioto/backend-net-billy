import base64
import io
import json
import unittest
from contextlib import redirect_stderr
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
        response = Mock(ok=True, status_code=200)
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
        self.assertEqual(post.call_count, 1)

    def test_request_debug_is_disabled_by_default(self):
        errors = io.StringIO()
        with patch.dict("os.environ", {"SCALEDOWN_API_KEY": "key"}, clear=True), patch.object(
            scaledown_provider.requests, "post", return_value=self.response(raw())
        ), redirect_stderr(errors):
            scaledown_provider.extract_pdf(b"%PDF-private", CTE_EXTRACTION_SCHEMA)
        self.assertEqual(errors.getvalue(), "")

    def test_request_debug_logs_sanitized_complete_structure_and_sizes(self):
        pdf = b"%PDF-private-original-bytes"
        environment = {"SCALEDOWN_API_KEY": "API_KEY_SECRET", "SCALEDOWN_DEBUG": "true", "SCALEDOWN_TIMEOUT_SECONDS": "123"}
        errors = io.StringIO()
        with patch.dict("os.environ", environment, clear=True), patch.object(
            scaledown_provider.requests, "post", return_value=self.response(raw())
        ) as post, redirect_stderr(errors):
            scaledown_provider.extract_pdf(pdf, CTE_EXTRACTION_SCHEMA)
        self.assertEqual(post.call_count, 1)
        request = post.call_args.kwargs
        self.assertEqual(base64.b64decode(request["json"]["document"]), pdf)
        self.assertEqual(len(request["json"]["document"]), 36)
        diagnostic = json.loads(errors.getvalue().split("[CTE][ScaleDown][Request] ", 1)[1])
        self.assertEqual(diagnostic["endpoint"], scaledown_provider.SCALEDOWN_URL)
        self.assertEqual(diagnostic["method"], "POST")
        self.assertEqual(diagnostic["model"], request["json"]["model"])
        self.assertEqual(diagnostic["messages"], request["json"]["messages"])
        self.assertEqual(diagnostic["response_format"], request["json"]["response_format"])
        self.assertEqual(diagnostic["document_mime_type"], "application/pdf")
        self.assertEqual(diagnostic["document"], "[PDF_BASE64_OMESSO]")
        self.assertEqual(diagnostic["pdf_size_bytes"], len(pdf))
        self.assertEqual(diagnostic["base64_size_bytes"], len(request["json"]["document"].encode("ascii")))
        self.assertEqual(diagnostic["payload_json_size_bytes"], len(json.dumps(request["json"]).encode("utf-8")))
        self.assertEqual(diagnostic["timeout_seconds"], 123.0)
        self.assertEqual(diagnostic["connect_timeout_seconds"], 123.0)
        self.assertEqual(diagnostic["read_timeout_seconds"], 123.0)
        self.assertEqual(set(diagnostic["header_names"]), {"x-api-key", "Content-Type"})
        serialized_log = errors.getvalue()
        for secret in ("API_KEY_SECRET", request["json"]["document"], pdf.decode("ascii")):
            self.assertNotIn(secret, serialized_log)

    def test_timeout_is_structured(self):
        with patch.dict("os.environ", {"SCALEDOWN_API_KEY": "key"}), patch.object(
            scaledown_provider.requests, "post", side_effect=requests.Timeout("PROVIDER_SECRET")
        ), patch.object(scaledown_provider.time, "monotonic", side_effect=[10, 10.125]), self.assertRaises(
            scaledown_provider.ScaleDownTimeoutError
        ) as raised:
            scaledown_provider.extract_pdf(b"PDF_SECRET", {})
        error = raised.exception
        self.assertEqual((error.category, error.status_code, error.duration_ms), ("timeout", None, 125))
        self.assertEqual(error.endpoint, scaledown_provider.SCALEDOWN_URL)
        self.assertNotIn("PROVIDER_SECRET", str(error))
        self.assertNotIn("PDF_SECRET", str(error))

    def test_connect_and_read_timeouts_are_distinguished(self):
        for exception, expected_type in ((requests.ConnectTimeout("secret"), "connect"),
                                         (requests.ReadTimeout("secret"), "read")):
            with self.subTest(timeout_type=expected_type), patch.dict(
                "os.environ", {"SCALEDOWN_API_KEY": "key", "SCALEDOWN_TIMEOUT_SECONDS": "12"}, clear=True
            ), patch.object(
                scaledown_provider.requests, "post", side_effect=exception
            ), patch.object(scaledown_provider.time, "monotonic", side_effect=[10, 10.25]), self.assertRaises(
                scaledown_provider.ScaleDownTimeoutError
            ) as raised:
                scaledown_provider.extract_pdf(b"PDF_SECRET", {})
            error = raised.exception
            self.assertEqual(error.category, "timeout")
            self.assertEqual(error.timeout_type, expected_type)
            self.assertEqual(error.duration_ms, 250)
            self.assertEqual(error.connect_timeout_seconds, 12.0)
            self.assertEqual(error.read_timeout_seconds, 12.0)
            self.assertTrue(error.started_at.endswith("+00:00"))

    def test_http_errors_are_structured_and_sanitized(self):
        for status in (400, 401, 402, 422, 500):
            with self.subTest(status=status):
                response = Mock(ok=False, status_code=status)
                response.json.return_value = {"error": {"code": "invalid_schema", "message": "PROVIDER_SECRET"}, "document": "BASE64_SECRET"}
                with patch.dict("os.environ", {"SCALEDOWN_API_KEY": "API_SECRET"}), patch.object(
                    scaledown_provider.requests, "post", return_value=response
                ), patch.object(scaledown_provider.time, "monotonic", side_effect=[10, 10.125]), self.assertRaises(
                    scaledown_provider.ScaleDownError
                ) as raised:
                    scaledown_provider.extract_pdf(b"PDF_SECRET", {})
                error = raised.exception
                self.assertEqual((error.category, error.status_code, error.duration_ms), ("http", status, 125))
                self.assertEqual(error.error_code, "invalid_schema")
                metadata = repr(vars(error))
                for secret in ("PROVIDER_SECRET", "BASE64_SECRET", "API_SECRET", "PDF_SECRET"):
                    self.assertNotIn(secret, metadata)

    def test_malformed_response_is_rejected(self):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"choices": []}
        with patch.dict("os.environ", {"SCALEDOWN_API_KEY": "key"}), patch.object(
            scaledown_provider.requests, "post", return_value=response
        ), patch.object(scaledown_provider.time, "monotonic", side_effect=[10, 10.050]), self.assertRaises(
            scaledown_provider.ScaleDownResponseError
        ) as raised:
            scaledown_provider.extract_pdf(b"pdf", {})
        self.assertEqual(raised.exception.category, "response_format")
        self.assertEqual(raised.exception.status_code, 200)
        self.assertEqual(raised.exception.duration_ms, 50)


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
        result = scaledown_provider.ScaleDownResult(raw(tariffa="Sconosciuta"), 77)
        with patch.object(document_extraction, "extract_pdf", return_value=result), self.assertRaises(
            scaledown_provider.ScaleDownResponseError
        ) as raised:
            document_extraction.extract_document(b"pdf", "cte", CTE_EXTRACTION_SCHEMA)
        error = raised.exception
        self.assertEqual(error.category, "validation")
        self.assertEqual(error.duration_ms, 77)
        self.assertEqual(error.invalid_fields, ("tariffa",))
        self.assertNotIn("Sconosciuta", repr(vars(error)))


if __name__ == "__main__":
    unittest.main()
