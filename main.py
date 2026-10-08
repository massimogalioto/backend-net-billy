from fastapi import Depends, FastAPI, HTTPException
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
from market_prices_endpoint import router as market_prices_router
from cte_archive_endpoint import router as cte_archive_router
from auth_endpoint import router as auth_router
from auth_service import CurrentUser, current_user
from account_endpoint import router as account_router
from plan_service import UsageLimitError, comparison_slot

app = FastAPI(
    title="Servizio confronto bollette",
    description="API che confronta offerte luce/gas, calcola mesi da testo e analizza CTE PDF con AI.",
    version="1.0.0"
)

# CORS (in produzione metti il dominio del frontend)
allowed_origins = [origin.strip() for origin in os.getenv("AUTH_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
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
app.include_router(market_prices_router)
app.include_router(cte_archive_router)
app.include_router(auth_router)
app.include_router(account_router)

@app.get("/cte-offers/{offer_id}/pdf")
def cte_pdf(offer_id: str, user: CurrentUser = Depends(current_user)):
    try:
        offer = get_offer_pdf(offer_id, tenant_id=user.tenant_id)
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
    spesa_vendita_energia: float
    quota_fissa_vendita: float #modifica 05-09-2025
    tipo_fornitura: str  # "Luce" o "Gas"
    tipologia_cliente: str  # "Residenziale" o "Business"
    data_riferimento: str  # formato "YYYY-MM-DD"

class PeriodoRequest(BaseModel):
    periodo: str

# 🔐 Endpoint confronto con chiave API
@app.post("/confronta")
def confronta_bolletta(bolletta: BollettaInput, user: CurrentUser = Depends(current_user)):
    try:
        with comparison_slot(user.tenant_id, user.id) as slot:
            risultato = confronta_offerte(bolletta.dict(), tenant_id=user.tenant_id) #modifica 05-09-2025
            if risultato:
                slot.record_success(bolletta.tipo_fornitura)
        return {"offerte": risultato}
    except UsageLimitError as error:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content=error.payload())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 🧠 Endpoint AI per calcolo mesi
@app.post("/calcola-mesi", summary="Calcola i mesi da un intervallo testuale")
def calcola_mesi(body: PeriodoRequest, user: CurrentUser = Depends(current_user)):
    mesi = chiedi_ai_mesi(body.periodo)
    if mesi is None:
        return {"error": "Impossibile determinare il numero di mesi"}
    return {"mesi": mesi}
