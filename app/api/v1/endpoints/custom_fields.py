"""
Clarive v18 API — Endpoints para:
  1. Campos personalizados por proyecto  GET/POST/PATCH/DELETE custom-fields/{project_id}
  2. Valores de campos por tarea         GET/POST custom-fields/{project_id}/values/{task_id}
  3. Workflows personalizados            GET/POST/PATCH/DELETE workflows/{project_id}
  4. Transiciones de workflow            POST/DELETE workflows/{project_id}/transitions
  5. Ejecutar transición en tarea        POST workflows/{project_id}/tasks/{task_id}/transition
  6. Permisos por proyecto               GET/POST/PATCH/DELETE permissions/{project_id}
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import Optional, List
from pydantic import BaseModel
import json

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_pm
from app.models.user import User
from app.models.project import Project
from app.models.task import Task
from app.models.custom_fields import WorkflowState, WorkflowTransition, ProjectCustomField, ProjectCustomFieldValue
from app.models.enterprise import ProjectPermission, ProjectPermissionLevel

router = APIRouter()


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _project_or_404(project_id: str, db: Session) -> Project:
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, f"Proyecto {project_id} no encontrado")
    return p


def _serialize_field(f: ProjectCustomField) -> dict:
    return {
        "id": f.id, "project_id": f.project_id, "name": f.name,
        "field_key": f.field_key, "field_type": f.field_type,
        "options": json.loads(f.options) if f.options else [],
        "is_required": f.is_required, "show_in_list": f.show_in_list,
        "sort_order": f.sort_order, "created_at": f.created_at.isoformat() if f.created_at else None,
    }


def _serialize_state(s: WorkflowState) -> dict:
    return {
        "id": s.id, "project_id": s.project_id, "name": s.name,
        "value": s.value, "color": s.color, "icon": s.icon,
        "is_initial": s.is_initial, "is_final": s.is_final, "sort_order": s.sort_order,
        "transitions_from": [
            {"id": t.id, "to_state_id": t.to_state_id, "to_state_name": t.to_state.name if t.to_state else None,
             "label": t.label, "required_role": t.required_role, "requires_comment": t.requires_comment}
            for t in (s.transitions_from or [])
        ],
    }


def _serialize_perm(p: ProjectPermission) -> dict:
    return {
        "id": p.id, "project_id": p.project_id, "user_id": p.user_id,
        "level": p.level.value if p.level else None,
        "can_see_financials": p.can_see_financials,
        "can_see_rates": p.can_see_rates,
        "can_export": p.can_export,
        "granted_at": p.granted_at.isoformat() if p.granted_at else None,
        "user": {"id": p.user.id, "full_name": p.user.full_name, "role": p.user.role.value,
                 "job_title": p.user.job_title, "department": p.user.department} if p.user else None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 1. CAMPOS PERSONALIZADOS POR PROYECTO
# ══════════════════════════════════════════════════════════════════════════════

class CustomFieldIn(BaseModel):
    name: str
    field_key: str
    field_type: str  # text|number|date|select|url|user|boolean
    options: Optional[List[str]] = []
    is_required: bool = False
    show_in_list: bool = True
    sort_order: int = 0


@router.get("/custom-fields/{project_id}", summary="Campos personalizados del proyecto")
def get_project_custom_fields(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _project_or_404(project_id, db)
    fields = (db.query(ProjectCustomField)
              .filter(ProjectCustomField.project_id == project_id)
              .order_by(ProjectCustomField.sort_order)
              .all())
    return [_serialize_field(f) for f in fields]


@router.post("/custom-fields/{project_id}", summary="Crear campo personalizado")
def create_project_custom_field(
    project_id: str,
    payload: CustomFieldIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin_or_pm),
):
    _project_or_404(project_id, db)
    existing = db.query(ProjectCustomField).filter(
        ProjectCustomField.project_id == project_id,
        ProjectCustomField.field_key == payload.field_key,
    ).first()
    if existing:
        raise HTTPException(400, f"Ya existe un campo con clave '{payload.field_key}' en este proyecto")
    f = ProjectCustomField(
        project_id=project_id,
        name=payload.name, field_key=payload.field_key, field_type=payload.field_type,
        options=json.dumps(payload.options) if payload.options else None,
        is_required=payload.is_required, show_in_list=payload.show_in_list, sort_order=payload.sort_order,
    )
    db.add(f); db.commit(); db.refresh(f)
    return _serialize_field(f)


@router.patch("/custom-fields/{project_id}/{field_id}", summary="Actualizar campo")
def update_project_custom_field(
    project_id: str, field_id: str,
    payload: CustomFieldIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    f = db.query(ProjectCustomField).filter(
        ProjectCustomField.id == field_id, ProjectCustomField.project_id == project_id
    ).first()
    if not f:
        raise HTTPException(404, "Campo no encontrado")
    for k, v in payload.model_dump(exclude_unset=True).items():
        if k == "options":
            f.options = json.dumps(v) if v else None
        else:
            setattr(f, k, v)
    db.commit(); db.refresh(f)
    return _serialize_field(f)


@router.delete("/custom-fields/{project_id}/{field_id}", summary="Eliminar campo")
def delete_project_custom_field(
    project_id: str, field_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    f = db.query(ProjectCustomField).filter(
        ProjectCustomField.id == field_id, ProjectCustomField.project_id == project_id
    ).first()
    if not f:
        raise HTTPException(404, "Campo no encontrado")
    db.delete(f); db.commit()
    return {"deleted": True}


# ── Valores de campos por tarea ────────────────────────────────────────────────

@router.get("/custom-fields/{project_id}/values/{task_id}", summary="Valores de campos de una tarea")
def get_task_custom_values(
    project_id: str, task_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    values = (db.query(ProjectCustomFieldValue)
              .options(joinedload(ProjectCustomFieldValue.field))
              .filter(ProjectCustomFieldValue.task_id == task_id)
              .all())
    return [
        {"field_id": v.field_id, "field_key": v.field.field_key, "field_name": v.field.name,
         "field_type": v.field.field_type, "value": v.value}
        for v in values
    ]


class FieldValueIn(BaseModel):
    field_id: str
    value: Optional[str] = None


@router.post("/custom-fields/{project_id}/values/{task_id}", summary="Guardar valores de campos")
def save_task_custom_values(
    project_id: str, task_id: str,
    payload: List[FieldValueIn],
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    for item in payload:
        existing = db.query(ProjectCustomFieldValue).filter(
            ProjectCustomFieldValue.field_id == item.field_id,
            ProjectCustomFieldValue.task_id == task_id,
        ).first()
        if existing:
            existing.value = item.value
        else:
            db.add(ProjectCustomFieldValue(field_id=item.field_id, task_id=task_id, value=item.value))
    db.commit()
    return {"saved": len(payload)}


# ══════════════════════════════════════════════════════════════════════════════
# 2. WORKFLOWS PERSONALIZADOS
# ══════════════════════════════════════════════════════════════════════════════

class WorkflowStateIn(BaseModel):
    name: str
    value: str
    color: str = "#7a8aaa"
    icon: Optional[str] = None
    is_initial: bool = False
    is_final: bool = False
    sort_order: int = 0


class TransitionIn(BaseModel):
    from_state_id: str
    to_state_id: str
    label: Optional[str] = None
    required_role: Optional[str] = None
    requires_comment: bool = False


class TaskTransitionIn(BaseModel):
    to_state_id: str
    comment: Optional[str] = None


@router.get("/project-workflows/{project_id}", summary="Workflow del proyecto")
def get_workflow(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _project_or_404(project_id, db)
    states = (db.query(WorkflowState)
              .options(joinedload(WorkflowState.transitions_from).joinedload(WorkflowTransition.to_state))
              .filter(WorkflowState.project_id == project_id)
              .order_by(WorkflowState.sort_order)
              .all())
    return {"project_id": project_id, "states": [_serialize_state(s) for s in states]}


@router.post("/project-workflows/{project_id}/states", summary="Crear estado en workflow")
def create_workflow_state(
    project_id: str,
    payload: WorkflowStateIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    _project_or_404(project_id, db)
    existing = db.query(WorkflowState).filter(
        WorkflowState.project_id == project_id, WorkflowState.value == payload.value
    ).first()
    if existing:
        raise HTTPException(400, f"Ya existe un estado con valor '{payload.value}'")
    s = WorkflowState(project_id=project_id, **payload.model_dump())
    db.add(s); db.commit(); db.refresh(s)
    return _serialize_state(s)


@router.patch("/project-workflows/{project_id}/states/{state_id}", summary="Actualizar estado")
def update_workflow_state(
    project_id: str, state_id: str,
    payload: WorkflowStateIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    s = db.query(WorkflowState).filter(
        WorkflowState.id == state_id, WorkflowState.project_id == project_id
    ).first()
    if not s:
        raise HTTPException(404, "Estado no encontrado")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit(); db.refresh(s)
    return _serialize_state(s)


@router.delete("/project-workflows/{project_id}/states/{state_id}", summary="Eliminar estado")
def delete_workflow_state(
    project_id: str, state_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    s = db.query(WorkflowState).filter(
        WorkflowState.id == state_id, WorkflowState.project_id == project_id
    ).first()
    if not s:
        raise HTTPException(404, "Estado no encontrado")
    in_use = db.query(Task).filter(Task.status == s.value).count()
    if in_use > 0:
        raise HTTPException(400, f"No se puede eliminar: {in_use} tareas usan este estado. Reasígnalas primero.")
    db.delete(s); db.commit()
    return {"deleted": True}


@router.post("/project-workflows/{project_id}/transitions", summary="Crear transición")
def create_transition(
    project_id: str,
    payload: TransitionIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    for sid in [payload.from_state_id, payload.to_state_id]:
        s = db.query(WorkflowState).filter(WorkflowState.id == sid, WorkflowState.project_id == project_id).first()
        if not s:
            raise HTTPException(404, f"Estado {sid} no encontrado en este proyecto")
    t = WorkflowTransition(project_id=project_id, **payload.model_dump())
    db.add(t); db.commit(); db.refresh(t)
    return {"id": t.id, "from_state_id": t.from_state_id, "to_state_id": t.to_state_id,
            "label": t.label, "required_role": t.required_role, "requires_comment": t.requires_comment}


@router.delete("/project-workflows/{project_id}/transitions/{transition_id}", summary="Eliminar transición")
def delete_transition(
    project_id: str, transition_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    t = db.query(WorkflowTransition).filter(
        WorkflowTransition.id == transition_id, WorkflowTransition.project_id == project_id
    ).first()
    if not t:
        raise HTTPException(404, "Transición no encontrada")
    db.delete(t); db.commit()
    return {"deleted": True}


@router.post("/project-workflows/{project_id}/init", summary="Inicializar workflow con estados por defecto")
def init_default_workflow(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    """Crea un workflow estándar Scrum con 5 estados y sus transiciones."""
    _project_or_404(project_id, db)
    existing = db.query(WorkflowState).filter(WorkflowState.project_id == project_id).count()
    if existing > 0:
        raise HTTPException(400, "Este proyecto ya tiene un workflow definido")

    defaults = [
        ("Pendiente",     "todo",        "#7a8aaa", "⭕", True,  False, 0),
        ("En progreso",   "in_progress", "#00d4ff", "🔵", False, False, 1),
        ("En revisión",   "in_review",   "#ffb800", "🟡", False, False, 2),
        ("Completado",    "done",        "#00e5a0", "✅", False, True,  3),
        ("Bloqueado",     "blocked",     "#ff4757", "🔴", False, False, 4),
    ]
    states = {}
    for name, value, color, icon, is_initial, is_final, order in defaults:
        s = WorkflowState(project_id=project_id, name=name, value=value, color=color,
                          icon=icon, is_initial=is_initial, is_final=is_final, sort_order=order)
        db.add(s); db.flush(); states[value] = s

    transitions = [
        ("todo",        "in_progress", "Iniciar",        None,    False),
        ("in_progress", "in_review",   "Enviar a revisión", None, False),
        ("in_progress", "blocked",     "Marcar bloqueado", None,  True),
        ("in_review",   "done",        "Aprobar",         "pm",   True),
        ("in_review",   "in_progress", "Rechazar",        "pm",   True),
        ("blocked",     "in_progress", "Desbloquear",     None,   False),
        ("todo",        "blocked",     "Bloquear",        None,   False),
    ]
    for from_v, to_v, label, role, req_comment in transitions:
        db.add(WorkflowTransition(
            project_id=project_id,
            from_state_id=states[from_v].id, to_state_id=states[to_v].id,
            label=label, required_role=role, requires_comment=req_comment,
        ))
    db.commit()
    return {"initialized": True, "states": len(defaults), "transitions": len(transitions)}


@router.post("/project-workflows/{project_id}/tasks/{task_id}/transition", summary="Transicionar tarea")
def transition_task(
    project_id: str, task_id: str,
    payload: TaskTransitionIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    task = db.query(Task).filter(Task.id == task_id, Task.project_id == project_id).first()
    if not task:
        raise HTTPException(404, "Tarea no encontrada")
    to_state = db.query(WorkflowState).filter(
        WorkflowState.id == payload.to_state_id, WorkflowState.project_id == project_id
    ).first()
    if not to_state:
        raise HTTPException(404, "Estado destino no encontrado")
    # Verificar que la transición existe
    transition = db.query(WorkflowTransition).join(
        WorkflowState, WorkflowTransition.from_state_id == WorkflowState.id
    ).filter(
        WorkflowTransition.to_state_id == payload.to_state_id,
        WorkflowTransition.project_id == project_id,
        WorkflowState.value == task.status,
    ).first()
    if not transition:
        raise HTTPException(400, f"No existe transición de '{task.status}' a '{to_state.value}'")
    if transition.requires_comment and not payload.comment:
        raise HTTPException(400, "Esta transición requiere un comentario")
    if transition.required_role and current.role.value != transition.required_role and current.role.value != "admin":
        raise HTTPException(403, f"Solo usuarios con rol '{transition.required_role}' pueden ejecutar esta transición")
    old_status = task.status
    task.status = to_state.value
    db.commit()
    return {"task_id": task_id, "from": old_status, "to": to_state.value, "state_name": to_state.name}


# ══════════════════════════════════════════════════════════════════════════════
# 3. PERMISOS GRANULARES POR PROYECTO
# ══════════════════════════════════════════════════════════════════════════════

class PermissionIn(BaseModel):
    user_id: str
    level: str = "member"  # none|viewer|member|manager|owner
    can_see_financials: bool = False
    can_see_rates: bool = False
    can_export: bool = True


@router.get("/permissions/{project_id}", summary="Permisos del proyecto")
def get_permissions(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _project_or_404(project_id, db)
    perms = (db.query(ProjectPermission)
             .options(joinedload(ProjectPermission.user))
             .filter(ProjectPermission.project_id == project_id)
             .all())
    return [_serialize_perm(p) for p in perms]


@router.post("/permissions/{project_id}", summary="Conceder permiso")
def grant_permission(
    project_id: str,
    payload: PermissionIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin_or_pm),
):
    _project_or_404(project_id, db)
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    existing = db.query(ProjectPermission).filter(
        ProjectPermission.project_id == project_id,
        ProjectPermission.user_id == payload.user_id,
    ).first()
    try:
        level_enum = ProjectPermissionLevel(payload.level)
    except ValueError:
        raise HTTPException(400, f"Nivel inválido: {payload.level}")
    if existing:
        existing.level = level_enum
        existing.can_see_financials = payload.can_see_financials
        existing.can_see_rates = payload.can_see_rates
        existing.can_export = payload.can_export
        existing.granted_by = current.id
        db.commit(); db.refresh(existing)
        return _serialize_perm(existing)
    perm = ProjectPermission(
        project_id=project_id, user_id=payload.user_id, level=level_enum,
        can_see_financials=payload.can_see_financials, can_see_rates=payload.can_see_rates,
        can_export=payload.can_export, granted_by=current.id,
    )
    db.add(perm); db.commit(); db.refresh(perm)
    perm = db.query(ProjectPermission).options(joinedload(ProjectPermission.user)).filter(ProjectPermission.id == perm.id).first()
    return _serialize_perm(perm)


@router.patch("/permissions/{project_id}/{permission_id}", summary="Actualizar permiso")
def update_permission(
    project_id: str, permission_id: str,
    payload: PermissionIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    perm = db.query(ProjectPermission).filter(
        ProjectPermission.id == permission_id, ProjectPermission.project_id == project_id
    ).first()
    if not perm:
        raise HTTPException(404, "Permiso no encontrado")
    try:
        perm.level = ProjectPermissionLevel(payload.level)
    except ValueError:
        raise HTTPException(400, f"Nivel inválido: {payload.level}")
    perm.can_see_financials = payload.can_see_financials
    perm.can_see_rates = payload.can_see_rates
    perm.can_export = payload.can_export
    db.commit(); db.refresh(perm)
    perm = db.query(ProjectPermission).options(joinedload(ProjectPermission.user)).filter(ProjectPermission.id == perm.id).first()
    return _serialize_perm(perm)


@router.delete("/permissions/{project_id}/{permission_id}", summary="Revocar permiso")
def revoke_permission(
    project_id: str, permission_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    perm = db.query(ProjectPermission).filter(
        ProjectPermission.id == permission_id, ProjectPermission.project_id == project_id
    ).first()
    if not perm:
        raise HTTPException(404, "Permiso no encontrado")
    db.delete(perm); db.commit()
    return {"revoked": True}
