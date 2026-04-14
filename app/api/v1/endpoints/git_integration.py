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

import hashlib
import hmac
import logging
import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.models.git_integration import DeployStatus, GitDeployment, GitProvider, GitPullRequest, PRStatus
from app.models.task import Task
from app.models.user import User

router = APIRouter()
_logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

_TASK_REF_RE = re.compile(r'\b([A-Z]{2,10})-(\d+)\b|#(\d+)')


def _find_task_by_ref(db: Session, ref_text: str) -> Optional[int]:
    """Attempt to find a task_id from a branch name / PR title."""
    for m in _TASK_REF_RE.finditer(ref_text or ''):
        code = f"{m.group(1)}-{m.group(2)}" if m.group(1) else None
        num  = int(m.group(3)) if m.group(3) else None
        if code:
            t = db.query(Task).filter(Task.code == code).first()
            if t:
                return t.id
        if num:
            t = db.query(Task).filter(Task.id == num).first()
            if t:
                return t.id
    return None


def _verify_github_signature(body: bytes, sig_header: str) -> bool:
    """HMAC-SHA256 verification for GitHub webhooks."""
    if not settings.GITHUB_WEBHOOK_SECRET:
        return True  # Secret not configured → accept all (dev mode)
    if not sig_header or not sig_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig_header)


def _verify_gitlab_token(token_header: str) -> bool:
    """Token-based verification for GitLab webhooks."""
    if not settings.GITLAB_WEBHOOK_SECRET:
        return True
    if not token_header:
        return False
    return hmac.compare_digest(settings.GITLAB_WEBHOOK_SECRET, token_header)


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

    if x_github_event == "pull_request":
        _handle_github_pr(db, payload)
    elif x_github_event == "deployment_status":
        _handle_github_deployment(db, payload)
    elif x_github_event == "push":
        # Push events: useful for branch creation link tracking (no-op for now)
        pass

    db.commit()
    return {"status": "ok"}


def _handle_github_pr(db: Session, payload: dict):
    action = payload.get("action", "")
    pr_data = payload.get("pull_request", {})
    repo    = payload.get("repository", {})

    pr_number      = pr_data.get("number")
    repo_full_name = repo.get("full_name", "")
    pr_title       = pr_data.get("title", "")
    pr_url         = pr_data.get("html_url", "")
    author_login   = pr_data.get("user", {}).get("login", "")
    source_branch  = pr_data.get("head", {}).get("ref", "")
    target_branch  = pr_data.get("base", {}).get("ref", "")

    # Map action → status
    status_map = {
        "opened": PRStatus.open,
        "reopened": PRStatus.open,
        "synchronize": PRStatus.open,
        "converted_to_draft": PRStatus.draft,
        "ready_for_review": PRStatus.open,
        "closed": PRStatus.merged if pr_data.get("merged") else PRStatus.closed,
    }
    status = status_map.get(action, PRStatus.open)

    # Auto-link task from branch name or title
    ref_text = f"{source_branch} {pr_title}"
    task_id  = _find_task_by_ref(db, ref_text)

    # Upsert
    existing = db.query(GitPullRequest).filter(
        GitPullRequest.repo_full_name == repo_full_name,
        GitPullRequest.pr_number      == pr_number,
        GitPullRequest.provider       == GitProvider.github,
    ).first()

    merged_at = None
    closed_at = None
    if pr_data.get("merged_at"):
        try:
            merged_at = datetime.fromisoformat(pr_data["merged_at"].replace("Z", "+00:00"))
        except Exception:
            _logger.warning("Could not parse merged_at: %s", pr_data.get("merged_at"))
    if pr_data.get("closed_at") and status == PRStatus.closed:
        try:
            closed_at = datetime.fromisoformat(pr_data["closed_at"].replace("Z", "+00:00"))
        except Exception:
            _logger.warning("Could not parse closed_at: %s", pr_data.get("closed_at"))

    if existing:
        existing.status        = status
        existing.pr_title      = pr_title
        existing.merged_at     = merged_at
        existing.closed_at     = closed_at
        if task_id and not existing.task_id:
            existing.task_id = task_id
        existing.updated_at = datetime.utcnow()
    else:
        pr = GitPullRequest(
            provider       = GitProvider.github,
            repo_full_name = repo_full_name,
            pr_number      = pr_number,
            pr_title       = pr_title,
            pr_url         = pr_url,
            author_login   = author_login,
            source_branch  = source_branch,
            target_branch  = target_branch,
            status         = status,
            task_id        = task_id,
            merged_at      = merged_at,
            closed_at      = closed_at,
        )
        db.add(pr)

    # Auto-close linked task when PR is merged
    effective_task_id = task_id or (existing.task_id if existing else None)
    if action == "closed" and pr_data.get("merged") and effective_task_id:
        linked_task = db.query(Task).filter(Task.id == effective_task_id).first()
        if linked_task and linked_task.status not in ("done", "closed", "cancelled"):
            linked_task.status = "done"
            _logger.info("[Git] Auto-closed task %s on merged PR #%s", effective_task_id, pr_number)

    _logger.info(f"[Git] GitHub PR #{pr_number} {action} → {repo_full_name}")


