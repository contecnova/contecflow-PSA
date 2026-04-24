import uuid
from fastapi import APIRouter, Depends, Body
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()

_created_templates: dict = {}


@router.get("/templates", summary="List templates")
def list_templates(current_user: User = Depends(get_current_user)):
    return list(_created_templates.values()) or [
        {"id": "tpl-1", "name": "Template base", "phases": []}
    ]


@router.post("/templates", summary="Create template", status_code=201)
def create_template(payload: dict = Body(...), current_user: User = Depends(get_current_user)):
    tmpl_id = str(uuid.uuid4())
    template = {"id": tmpl_id, **payload}
    _created_templates[tmpl_id] = template
    return template


@router.get("/templates/{template_id}", summary="Get template")
def get_template(template_id: str, current_user: User = Depends(get_current_user)):
    if template_id in _created_templates:
        return _created_templates[template_id]
    return {"id": template_id, "phases": []}
