"""HTTP client for ScaleDown Extract. It never logs document contents."""
import base64
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

SCALEDOWN_URL = "https://api.scaledown.xyz/v1/chat/completions"


class ScaleDownError(RuntimeError):
    def __init__(self, message: str, *, category: str, status_code: int | None = None,
                 endpoint: str = SCALEDOWN_URL, duration_ms: int | None = None,
                 error_code: str | None = None, invalid_fields: tuple[str, ...] = (),
                 validation_errors: tuple[tuple[str, str], ...] = ()):
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.endpoint = endpoint
        self.duration_ms = duration_ms
        self.error_code = error_code
        self.invalid_fields = invalid_fields
        self.validation_errors = validation_errors
        self.started_at = None
        self.connect_timeout_seconds = None
        self.read_timeout_seconds = None
        self.timeout_type = None


class ScaleDownConfigurationError(ScaleDownError):
    pass


class ScaleDownTimeoutError(ScaleDownError):
    pass


class ScaleDownResponseError(ScaleDownError):
    pass


class ScaleDownEntities(list):
    def __init__(self, values: list[dict], duration_ms: int):
        super().__init__(values)
        self.duration_ms = duration_ms


def _duration_ms(started_at: float) -> int:
    return max(0, round((time.monotonic() - started_at) * 1000))


def _safe_error_code(response) -> str | None:
    try:
        body = response.json()
    except (ValueError, TypeError):
        return None
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    candidate = error.get("code") if isinstance(error, dict) else body.get("code")
    text = str(candidate) if isinstance(candidate, (str, int)) else ""
    return text if re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", text) else None


def _debug_enabled() -> bool:
    return os.getenv("SCALEDOWN_DEBUG", "").strip().lower() == "true"


def _log_request_debug(payload: dict, headers: dict, file_bytes: bytes,
                       timeout_seconds: float, started_at: str) -> None:
    if not _debug_enabled():
        return
    sanitized_payload = dict(payload)
    sanitized_payload["document"] = "[PDF_BASE64_OMESSO]"
    diagnostic = {
        "endpoint": SCALEDOWN_URL,
        "method": "POST",
        "started_at": started_at,
        "model": payload["model"],
        "messages": payload["messages"],
        "entities": payload["entities"],
        "document_mime_type": payload["document_mime_type"],
        "document": sanitized_payload["document"],
        "pdf_size_bytes": len(file_bytes),
        "base64_size_bytes": len(payload["document"].encode("ascii")),
        "payload_json_size_bytes": len(json.dumps(payload).encode("utf-8")),
        "timeout_seconds": timeout_seconds,
        "connect_timeout_seconds": timeout_seconds,
        "read_timeout_seconds": timeout_seconds,
        "header_names": list(headers),
    }
    print(
        "[ScaleDown][Request] " + json.dumps(diagnostic, ensure_ascii=False, separators=(",", ":")),
        file=sys.stderr, flush=True,
    )


def extract_pdf(file_bytes: bytes, entities: dict[str, str]) -> list[dict]:
    api_key = os.getenv("SCALEDOWN_API_KEY")
    if not api_key:
        raise ScaleDownConfigurationError(
            "SCALEDOWN_API_KEY non configurata", category="configuration", duration_ms=0
        )
    payload = {
        "model": "extract",
        "messages": [{"role": "user", "content": "Extract the requested entities from the PDF without inventing missing values."}],
        "entities": entities,
        "document": base64.b64encode(file_bytes).decode("ascii"),
        "document_mime_type": "application/pdf",
    }
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    try:
        timeout_seconds = float(os.getenv("SCALEDOWN_TIMEOUT_SECONDS", "90"))
    except ValueError as error:
        raise ScaleDownConfigurationError(
            "SCALEDOWN_TIMEOUT_SECONDS non valido", category="configuration", duration_ms=0
        ) from error
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ScaleDownConfigurationError(
            "SCALEDOWN_TIMEOUT_SECONDS non valido", category="configuration", duration_ms=0
        )
    started_at_iso = datetime.now(timezone.utc).isoformat()
    _log_request_debug(payload, headers, file_bytes, timeout_seconds, started_at_iso)
    started_at = time.monotonic()
    try:
        response = requests.post(
            SCALEDOWN_URL,
            headers=headers,
            json=payload,
            timeout=timeout_seconds,
        )
    except (requests.ConnectTimeout, requests.ReadTimeout, requests.Timeout) as error:
        if isinstance(error, requests.ConnectTimeout):
            timeout_type = "connect"
        elif isinstance(error, requests.ReadTimeout):
            timeout_type = "read"
        else:
            timeout_type = "unspecified"
        wrapped = ScaleDownTimeoutError(
            "Timeout durante l'estrazione ScaleDown", category="timeout",
            duration_ms=_duration_ms(started_at),
        )
        wrapped.started_at = started_at_iso
        wrapped.connect_timeout_seconds = timeout_seconds
        wrapped.read_timeout_seconds = timeout_seconds
        wrapped.timeout_type = timeout_type
        raise wrapped from error
    except requests.RequestException as error:
        wrapped = ScaleDownError(
            "Connessione a ScaleDown fallita", category="network",
            duration_ms=_duration_ms(started_at),
        )
        wrapped.started_at = started_at_iso
        wrapped.connect_timeout_seconds = timeout_seconds
        wrapped.read_timeout_seconds = timeout_seconds
        raise wrapped from error
    if not response.ok:
        raise ScaleDownError(
            "ScaleDown ha restituito un errore HTTP", category="http",
            status_code=response.status_code, duration_ms=_duration_ms(started_at),
            error_code=_safe_error_code(response),
        )
    try:
        envelope = response.json()
        content = envelope["choices"][0]["message"]["content"]
        decoded = json.loads(content) if isinstance(content, str) else content
        result = decoded["entities"]
    except (ValueError, TypeError, KeyError, IndexError) as error:
        raise ScaleDownResponseError(
            "Risposta ScaleDown malformata", category="response_format",
            status_code=response.status_code, duration_ms=_duration_ms(started_at),
        ) from error
    if not isinstance(result, list):
        raise ScaleDownResponseError(
            "Entità ScaleDown mancanti", category="response_format",
            status_code=response.status_code, duration_ms=_duration_ms(started_at),
        )
    parsed = []
    for item in result:
        if not isinstance(item, dict) or not isinstance(item.get("type"), str) or not isinstance(item.get("text"), str):
            raise ScaleDownResponseError(
                "Entità ScaleDown malformata", category="response_format",
                status_code=response.status_code, duration_ms=_duration_ms(started_at),
            )
        confidence = item.get("confidence")
        if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (int, float))):
            raise ScaleDownResponseError(
                "Confidence ScaleDown malformata", category="response_format",
                status_code=response.status_code, duration_ms=_duration_ms(started_at),
            )
        parsed.append({
            "type": item["type"], "text": item["text"], "confidence": confidence,
            "start": item.get("start"), "end": item.get("end"), "context": item.get("context"),
        })
    return ScaleDownEntities(parsed, _duration_ms(started_at))


def emit_error_diagnostic(error: ScaleDownError) -> None:
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
        "validation_errors": [
            {"field": field, "type": error_type}
            for field, error_type in error.validation_errors
        ],
    }
    print(
        "[ScaleDown][Error] " + json.dumps(diagnostic, ensure_ascii=False, separators=(",", ":")),
        file=sys.stderr, flush=True,
    )
