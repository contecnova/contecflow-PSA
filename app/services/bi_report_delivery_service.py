"""BI Report Scheduled Delivery service.

Provides multi-channel scheduled delivery of BI reports:
  - Email (SMTP via existing email template system)
  - Slack (incoming webhook)
  - Microsoft Teams (incoming webhook — Adaptive Card)
  - PDF export (ReportLab, fallback to plain text)
  - Excel export (openpyxl)

Delivery schedules are stored as AppSetting JSON blobs scoped by org_id.
A Celery beat task (`bi_scheduled_delivery_run`) evaluates due schedules
every hour and dispatches pending deliveries.

AppSetting key: ``bi.delivery.schedules.<org_id>``
"""
from __future__ import annotations

import io
import json
import logging
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting

logger = logging.getLogger(__name__)

SCHEDULES_KEY_TPL = "bi.delivery.schedules"
DELIVERY_LOG_KEY_TPL = "bi.delivery.log"
DELIVERY_SNAPSHOT_KEY_TPL = "bi.delivery.snapshot"

VALID_CHANNELS = {"email", "slack", "teams"}
VALID_FORMATS = {"json", "csv", "xlsx", "pdf"}
VALID_FREQUENCIES = {"hourly", "daily", "weekly", "monthly"}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _setting_row(db: Session, key: str, organization_id: Optional[str]) -> Optional[AppSetting]:
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if organization_id:
        q = q.filter(AppSetting.organization_id == organization_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    return q.first()


def _get_json(db: Session, key: str, organization_id: Optional[str], default: Any = None) -> Any:
    row = _setting_row(db, key, organization_id)
    if not row or not row.value:
        return default if default is not None else {}
    try:
        return json.loads(row.value)
    except Exception:
        logger.warning("Failed to decode JSON for AppSetting key=%s org=%s", key, organization_id, exc_info=True)
        return default if default is not None else {}


def _set_json(db: Session, key: str, organization_id: Optional[str], value: Any, description: str) -> None:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    row = _setting_row(db, key, organization_id)
    if not row:
        row = AppSetting(key=key, organization_id=organization_id, description=description, value=payload)
        db.add(row)
    else:
        row.value = payload
    db.commit()


def _snapshot_key(schedule_id: str) -> str:
    return f"{DELIVERY_SNAPSHOT_KEY_TPL}.{schedule_id}"


def _normalize_row(row: Dict[str, Any], columns: List[str]) -> Dict[str, Any]:
    return {c: row.get(c) for c in columns}


def _row_token(row: Dict[str, Any], columns: List[str]) -> str:
    payload = json.dumps(_normalize_row(row, columns), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _report_fingerprint(columns: List[str], rows: List[Dict[str, Any]]) -> str:
    tokens = sorted(_row_token(r, columns) for r in rows)
    payload = json.dumps({"columns": columns, "tokens": tokens}, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _compute_report_diff(
    previous: Optional[Dict[str, Any]],
    columns: List[str],
    rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    current_fp = _report_fingerprint(columns, rows)
    current_tokens = sorted(_row_token(r, columns) for r in rows)
    current_set = set(current_tokens)

    prev_fp = None
    prev_tokens: List[str] = []
    if previous and isinstance(previous, dict):
        prev_fp = previous.get("fingerprint")
        prev_tokens = list(previous.get("row_tokens") or [])
    prev_set = set(prev_tokens)

    added = sorted(current_set - prev_set)
    removed = sorted(prev_set - current_set)

    has_changes = prev_fp is None or prev_fp != current_fp
    return {
        "has_changes": has_changes,
        "previous_exists": prev_fp is not None,
        "previous_fingerprint": prev_fp,
        "current_fingerprint": current_fp,
        "previous_row_count": len(prev_tokens),
        "current_row_count": len(current_tokens),
        "added_rows": len(added),
        "removed_rows": len(removed),
        "added_samples": added[:10],
        "removed_samples": removed[:10],
    }


def _build_snapshot(columns: List[str], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    row_tokens = sorted(_row_token(r, columns) for r in rows)
    return {
        "captured_at": _iso_now(),
        "columns": columns,
        "row_count": len(rows),
        "row_tokens": row_tokens,
        "fingerprint": _report_fingerprint(columns, rows),
    }


def _append_delivery_log(
    db: Session,
    *,
    organization_id: Optional[str],
    entry: Dict[str, Any],
) -> None:
    logs = _get_json(db, DELIVERY_LOG_KEY_TPL, organization_id, default=[])
    if not isinstance(logs, list):
        logs = []
    logs.append(entry)
    logs = logs[-300:]
    _set_json(
        db,
        DELIVERY_LOG_KEY_TPL,
        organization_id,
        logs,
        description="BI scheduled delivery execution log (JSON)",
    )


# ── Schedule CRUD ──────────────────────────────────────────────────────────────

def list_schedules(db: Session, *, organization_id: Optional[str]) -> List[Dict[str, Any]]:
    schedules = _get_json(db, SCHEDULES_KEY_TPL, organization_id, default={})
    return sorted(schedules.values(), key=lambda s: s.get("created_at", ""), reverse=True)


def get_schedule(db: Session, *, organization_id: Optional[str], schedule_id: str) -> Dict[str, Any]:
    schedules = _get_json(db, SCHEDULES_KEY_TPL, organization_id, default={})
    sched = schedules.get(schedule_id)
    if not sched:
        raise ValueError("schedule_not_found")
    return sched


def create_schedule(
    db: Session,
    *,
    organization_id: Optional[str],
    name: str,
    report_preset_id: str,
    channels: List[str],
    recipients: List[str],
    frequency: str,
    cron_expression: Optional[str] = None,
    export_format: str = "xlsx",
    slack_webhook_url: Optional[str] = None,
    teams_webhook_url: Optional[str] = None,
    is_active: bool = True,
    send_only_on_change: bool = False,
) -> Dict[str, Any]:
    _validate_channels(channels)
    _validate_format(export_format)
    _validate_frequency(frequency)

    schedules = _get_json(db, SCHEDULES_KEY_TPL, organization_id, default={})
    schedule_id = str(uuid.uuid4())
    schedule = {
        "id": schedule_id,
        "name": name,
        "report_preset_id": report_preset_id,
        "channels": channels,
        "recipients": recipients,
        "frequency": frequency,
        "cron_expression": cron_expression,
        "export_format": export_format,
        "slack_webhook_url": slack_webhook_url,
        "teams_webhook_url": teams_webhook_url,
        "is_active": is_active,
        "send_only_on_change": bool(send_only_on_change),
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
        "last_run_at": None,
        "last_status": None,
        "error_count": 0,
    }
    schedules[schedule_id] = schedule
    _set_json(db, SCHEDULES_KEY_TPL, organization_id, schedules,
              description="BI scheduled delivery configs (JSON)")
    return schedule


def update_schedule(
    db: Session,
    *,
    organization_id: Optional[str],
    schedule_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    schedules = _get_json(db, SCHEDULES_KEY_TPL, organization_id, default={})
    sched = schedules.get(schedule_id)
    if not sched:
        raise ValueError("schedule_not_found")

    allowed = {
        "name", "channels", "recipients", "frequency", "cron_expression",
        "export_format", "slack_webhook_url", "teams_webhook_url", "is_active",
        "report_preset_id", "send_only_on_change",
    }
    for field in allowed:
        if field in payload:
            sched[field] = payload[field]

    if "channels" in payload:
        _validate_channels(sched["channels"])
    if "export_format" in payload:
        _validate_format(sched["export_format"])

    sched["updated_at"] = _iso_now()
    schedules[schedule_id] = sched
    _set_json(db, SCHEDULES_KEY_TPL, organization_id, schedules,
              description="BI scheduled delivery configs (JSON)")
    return sched


def delete_schedule(db: Session, *, organization_id: Optional[str], schedule_id: str) -> bool:
    schedules = _get_json(db, SCHEDULES_KEY_TPL, organization_id, default={})
    if schedule_id not in schedules:
        raise ValueError("schedule_not_found")
    del schedules[schedule_id]
    _set_json(db, SCHEDULES_KEY_TPL, organization_id, schedules,
              description="BI scheduled delivery configs (JSON)")
    return True


# ── Validation helpers ─────────────────────────────────────────────────────────

def _validate_channels(channels: List[str]) -> None:
    invalid = [c for c in channels if c not in VALID_CHANNELS]
    if invalid:
        raise ValueError(f"Invalid channels: {invalid}. Supported: {VALID_CHANNELS}")


def _validate_format(fmt: str) -> None:
    if fmt not in VALID_FORMATS:
        raise ValueError(f"Invalid format: {fmt!r}. Supported: {VALID_FORMATS}")


def _validate_frequency(freq: str) -> None:
    if freq not in VALID_FREQUENCIES:
        raise ValueError(f"Invalid frequency: {freq!r}. Supported: {VALID_FREQUENCIES}")


# ── Export helpers ─────────────────────────────────────────────────────────────

def _export_to_excel(columns: List[str], rows: List[Dict], sheet_name: str = "Report") -> bytes:
    """Generate Excel file bytes using openpyxl."""
    try:
        from openpyxl import Workbook  # type: ignore
        from openpyxl.styles import Font, PatternFill, Alignment  # type: ignore
    except ImportError:
        raise ImportError("pip install openpyxl")

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]  # Excel sheet name limit

    # Header row with styling
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for col_idx, col_name in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    for row_idx, row in enumerate(rows, start=2):
        for col_idx, col_name in enumerate(columns, start=1):
            ws.cell(row=row_idx, column=col_idx, value=row.get(col_name))

    # Auto-width columns
    for column in ws.columns:
        max_length = max((len(str(cell.value or "")) for cell in column), default=0)
        ws.column_dimensions[column[0].column_letter].width = min(max_length + 2, 50)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _export_to_pdf(title: str, columns: List[str], rows: List[Dict]) -> bytes:
    """Generate PDF bytes using ReportLab (falls back to plain text if unavailable)."""
    try:
        from reportlab.lib.pagesizes import A4, landscape  # type: ignore
        from reportlab.lib import colors  # type: ignore
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer  # type: ignore
        from reportlab.lib.styles import getSampleStyleSheet  # type: ignore

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4))
        styles = getSampleStyleSheet()
        elems = []

        elems.append(Paragraph(title, styles["Title"]))
        elems.append(Spacer(1, 12))

        table_data = [columns]
        for row in rows[:500]:  # Cap at 500 rows for PDF readability
            table_data.append([str(row.get(c, "")) for c in columns])

        tbl = Table(table_data, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elems.append(tbl)
        doc.build(elems)
        return buf.getvalue()

    except ImportError:
        # Fallback: plain-text representation
        lines = [title, "=" * len(title), "\t".join(columns)]
        for row in rows[:200]:
            lines.append("\t".join(str(row.get(c, "")) for c in columns))
        return "\n".join(lines).encode("utf-8")


# ── Channel senders ────────────────────────────────────────────────────────────

def _send_slack(webhook_url: str, title: str, summary: str, report_url: Optional[str] = None) -> bool:
    """Post a Slack message via incoming webhook."""
    try:
        import httpx  # type: ignore
    except ImportError:
        raise ImportError("pip install httpx")

    blocks: List[Dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📊 {title}", "emoji": True},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": summary},
        },
    ]
    if report_url:
        blocks.append({
            "type": "actions",
            "elements": [{"type": "button", "text": {"type": "plain_text", "text": "Ver informe"}, "url": report_url}],
        })

    payload = {"blocks": blocks}
    resp = httpx.post(webhook_url, json=payload, timeout=10.0)
    return resp.status_code == 200


def _send_teams(webhook_url: str, title: str, summary: str, report_url: Optional[str] = None) -> bool:
    """Post an Adaptive Card to Microsoft Teams via incoming webhook."""
    try:
        import httpx  # type: ignore
    except ImportError:
        raise ImportError("pip install httpx")

    # Teams Adaptive Card 1.2 format
    card: Dict = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {"type": "TextBlock", "size": "Medium", "weight": "Bolder", "text": f"📊 {title}"},
                        {"type": "TextBlock", "text": summary, "wrap": True},
                    ],
                    "actions": (
                        [{"type": "Action.OpenUrl", "title": "Ver informe", "url": report_url}]
                        if report_url
                        else []
                    ),
                },
            }
        ],
    }

    resp = httpx.post(webhook_url, json=card, timeout=10.0)
    return resp.status_code in (200, 202)


