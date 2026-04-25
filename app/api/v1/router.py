"""
API v1 top-level router.

All endpoint modules are aggregated through five domain sub-routers defined
in app/api/v1/routers/.  Adding a new module means editing the appropriate
domain file rather than this orchestrator.

  core       — Auth, users, primary workflow modules
  delivery   — Project delivery tools, resources, documents, reporting
  ai_domain  — All AI/ML stack modules
  platform   — Integrations, security, compliance, admin tooling
  framework  — Health checks, websockets, notifications
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.core.deps import require_admin_or_pm
from app.db.session import get_db

from app.api.v1.routers import core, delivery, ai_domain, platform, framework

# ── Legacy compat imports (used only for the /projects/* alias block below) ───
from app.api.v1.endpoints import tasks, milestones, sprints, epics, issue_types
from app.api.v1.endpoints.cmdb import SprintPlanIn
import app.services.cmdb_service as cmdb_svc

api_router = APIRouter()

# ── Legacy compatibility aliases ──────────────────────────────────────────────
# Register before domain routers so static /projects/* aliases are not shadowed
# by dynamic /projects/{project_id} routes.
api_router.include_router(tasks.router,       prefix="/projects/tasks",        tags=["Projects"])
api_router.include_router(milestones.router,  prefix="/projects/milestones",   tags=["Projects"])
api_router.include_router(sprints.router,     prefix="/projects/sprints",      tags=["Projects"])
api_router.include_router(epics.router,       prefix="/projects/epics",        tags=["Projects"])
api_router.include_router(issue_types.router, prefix="/projects/issue-types",  tags=["Projects"])


@api_router.get("/projects/epics", tags=["Projects"])
def _legacy_projects_epics_alias(_: dict = Depends(get_current_user)):
  """Legacy alias placeholder kept for backward compatibility."""
  return []


@api_router.get("/projects/issue-types", tags=["Projects"])
def _legacy_projects_issue_types_alias(_: dict = Depends(get_current_user)):
  """Legacy alias placeholder kept for backward compatibility."""
  return []

api_router.include_router(core.router)
api_router.include_router(delivery.router)
api_router.include_router(ai_domain.router)
api_router.include_router(platform.router)
api_router.include_router(framework.router)


@api_router.post("/sprint-plans/generate", tags=["CMDB"])
def _legacy_generate_sprint_plan(
  p: SprintPlanIn,
  db: Session = Depends(get_db),
  cu=Depends(require_admin_or_pm),
):
  return cmdb_svc.generate_sprint_plan(
    p.project_id, p.sprint_id, p.name, p.team_capacity, p.priorities or [], cu.id, db
  )


@api_router.get("/sprint-plans/{project_id}", tags=["CMDB"])
def _legacy_list_sprint_plans(
  project_id: str,
  db: Session = Depends(get_db),
  cu=Depends(get_current_user),
):
  return cmdb_svc.list_sprint_plans(project_id, db)


@api_router.patch("/sprint-plans/{plan_id}/status", tags=["CMDB"])
def _legacy_update_plan_status(
  plan_id: str,
  status: str,
  db: Session = Depends(get_db),
  cu=Depends(require_admin_or_pm),
):
  return cmdb_svc.update_sprint_plan_status(plan_id, status, db)


@api_router.delete("/sprint-plans/{plan_id}", tags=["CMDB"])
def _legacy_delete_sprint_plan(
  plan_id: str,
  db: Session = Depends(get_db),
  cu=Depends(require_admin_or_pm),
):
  return cmdb_svc.delete_sprint_plan(plan_id, db)

