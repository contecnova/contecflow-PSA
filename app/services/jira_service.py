"""
jira_service.py — DB-layer logic for Jira integration.

All SQLAlchemy session calls (query/add/commit/flush) live here;
the router only handles HTTP I/O and business validation.
"""
from __future__ import annotations

import datetime
from typing import Optional, List

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.models.task import Task
from app.core.encryption import encrypt_value, decrypt_value
from app.core.config import settings

_SENSITIVE_SETTING_KEYS = {"jira_api_token"}


# ── Inbound webhook authentication ──────────────────────────────────────────────

def verify_jira_webhook(body: bytes, token_header: Optional[str], signature_header: Optional[str]) -> bool:
    """Authenticate an inbound Jira webhook against ``JIRA_WEBHOOK_SECRET``.

    Jira Cloud does not sign native webhooks, so we support either:
      * a shared secret in ``X-Atlassian-Webhook-Token`` (configure a Jira
        automation rule to send it), or
      * an HMAC-SHA256 of the raw body in ``X-Hub-Signature-256`` (``sha256=``
        prefixed), for setups that proxy/sign the payload.

    Constant-time comparison throughout. Returns False when the secret is not
    configured (fail-closed) — unauthenticated webhooks can mutate tickets
    cross-tenant, so they must never be trusted by default.
    """
    import hmac
    import hashlib

    secret = settings.JIRA_WEBHOOK_SECRET
    if not secret:
        return False
    if token_header and hmac.compare_digest(secret, token_header.strip()):
        return True
    if signature_header and signature_header.startswith("sha256="):
        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, signature_header.strip()):
            return True
    return False

# ── Jira ↔ NexusPM status / priority maps ─────────────────────────────────────

JIRA_STATUS_MAP = {
    "to do":       "todo",
    "open":        "todo",
    "backlog":     "backlog",
    "in progress": "in_progress",
    "in review":   "in_review",
    "done":        "done",
    "closed":      "done",
    "resolved":    "done",
    "cancelled":   "cancelled",
    "won't fix":   "cancelled",
}

JIRA_PRIORITY_MAP = {
    "blocker":  "critical",
    "critical": "critical",
    "highest":  "critical",
    "high":     "high",
    "medium":   "medium",
    "low":      "low",
    "lowest":   "low",
    "trivial":  "low",
}

# ── AppSetting helpers ─────────────────────────────────────────────────────────

def get_setting(db: Session, key: str, org_id: Optional[str] = None) -> Optional[str]:
    """Return tenant-specific setting, falling back to global row."""
    if org_id:
        row = db.query(AppSetting).filter(
            AppSetting.key == key, AppSetting.organization_id == org_id
        ).first()
        if row:
            return row.value
    row = db.query(AppSetting).filter(
        AppSetting.key == key, AppSetting.organization_id.is_(None)
    ).first()
    value = row.value if row else None
    if value and key in _SENSITIVE_SETTING_KEYS:
        dec = decrypt_value(value)
        return dec if dec is not None else value
    return value


