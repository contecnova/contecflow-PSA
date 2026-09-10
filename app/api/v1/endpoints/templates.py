"""Plantillas de proyecto: documentos, roles y exportacion.

Auditoria 2026-08 (hallazgo 22). Este fichero tenia su propio
`_get_template_or_404` que buscaba la plantilla por id **sin ningun filtro de
organizacion**, y de el colgaban las dos altas: anadir un documento o un rol a
la plantilla de otro cliente era una escritura cruzada. Y las dos funciones de
servicio que usa —`get_full_template` y `export_project_as_template`— **no
recibian al sujeto**, asi que no podian comprobar nada aunque quisieran.

Al arreglarlo salio un defecto que no buscaba: la exportacion escribia la
probabilidad de un riesgo con `str()` sobre un enum, lo que da
`"RiskProbability.medium"` en una columna `VARCHAR(20)`. Ver el docstring de
`_valor_de_enum` en `services/advanced_config_service.py`.
"""
from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user
from app.core.responses import APIResponse
from app.models.user import User
from app.services.advanced_config_service import (
    agregar_documento_a_plantilla,
    agregar_rol_a_plantilla,
    export_project_as_template,
    get_full_template,
)

router = APIRouter()


@router.post("/{template_id}/documents", summary="Add document to template", status_code=201)
def add_document(
    template_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = agregar_documento_a_plantilla(db, current_user, template_id, payload)
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
    role = agregar_rol_a_plantilla(db, current_user, template_id, payload)
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
    return APIResponse.ok(
        data=get_full_template(template_id, db, current_user))


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
        current_user=current_user,
    ))
