"""
raci — Market-leader feature expansion:
  1. RACI Matrix         GET/PUT /projects/{id}/raci
                         DELETE  /projects/{id}/raci/{entry_id}
  2. Sprint Retrospective GET  /projects/{pid}/sprints/{sid}/retrospective
                          PUT  /projects/{pid}/sprints/{sid}/retrospective
  3. Burnout Risk Monitor GET  /resources/burnout-risk
                          POST /resources/burnout-risk/compute
  4. Project Changelog    GET  /projects/{id}/changelog
                          POST /projects/{id}/changelog          (manual entry)
                          POST /projects/{id}/changelog/generate (auto from tasks)
                          PATCH/DELETE /projects/{id}/changelog/{entry_id}
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Request, Response
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, datetime
from app.core.ratelimit import limiter
from pydantic import BaseModel
from app.schemas.raci import RACIEntryIn, RACIBatchIn, RetroNotesIn, ChangelogEntryIn, ChangelogEntryPatch, UATCaseIn

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User
import app.services.raci_service as _svc


def _http(e: ValueError) -> HTTPException:
    msg = str(e)
    if msg.startswith("422:"):
        return HTTPException(422, msg[4:])
    if "no encontrado" in msg.lower() or "not found" in msg.lower():
        return HTTPException(404, msg)
    return HTTPException(400, msg)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# 1. RACI MATRIX
# ═══════════════════════════════════════════════════════════════════════════════



@router.get("/projects/{project_id}/raci", summary="RACI Matrix del proyecto",
            tags=["v25 — RACI"])
def get_project_raci(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    response: Response = None,
):
    if response is not None:
        response.headers["x-api-version"] = "1"
        response.headers["x-api-deprecated"] = "true"
        response.headers["deprecation"] = "true"
    try:
        return _svc.get_project_raci(project_id, db)
    except ValueError as e:
        raise _http(e)


@router.put("/projects/{project_id}/raci", summary="Guardar/actualizar entradas RACI (batch upsert)",
            tags=["v25 — RACI"])
def upsert_raci(
    project_id: str,
    payload: RACIBatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
    response: Response = None,
):
    if response is not None:
        response.headers["x-api-version"] = "1"
        response.headers["x-api-deprecated"] = "true"
        response.headers["deprecation"] = "true"
@router.put("/projects/{project_id}/raci", summary="Guardar/actualizar entradas RACI (batch upsert)",
            tags=["v25 — RACI"])
def upsert_raci(
    project_id: str,
    payload: RACIBatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
    response: Response = None,
):
    if response is not None:
        response.headers["x-api-version"] = "1"
        response.headers["x-api-deprecated"] = "true"
        response.headers["deprecation"] = "true"
    try:
        return _svc.upsert_raci(project_id, payload.entries, db)
    except ValueError as e:
        raise _http(e)


@router.delete("/projects/{project_id}/raci/{entry_id}", summary="Eliminar entrada RACI",
               status_code=204, tags=["v25 — RACI"])
def delete_raci_entry(
    project_id: str,
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
    response: Response = None,
):
    if response is not None:
        response.headers["x-api-version"] = "1"
        response.headers["x-api-deprecated"] = "true"
        response.headers["deprecation"] = "true"
    try:
        _svc.delete_raci_entry(project_id, entry_id, db)
    except ValueError as e:
        raise _http(e)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SPRINT RETROSPECTIVE AI
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/projects/{project_id}/sprints/{sprint_id}/retrospective",
    summary="Insights de retrospectiva del sprint (AI algorítmico)",
    tags=["v25 — Sprint Retrospective"],
)
def get_sprint_retrospective(
    project_id: str,
    sprint_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    response: Response = None,
):
    if response is not None:
        response.headers["x-api-version"] = "1"
        response.headers["x-api-deprecated"] = "true"
        response.headers["deprecation"] = "true"
    try:
        return _svc.get_sprint_retrospective(project_id, sprint_id, db)
    except ValueError as e:
        raise _http(e)




@router.put(
    "/projects/{project_id}/sprints/{sprint_id}/retrospective",
    summary="Guardar notas de retrospectiva",
    tags=["v25 — Sprint Retrospective"],
)
def save_sprint_retrospective(
    project_id: str,
    sprint_id: str,
    payload: RetroNotesIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _svc.save_sprint_retrospective(project_id, sprint_id, payload, current_user.id, db)
    except ValueError as e:
        raise _http(e)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. BURNOUT RISK MONITOR
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/resources/burnout-risk", summary="Monitor de riesgo de burnout del equipo",
            tags=["v25 — Burnout Monitor"])
def get_burnout_risk(
    department: Optional[str] = Query(None),
    min_risk_level: Optional[str] = Query(None, description="green|yellow|orange|red"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.get_burnout_risk(department, min_risk_level, db)


@router.post("/resources/burnout-risk/compute", summary="Recalcular y persistir snapshots de burnout",
             tags=["v25 — Burnout Monitor"])
@limiter.limit("10/minute")
def compute_and_save_burnout_snapshots(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.compute_and_save_burnout_snapshots(db)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. PROJECT CHANGELOG / RELEASE NOTES
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/projects/{project_id}/changelog", summary="Changelog del proyecto",
            tags=["v25 — Changelog"])
def get_project_changelog(
    project_id: str,
    entry_type: Optional[str] = Query(None),
    since: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _svc.get_project_changelog(project_id, entry_type, since, db)
    except ValueError as e:
        raise _http(e)


@router.post("/projects/{project_id}/changelog", summary="Añadir entrada manual al changelog",
             tags=["v25 — Changelog"])
def create_changelog_entry(
    project_id: str,
    payload: ChangelogEntryIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.create_changelog_entry(project_id, payload, current_user.id, db)
    except ValueError as e:
        raise _http(e)


@router.post("/projects/{project_id}/changelog/generate",
             summary="Generar changelog automático desde tareas completadas (últimas N semanas)",
             tags=["v25 — Changelog"])
def generate_changelog(
    project_id: str,
    weeks: int = Body(default=2, embed=True, ge=1, le=52),
    version_tag: Optional[str] = Body(default=None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.generate_changelog(project_id, weeks, version_tag, current_user.id, db)
    except ValueError as e:
        raise _http(e)


@router.patch("/projects/{project_id}/changelog/{entry_id}",
              summary="Editar entrada del changelog",
              tags=["v25 — Changelog"])
def update_changelog_entry(
    project_id: str,
    entry_id: str,
    payload: ChangelogEntryPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.update_changelog_entry(project_id, entry_id, payload, db)
    except ValueError as e:
        raise _http(e)


@router.delete("/projects/{project_id}/changelog/{entry_id}",
               summary="Eliminar entrada del changelog",
               status_code=204, tags=["v25 — Changelog"])
def delete_changelog_entry(
    project_id: str,
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        _svc.delete_changelog_entry(project_id, entry_id, db)
    except ValueError as e:
        raise _http(e)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. UAT CASES
# ═══════════════════════════════════════════════════════════════════════════════



@router.get("/projects/{project_id}/uat",
            summary="Lista de casos UAT del proyecto",
            tags=["v25 — UAT"])
def list_uat_cases(
    project_id: str,
    status: Optional[str] = Query(None),
    task_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.list_uat_cases(project_id, status, task_id, db)


@router.post("/projects/{project_id}/uat",
             summary="Crear caso UAT",
             status_code=201, tags=["v25 — UAT"])
def create_uat_case(
    project_id: str,
    payload: UATCaseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.create_uat_case(project_id, payload, db)


@router.patch("/projects/{project_id}/uat/{case_id}",
              summary="Actualizar caso UAT",
              tags=["v25 — UAT"])
def update_uat_case(
    project_id: str,
    case_id: str,
    payload: UATCaseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _svc.update_uat_case(project_id, case_id, payload, db)
    except ValueError as e:
        raise _http(e)


@router.delete("/projects/{project_id}/uat/{case_id}",
               summary="Eliminar caso UAT",
               status_code=204, tags=["v25 — UAT"])
def delete_uat_case(
    project_id: str,
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        _svc.delete_uat_case(project_id, case_id, db)
    except ValueError as e:
        raise _http(e)


@router.get("/projects/{project_id}/uat/export",
            summary="Exportar UAT como texto estructurado para cliente",
            tags=["v25 — UAT"])
def export_uat_report(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    response: Response = None,
):
    if response is not None:
        response.headers["x-api-version"] = "1"
        response.headers["x-api-deprecated"] = "true"
        response.headers["deprecation"] = "true"
    try:
        return _svc.export_uat_report(project_id, db)
    except ValueError as e:
        raise _http(e)
