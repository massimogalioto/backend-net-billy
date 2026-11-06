import io
import types
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from PyPDF2 import PdfReader

import bill_document as document


def upload(name: str, content: bytes):
    return types.SimpleNamespace(filename=name, file=io.BytesIO(content))


def image_bytes(fmt="JPEG", size=(120, 200), color="white", orientation=None):
    output = io.BytesIO()
    with Image.new("RGB", size, color) as image:
        if orientation:
            exif = Image.Exif()
            exif[274] = orientation
            image.save(output, format=fmt, exif=exif)
        else:
            image.save(output, format=fmt)
    return output.getvalue()


class BillDocumentTests(unittest.TestCase):
    def test_original_pdf_is_returned_without_conversion(self):
        original = b"%PDF-1.7\noriginal exact bytes"
        self.assertEqual(document.prepare_bill_pdf(upload("bill.pdf", original)), original)

    def test_one_and_multiple_photos_create_ordered_pdf(self):
        single = document.prepare_bill_pdf(image_files=[upload("one.jpg", image_bytes())])
        self.assertEqual(len(PdfReader(io.BytesIO(single)).pages), 1)
        combined = document.prepare_bill_pdf(image_files=[
            upload("portrait.jpg", image_bytes(size=(100, 240), color="red")),
            upload("landscape.png", image_bytes(fmt="PNG", size=(300, 100), color="blue")),
        ])
        pages = PdfReader(io.BytesIO(combined)).pages
        self.assertEqual(len(pages), 2)
        self.assertLess(float(pages[0].mediabox.width), float(pages[0].mediabox.height))
        self.assertGreater(float(pages[1].mediabox.width), float(pages[1].mediabox.height))

    def test_exif_orientation_and_webp_are_supported(self):
        rotated = document.prepare_bill_pdf(image_files=[
            upload("phone.jpg", image_bytes(size=(60, 140), orientation=6)),
            upload("page.webp", image_bytes(fmt="WEBP", size=(120, 180))),
        ])
        pages = PdfReader(io.BytesIO(rotated)).pages
        self.assertGreater(float(pages[0].mediabox.width), float(pages[0].mediabox.height))
        self.assertEqual(len(pages), 2)

    def test_corrupt_unsupported_and_conflicting_inputs_are_rejected(self):
        cases = (
            (422, lambda: document.prepare_bill_pdf(image_files=[upload("bad.jpg", b"not an image")])),
            (415, lambda: document.prepare_bill_pdf(image_files=[upload("page.gif", image_bytes(fmt="GIF"))])),
            (400, lambda: document.prepare_bill_pdf(
                upload("bill.pdf", b"%PDF-1.7 ok"), [upload("page.jpg", image_bytes())]
            )),
            (400, lambda: document.prepare_bill_pdf()),
        )
        for status, call in cases:
            with self.subTest(status=status), self.assertRaises(document.BillDocumentError) as raised:
                call()
            self.assertEqual(raised.exception.status_code, status)

    def test_count_file_total_and_generated_pdf_limits(self):
        photo = upload("page.jpg", image_bytes())
        with patch.object(document, "MAX_BILL_IMAGES", 1), self.assertRaises(document.BillDocumentError) as count:
            document.prepare_bill_pdf(image_files=[photo, photo])
        self.assertEqual(count.exception.status_code, 413)
        with patch.object(document, "MAX_BILL_IMAGE_BYTES", 10), self.assertRaises(document.BillDocumentError) as size:
            document.prepare_bill_pdf(image_files=[upload("large.jpg", image_bytes())])
        self.assertEqual(size.exception.status_code, 413)
        with patch.object(document, "MAX_BILL_TOTAL_IMAGE_BYTES", 100), self.assertRaises(document.BillDocumentError):
            document.prepare_bill_pdf(image_files=[upload("page.jpg", image_bytes())])
        with patch.object(document, "MAX_BILL_PDF_BYTES", 10), self.assertRaises(document.BillDocumentError):
            document.prepare_bill_pdf(image_files=[upload("page.jpg", image_bytes())])

    def test_loaded_pages_are_closed_when_a_later_page_fails(self):
        first_page = Mock()
        with patch.object(document, "_rgb_page", side_effect=[
            first_page, document.BillDocumentError(422, "corrupt"),
        ]), self.assertRaises(document.BillDocumentError):
            document.images_to_pdf([b"first", b"second"])
        first_page.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
