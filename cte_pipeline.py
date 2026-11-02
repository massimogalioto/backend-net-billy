"""Shared synchronous CTE pipeline; callers run it outside the event loop."""
import logging

from fastapi import HTTPException

from document_extraction import extract_document
from document_schemas import DOCUMENT_SCHEMAS
from scaledown_provider import ScaleDownConfigurationError, ScaleDownError, ScaleDownTimeoutError

logger = logging.getLogger("uvicorn.error")
MAX_CTE_PDF_BYTES = 25 * 1024 * 1024


def _log_scaledown_error(error: ScaleDownError) -> None:
    logger.error(
        "[CTE][ScaleDown] endpoint=%s category=%s status=%s started_at=%s duration_ms=%s timeout_type=%s connect_timeout_seconds=%s read_timeout_seconds=%s error_code=%s invalid_fields=%s",
        error.endpoint, error.category, error.status_code if error.status_code is not None else "-",
        error.started_at or "-", error.duration_ms if error.duration_ms is not None else "-",
        error.timeout_type or "-",
        error.connect_timeout_seconds if error.connect_timeout_seconds is not None else "-",
        error.read_timeout_seconds if error.read_timeout_seconds is not None else "-", error.error_code or "-",
        ",".join(error.invalid_fields) if error.invalid_fields else "-",
    )


def processa_cte(file):
    logger.info("[CTE] Inizio elaborazione")
    try:
        file.file.seek(0)
        file_bytes = file.file.read(MAX_CTE_PDF_BYTES + 1)
        if len(file_bytes) > MAX_CTE_PDF_BYTES:
            raise HTTPException(status_code=413, detail="Il PDF supera il limite di 25 MB")
        if not file_bytes or b"%PDF-" not in file_bytes[:1024]:
            raise HTTPException(status_code=422, detail="Il file non contiene un PDF originale valido")
        result = extract_document(file_bytes, "cte", DOCUMENT_SCHEMAS["cte"])
        logger.info("[CTE] Estrazione completata")
        return result
    except ScaleDownConfigurationError as error:
        _log_scaledown_error(error)
        raise HTTPException(status_code=503, detail="Servizio ScaleDown non configurato") from error
    except ScaleDownTimeoutError as error:
        _log_scaledown_error(error)
        raise HTTPException(status_code=504, detail="Timeout durante l'estrazione del PDF") from error
    except ScaleDownError as error:
        _log_scaledown_error(error)
        raise HTTPException(status_code=502, detail="Estrazione ScaleDown fallita") from error
    except Exception:
        logger.error("[CTE] Elaborazione fallita")
        raise
    finally:
        logger.info("[CTE] Fine elaborazione")
