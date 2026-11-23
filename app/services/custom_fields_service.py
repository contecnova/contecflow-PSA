"""
custom_fields_service.py — Business logic for custom fields, workflows, and permissions.

Covers:
  - Project custom fields CRUD
  - Custom field values per task
  - Project workflow states and transitions
  - Granular project permissions
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session, joinedload
from app.models.custom_fields import ProjectCustomField
from app.models.custom_fields import ProjectCustomFieldValue
from app.models.custom_fields import WorkflowState, WorkflowTransition
from app.models.enterprise import ProjectPermission
from app.models.enterprise import ProjectPermissionLevel
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.core.errores import ErrorDeDominio
from app.models.user import UserRole
from app.core.codigos_de_error import error
from app.services.textos_guardados import pintar_campo as _pintar

if TYPE_CHECKING:
    pass


# ── Serializers ───────────────────────────────────────────────────────────────

def serialize_field(f) -> dict:
    return {
        "id": f.id, "project_id": f.project_id, "name": f.name,
        "field_key": f.field_key, "field_type": f.field_type,
        "options": json.loads(f.options) if f.options else [],
        "is_required": f.is_required, "show_in_list": f.show_in_list,
        "sort_order": f.sort_order,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


def serialize_state(s) -> dict:
    return {
        "id": s.id, "project_id": s.project_id,
        "name": _pintar(s, "name", clave="texto_clave", params="texto_params"),
        "value": s.value, "color": s.color, "icon": s.icon,
        "is_initial": s.is_initial, "is_final": s.is_final, "sort_order": s.sort_order,
        "transitions_from": [
            {
                "id": t.id, "to_state_id": t.to_state_id,
                "to_state_name": _pintar(t.to_state, "name", clave="texto_clave", params="texto_params") if t.to_state else None,
                "label": _pintar(t, "label", clave="texto_clave", params="texto_params"), "required_role": t.required_role,
                "requires_comment": t.requires_comment,
            }
            for t in (s.transitions_from or [])
            if t.is_active
        ],
    }


def serialize_perm(p) -> dict:
    return {
        "id": p.id, "project_id": p.project_id, "user_id": p.user_id,
        "level": p.level.value if p.level else None,
        "can_see_financials": p.can_see_financials,
        "can_see_rates": p.can_see_rates,
        "can_export": p.can_export,
        "granted_at": p.granted_at.isoformat() if p.granted_at else None,
        "user": {
            "id": p.user.id, "full_name": p.user.full_name,
            "role": p.user.role, "job_title": p.user.job_title,
            "department": p.user.department,
        } if p.user else None,
    }


# ── Project helpers ───────────────────────────────────────────────────────────

def get_project_or_404(project_id: str, db: Session):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise error(404, "no_encontrado", detail=f"Proyecto {project_id} no encontrado", que="proyecto")
    return p


# ── Custom fields ─────────────────────────────────────────────────────────────

def list_project_custom_fields(project_id: str, db: Session) -> list:
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        return []
    fields = (
        db.query(ProjectCustomField)
        .filter(ProjectCustomField.project_id == project_id)
        .order_by(ProjectCustomField.sort_order)
        .all()
    )
    return [serialize_field(f) for f in fields]


def create_project_custom_field(project_id: str, payload, db: Session) -> dict:
    get_project_or_404(project_id, db)
    existing = db.query(ProjectCustomField).filter(
        ProjectCustomField.project_id == project_id,
        ProjectCustomField.field_key == payload.field_key,
    ).first()
    if existing:
        raise error(400, "campo_clave_ya_existe_proyecto", detail=f"Ya existe un campo con clave '{payload.field_key}' en este proyecto", clave=payload.field_key)
    f = ProjectCustomField(
        project_id=project_id,
        name=payload.name, field_key=payload.field_key, field_type=payload.field_type,
        options=json.dumps(payload.options) if payload.options else None,
        is_required=payload.is_required, show_in_list=payload.show_in_list,
        sort_order=payload.sort_order,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return serialize_field(f)


def update_project_custom_field(project_id: str, field_id: str, payload, db: Session) -> dict:
    f = db.query(ProjectCustomField).filter(
        ProjectCustomField.id == field_id,
        ProjectCustomField.project_id == project_id,
    ).first()
    if not f:
        raise error(404, "no_encontrado", detail="Campo no encontrado", que="campo")
    for k, v in payload.model_dump(exclude_unset=True).items():
        if k == "options":
            f.options = json.dumps(v) if v else None
        else:
            setattr(f, k, v)
    db.commit()
    db.refresh(f)
    return serialize_field(f)


def delete_project_custom_field(project_id: str, field_id: str, db: Session) -> dict:
    f = db.query(ProjectCustomField).filter(
        ProjectCustomField.id == field_id,
        ProjectCustomField.project_id == project_id,
    ).first()
    if not f:
        raise error(404, "no_encontrado", detail="Campo no encontrado", que="campo")
    db.delete(f)
    db.commit()
    return {"deleted": True}


# ── Custom field values ───────────────────────────────────────────────────────

def get_task_custom_values(project_id: str, task_id: str, db: Session) -> list:
    values = (
        db.query(ProjectCustomFieldValue)
        .options(joinedload(ProjectCustomFieldValue.field))
        .filter(ProjectCustomFieldValue.task_id == task_id)
        .all()
    )
    return [
        {
            "field_id": v.field_id, "field_key": v.field.field_key,
            "field_name": v.field.name, "field_type": v.field.field_type,
            "value": v.value,
        }
        for v in values
    ]


def save_task_custom_values(project_id: str, task_id: str, payload: list, db: Session) -> dict:
    for item in payload:
        existing = db.query(ProjectCustomFieldValue).filter(
            ProjectCustomFieldValue.field_id == item.field_id,
            ProjectCustomFieldValue.task_id == task_id,
        ).first()
        if existing:
            existing.value = item.value
        else:
            db.add(ProjectCustomFieldValue(
                field_id=item.field_id, task_id=task_id, value=item.value
            ))
    db.commit()
    return {"saved": len(payload)}


# ── Workflow states ───────────────────────────────────────────────────────────

def get_workflow(project_id: str, db: Session) -> dict:
    get_project_or_404(project_id, db)
    states = (
        db.query(WorkflowState)
        .options(joinedload(WorkflowState.transitions_from).joinedload(WorkflowTransition.to_state))
        .filter(WorkflowState.project_id == project_id, WorkflowState.is_active == True)
        .order_by(WorkflowState.sort_order)
        .all()
    )
    return {"project_id": project_id, "states": [serialize_state(s) for s in states]}


def create_workflow_state(project_id: str, payload, db: Session) -> dict:
    get_project_or_404(project_id, db)
    existing = db.query(WorkflowState).filter(
        WorkflowState.project_id == project_id,
        WorkflowState.value == payload.value,
        WorkflowState.is_active == True,
    ).first()
    if existing:
        raise error(400, "estado_ya_existe", detail=f"Ya existe un estado con valor '{payload.value}'", valor=payload.value)
    s = WorkflowState(project_id=project_id, **payload.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return serialize_state(s)


def update_workflow_state(project_id: str, state_id: str, payload, db: Session) -> dict:
    s = db.query(WorkflowState).filter(
        WorkflowState.id == state_id,
        WorkflowState.project_id == project_id,
        WorkflowState.is_active == True,
    ).first()
    if not s:
        raise error(404, "no_encontrado", detail="Estado no encontrado", que="estado")
    for k, v in payload.model_dump(exclude_unset=True).items():
        if k == "name" and v not in (s.name, _pintar(s, "name", clave="texto_clave", params="texto_params")):
            s.texto_clave = s.texto_params = None   # migracion 200: nombre escrito a mano, se respeta
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return serialize_state(s)


def delete_workflow_state(project_id: str, state_id: str, db: Session) -> dict:
    """Soft-delete a workflow state. Validates no tasks actively in this state."""
    s = db.query(WorkflowState).filter(
        WorkflowState.id == state_id,
        WorkflowState.project_id == project_id,
        WorkflowState.is_active == True,
    ).first()
    if not s:
        raise error(404, "no_encontrado", detail="Estado no encontrado", que="estado")

    # Check if any active tasks are using this state
    in_use = db.query(Task).filter(
        Task.status == s.value,
        Task.project_id == project_id,
    ).count()
    if in_use > 0:
        raise error(400, "estado_en_uso", n=in_use)

    # Soft-delete: mark as inactive
    s.is_active = False
    db.commit()
    return {"ok": True, "message": f"Estado '{s.name}' eliminado"}


# ── Workflow transitions ──────────────────────────────────────────────────────

def create_transition(project_id: str, payload, db: Session) -> dict:
    for sid in [payload.from_state_id, payload.to_state_id]:
        s = db.query(WorkflowState).filter(
            WorkflowState.id == sid, WorkflowState.project_id == project_id, WorkflowState.is_active == True
        ).first()
        if not s:
            raise error(404, "no_encontrado", detail=f"Estado {sid} no encontrado en este proyecto", que="estado")
    t = WorkflowTransition(project_id=project_id, **payload.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return {
        "id": t.id, "from_state_id": t.from_state_id, "to_state_id": t.to_state_id,
        "label": _pintar(t, "label", clave="texto_clave", params="texto_params"), "required_role": t.required_role,
        "requires_comment": t.requires_comment,
    }


def delete_transition(project_id: str, transition_id: str, db: Session) -> dict:
    """Soft-delete a workflow transition."""
    t = db.query(WorkflowTransition).filter(
        WorkflowTransition.id == transition_id,
        WorkflowTransition.project_id == project_id,
        WorkflowTransition.is_active == True,
    ).first()
    if not t:
        raise error(404, "no_encontrado", detail="Transición no encontrada", que="transicion")

    # Soft-delete: mark as inactive
    t.is_active = False
    db.commit()
    from app.models.project import Project as _Proyecto
    from app.services.formato_regional import idioma_de_salida
    from app.services.textos_de_salida import texto as _tx
    _org = db.query(_Proyecto.organization_id).filter(_Proyecto.id == project_id).scalar()
    return {"ok": True, "message": _tx("flujo.transicion_eliminada", idioma_de_salida(db, org_id=_org))}


def init_default_workflow(project_id: str, db: Session) -> dict:
    get_project_or_404(project_id, db)
    existing = db.query(WorkflowState).filter(
        WorkflowState.project_id == project_id,
        WorkflowState.is_active == True,
    ).count()
    if existing > 0:
        raise error(400, "proyecto_ya_tiene_flujo", detail="Este proyecto ya tiene un workflow definido")

    from app.models.project import Project as _Proyecto
    from app.services.formato_regional import idioma_de_salida
    from app.services.textos_de_salida import texto as _tx
    _org = db.query(_Proyecto.organization_id).filter(_Proyecto.id == project_id).scalar()
    _id = idioma_de_salida(db, org_id=_org)
    # 23-11-2026: nombres y etiquetas en el idioma de la empresa (`flujo.estado.*`, `flujo.transicion.*`).
    defaults = [
        ("todo",        "#7a8aaa", "⭕", True,  False, 0),
        ("in_progress", "#00d4ff", "🔵", False, False, 1),
        ("in_review",   "#ffb800", "🟡", False, False, 2),
        ("done",        "#00e5a0", "✅", False, True,  3),
        ("blocked",     "#ff4757", "🔴", False, False, 4),
    ]
    states: dict = {}
    for value, color, icon, is_initial, is_final, order in defaults:
        name = _tx(f"flujo.estado.{value}", _id)
        s = WorkflowState(
            project_id=project_id, name=name, value=value, color=color,
            icon=icon, is_initial=is_initial, is_final=is_final, sort_order=order,
            texto_clave=f"flujo.estado.{value}",   # migracion 200
        )
        db.add(s)
        db.flush()
        states[value] = s

    transitions = [
        ("todo",        "in_progress", "iniciar",     None, False),
        ("in_progress", "in_review",   "revision",    None, False),
        ("in_progress", "blocked",     "bloqueado",   None, True),
        ("in_review",   "done",        "aprobar",     "pm", True),
        ("in_review",   "in_progress", "rechazar",    "pm", True),
        ("blocked",     "in_progress", "desbloquear", None, False),
        ("todo",        "blocked",     "bloquear",    None, False),
    ]
    for from_v, to_v, clave, role, req_comment in transitions:
        label = _tx(f"flujo.transicion.{clave}", _id)
        db.add(WorkflowTransition(
            project_id=project_id,
            from_state_id=states[from_v].id, to_state_id=states[to_v].id,
            label=label, required_role=role, requires_comment=req_comment,
            texto_clave=f"flujo.transicion.{clave}",   # migracion 200
        ))
    db.commit()
    return {"initialized": True, "states": len(defaults), "transitions": len(transitions)}


def transition_task(project_id: str, task_id: str, payload, current_user, db: Session) -> dict:
    task = db.query(Task).filter(Task.id == task_id, Task.project_id == project_id).first()
    if not task:
        raise error(404, "no_encontrado", detail="Tarea no encontrada", que="tarea")
    to_state = db.query(WorkflowState).filter(
        WorkflowState.id == payload.to_state_id,
        WorkflowState.project_id == project_id,
        WorkflowState.is_active == True,
    ).first()
    if not to_state:
        raise error(404, "no_encontrado", detail="Estado destino no encontrado", que="estado_destino")
    transition = db.query(WorkflowTransition).join(
        WorkflowState, WorkflowTransition.from_state_id == WorkflowState.id
    ).filter(
        WorkflowTransition.to_state_id == payload.to_state_id,
        WorkflowTransition.project_id == project_id,
        WorkflowTransition.is_active == True,
        WorkflowState.value == task.status,
        WorkflowState.is_active == True,
    ).first()
    if not transition:
        raise error(400, "transicion_no_permitida", detail=f"No existe transición de '{task.status}' a '{to_state.value}'", desde=task.status, hasta=to_state.value)
    if transition.requires_comment and not payload.comment:
        raise error(400, "transicion_requiere_comentario")
    if (
        transition.required_role
        and current_user.role != transition.required_role
        and current_user.role != UserRole.admin
    ):
        raise error(403, "transicion_requiere_rol", detail=f"Solo usuarios con rol '{transition.required_role}' pueden ejecutar esta transición", rol=transition.required_role)
    old_status = task.status
    task.status = to_state.value
    db.commit()
    return {
        "task_id": task_id, "from": old_status,
        "to": to_state.value, "state_name": _pintar(to_state, "name", clave="texto_clave", params="texto_params"),
    }


def reset_workflow(project_id: str, db: Session) -> dict:
    """Soft-delete de estados/transiciones actuales y recreación de workflow estándar."""
    get_project_or_404(project_id, db)
    db.query(WorkflowTransition).filter(
        WorkflowTransition.project_id == project_id,
        WorkflowTransition.is_active == True,
    ).update({"is_active": False}, synchronize_session=False)
    db.query(WorkflowState).filter(
        WorkflowState.project_id == project_id,
        WorkflowState.is_active == True,
    ).update({"is_active": False}, synchronize_session=False)
    db.commit()
    return init_default_workflow(project_id, db)


# ── Project permissions ───────────────────────────────────────────────────────

def get_permissions(project_id: str, db: Session) -> list:
    get_project_or_404(project_id, db)
    perms = (
        db.query(ProjectPermission)
        .options(joinedload(ProjectPermission.user))
        .filter(ProjectPermission.project_id == project_id)
        .all()
    )
    return [serialize_perm(p) for p in perms]


def grant_permission(project_id: str, payload, current_user, db: Session) -> dict:
    get_project_or_404(project_id, db)
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise error(404, "no_encontrado", detail="Usuario no encontrado", que="usuario")
    existing = db.query(ProjectPermission).filter(
        ProjectPermission.project_id == project_id,
        ProjectPermission.user_id == payload.user_id,
    ).first()
    try:
        level_enum = ProjectPermissionLevel(payload.level)
    except ValueError:
        raise error(400, "valor_no_valido", detail=f"Nivel inválido: {payload.level}", valor=payload.level)
    if existing:
        existing.level = level_enum
        existing.can_see_financials = payload.can_see_financials
        existing.can_see_rates = payload.can_see_rates
        existing.can_export = payload.can_export
        existing.granted_by = current_user.id
        db.commit()
        db.refresh(existing)
        existing = db.query(ProjectPermission).options(
            joinedload(ProjectPermission.user)
        ).filter(ProjectPermission.id == existing.id).first()
        return serialize_perm(existing)
    perm = ProjectPermission(
        project_id=project_id, user_id=payload.user_id, level=level_enum,
        can_see_financials=payload.can_see_financials, can_see_rates=payload.can_see_rates,
        can_export=payload.can_export, granted_by=current_user.id,
    )
    db.add(perm)
    db.commit()
    db.refresh(perm)
    perm = db.query(ProjectPermission).options(
        joinedload(ProjectPermission.user)
    ).filter(ProjectPermission.id == perm.id).first()
    return serialize_perm(perm)


def update_permission(project_id: str, permission_id: str, payload, db: Session) -> dict:
    perm = db.query(ProjectPermission).filter(
        ProjectPermission.id == permission_id,
        ProjectPermission.project_id == project_id,
    ).first()
    if not perm:
        raise error(404, "no_encontrado", detail="Permiso no encontrado", que="permiso")
    try:
        perm.level = ProjectPermissionLevel(payload.level)
    except ValueError:
        raise error(400, "valor_no_valido", detail=f"Nivel inválido: {payload.level}", valor=payload.level)
    perm.can_see_financials = payload.can_see_financials
    perm.can_see_rates = payload.can_see_rates
    perm.can_export = payload.can_export
    db.commit()
    db.refresh(perm)
    perm = db.query(ProjectPermission).options(
        joinedload(ProjectPermission.user)
    ).filter(ProjectPermission.id == perm.id).first()
    return serialize_perm(perm)


def revoke_permission(project_id: str, permission_id: str, db: Session) -> dict:
    perm = db.query(ProjectPermission).filter(
        ProjectPermission.id == permission_id,
        ProjectPermission.project_id == project_id,
    ).first()
    if not perm:
        raise error(404, "no_encontrado", detail="Permiso no encontrado", que="permiso")
    db.delete(perm)
    db.commit()
    return {"revoked": True}
