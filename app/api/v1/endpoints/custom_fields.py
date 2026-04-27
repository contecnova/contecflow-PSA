"""
Contecflow v18 API — Endpoints para:
  1. Campos personalizados por proyecto  GET/POST/PATCH/DELETE custom-fields/{project_id}
  2. Valores de campos por tarea         GET/POST custom-fields/{project_id}/values/{task_id}
  3. Workflows personalizados            GET/POST/PATCH/DELETE workflows/{project_id}
  4. Transiciones de workflow            POST/DELETE workflows/{project_id}/transitions
  5. Ejecutar transición en tarea        POST workflows/{project_id}/tasks/{task_id}/transition
  6. Permisos por proyecto               GET/POST/PATCH/DELETE permissions/{project_id}
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.schemas.custom_fields import CustomFieldIn, FieldValueIn, WorkflowStateIn, TransitionIn, TaskTransitionIn, PermissionIn

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_pm
from app.models.user import User
import app.services.custom_fields_service as _svc

router = APIRouter()


# ══════════════════════════════════════════════════════════════════════════════
# 1. CAMPOS PERSONALIZADOS POR PROYECTO
# ══════════════════════════════════════════════════════════════════════════════



@router.get("/custom-fields/{project_id}", summary="Campos personalizados del proyecto")
def get_project_custom_fields(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return _svc.list_project_custom_fields(project_id, db)


@router.post("/custom-fields/{project_id}", summary="Crear campo personalizado")
def create_project_custom_field(
    project_id: str,
    payload: CustomFieldIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin_or_pm),
):
    return _svc.create_project_custom_field(project_id, payload, db)


@router.patch("/custom-fields/{project_id}/{field_id}", summary="Actualizar campo")
def update_project_custom_field(
    project_id: str, field_id: str,
    payload: CustomFieldIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    return _svc.update_project_custom_field(project_id, field_id, payload, db)


@router.delete("/custom-fields/{project_id}/{field_id}", summary="Eliminar campo")
def delete_project_custom_field(
    project_id: str, field_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    return _svc.delete_project_custom_field(project_id, field_id, db)


# ── Valores de campos por tarea ────────────────────────────────────────────────

@router.get("/custom-fields/{project_id}/values/{task_id}", summary="Valores de campos de una tarea")
def get_task_custom_values(
    project_id: str, task_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return _svc.get_task_custom_values(project_id, task_id, db)




@router.post("/custom-fields/{project_id}/values/{task_id}", summary="Guardar valores de campos")
def save_task_custom_values(
    project_id: str, task_id: str,
    payload: List[FieldValueIn],
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return _svc.save_task_custom_values(project_id, task_id, payload, db)


# ══════════════════════════════════════════════════════════════════════════════
# 2. WORKFLOWS PERSONALIZADOS
# ══════════════════════════════════════════════════════════════════════════════







@router.get("/project-workflows/{project_id}", summary="Workflow del proyecto")
def get_workflow(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return _svc.get_workflow(project_id, db)


@router.post("/project-workflows/{project_id}/states", summary="Crear estado en workflow")
def create_workflow_state(
    project_id: str,
    payload: WorkflowStateIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    return _svc.create_workflow_state(project_id, payload, db)


@router.patch("/project-workflows/{project_id}/states/{state_id}", summary="Actualizar estado")
def update_workflow_state(
    project_id: str, state_id: str,
    payload: WorkflowStateIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    return _svc.update_workflow_state(project_id, state_id, payload, db)


@router.delete("/project-workflows/{project_id}/states/{state_id}", summary="Eliminar estado")
def delete_workflow_state(
    project_id: str, state_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    return _svc.delete_workflow_state(project_id, state_id, db)


@router.post("/project-workflows/{project_id}/transitions", summary="Crear transición")
def create_transition(
    project_id: str,
    payload: TransitionIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    return _svc.create_transition(project_id, payload, db)


@router.delete("/project-workflows/{project_id}/transitions/{transition_id}", summary="Eliminar transición")
def delete_transition(
    project_id: str, transition_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    return _svc.delete_transition(project_id, transition_id, db)


@router.post("/project-workflows/{project_id}/init", summary="Inicializar workflow con estados por defecto")
def init_default_workflow(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    return _svc.init_default_workflow(project_id, db)


@router.post("/project-workflows/{project_id}/tasks/{task_id}/transition", summary="Transicionar tarea")
def transition_task(
    project_id: str, task_id: str,
    payload: TaskTransitionIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return _svc.transition_task(project_id, task_id, payload, current, db)


# ══════════════════════════════════════════════════════════════════════════════
# 3. PERMISOS GRANULARES POR PROYECTO
# ══════════════════════════════════════════════════════════════════════════════



@router.get("/permissions/{project_id}", summary="Permisos del proyecto")
def get_permissions(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return _svc.get_permissions(project_id, db)


@router.post("/permissions/{project_id}", summary="Conceder permiso")
def grant_permission(
    project_id: str,
    payload: PermissionIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin_or_pm),
):
    return _svc.grant_permission(project_id, payload, current, db)


@router.patch("/permissions/{project_id}/{permission_id}", summary="Actualizar permiso")
def update_permission(
    project_id: str, permission_id: str,
    payload: PermissionIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    return _svc.update_permission(project_id, permission_id, payload, db)


@router.delete("/permissions/{project_id}/{permission_id}", summary="Revocar permiso")
def revoke_permission(
    project_id: str, permission_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    return _svc.revoke_permission(project_id, permission_id, db)
