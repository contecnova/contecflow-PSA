"""
tasks/core.py — Core TaskService class plus status-transition helpers.

Exports:
    TaskService
    validate_task_transition
    apply_status_side_effects
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.models.project import Project, ProjectMember
from app.models.semantic_engine import SemConfig
from app.models.task import Task, TaskComment, TaskStatus
from app.models.task import Task as TaskModel
from app.models.task_movement_log import TaskMovementLog
from app.models.user import UserRole
from app.schemas import TaskOut as TaskOutSchema
from app.services.base import ServiceBase
from app.services.numbering import next_numbered_code
from app.services.tasks.queries import task_query_for_user, project_for_user

if TYPE_CHECKING:
    pass


# ── Transition policy ─────────────────────────────────────────────────────────
# Toda transición entre estados está permitida: el kanban es una herramienta de
# trabajo donde el usuario decide cómo mueve sus tareas. La trazabilidad se
# garantiza vía TaskMovementLog (cada cambio queda registrado con quién, cuándo,
# desde/hasta y motivo opcional). Si el frontend considera una transición
# "sensible" (p.ej. reabrir una tarea ya done/cancelled) puede solicitar al
# usuario un `move_reason` antes de enviar el PATCH.

_TASK_VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.backlog:     {TaskStatus.todo, TaskStatus.cancelled},
    TaskStatus.todo:        {TaskStatus.in_progress, TaskStatus.backlog, TaskStatus.cancelled},
    TaskStatus.in_progress: {TaskStatus.in_review, TaskStatus.todo, TaskStatus.done,
                              TaskStatus.blocked, TaskStatus.cancelled},
    TaskStatus.in_review:   {TaskStatus.done, TaskStatus.in_progress, TaskStatus.cancelled},
    TaskStatus.done:        {TaskStatus.in_progress},  # reopen
    TaskStatus.blocked:     {TaskStatus.in_progress, TaskStatus.todo, TaskStatus.cancelled},
    TaskStatus.cancelled:   set(),  # terminal
}


def validate_task_transition(current_status: TaskStatus, new_status: TaskStatus) -> None:
    """Raise 400 if the transition is not permitted by _TASK_VALID_TRANSITIONS."""
    allowed = _TASK_VALID_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Transición inválida: {current_status.value} → {new_status.value}.",
        )


def apply_status_side_effects(task, new_status: TaskStatus) -> None:
    """Set started_at / completed_at timestamps when status changes."""
    if new_status == TaskStatus.in_progress:
        task.started_at = datetime.now(timezone.utc)
    elif new_status == TaskStatus.done:
        task.completed_at = datetime.now(timezone.utc)

        # Trigger OKR sync si la tarea está vinculada a un proyecto con OKRs
        try:
            from app.services import okr_service
            getattr(task, '_sa_instance_state', None)
            if hasattr(task, 'project_id') and task.project_id:
                session = getattr(task, '_sa_instance_state', None)
                if session:
                    db_session = session.session
                    krs = db_session.query(okr_service.KeyResult).join(okr_service.Objective).filter(
                        okr_service.Objective.project_id == task.project_id
                    ).all()
                    for kr in krs:
                        try:
                            okr_service.sync_kr_from_tasks(kr.id, task.assignee_id or "system", db_session)
                        except Exception as e:
                            import logging
                            logging.getLogger(__name__).warning(f"OKR sync failed for KR {kr.id}: {e}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"OKR sync global error: {e}")


# ── TaskService ───────────────────────────────────────────────────────────────

class TaskService(ServiceBase):
    """Service class encapsulating all task business logic."""

    # ── Auto-assign on create ─────────────────────────────────────────────────

    def _auto_assign_on_create(self, task: Task) -> None:
        """Auto-assign task at creation time when semantic config enables it."""
        if task.assignee_id:
            return

        cfg = self.db.query(SemConfig).first()
        if not cfg or not bool(getattr(cfg, "auto_assign_tasks", False)):
            return

        members = (
            self.db.query(ProjectMember)
            .filter(ProjectMember.project_id == task.project_id)
            .all()
        )
        candidate_user_ids = [m.user_id for m in members if getattr(m, "user_id", None)]
        if not candidate_user_ids:
            return

        from app.services.semantic_classifier import SemanticAssigner
        priority = str(task.priority.value) if hasattr(task.priority, "value") else str(task.priority or "medium")
        suggestion = SemanticAssigner(self.db).suggest_for_task(
            task.title or "",
            task.description or "",
            candidate_user_ids,
            priority=priority,
        )
        suggested = suggestion.get("suggested_user_id")
        if not suggested or suggestion.get("needs_review", True):
            return
        if suggested not in set(candidate_user_ids):
            return

        task.assignee_id = suggested

    # ── Kanban ────────────────────────────────────────────────────────────────

    def get_kanban(self, project_id: str) -> dict:
        project = project_for_user(self.db, project_id, self.current_user)
        if not project:
            raise HTTPException(status_code=404, detail="Proyecto no encontrado")

        if self.current_user.role in (UserRole.employee, UserRole.subcontractor):
            has_task = self.db.query(Task).filter(
                Task.project_id == project_id,
                Task.assignee_id == self.current_user.id,
            ).first()
            if not has_task:
                raise HTTPException(status_code=403, detail="No tienes tareas en este proyecto")

        tasks = self.db.query(Task).options(
            joinedload(Task.assignee)
        ).filter(
            Task.project_id == project_id,
            Task.status != TaskStatus.cancelled,
            Task.parent_task_id == None,
        ).all()

        columns = {s.value: [] for s in TaskStatus if s != TaskStatus.cancelled}
        for task in tasks:
            col = task.status.value
            if col in columns:
                columns[col].append(TaskOutSchema.model_validate(task))
        return columns

    # ── Create ────────────────────────────────────────────────────────────────

    def create(self, payload):
        if self.current_user.role in (UserRole.employee, UserRole.subcontractor):
            raise HTTPException(status_code=403, detail="No tienes permiso para crear tareas")

        project = project_for_user(self.db, payload.project_id, self.current_user)
        if not project:
            raise HTTPException(status_code=404, detail="Proyecto no encontrado")

        task = Task(
            **payload.model_dump(),
            code=next_numbered_code(self.db, "task", prefix="TSK", padding=5),
            reporter_id=self.current_user.id,
            created_by=self.current_user.id,
        )
        self._auto_assign_on_create(task)
        try:
            self.db.add(task)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(status_code=409, detail="Código de tarea duplicado. Inténtalo de nuevo.")
        self.db.refresh(task)
        from app.core.events import emit, EventType
        emit(self.db, EventType.TASK_CREATED,
             {"title": task.title, "status": str(task.status), "assignee_id": task.assignee_id,
              "project_id": task.project_id, "code": task.code},
             actor=self.current_user, resource_type="task", resource_id=task.id,
             project_id=task.project_id)
        return task

    # ── Get single ────────────────────────────────────────────────────────────

    def get(self, task_id: str):
        task = task_query_for_user(self.db, self.current_user).options(
            joinedload(Task.assignee),
            joinedload(Task.reporter),
            joinedload(Task.comments).joinedload(TaskComment.author),
            joinedload(Task.subtasks),
        ).filter(Task.id == task_id).first()

        if not task:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")

        if self.current_user.role != UserRole.admin:
            project = self.db.query(Project).filter(Project.id == task.project_id).first()
            is_project_pm = project and project.pm_id == self.current_user.id
            is_task_participant = (
                task.assignee_id == self.current_user.id or
                task.reporter_id == self.current_user.id
            )
            if not is_project_pm and not is_task_participant:
                raise HTTPException(status_code=403, detail="No tienes acceso a esta tarea")

        return task

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, task_id: str, payload):
        import logging
        logger = logging.getLogger(__name__)

        task = task_query_for_user(self.db, self.current_user).filter(Task.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")

        project = project_for_user(self.db, task.project_id, self.current_user)
        if not project:
            raise HTTPException(status_code=404, detail="Proyecto no encontrado")

        if self.current_user.role != UserRole.admin:
            is_project_pm = project and project.pm_id == self.current_user.id
            if not is_project_pm and task.assignee_id != self.current_user.id:
                raise HTTPException(status_code=403, detail="No tienes permiso para editar esta tarea")

        old_assignee_id = task.assignee_id
        old_status = task.status

        if payload.status and payload.status != task.status:
            validate_task_transition(task.status, payload.status)
            apply_status_side_effects(task, payload.status)

        for field, value in payload.model_dump(exclude_unset=True).items():
            if field == "version":
                continue
            setattr(task, field, value)

        client_version = payload.model_dump(exclude_unset=True).get("version")
        if client_version is not None and client_version != (task.version or 1):
            raise HTTPException(
                status_code=409,
                detail=f"Conflicto de edición: la tarea fue modificada por otro usuario (versión {task.version}). Recarga y reintenta.",
            )
        task.version = (task.version or 1) + 1

        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Integrity error updating task {task_id}: {str(e)}")
            raise HTTPException(status_code=409, detail="Task state conflict. Please reload and try again.")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Database error updating task {task_id}: {str(e)}")
            raise HTTPException(status_code=503, detail="Database operation failed")

        self.db.refresh(task)

        # ── Movement log ──────────────────────────────────────────────────────
        changed_fields = payload.model_dump(exclude_unset=True)
        new_status_val = changed_fields.get("status")
        if new_status_val is not None and new_status_val != old_status:
            move_reason = changed_fields.get("move_reason")
            log_entry = TaskMovementLog(
                task_id=task.id,
                project_id=task.project_id,
                moved_by_id=self.current_user.id,
                from_status=str(old_status.value) if old_status else None,
                to_status=str(new_status_val.value) if hasattr(new_status_val, 'value') else str(new_status_val),
                reason=move_reason,
            )
            self.db.add(log_entry)
            self.db.commit()

        from app.core.events import emit, EventType
        new_assignee = changed_fields.get("assignee_id")
        new_status = changed_fields.get("status")
        if new_status and str(new_status) in ("done", "completed", "closed"):
            etype = EventType.TASK_COMPLETED
        elif new_assignee and new_assignee != old_assignee_id:
            etype = EventType.TASK_ASSIGNED
        else:
            etype = EventType.TASK_UPDATED
        emit(self.db, etype,
             {"title": task.title, "status": str(task.status), "assignee_id": task.assignee_id,
              "project_id": task.project_id, **changed_fields},
             actor=self.current_user, resource_type="task", resource_id=task.id,
             project_id=task.project_id)
        return task, old_assignee_id

    # ── Cancel ────────────────────────────────────────────────────────────────

    def cancel(self, task_id: str) -> dict:
        import logging
        logger = logging.getLogger(__name__)

        task = self.db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        task.status = TaskStatus.cancelled
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Integrity error cancelling task {task_id}: {str(e)}")
            raise HTTPException(status_code=409, detail="Cannot cancel task. State conflict.")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Database error cancelling task {task_id}: {str(e)}")
            raise HTTPException(status_code=503, detail="Database operation failed")
        from app.core.events import emit, EventType
        emit(self.db, EventType.TASK_DELETED,
             {"title": task.title, "project_id": task.project_id, "reason": "cancelled"},
             resource_type="task", resource_id=task_id, project_id=task.project_id)
        return {"message": "Tarea cancelada"}

    # ── Comment ───────────────────────────────────────────────────────────────

    def add_comment(self, task_id: str, payload):
        import logging
        logger = logging.getLogger(__name__)

        task = self.db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")

        if self.current_user.role != UserRole.admin:
            project = self.db.query(Project).filter(Project.id == task.project_id).first()
            is_project_pm = project and project.pm_id == self.current_user.id
            is_task_participant = (
                task.assignee_id == self.current_user.id or
                task.reporter_id == self.current_user.id
            )
            if not is_project_pm and not is_task_participant:
                raise HTTPException(status_code=403, detail="No tienes acceso a esta tarea")

        comment = TaskComment(
            task_id=task_id,
            author_id=self.current_user.id,
            content=payload.content,
        )
        self.db.add(comment)
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Integrity error adding comment to task {task_id}: {str(e)}")
            raise HTTPException(status_code=409, detail="Cannot add comment. Conflict.")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Database error adding comment to task {task_id}: {str(e)}")
            raise HTTPException(status_code=503, detail="Database operation failed")
        self.db.refresh(comment)
        return comment

    # ── Bulk dates ────────────────────────────────────────────────────────────

    def bulk_update_dates(self, updates: list) -> dict:
        from datetime import date as _date
        import logging
        logger = logging.getLogger(__name__)

        def _to_date(v):
            if not v:
                return None
            if isinstance(v, _date):
                return v
            try:
                return _date.fromisoformat(str(v)[:10])
            except (ValueError, TypeError):
                return None

        updated = 0
        errors = []
        for u in updates:
            task = self.db.query(TaskModel).filter(TaskModel.id == u.get("id")).first()
            if not task:
                errors.append(u.get("id"))
                continue
            if "start_date" in u:
                task.start_date = _to_date(u["start_date"])
            if "due_date" in u:
                task.due_date = _to_date(u["due_date"])
            updated += 1
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Integrity error in bulk_update_dates: {str(e)}")
            raise HTTPException(status_code=409, detail="Constraint violation in bulk date update.")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Database error in bulk_update_dates: {str(e)}")
            raise HTTPException(status_code=503, detail="Database operation failed")
        return {"updated": updated, "errors": errors}

    # ── Task Dependencies ─────────────────────────────────────────────────────

    def list_dependencies(self, project_id: str) -> list:
        from app.models.bookings import TaskDependency
        q = (
            self.db.query(TaskDependency)
            .options(
                joinedload(TaskDependency.predecessor),
                joinedload(TaskDependency.successor),
            )
            .join(Task, TaskDependency.predecessor_id == Task.id)
            .filter(Task.project_id == project_id)
        )
        return [
            {
                "id": d.id,
                "predecessor_id": d.predecessor_id,
                "successor_id": d.successor_id,
                "dependency_type": d.dependency_type,
                "lag_days": d.lag_days,
            }
            for d in q.all()
        ]

    def create_dependency(
        self,
        predecessor_id: str,
        successor_id: str,
        dependency_type: str,
        lag_days: int,
        created_by: str,
    ) -> dict:
        from app.models.bookings import TaskDependency
        if predecessor_id == successor_id:
            raise HTTPException(400, "Una tarea no puede depender de sí misma")
        existing = (
            self.db.query(TaskDependency)
            .filter(
                TaskDependency.predecessor_id == predecessor_id,
                TaskDependency.successor_id == successor_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(409, "La dependencia ya existe")
        dep = TaskDependency(
            predecessor_id=predecessor_id,
            successor_id=successor_id,
            dependency_type=dependency_type,
            lag_days=lag_days,
            created_by=created_by,
        )
        self.db.add(dep)
        self.db.commit()
        self.db.refresh(dep)
        return {
            "id": dep.id,
            "predecessor_id": dep.predecessor_id,
            "successor_id": dep.successor_id,
            "dependency_type": dep.dependency_type,
            "lag_days": dep.lag_days,
        }

    def delete_dependency(self, dep_id: str) -> dict:
        from app.models.bookings import TaskDependency
        dep = self.db.query(TaskDependency).filter(TaskDependency.id == dep_id).first()
        if not dep:
            raise HTTPException(404, "Dependencia no encontrada")
        self.db.delete(dep)
        self.db.commit()
        return {"ok": True}
