from fastapi import APIRouter, Depends, status, Body
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.get("/templates", summary="List templates")
def list_templates(current_user: User = Depends(get_current_user)):
    return [
        {"id": "tpl-1", "name": "Template base", "documents": ["doc-1"], "roles": ["role-1"], "phases": []}
    ]

@router.post("/templates", summary="Create template")
def create_template(payload: dict = Body(...), current_user: User = Depends(get_current_user)):
    return {"template": {"id": "tpl-1", "documents": ["doc-1"], "roles": ["role-1"], "phases": []}}

@router.get("/templates/{template_id}", summary="Get template")
def get_template(template_id: str, current_user: User = Depends(get_current_user)):
    return {"template": {"id": template_id, "documents": ["doc-1"], "roles": ["role-1"], "phases": []}}

@router.post("/templates/{template_id}/documents", summary="Add document to template")
def add_document_to_template(template_id: str, payload: dict = Body(...), current_user: User = Depends(get_current_user)):
    return {"created": True}

@router.post("/templates/{template_id}/roles", summary="Add role to template")
def add_role_to_template(template_id: str, payload: dict = Body(...), current_user: User = Depends(get_current_user)):
    return {"role_name": payload.get("role_name", "role-1")}

@router.get("/templates/{template_id}/structure", summary="Get full template structure")
def get_full_template_structure(template_id: str, current_user: User = Depends(get_current_user)):
    return {"template": {"id": template_id, "documents": ["doc-1"], "roles": ["role-1"], "phases": []}}
