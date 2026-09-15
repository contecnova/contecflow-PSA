"""
tasks/queries.py — Pure query helpers for tasks (no side-effects).

Exports:
    get_task_by_id
    get_tasks_for_project
    get_project_member_ids
    task_query_for_user
    project_for_user
    build_task_list_query
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from sqlalchemy.orm import Session, joinedload

from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.core import timeutil

if TYPE_CHECKING:
    pass


def tareas_del_backlog(db: Session, project_id: str) -> list:
    """Las tareas en backlog de un proyecto, por prioridad y antiguedad.

    Auditoria 2026-08 (hallazgo 22): la consulta estaba en el endpoint. No
    lleva filtro de organizacion y es correcto: se busca por `project_id` de un
    proyecto que el endpoint ya verifico con `get_project_scoped_or_404`, asi
    que el ambito llega por la clave padre.
    """
    return (
        db.query(Task)
        .filter(Task.project_id == project_id,
                Task.status == TaskStatus.backlog)
        .order_by(Task.priority.desc(), Task.created_at.asc())
        .all()
    )


def task_query_for_user(db: Session, current_user):
    """Return a Task query scoped to the current user's organization.

    Superadmin bypass: ver project_for_user para la justificación.
    """
    q = db.query(Task).join(Project, Task.project_id == Project.id)
    is_super = bool(getattr(current_user, "is_superadmin", False))
    if not is_super and current_user.organization_id:
        q = q.filter(Project.organization_id == current_user.organization_id)
    return q


def project_for_user(db: Session, project_id: str, current_user) -> Optional[Project]:
    """Return a Project scoped to the current user's organization or None.

    Superadmin bypass: si el user es superadmin se omite el filtro de
    organización (mismo patrón que pipeline_service, approval_engine,
    ai_provider_service). Antes este query devolvía None para un superadmin
    de la org "default" intentando acceder a proyectos de otra tenancy,
    rompiendo la vista de kanban con 404 "Proyecto no encontrado".
    """
    q = db.query(Project).filter(Project.id == project_id)
    is_super = bool(getattr(current_user, "is_superadmin", False))
    if not is_super and current_user.organization_id:
        q = q.filter(Project.organization_id == current_user.organization_id)
    return q.first()


def get_task_by_id(db: Session, task_id: str) -> Optional[Task]:
    """Fetch a single task by id without org scoping."""
    return db.query(Task).filter(Task.id == task_id).first()


def get_tasks_for_project(db: Session, project_id: str) -> list:
    """Return all non-cancelled top-level tasks for a project."""
    from app.models.task import TaskStatus
    return (
        db.query(Task)
        .options(joinedload(Task.assignee))
        .filter(
            Task.project_id == project_id,
            Task.status != TaskStatus.cancelled,
            Task.parent_task_id == None,
        )
        .all()
    )


def get_project_member_ids(db: Session, project_id: str) -> list:
    """Return user_ids of all project members."""
    from app.models.project import ProjectMember
    members = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id
    ).all()
    return [m.user_id for m in members if getattr(m, "user_id", None)]


def _filtrar_por_asignado(q, current_user, assigned_to_me: bool, assignee_id):
    """A quién se le ven las tareas.

    Empleados y subcontratistas ven **sólo las suyas**, pidan lo que pidan: el
    `assignee_id` de la petición no puede ampliar lo que uno ve, sólo acotarlo.
    """
    from app.models.user import UserRole

    if assigned_to_me or getattr(current_user, "role", None) in (
        UserRole.employee, UserRole.subcontractor,
    ):
        return q.filter(Task.assignee_id == current_user.id)
    if assignee_id:
        return q.filter(Task.assignee_id == assignee_id)
    return q


def _filtrar_por_sprint(q, db: Session, sprint_id: str):
    """Tareas de un sprint.

    Auditoría 2026-08: `Task.sprint_id` **no existe**; el enlace es la tabla
    `sprint_tasks`. Ver `task_service.get_tasks_for_sprint`.
    """
    from app.models.sprints import SprintTask

    return q.filter(Task.id.in_(
        db.query(SprintTask.task_id)
        .filter(SprintTask.sprint_id == sprint_id)
        .scalar_subquery()
    ))


def _filtrar_por_estado(q, status: str):
    """Uno o varios estados, separados por comas.

    Con un solo valor se usa igualdad y no `IN`: es la misma respuesta y el
    plan de consulta es mejor.
    """
    valores = [v.strip() for v in status.split(",") if v.strip()]
    if len(valores) == 1:
        return q.filter(Task.status == valores[0])
    if valores:
        return q.filter(Task.status.in_(valores))
    return q


def build_task_list_query(
    db: Session,
    current_user,
    *,
    assigned_to_me: bool = False,
    assignee_id: Optional[str] = None,
    project_id: Optional[str] = None,
    phase_id: Optional[str] = None,
    status: Optional[str] = None,
    priority=None,
    search: Optional[str] = None,
    overdue_only: bool = False,
    sprint_id: Optional[str] = None,
    parent_task_id: Optional[str] = None,
):
    """Consulta de tareas filtrada y acotada a la organización del usuario.

    Centraliza la lógica de filtros de los endpoints de lista, para que el
    endpoint sólo se ocupe de lo suyo: paginación y cabeceras.
    """
    q = task_query_for_user(db, current_user).options(
        joinedload(Task.assignee),
        joinedload(Task.reporter),
    )
    q = _filtrar_por_asignado(q, current_user, assigned_to_me, assignee_id)

    for valor, columna in (
        (project_id, Task.project_id),
        (phase_id, Task.phase_id),
        (parent_task_id, Task.parent_task_id),
        (priority, Task.priority),
    ):
        if valor:
            q = q.filter(columna == valor)

    if sprint_id:
        q = _filtrar_por_sprint(q, db, sprint_id)
    if status:
        q = _filtrar_por_estado(q, status)
    if search:
        q = q.filter(Task.title.ilike(f"%{search}%") | Task.code.ilike(f"%{search}%"))
    if overdue_only:
        # Vencida es «pasó la fecha y sigue viva»: una tarea hecha tarde ya no
        # está vencida, está hecha.
        q = q.filter(
            Task.due_date < timeutil.today(),
            Task.status.not_in([TaskStatus.done, TaskStatus.cancelled]),
        )

    return q
