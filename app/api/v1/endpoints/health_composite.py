from fastapi import APIRouter, status, Depends, HTTPException
from app.api.deps import get_current_user
from app.core.responses import APIResponse
from app.services.customer_health_service import compute_composite_health
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter()


# Barrido final 2026-11: antes un HTTPException/ErrorDeDominio que no fuera
# 400/404/422 (p. ej. un 403) se convertía en 500, y cualquier otra excepción
# devolvía `f"Error interno: {e}"` al cliente. Ahora sólo ValueError es 400; lo
# demás conserva su código o llega al manejador genérico de 500.
def _health(client_id: str, db: Session):
    try:
        return APIResponse.ok(data=compute_composite_health(client_id, db))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/customers/{client_id}/health-composite", status_code=status.HTTP_200_OK)
def get_health_composite(client_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return _health(client_id, db)


@router.get("/clients/{client_id}/health-composite", status_code=status.HTTP_200_OK)
def get_health_composite_clients(client_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return _health(client_id, db)
