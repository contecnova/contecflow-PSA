from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
import uuid

from app.db.session import get_db
from app.core.deps import get_current_user
from app.core.responses import APIResponse
from app.models.user import User
from app.models.advanced_config import ProjectTemplate
from app.models.marketplace import TemplateDocument, TemplateRole
from app.services.advanced_config_service import get_full_template, export_project_as_template

router = APIRouter()


def _get_template_or_404(template_id: str, db: Session) -> ProjectTemplate:
    tmpl = db.query(ProjectTemplate).filter(ProjectTemplate.id == template_id).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return tmpl


@router.post("/{template_id}/documents", summary="Add document to template", status_code=201)
def add_document(
    template_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_template_or_404(template_id, db)
    doc = TemplateDocument(
        id=str(uuid.uuid4()),
        template_id=template_id,
        name=payload.get("name", "Document"),
        document_type=payload.get("document_type", "spec"),
        description=payload.get("description"),
        url=payload.get("url"),
        is_required=bool(payload.get("is_required", False)),
        due_week_offset=payload.get("due_week_offset"),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return APIResponse.ok(data={
        "created": True,
        "template_id": template_id,
        "document_id": doc.id,
        "document": {
            "id": doc.id,
            "name": doc.name,
            "document_type": doc.document_type,
            "description": doc.description,
            "url": doc.url,
            "is_required": doc.is_required,
            "due_week_offset": doc.due_week_offset,
        },
    })


@router.post("/{template_id}/roles", summary="Add role to template", status_code=201)
def add_role(
    template_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_template_or_404(template_id, db)
    role_name = payload.get("role_name") or payload.get("name", "Role")
    role = TemplateRole(
        id=str(uuid.uuid4()),
        template_id=template_id,
        role_name=role_name,
        skill_required=payload.get("skill_required"),
        min_seniority=payload.get("min_seniority"),
        estimated_hours=payload.get("estimated_hours"),
        is_mandatory=bool(payload.get("is_mandatory", True)),
        notes=payload.get("notes"),
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return APIResponse.ok(data={
        "created": True,
        "template_id": template_id,
        "role_id": role.id,
        "role_name": role.role_name,
        "skill_required": role.skill_required,
        "min_seniority": role.min_seniority,
        "estimated_hours": role.estimated_hours,
        "is_mandatory": role.is_mandatory,
        "notes": role.notes,
    })


@router.get("/{template_id}/full", summary="Get full template structure")
def get_full_template_endpoint(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=get_full_template(template_id, db))


@router.post("/export", summary="Export project as template", status_code=201)
def export_project_as_template_endpoint(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=export_project_as_template(
        project_id=payload.get("project_id", ""),
        name=payload.get("name"),
        description=payload.get("description"),
        user_id=current_user.id,
        db=db,
    ))
