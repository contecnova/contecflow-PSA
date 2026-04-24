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
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
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


# ── GitHub webhook ─────────────────────────────────────────────────────────────

@router.post("/webhooks/github", summary="Recibir eventos GitHub (PR / deployment)")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str = Header(default=""),
    db: Session = Depends(get_db),
):
    body = await request.body()
    if not _verify_github_signature(body, x_hub_signature_256):
        raise HTTPException(403, "Invalid GitHub webhook signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    process_github_webhook(db, x_github_event, payload)
    return {"status": "ok"}


# ── GitLab webhook ─────────────────────────────────────────────────────────────

@router.post("/webhooks/gitlab", summary="Recibir eventos GitLab (MR / deployment)")
async def gitlab_webhook(
    request: Request,
    x_gitlab_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    if not _verify_gitlab_token(x_gitlab_token):
        raise HTTPException(403, "Invalid GitLab webhook token")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    process_gitlab_webhook(db, payload.get("object_kind", ""), payload)
    return {"status": "ok"}


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


@router.get("/pull-requests", response_model=List[PROut], summary="Listar Pull Requests")
def list_prs(
    task_id:    Optional[int] = Query(None),
    project_id: Optional[int] = Query(None),
    status:     Optional[str] = Query(None),
    provider:   Optional[str] = Query(None),
    limit:      int           = Query(50, le=200),
    db:         Session       = Depends(get_db),
    _:          User          = Depends(get_current_user),
):
    return list_pull_requests(db, task_id=task_id, project_id=project_id, status=status, provider=provider, limit=limit)


@router.get("/pull-requests/{pr_id}", response_model=PROut, summary="Detalle de PR")
def get_pr(
    pr_id: int,
    db:    Session = Depends(get_db),
    _:     User    = Depends(get_current_user),
):
    pr = get_pull_request(db, pr_id)
    if not pr:
        raise HTTPException(404, "Pull request not found")
    return pr


@router.get("/deployments", response_model=List[DeployOut], summary="Listar deployments")
def list_deployments(
    task_id:    Optional[int] = Query(None),
    project_id: Optional[int] = Query(None),
    status:     Optional[str] = Query(None),
    limit:      int           = Query(50, le=200),
    db:         Session       = Depends(get_db),
    _:          User          = Depends(get_current_user),
):
    return svc_list_deployments(db, task_id=task_id, project_id=project_id, status=status, limit=limit)


@router.post("/tasks/{task_id}/branch", summary="Sugerir nombre de rama para una tarea")
def suggest_branch(
    task_id: int,
    db:      Session = Depends(get_db),
    _:       User    = Depends(get_current_user),
):
    task = get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return suggest_branch_name(task)


@router.get("/tasks/{task_id}/pr-status", summary="Estado de PR/Deploy para una tarea")
def task_pr_status(
    task_id: int,
    db:      Session = Depends(get_db),
    _:       User    = Depends(get_current_user),
):
    """Returns the latest PR and latest deployment linked to a task."""
    pr, dep = get_task_pr_status(db, task_id)

    return {
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
    }
