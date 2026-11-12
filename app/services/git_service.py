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
from app.core.timeutil import utcnow
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.git_integration import (
    DeployStatus, GitDeployment, GitProvider, GitPullRequest, PRStatus,
)
from app.models.task import Task
from app.core.errores import ErrorDeDominio

_logger = logging.getLogger(__name__)

_TASK_REF_RE = re.compile(r'\b([A-Z]{2,10})-(\d+)\b')


def find_task_by_ref(db: Session, ref_text: str) -> Optional[str]:
    """La tarea cuyo código aparece en la rama o el título, en la empresa de la sesión.

    Revisión 2026-11: buscaba `Task.code` en todas las empresas, así que un PR
    fusionado en una podía cerrar la tarea homónima de otra. Ahora la sesión
    trabaja como la empresa del webhook (ver `procesar_como`) y la consulta lo
    exige además de forma explícita. Fuera `#123`: se comparaba con un UUID y
    no enlazaba nunca.
    """
    org = db.info.get("organization_id")
    for m in _TASK_REF_RE.finditer(ref_text or ''):
        q = db.query(Task).filter(Task.code == f"{m.group(1)}-{m.group(2)}")
        if org:
            q = q.filter(Task.organization_id == org)
        t = q.first()
        if t:
            return t.id
    return None


def verify_github_signature(body: bytes, sig_header: str, secret: Optional[str] = None) -> bool:
    """HMAC-SHA256 verification for GitHub webhooks (el secreto de la empresa, o el global)."""
    secret = secret if secret is not None else settings.GITHUB_WEBHOOK_SECRET
    if not secret:
        # Reject all requests when no secret is configured — do not allow unauthenticated access
        return False
    if not sig_header or not sig_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig_header)


def verify_gitlab_token(token_header: str, secret: Optional[str] = None) -> bool:
    """Token-based verification for GitLab webhooks (el secreto de la empresa, o el global)."""
    secret = secret if secret is not None else settings.GITLAB_WEBHOOK_SECRET
    if not secret:
        # Reject all requests when no secret is configured — do not allow unauthenticated access
        return False
    if not token_header:
        return False
    return hmac.compare_digest(secret, token_header)


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
        existing.updated_at = utcnow()
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
            # Revisión 2026-11: por las reglas de transición, como desde la pantalla (antes la pasaba a
            # done desde cualquier estado, también backlog o bloqueada, y sin fecha de cierre).
            from fastapi import HTTPException

            from app.models.task import TaskStatus
            from app.services.tasks.core import apply_status_side_effects, validate_task_transition
            try:
                validate_task_transition(TaskStatus(getattr(linked_task.status, "value", linked_task.status)), TaskStatus.done)
                linked_task.status = TaskStatus.done
                apply_status_side_effects(linked_task, TaskStatus.done)
                _logger.info("[Git] Auto-closed task %s on merged PR #%s", effective_task_id, pr_number)
            except (HTTPException, ErrorDeDominio):
                _logger.info("[Git] PR #%s fusionado: la tarea %s sigue en %s (no puede pasar a done)",
                             pr_number, effective_task_id, linked_task.status)

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
    deployed_at    = utcnow() if status == DeployStatus.success else None

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
        existing.updated_at = utcnow()
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
            _logger.debug("handle_gitlab_deployment: excepcion ignorada", exc_info=True)
            deployed_at = utcnow()

    db.add(GitDeployment(
        provider=GitProvider.gitlab, repo_full_name=repo_full_name,
        sha=sha, environment=environment, deploy_url=deploy_url,
        status=status, task_id=task_id, deployed_at=deployed_at,
    ))


def process_github_webhook(db: Session, event: str, payload: dict, org_id: Optional[str] = None) -> None:
    """Procesa un evento de GitHub como la empresa del webhook y confirma."""
    from app.services.service_desk.ticket_events import como_organizacion
    with como_organizacion(db, org_id):
        if event == "pull_request":
            handle_github_pr(db, payload)
        elif event == "deployment_status":
            handle_github_deployment(db, payload)
        db.commit()


def process_gitlab_webhook(db: Session, event: str, payload: dict, org_id: Optional[str] = None) -> None:
    """Procesa un evento de GitLab como la empresa del webhook y confirma."""
    from app.services.service_desk.ticket_events import como_organizacion
    with como_organizacion(db, org_id):
        event_type = payload.get("object_kind", "")
        if event_type == "merge_request":
            handle_gitlab_mr(db, payload)
        elif event_type == "deployment":
            handle_gitlab_deployment(db, payload)
        db.commit()


def empresa_por_slug(db: Session, slug: str) -> Optional[str]:
    from app.models.mfa import Organization
    org = db.query(Organization).filter(Organization.slug == slug, Organization.is_active == True).first()  # noqa: E712
    return org.id if org else None


def unica_empresa(db: Session) -> Optional[str]:
    """La empresa, si la instalación sólo tiene una (las rutas antiguas sin empresa)."""
    from app.models.mfa import Organization
    ids = [r[0] for r in db.query(Organization.id).filter(Organization.is_active == True).limit(2).all()]  # noqa: E712
    return ids[0] if len(ids) == 1 else None


def direcciones_de_la_empresa(db: Session, org_id: Optional[str]) -> dict:
    """Las direcciones de webhook de la empresa y si ya tiene su secreto."""
    from app.core.config import settings as _s
    from app.models.mfa import Organization
    org = db.get(Organization, org_id) if org_id else None
    if not org:
        return {"slug": None}
    base = f"{_s.API_V1_STR}/git/webhooks"
    return {"slug": org.slug, **{p: {"ruta": f"{base}/{p}/{org.slug}",
                                      "secreto": bool(secreto_de_la_empresa(db, p, org.id))}
                                  for p in ("github", "gitlab")}}


def secreto_de_la_empresa(db: Session, proveedor: str, org_id: str) -> Optional[str]:
    """El secreto del webhook guardado PARA esa empresa (sin caer al global).

    Con el global, quien lo tuviera podría escribir en cualquier empresa
    cambiando la URL; por eso la ruta por empresa exige el suyo.
    """
    from app.core.encryption import decrypt_value
    from app.models.settings import IntegrationCredential
    fila = db.query(IntegrationCredential).filter(
        IntegrationCredential.provider == "webhooks", IntegrationCredential.key == f"{proveedor}_secret",
        IntegrationCredential.organization_id == org_id).first()
    return decrypt_value(fila.value_encrypted) if fila and fila.value_encrypted else None


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
