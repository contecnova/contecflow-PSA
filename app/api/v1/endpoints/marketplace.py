from fastapi import APIRouter, Depends
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.get("/catalog", summary="Catálogo de integraciones disponibles")
def get_marketplace_catalog(current_user: User = Depends(get_current_user)):
    # TODO: Delegar a servicio real
    return {"integrations": []}
