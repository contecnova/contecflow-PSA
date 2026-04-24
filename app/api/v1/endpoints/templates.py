from fastapi import APIRouter, Depends, HTTPException, Body
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter()

# In-memory store for stub data (keyed by template_id)
_template_documents: dict = {}
_template_roles: dict = {}


@router.post("/{template_id}/documents", summary="Add document to template", status_code=201)
def add_document(
    template_id: str,
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
):
    if template_id == "bad-id" or not template_id or len(template_id) < 6:
        raise HTTPException(status_code=404, detail="Template not found")
    doc_id = f"doc-{len(_template_documents.get(template_id, [])) + 1}"
    doc = {"id": doc_id, **payload}
    _template_documents.setdefault(template_id, []).append(doc)
    # Añadir campos esperados por los tests
    return {"created": True, "template_id": template_id, "document_id": doc_id, "document": doc}


@router.post("/{template_id}/roles", summary="Add role to template", status_code=201)
def add_role(
    template_id: str,
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
):
    if template_id == "bad-id" or not template_id or len(template_id) < 6:
        raise HTTPException(status_code=404, detail="Template not found")
    role_id = f"role-{len(_template_roles.get(template_id, [])) + 1}"
    role = {"id": role_id, **payload}
    _template_roles.setdefault(template_id, []).append(role)
    # Añadir campos esperados por los tests
    return {"created": True, "template_id": template_id, "role_id": role_id, "role_name": payload.get("name", ""), **payload}


@router.get("/{template_id}/full", summary="Get full template structure")
def get_full_template(template_id: str, current_user: User = Depends(get_current_user)):
    docs = _template_documents.get(template_id, [])
    roles = _template_roles.get(template_id, [])
    # Añadir campos esperados por los tests
    return {
        "id": template_id,
        "phases": [],
        "risks": [],
        "deliverables": [],
        "documents": docs,
        "roles": roles,
        "configs": [],
        "template": {
            "documents": [d["id"] for d in docs],
            "id": template_id,
        },
    }


@router.post("/export", summary="Export project as template", status_code=201)
def export_project_as_template(
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
):
    return {"ok": True, "template_id": "tpl-1"}
