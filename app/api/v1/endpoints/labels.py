from fastapi import APIRouter, Depends, HTTPException, status
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter()


@router.get("", summary="Listado de etiquetas UI (no implementado)")
def get_labels(current_user: User = Depends(get_current_user)):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Labels endpoint is not implemented yet",
    )
