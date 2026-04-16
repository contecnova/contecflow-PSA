"""
git_service.py — Lógica de negocio para la integración Git.

Funciones exportadas:
  find_task_by_ref(db, ref_text) -> Optional[str]
  verify_github_signature(body, sig_header) -> bool
  verify_gitlab_token(token_header) -> bool
  handle_github_pr(db, payload) -> None
  handle_github_deployment(db, payload) -> None
  handle_gitlab_mr(db, payload) -> None
  handle_gitlab_deployment(db, payload) -> None
  suggest_branch_name(task) -> dict
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.git_integration import (
    DeployStatus, GitDeployment, GitProvider, GitPullRequest, PRStatus,
)
from app.models.task import Task

_logger = logging.getLogger(__name__)

_TASK_REF_RE = re.compile(r'\b([A-Z]{2,10})-(\d+)\b|#(\d+)')


def find_task_by_ref(db: Session, ref_text: str) -> Optional[str]:
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


def verify_github_signature(body: bytes, sig_header: str) -> bool:
    """HMAC-SHA256 verification for GitHub webhooks."""
    if not settings.GITHUB_WEBHOOK_SECRET:
        return True
    if not sig_header or not sig_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig_header)


def verify_gitlab_token(token_header: str) -> bool:
    """Token-based verification for GitLab webhooks."""
    if not settings.GITLAB_WEBHOOK_SECRET:
        return True
    if not token_header:
        return False
    return hmac.compare_digest(settings.GITLAB_WEBHOOK_SECRET, token_header)


def handle_github_pr(db: Session, payload: dict) -> None:
    """Process a GitHub pull_request event — upsert GitPullRequest and optionally auto-close task."""
    action  = payload.get("action", "")
    pr_data = payload.get("pull_request", {})
    repo    = payload.get("repository", {})

    pr_number      = pr_data.get("number")
    repo_full_name = repo.get("full_name", "")
    pr_title       = pr_data.get("title", "")
    pr_url         = pr_data.get("html_url", "")
    author_login   = pr_data.get("user", {}).get("login", "")
    source_branch  = pr_data.get("head", {}).get("ref", "")
    target_branch  = pr_data.get("base", {}).get("ref", "")

    status_map = {
        "opened": PRStatus.open,
        "reopened": PRStatus.open,
        "synchronize": PRStatus.open,
        "converted_to_draft": PRStatus.draft,
        "ready_for_review": PRStatus.open,
        "closed": PRStatus.merged if pr_data.get("merged") else PRStatus.closed,
    }
    status   = status_map.get(action, PRStatus.open)
    ref_text = f"{source_branch} {pr_title}"
    task_id  = find_task_by_ref(db, ref_text)

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

    existing = db.query(GitPullRequest).filter(
        GitPullRequest.repo_full_name == repo_full_name,
        GitPullRequest.pr_number      == pr_number,
        GitPullRequest.provider       == GitProvider.github,
    ).first()

    if existing:
        existing.status    = status
        existing.pr_title  = pr_title
        existing.merged_at = merged_at
        existing.closed_at = closed_at
        if task_id and not existing.task_id:
            existing.task_id = task_id
        existing.updated_at = datetime.utcnow()
    else:
        pr = GitPullRequest(
            provider=GitProvider.github, repo_full_name=repo_full_name,
            pr_number=pr_number, pr_title=pr_title, pr_url=pr_url,
            author_login=author_login, source_branch=source_branch,
            target_branch=target_branch, status=status, task_id=task_id,
            merged_at=merged_at, closed_at=closed_at,
        )
        db.add(pr)

    # Auto-close linked task when PR is merged
    effective_task_id = task_id or (existing.task_id if existing else None)
    if action == "closed" and pr_data.get("merged") and effective_task_id:
        linked_task = db.query(Task).filter(Task.id == effective_task_id).first()
        if linked_task and linked_task.status not in ("done", "closed", "cancelled"):
            linked_task.status = "done"
            _logger.info("[Git] Auto-closed task %s on merged PR #%s", effective_task_id, pr_number)

    _logger.info("[Git] GitHub PR #%s %s → %s", pr_number, action, repo_full_name)


def handle_github_deployment(db: Session, payload: dict) -> None:
    """Process a GitHub deployment_status event — insert GitDeployment."""
    dep_status_data = payload.get("deployment_status", {})
    deployment      = payload.get("deployment", {})
    repo            = payload.get("repository", {})

    state_map = {
        "pending":     DeployStatus.pending,
        "in_progress": DeployStatus.running,
        "success":     DeployStatus.success,
        "failure":     DeployStatus.failure,
        "error":       DeployStatus.failure,
        "inactive":    DeployStatus.cancelled,
    }
    status         = state_map.get(dep_status_data.get("state", ""), DeployStatus.pending)
    repo_full_name = repo.get("full_name", "")
    sha            = deployment.get("sha", "")
    environment    = deployment.get("environment", "production")
    deploy_url     = dep_status_data.get("target_url", "") or dep_status_data.get("log_url", "")
    task_id        = find_task_by_ref(db, deployment.get("ref", ""))
    deployed_at    = datetime.utcnow() if status == DeployStatus.success else None

    db.add(GitDeployment(
        provider=GitProvider.github, repo_full_name=repo_full_name,
        sha=sha, environment=environment, deploy_url=deploy_url,
        status=status, task_id=task_id, deployed_at=deployed_at,
    ))
    _logger.info("[Git] GitHub deployment %s → %s (%s)", sha[:8], environment, status)


def handle_gitlab_mr(db: Session, payload: dict) -> None:
    """Process a GitLab merge_request event — upsert GitPullRequest."""
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

    state_map = {"opened": PRStatus.open, "merged": PRStatus.merged,
                 "closed": PRStatus.closed, "locked": PRStatus.closed}
    status   = state_map.get(state, PRStatus.open)
    ref_text = f"{source_branch} {pr_title}"
    task_id  = find_task_by_ref(db, ref_text)

    existing = db.query(GitPullRequest).filter(
        GitPullRequest.repo_full_name == repo_full_name,
        GitPullRequest.pr_number      == pr_number,
        GitPullRequest.provider       == GitProvider.gitlab,
    ).first()

    if existing:
        existing.status   = status
        existing.pr_title = pr_title
        if task_id and not existing.task_id:
            existing.task_id = task_id
        existing.updated_at = datetime.utcnow()
    else:
        db.add(GitPullRequest(
            provider=GitProvider.gitlab, repo_full_name=repo_full_name,
            pr_number=pr_number, pr_title=pr_title, pr_url=pr_url,
            author_login=author_login, source_branch=source_branch,
            target_branch=target_branch, status=status, task_id=task_id,
        ))


def handle_gitlab_deployment(db: Session, payload: dict) -> None:
    """Process a GitLab deployment event — insert GitDeployment."""
    state_map = {
        "created":  DeployStatus.pending,
        "running":  DeployStatus.running,
        "success":  DeployStatus.success,
        "failed":   DeployStatus.failure,
        "canceled": DeployStatus.cancelled,
    }
    status         = state_map.get(payload.get("status", "running"), DeployStatus.pending)
    project        = payload.get("project", {})
    repo_full_name = project.get("path_with_namespace", "")
    environment    = payload.get("environment", "production")
    sha            = payload.get("sha", "")
    deploy_url     = payload.get("deployable_url", "")
    task_id        = find_task_by_ref(db, payload.get("ref", ""))

    deployed_at = None
    finished    = payload.get("finished_at")
    if finished and status == DeployStatus.success:
        try:
            deployed_at = datetime.fromisoformat(finished.replace("Z", "+00:00"))
        except Exception:
            deployed_at = datetime.utcnow()

    db.add(GitDeployment(
        provider=GitProvider.gitlab, repo_full_name=repo_full_name,
        sha=sha, environment=environment, deploy_url=deploy_url,
        status=status, task_id=task_id, deployed_at=deployed_at,
    ))


def process_github_webhook(db: Session, event: str, payload: dict) -> None:
    """Dispatch a GitHub webhook event and commit."""
    if event == "pull_request":
        handle_github_pr(db, payload)
    elif event == "deployment_status":
        handle_github_deployment(db, payload)
    db.commit()


def process_gitlab_webhook(db: Session, event: str, payload: dict) -> None:
    """Dispatch a GitLab webhook event and commit."""
    event_type = payload.get("object_kind", "")
    if event_type == "merge_request":
        handle_gitlab_mr(db, payload)
    elif event_type == "deployment":
        handle_gitlab_deployment(db, payload)
    db.commit()


def list_pull_requests(
    db: Session,
    task_id: Optional[int] = None,
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    provider: Optional[str] = None,
    limit: int = 50,
):
    q = db.query(GitPullRequest)
    if task_id:    q = q.filter(GitPullRequest.task_id == task_id)
    if project_id: q = q.filter(GitPullRequest.project_id == project_id)
    if status:     q = q.filter(GitPullRequest.status == status)
    if provider:   q = q.filter(GitPullRequest.provider == provider)
    return q.order_by(GitPullRequest.created_at.desc()).limit(limit).all()


def get_pull_request(db: Session, pr_id: int) -> Optional[GitPullRequest]:
    return db.query(GitPullRequest).filter(GitPullRequest.id == pr_id).first()


def list_deployments(
    db: Session,
    task_id: Optional[int] = None,
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
):
    q = db.query(GitDeployment)
    if task_id:    q = q.filter(GitDeployment.task_id == task_id)
    if project_id: q = q.filter(GitDeployment.project_id == project_id)
    if status:     q = q.filter(GitDeployment.status == status)
    return q.order_by(GitDeployment.created_at.desc()).limit(limit).all()


def get_task(db: Session, task_id: int) -> Optional[Task]:
    return db.query(Task).filter(Task.id == task_id).first()


def get_task_pr_status(db: Session, task_id: int):
    """Return (latest_pr, latest_deployment) for the given task."""
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
    return pr, dep


def suggest_branch_name(task) -> dict:
    """Generate a canonical branch name for a task following {type}/{code}-{slug} convention."""
    issue_type = getattr(task, "issue_type", None) or ""
    prefix_map = {
        "feature": "feat", "bug": "fix", "bugfix": "fix",
        "hotfix": "hotfix", "chore": "chore", "docs": "docs",
    }
    prefix     = prefix_map.get(issue_type.lower(), "task")
    title      = task.title or ""
    slug       = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]
    slug       = re.sub(r"-+", "-", slug)
    code       = getattr(task, "code", None) or str(task.id)
    branch_name = f"{prefix}/{code}-{slug}"
    return {"task_id": task.id, "task_code": code, "branch_name": branch_name, "prefix": prefix}
