from fastapi import APIRouter, status, Depends, HTTPException
from app.api.deps import get_current_user
from app.services.customer_health_service import compute_composite_health
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter()

@router.get("/customers/{client_id}/health-composite", status_code=status.HTTP_200_OK)
def get_health_composite(client_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    try:
        return compute_composite_health(client_id, db)
    except HTTPException as e:
        if e.status_code == 404:
            raise
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/clients/{client_id}/health-composite", status_code=status.HTTP_200_OK)
def get_health_composite_clients(client_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    try:
        return compute_composite_health(client_id, db)
    except HTTPException as e:
        if e.status_code == 404:
            raise
        raise HTTPException(status_code=500, detail=str(e))
