from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from typing import Optional, List
from datetime import date
import re

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin, require_admin_or_pm
from app.models.user import User, UserRole
from app.models.project import Project, ProjectPhase, ProjectStatus, ProjectType, ProjectMember
from app.models.imputation import Imputation
from app.models.task import Task, TaskStatus
from app.schemas.projects import (
    ProjectCreate, ProjectUpdate, ProjectOut, ProjectSummary, ProjectPhaseCreate, ProjectPhaseOut
)
from app.schemas.users import UserPublic

router = APIRouter()


def _build_code(db: Session) -> str:
    """Generate a unique project code (PRJ-NNNN).

    Uses SELECT FOR UPDATE (PostgreSQL) to lock the MAX row and prevent
    duplicate codes under concurrent inserts. Falls back gracefully on SQLite.
    """
    from app.db.session import is_postgres
    if is_postgres():
        # Lock the table-level aggregate to prevent concurrent reads of the same MAX
        row = db.execute(
            select(func.max(Project.code)).with_for_update()
        ).scalar()
    else:
        row = db.query(func.max(Project.code)).scalar()

    if row:
        m = re.search(r"(\d+)$", row)
        next_num = (int(m.group(1)) + 1) if m else 1
    else:
        next_num = 1
    return f"PRJ-{next_num:04d}"


def _enrich_project(project: Project, db: Session) -> dict:
    """Enrich a single project with aggregated metrics. Use _enrich_projects_batch for lists."""
    return _enrich_projects_batch([project.id], db).get(project.id, _empty_enrichment())


def _empty_enrichment() -> dict:
    return {
        "total_hours_spent": 0.0,
        "total_cost_spent": 0.0,
        "budget_used_pct": 0.0,
        "progress_pct": 0.0,
        "tasks_total": 0,
        "tasks_done": 0,
        "team_size": 0,
    }


def _enrich_projects_batch(project_ids: list, db: Session) -> dict:
    """Return enrichment metrics for multiple projects in a minimal set of queries."""
    if not project_ids:
        return {}

    # Imputation aggregates: hours, cost, team size — all in one query
    imp_rows = db.query(
        Imputation.project_id,
        func.sum(Imputation.hours).label("total_hours"),
        func.sum(Imputation.cost_amount).label("total_cost"),
        func.count(func.distinct(Imputation.user_id)).label("imp_team"),
    ).filter(Imputation.project_id.in_(project_ids)).group_by(Imputation.project_id).all()

    imp_by_project = {r.project_id: r for r in imp_rows}

    # Task counts: total and done — one query each
    task_total_rows = db.query(
        Task.project_id,
        func.count(Task.id).label("cnt"),
    ).filter(Task.project_id.in_(project_ids)).group_by(Task.project_id).all()

    task_done_rows = db.query(
        Task.project_id,
        func.count(Task.id).label("cnt"),
    ).filter(Task.project_id.in_(project_ids), Task.status == TaskStatus.done).group_by(Task.project_id).all()

    task_total = {r.project_id: r.cnt for r in task_total_rows}
    task_done = {r.project_id: r.cnt for r in task_done_rows}

    # Explicit member counts — one query
    member_rows = db.query(
        ProjectMember.project_id,
        func.count(ProjectMember.id).label("cnt"),
    ).filter(ProjectMember.project_id.in_(project_ids)).group_by(ProjectMember.project_id).all()

    member_count = {r.project_id: r.cnt for r in member_rows}

    # Build result dict keyed by project_id
    # We need project budget fields; caller must pass Project objects if needed.
    # This function returns raw aggregates; budget_used_pct is computed per-project below.
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
            "budget_used_pct": 0.0,  # computed after merge with project fields
            "progress_pct": progress,
            "tasks_total": t_total,
            "tasks_done": t_done,
            "team_size": members,
            "_total_hours": total_hours,
            "_total_cost": total_cost,
        }
    return result


