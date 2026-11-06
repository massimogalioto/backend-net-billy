"""Prepare a bill PDF from either an original PDF or ordered page photographs."""
from __future__ import annotations

import io
import os
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError


SUPPORTED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def _positive_env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


MAX_BILL_IMAGES = _positive_env_int("BILL_MAX_IMAGES", 12)
MAX_BILL_IMAGE_BYTES = _positive_env_int("BILL_MAX_IMAGE_BYTES", 10 * 1024 * 1024)
MAX_BILL_TOTAL_IMAGE_BYTES = _positive_env_int("BILL_MAX_TOTAL_IMAGE_BYTES", 50 * 1024 * 1024)
MAX_BILL_PDF_BYTES = _positive_env_int("BILL_MAX_PDF_BYTES", 25 * 1024 * 1024)
MAX_BILL_IMAGE_PIXELS = _positive_env_int("BILL_MAX_IMAGE_PIXELS", 40_000_000)


class BillDocumentError(ValueError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _read_limited(upload, limit: int, label: str) -> bytes:
    upload.file.seek(0)
    content = upload.file.read(limit + 1)
    if not content:
        raise BillDocumentError(422, f"{label} è vuoto")
    if len(content) > limit:
        raise BillDocumentError(413, f"{label} supera il limite di {limit // (1024 * 1024)} MB")
    return content


def _rgb_page(content: bytes) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as source:
                source.load()
                if (source.format or "").upper() not in SUPPORTED_IMAGE_FORMATS:
                    raise BillDocumentError(415, "Formato immagine non supportato: usa JPG, PNG o WEBP")
                if source.width * source.height > MAX_BILL_IMAGE_PIXELS:
                    raise BillDocumentError(413, "Una fotografia supera il limite massimo di risoluzione")
                oriented = ImageOps.exif_transpose(source)
                try:
                    if oriented.mode in {"RGBA", "LA"} or "transparency" in oriented.info:
                        rgba = oriented.convert("RGBA")
                        try:
                            page = Image.new("RGB", rgba.size, "white")
                            page.paste(rgba, mask=rgba.getchannel("A"))
                            return page
                        finally:
                            rgba.close()
                    return oriented.convert("RGB")
                finally:
                    if oriented is not source:
                        oriented.close()
    except BillDocumentError:
        raise
    except (
        UnidentifiedImageError, OSError, SyntaxError,
        Image.DecompressionBombError, Image.DecompressionBombWarning,
    ) as error:
        raise BillDocumentError(422, "Una fotografia non è valida o è danneggiata") from error


def images_to_pdf(contents: list[bytes]) -> bytes:
    if not contents:
        raise BillDocumentError(400, "Carica almeno una fotografia")
    pages: list[Image.Image] = []
    output = io.BytesIO()
    try:
        for content in contents:
            pages.append(_rgb_page(content))
        pages[0].save(
            output,
            format="PDF",
            save_all=True,
            append_images=pages[1:],
            resolution=200.0,
            quality=90,
            optimize=False,
        )
        pdf = output.getvalue()
    except BillDocumentError:
        raise
    except (OSError, ValueError) as error:
        raise BillDocumentError(422, "Impossibile creare il PDF dalle fotografie") from error
    finally:
        for page in pages:
            page.close()
        output.close()
    if not pdf.startswith(b"%PDF-"):
        raise BillDocumentError(422, "Il PDF generato dalle fotografie non è valido")
    if len(pdf) > MAX_BILL_PDF_BYTES:
        raise BillDocumentError(413, "Il PDF generato supera il limite di 25 MB")
    return pdf


def prepare_bill_pdf(pdf_file=None, image_files=None) -> bytes:
    images = list(image_files or [])
    if pdf_file is not None and images:
        raise BillDocumentError(400, "Carica un PDF oppure delle fotografie, non entrambi")
    if pdf_file is None and not images:
        raise BillDocumentError(400, "Carica un PDF oppure almeno una fotografia")
    if pdf_file is not None:
        if not (pdf_file.filename or "").lower().endswith(".pdf"):
            raise BillDocumentError(400, "Il file deve essere un PDF")
        pdf = _read_limited(pdf_file, MAX_BILL_PDF_BYTES, "Il PDF")
        if b"%PDF-" not in pdf[:1024]:
            raise BillDocumentError(422, "Il file non contiene un PDF originale valido")
        return pdf
    if len(images) > MAX_BILL_IMAGES:
        raise BillDocumentError(413, f"Puoi caricare al massimo {MAX_BILL_IMAGES} fotografie")
    contents = []
    total_size = 0
    for image in images:
        content = _read_limited(image, MAX_BILL_IMAGE_BYTES, "Una fotografia")
        total_size += len(content)
        if total_size > MAX_BILL_TOTAL_IMAGE_BYTES:
            raise BillDocumentError(413, "Le fotografie superano il limite complessivo consentito")
        contents.append(content)
    return images_to_pdf(contents)
