import asyncio
import io
import types
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import upload_pdf
import bolletta_extraction as bill_extraction
from auth_service import CurrentUser
from scaledown_provider import ScaleDownEntities


PDF = b"%PDF-1.7 original-bill"
USER = CurrentUser("user-a", "demo@example.test", "Demo", "tenant-a", "Tenant", "FREE", "Free")
BILL = {
    "cliente": "Mario", "indirizzo": "Via Roma", "pod": "IT001", "kwh_totali": 459.0,
    "mesi_bolletta": 2, "spesa_materia_energia": 105.09, "spesa_vendita_energia": 105.09,
    "quota_fissa_vendita": 8.34, "tipo_fornitura": "Luce", "tipologia_cliente": "Residenziale",
    "potenza_kw": 3.0,
}


class BillPipelineTests(unittest.TestCase):
    def slot_context(self):
        context = Mock()
        slot = Mock()
        context.__enter__ = Mock(return_value=slot)
        context.__exit__ = Mock(return_value=False)
        return context, slot

    def test_original_pdf_reaches_bill_extractor_and_response_is_compatible(self):
        file = types.SimpleNamespace(filename="bill.pdf", file=io.BytesIO(PDF))
        context, slot = self.slot_context()
        offers = [{"nome_offerta": "Test"}]
        with patch.object(upload_pdf, "comparison_slot", return_value=context) as quota, patch.object(
            upload_pdf, "extract_bolletta", return_value=BILL
        ) as extract, patch.object(upload_pdf, "confronta_offerte", return_value=offers) as compare:
            result = asyncio.run(upload_pdf.upload_bolletta(file, USER))
        self.assertEqual(result, {"bolletta": BILL, "offerte": offers})
        extract.assert_called_once_with(PDF)
        quota.assert_called_once_with("tenant-a", "user-a")
        self.assertEqual(compare.call_args.kwargs["tenant_id"], "tenant-a")
        self.assertEqual(compare.call_args.args[0]["spesa_vendita_energia"], 105.09)
        slot.record_success.assert_called_once_with("Luce")
        self.assertNotIn("pytesseract", upload_pdf.__dict__)
        self.assertNotIn("convert_from_path", upload_pdf.__dict__)
        self.assertNotIn("estrai_dati_bolletta", upload_pdf.__dict__)

    def test_ordered_photos_become_one_pdf_one_extraction_and_one_comparison(self):
        photos = [object(), object(), object()]
        generated_pdf = b"%PDF-generated-from-three-pages"
        context, slot = self.slot_context()
        offers = [{"nome_offerta": "Test"}]
        with patch.object(upload_pdf, "comparison_slot", return_value=context), patch.object(
            upload_pdf, "prepare_bill_pdf", return_value=generated_pdf
        ) as prepare, patch.object(
            upload_pdf, "extract_bolletta", return_value=BILL
        ) as extract, patch.object(upload_pdf, "confronta_offerte", return_value=offers) as compare:
            result = asyncio.run(upload_pdf.upload_bolletta(None, USER, photos))
        self.assertEqual(result, {"bolletta": BILL, "offerte": offers})
        prepare.assert_called_once_with(None, photos)
        extract.assert_called_once_with(generated_pdf)
        compare.assert_called_once()
        slot.record_success.assert_called_once_with("Luce")

    def test_route_accepts_repeated_images_multipart_field(self):
        app = FastAPI()
        app.include_router(upload_pdf.router)
        app.dependency_overrides[upload_pdf.current_user] = lambda: USER
        context, _slot = self.slot_context()
        with patch.object(upload_pdf, "comparison_slot", return_value=context), patch.object(
            upload_pdf, "prepare_bill_pdf", return_value=b"%PDF-generated"
        ) as prepare, patch.object(upload_pdf, "extract_bolletta", return_value=BILL), patch.object(
            upload_pdf, "confronta_offerte", return_value=[]
        ):
            response = TestClient(app).post("/upload-bolletta", files=[
                ("images", ("page-1.jpg", b"first", "image/jpeg")),
                ("images", ("page-2.webp", b"second", "image/webp")),
            ])
        self.assertEqual(response.status_code, 200, response.text)
        pdf_file, images = prepare.call_args.args
        self.assertIsNone(pdf_file)
        self.assertEqual([image.filename for image in images], ["page-1.jpg", "page-2.webp"])

    def test_missing_required_field_does_not_call_comparison(self):
        file = types.SimpleNamespace(filename="bill.pdf", file=io.BytesIO(PDF))
        context, _slot = self.slot_context()
        with patch.object(upload_pdf, "comparison_slot", return_value=context), patch.object(
            upload_pdf, "extract_bolletta", return_value={**BILL, "spesa_vendita_energia": None}
        ), patch.object(upload_pdf, "confronta_offerte") as compare:
            result = asyncio.run(upload_pdf.upload_bolletta(file, USER))
        self.assertEqual(result["errore"], "Campo mancante nella risposta AI")
        self.assertEqual(result["mancanti"], ["spesa_vendita_energia"])
        self.assertIsNone(result["output_ai"]["spesa_vendita_energia"])
        compare.assert_not_called()

    def test_fallback_still_accounts_for_only_one_comparison(self):
        file = types.SimpleNamespace(filename="a2a.pdf", file=io.BytesIO(PDF))
        context, slot = self.slot_context()
        recovered = ScaleDownEntities([
            {"type": "kwh_totali", "text": "299"},
            {"type": "mesi_bolletta", "text": "2"},
            {"type": "spesa_vendita_energia", "text": "86,24"},
            {"type": "quota_fissa_vendita", "text": "5,06"},
            {"type": "periodicita_quota_fissa", "text": "Totale periodo"},
            {"type": "tipo_fornitura", "text": "Energia elettrica"},
            {"type": "tipologia_cliente", "text": "Altri Usi"},
            {"type": "potenza_kw", "text": "3"},
        ], 10)
        with patch.object(upload_pdf, "comparison_slot", return_value=context), patch.object(
            bill_extraction, "extract_pdf", side_effect=[ScaleDownEntities([], 5), recovered]
        ) as provider, patch.object(upload_pdf, "confronta_offerte", return_value=[{"nome_offerta": "Test"}]) as compare:
            result = asyncio.run(upload_pdf.upload_bolletta(file, USER))
        self.assertEqual(provider.call_count, 2)
        compare.assert_called_once()
        slot.record_success.assert_called_once_with("Luce")
        self.assertEqual(result["bolletta"]["quota_fissa_vendita"], 2.53)


if __name__ == "__main__":
    unittest.main()