def _handle_github_deployment(db: Session, payload: dict):
    dep_status_data = payload.get("deployment_status", {})
    deployment      = payload.get("deployment", {})
    repo            = payload.get("repository", {})

    state_map = {
        "pending":  DeployStatus.pending,
        "in_progress": DeployStatus.running,
        "success":  DeployStatus.success,
        "failure":  DeployStatus.failure,
        "error":    DeployStatus.failure,
        "inactive": DeployStatus.cancelled,
    }
    status = state_map.get(dep_status_data.get("state", ""), DeployStatus.pending)

    repo_full_name = repo.get("full_name", "")
    sha            = deployment.get("sha", "")
    environment    = deployment.get("environment", "production")
    deploy_url     = dep_status_data.get("target_url", "") or dep_status_data.get("log_url", "")

    ref_text = deployment.get("ref", "")
    task_id  = _find_task_by_ref(db, ref_text)

    deployed_at = None
    if status == DeployStatus.success:
        deployed_at = datetime.utcnow()

    dep = GitDeployment(
        provider       = GitProvider.github,
        repo_full_name = repo_full_name,
        sha            = sha,
        environment    = environment,
        deploy_url     = deploy_url,
        status         = status,
        task_id        = task_id,
        deployed_at    = deployed_at,
    )
    db.add(dep)
    _logger.info(f"[Git] GitHub deployment {sha[:8]} → {environment} ({status})")


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

    event_type = payload.get("object_kind", "")

    if event_type == "merge_request":
        _handle_gitlab_mr(db, payload)
    elif event_type == "deployment":
        _handle_gitlab_deployment(db, payload)

    db.commit()
    return {"status": "ok"}


def _handle_gitlab_mr(db: Session, payload: dict):
    obj_attrs      = payload.get("object_attributes", {})
    project        = payload.get("project", {})
    repo_full_name = project.get("path_with_namespace", "")
    pr_number      = obj_attrs.get("iid") or obj_attrs.get("id")
    pr_title       = obj_attrs.get("title", "")
    pr_url         = obj_attrs.get("url", "")
    author_login   = (payload.get("user") or {}).get("username", "")
    source_branch  = obj_attrs.get("source_branch", "")
    target_branch  = obj_attrs.get("target_branch", "")
    state          = obj_attrs.get("state", "opened")

    state_map = {
        "opened": PRStatus.open,
        "merged": PRStatus.merged,
        "closed": PRStatus.closed,
        "locked": PRStatus.closed,
    }
    status = state_map.get(state, PRStatus.open)

    ref_text = f"{source_branch} {pr_title}"
    task_id  = _find_task_by_ref(db, ref_text)

    existing = db.query(GitPullRequest).filter(
        GitPullRequest.repo_full_name == repo_full_name,
        GitPullRequest.pr_number      == pr_number,
        GitPullRequest.provider       == GitProvider.gitlab,
    ).first()

    if existing:
        existing.status    = status
        existing.pr_title  = pr_title
        if task_id and not existing.task_id:
            existing.task_id = task_id
        existing.updated_at = datetime.utcnow()
    else:
        pr = GitPullRequest(
            provider       = GitProvider.gitlab,
            repo_full_name = repo_full_name,
            pr_number      = pr_number,
            pr_title       = pr_title,
            pr_url         = pr_url,
            author_login   = author_login,
            source_branch  = source_branch,
            target_branch  = target_branch,
            status         = status,
            task_id        = task_id,
        )
        db.add(pr)


