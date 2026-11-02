from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from estrai_dati_bolletta import estrai_dati_bolletta
import hmac
import os

router = APIRouter()

class BollettaTesto(BaseModel):
    testo: str

@router.post("/analizza-bolletta")
def analizza_bolletta(body: BollettaTesto, x_api_key: str = Header(None)):
    secret_key = os.getenv("API_SECRET_KEY")
    if not secret_key or not x_api_key or not hmac.compare_digest(x_api_key, secret_key):
        raise HTTPException(status_code=401, detail="Chiave API non valida")

    try:
        risultato = estrai_dati_bolletta(body.testo)
        return risultato
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
