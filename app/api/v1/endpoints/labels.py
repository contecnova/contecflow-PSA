from fastapi import APIRouter, Depends, HTTPException, status
from app.core.deps import get_current_user
from app.models.user import User
from app.core.codigos_de_error import error_http

router = APIRouter()


@router.get("", summary="Listado de etiquetas UI (no implementado)")
def get_labels(current_user: User = Depends(get_current_user)):
    raise error_http(status.HTTP_501_NOT_IMPLEMENTED, "pagina_no_implementada", detail="Labels endpoint is not implemented yet")
