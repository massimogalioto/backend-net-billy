from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from auth_service import CurrentUser, current_user
from estrai_dati_cte import estrai_dati_offerta_cte

router = APIRouter()

class CTETextRequest(BaseModel):
    testo: str

@router.post("/analizza-cte")
def analizza_cte(data: CTETextRequest, user: CurrentUser = Depends(current_user)):
    if not data.testo.strip():
        raise HTTPException(status_code=400, detail="Testo CTE mancante")

    risultato = estrai_dati_offerta_cte(data.testo)
    return risultato
