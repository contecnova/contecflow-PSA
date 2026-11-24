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
from app.services import numbering as _numeracion  # prefijos por defecto (§6)

from datetime import date
from typing import Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session
from app.services.settings_service import por_empresa as _pe
from app.models.clients import Client
from app.models.financial import ProjectMilestone
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.project import ProjectMember
from app.models.project import ProjectStatus
from app.models.project import ProjectPhase
from app.models.task import Task, TaskStatus
from app.models.task import Task as _Task
from app.models.user import UserRole
from app.models.user import User as UserModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from app.services.base import ServiceBase
import logging
from app.core import timeutil
from app.core.asignacion import es_asignable
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error
from app.core.codigos_de_error import ErrorConCodigo

logger = logging.getLogger(__name__)


# ── ProjectService class ───────────────────────────────────────────────────────

class ProjectService(ServiceBase):
    """Service class encapsulating all project business logic."""

    # ── Code generation ────────────────────────────────────────────────────────

    def build_code(self) -> str:
        """Codigo de proyecto de la secuencia de la empresa (`numbering`).

        Auditoria 2026-11-22 (A-MP5): era `SELECT max(code) ... FOR UPDATE`,
        que Postgres rechaza (FOR UPDATE no admite agregados), asi que el alta
        de proyecto fallaba siempre en Postgres; ademas `max` sobre texto ordena
        "PRJ-9999" por encima de "PRJ-10000" y no casaba con la secuencia que
        ya usan cartera, demanda, pipeline y plantillas. Ahora la misma
        secuencia por empresa, bloqueada con FOR UPDATE sobre su fila.
        """
        from app.services.numbering import next_numbered_code
        return next_numbered_code(self.db, "project", prefix=_numeracion.PREFIJO_PROYECTO, padding=4)

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

        # Rev. 173: el cálculo es uno solo (app/services/evm_service.py): PV de la
        # línea base vigente y EV por el avance real de cada tarea. Aquí solo se
        # añaden los campos de la ficha.
        from app.services.evm_service import evm_de_proyecto
        d = evm_de_proyecto(self.db, proj)
        d.pop("_partidas", None)
        total, hechas = self.db.query(
            func.count(Task.id), func.sum(case((Task.status == TaskStatus.done, 1), else_=0)),
        ).filter(Task.project_id == project_id, Task.is_active.is_(True),
                 Task.status != TaskStatus.cancelled).first()
        org = proj.organization_id
        return {
            "project_id": project_id,
            "project_name": proj.name,
            "currency": _pe.moneda_de_empresa(self.db, registro=proj),  # 18-11-2026
            **d,
            "pct_time_elapsed": d["pct_planned"],
            "total_tasks": total or 0,
            "done_tasks": int(hechas or 0),
            "health": _evm_health(d["cpi"], d["spi"], self.db, org),
            "cpi_status": estado_de_indice(d["cpi"], self.db, org_id=org),
            "spi_status": estado_de_indice(d["spi"], self.db, org_id=org),
            "tcpi_status": estado_de_indice(d["tcpi"], self.db, menor_es_mejor=True, org_id=org),
            "start_date": proj.start_date.isoformat() if proj.start_date else None,
            "planned_end": proj.end_date_planned.isoformat() if proj.end_date_planned else None,
        }

    def evm_portfolio(self) -> list:
        """EVM de los proyectos activos o en pausa, con el mismo cálculo que la ficha.

        Revisión 2026-11: tenía su propia copia sin los respaldos de AC y de
        fechas, y la lista y la ficha daban valores distintos del mismo proyecto.
        """
        activos = self.db.query(Project.id).filter(
            Project.status.in_([ProjectStatus.active, ProjectStatus.on_hold])
        ).all()
        campos = ("project_id", "project_name", "bac", "ac", "ev", "pv", "cpi", "spi", "eac", "tcpi",
                  "pct_complete", "health", "cpi_status", "spi_status", "tcpi_status", "has_schedule")
        results = [{k: d[k] for k in campos} for d in (self.evm(pid) for (pid,) in activos) if d]
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


def estado_de_indice(valor: Optional[float], db: Session, menor_es_mejor: bool = False,
                     org_id: Optional[str] = None) -> str:
    """Semáforo de un índice EVM con los umbrales de Admin (`EVM_INDEX_*`).

    CPI y SPI: mejor cuanto más alto. TCPI (el CPI que haría falta para acabar
    en presupuesto): mejor cuanto más bajo, así que se juzga su inverso.
    """
    if valor is None:
        return "grey"
    if menor_es_mejor:
        if valor <= 0:
            return "green"
        valor = 1 / valor
    from app.services.settings_service import get_runtime_float
    org = org_id or db.info.get("organization_id")  # el ajuste es por empresa
    verde = get_runtime_float(db, "EVM_INDEX_GREEN_MIN", org)
    rojo = get_runtime_float(db, "EVM_INDEX_RED_BELOW", org)
    if valor >= verde:
        return "green"
    return "red" if valor < rojo else "yellow"


