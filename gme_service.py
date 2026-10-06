"""Small client for the official GME public market-results API."""
import base64
import io
import json
import os
import zipfile
from datetime import date
from typing import Any

import requests


class GmeError(RuntimeError):
    """The GME service could not provide usable market data."""


class GmeConfigurationError(GmeError):
    pass


class GmeMarketClient:
    """Retrieve public GME data without exposing credentials in callers or logs."""

    def __init__(self, *, base_url: str | None = None, username: str | None = None,
                 password: str | None = None, timeout: int | None = None,
                 max_response_bytes: int | None = None, session: Any = requests):
        self.base_url = (base_url or os.getenv(
            "GME_API_BASE_URL", "https://api.mercatoelettrico.org/request"
        )).rstrip("/")
        self.username = (os.getenv("USER_API_GME") or os.getenv("GME_API_USERNAME")
                         if username is None else username)
        self.password = (os.getenv("PWD_API_GME") or os.getenv("GME_API_PASSWORD")
                         if password is None else password)
        self.timeout = timeout if timeout is not None else int(os.getenv("GME_API_TIMEOUT_SECONDS", "30"))
        self.max_response_bytes = (max_response_bytes if max_response_bytes is not None else int(
            os.getenv("GME_API_MAX_RESPONSE_BYTES", "10485760")
        ))
        self.session = session

    def _authenticate(self) -> str:
        if not self.username or not self.password:
            raise GmeConfigurationError("Credenziali GME mancanti")
        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/Auth",
                json={"Login": self.username, "Password": self.password},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            raise GmeError("Timeout durante l'autenticazione GME") from exc
        except requests.RequestException as exc:
            raise GmeError("Errore HTTP durante l'autenticazione GME") from exc
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GmeError("Risposta di autenticazione GME non valida") from exc

        if not isinstance(payload, dict):
            raise GmeError("Risposta di autenticazione GME non valida")
        token = payload.get("token")
        if payload.get("Success") is not True or not isinstance(token, str) or not token:
            raise GmeError("Autenticazione GME fallita")
        return token

    def request_pun_hourly(self, target_date: date) -> list[dict[str, Any]]:
        """Request MGP zonal prices at PT60 and return the decoded JSON rows."""
        token = self._authenticate()
        request_payload = {
            "Platform": "PublicMarketResults",
            "Segment": "MGP",
            "DataName": "ME_ZonalPrices",
            "IntervalStart": target_date.strftime("%Y%m%d"),
            "IntervalEnd": target_date.strftime("%Y%m%d"),
            "Attributes": {"GranularityType": "PT60"},
        }
        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/RequestData",
                headers={"Authorization": f"Bearer {token}"},
                json=request_payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            envelope = response.json()
        except requests.Timeout as exc:
            raise GmeError("Timeout durante la richiesta dati GME") from exc
        except requests.RequestException as exc:
            raise GmeError("Errore HTTP durante la richiesta dati GME") from exc
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GmeError("Risposta GME non valida") from exc

        if not isinstance(envelope, dict):
            raise GmeError("Busta GME non valida")
        if envelope.get("FormatType") != ".json.zip":
            raise GmeError("GME non ha restituito dati JSON compressi")
        encoded = envelope.get("ContentResponse")
        if not isinstance(encoded, str) or not encoded:
            raise GmeError("Dataset GME vuoto")
        if len(encoded) > ((self.max_response_bytes * 4 + 2) // 3 + 4):
            raise GmeError("Risposta GME oltre il limite configurato")
        try:
            zipped = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise GmeError("Contenuto GME base64 non valido") from exc
        if len(zipped) > self.max_response_bytes:
            raise GmeError("Risposta GME oltre il limite configurato")
        return self._decode_json_zip(zipped)

    def _decode_json_zip(self, zipped: bytes) -> list[dict[str, Any]]:
        try:
            with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
                json_members = [item for item in archive.infolist()
                                if not item.is_dir() and item.filename.lower().endswith(".json")]
                if len(json_members) != 1 or json_members[0].file_size > self.max_response_bytes:
                    raise GmeError("Archivio GME non valido o oltre il limite")
                raw = archive.read(json_members[0])
            if len(raw) > self.max_response_bytes:
                raise GmeError("Dataset GME oltre il limite configurato")
            decoded = json.loads(raw.decode("utf-8-sig"))
        except GmeError:
            raise
        except (zipfile.BadZipFile, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GmeError("Archivio JSON GME non valido") from exc
        if not isinstance(decoded, list) or not all(isinstance(row, dict) for row in decoded):
            raise GmeError("Dataset GME non valido")
        return decoded
