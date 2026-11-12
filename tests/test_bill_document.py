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


def noisy_image_bytes(size=(2600, 1800), quality=98):
    output = io.BytesIO()
    with Image.effect_noise(size, 80).convert("RGB") as image:
        image.save(output, format="JPEG", quality=quality)
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

    def test_twenty_megapixel_photo_is_resized_to_max_side(self):
        content = image_bytes(size=(5000, 4000))
        page, optimized_size, quality = document._optimized_page(content)
        try:
            self.assertEqual(page.size, (2000, 1600))
            self.assertLess(optimized_size, len(content))
            self.assertGreaterEqual(quality, 75)
        finally:
            page.close()

    def test_high_quality_twenty_megapixel_upload_fits_new_original_limit(self):
        content = noisy_image_bytes(size=(5000, 4000), quality=90)
        self.assertGreater(len(content), 10 * 1024 * 1024)
        self.assertLessEqual(len(content), document.MAX_BILL_IMAGE_BYTES)
        self.assertEqual(
            document._read_limited(upload("phone.jpg", content), document.MAX_BILL_IMAGE_BYTES, "Una fotografia"),
            content,
        )

    def test_large_jpeg_is_reduced_without_dropping_below_minimum_quality(self):
        content = noisy_image_bytes()
        page, optimized_size, quality = document._optimized_page(content)
        try:
            self.assertEqual(max(page.size), 2000)
            self.assertLess(optimized_size, len(content))
            self.assertGreaterEqual(quality, document.MIN_BILL_IMAGE_QUALITY)
        finally:
            page.close()

    def test_small_photo_is_not_upscaled(self):
        page, _optimized_size, _quality = document._optimized_page(
            image_bytes(size=(640, 480))
        )
        try:
            self.assertEqual(page.size, (640, 480))
        finally:
            page.close()

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
        with patch.object(document, "GENERATED_BILL_PDF_BYTES", 10), self.assertRaises(document.BillDocumentError):
            document.prepare_bill_pdf(image_files=[upload("page.jpg", image_bytes())])

    def test_generated_pdf_gets_only_one_additional_optimization_attempt(self):
        oversized = b"%PDF-" + (b"x" * 100)
        with patch.object(document, "GENERATED_BILL_PDF_BYTES", 50), patch.object(
            document, "_build_pdf", side_effect=[oversized, oversized]
        ) as build, self.assertRaises(document.BillDocumentError) as raised:
            document.images_to_pdf([image_bytes()])
        self.assertEqual(raised.exception.status_code, 413)
        self.assertEqual(build.call_count, 2)

    def test_safe_diagnostics_report_sizes_without_image_content(self):
        marker = b"private-image-marker"
        content = image_bytes()
        with self.assertLogs(document.logger, level="INFO") as captured:
            document.images_to_pdf([content])
        log_output = " ".join(captured.output)
        self.assertIn("image_count=1", log_output)
        self.assertIn(f"original_bytes={len(content)}", log_output)
        self.assertIn("optimized_bytes=", log_output)
        self.assertIn("pdf_bytes=", log_output)
        self.assertNotIn(marker.decode(), log_output)

    def test_loaded_pages_are_closed_when_a_later_page_fails(self):
        first_page = Mock()
        with patch.object(document, "_optimized_page", side_effect=[
            (first_page, 100, 85), document.BillDocumentError(422, "corrupt"),
        ]), self.assertRaises(document.BillDocumentError):
            document.images_to_pdf([b"first", b"second"])
        first_page.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