def _handle_gitlab_deployment(db: Session, payload: dict):
    status_str = payload.get("status", "running")
    state_map  = {"created": DeployStatus.pending, "running": DeployStatus.running,
                  "success": DeployStatus.success, "failed": DeployStatus.failure,
                  "canceled": DeployStatus.cancelled}
    status     = state_map.get(status_str, DeployStatus.pending)

    project        = payload.get("project", {})
    repo_full_name = project.get("path_with_namespace", "")
    environment    = payload.get("environment", "production")
    sha            = payload.get("sha", "")
    deploy_url     = payload.get("deployable_url", "")

    ref_text = payload.get("ref", "")
    task_id  = _find_task_by_ref(db, ref_text)

    deployed_at = None
    finished    = payload.get("finished_at")
    if finished and status == DeployStatus.success:
        try: deployed_at = datetime.fromisoformat(finished.replace("Z", "+00:00"))
        except Exception: deployed_at = datetime.utcnow()

    dep = GitDeployment(
        provider       = GitProvider.gitlab,
        repo_full_name = repo_full_name,
        sha            = sha,
        environment    = environment,
        deploy_url     = deploy_url,
        status         = status,
        task_id        = task_id,
        deployed_at    = deployed_at,
    )
    db.add(dep)


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
    q = db.query(GitPullRequest)
    if task_id:    q = q.filter(GitPullRequest.task_id == task_id)
    if project_id: q = q.filter(GitPullRequest.project_id == project_id)
    if status:     q = q.filter(GitPullRequest.status == status)
    if provider:   q = q.filter(GitPullRequest.provider == provider)
    return q.order_by(GitPullRequest.created_at.desc()).limit(limit).all()


@router.get("/pull-requests/{pr_id}", response_model=PROut, summary="Detalle de PR")
def get_pr(
    pr_id: int,
    db:    Session = Depends(get_db),
    _:     User    = Depends(get_current_user),
):
    pr = db.query(GitPullRequest).filter(GitPullRequest.id == pr_id).first()
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
    q = db.query(GitDeployment)
    if task_id:    q = q.filter(GitDeployment.task_id == task_id)
    if project_id: q = q.filter(GitDeployment.project_id == project_id)
    if status:     q = q.filter(GitDeployment.status == status)
    return q.order_by(GitDeployment.created_at.desc()).limit(limit).all()


@router.post("/tasks/{task_id}/branch", summary="Sugerir nombre de rama para una tarea")
def suggest_branch(
    task_id: int,
    db:      Session = Depends(get_db),
    _:       User    = Depends(get_current_user),
):
    """
    Generates a canonical branch name for a task following the convention:
      {type}/{code}-{slug}
    e.g.  feat/PROJ-123-add-user-auth

    If GITHUB_TOKEN is configured and the payload includes repo_full_name,
    the branch can be created remotely (requires caller to pass repo info).
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    issue_type = getattr(task, "issue_type", None) or ""
    prefix_map = {"feature": "feat", "bug": "fix", "bugfix": "fix", "hotfix": "hotfix", "chore": "chore", "docs": "docs"}
    prefix = prefix_map.get(issue_type.lower(), "task")

    title = task.title or ""
    slug  = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]
    slug  = re.sub(r"-+", "-", slug)

    code = getattr(task, "code", None) or str(task_id)
    branch_name = f"{prefix}/{code}-{slug}"

    return {
        "task_id":     task_id,
        "task_code":   code,
        "branch_name": branch_name,
        "prefix":      prefix,
    }


@router.get("/tasks/{task_id}/pr-status", summary="Estado de PR/Deploy para una tarea")
def task_pr_status(
    task_id: int,
    db:      Session = Depends(get_db),
    _:       User    = Depends(get_current_user),
):
    """Returns the latest PR and latest deployment linked to a task."""
    pr = (
        db.query(GitPullRequest)
        .filter(GitPullRequest.task_id == task_id)
        .order_by(GitPullRequest.updated_at.desc())
        .first()
    )
    dep = (
        db.query(GitDeployment)
        .filter(GitDeployment.task_id == task_id)
        .order_by(GitDeployment.created_at.desc())
        .first()
    )

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
