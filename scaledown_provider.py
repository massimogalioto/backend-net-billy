"""HTTP client for ScaleDown Extract. It never logs document contents."""
import base64
import json
import os

import requests

SCALEDOWN_URL = "https://api.scaledown.xyz/v1/chat/completions"


class ScaleDownError(RuntimeError):
    pass


class ScaleDownConfigurationError(ScaleDownError):
    pass


class ScaleDownTimeoutError(ScaleDownError):
    pass


class ScaleDownResponseError(ScaleDownError):
    pass


def extract_pdf(file_bytes: bytes, schema: dict) -> dict:
    api_key = os.getenv("SCALEDOWN_API_KEY")
    if not api_key:
        raise ScaleDownConfigurationError("SCALEDOWN_API_KEY non configurata")
    payload = {
        "model": "extract",
        "messages": [{"role": "user", "content": "Estrai i dati richiesti senza inventare valori mancanti."}],
        "document": base64.b64encode(file_bytes).decode("ascii"),
        "document_mime_type": "application/pdf",
        "response_format": {"type": "json_schema", "json_schema": {"name": "cte_extraction", "schema": schema}},
    }
    try:
        response = requests.post(
            SCALEDOWN_URL,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=float(os.getenv("SCALEDOWN_TIMEOUT_SECONDS", "90")),
        )
    except requests.Timeout as error:
        raise ScaleDownTimeoutError("Timeout durante l'estrazione ScaleDown") from error
    except requests.RequestException as error:
        raise ScaleDownError("Connessione a ScaleDown fallita") from error
    if not response.ok:
        raise ScaleDownError(f"ScaleDown ha restituito HTTP {response.status_code}")
    try:
        envelope = response.json()
        content = envelope["choices"][0]["message"]["content"]
        decoded = json.loads(content) if isinstance(content, str) else content
        result = decoded["structured_result"]
    except (ValueError, TypeError, KeyError, IndexError) as error:
        raise ScaleDownResponseError("Risposta ScaleDown malformata") from error
    if not isinstance(result, dict):
        raise ScaleDownResponseError("Risultato strutturato ScaleDown mancante")
    cte = result.get("cte")
    if not isinstance(cte, dict):
        raise ScaleDownResponseError("Risultato CTE ScaleDown mancante")
    return cte
