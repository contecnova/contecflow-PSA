from fastapi import APIRouter, Depends, HTTPException, status
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter()


@router.get("/status", summary="Estado de colaboración en tiempo real (no implementado)")
def get_collab_status(current_user: User = Depends(get_current_user)):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Collaboration status endpoint is not implemented yet",
    )
