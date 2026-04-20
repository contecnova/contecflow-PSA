from fastapi import APIRouter, Depends
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.get("", summary="Traducciones de la UI")
def get_translations(current_user: User = Depends(get_current_user)):
    # TODO: Delegar a servicio real
    return {"translations": {}}
