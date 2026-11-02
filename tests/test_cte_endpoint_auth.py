import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
    import analizza_cte
import estrai_testo_pdf
from auth_service import CurrentUser


USER = CurrentUser(
    "user-a",
    "demo@example.test",
    "Demo",
    "tenant-a",
    "Tenant A",
    "FREE",
    "Free",
)


class CTEEndpointAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(analizza_cte.router)
        self.app.include_router(estrai_testo_pdf.router)
        self.client = TestClient(self.app)

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def authenticate(self):
        self.app.dependency_overrides[analizza_cte.current_user] = lambda: USER

    def test_analizza_cte_requires_authentication(self):
        response = self.client.post("/analizza-cte", json={"testo": "contenuto CTE"})

        self.assertEqual(response.status_code, 401)

    def test_estrai_testo_pdf_requires_authentication(self):
        response = self.client.post(
            "/estrai-testo-pdf",
            files={"file": ("cte.pdf", b"%PDF-1.4 test", "application/pdf")},
        )

        self.assertEqual(response.status_code, 401)

    def test_authenticated_user_can_analyze_cte(self):
        self.authenticate()
        expected = {"fornitore": "Test Energia"}

        with patch.object(
            analizza_cte, "estrai_dati_offerta_cte", return_value=expected
        ) as parser:
            response = self.client.post(
                "/analizza-cte", json={"testo": "contenuto CTE"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        parser.assert_called_once_with("contenuto CTE")

    def test_authenticated_user_can_extract_pdf_text(self):
        self.authenticate()

        with patch.object(
            estrai_testo_pdf, "convert_from_path", return_value=[object()]
        ) as convert, patch.object(
            estrai_testo_pdf.pytesseract,
            "image_to_string",
            return_value="testo OCR",
        ) as ocr:
            response = self.client.post(
                "/estrai-testo-pdf",
                files={"file": ("cte.pdf", b"%PDF-1.4 test", "application/pdf")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"filename": "cte.pdf", "contenuto_testo": "testo OCR\n"},
        )
        convert.assert_called_once()
        ocr.assert_called_once()


if __name__ == "__main__":
    unittest.main()