def _evm_health(cpi: Optional[float], spi: Optional[float], db: Session, org_id: Optional[str] = None) -> str:
    if cpi is None or spi is None:
        return "grey"
    estados = {estado_de_indice(cpi, db, org_id=org_id), estado_de_indice(spi, db, org_id=org_id)}
    return "red" if "red" in estados else "yellow" if "yellow" in estados else "green"


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

    # Auditoria 2026-11: los permisos por proyecto se aplican (`permisos_de_proyecto`).
    from app.core.permisos_de_proyecto import vetados_y_concedidos
    vetados, concedidos = vetados_y_concedidos(db, current_user)

    if current_user.role == UserRole.pm:
        q = q.filter((Project.pm_id == current_user.id) | Project.id.in_(concedidos or [""]))
    elif current_user.role in (UserRole.employee, UserRole.subcontractor):
        project_ids = db.query(func.distinct(Imputation.project_id)).filter(
            Imputation.user_id == current_user.id
        ).subquery()
        task_project_ids = db.query(func.distinct(_Task.project_id)).filter(
            _Task.assignee_id == current_user.id,
            _Task.project_id.isnot(None),
        ).subquery()
        # Segunda auditoría 2026-11: el miembro explícito y activo del equipo
        # (`project_members`) ve el proyecto aunque aún no tenga tareas ni horas.
        member_project_ids = db.query(ProjectMember.project_id).filter(
            ProjectMember.user_id == current_user.id,
            ProjectMember.is_active.is_(True),
        ).subquery()
        q = q.filter((Project.id.in_(project_ids)) | (Project.id.in_(task_project_ids))
                     | Project.id.in_(member_project_ids)
                     | Project.id.in_(concedidos or [""]))

    if vetados:
        q = q.filter(Project.id.notin_(vetados))
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
        raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    if (
        not current_user.is_superadmin
        and current_user.organization_id
        and project.organization_id
        and project.organization_id != current_user.organization_id
    ):
        raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
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
    # Revision multitenant 2026-11: el limite de proyectos del plan.
    from app.services.organizations_service import exigir_cupo
    exigir_cupo(db, project_data.get("organization_id"), "projects")

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
    except Exception:
        # No bloquear creación de proyecto si collaboration falla, pero dejar rastro
        # diagnosticable: en debug, no en el nivel por defecto.
        logger.debug(
            "create_project: no se pudo crear el equipo/canal de colaboración",
            exc_info=True,
        )

    return project


def apply_project_update(db: Session, project, data: dict) -> None:
    """Apply update data to a project instance — handles optimistic locking and client_name sync."""

    if "version" in data:
        client_version = data.pop("version")
        if project.version is not None and client_version != project.version:
            raise error(409, "conflicto_concurrente", detail=f"Conflicto de edición: el proyecto fue modificado por otro usuario "
                f"(versión esperada {client_version}, versión actual {project.version}). "
                "Recarga y reintenta.")

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
        raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    if project.status == ProjectStatus.cancelled:
        raise ErrorConCodigo("proyecto_ya_cancelado", detail="El proyecto ya esta cancelado")
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
        raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
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
            "external_company": u.external_company if u else None,
            "role": m.role, "allocation_pct": m.allocation_pct,
            "start_date": str(m.start_date) if m.start_date else None,
            "end_date":   str(m.end_date)   if m.end_date   else None,
            "notes": m.notes,
        })
    return result


def add_member_record(db: Session, project_id: str, data: dict):
    """Valida, persiste y retorna un nuevo ProjectMember. Lanza error si ya existe."""

    if not data.get("user_id"):
        raise error(422, "campo_obligatorio", detail="user_id es obligatorio", campo="user_id")
    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == data["user_id"],
    ).first()
    if existing and existing.is_active:
        raise error(409, "ya_es_miembro_proyecto")
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
        raise error(404, "no_encontrado", detail="Miembro no encontrado", que="miembro")
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
    _CERRADO = ("completed", "closed")
    if (getattr(project.status, "value", project.status) in _CERRADO
            and old_status.rsplit(".", 1)[-1] not in _CERRADO):
        # Migración 206 (docs/PIR.md): el cierre programa la PIR del proyecto si es obligatoria.
        from app.services.pir.programacion import al_cerrar_proyecto
        al_cerrar_proyecto(db, project)
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
        if es_asignable(m, k, ("project_id", "user_id")):
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


def proyectos_para_exportar(db: Session, current_user):
    """Los proyectos activos que este usuario puede ver, ordenados por codigo.

    Auditoria 2026-08 (hallazgo 22). Vivia dentro del endpoint del export a CSV,
    y el guardian de la capa API lo cazó — con razon, y merece la nota: la
    consulta estaba escrita **en el mismo sitio donde se decide que columnas
    lleva un fichero**, que es justo la mezcla que hizo falta deshacer en 41
    ficheros. Que el defecto se colara en un endpoint nuevo, escrito en la misma
    auditoria que cerro el hallazgo, dice que el guardian no sobra.

    El ambito sale de `scope_projects_query`, el mismo del listado: un gestor
    exporta lo que ya ve en pantalla, ni una fila mas.
    """
    return (
        scope_projects_query(db.query(Project), db, current_user)
        .filter(Project.is_active == True)  # noqa: E712
        .order_by(Project.code)
        .all()
    )