def _send_email(recipients: List[str], subject: str, body_html: str, attachment_bytes: Optional[bytes] = None,
                attachment_filename: Optional[str] = None) -> bool:
    """Send email using existing email infrastructure."""
    try:
        from app.services.email_service import send_email  # type: ignore
        for recipient in recipients:
            send_email(to=recipient, subject=subject, body_html=body_html)
        return True
    except Exception:
        logger.warning("Primary email_service path failed; falling back to direct SMTP", exc_info=True)
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from email.mime.application import MIMEApplication
            from app.core.config import settings  # type: ignore

            smtp_host = getattr(settings, "SMTP_HOST", None)
            smtp_port = int(getattr(settings, "SMTP_PORT", 587))
            smtp_user = getattr(settings, "SMTP_USER", None)
            smtp_pass = getattr(settings, "SMTP_PASSWORD", None)
            from_addr = getattr(settings, "EMAILS_FROM_EMAIL", smtp_user or "noreply@contecflow.com")

            if not smtp_host:
                logger.warning("SMTP not configured — email delivery skipped")
                return False

            msg = MIMEMultipart()
            msg["From"] = from_addr
            msg["Subject"] = subject
            msg.attach(MIMEText(body_html, "html"))
            if attachment_bytes and attachment_filename:
                part = MIMEApplication(attachment_bytes)
                part["Content-Disposition"] = f'attachment; filename="{attachment_filename}"'
                msg.attach(part)

            with smtplib.SMTP(smtp_host, smtp_port) as smtp:
                smtp.starttls()
                if smtp_user and smtp_pass:
                    smtp.login(smtp_user, smtp_pass)
                for recipient in recipients:
                    msg["To"] = recipient
                    smtp.sendmail(from_addr, recipient, msg.as_string())
            return True
        except Exception as exc:
            logger.error("Email delivery failed: %s", exc)
            return False


