from fastapi import APIRouter, Depends, Body
from app.api.deps import get_current_user
from app.core.responses import APIResponse
from app.models.user import User

router = APIRouter()

@router.patch("/documents/{doc_id}/edit", summary="Edit document")
def edit_document(doc_id: str, payload: dict = Body(...), current_user: User = Depends(get_current_user)):
    return APIResponse.ok(data={"ok": True, "doc_id": doc_id})