@router.get("", response_model=List[ProjectSummary], summary="Listar proyectos")
def list_projects(
    status: Optional[ProjectStatus] = None,
    project_type: Optional[ProjectType] = None,
    pm_id: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Project).options(joinedload(Project.project_manager))

    # Org isolation: non-superadmins only see projects belonging to their organisation
    if not current_user.is_superadmin and current_user.organization_id:
        q = q.filter(Project.organization_id == current_user.organization_id)

    # PMs only see their own projects
    if current_user.role == UserRole.pm:
        q = q.filter(Project.pm_id == current_user.id)
    elif current_user.role in (UserRole.employee, UserRole.subcontractor):
        # Employees/subcontractors see projects they have imputations or tasks on
        project_ids = db.query(func.distinct(Imputation.project_id)).filter(
            Imputation.user_id == current_user.id
        ).subquery()
        from app.models.task import Task as _Task
        task_project_ids = db.query(func.distinct(_Task.project_id)).filter(
            _Task.assignee_id == current_user.id,
            _Task.project_id.isnot(None),
        ).subquery()
        q = q.filter((Project.id.in_(project_ids)) | (Project.id.in_(task_project_ids)))

    if status:
        q = q.filter(Project.status == status)
    if project_type:
        q = q.filter(Project.project_type == project_type)
    if pm_id:
        q = q.filter(Project.pm_id == pm_id)
    if search:
        q = q.filter(
            (Project.name.ilike(f"%{search}%")) |
            (Project.code.ilike(f"%{search}%")) |
            (Project.client_name.ilike(f"%{search}%"))
        )

    total = q.count()
    projects = q.offset((page - 1) * page_size).limit(page_size).all()

    # Batch-enrich all projects in a fixed number of queries instead of N×6
    project_ids = [p.id for p in projects]
    enrichments = _enrich_projects_batch(project_ids, db)

    result = []
    for p in projects:
        enriched = enrichments.get(p.id, _empty_enrichment())
        total_cost = enriched["_total_cost"]
        total_hours = enriched["_total_hours"]
        if p.budget_amount and p.budget_amount > 0:
            budget_used_pct = round((total_cost / p.budget_amount) * 100, 1)
        elif p.budget_hours and p.budget_hours > 0:
            budget_used_pct = round((total_hours / p.budget_hours) * 100, 1)
        else:
            budget_used_pct = 0.0
        result.append(ProjectSummary(
            id=p.id, code=p.code, name=p.name,
            project_type=p.project_type, status=p.status,
            risk_level=p.risk_level,
            pm_name=p.project_manager.full_name if p.project_manager else None,
            client_name=p.client_name,
            department=p.department,
            budget_amount=p.budget_amount,
            total_cost_spent=enriched["total_cost_spent"],
            budget_used_pct=budget_used_pct,
            progress_pct=enriched["progress_pct"],
            team_size=enriched["team_size"],
        ))
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
    return result


