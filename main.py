from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from confronto import confronta_offerte
from ai_mesi import chiedi_ai_mesi
from upload_pdf import router as upload_router
from analizza_cte import router as analizza_router
from salva_offerta_endpoint import router as salva_offerta_router
from analizza_bolletta import router as analizza_bolletta_router
from estrai_testo_pdf import router as estrai_testo_pdf_router
import os
from database_service import ConfigurationError, get_offer_pdf
from storage_service import get_pdf

app = FastAPI(
    title="Servizio confronto bollette",
    description="API che confronta offerte luce/gas, calcola mesi da testo e analizza CTE PDF con AI.",
    version="1.0.0"
)

# CORS (in produzione metti il dominio del frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Es: ["https://madonie-front.vercel.app"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers per upload e analisi CTE
app.include_router(upload_router)
app.include_router(analizza_router)
app.include_router(salva_offerta_router)
app.include_router(analizza_bolletta_router)
app.include_router(estrai_testo_pdf_router)

@app.get("/cte-offers/{offer_id}/pdf")
def cte_pdf(offer_id: str):
    # TEMPORARY TEST MODE - authentication will replace DEFAULT_TENANT_ID
    try:
        offer = get_offer_pdf(offer_id)
        if not offer or not offer["pdf_object_key"]:
            raise HTTPException(status_code=404, detail="PDF CTE non trovato")
        content = get_pdf(offer["pdf_object_key"])
        filename = (offer["pdf_filename"] or "cte.pdf").replace('"', "")
        return Response(content=content, media_type=offer["pdf_content_type"] or "application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{filename}"'})
    except HTTPException:
        raise
    except ConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail="Recupero PDF dal Bucket fallito") from error

# 📦 Modelli dati
class BollettaInput(BaseModel):
    kwh_totali: float
    mesi_bolletta: int
    spesa_materia_energia: float
    quota_fissa_vendita: float #modifica 05-09-2025
    tipo_fornitura: str  # "Luce" o "Gas"
    tipologia_cliente: str  # "Residenziale" o "Business"
    data_riferimento: str  # formato "YYYY-MM-DD"

class PeriodoRequest(BaseModel):
    periodo: str

# 🔐 Endpoint confronto con chiave API
@app.post("/confronta")
def confronta_bolletta(bolletta: BollettaInput, x_api_key: str = Header(None)):
    secret_key = os.getenv("API_SECRET_KEY")
    if secret_key and x_api_key != secret_key:
        raise HTTPException(status_code=401, detail="Chiave API non valida")

    try:
        risultato = confronta_offerte(bolletta.dict()) #modifica 05-09-2025
        return {"offerte": risultato}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 🧠 Endpoint AI per calcolo mesi
@app.post("/calcola-mesi", summary="Calcola i mesi da un intervallo testuale")
def calcola_mesi(body: PeriodoRequest, x_api_key: str = Header(None)):
    secret_key = os.getenv("API_SECRET_KEY")
    if secret_key and x_api_key != secret_key:
        raise HTTPException(status_code=401, detail="Chiave API non valida")

    mesi = chiedi_ai_mesi(body.periodo)
    if mesi is None:
        return {"error": "Impossibile determinare il numero di mesi"}
    return {"mesi": mesi}
