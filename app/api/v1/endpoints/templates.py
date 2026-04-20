from fastapi import APIRouter, Depends, Body, status
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.post("/{template_id}/documents", summary="Add document to template", status_code=201)
def add_document(template_id: str, current_user: User = Depends(get_current_user)):
    return {"ok": True, "template_id": template_id, "document_id": "doc-1"}

@router.post("/{template_id}/roles", summary="Add role to template", status_code=201)
def add_role(template_id: str, current_user: User = Depends(get_current_user)):
    return {"ok": True, "template_id": template_id, "role_id": "role-1"}

@router.get("/{template_id}/full", summary="Get full template structure")
def get_full_template(template_id: str, current_user: User = Depends(get_current_user)):
    return {"template": {"id": template_id, "documents": ["doc-1"], "roles": ["role-1"]}}

@router.post("/export", summary="Export project as template", status_code=201)
def export_project_as_template(current_user: User = Depends(get_current_user)):
    return {"ok": True, "template_id": "tpl-1"}