def set_setting(db: Session, key: str, value: str, org_id: Optional[str] = None) -> None:
    """Upsert a setting scoped to *org_id* (or global when None)."""
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if org_id:
        q = q.filter(AppSetting.organization_id == org_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    store_value = encrypt_value(value) if key in _SENSITIVE_SETTING_KEYS and value else value
    if row:
        row.value = store_value
    else:
        db.add(AppSetting(key=key, value=store_value, organization_id=org_id,
                          description=f"Jira integration: {key}"))
    db.flush()


def get_jira_config(db: Session, org_id: Optional[str] = None) -> dict:
    return {
        "jira_url":         get_setting(db, "jira_url",         org_id),
        "jira_email":       get_setting(db, "jira_email",       org_id),
        "jira_api_token":   get_setting(db, "jira_api_token",   org_id),
        "jira_project_key": get_setting(db, "jira_project_key", org_id),
    }


def save_jira_config(
    db: Session,
    org_id: Optional[str],
    jira_url: str,
    jira_email: str,
    jira_api_token: str,
    jira_project_key: str,
) -> None:
    """Upsert all four Jira config settings and commit."""
    set_setting(db, "jira_url",         jira_url,         org_id)
    set_setting(db, "jira_email",       jira_email,       org_id)
    set_setting(db, "jira_api_token",   jira_api_token,   org_id)
    set_setting(db, "jira_project_key", jira_project_key, org_id)
    db.commit()


# ── Task helpers ───────────────────────────────────────────────────────────────

def get_task_by_jira_key(db: Session, jira_key: str) -> Optional[Task]:
    return db.query(Task).filter(Task.jira_issue_key == jira_key).first()


def _extract_adf_text(node) -> list:
    """Best-effort plain-text extraction from Atlassian Document Format."""
    parts: list = []
    if isinstance(node, dict):
        if node.get("type") == "text":
            parts.append(node.get("text", ""))
        for child in node.get("content", []):
            parts.extend(_extract_adf_text(child))
    return parts


def sync_jira_issues(
    db: Session,
    issues: list,
    project_id: Optional[str],
    current_user_id: str,
    dry_run: bool,
) -> dict:
    """
    Create or update NexusPM Tasks from a list of raw Jira issue dicts.
    Returns ``{"created": int, "updated": int, "skipped": int}``.
    """
    created = updated = skipped = 0
    now = datetime.datetime.now(datetime.timezone.utc)

    for iss in issues:
        f = iss.get("fields", {})
        jira_key     = iss["key"]
        jira_id      = iss["id"]
        title        = f.get("summary") or jira_key
        raw_status   = (f.get("status", {}).get("name") or "").lower()
        raw_priority = (f.get("priority", {}).get("name") or "").lower()
        nm_status    = JIRA_STATUS_MAP.get(raw_status, "todo")
        nm_priority  = JIRA_PRIORITY_MAP.get(raw_priority, "medium")
        due_date     = f.get("duedate")

        desc_adf  = f.get("description")
        desc_text = None
        if desc_adf and isinstance(desc_adf, dict):
            parts = _extract_adf_text(desc_adf)
            desc_text = " ".join(parts).strip() or None

        existing = db.query(Task).filter(Task.jira_issue_key == jira_key).first()

        if existing:
            if not dry_run:
                existing.status         = nm_status
                existing.priority       = nm_priority
                existing.jira_issue_id  = jira_id
                existing.jira_synced_at = now
                if due_date:
                    existing.due_date = due_date
            updated += 1
        else:
            if not dry_run:
                task = Task(
                    title=title,
                    description=desc_text,
                    status=nm_status,
                    priority=nm_priority,
                    due_date=due_date,
                    project_id=project_id,
                    jira_issue_key=jira_key,
                    jira_issue_id=jira_id,
                    jira_synced_at=now,
                    created_by_user_id=current_user_id,
                )
                db.add(task)
            created += 1

    if not dry_run:
        db.commit()

    return {"created": created, "updated": updated, "skipped": skipped}


def get_tasks_for_push(db: Session, project_id: str, statuses: List[str]) -> list:
    """Return tasks in a project without a Jira key, filtered by status."""
    return (
        db.query(Task)
        .filter(
            Task.project_id == project_id,
            Task.status.in_(statuses),
            Task.jira_issue_key == None,  # noqa: E711
        )
        .all()
    )


def commit_db(db: Session) -> None:
    """Commit the current session (used after bulk task mutations in the push loop)."""
    db.commit()


def update_task_from_webhook(
    db: Session,
    task: Task,
    nm_status: Optional[str],
    nm_priority: Optional[str],
    event: str,
) -> bool:
    """
    Apply status/priority changes from a Jira webhook event.
    Commits if anything changed.  Returns True when the task was updated.
    """
    changed = False
    if nm_status and task.status != nm_status:
        task.status = nm_status
        changed = True
    if nm_priority and task.priority != nm_priority:
        task.priority = nm_priority
        changed = True
    if event == "jira:issue_deleted":
        task.jira_issue_key = None
        task.jira_issue_id  = None
        changed = True
    if changed:
        task.jira_synced_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()
    return changed


def get_linked_tasks_query(db: Session, project_id: Optional[str]):
    """Return a query for tasks that have a Jira issue key, optionally scoped to a project."""
    q = db.query(Task).filter(Task.jira_issue_key != None)  # noqa: E711
    if project_id:
        q = q.filter(Task.project_id == project_id)
    return q


# ── HTTP helper ──────────────────────────────────────────────────────────────

def jira_headers(email: str, token: str) -> dict:
    import base64 as _b64
    creds = _b64.b64encode(f"{email}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
