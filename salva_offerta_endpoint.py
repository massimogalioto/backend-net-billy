from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field, ValidationError, validator
from database_service import ConfigurationError, find_duplicate_cte_offer, insert_offer
from fastapi.responses import JSONResponse
from storage_service import delete_pdf, upload_cte_pdf
import logging
import base64
import binascii

logger = logging.getLogger("uvicorn.error")

router = APIRouter()

class CtePdfInput(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1, max_length=35_000_000)

class OffertaInput(BaseModel):
    fornitore: str
    nome_offerta: str
    tipologia_cliente: str
    tariffa: str
    prezzo_kwh: float | None = None
    spread: float | None = None
    costo_fisso: float | None = None
    validita: str | None = None
    valid_until: str | None = None
    fonte_cte: str | None = None
    vincoli: str | None = None
    notes: str | None = None
    tipo_fornitura: str
    min_power_kw: float | None = Field(default=None, ge=0)
    max_power_kw: float | None = Field(default=None, ge=0)
    cte_pdf: CtePdfInput | None = None
    cte_retry_token: str | None = Field(default=None, max_length=200)

    @validator("tipo_fornitura", pre=True)
    def normalize_supply_type(cls, value):
        normalized = str(value).strip().lower() if value is not None else ""
        if normalized == "luce":
            return "Luce"
        if normalized == "gas":
            return "Gas"
        raise ValueError("Campo obbligatorio o non riconosciuto")


def _validation_error(payload: dict, error: ValidationError):
    errors = []
    for item in error.errors():
        field = str(item["loc"][-1])
        errors.append({"field": field, "message": "Campo obbligatorio o non riconosciuto"})
    extracted_data = {key: value for key, value in payload.items()
                      if key not in {"cte_pdf", "cte_retry_token", "tenant_id"}}
    return JSONResponse(status_code=422, content={
        "status": "validation_error",
        "message": "Tipo fornitura non riconosciuto" if any(
            item["field"] == "tipo_fornitura" for item in errors
        ) else "Dati CTE non validi",
        "errors": errors,
        "extracted_data": extracted_data,
    })


def _validated_offer(payload: dict | OffertaInput):
    if isinstance(payload, OffertaInput):
        return payload
    try:
        return OffertaInput(**payload)
    except ValidationError as error:
        return _validation_error(payload, error)

@router.post("/salva-offerta", summary="Salva un'offerta CTE in PostgreSQL")
def salva(payload: dict, x_api_key: str = Header(None)):
    from os import getenv
    if x_api_key != getenv("API_SECRET_KEY"):
        raise HTTPException(status_code=401, detail="Chiave API non valida")

    offerta = _validated_offer(payload)
    if isinstance(offerta, JSONResponse):
        return offerta

    return _salva_validata(offerta)


@router.post("/salva-offerta-manuale", summary="Salva una CTE corretta manualmente senza rieseguire l'AI")
def salva_manuale(payload: dict, x_api_key: str = Header(None)):
    from os import getenv
    if x_api_key != getenv("API_SECRET_KEY"):
        raise HTTPException(status_code=401, detail="Chiave API non valida")

    offerta = _validated_offer(payload)
    if isinstance(offerta, JSONResponse):
        return offerta
    return _salva_validata(offerta)


def _salva_validata(offerta: OffertaInput):

    dati = offerta.dict(exclude={"cte_pdf", "cte_retry_token"})
    if offerta.cte_retry_token:
        raise HTTPException(status_code=422, detail="Retry CTE non supportato: ripeti il salvataggio del PDF originale")
    try:
        existing_offer_id = find_duplicate_cte_offer(dati)
    except ConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        logger.exception("[CTE] PostgreSQL controllo duplicati fallito")
        raise HTTPException(status_code=500, detail="Controllo duplicati CTE fallito") from error
    if existing_offer_id:
        return JSONResponse(status_code=409, content={
            "detail": "CTE già presente", "existing_offer_id": existing_offer_id,
        })
    pdf_metadata = None
    if offerta.cte_pdf:
        filename = offerta.cte_pdf.filename
        if not filename.lower().endswith(".pdf") or any(character in filename for character in "/\\\r\n"):
            raise HTTPException(status_code=422, detail="Nome PDF CTE non valido")
        try:
            pdf = base64.b64decode(offerta.cte_pdf.content_base64, validate=True)
        except (ValueError, binascii.Error):
            raise HTTPException(status_code=422, detail="PDF CTE Base64 non valido")
        if not pdf or b"%PDF-" not in pdf[:1024]:
            raise HTTPException(status_code=422, detail="L'allegato CTE deve essere un PDF originale valido")
        try:
            pdf_metadata = upload_cte_pdf(pdf, filename)
        except ConfigurationError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except Exception as error:
            logger.exception("[CTE] Bucket upload fallito: %s", filename)
            raise HTTPException(status_code=502, detail="Caricamento PDF nel Bucket fallito") from error
    try:
        offer_id = insert_offer(dati, pdf_metadata)
    except ConfigurationError as error:
        if pdf_metadata:
            delete_pdf(pdf_metadata["object_key"])
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        if pdf_metadata:
            try:
                delete_pdf(pdf_metadata["object_key"])
            except Exception:
                logger.exception("[CTE] Cleanup Bucket fallito dopo errore PostgreSQL")
        logger.exception("[CTE] PostgreSQL salvataggio fallito: %s", offerta.fonte_cte)
        raise HTTPException(status_code=500, detail="Salvataggio offerta PostgreSQL fallito") from error
    logger.info("[CTE] PostgreSQL salvato: %s - %s", offerta.fonte_cte, offer_id)
    return {"successo": True, "id": offer_id}

