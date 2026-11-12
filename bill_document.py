"""Prepare a bill PDF from either an original PDF or ordered page photographs."""
from __future__ import annotations

import io
import logging
import os
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError


SUPPORTED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
logger = logging.getLogger("uvicorn.error")


def _positive_env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


MAX_BILL_IMAGES = _positive_env_int("BILL_MAX_IMAGES", 12)
MAX_BILL_IMAGE_BYTES = _positive_env_int("BILL_MAX_IMAGE_BYTES", 25 * 1024 * 1024)
MAX_BILL_TOTAL_IMAGE_BYTES = _positive_env_int("BILL_MAX_TOTAL_IMAGE_BYTES", 100 * 1024 * 1024)
MAX_BILL_PDF_BYTES = _positive_env_int("BILL_MAX_PDF_BYTES", 25 * 1024 * 1024)
MAX_BILL_IMAGE_PIXELS = _positive_env_int("BILL_MAX_IMAGE_PIXELS", 40_000_000)
MAX_BILL_IMAGE_SIDE = _positive_env_int("BILL_MAX_IMAGE_SIDE", 2_000)
TARGET_BILL_IMAGE_BYTES = _positive_env_int("BILL_TARGET_IMAGE_BYTES", 1024 * 1024)
INITIAL_BILL_IMAGE_QUALITY = max(75, min(_positive_env_int("BILL_IMAGE_QUALITY", 85), 95))
MIN_BILL_IMAGE_QUALITY = max(75, min(
    _positive_env_int("BILL_MIN_IMAGE_QUALITY", 75),
    INITIAL_BILL_IMAGE_QUALITY,
))
GENERATED_BILL_PDF_BYTES = min(
    _positive_env_int("BILL_MAX_GENERATED_PDF_BYTES", 20 * 1024 * 1024),
    MAX_BILL_PDF_BYTES,
)


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


def _jpeg_size(page: Image.Image, quality: int) -> int:
    output = io.BytesIO()
    try:
        page.save(output, format="JPEG", quality=quality, optimize=True)
        return output.tell()
    finally:
        output.close()


def _optimized_page(content: bytes) -> tuple[Image.Image, int, int]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as source:
                if (source.format or "").upper() not in SUPPORTED_IMAGE_FORMATS:
                    raise BillDocumentError(415, "Formato immagine non supportato: usa JPG, PNG o WEBP")
                if source.width * source.height > MAX_BILL_IMAGE_PIXELS:
                    raise BillDocumentError(413, "Una fotografia supera il limite massimo di risoluzione")
                source.load()
                oriented = ImageOps.exif_transpose(source)
                try:
                    if oriented.mode in {"RGBA", "LA"} or "transparency" in oriented.info:
                        rgba = oriented.convert("RGBA")
                        try:
                            rgb = Image.new("RGB", rgba.size, "white")
                            rgb.paste(rgba, mask=rgba.getchannel("A"))
                        finally:
                            rgba.close()
                    else:
                        rgb = oriented.convert("RGB")
                finally:
                    if oriented is not source:
                        oriented.close()

                try:
                    if max(rgb.size) > MAX_BILL_IMAGE_SIDE:
                        ratio = MAX_BILL_IMAGE_SIDE / max(rgb.size)
                        resized = rgb.resize(
                            (max(1, round(rgb.width * ratio)), max(1, round(rgb.height * ratio))),
                            Image.Resampling.LANCZOS,
                        )
                        rgb.close()
                        rgb = resized

                    quality = INITIAL_BILL_IMAGE_QUALITY
                    optimized_size = _jpeg_size(rgb, quality)
                    while optimized_size > TARGET_BILL_IMAGE_BYTES and quality > MIN_BILL_IMAGE_QUALITY:
                        quality = max(MIN_BILL_IMAGE_QUALITY, quality - 5)
                        optimized_size = _jpeg_size(rgb, quality)
                    return rgb, optimized_size, quality
                except Exception:
                    rgb.close()
                    raise
    except BillDocumentError:
        raise
    except (
        UnidentifiedImageError, OSError, SyntaxError,
        Image.DecompressionBombError, Image.DecompressionBombWarning,
    ) as error:
        raise BillDocumentError(422, "Una fotografia non è valida o è danneggiata") from error


def _build_pdf(pages: list[Image.Image], quality: int) -> bytes:
    output = io.BytesIO()
    try:
        pages[0].save(
            output,
            format="PDF",
            save_all=True,
            append_images=pages[1:],
            resolution=200.0,
            quality=quality,
            optimize=True,
        )
        return output.getvalue()
    finally:
        output.close()


def images_to_pdf(contents: list[bytes]) -> bytes:
    if not contents:
        raise BillDocumentError(400, "Carica almeno una fotografia")
    pages: list[Image.Image] = []
    optimized_total = 0
    selected_quality = INITIAL_BILL_IMAGE_QUALITY
    second_pass = False
    try:
        for content in contents:
            page, optimized_size, quality = _optimized_page(content)
            pages.append(page)
            optimized_total += optimized_size
            selected_quality = min(selected_quality, quality)
        if pages and selected_quality < INITIAL_BILL_IMAGE_QUALITY:
            optimized_total = sum(_jpeg_size(page, selected_quality) for page in pages)
        pdf = _build_pdf(pages, selected_quality)
        if len(pdf) > GENERATED_BILL_PDF_BYTES:
            second_pass = True
            logger.warning(
                "[BILL][PhotoPreparation] generated_pdf_limit_exceeded pdf_bytes=%d limit_bytes=%d",
                len(pdf), GENERATED_BILL_PDF_BYTES,
            )
            optimized_total = sum(_jpeg_size(page, MIN_BILL_IMAGE_QUALITY) for page in pages)
            pdf = _build_pdf(pages, MIN_BILL_IMAGE_QUALITY)
    except BillDocumentError:
        raise
    except (OSError, ValueError) as error:
        raise BillDocumentError(422, "Impossibile creare il PDF dalle fotografie") from error
    finally:
        for page in pages:
            page.close()
    logger.info(
        "[BILL][PhotoPreparation] image_count=%d original_bytes=%d optimized_bytes=%d "
        "pdf_bytes=%d second_pass=%s",
        len(contents), sum(map(len, contents)), optimized_total, len(pdf), second_pass,
    )
    if not pdf.startswith(b"%PDF-"):
        raise BillDocumentError(422, "Il PDF generato dalle fotografie non è valido")
    if len(pdf) > GENERATED_BILL_PDF_BYTES:
        limit_mb = GENERATED_BILL_PDF_BYTES / (1024 * 1024)
        raise BillDocumentError(413, f"Il PDF generato supera il limite di {limit_mb:g} MB")
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
        logger.warning(
            "[BILL][PhotoPreparation] image_count_limit_exceeded image_count=%d limit=%d",
            len(images), MAX_BILL_IMAGES,
        )
        raise BillDocumentError(413, f"Puoi caricare al massimo {MAX_BILL_IMAGES} fotografie")
    contents = []
    total_size = 0
    for image in images:
        content = _read_limited(image, MAX_BILL_IMAGE_BYTES, "Una fotografia")
        total_size += len(content)
        if total_size > MAX_BILL_TOTAL_IMAGE_BYTES:
            logger.warning(
                "[BILL][PhotoPreparation] original_total_limit_exceeded original_bytes=%d limit_bytes=%d",
                total_size, MAX_BILL_TOTAL_IMAGE_BYTES,
            )
            raise BillDocumentError(413, "Le fotografie superano il limite complessivo consentito")
        contents.append(content)
    return images_to_pdf(contents)
