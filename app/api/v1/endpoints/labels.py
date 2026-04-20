from fastapi import APIRouter, Depends
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.get("", summary="Listado de etiquetas UI")
def get_labels(current_user: User = Depends(get_current_user)):
    # TODO: Delegar a servicio real
    return {"labels": {}}
