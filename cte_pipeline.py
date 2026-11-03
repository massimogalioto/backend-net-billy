"""Shared synchronous CTE pipeline; callers run it outside the event loop."""
import logging
import json
import sys

from fastapi import HTTPException

from document_extraction import extract_document
from document_schemas import DOCUMENT_SCHEMAS
from scaledown_provider import ScaleDownConfigurationError, ScaleDownError, ScaleDownTimeoutError

logger = logging.getLogger("uvicorn.error")
MAX_CTE_PDF_BYTES = 25 * 1024 * 1024


def _log_scaledown_error(error: ScaleDownError) -> None:
    diagnostic = {
        "endpoint": error.endpoint,
        "category": error.category,
        "status": error.status_code,
        "started_at": error.started_at,
        "duration_ms": error.duration_ms,
        "timeout_type": error.timeout_type,
        "connect_timeout_seconds": error.connect_timeout_seconds,
        "read_timeout_seconds": error.read_timeout_seconds,
        "error_code": error.error_code,
        "invalid_fields": list(error.invalid_fields),
    }
    print(
        "[CTE][ScaleDown][Error] " + json.dumps(diagnostic, ensure_ascii=False, separators=(",", ":")),
        file=sys.stderr, flush=True,
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
