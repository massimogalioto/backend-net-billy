import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
    import analizza_bolletta as endpoint


class AnalizzaBollettaAuthTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(endpoint.router)
        self.client = TestClient(app)

    def test_accepts_correct_api_key(self):
        with patch.dict(os.environ, {"API_SECRET_KEY": "server-secret"}), patch.object(
            endpoint, "estrai_dati_bolletta", return_value={"tipo_fornitura": "Luce"}
        ) as analyze:
            response = self.client.post(
                "/analizza-bolletta",
                headers={"x-api-key": "server-secret"},
                json={"testo": "testo bolletta"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"tipo_fornitura": "Luce"})
        analyze.assert_called_once_with("testo bolletta")

    def test_rejects_incorrect_api_key(self):
        with patch.dict(os.environ, {"API_SECRET_KEY": "server-secret"}), patch.object(
            endpoint, "estrai_dati_bolletta"
        ) as analyze:
            response = self.client.post(
                "/analizza-bolletta",
                headers={"x-api-key": "wrong-secret"},
                json={"testo": "testo bolletta"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Chiave API non valida"})
        analyze.assert_not_called()

    def test_rejects_missing_api_key(self):
        with patch.dict(os.environ, {"API_SECRET_KEY": "server-secret"}), patch.object(
            endpoint, "estrai_dati_bolletta"
        ) as analyze:
            response = self.client.post(
                "/analizza-bolletta", json={"testo": "testo bolletta"}
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Chiave API non valida"})
        analyze.assert_not_called()

    def test_rejects_when_api_secret_key_is_not_configured(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
            endpoint, "estrai_dati_bolletta"
        ) as analyze:
            response = self.client.post(
                "/analizza-bolletta",
                headers={"x-api-key": "client-secret"},
                json={"testo": "testo bolletta"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Chiave API non valida"})
        analyze.assert_not_called()


if __name__ == "__main__":
    unittest.main()
