from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from typing import Optional, List

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin, require_admin_or_pm
from app.models.user import User, UserRole
from app.models.project import Project, ProjectStatus, ProjectType
from app.schemas import (
    ProjectCreate, ProjectUpdate, ProjectOut, ProjectSummary, ProjectPhaseCreate, ProjectPhaseOut
)
from app.services.project_service import (
    enrich_project,
    enrich_projects_batch,
    empty_enrichment,
    compute_budget_used_pct,
    calculate_evm,
    calculate_evm_portfolio,
    scope_projects_query,
    list_milestones_payload,
    get_project_scoped_or_404,
    get_projects_base_query,
    get_project_by_id,
    save_new_project,
    update_and_save_project,
    cancel_project_record,
    add_project_phase_record,
    get_project_team_users,
    list_members_payload,
    add_member_record,
    get_member_or_404,
    update_member_record,
    remove_member_record,
)

router = APIRouter()


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
    q = get_projects_base_query(db)
    q = scope_projects_query(q, db, current_user)

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
    enrichments = enrich_projects_batch(project_ids, db)

    result = []
    for p in projects:
        enriched = enrichments.get(p.id, empty_enrichment())
        budget_used_pct = compute_budget_used_pct(p, enriched)
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
            start_date=p.start_date,
            end_date_planned=p.end_date_planned,
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
    return list_milestones_payload(db, project_id, date_from, date_to, status)


@router.get("/{project_id}", response_model=ProjectOut, summary="Detalle de proyecto")
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = get_project_scoped_or_404(db, project_id, current_user)
    enriched = enrich_project(project, db)
    out = ProjectOut.model_validate(project)
    out.total_hours_spent = enriched["total_hours_spent"]
    out.total_cost_spent = enriched["total_cost_spent"] if current_user.role in [UserRole.admin] else None
    out.budget_used_pct = compute_budget_used_pct(project, enriched)
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
    project = save_new_project(db, payload, current_user)
    return ProjectOut.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectOut, summary="Actualizar proyecto")
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    project = get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    if current_user.role == UserRole.pm and project.pm_id is not None and project.pm_id != current_user.id:
        raise HTTPException(status_code=403, detail="Solo puedes editar tus proyectos")

    project = update_and_save_project(db, project, payload.model_dump(exclude_unset=True))
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", summary="Cancelar/archivar proyecto")
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = cancel_project_record(db, project_id)
    return result


@router.post("/{project_id}/phases", response_model=ProjectPhaseOut, summary="Añadir fase a proyecto")
def add_phase(
    project_id: str,
    payload: ProjectPhaseCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    phase = add_project_phase_record(db, project_id, payload)
    return phase


@router.get("/{project_id}/team", summary="Equipo activo del proyecto")
def get_project_team(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.schemas import UserPublic
    return [UserPublic.model_validate(m) for m in get_project_team_users(db, project_id)]


# ── Miembros del equipo del proyecto ─────────────────────────────────────────
@router.get("/{project_id}/members", summary="Listar miembros del equipo")
def list_members(project_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    return list_members_payload(db, project_id)


@router.post("/{project_id}/members", summary="Añadir miembro al equipo")
def add_member(project_id: str, data: dict, db: Session = Depends(get_db),
               current_user: User = Depends(require_admin_or_pm)):
    m = add_member_record(db, project_id, data)
    return {"id": m.id, "user_id": m.user_id, "role": m.role,
            "allocation_pct": m.allocation_pct}


@router.patch("/{project_id}/members/{member_id}", summary="Actualizar miembro")
def update_member(project_id: str, member_id: str, data: dict,
                  db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin_or_pm)):
    m = get_member_or_404(db, project_id, member_id)
    m = update_member_record(db, m, data)
    return {"id": m.id, "role": m.role, "allocation_pct": m.allocation_pct}


@router.delete("/{project_id}/members/{member_id}", summary="Eliminar miembro del equipo")
def remove_member(project_id: str, member_id: str, db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin_or_pm)):
    m = get_member_or_404(db, project_id, member_id)
    remove_member_record(db, m)
    return {"ok": True}


# ── EVM ───────────────────────────────────────────────────────────────────────
@router.get("/{project_id}/evm", summary="Earned Value Management — métricas CPI/SPI/EAC/VAC/TCPI")
def get_evm(project_id: str, db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user)):
    result = calculate_evm(project_id, db)
    if result is None:
        raise HTTPException(404, "Proyecto no encontrado")
    return result


@router.get("/evm/portfolio", summary="EVM de toda la cartera activa")
def get_evm_portfolio(db: Session = Depends(get_db),
                      current_user: User = Depends(require_admin_or_pm)):
    return calculate_evm_portfolio(db)

