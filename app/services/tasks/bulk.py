"""
tasks/bulk.py — Bulk task operations.

Exports:
    bulk_update_tasks
"""
from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from app.models.project import Project
from app.models.task import Task
from app.models.user import UserRole
from app.services.tasks.core import apply_status_side_effects, validate_task_transition
from app.core.abac_enforce import enforce_abac
from app.core.errores import ErrorDeDominio


def _puede_modificar_la_tarea(db: Session, current_user, task) -> bool:
    """¿Este usuario puede tocar **esta** tarea?

    Auditoría 2026-08 (hallazgo 18). Esta cascada estaba dentro del bucle de
    `bulk_update_tasks`, que con ella llegaba a complejidad 15, y su forma lo
    decía todo: cuatro ramas por rol y **la misma comprobación de asignatario
    escrita tres veces**, cada una con su `skipped.append(...)` y su `continue`.
    Sacarla convierte cuatro ramas y tres copias en una pregunta con respuesta
    de sí o no, y el bucle se queda con el reparto de trabajo.

    La política que implementa se conserva **exactamente**:

      · `employee` y `subcontractor` no entran, ni sobre sus propias tareas —
        la actualización masiva es una herramienta de gestión;
      · `admin`, cualquier tarea;
      · `pm`, las de los proyectos que dirige;
      · `team_lead`, las de los proyectos donde es miembro con rol `lead`;
      · y todos los demás roles, sólo las que tienen asignadas. Ese último
        `else` cubre también al `pm` y al `team_lead` fuera de su ámbito, que es
        por lo que aparecía tres veces.
    """
    from app.models.project import ProjectMember, ProjectMemberRole

    rol = current_user.role
    if rol in (UserRole.employee, UserRole.subcontractor):
        return False
    if rol == UserRole.admin:
        return True

    if rol == UserRole.pm:
        proyecto = db.query(Project).filter(Project.id == task.project_id).first()
        if proyecto and proyecto.pm_id == current_user.id:
            return True
    elif rol == UserRole.team_lead:
        es_lead = db.query(ProjectMember).filter(
            ProjectMember.project_id == task.project_id,
            ProjectMember.user_id == current_user.id,
            ProjectMember.role == ProjectMemberRole.lead,
        ).first()
        if es_lead:
            return True

    return task.assignee_id == current_user.id


def bulk_update_tasks(task_ids: list, updates: dict, current_user, db: Session) -> dict:
    """
    Apply status / assignee_id / priority changes to multiple tasks.
    Returns {"updated": int, "skipped": list}.
    """
    task_id_list = list(set(task_ids))
    tasks = db.query(Task).options(joinedload(Task.assignee)).filter(Task.id.in_(task_id_list)).all()

    new_status = updates.get("status")
    new_assignee_id = updates.get("assignee_id")
    new_priority = updates.get("priority")

    updated = 0
    skipped = []

    for task in tasks:
        if not _puede_modificar_la_tarea(db, current_user, task):
            skipped.append({"id": task.id, "reason": "forbidden"})
            continue

        # Auditoría 2026-08 (hallazgo 18): esta comprobación faltaba en la copia
        # de `task_service.py`, que era la que ejecutaba el endpoint. Por qué
        # aquello era latente y no una brecha está escrito allí, en el bloque de
        # reexportación.
        try:
            enforce_abac(db, current_user, "task", task.id, action="update")
        except ErrorDeDominio:
            skipped.append({"id": task.id, "reason": "abac_denied"})
            continue

        if new_status and new_status != task.status:
            # Revisión 2026-11: las mismas reglas que la edición de una tarea;
            # antes la masiva permitía saltos como `cancelled → todo`.
            try:
                validate_task_transition(task.status, new_status)
            except ErrorDeDominio:
                skipped.append({"id": task.id, "reason": "invalid_transition"})
                continue
            apply_status_side_effects(task, new_status)
            task.status = new_status

        if new_assignee_id is not None:
            task.assignee_id = new_assignee_id or None
        if new_priority is not None:
            task.priority = new_priority

        task.version = (task.version or 1) + 1
        updated += 1

    db.commit()
    return {"updated": updated, "skipped": skipped}
