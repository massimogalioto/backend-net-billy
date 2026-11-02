"""Offline tests for the ScaleDown CTE pipeline."""
import asyncio
import io
import os
import threading
import time
import types
import unittest
from unittest.mock import patch

from fastapi import HTTPException

import cte_pipeline as pipeline
os.environ.setdefault("OPENAI_API_KEY", "test-key")
import upload_pdf

PDF = b"%PDF-1.7 original-pdf-bytes"


class PipelineTests(unittest.TestCase):
    def test_original_pdf_reaches_document_extraction_without_ocr(self):
        file = types.SimpleNamespace(filename="offer.pdf", file=io.BytesIO(PDF))
        with patch.object(pipeline, "extract_document", return_value={"nome_offerta": "Test"}) as extract:
            self.assertEqual(pipeline.processa_cte(file), {"nome_offerta": "Test"})
        self.assertEqual(extract.call_args.args[0], PDF)
        self.assertEqual(extract.call_args.args[1], "cte")
        self.assertNotIn("pytesseract", pipeline.__dict__)
        self.assertNotIn("convert_from_path", pipeline.__dict__)

    def test_invalid_pdf_is_rejected_before_provider(self):
        file = types.SimpleNamespace(filename="bad.pdf", file=io.BytesIO(b"not-pdf"))
        with patch.object(pipeline, "extract_document") as extract, self.assertRaises(HTTPException) as error:
            pipeline.processa_cte(file)
        self.assertEqual(error.exception.status_code, 422)
        extract.assert_not_called()

    def test_provider_timeout_is_safe_gateway_timeout(self):
        from scaledown_provider import ScaleDownTimeoutError
        file = types.SimpleNamespace(filename="offer.pdf", file=io.BytesIO(PDF))
        with patch.object(pipeline, "extract_document", side_effect=ScaleDownTimeoutError("secret")), self.assertRaises(HTTPException) as error:
            pipeline.processa_cte(file)
        self.assertEqual(error.exception.status_code, 504)
        self.assertNotIn("secret", error.exception.detail)

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
