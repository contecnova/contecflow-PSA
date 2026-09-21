from fastapi import APIRouter, Depends, Body
from app.api.deps import get_current_user
from app.core.responses import APIResponse
from app.models.user import User
from app.core.deps import require_internal_user

router = APIRouter()

@router.patch("/documents/{doc_id}/edit", summary="Edit document")
def edit_document(doc_id: str, payload: dict = Body(...), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: los documentos ya tienen permisos por documento; el rol solo excluye al externo
):
    return APIResponse.ok(data={"ok": True, "doc_id": doc_id})
