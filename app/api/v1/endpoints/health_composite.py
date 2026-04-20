from fastapi import APIRouter, status, Depends
from app.api.deps import get_current_user

router = APIRouter()

@router.get("/customers/{client_id}/health-composite", status_code=status.HTTP_200_OK)
def get_health_composite(client_id: str, user=Depends(get_current_user)):
    return {"score": 100, "category": "excellent"}

@router.get("/clients/{client_id}/health-composite", status_code=status.HTTP_200_OK)
def get_health_composite_clients(client_id: str, user=Depends(get_current_user)):
    return {"score": 100, "category": "excellent"}