# ── Delivery execution ────────────────────────────────────────────────────────

def send_schedule_now(
    db: Session,
    *,
    organization_id: Optional[str],
    schedule_id: str,
) -> Dict[str, Any]:
    """Execute a single scheduled delivery immediately."""
    from app.services.bi_report_builder_v2_service import preview_preset  # type: ignore

    sched = get_schedule(db, organization_id=organization_id, schedule_id=schedule_id)
    preset_id = sched.get("report_preset_id", "")
    export_format = sched.get("export_format", "xlsx")
    title = sched.get("name", preset_id)
    channels = sched.get("channels", [])
    recipients = sched.get("recipients", [])
    send_only_on_change = bool(sched.get("send_only_on_change", False))

    started_at = _iso_now()
    errors: List[str] = []
    results: Dict[str, Any] = {}

    # Generate report data
    try:
        report_data = preview_preset(db, organization_id=organization_id, preset_id=preset_id, limit=5000)
        columns = report_data.get("columns") or []
        rows = report_data.get("rows") or []
    except Exception as exc:
        logger.exception("Failed to generate report preview for preset=%s org=%s", preset_id, organization_id)
        errors.append(f"report_generation: {exc}")
        columns, rows = [], []

    prev_snapshot = _get_json(
        db,
        _snapshot_key(schedule_id),
        organization_id,
        default=None,
    )
    diff = _compute_report_diff(prev_snapshot, columns, rows)
    skipped_no_changes = bool(send_only_on_change and not diff.get("has_changes"))

    # Generate attachment
    attachment_bytes: Optional[bytes] = None
    attachment_filename: Optional[str] = None
    try:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        if export_format == "xlsx" and columns:
            attachment_bytes = _export_to_excel(columns, rows, sheet_name=title[:31])
            attachment_filename = f"{preset_id}_{ts}.xlsx"
        elif export_format == "pdf":
            attachment_bytes = _export_to_pdf(title, columns, rows)
            attachment_filename = f"{preset_id}_{ts}.pdf"
    except Exception as exc:
        logger.exception("Failed to generate report attachment for preset=%s format=%s", preset_id, export_format)
        errors.append(f"export_generation: {exc}")

    summary = (
        f"*{title}* — {len(rows)} registros generados el {_iso_now()[:10]}.\n"
        f"Formato: `{export_format}` | Filas: `{len(rows)}`"
    )

    if skipped_no_changes:
        for channel in channels:
            results[channel] = "skipped_no_changes"
    else:
        # Dispatch to each channel
        for channel in channels:
            try:
                if channel == "slack":
                    url = sched.get("slack_webhook_url", "")
                    if url:
                        ok = _send_slack(url, title=title, summary=summary)
                        results["slack"] = "ok" if ok else "failed"
                    else:
                        results["slack"] = "skipped_no_url"

                elif channel == "teams":
                    url = sched.get("teams_webhook_url", "")
                    if url:
                        ok = _send_teams(url, title=title, summary=summary)
                        results["teams"] = "ok" if ok else "failed"
                    else:
                        results["teams"] = "skipped_no_url"

                elif channel == "email":
                    if recipients:
                        body_html = f"<h2>📊 {title}</h2><p>{summary.replace(chr(10), '<br>')}</p>"
                        ok = _send_email(recipients, subject=f"[Contecflow BI] {title}", body_html=body_html,
                                         attachment_bytes=attachment_bytes, attachment_filename=attachment_filename)
                        results["email"] = "ok" if ok else "failed"
                    else:
                        results["email"] = "skipped_no_recipients"
            except Exception as exc:
                logger.exception("BI delivery channel %s failed for schedule=%s", channel, schedule_id)
                errors.append(f"{channel}: {exc}")
                results[channel] = "error"

    if not errors and columns:
        _set_json(
            db,
            _snapshot_key(schedule_id),
            organization_id,
            _build_snapshot(columns, rows),
            description="BI scheduled delivery last report snapshot (JSON)",
        )

    # Update schedule metadata
    schedules = _get_json(db, SCHEDULES_KEY_TPL, organization_id, default={})
    if schedule_id in schedules:
        schedules[schedule_id]["last_run_at"] = _iso_now()
        schedules[schedule_id]["last_status"] = "error" if errors else ("skipped_no_changes" if skipped_no_changes else "ok")
        schedules[schedule_id]["last_diff"] = diff
        if diff.get("has_changes"):
            schedules[schedule_id]["last_change_detected_at"] = _iso_now()
        if errors:
            schedules[schedule_id]["error_count"] = schedules[schedule_id].get("error_count", 0) + 1
        _set_json(db, SCHEDULES_KEY_TPL, organization_id, schedules,
                  description="BI scheduled delivery configs (JSON)")

    _append_delivery_log(
        db,
        organization_id=organization_id,
        entry={
            "schedule_id": schedule_id,
            "ok": not errors,
            "status": "error" if errors else ("skipped_no_changes" if skipped_no_changes else "ok"),
            "rows_delivered": len(rows),
            "results": results,
            "diff": diff,
            "timestamp": _iso_now(),
        },
    )

    return {
        "schedule_id": schedule_id,
        "ok": not errors,
        "send_only_on_change": send_only_on_change,
        "skipped_no_changes": skipped_no_changes,
        "diff": diff,
        "results": results,
        "rows_delivered": len(rows),
        "errors": errors,
        "started_at": started_at,
        "finished_at": _iso_now(),
    }


