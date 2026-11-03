import asyncio
import io
import types
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

import upload_pdf
from auth_service import CurrentUser


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


if __name__ == "__main__":
    unittest.main()
