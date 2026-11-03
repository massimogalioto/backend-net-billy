import base64
import io
import json
import unittest
from contextlib import redirect_stderr
from unittest.mock import Mock, patch

import requests

import scaledown_provider as provider


ENTITIES = {"fornitore": "Società che vende energia", "tariffa": "Fisso o Variabile"}
PDF = b"%PDF-original-private"


def response(entities):
    result = Mock(ok=True, status_code=200)
    result.json.return_value = {"choices": [{"message": {"content": json.dumps({
        "entities": entities, "structured_result": None, "input_tokens": 10, "ocr_text": "private"
    })}}]}
    return result


class ScaleDownProviderTests(unittest.TestCase):
    def test_sends_original_pdf_and_entity_descriptions_in_official_format(self):
        extracted = [{"type": "fornitore", "text": "Test Energia", "confidence": 0.94,
                      "start": 1, "end": 12, "context": "private context"}]
        with patch.dict("os.environ", {"SCALEDOWN_API_KEY": "key"}, clear=True), patch.object(
            provider.requests, "post", return_value=response(extracted)
        ) as post:
            result = provider.extract_pdf(PDF, ENTITIES)
        request = post.call_args.kwargs
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], provider.SCALEDOWN_URL)
        self.assertEqual(base64.b64decode(request["json"]["document"]), PDF)
        self.assertEqual(request["json"]["document_mime_type"], "application/pdf")
        self.assertEqual(request["json"]["model"], "extract")
        self.assertEqual(request["json"]["entities"], ENTITIES)
        self.assertNotIn("response_format", request["json"])
        self.assertEqual(result[0]["type"], "fornitore")
        self.assertEqual(result[0]["text"], "Test Energia")
        self.assertEqual(result[0]["confidence"], 0.94)

    def test_missing_entity_is_omitted_and_malformed_response_is_rejected(self):
        with patch.dict("os.environ", {"SCALEDOWN_API_KEY": "key"}), patch.object(
            provider.requests, "post", return_value=response([])
        ):
            self.assertEqual(provider.extract_pdf(PDF, ENTITIES), [])
        malformed = response([{"type": "fornitore", "confidence": 0.9}])
        with patch.dict("os.environ", {"SCALEDOWN_API_KEY": "key"}), patch.object(
            provider.requests, "post", return_value=malformed
        ), self.assertRaises(provider.ScaleDownResponseError):
            provider.extract_pdf(PDF, ENTITIES)

    def test_debug_stderr_masks_document_key_and_provider_response(self):
        errors = io.StringIO()
        environment = {"SCALEDOWN_API_KEY": "API_KEY_SECRET", "SCALEDOWN_DEBUG": "true"}
        with patch.dict("os.environ", environment, clear=True), patch.object(
            provider.requests, "post", return_value=response([])
        ), redirect_stderr(errors):
            provider.extract_pdf(PDF, ENTITIES)
        log = errors.getvalue()
        diagnostic = json.loads(log.split("[ScaleDown][Request] ", 1)[1])
        self.assertEqual(diagnostic["entities"], ENTITIES)
        self.assertEqual(diagnostic["document"], "[PDF_BASE64_OMESSO]")
        for secret in ("API_KEY_SECRET", base64.b64encode(PDF).decode("ascii"), "private"):
            self.assertNotIn(secret, log)

    def test_timeout_and_http_errors_are_structured_without_real_calls(self):
        for exception, timeout_type in ((requests.ConnectTimeout("secret"), "connect"),
                                        (requests.ReadTimeout("secret"), "read")):
            with self.subTest(timeout_type=timeout_type), patch.dict(
                "os.environ", {"SCALEDOWN_API_KEY": "key"}, clear=True
            ), patch.object(provider.requests, "post", side_effect=exception), self.assertRaises(
                provider.ScaleDownTimeoutError
            ) as raised:
                provider.extract_pdf(PDF, ENTITIES)
            self.assertEqual(raised.exception.timeout_type, timeout_type)
        http = Mock(ok=False, status_code=422)
        http.json.return_value = {"error": {"code": "invalid_document", "message": "secret"}}
        with patch.dict("os.environ", {"SCALEDOWN_API_KEY": "key"}), patch.object(
            provider.requests, "post", return_value=http
        ), self.assertRaises(provider.ScaleDownError) as raised:
            provider.extract_pdf(PDF, ENTITIES)
        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(raised.exception.error_code, "invalid_document")
        self.assertNotIn("secret", repr(vars(raised.exception)))


if __name__ == "__main__":
    unittest.main()
