"""
project_service.py — Lógica de negocio para proyectos.

Funciones exportadas (backward-compat wrappers around ProjectService):
  build_project_code(db)
  empty_enrichment()
  enrich_projects_batch(project_ids, db)
  enrich_project(project, db)
  compute_budget_used_pct(project, enrichment)
  calculate_evm(project_id, db)
  calculate_evm_portfolio(db)
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.db.session import is_postgres
from app.models.clients import Client
from app.models.financial import ProjectMilestone
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.project import ProjectMember
from app.models.project import ProjectStatus
from app.models.project import ProjectPhase
from app.models.task import Task, TaskStatus
from app.models.task import Task as _Task
from app.core.config import settings
from app.models.user import UserRole
from app.models.user import User as UserModel
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from app.services.base import ServiceBase


# ── ProjectService class ───────────────────────────────────────────────────────

class ProjectService(ServiceBase):
    """Service class encapsulating all project business logic."""

    # ── Code generation ────────────────────────────────────────────────────────

    def build_code(self) -> str:
        """Generate a unique project code (PRJ-NNNN) with optimistic locking on Postgres."""
        if is_postgres():
            row = self.db.execute(
                select(func.max(Project.code)).with_for_update()
            ).scalar()
        else:
            row = self.db.query(func.max(Project.code)).scalar()

        if row:
            m = re.search(r"(\d+)$", row)
            next_num = (int(m.group(1)) + 1) if m else 1
        else:
            next_num = 1
        return f"PRJ-{next_num:04d}"

    # ── Batch enrichment ───────────────────────────────────────────────────────

    def enrich_batch(self, project_ids: list) -> dict:
        """Return enrichment metrics for multiple projects in a minimal set of queries."""
        if not project_ids:
            return {}

        imp_rows = self.db.query(
            Imputation.project_id,
            func.sum(Imputation.hours).label("total_hours"),
            func.sum(Imputation.cost_amount).label("total_cost"),
            func.count(func.distinct(Imputation.user_id)).label("imp_team"),
        ).filter(Imputation.project_id.in_(project_ids)).group_by(Imputation.project_id).all()
        imp_by_project = {r.project_id: r for r in imp_rows}

        task_total_rows = self.db.query(
            Task.project_id,
            func.count(Task.id).label("cnt"),
        ).filter(Task.project_id.in_(project_ids)).group_by(Task.project_id).all()

        task_done_rows = self.db.query(
            Task.project_id,
            func.count(Task.id).label("cnt"),
        ).filter(Task.project_id.in_(project_ids), Task.status == TaskStatus.done).group_by(Task.project_id).all()

        task_total = {r.project_id: r.cnt for r in task_total_rows}
        task_done = {r.project_id: r.cnt for r in task_done_rows}

        member_rows = self.db.query(
            ProjectMember.project_id,
            func.count(ProjectMember.id).label("cnt"),
        ).filter(ProjectMember.project_id.in_(project_ids)).group_by(ProjectMember.project_id).all()
        member_count = {r.project_id: r.cnt for r in member_rows}

        result: dict = {}
        for pid in project_ids:
            imp = imp_by_project.get(pid)
            total_hours = float(imp.total_hours or 0) if imp else 0.0
            total_cost = float(imp.total_cost or 0) if imp else 0.0
            imp_team = int(imp.imp_team or 0) if imp else 0
            t_total = task_total.get(pid, 0)
            t_done = task_done.get(pid, 0)
            members = member_count.get(pid, 0) or imp_team
            progress = round((t_done / t_total) * 100, 1) if t_total > 0 else 0.0

            result[pid] = {
                "total_hours_spent": total_hours,
                "total_cost_spent": total_cost,
                "budget_used_pct": 0.0,
                "progress_pct": progress,
                "tasks_total": t_total,
                "tasks_done": t_done,
                "team_size": members,
                "_total_hours": total_hours,
                "_total_cost": total_cost,
            }
        return result

    def enrich_single(self, project) -> dict:
        return self.enrich_batch([project.id]).get(project.id, _empty_enrichment())

    def budget_used_pct(self, project, enrichment: dict) -> float:
        total_cost = enrichment["_total_cost"]
        total_hours = enrichment["_total_hours"]
        if project.budget_amount and project.budget_amount > 0:
            return round((total_cost / project.budget_amount) * 100, 1)
        elif project.budget_hours and project.budget_hours > 0:
            return round((total_hours / project.budget_hours) * 100, 1)
        return 0.0

    # ── EVM ────────────────────────────────────────────────────────────────────

    def evm(self, project_id: str) -> dict:
        """
        Calcula indicadores EVM completos para un proyecto:
        BAC, PV, EV, AC, CPI, SPI, CV, SV, EAC, ETC, VAC, TCPI.
        """
        proj = self.db.query(Project).filter(Project.id == project_id).first()
        if not proj:
            return None  # caller raises 404

        today = date.today()

        bac = proj.budget_amount or 0.0
        if bac == 0:
            total_est = self.db.query(func.sum(Task.estimated_hours)).filter(
                Task.project_id == project_id
            ).scalar() or 0.0
            avg_rate = self.db.query(func.avg(Imputation.hourly_rate_snapshot)).filter(
                Imputation.project_id == project_id,
                Imputation.hourly_rate_snapshot.isnot(None),
            ).scalar() or 0.0
            bac = total_est * avg_rate

        ac_cost = self.db.query(func.sum(Imputation.cost_amount)).filter(
            Imputation.project_id == project_id,
            Imputation.cost_amount.isnot(None),
        ).scalar() or 0.0
        if ac_cost == 0:
            rows = self.db.query(Imputation.hours, Imputation.hourly_rate_snapshot).filter(
                Imputation.project_id == project_id
            ).all()
            ac_cost = sum((r.hours * r.hourly_rate_snapshot) for r in rows if r.hourly_rate_snapshot) or 0.0
        ac = ac_cost

        tasks_total = self.db.query(
            func.count(Task.id).label("cnt"),
            func.sum(Task.estimated_hours).label("est"),
        ).filter(Task.project_id == project_id).first()
        tasks_done = self.db.query(
            func.count(Task.id).label("cnt"),
            func.sum(Task.estimated_hours).label("est"),
        ).filter(Task.project_id == project_id, Task.status == TaskStatus.done).first()

        total_est_hours = tasks_total.est or 0.0
        done_est_hours = tasks_done.est or 0.0
        pct_complete = (done_est_hours / total_est_hours) if total_est_hours > 0 else 0.0
        ev = bac * pct_complete

        start = proj.start_date
        end = proj.end_date_planned
        if start and end and end > start:
            total_days = (end - start).days
            elapsed_days = max(0, (today - start).days)
            pct_time = min(elapsed_days / total_days, 1.0)
        else:
            pct_time = None

        pv = bac * pct_time if pct_time is not None else None

        cpi = round(ev / ac, 4) if ac > 0 else None
        spi = round(ev / pv, 4) if (pv is not None and pv > 0) else None
        cv = round(ev - ac, 2)
        sv = round(ev - pv, 2) if pv is not None else None
        eac = round(bac / cpi, 2) if cpi and cpi > 0 else None
        etc = round(eac - ac, 2) if eac is not None else None
        vac = round(bac - eac, 2) if eac is not None else None
        tcpi_denom = bac - ac
        tcpi = round((bac - ev) / tcpi_denom, 4) if tcpi_denom != 0 else None

        return {
            "project_id": project_id,
            "project_name": proj.name,
            "currency": settings.DEFAULT_CURRENCY,
            "bac": round(bac, 2),
            "pv": round(pv, 2) if pv is not None else None,
            "ev": round(ev, 2),
            "ac": round(ac, 2),
            "cpi": cpi,
            "spi": spi,
            "cv": cv,
            "sv": sv,
            "eac": eac,
            "etc": etc,
            "vac": vac,
            "tcpi": tcpi,
            "pct_complete": round(pct_complete * 100, 1),
            "pct_time_elapsed": round(pct_time * 100, 1) if pct_time is not None else None,
            "has_schedule": pct_time is not None,
            "total_tasks": tasks_total.cnt or 0,
            "done_tasks": tasks_done.cnt or 0,
            "health": _evm_health(cpi, spi),
            "start_date": proj.start_date.isoformat() if proj.start_date else None,
            "planned_end": proj.end_date_planned.isoformat() if proj.end_date_planned else None,
        }

    def evm_portfolio(self) -> list:
        """EVM summary for all active/on-hold projects."""
        active = self.db.query(Project).filter(
            Project.status.in_([ProjectStatus.active, ProjectStatus.on_hold])
        ).all()

        results = []
        today = date.today()
        for proj in active:
            bac = proj.budget_amount or 0.0
            if bac == 0:
                total_est = self.db.query(func.sum(Task.estimated_hours)).filter(
                    Task.project_id == proj.id
                ).scalar() or 0.0
                avg_rate = self.db.query(func.avg(Imputation.hourly_rate_snapshot)).filter(
                    Imputation.project_id == proj.id,
                    Imputation.hourly_rate_snapshot.isnot(None),
                ).scalar() or 0.0
                bac = total_est * avg_rate

            ac = self.db.query(func.sum(Imputation.cost_amount)).filter(
                Imputation.project_id == proj.id,
                Imputation.cost_amount.isnot(None),
            ).scalar() or 0.0

            total_est_h = self.db.query(func.sum(Task.estimated_hours)).filter(
                Task.project_id == proj.id
            ).scalar() or 0.0
            done_est_h = self.db.query(func.sum(Task.estimated_hours)).filter(
                Task.project_id == proj.id, Task.status == TaskStatus.done
            ).scalar() or 0.0
            pct = (done_est_h / total_est_h) if total_est_h > 0 else 0.0
            ev = bac * pct

            start, end = proj.start_date, proj.end_date_planned
            if start and end and end > start:
                pct_t = min((today - start).days / (end - start).days, 1.0)
            else:
                pct_t = pct
            pv = bac * max(pct_t, 0)

            cpi = round(ev / ac, 3) if ac > 0 else None
            spi = round(ev / pv, 3) if pv > 0 else None
            eac = round(bac / cpi, 2) if cpi and cpi > 0 else None

            results.append({
                "project_id": proj.id,
                "project_name": proj.name,
                "bac": round(bac, 2),
                "ac": round(ac, 2),
                "ev": round(ev, 2),
                "pv": round(pv, 2),
                "cpi": cpi,
                "spi": spi,
                "eac": eac,
                "pct_complete": round(pct * 100, 1),
                "health": _evm_health(cpi, spi),
            })

        return sorted(results, key=lambda r: r["health"] == "red", reverse=True)


# ── Module-level helper (used by ProjectService and standalone code) ───────────

def _empty_enrichment() -> dict:
    return {
        "total_hours_spent": 0.0,
        "total_cost_spent": 0.0,
        "budget_used_pct": 0.0,
        "progress_pct": 0.0,
        "tasks_total": 0,
        "tasks_done": 0,
        "team_size": 0,
        "_total_hours": 0.0,
        "_total_cost": 0.0,
    }


def _evm_health(cpi: Optional[float], spi: Optional[float]) -> str:
    if cpi is None or spi is None:
        return "grey"
    if cpi >= 0.9 and spi >= 0.9:
        return "green"
    if cpi < 0.85 or spi < 0.85:
        return "red"
    return "yellow"


# ── Backward-compat standalone functions ──────────────────────────────────────

# Code generation ──────────────────────────────────────────────────────────────

def build_project_code(db: Session) -> str:
    """Generate a unique project code (PRJ-NNNN). Backward-compat wrapper."""
    return ProjectService(db).build_code()


# ── Batch enrichment ───────────────────────────────────────────────────────────

def empty_enrichment() -> dict:
    """Return a zeroed enrichment dict. Backward-compat wrapper."""
    return _empty_enrichment()


def enrich_projects_batch(project_ids: list, db: Session) -> dict:
    """Return enrichment metrics for multiple projects. Backward-compat wrapper."""
    return ProjectService(db).enrich_batch(project_ids)


def enrich_project(project, db: Session) -> dict:
    """Return enrichment for a single project. Backward-compat wrapper."""
    return ProjectService(db).enrich_single(project)


def compute_budget_used_pct(project, enrichment: dict) -> float:
    """Compute budget used percentage. Backward-compat wrapper."""
    # Stateless — no need to instantiate service with DB
    total_cost = enrichment["_total_cost"]
    total_hours = enrichment["_total_hours"]
    if project.budget_amount and project.budget_amount > 0:
        return round((total_cost / project.budget_amount) * 100, 1)
    elif project.budget_hours and project.budget_hours > 0:
        return round((total_hours / project.budget_hours) * 100, 1)
    return 0.0


# ── EVM ────────────────────────────────────────────────────────────────────────

def calculate_evm(project_id: str, db: Session) -> dict:
    """
    Calcula indicadores EVM completos para un proyecto. Backward-compat wrapper.
    """
    return ProjectService(db).evm(project_id)


def calculate_evm_portfolio(db: Session) -> list:
    """EVM summary for all active/on-hold projects. Backward-compat wrapper."""
    return ProjectService(db).evm_portfolio()


# ── Project scoped query ───────────────────────────────────────────────────────

def scope_projects_query(q, db: Session, current_user):
    """Apply org isolation and role-based visibility rules to a Project query."""

    if not current_user.is_superadmin and current_user.organization_id:
        q = q.filter(Project.organization_id == current_user.organization_id)

    if current_user.role == UserRole.pm:
        q = q.filter(Project.pm_id == current_user.id)
    elif current_user.role in (UserRole.employee, UserRole.subcontractor):
        project_ids = db.query(func.distinct(Imputation.project_id)).filter(
            Imputation.user_id == current_user.id
        ).subquery()
        task_project_ids = db.query(func.distinct(_Task.project_id)).filter(
            _Task.assignee_id == current_user.id,
            _Task.project_id.isnot(None),
        ).subquery()
        q = q.filter((Project.id.in_(project_ids)) | (Project.id.in_(task_project_ids)))

    return q


# ── Milestones ─────────────────────────────────────────────────────────────────

def list_milestones_payload(
    db: Session,
    project_id: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    status: Optional[str],
) -> list:

    q = db.query(ProjectMilestone)
    if project_id:
        q = q.filter(ProjectMilestone.project_id == project_id)
    if date_from:
        try:
            df = date.fromisoformat(date_from)
            q = q.filter(ProjectMilestone.due_date >= df)
        # intentional: best-effort fallback, log noise outweighs diagnostic value
        except ValueError:
            pass
    if date_to:
        try:
            dt = date.fromisoformat(date_to)
            q = q.filter(ProjectMilestone.due_date <= dt)
        # intentional: best-effort fallback, log noise outweighs diagnostic value
        except ValueError:
            pass
    if status:
        q = q.filter(ProjectMilestone.billing_status == status)

    milestones = q.order_by(ProjectMilestone.due_date).all()
    return [
        {
            "id":             m.id,
            "project_id":     m.project_id,
            "name":           m.name,
            "billing_amount": m.billing_amount,
            "billing_status": m.billing_status,
            "due_date":       str(m.due_date) if m.due_date else None,
        }
        for m in milestones
    ]


# ── Project CRUD helpers ───────────────────────────────────────────────────────

def get_project_scoped_or_404(db: Session, project_id: str, current_user):
    """Fetch project with joinedloads + org isolation. Raises 404 on cross-tenant access."""

    project = (
        db.query(Project)
        .options(joinedload(Project.project_manager), joinedload(Project.phases))
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")
    if (
        not current_user.is_superadmin
        and current_user.organization_id
        and project.organization_id
        and project.organization_id != current_user.organization_id
    ):
        raise HTTPException(404, "Proyecto no encontrado")
    return project


def create_project_record(db: Session, payload, current_user):
    """Build, flush, and return a new Project (with phases, code generation, org isolation, retry on code clash)."""

    phases_data = payload.phases or []
    project_data = payload.model_dump(exclude={"phases"})
    code = project_data.pop("code", None) or build_project_code(db)
    if current_user.role == UserRole.pm and not project_data.get("pm_id"):
        project_data["pm_id"] = current_user.id
    if not project_data.get("organization_id") and current_user.organization_id:
        project_data["organization_id"] = current_user.organization_id

    project = Project(**project_data, code=code, created_by=current_user.id)
    db.add(project)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        if "UNIQUE" in str(e).upper() or "unique" in str(e).lower():
            code = build_project_code(db)
            project_data_retry = payload.model_dump(exclude={"phases"})
            project_data_retry.pop("code", None)
            if current_user.role == UserRole.pm and not project_data_retry.get("pm_id"):
                project_data_retry["pm_id"] = current_user.id
            project = Project(**project_data_retry, code=code, created_by=current_user.id)
            db.add(project)
            db.flush()
        else:
            raise

    for i, phase_data in enumerate(phases_data):
        phase = ProjectPhase(**phase_data.model_dump(), project_id=project.id, order=i)
        db.add(phase)

    # Collaboration: auto-create team + channel for the project (best-effort).
    try:
        from app.services.collaboration._project_sync import on_project_created
        on_project_created(db, project, current_user)
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except Exception:
        # No bloquear creación de proyecto si collaboration falla
        pass

    return project


def apply_project_update(db: Session, project, data: dict) -> None:
    """Apply update data to a project instance — handles optimistic locking and client_name sync."""

    if "version" in data:
        client_version = data.pop("version")
        if project.version is not None and client_version != project.version:
            raise HTTPException(
                409,
                f"Conflicto de edición: el proyecto fue modificado por otro usuario "
                f"(versión esperada {client_version}, versión actual {project.version}). "
                "Recarga y reintenta.",
            )

    if "client_id" in data and data["client_id"] and data["client_id"] != project.client_id:
        new_client = db.query(Client).filter(Client.id == data["client_id"]).first()
        if new_client and "client_name" not in data:
            data["client_name"] = new_client.name

    for field, value in data.items():
        setattr(project, field, value)
    project.version = (project.version or 1) + 1


def cancel_project_record(db: Session, project_id: str) -> dict:

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")
    if project.status == ProjectStatus.cancelled:
        raise ValueError("El proyecto ya esta cancelado")
    project.status = ProjectStatus.cancelled
    db.commit()
    from app.core.events import emit, EventType
    emit(db, EventType.PROJECT_STATUS_CHANGED,
         {"name": project.name, "status": "cancelled", "project_id": project_id},
         resource_type="project", resource_id=project_id, project_id=project_id)
    return {"ok": True, "message": "Proyecto cancelado correctamente"}


def add_project_phase_record(db: Session, project_id: str, payload):
    """Create, persist, and return a new ProjectPhase after verifying the project exists."""

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")
    phase = ProjectPhase(**payload.model_dump(), project_id=project_id)
    db.add(phase)
    db.commit()
    db.refresh(phase)
    return phase


# ── Team / Members ─────────────────────────────────────────────────────────────

def get_project_team_users(db: Session, project_id: str) -> list:
    """Return distinct User objects with imputations on the project."""

    return (
        db.query(UserModel)
        .join(Imputation, Imputation.user_id == UserModel.id)
        .filter(Imputation.project_id == project_id)
        .distinct()
        .all()
    )


def list_members_payload(db: Session, project_id: str) -> list:

    members = (
        db.query(ProjectMember)
        .options(joinedload(ProjectMember.user))
        .filter(ProjectMember.project_id == project_id, ProjectMember.is_active == True)
        .all()
    )
    result = []
    for m in members:
        u = m.user
        result.append({
            "id": m.id, "user_id": m.user_id,
            "full_name": u.full_name if u else "—",
            "email": u.email if u else "—",
            "avatar_initials": (u.full_name or "?")[:2].upper() if u else "?",
            "role": m.role, "allocation_pct": m.allocation_pct,
            "start_date": str(m.start_date) if m.start_date else None,
            "end_date":   str(m.end_date)   if m.end_date   else None,
            "notes": m.notes,
        })
    return result


def add_member_record(db: Session, project_id: str, data: dict):
    """Valida, persiste y retorna un nuevo ProjectMember. Lanza error si ya existe."""

    if not data.get("user_id"):
        raise HTTPException(422, "user_id es obligatorio")
    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == data["user_id"],
    ).first()
    if existing and existing.is_active:
        raise HTTPException(409, "El usuario ya es miembro del proyecto")
    if existing and not existing.is_active:
        existing.is_active = True
        existing.role = data.get("role", existing.role or "developer")
        existing.allocation_pct = data.get("allocation_pct", existing.allocation_pct or 100)
        existing.start_date = data.get("start_date")
        existing.end_date = data.get("end_date")
        existing.notes = data.get("notes")
        db.commit()
        db.refresh(existing)
        return existing
    m = ProjectMember(
        project_id=project_id,
        user_id=data["user_id"],
        role=data.get("role", "developer"),
        allocation_pct=data.get("allocation_pct", 100),
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
        notes=data.get("notes"),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    from app.core.events import emit, EventType
    emit(db, EventType.PROJECT_MEMBER_ADDED,
         {"project_id": project_id, "user_id": data["user_id"], "role": data.get("role")},
         resource_type="project", resource_id=project_id, project_id=project_id)
    return m


def get_member_or_404(db: Session, project_id: str, member_id: str):

    m = db.query(ProjectMember).filter(
        ProjectMember.id == member_id,
        ProjectMember.project_id == project_id,
        ProjectMember.is_active == True,
    ).first()
    if not m:
        raise HTTPException(404, "Miembro no encontrado")
    return m


# ── Thin wrappers used by the router (all DB side-effects live here) ───────────

def get_projects_base_query(db: Session):
    """Return a base Project query with project_manager joinedload."""
    return db.query(Project).options(joinedload(Project.project_manager))


def get_project_by_id(db: Session, project_id: str):
    """Fetch a project by id without org scoping."""
    return db.query(Project).filter(Project.id == project_id).first()


def save_new_project(db: Session, payload, current_user):
    """Create, commit, refresh and return a new Project."""
    project = create_project_record(db, payload, current_user)
    db.commit()
    db.refresh(project)
    from app.core.events import emit, EventType
    emit(db, EventType.PROJECT_CREATED,
         {"name": project.name, "status": str(project.status), "project_id": project.id},
         actor=current_user, resource_type="project", resource_id=project.id,
         project_id=project.id)
    return project


def update_and_save_project(db: Session, project, data: dict):
    """Apply field updates, commit, refresh, and return the updated project."""
    old_status = str(project.status)
    apply_project_update(db, project, data)
    db.commit()
    db.refresh(project)
    from app.core.events import emit, EventType
    new_status = str(project.status)
    etype = EventType.PROJECT_STATUS_CHANGED if new_status != old_status else EventType.PROJECT_UPDATED
    emit(db, etype,
         {"name": project.name, "status": new_status, "project_id": project.id, **data},
         resource_type="project", resource_id=project.id, project_id=project.id)
    return project


def update_member_record(db: Session, m, data: dict):
    """Apply field updates to a ProjectMember, commit, refresh, return it."""
    for k, v in data.items():
        if hasattr(m, k):
            setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return m


def remove_member_record(db: Session, m) -> None:
    """Delete a ProjectMember and commit."""
    project_id = m.project_id
    user_id = m.user_id
    m.is_active = False
    db.commit()
    from app.core.events import emit, EventType
    emit(db, EventType.PROJECT_MEMBER_REMOVED,
         {"project_id": project_id, "user_id": user_id},
         resource_type="project", resource_id=project_id, project_id=project_id)
