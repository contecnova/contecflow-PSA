from fastapi import APIRouter, Depends
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.get("/status", summary="Estado de colaboración en tiempo real")
def get_collab_status(current_user: User = Depends(get_current_user)):
    # Servicio real pendiente de implementación
    return {"status": "ok", "active_sessions": 0}
