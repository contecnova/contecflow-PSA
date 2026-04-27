"""
Jira SM Sync Service — bidirectional synchronisation between Contecflow tickets and Jira issues.

Responsibilities:
  - Push: ticket create/update/comment → Jira REST API
  - Pull: Jira webhook events or polled diff → update local tickets
  - Conflict resolution: last-write-wins with manual override flag
  - Audit: every event written to JiraSyncLog
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.models.jira_integration import (
    JiraConfig,
    JiraFieldMap,
    JiraSyncDirection,
    JiraSyncEventType,
    JiraSyncLog,
    JiraSyncMap,
    JiraSyncStatus,
)
from app.models.service_desk import Ticket, TicketComment, TicketPriority, TicketStatus

logger = logging.getLogger(__name__)

# ── Priority + Status default maps ────────────────────────────────────────────

_DEFAULT_PRIORITY_MAP: dict[str, str] = {
    "p1_critical": "Highest",
    "p2_high": "High",
    "p3_medium": "Medium",
    "p4_low": "Low",
}

_DEFAULT_STATUS_MAP: dict[str, str] = {
    "new": "Open",
    "assigned": "In Progress",
    "in_progress": "In Progress",
    "pending_client": "Waiting for customer",
    "pending_third": "Waiting for support",
    "resolved": "Resolved",
    "closed": "Closed",
    "cancelled": "Cancelled",
}

_JIRA_TO_TICKET_STATUS: dict[str, str] = {
    "open": "new",
    "in progress": "in_progress",
    "waiting for customer": "pending_client",
    "waiting for support": "pending_third",
    "resolved": "resolved",
    "closed": "closed",
    "done": "resolved",
}

# ── HTTP client helpers ────────────────────────────────────────────────────────


def _jira_client(config: JiraConfig) -> httpx.Client:
    """Build an authenticated httpx client for Jira Cloud REST API."""
    import base64
    token_b64 = config.jira_api_token_enc  # service layer handles decrypt externally
    # Basic auth: email:token base64-encoded
    creds = base64.b64encode(f"{config.jira_email}:{token_b64}".encode()).decode()
    return httpx.Client(
        base_url=config.jira_base_url.rstrip("/"),
        headers={
            "Authorization": f"Basic {creds}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=15.0,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────


def _resolve_priority(config: JiraConfig, ticket_priority: str) -> str:
    pmap = json.loads(config.priority_map_json) if config.priority_map_json else {}
    merged = {**_DEFAULT_PRIORITY_MAP, **pmap}
    return merged.get(ticket_priority, "Medium")


def _resolve_status_to_jira(config: JiraConfig, ticket_status: str) -> str:
    smap = json.loads(config.status_map_json) if config.status_map_json else {}
    merged = {**_DEFAULT_STATUS_MAP, **smap}
    return merged.get(ticket_status, "Open")


def _resolve_issue_type(config: JiraConfig, ticket_type: str) -> str:
    mapping = {
        "incident": config.jira_issue_type_incident,
        "service_request": config.jira_issue_type_service_request,
        "change": config.jira_issue_type_change,
        "problem": config.jira_issue_type_problem,
    }
    return mapping.get(ticket_type, "Incident")


def _build_issue_body(config: JiraConfig, ticket: Ticket, field_maps: list[JiraFieldMap]) -> dict:
    fields: dict = {
        "project": {"key": config.jira_project_key},
        "summary": f"[CF-{ticket.number}] {ticket.title}",
        "description": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": ticket.description or ""}],
                }
            ],
        },
        "issuetype": {"name": _resolve_issue_type(config, ticket.ticket_type.value)},
        "priority": {"name": _resolve_priority(config, ticket.priority.value)},
    }
    # Apply custom field maps
    for fm in field_maps:
        if not fm.is_active:
            continue
        val = getattr(ticket, fm.contecflow_field, None)
        if val is not None:
            fields[fm.jira_field_id] = str(val)
    return {"fields": fields}


def _write_log(
    db: Session,
    config_id: str,
    ticket_id: Optional[str],
    jira_key: Optional[str],
    event_type: JiraSyncEventType,
    direction: JiraSyncDirection,
    payload: Optional[dict],
    response: Optional[dict],
    success: bool,
    error: Optional[str] = None,
) -> None:
    log = JiraSyncLog(
        config_id=config_id,
        ticket_id=ticket_id,
        jira_issue_key=jira_key,
        event_type=event_type,
        direction=direction,
        payload_json=json.dumps(payload) if payload else None,
        response_json=json.dumps(response) if response else None,
        success=success,
        error_message=error,
    )
    db.add(log)
    # No commit here — caller handles transaction


# ── Push: Contecflow → Jira ────────────────────────────────────────────────────


def push_ticket_to_jira(db: Session, config: JiraConfig, ticket: Ticket) -> JiraSyncMap:
    """
    Create or update a Jira issue from a Contecflow ticket.
    Returns the JiraSyncMap entry (created or updated).
    """
    field_maps: list[JiraFieldMap] = (
        db.query(JiraFieldMap)
        .filter(JiraFieldMap.config_id == config.id, JiraFieldMap.is_active == True)
        .all()
    )

    existing_map: Optional[JiraSyncMap] = (
        db.query(JiraSyncMap)
        .filter(JiraSyncMap.config_id == config.id, JiraSyncMap.ticket_id == ticket.id)
        .first()
    )

    body = _build_issue_body(config, ticket, field_maps)

    try:
        with _jira_client(config) as client:
            if existing_map and existing_map.jira_issue_key:
                # UPDATE existing issue
                resp = client.put(
                    f"/rest/api/3/issue/{existing_map.jira_issue_key}",
                    content=json.dumps(body),
                )
                resp.raise_for_status()
                response_data = resp.json() if resp.content else {}
                jira_key = existing_map.jira_issue_key
                event = JiraSyncEventType.updated
            else:
                # CREATE new issue
                resp = client.post("/rest/api/3/issue", content=json.dumps(body))
                resp.raise_for_status()
                response_data = resp.json()
                jira_key = response_data.get("key", "")
                event = JiraSyncEventType.created

                existing_map = JiraSyncMap(
                    config_id=config.id,
                    ticket_id=ticket.id,
                    jira_issue_key=jira_key,
                    jira_issue_id=response_data.get("id"),
                )
                db.add(existing_map)

        existing_map.sync_status = JiraSyncStatus.synced
        existing_map.last_synced_at = datetime.now(timezone.utc)
        existing_map.last_ticket_updated_at = ticket.updated_at or ticket.created_at
        existing_map.sync_error = None

        _write_log(
            db, config.id, ticket.id, jira_key, event,
            JiraSyncDirection.contecflow_to_jira, body, response_data, True,
        )
        db.flush()
        return existing_map

    except httpx.HTTPStatusError as exc:
        error_msg = f"HTTP {exc.response.status_code}: {exc.response.text[:500]}"
        logger.error("Jira push failed for ticket %s: %s", ticket.number, error_msg)
        if existing_map:
            existing_map.sync_status = JiraSyncStatus.error
            existing_map.sync_error = error_msg
        _write_log(
            db, config.id, ticket.id, None, JiraSyncEventType.error,
            JiraSyncDirection.contecflow_to_jira, body, None, False, error_msg,
        )
        db.flush()
        raise
    except Exception as exc:
        error_msg = str(exc)
        logger.exception("Unexpected Jira push error for ticket %s", ticket.number)
        _write_log(
            db, config.id, ticket.id, None, JiraSyncEventType.error,
            JiraSyncDirection.contecflow_to_jira, body, None, False, error_msg,
        )
        db.flush()
        raise


def push_comment_to_jira(
    db: Session, config: JiraConfig, sync_map: JiraSyncMap, comment: TicketComment
) -> None:
    """Sync a public comment from Contecflow to the linked Jira issue."""
    if not config.sync_comments:
        return

    body = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": f"[Contecflow] {comment.body}"}
                    ],
                }
            ],
        }
    }

    try:
        with _jira_client(config) as client:
            resp = client.post(
                f"/rest/api/3/issue/{sync_map.jira_issue_key}/comment",
                content=json.dumps(body),
            )
            resp.raise_for_status()
        _write_log(
            db, config.id, comment.ticket_id, sync_map.jira_issue_key,
            JiraSyncEventType.comment_synced, JiraSyncDirection.contecflow_to_jira,
            {"comment_id": comment.id}, None, True,
        )
    except Exception as exc:
        _write_log(
            db, config.id, comment.ticket_id, sync_map.jira_issue_key,
            JiraSyncEventType.error, JiraSyncDirection.contecflow_to_jira,
            {"comment_id": comment.id}, None, False, str(exc),
        )
        logger.warning("Failed to push comment to Jira: %s", exc)


# ── Pull: Jira → Contecflow ────────────────────────────────────────────────────


def pull_jira_issue(
    db: Session, config: JiraConfig, jira_issue_key: str
) -> Optional[dict]:
    """Fetch a single Jira issue and return its fields dict."""
    try:
        with _jira_client(config) as client:
            resp = client.get(f"/rest/api/3/issue/{jira_issue_key}")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("Failed to pull Jira issue %s: %s", jira_issue_key, exc)
        return None


def apply_jira_update_to_ticket(
    db: Session,
    config: JiraConfig,
    sync_map: JiraSyncMap,
    jira_fields: dict,
) -> None:
    """
    Apply changes from a Jira issue onto the linked Contecflow ticket.
    Only updates fields allowed by the config sync flags.
    """
    ticket: Optional[Ticket] = db.query(Ticket).filter(
        Ticket.id == sync_map.ticket_id
    ).first()
    if not ticket:
        logger.warning("Ticket %s not found for Jira sync map %s", sync_map.ticket_id, sync_map.id)
        return

    changed = False

    if config.sync_status_changes:
        jira_status = (jira_fields.get("status", {}).get("name") or "").lower()
        mapped = _JIRA_TO_TICKET_STATUS.get(jira_status)
        if mapped and mapped != ticket.status.value:
            ticket.status = TicketStatus(mapped)
            changed = True

    if config.sync_priority_changes:
        jira_priority = (jira_fields.get("priority", {}).get("name") or "").lower()
        reverse_map = {v.lower(): k for k, v in _DEFAULT_PRIORITY_MAP.items()}
        if config.priority_map_json:
            custom = json.loads(config.priority_map_json)
            reverse_map.update({v.lower(): k for k, v in custom.items()})
        mapped_p = reverse_map.get(jira_priority)
        if mapped_p and mapped_p != ticket.priority.value:
            ticket.priority = TicketPriority(mapped_p)
            changed = True

    if changed:
        sync_map.last_synced_at = datetime.now(timezone.utc)
        sync_map.last_jira_updated_at = datetime.now(timezone.utc)
        sync_map.sync_status = JiraSyncStatus.synced
        _write_log(
            db, config.id, ticket.id, sync_map.jira_issue_key,
            JiraSyncEventType.updated, JiraSyncDirection.jira_to_contecflow,
            jira_fields, None, True,
        )
        db.flush()


# ── Polling loop (called by Celery beat) ──────────────────────────────────────


def run_incremental_sync(db: Session, config_id: str) -> dict:
    """
    Poll all active sync maps for a config and reconcile divergent state.
    Returns summary: {"synced": N, "errors": N, "skipped": N}
    """
    config: Optional[JiraConfig] = db.query(JiraConfig).filter(
        JiraConfig.id == config_id, JiraConfig.is_active == True
    ).first()
    if not config:
        return {"synced": 0, "errors": 0, "skipped": 0}

    maps: list[JiraSyncMap] = (
        db.query(JiraSyncMap)
        .filter(JiraSyncMap.config_id == config_id)
        .all()
    )

    stats = {"synced": 0, "errors": 0, "skipped": 0}

    for sm in maps:
        try:
            jira_data = pull_jira_issue(db, config, sm.jira_issue_key)
            if not jira_data:
                stats["skipped"] += 1
                continue

            jira_fields = jira_data.get("fields", {})
            jira_updated_str = jira_data.get("fields", {}).get("updated")
            if jira_updated_str:
                from dateutil import parser as dtparser
                jira_updated = dtparser.parse(jira_updated_str)
                if sm.last_jira_updated_at and jira_updated <= sm.last_jira_updated_at:
                    stats["skipped"] += 1
                    continue

            if config.sync_direction in (
                JiraSyncDirection.bidirectional,
                JiraSyncDirection.jira_to_contecflow,
            ):
                apply_jira_update_to_ticket(db, config, sm, jira_fields)

            stats["synced"] += 1
        except Exception as exc:
            logger.exception("Sync error for map %s: %s", sm.id, exc)
            sm.sync_status = JiraSyncStatus.error
            sm.sync_error = str(exc)[:500]
            stats["errors"] += 1

    db.commit()
    return stats
