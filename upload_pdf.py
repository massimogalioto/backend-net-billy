import asyncio
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from auth_service import CurrentUser, current_user
from bill_document import BillDocumentError, prepare_bill_pdf
from bolletta_extraction import extract_bolletta
from confronto import confronta_offerte
from cte_pipeline import processa_cte
from plan_service import UsageLimitError, comparison_slot
from scaledown_provider import (
    ScaleDownConfigurationError,
    ScaleDownError,
    ScaleDownTimeoutError,
    emit_error_diagnostic,
)


router = APIRouter()
MAX_CONCURRENT = 2
cte_slots = asyncio.Semaphore(MAX_CONCURRENT)


def data_oggi_iso():
    return date.today().isoformat()


@router.post("/upload-cte")
async def upload_cte_pdf(file: UploadFile = File(...), user: CurrentUser = Depends(current_user)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Il file deve essere un PDF")
    try:
        async with cte_slots:
            dati = await run_in_threadpool(processa_cte, file)
        return {"filename": file.filename, "output_ai": dati}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Errore durante l'elaborazione: {str(error)}") from error


@router.post("/upload-bolletta")
async def upload_bolletta(
    file: UploadFile | None = File(None),
    user: CurrentUser = Depends(current_user),
    images: list[UploadFile] | None = File(None),
):
    try:
        with comparison_slot(user.tenant_id, user.id) as slot:
            image_files = images if isinstance(images, list) else None
            file_bytes = await run_in_threadpool(prepare_bill_pdf, file, image_files)
            dati = await run_in_threadpool(extract_bolletta, file_bytes)
            required = (
                "kwh_totali", "mesi_bolletta", "spesa_vendita_energia", "quota_fissa_vendita",
                "tipo_fornitura", "tipologia_cliente",
            )
            missing = [field for field in required if dati.get(field) is None]
            if missing:
                return {
                    "errore": "Campo mancante nella risposta AI",
                    "mancanti": missing,
                    "output_ai": dati,
                }
            comparison_input = {
                "kwh_totali": dati["kwh_totali"],
                "mesi_bolletta": dati["mesi_bolletta"],
                "spesa_vendita_energia": dati["spesa_vendita_energia"],
                "quota_fissa_vendita": dati["quota_fissa_vendita"],
                "tipo_fornitura": dati["tipo_fornitura"],
                "tipologia_cliente": dati["tipologia_cliente"],
                "potenza_kw": dati.get("potenza_kw"),
                "data_riferimento": data_oggi_iso(),
            }
            offerte = confronta_offerte(comparison_input, tenant_id=user.tenant_id)
            if offerte:
                slot.record_success(dati.get("tipo_fornitura"))
            return {"bolletta": dati, "offerte": offerte}
    except UsageLimitError as error:
        return JSONResponse(status_code=403, content=error.payload())
    except BillDocumentError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except ScaleDownConfigurationError as error:
        emit_error_diagnostic(error)
        raise HTTPException(status_code=503, detail="Servizio ScaleDown non configurato") from error
    except ScaleDownTimeoutError as error:
        emit_error_diagnostic(error)
        raise HTTPException(status_code=504, detail="Timeout durante l'estrazione del PDF") from error
    except ScaleDownError as error:
        emit_error_diagnostic(error)
        raise HTTPException(status_code=502, detail="Estrazione ScaleDown fallita") from error
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail="Errore durante l'elaborazione della bolletta") from error
