"""Plantilla desde un proyecto (ruta histórica).

Rev. 173: esta ruta contestaba siempre `{"ok": True, "template_id": "tpl-123"}`
sin crear nada. Ahora crea la plantilla de verdad con el servicio único
(`plantillas_de_proyecto.crear_desde_proyecto`), igual que
`POST /templates/from-project/{project_id}`.
"""
from typing import Optional

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_admin_or_pm
from app.core.responses import APIResponse
from app.models.user import User
from app.services.plantillas_de_proyecto import crear_desde_proyecto

router = APIRouter()


@router.post("/projects/{project_id}/export-template", summary="Export project as template")
def export_project_template(
    project_id: str,
    name: Optional[str] = Body(None, embed=True),
    description: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin_or_pm),  # auditoria 2026-09: dominio: estructura de proyecto
):
    return APIResponse.ok(data={"ok": True, **crear_desde_proyecto(db, current_user, project_id, name, description)})
