"""
Git integration — bidirectional GitHub/GitLab webhook handler + query API.

Inbound webhooks:
  POST /git/webhooks/github  — GitHub PR + deployment events
  POST /git/webhooks/gitlab  — GitLab MR + deployment events

Query:
  GET  /git/pull-requests            — list PRs (filter by task/project/status)
  GET  /git/pull-requests/{pr_id}    — PR detail
  GET  /git/deployments              — list deployments
  GET  /git/tasks/{task_id}/pr-status — summary for a task modal

Task linkage convention (auto-detect):
  Branch name or PR title must contain a task code like "PROJ-123" or "#123".
  The system looks up matching tasks and links automatically.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_admin, require_admin_or_pm
from app.core.async_db import run_db
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.services.git_service import (
    get_pull_request,
    get_task,
    get_task_pr_status,
    list_deployments as svc_list_deployments,
    list_pull_requests,
    process_github_webhook,
    process_gitlab_webhook,
    suggest_branch_name,
    verify_github_signature as _verify_github_signature,
    verify_gitlab_token as _verify_gitlab_token,
)

router = APIRouter()
_logger = logging.getLogger(__name__)


# ── Webhooks ───────────────────────────────────────────────────────────────────
#
# Revisión 2026-11. Antes había una sola dirección y un solo secreto para toda
# la instalación: el evento no decía de qué empresa era, las filas quedaban sin
# empresa y el código de la tarea se buscaba en todas (un PR fusionado en una
# cerraba la tarea homónima de otra). Ahora cada empresa tiene su dirección
# `/git/webhooks/{github|gitlab}/{slug}` con su propio secreto (Credenciales →
# Inbound webhooks, guardado PARA esa empresa) y el evento se procesa como ella.
# Las direcciones sin empresa sólo valen si la instalación tiene una única.

def _empresa(db: Session, slug: Optional[str]) -> str:
    from app.services import git_service as gs
    org = gs.empresa_por_slug(db, slug) if slug else gs.unica_empresa(db)
    if not org:
        raise HTTPException(404 if slug else 409,
                            "Empresa no encontrada" if slug else
                            "Hay varias empresas: usa /git/webhooks/{proveedor}/{empresa}")
    return org


async def _github(request: Request, evento: str, firma: str, db: Session, slug: Optional[str]):
    from app.services import git_service as gs
    org = _empresa(db, slug)
    secreto = gs.secreto_de_la_empresa(db, "github", org) if slug else None
    if slug and not secreto:
        raise HTTPException(403, "La empresa no tiene secreto de GitHub (Credenciales → Inbound webhooks)")
    body = await request.body()
    if not _verify_github_signature(body, firma, secreto):
        raise HTTPException(403, "Invalid GitHub webhook signature")
    try:
        payload = await request.json()
    except Exception:
        _logger.warning("GitHub webhook rejected: invalid JSON payload event=%s", evento, exc_info=True)
        raise HTTPException(400, "Invalid JSON payload")
    try:
        await run_db(process_github_webhook, db, evento, payload, org)
    except Exception:
        _logger.exception("GitHub webhook processing failed event=%s", evento)
        raise HTTPException(500, "Error procesando webhook GitHub")  # GitHub reintenta
    return {"status": "ok"}


async def _gitlab(request: Request, token: str, db: Session, slug: Optional[str]):
    from app.services import git_service as gs
    org = _empresa(db, slug)
    secreto = gs.secreto_de_la_empresa(db, "gitlab", org) if slug else None
    if slug and not secreto:
        raise HTTPException(403, "La empresa no tiene secreto de GitLab (Credenciales → Inbound webhooks)")
    if not _verify_gitlab_token(token, secreto):
        raise HTTPException(403, "Invalid GitLab webhook token")
    try:
        payload = await request.json()
    except Exception:
        _logger.warning("GitLab webhook rejected: invalid JSON payload", exc_info=True)
        raise HTTPException(400, "Invalid JSON payload")
    try:
        await run_db(process_gitlab_webhook, db, payload.get("object_kind", ""), payload, org)
    except Exception:
        _logger.exception("GitLab webhook processing failed kind=%s", payload.get("object_kind"))
        raise HTTPException(500, "Error procesando webhook GitLab")
    return {"status": "ok"}


@router.post("/webhooks/github/{slug}", summary="Eventos de GitHub de una empresa (PR / despliegue)")
async def github_webhook_empresa(slug: str, request: Request, x_github_event: str = Header(default=""),
                                 x_hub_signature_256: str = Header(default=""), db: Session = Depends(get_db)):
    return await _github(request, x_github_event, x_hub_signature_256, db, slug)


@router.post("/webhooks/github", summary="Eventos de GitHub (sólo instalaciones de una empresa)")
async def github_webhook(request: Request, x_github_event: str = Header(default=""),
                         x_hub_signature_256: str = Header(default=""), db: Session = Depends(get_db)):
    return await _github(request, x_github_event, x_hub_signature_256, db, None)


@router.post("/webhooks/gitlab/{slug}", summary="Eventos de GitLab de una empresa (MR / despliegue)")
async def gitlab_webhook_empresa(slug: str, request: Request, x_gitlab_token: str = Header(default=""),
                                 db: Session = Depends(get_db)):
    return await _gitlab(request, x_gitlab_token, db, slug)


@router.post("/webhooks/gitlab", summary="Eventos de GitLab (sólo instalaciones de una empresa)")
async def gitlab_webhook(request: Request, x_gitlab_token: str = Header(default=""), db: Session = Depends(get_db)):
    return await _gitlab(request, x_gitlab_token, db, None)


@router.get("/webhooks", summary="Direcciones de webhook de mi empresa y si tienen secreto")
def mis_webhooks(db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    from app.services.git_service import direcciones_de_la_empresa
    return APIResponse.ok(data=direcciones_de_la_empresa(db, current_user.organization_id))


# ── Query endpoints ──────────────────────────────────────────────────────────

class PROut(BaseModel):
    id: int
    provider: str
    repo_full_name: str
    pr_number: int
    pr_title: Optional[str]
    pr_url: Optional[str]
    author_login: Optional[str]
    source_branch: Optional[str]
    target_branch: Optional[str]
    status: str
    task_id: Optional[int]
    project_id: Optional[int]
    merged_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class DeployOut(BaseModel):
    id: int
    provider: str
    repo_full_name: Optional[str]
    environment: Optional[str]
    deploy_url: Optional[str]
    status: str
    sha: Optional[str]
    task_id: Optional[int]
    deployed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/pull-requests", response_model=APIListResponse[PROut], summary="Listar Pull Requests")
def list_prs(
    task_id:    Optional[int] = Query(None),
    project_id: Optional[int] = Query(None),
    status:     Optional[str] = Query(None),
    provider:   Optional[str] = Query(None),
    limit:      int           = Query(50, le=200),
    page:       int           = Query(1, ge=1),
    page_size:  int           = Query(50, ge=1, le=200),
    db:         Session       = Depends(get_db),
    _:          User          = Depends(get_current_user),
):
    items = list_pull_requests(db, task_id=task_id, project_id=project_id, status=status, provider=provider, limit=limit)
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


@router.get("/pull-requests/{pr_id}", response_model=APIResponse[PROut], summary="Detalle de PR")
def get_pr(
    pr_id: int,
    db:    Session = Depends(get_db),
    _:     User    = Depends(get_current_user),
):
    pr = get_pull_request(db, pr_id)
    if not pr:
        raise HTTPException(404, "Pull request not found")
    return APIResponse.ok(data=pr)


@router.get("/deployments", response_model=APIListResponse[DeployOut], summary="Listar deployments")
def list_deployments(
    task_id:    Optional[int] = Query(None),
    project_id: Optional[int] = Query(None),
    status:     Optional[str] = Query(None),
    limit:      int           = Query(50, le=200),
    page:       int           = Query(1, ge=1),
    page_size:  int           = Query(50, ge=1, le=200),
    db:         Session       = Depends(get_db),
    _:          User          = Depends(get_current_user),
):
    items = svc_list_deployments(db, task_id=task_id, project_id=project_id, status=status, limit=limit)
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


@router.post("/tasks/{task_id}/branch", summary="Sugerir nombre de rama para una tarea")
def suggest_branch(
    task_id: int,
    db:      Session = Depends(get_db),
    _:       User    = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: integracion con el repositorio
):
    task = get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return APIResponse.ok(data=suggest_branch_name(task))


@router.get("/tasks/{task_id}/pr-status", summary="Estado de PR/Deploy para una tarea")
def task_pr_status(
    task_id: int,
    db:      Session = Depends(get_db),
    _:       User    = Depends(get_current_user),
):
    """Returns the latest PR and latest deployment linked to a task."""
    pr, dep = get_task_pr_status(db, task_id)

    return APIResponse.ok(data={
        "task_id":    task_id,
        "pr": {
            "id":          pr.id           if pr else None,
            "pr_number":   pr.pr_number    if pr else None,
            "pr_title":    pr.pr_title     if pr else None,
            "pr_url":      pr.pr_url       if pr else None,
            "status":      pr.status       if pr else None,
            "source_branch": pr.source_branch if pr else None,
            "repo":        pr.repo_full_name if pr else None,
        } if pr else None,
        "deployment": {
            "id":          dep.id          if dep else None,
            "environment": dep.environment if dep else None,
            "status":      dep.status      if dep else None,
            "deploy_url":  dep.deploy_url  if dep else None,
            "deployed_at": dep.deployed_at if dep else None,
            "sha":         dep.sha         if dep else None,
        } if dep else None,
    })
