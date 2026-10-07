from fastapi import APIRouter, HTTPException
from database_service import ConfigurationError, list_cte_offers

router = APIRouter()


@router.get("/cte-offers")
def cte_archive(customer_type: str | None = None, supply_type: str | None = None,
                active_only: bool = True):
    try:
        return {"offers": list_cte_offers(customer_type, supply_type, active_only)}
    except ConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail="Archivio CTE non disponibile") from error