def get_schedule_report_diff(
    db: Session,
    *,
    organization_id: Optional[str],
    schedule_id: str,
) -> Dict[str, Any]:
    """Return diff between last sent snapshot and current report preview."""
    from app.services.bi_report_builder_v2_service import preview_preset  # type: ignore

    sched = get_schedule(db, organization_id=organization_id, schedule_id=schedule_id)
    preset_id = sched.get("report_preset_id", "")

    report_data = preview_preset(db, organization_id=organization_id, preset_id=preset_id, limit=5000)
    columns = report_data.get("columns") or []
    rows = report_data.get("rows") or []

    prev_snapshot = _get_json(
        db,
        _snapshot_key(schedule_id),
        organization_id,
        default=None,
    )
    return {
        "schedule_id": schedule_id,
        "preset_id": preset_id,
        "diff": _compute_report_diff(prev_snapshot, columns, rows),
        "checked_at": _iso_now(),
    }


def run_due_deliveries(db: Session) -> Dict[str, Any]:
    """Celery task handler: check all active schedules across all orgs and run due ones.

    A schedule is "due" if it has never run (last_run_at is None) or if the
    last run was more than N hours ago (based on frequency).
    """
    from app.models.settings import AppSetting as _AppSetting

    # Find all AppSetting rows matching the schedule key prefix
    rows = db.query(_AppSetting).filter(
        _AppSetting.key == SCHEDULES_KEY_TPL
    ).all()

    total_run = 0
    total_errors = 0

    for row in rows:
        org_id = row.organization_id
        try:
            schedules = json.loads(row.value or "{}")
        except Exception:
            logger.warning("Failed to decode BI schedules JSON for org=%s", org_id, exc_info=True)
            continue

        for sched in schedules.values():
            if not sched.get("is_active"):
                continue
            if not _is_schedule_due(sched):
                continue

            try:
                result = send_schedule_now(db, organization_id=org_id, schedule_id=sched["id"])
                if result.get("ok"):
                    total_run += 1
                else:
                    total_errors += 1
            except Exception as exc:
                logger.error("BI delivery error [org=%s, sched=%s]: %s", org_id, sched.get("id"), exc)
                total_errors += 1

    return {"total_run": total_run, "total_errors": total_errors, "checked_at": _iso_now()}


def _is_schedule_due(sched: Dict[str, Any]) -> bool:
    """Return True if the schedule should run now based on its frequency."""
    from datetime import timedelta

    last_run = sched.get("last_run_at")
    frequency = sched.get("frequency", "daily")
    now = datetime.now(timezone.utc)

    if not last_run:
        return True  # Never run — due immediately

    try:
        last_dt = datetime.fromisoformat(last_run)
    except Exception:
        logger.debug("Schedule has invalid last_run_at=%r; treating as due", last_run, exc_info=True)
        return True

    thresholds = {
        "hourly": timedelta(hours=1),
        "daily": timedelta(hours=24),
        "weekly": timedelta(days=7),
        "monthly": timedelta(days=30),
    }
    threshold = thresholds.get(frequency, timedelta(hours=24))
    return (now - last_dt) >= threshold
