"""HTTP client for ScaleDown Extract. It never logs document contents."""
import base64
import json
import os
import re
import time

import requests

SCALEDOWN_URL = "https://api.scaledown.xyz/v1/chat/completions"


class ScaleDownError(RuntimeError):
    def __init__(self, message: str, *, category: str, status_code: int | None = None,
                 endpoint: str = SCALEDOWN_URL, duration_ms: int | None = None,
                 error_code: str | None = None, invalid_fields: tuple[str, ...] = ()):
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.endpoint = endpoint
        self.duration_ms = duration_ms
        self.error_code = error_code
        self.invalid_fields = invalid_fields


class ScaleDownConfigurationError(ScaleDownError):
    pass


class ScaleDownTimeoutError(ScaleDownError):
    pass


class ScaleDownResponseError(ScaleDownError):
    pass


class ScaleDownResult(dict):
    def __init__(self, values: dict, duration_ms: int):
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


def extract_pdf(file_bytes: bytes, schema: dict) -> dict:
    api_key = os.getenv("SCALEDOWN_API_KEY")
    if not api_key:
        raise ScaleDownConfigurationError(
            "SCALEDOWN_API_KEY non configurata", category="configuration", duration_ms=0
        )
    payload = {
        "model": "extract",
        "messages": [{"role": "user", "content": "Estrai i dati richiesti senza inventare valori mancanti."}],
        "document": base64.b64encode(file_bytes).decode("ascii"),
        "document_mime_type": "application/pdf",
        "response_format": {"type": "json_schema", "json_schema": {"name": "cte_extraction", "schema": schema}},
    }
    started_at = time.monotonic()
    try:
        response = requests.post(
            SCALEDOWN_URL,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=float(os.getenv("SCALEDOWN_TIMEOUT_SECONDS", "90")),
        )
    except requests.Timeout as error:
        raise ScaleDownTimeoutError(
            "Timeout durante l'estrazione ScaleDown", category="timeout",
            duration_ms=_duration_ms(started_at),
        ) from error
    except requests.RequestException as error:
        raise ScaleDownError(
            "Connessione a ScaleDown fallita", category="network",
            duration_ms=_duration_ms(started_at),
        ) from error
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
        result = decoded["structured_result"]
    except (ValueError, TypeError, KeyError, IndexError) as error:
        raise ScaleDownResponseError(
            "Risposta ScaleDown malformata", category="response_format",
            status_code=response.status_code, duration_ms=_duration_ms(started_at),
        ) from error
    if not isinstance(result, dict):
        raise ScaleDownResponseError(
            "Risultato strutturato ScaleDown mancante", category="response_format",
            status_code=response.status_code, duration_ms=_duration_ms(started_at),
        )
    cte = result.get("cte")
    if not isinstance(cte, dict):
        raise ScaleDownResponseError(
            "Risultato CTE ScaleDown mancante", category="response_format",
            status_code=response.status_code, duration_ms=_duration_ms(started_at),
        )
    return ScaleDownResult(cte, _duration_ms(started_at))
