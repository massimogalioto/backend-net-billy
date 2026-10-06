"""Duplicate lookup and save contracts without OCR, AI or Bucket calls."""
import base64
import json
import unittest
from unittest.mock import MagicMock, patch

import database_service as database
import salva_offerta_endpoint as endpoint


OFFER = dict(fornitore=" Edison ", nome_offerta="Test", tipologia_cliente="Residenziale",
             tipo_fornitura="Luce", tariffa="Fisso", prezzo_kwh=0.12,
             spread=None, costo_fisso=10, valid_until="2026-12-31")


class DuplicateTests(unittest.TestCase):
    def lookup(self, offer, row=None, tenant="tenant-a"):
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = row
        with patch.object(database, "_connection", return_value=connection), patch.dict(
            "os.environ", {"DEFAULT_TENANT_ID": tenant}
        ):
            result = database.find_duplicate_cte_offer(offer)
        return result, cursor.execute.call_args.args

    def test_lookup_uses_only_null_safe_fingerprint_and_backend_tenant(self):
        result, (sql, params) = self.lookup({**OFFER, "tenant_id": "frontend-tenant"}, {"id": "existing"})
        self.assertEqual(result, "existing")
        self.assertEqual(params, ("tenant-a", "Edison", "Residenziale", "Luce", "Fisso",
                                  "2026-12-31", 0.12, None, 10, None, None))
        self.assertEqual(sql.count("IS NOT DISTINCT FROM"), 10)
        for excluded in ("offer_name", "pdf_filename", "pdf_object_key", "source_cte"):
            self.assertNotIn(excluded, sql)

    def test_variable_and_other_null_fields_are_preserved(self):
        result, (_, params) = self.lookup({**OFFER, "prezzo_kwh": None, "spread": 0.015,
                                          "costo_fisso": None, "valid_until": None,
                                          "fornitore": None, "tariffa": "Variabile"})
        self.assertIsNone(result)
        self.assertEqual(params, ("tenant-a", None, "Residenziale", "Luce", "Variabile",
                                  None, None, 0.015, None, None, None))

    def test_price_tariff_and_tenant_changes_reach_lookup(self):
        _, (_, original) = self.lookup(OFFER)
        for field, value, index in (("prezzo_kwh", 0.13, 6), ("tariffa", "Variabile", 4)):
            _, (_, changed) = self.lookup({**OFFER, field: value})
            self.assertNotEqual(original[index], changed[index])
        _, (_, changed) = self.lookup(OFFER, tenant="tenant-b")
        self.assertNotEqual(original[0], changed[0])

    def test_different_power_ranges_are_part_of_the_duplicate_fingerprint(self):
        _, (_, first) = self.lookup({**OFFER, "min_power_kw": 10, "max_power_kw": 20})
        _, (_, second) = self.lookup({**OFFER, "min_power_kw": 21, "max_power_kw": 50})
        self.assertNotEqual(first[-2:], second[-2:])

    def test_offer_input_defaults_to_no_power_limits(self):
        offer = endpoint.OffertaInput(**OFFER)
        self.assertIsNone(offer.min_power_kw)
        self.assertIsNone(offer.max_power_kw)

    def test_validation_error_keeps_extracted_data_without_pdf_or_tenant(self):
        payload = {**OFFER, "tipo_fornitura": None, "tenant_id": "browser-tenant",
                   "cte_pdf": {"filename": "test.pdf", "content_base64": "secret"}}
        with patch.dict("os.environ", {"API_SECRET_KEY": "test"}):
            response = endpoint.salva(payload, "test")
        self.assertEqual(response.status_code, 422)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "validation_error")
        self.assertEqual(body["extracted_data"]["tipo_fornitura"], None)
        self.assertNotIn("cte_pdf", body["extracted_data"])
        self.assertNotIn("tenant_id", body["extracted_data"])

    def test_manual_save_reuses_standard_duplicate_and_pdf_flow_without_ai(self):
        payload = {**OFFER, "tipo_fornitura": "luce", "cte_pdf": {
            "filename": "test.pdf", "content_base64": base64.b64encode(b"%PDF-original").decode(),
        }}
        with patch.dict("os.environ", {"API_SECRET_KEY": "test"}), patch.object(
            endpoint, "find_duplicate_cte_offer", return_value=None
        ) as duplicate, patch.object(
            endpoint, "upload_cte_pdf", return_value={"object_key": "cte/key", "filename": "test.pdf", "content_type": "application/pdf", "size_bytes": 13}
        ) as upload, patch.object(endpoint, "insert_offer", return_value="new") as insert:
            self.assertEqual(endpoint.salva_manuale(payload, "test"), {"successo": True, "id": "new"})
        duplicate.assert_called_once()
        upload.assert_called_once()
        insert.assert_called_once()

    def test_duplicate_returns_flat_409_without_upload_or_insert(self):
        offer = endpoint.OffertaInput(**OFFER, cte_pdf={"filename": "test.pdf",
            "content_base64": base64.b64encode(b"%PDF-original").decode()})
        with patch.dict("os.environ", {"API_SECRET_KEY": "test"}), patch.object(
            endpoint, "find_duplicate_cte_offer", return_value="existing"
        ), patch.object(endpoint, "upload_cte_pdf") as upload, patch.object(endpoint, "insert_offer") as insert:
            response = endpoint.salva(offer, "test")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(json.loads(response.body), {"detail": "CTE già presente", "existing_offer_id": "existing"})
        upload.assert_not_called()
        insert.assert_not_called()

    def test_new_offer_checks_before_upload_and_insert(self):
        offer = endpoint.OffertaInput(**OFFER, cte_pdf={"filename": "test.pdf",
            "content_base64": base64.b64encode(b"%PDF-original").decode()})
        calls = []
        with patch.dict("os.environ", {"API_SECRET_KEY": "test"}), patch.object(
            endpoint, "find_duplicate_cte_offer", side_effect=lambda data: calls.append("check")
        ), patch.object(endpoint, "upload_cte_pdf", side_effect=lambda *args: calls.append("upload") or {"object_key": "pdf"}), patch.object(
            endpoint, "insert_offer", side_effect=lambda *args: calls.append("insert") or "new"
        ):
            self.assertEqual(endpoint.salva(offer, "test"), {"successo": True, "id": "new"})
        self.assertEqual(calls, ["check", "upload", "insert"])


if __name__ == "__main__":
    unittest.main()
