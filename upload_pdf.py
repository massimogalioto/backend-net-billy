#modificato (2025-06-02)
import os
import asyncio
from starlette.concurrency import run_in_threadpool
from cte_pipeline import processa_cte
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from auth_service import CurrentUser, current_user
from plan_service import UsageLimitError, comparison_slot
from fastapi.responses import JSONResponse
from tempfile import NamedTemporaryFile
from estrai_dati_bolletta import estrai_dati_bolletta  # ✅ estrae dati bolletta
from confronto import confronta_offerte
from datetime import date
from pdf2image import convert_from_path  #modificato (2025-06-02)
import pytesseract  #modificato (2025-06-02)
import traceback  # 👈 #nuova modifica (2025-06-04)

def data_oggi_iso():
    return date.today().isoformat()

router = APIRouter()

MAX_CONCURRENT = 2
cte_slots = asyncio.Semaphore(MAX_CONCURRENT)

# 📄 Estrazione testo da CTE usando OCR
@router.post("/upload-cte")
async def upload_cte_pdf(file: UploadFile = File(...), user: CurrentUser = Depends(current_user)):
        
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Il file deve essere un PDF")

    try:
        async with cte_slots:
            dati = await run_in_threadpool(processa_cte, file)

        return {
            "filename": file.filename,
            "output_ai": dati
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante l'elaborazione: {str(e)}")





# 🧾 Estrazione + confronto da bolletta PDF
@router.post("/upload-bolletta")
async def upload_bolletta(file: UploadFile = File(...), user: CurrentUser = Depends(current_user)):
    temp_path = None
    try:
        # The slot checks the quota before OCR/LLM and serializes the tenant quota.
        with comparison_slot(user.tenant_id, user.id) as slot:
            with NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                file.file.seek(0)
                temp_file.write(file.file.read())
                temp_path = temp_file.name

            #modificato (2025-06-02) - OCR SEMPRE ATTIVO
            images = convert_from_path(temp_path)
            testo = ""
            for image in images:
                testo += pytesseract.image_to_string(image, lang='ita')

            os.remove(temp_path)
            temp_path = None

            if not testo.strip():
                raise HTTPException(status_code=422, detail="Errore: OCR non ha rilevato testo")

            dati = estrai_dati_bolletta(testo)
            if "errore" in dati:
                return {
                    "errore": "Estrazione fallita",
                    "dettagli": dati.get("output")
                }

        # ✅ Verifica che tutti i campi necessari siano presenti
            campi_obbligatori = [
                "kwh_totali", "mesi_bolletta", "spesa_vendita_energia", "quota_fissa_vendita",
                "tipo_fornitura", "tipologia_cliente"
            ]
            mancanti = [campo for campo in campi_obbligatori if campo not in dati or dati[campo] is None]

            if mancanti:
                return {
                    "errore": "Campo mancante nella risposta AI",
                    "mancanti": mancanti,
                    "output_ai": dati
                }

            confronto_input = {
                "kwh_totali": dati["kwh_totali"],
                "mesi_bolletta": dati["mesi_bolletta"],
                "spesa_vendita_energia": dati["spesa_vendita_energia"],
                "quota_fissa_vendita": dati["quota_fissa_vendita"], #modifica 05-09-2025
                "tipo_fornitura": dati["tipo_fornitura"],
                "tipologia_cliente": dati["tipologia_cliente"],
                "potenza_kw": dati.get("potenza_kw"),
                "data_riferimento": data_oggi_iso()
            }

            offerte = confronta_offerte(confronto_input, tenant_id=user.tenant_id)
            if offerte:
                slot.record_success(dati.get("tipo_fornitura"))

            return {
                "bolletta": dati,
                "offerte": offerte
            }

    except UsageLimitError as error:
        return JSONResponse(status_code=403, content=error.payload())
    except Exception as e:
        print("❌ Errore interno:", str(e))  # 👈 #nuova modifica (2025-06-04)
        traceback.print_exc()                # 👈 #nuova modifica (2025-06-04)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