@router.get("/milestones", summary="Milestones cross-proyecto con filtro de fecha")
def list_all_milestones(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    status:    Optional[str] = None,
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista milestones de todos los proyectos con filtros opcionales.
    Usado por el Calendario global para mostrar fechas clave.
    """
    from app.models.financial import ProjectMilestone

    q = db.query(ProjectMilestone)

    if project_id:
        q = q.filter(ProjectMilestone.project_id == project_id)
    if date_from:
        try:
            df = date.fromisoformat(date_from)
            q  = q.filter(ProjectMilestone.due_date >= df)
        except ValueError:
            pass
    if date_to:
        try:
            dt = date.fromisoformat(date_to)
            q  = q.filter(ProjectMilestone.due_date <= dt)
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


@router.get("/{project_id}", response_model=ProjectOut, summary="Detalle de proyecto")
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).options(
        joinedload(Project.project_manager),
        joinedload(Project.phases),
    ).filter(Project.id == project_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    # Org isolation: prevent cross-tenant access
    if (
        not current_user.is_superadmin
        and current_user.organization_id
        and project.organization_id
        and project.organization_id != current_user.organization_id
    ):
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    enriched = _enrich_project(project, db)
    out = ProjectOut.model_validate(project)
    out.total_hours_spent = enriched["total_hours_spent"]
    out.total_cost_spent = enriched["total_cost_spent"] if current_user.role in [UserRole.admin] else None
    # Compute budget_used_pct using the project's own budget fields
    total_cost = enriched["_total_cost"]
    total_hours = enriched["_total_hours"]
    if project.budget_amount and project.budget_amount > 0:
        out.budget_used_pct = round((total_cost / project.budget_amount) * 100, 1)
    elif project.budget_hours and project.budget_hours > 0:
        out.budget_used_pct = round((total_hours / project.budget_hours) * 100, 1)
    else:
        out.budget_used_pct = 0.0
    out.progress_pct = enriched["progress_pct"]
    out.team_size = enriched["team_size"]
    out.tasks_total = enriched["tasks_total"]
    out.tasks_done = enriched["tasks_done"]
    return out


@router.post("", response_model=ProjectOut, summary="Crear proyecto")
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    phases_data = payload.phases or []
    project_data = payload.model_dump(exclude={"phases"})
    code = project_data.pop("code", None) or _build_code(db)
    if current_user.role == UserRole.pm and not project_data.get("pm_id"):
        project_data["pm_id"] = current_user.id
    # Auto-assign organisation from creating user (tenant isolation)
    if not project_data.get("organization_id") and current_user.organization_id:
        project_data["organization_id"] = current_user.organization_id
    project = Project(**project_data, code=code, created_by=current_user.id)
    db.add(project)
    try:
        db.flush()  # Get ID before adding phases
    except IntegrityError as e:
        db.rollback()
        if "UNIQUE" in str(e).upper() or "unique" in str(e).lower():
            # Concurrent insert with same code — regenerate and retry once
            code = _build_code(db)
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

    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectOut, summary="Actualizar proyecto")
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    # PM can only edit their own projects (or projects with no PM assigned)
    if current_user.role == UserRole.pm and project.pm_id is not None and project.pm_id != current_user.id:
        raise HTTPException(status_code=403, detail="Solo puedes editar tus proyectos")

    data = payload.model_dump(exclude_unset=True)

    # P1-5: Optimistic locking — reject stale updates
    if "version" in data:
        client_version = data.pop("version")
        if project.version is not None and client_version != project.version:
            raise HTTPException(
                status_code=409,
                detail=f"Conflicto de edición: el proyecto fue modificado por otro usuario (versión esperada {client_version}, versión actual {project.version}). Recarga y reintenta.",
            )

    # Validar exclusividad de client_id: un proyecto solo puede pertenecer a un cliente
    if "client_id" in data and data["client_id"] and data["client_id"] != project.client_id:
        from app.models.clients import Client
        # Varios proyectos al mismo cliente está bien; sólo actualizamos client_name
        if project.client_id and project.client_id != data["client_id"]:
            pass  # el cambio de cliente se permite siempre
        # Actualizar client_name automáticamente si se vincula a un Client entity
        new_client = db.query(Client).filter(Client.id == data["client_id"]).first()
        if new_client and "client_name" not in data:
            data["client_name"] = new_client.name

    for field, value in data.items():
        setattr(project, field, value)

    # Increment version on every successful update
    project.version = (project.version or 1) + 1
    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", summary="Cancelar/archivar proyecto")
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    project.status = ProjectStatus.cancelled
    db.commit()
    return {"message": "Proyecto cancelado"}


@router.post("/{project_id}/phases", response_model=ProjectPhaseOut, summary="Añadir fase a proyecto")
def add_phase(
    project_id: str,
    payload: ProjectPhaseCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    phase = ProjectPhase(**payload.model_dump(), project_id=project_id)
    db.add(phase)
    db.commit()
    db.refresh(phase)
    return phase


@router.get("/{project_id}/team", summary="Equipo activo del proyecto")
def get_project_team(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.user import User as UserModel
    members = db.query(UserModel).join(
        Imputation, Imputation.user_id == UserModel.id
    ).filter(
        Imputation.project_id == project_id
    ).distinct().all()

    return [UserPublic.model_validate(m) for m in members]


# ── Miembros del equipo del proyecto ─────────────────────────────────────────
@router.get("/{project_id}/members", summary="Listar miembros del equipo")
def list_members(project_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    members = db.query(ProjectMember).options(joinedload(ProjectMember.user)).filter(
        ProjectMember.project_id == project_id
    ).all()
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


@router.post("/{project_id}/members", summary="Añadir miembro al equipo")
def add_member(project_id: str, data: dict, db: Session = Depends(get_db),
               current_user: User = Depends(require_admin_or_pm)):
    if not data.get("user_id"):
        raise HTTPException(status_code=422, detail="user_id es obligatorio")
    # Evitar duplicados
    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id    == data["user_id"]
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="El usuario ya es miembro del proyecto")
    m = ProjectMember(
        project_id     = project_id,
        user_id        = data["user_id"],
        role           = data.get("role", "developer"),
        allocation_pct = data.get("allocation_pct", 100),
        start_date     = data.get("start_date"),
        end_date       = data.get("end_date"),
        notes          = data.get("notes"),
    )
    db.add(m); db.commit(); db.refresh(m)
    return {"id": m.id, "user_id": m.user_id, "role": m.role,
            "allocation_pct": m.allocation_pct}


@router.patch("/{project_id}/members/{member_id}", summary="Actualizar miembro")
def update_member(project_id: str, member_id: str, data: dict,
                  db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin_or_pm)):
    m = db.query(ProjectMember).filter(
        ProjectMember.id == member_id,
        ProjectMember.project_id == project_id
    ).first()
    if not m: raise HTTPException(status_code=404, detail="Miembro no encontrado")
    for k, v in data.items():
        if hasattr(m, k): setattr(m, k, v)
    db.commit(); db.refresh(m)
    return {"id": m.id, "role": m.role, "allocation_pct": m.allocation_pct}


@router.delete("/{project_id}/members/{member_id}", summary="Eliminar miembro del equipo")
def remove_member(project_id: str, member_id: str, db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin_or_pm)):
    m = db.query(ProjectMember).filter(
        ProjectMember.id == member_id,
        ProjectMember.project_id == project_id
    ).first()
    if not m: raise HTTPException(status_code=404, detail="Miembro no encontrado")
    db.delete(m); db.commit()
    return {"ok": True}


# ── EVM ───────────────────────────────────────────────────────────────────────
@router.get("/{project_id}/evm", summary="Earned Value Management — métricas CPI/SPI/EAC/VAC/TCPI")
def get_evm(project_id: str, db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user)):
    """
    Calcula los indicadores EVM estándar para un proyecto:
    - BAC  Budget at Completion (presupuesto total)
    - PV   Planned Value (BCWS)  — valor planificado a la fecha de hoy
    - EV   Earned Value  (BCWP)  — valor del trabajo completado
    - AC   Actual Cost   (ACWP)  — coste real incurrido
    - CPI  Cost Performance Index          = EV / AC
    - SPI  Schedule Performance Index      = EV / PV
    - CV   Cost Variance                   = EV - AC
    - SV   Schedule Variance               = EV - PV
    - EAC  Estimate at Completion          = BAC / CPI
    - ETC  Estimate to Complete            = EAC - AC
    - VAC  Variance at Completion          = BAC - EAC
    - TCPI To-Complete Performance Index   = (BAC - EV) / (BAC - AC)
    """
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(404, "Proyecto no encontrado")

    today = date.today()

    # ── BAC: budget_amount or derive from estimated hours × avg rate ─────────
    bac = proj.budget_amount or 0.0

    # If no budget_amount, derive from tasks estimated hours × project avg cost/h
    if bac == 0:
        total_est = db.query(func.sum(Task.estimated_hours)).filter(
            Task.project_id == project_id
        ).scalar() or 0.0
        avg_rate = db.query(func.avg(Imputation.hourly_rate_snapshot)).filter(
            Imputation.project_id == project_id,
            Imputation.hourly_rate_snapshot.isnot(None),
        ).scalar() or 0.0
        bac = total_est * avg_rate

    # ── AC: actual cost from imputations ────────────────────────────────────
    ac_cost = db.query(func.sum(Imputation.cost_amount)).filter(
        Imputation.project_id == project_id,
        Imputation.cost_amount.isnot(None),
    ).scalar() or 0.0

    # Fallback: hours × rate snapshot when cost_amount not stored
    if ac_cost == 0:
        rows = db.query(Imputation.hours, Imputation.hourly_rate_snapshot).filter(
            Imputation.project_id == project_id
        ).all()
        ac_cost = sum((r.hours * r.hourly_rate_snapshot) for r in rows
                      if r.hourly_rate_snapshot) or 0.0

    ac = ac_cost

    # ── EV: earned value = BAC × %complete ─────────────────────────────────
    tasks_total = db.query(
        func.count(Task.id).label("cnt"),
        func.sum(Task.estimated_hours).label("est")
    ).filter(Task.project_id == project_id).first()

    tasks_done = db.query(
        func.count(Task.id).label("cnt"),
        func.sum(Task.estimated_hours).label("est")
    ).filter(
        Task.project_id == project_id,
        Task.status == TaskStatus.done
    ).first()

    total_est_hours = tasks_total.est or 0.0
    done_est_hours  = tasks_done.est or 0.0
    pct_complete = (done_est_hours / total_est_hours) if total_est_hours > 0 else 0.0
    ev = bac * pct_complete

    # ── PV: planned value = BAC × time_elapsed / total_duration ─────────────
    start = proj.start_date
    end   = proj.end_date_planned
    if start and end and end > start:
        total_days   = (end - start).days
        elapsed_days = max(0, (today - start).days)
        pct_time     = min(elapsed_days / total_days, 1.0)
    else:
        pct_time = None  # No schedule data — PV/SPI cannot be computed reliably

    pv = bac * pct_time if pct_time is not None else None

    # ── Derived metrics ─────────────────────────────────────────────────────
    cpi  = round(ev / ac,   4) if ac  > 0 else None
    spi  = round(ev / pv,   4) if (pv is not None and pv > 0) else None
    cv   = round(ev - ac,   2)
    sv   = round(ev - pv,   2) if pv is not None else None
    eac  = round(bac / cpi, 2) if cpi and cpi > 0 else None
    etc  = round(eac - ac,  2) if eac is not None else None
    vac  = round(bac - eac, 2) if eac is not None else None
    tcpi_denom = (bac - ac)
    tcpi = round((bac - ev) / tcpi_denom, 4) if tcpi_denom != 0 else None

    # ── Health signal ───────────────────────────────────────────────────────
    # Green: CPI≥0.9 and SPI≥0.9 / Yellow: one < 0.9 / Red: both < 0.85
    def _health(c, s):
        if c is None or s is None: return "grey"
        if c >= 0.9 and s >= 0.9:  return "green"
        if c < 0.85 or s < 0.85:   return "red"
        return "yellow"

    return {
        "project_id":   project_id,
        "project_name": proj.name,
        "currency":     "EUR",
        "bac":   round(bac, 2),
        "pv":    round(pv, 2) if pv is not None else None,
        "ev":    round(ev, 2),
        "ac":    round(ac, 2),
        "cpi":   cpi,
        "spi":   spi,
        "cv":    cv,
        "sv":    sv,
        "eac":   eac,
        "etc":   etc,
        "vac":   vac,
        "tcpi":  tcpi,
        "pct_complete": round(pct_complete * 100, 1),
        "pct_time_elapsed": round(pct_time * 100, 1) if pct_time is not None else None,
        "has_schedule": pct_time is not None,
        "total_tasks": tasks_total.cnt or 0,
        "done_tasks":  tasks_done.cnt or 0,
        "health": _health(cpi, spi),
        "start_date": proj.start_date.isoformat() if proj.start_date else None,
        "planned_end": proj.end_date_planned.isoformat() if proj.end_date_planned else None,
    }


@router.get("/evm/portfolio", summary="EVM de toda la cartera activa")
def get_evm_portfolio(db: Session = Depends(get_db),
                      current_user: User = Depends(require_admin_or_pm)):
    """Resumen EVM de todos los proyectos activos para vista de cartera."""
    active = db.query(Project).filter(
        Project.status.in_([ProjectStatus.active, ProjectStatus.on_hold])
    ).all()

    results = []
    today = date.today()
    for proj in active:
        bac = proj.budget_amount or 0.0
        if bac == 0:
            total_est = db.query(func.sum(Task.estimated_hours)).filter(
                Task.project_id == proj.id
            ).scalar() or 0.0
            avg_rate = db.query(func.avg(Imputation.hourly_rate_snapshot)).filter(
                Imputation.project_id == proj.id,
                Imputation.hourly_rate_snapshot.isnot(None),
            ).scalar() or 0.0
            bac = total_est * avg_rate

        ac = db.query(func.sum(Imputation.cost_amount)).filter(
            Imputation.project_id == proj.id,
            Imputation.cost_amount.isnot(None),
        ).scalar() or 0.0

        total_est_h = db.query(func.sum(Task.estimated_hours)).filter(Task.project_id == proj.id).scalar() or 0.0
        done_est_h  = db.query(func.sum(Task.estimated_hours)).filter(
            Task.project_id == proj.id, Task.status == TaskStatus.done
        ).scalar() or 0.0
        pct = (done_est_h / total_est_h) if total_est_h > 0 else 0.0
        ev  = bac * pct

        start, end = proj.start_date, proj.end_date_planned
        if start and end and end > start:
            pct_t = min((today - start).days / (end - start).days, 1.0)
        else:
            pct_t = pct
        pv = bac * max(pct_t, 0)

        cpi = round(ev / ac, 3) if ac > 0 else None
        spi = round(ev / pv, 3) if pv > 0 else None
        eac = round(bac / cpi, 2) if cpi and cpi > 0 else None

        def _h(c, s):
            if c is None or s is None: return "grey"
            if c >= 0.9 and s >= 0.9:  return "green"
            if c < 0.85 or s < 0.85:   return "red"
            return "yellow"

        results.append({
            "project_id": proj.id, "project_name": proj.name,
            "bac": round(bac, 2), "ac": round(ac, 2),
            "ev": round(ev, 2), "pv": round(pv, 2),
            "cpi": cpi, "spi": spi, "eac": eac,
            "pct_complete": round(pct * 100, 1),
            "health": _h(cpi, spi),
        })

    return sorted(results, key=lambda r: r["health"] == "red", reverse=True)
