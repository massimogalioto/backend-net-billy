"""Offline tests for the ScaleDown CTE pipeline."""
import asyncio
import io
import json
import os
import threading
import time
import types
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from fastapi import HTTPException

import cte_pipeline as pipeline
os.environ.setdefault("OPENAI_API_KEY", "test-key")
import upload_pdf

PDF = b"%PDF-1.7 original-pdf-bytes"


class PipelineTests(unittest.TestCase):
    def test_original_pdf_reaches_cte_extraction_without_ocr(self):
        file = types.SimpleNamespace(filename="offer.pdf", file=io.BytesIO(PDF))
        with patch.object(pipeline, "extract_cte", return_value={"nome_offerta": "Test"}) as extract:
            self.assertEqual(pipeline.processa_cte(file), {"nome_offerta": "Test"})
        self.assertEqual(extract.call_args.args[0], PDF)
        self.assertEqual(len(extract.call_args.args), 1)
        self.assertNotIn("pytesseract", pipeline.__dict__)
        self.assertNotIn("convert_from_path", pipeline.__dict__)

    def test_invalid_pdf_is_rejected_before_provider(self):
        file = types.SimpleNamespace(filename="bad.pdf", file=io.BytesIO(b"not-pdf"))
        with patch.object(pipeline, "extract_cte") as extract, self.assertRaises(HTTPException) as error:
            pipeline.processa_cte(file)
        self.assertEqual(error.exception.status_code, 422)
        extract.assert_not_called()

    def test_provider_timeout_is_safe_gateway_timeout(self):
        from scaledown_provider import ScaleDownTimeoutError
        file = types.SimpleNamespace(filename="offer.pdf", file=io.BytesIO(PDF))
        provider_error = ScaleDownTimeoutError("secret", category="timeout", duration_ms=90000)
        errors = io.StringIO()
        with patch.object(pipeline, "extract_cte", side_effect=provider_error), redirect_stderr(
            errors
        ), self.assertRaises(HTTPException) as error:
            pipeline.processa_cte(file)
        self.assertEqual(error.exception.status_code, 504)
        self.assertNotIn("secret", error.exception.detail)
        self.assertEqual(len(errors.getvalue().splitlines()), 1)
        self.assertEqual(json.loads(errors.getvalue().split("[ScaleDown][Error] ", 1)[1])["category"], "timeout")

    def test_provider_error_log_contains_only_safe_metadata(self):
        from scaledown_provider import ScaleDownError
        file = types.SimpleNamespace(filename="customer-name.pdf", file=io.BytesIO(PDF))
        provider_error = ScaleDownError(
            "PROVIDER_MESSAGE_SECRET", category="http", status_code=422,
            duration_ms=321, error_code="invalid_schema",
        )
        errors = io.StringIO()
        with patch.dict("os.environ", {"SCALEDOWN_DEBUG": "true"}), patch.object(
            pipeline, "extract_cte", side_effect=provider_error
        ), redirect_stderr(errors), self.assertRaises(HTTPException) as raised:
            pipeline.processa_cte(file)
        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(raised.exception.detail, "Estrazione ScaleDown fallita")
        self.assertEqual(len(errors.getvalue().splitlines()), 1)
        log = errors.getvalue()
        diagnostic = json.loads(log.split("[ScaleDown][Error] ", 1)[1])
        self.assertEqual(diagnostic["endpoint"], "https://api.scaledown.xyz/v1/chat/completions")
        self.assertEqual(diagnostic["category"], "http")
        self.assertEqual(diagnostic["status"], 422)
        self.assertEqual(diagnostic["duration_ms"], 321)
        self.assertEqual(diagnostic["error_code"], "invalid_schema")
        for secret in ("PROVIDER_MESSAGE_SECRET", "customer-name.pdf", "original-pdf-bytes", "SCALEDOWN_API_KEY"):
            self.assertNotIn(secret, log)

    def test_validation_log_contains_field_names_not_values(self):
        from scaledown_provider import ScaleDownResponseError
        file = types.SimpleNamespace(filename="offer.pdf", file=io.BytesIO(PDF))
        provider_error = ScaleDownResponseError(
            "invalid value Sconosciuta", category="validation", duration_ms=45,
            invalid_fields=("tariffa", "tipo_fornitura"),
            validation_errors=(("tariffa", "literal_error"), ("tipo_fornitura", "missing")),
        )
        errors = io.StringIO()
        with patch.object(pipeline, "extract_cte", side_effect=provider_error), redirect_stderr(
            errors
        ), self.assertRaises(HTTPException):
            pipeline.processa_cte(file)
        diagnostic = json.loads(errors.getvalue().split("[ScaleDown][Error] ", 1)[1])
        self.assertEqual(diagnostic["invalid_fields"], ["tariffa", "tipo_fornitura"])
        self.assertEqual(diagnostic["validation_errors"], [
            {"field": "tariffa", "type": "literal_error"},
            {"field": "tipo_fornitura", "type": "missing"},
        ])
        self.assertNotIn("Sconosciuta", errors.getvalue())

    def test_upload_response_contract_is_unchanged(self):
        file = types.SimpleNamespace(filename="single.pdf", file=io.BytesIO(PDF))
        with patch.object(upload_pdf, "processa_cte", return_value={"nome_offerta": "Test"}):
            result = asyncio.run(upload_pdf.upload_cte_pdf(file, "test-user"))
        self.assertEqual(result, {"filename": "single.pdf", "output_ai": {"nome_offerta": "Test"}})

    def test_upload_concurrency_limit_remains_two(self):
        active = peak = 0
        guard = threading.Lock()
        def process(_file):
            nonlocal active, peak
            with guard:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with guard: active -= 1
            return {}
        async def exercise():
            files = [types.SimpleNamespace(filename=f"{i}.pdf") for i in range(4)]
            with patch.object(upload_pdf, "cte_slots", asyncio.Semaphore(2)), patch.object(upload_pdf, "processa_cte", side_effect=process):
                await asyncio.gather(*(upload_pdf.upload_cte_pdf(item, "user") for item in files))
        asyncio.run(exercise())
        self.assertEqual(peak, 2)


if __name__ == "__main__":
    unittest.main()
