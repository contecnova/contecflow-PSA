"""scheduled_reports.py — Lógica de ejecución de informes programados BI.

Tipos de informe:
  executive_summary  KPIs OLAP + narrativa IA opcional
  utilization        Utilización por usuario (OLAP)
  pipeline           Funnel de pipeline (OLAP)
  portfolio          Salud del portfolio (OLAP)
  custom             Métrica analytics clásica (compatibilidad previa)

Canales de distribución:
  Email (SMTP)       — siempre intentado si recipients no vacío
  Slack              — si slack_webhook está configurado en el informe

Invocado por Celery beat cada hora: app.worker.run_scheduled_reports
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings
from app.models.billing_reports import ScheduledReport

logger = logging.getLogger("contecflow.scheduled_reports")


# ── Scheduling helpers ────────────────────────────────────────────────────────

def _get_next_run(frequency: str, from_dt: Optional[datetime] = None) -> datetime:
    base = from_dt or datetime.now(timezone.utc)
    if frequency == "daily":
        return base + timedelta(days=1)
    if frequency == "weekly":
        return base + timedelta(weeks=1)
    if frequency == "monthly":
        if base.month == 12:
            return base.replace(year=base.year + 1, month=1, day=1, hour=8, minute=0, second=0, microsecond=0)
        return base.replace(month=base.month + 1, day=1, hour=8, minute=0, second=0, microsecond=0)
    return base + timedelta(weeks=1)


# ── Email sender ──────────────────────────────────────────────────────────────

def _send_email(recipients: list[str], subject: str, html_body: str, pdf_bytes: bytes, filename: str) -> None:
    import smtplib
    from email import encoders
    from email.mime.base import MIMEBase
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    smtp_host = settings.SMTP_HOST
    smtp_user = settings.SMTP_USER
    if not smtp_host or not smtp_user:
        logger.warning("[SMTP no configurado] Informe '%s' generado (%d bytes) para: %s",
                       filename, len(pdf_bytes), recipients)
        return

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM or smtp_user
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    pdf_part = MIMEBase("application", "pdf")
    pdf_part.set_payload(pdf_bytes)
    encoders.encode_base64(pdf_part)
    pdf_part.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(pdf_part)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASS)
        server.sendmail(msg["From"], recipients, msg.as_string())

    logger.info("Email sent: %s → %s", subject, recipients)


# ── Slack sender ──────────────────────────────────────────────────────────────

def _send_slack(webhook_url: str, report_name: str, report_type: str, kpis: dict) -> None:
    """Post a summary block to a Slack incoming webhook."""
    try:
        import urllib.request
        import urllib.error

        type_emoji = {
            "executive_summary": ":bar_chart:",
            "utilization": ":busts_in_silhouette:",
            "pipeline": ":mega:",
            "portfolio": ":briefcase:",
            "custom": ":page_facing_up:",
        }
        emoji = type_emoji.get(report_type, ":page_facing_up:")

        lines = [f"{emoji} *{report_name}*"]
        if kpis:
            if kpis.get("active_projects") is not None:
                lines.append(f"• Proyectos activos: *{kpis['active_projects']}*")
            if kpis.get("avg_margin_pct") is not None:
                lines.append(f"• Margen medio: *{kpis['avg_margin_pct']}%*")
            if kpis.get("pipeline_weighted") is not None:
                lines.append(f"• Pipeline ponderado: *€{kpis['pipeline_weighted']:,.0f}*")
            if kpis.get("hours_mtd") is not None:
                lines.append(f"• Horas imputadas (mes): *{kpis['hours_mtd']}h*")
            if kpis.get("billability_pct") is not None:
                lines.append(f"• Facturabilidad: *{kpis['billability_pct']}%*")
        lines.append(f"_Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')} UTC_")

        payload = {"text": "\n".join(lines)}
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            webhook_url, data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info("Slack notification sent for '%s': %s", report_name, resp.status)
    except Exception as exc:
        logger.warning("Slack send failed for '%s': %s", report_name, exc)


# ── HTML email body ───────────────────────────────────────────────────────────

def _build_html_body(report_name: str, report_type: str, frequency: str, next_run: datetime) -> str:
    type_label = {
        "executive_summary": "Resumen Ejecutivo",
        "utilization": "Utilización del equipo",
        "pipeline": "Pipeline comercial",
        "portfolio": "Portfolio de proyectos",
        "custom": "Informe personalizado",
    }.get(report_type, report_type)

    return f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
  <div style="background:#0f172a;padding:24px;border-radius:8px 8px 0 0;">
    <h1 style="color:#4f8ef7;margin:0;font-size:18px;">ContecFlow — Informe Programado</h1>
  </div>
  <div style="background:#f8fafc;padding:24px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;">
    <h2 style="color:#1e293b;margin:0 0 12px;">{report_name}</h2>
    <p style="color:#64748b;margin:0 0 8px;">Tipo: <strong>{type_label}</strong></p>
    <p style="color:#64748b;">
      Generado el {datetime.now().strftime('%d/%m/%Y a las %H:%M')} UTC.
      Se adjunta el informe en PDF.
    </p>
    <p style="color:#64748b;font-size:13px;">
      Frecuencia: <strong>{frequency}</strong> ·
      Próximo envío: <strong>{next_run.strftime('%d/%m/%Y')}</strong>
    </p>
    <hr style="border:none;border-top:1px solid #e2e8f0;margin:16px 0;">
    <p style="color:#94a3b8;font-size:11px;">
      Informe generado automáticamente por ContecFlow.
      Para modificar la configuración accede a Analytics &amp; BI → Reports.
    </p>
  </div>
</div>
"""


# ── Core executor ─────────────────────────────────────────────────────────────

def _execute_report(report: ScheduledReport, db) -> None:
    """Generate PDF and distribute via email + Slack."""
    report_type = getattr(report, "report_type", None) or "custom"
    include_narrative = getattr(report, "include_narrative", False)
    slack_webhook = getattr(report, "slack_webhook", None)

    # Resolve recipients
    recipients: list[str] = []
    try:
        recipients = json.loads(report.recipients or "[]")
    except Exception:
        logger.warning("No se pudieron parsear los destinatarios del informe '%s'", report.name)
    try:
        extra = json.loads(getattr(report, "recipients_extra", None) or "[]")
        recipients = list(dict.fromkeys(recipients + extra))  # deduplicate, preserve order
    except Exception:
        logger.warning("No se pudieron parsear los destinatarios extra del informe '%s'", report.name)

    # Org context (report created_by user's org)
    org_id: Optional[str] = None
    try:
        from app.models.user import User
        creator = db.query(User).filter(User.id == report.created_by).first()
        if creator:
            org_id = getattr(creator, "organization_id", None)
    except Exception:
        logger.exception("Error resolviendo organización del creador del informe '%s'", report.name)

    # Fetch OLAP KPIs for Slack summary (always, even if no email)
    kpis: dict = {}
    try:
        from app.services.olap.query_engine import get_kpi_summary
        kpis = get_kpi_summary(org_id)
    except Exception:
        logger.warning("Fallo obteniendo KPIs OLAP para el informe '%s'", report.name)

    # Generate PDF
    pdf_bytes: bytes = b""
    try:
        from app.services.report_pdf_service import build_report_pdf
        pdf_bytes = build_report_pdf(report, db, org_id=org_id)
    except Exception as exc:
        logger.error("PDF generation failed for '%s': %s", report.name, exc, exc_info=True)
        # Fallback to legacy PDF
        try:
            from app.services.report_pdf import generate_report_pdf as _legacy
            pdf_bytes = _legacy(
                title=report.name,
                metric_label=report_type.replace("_", " ").title(),
                data=[], summary={}, filters={},
            )
        except Exception:
            logger.exception("Legacy PDF fallback also failed for report '%s'", report.name)
            pdf_bytes = b""

    safe_name = report.name.replace(" ", "_")[:40]
    filename = f"ContecFlow_{safe_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    subject = f"[ContecFlow] {report.name} — {datetime.now().strftime('%d/%m/%Y')}"
    next_run = _get_next_run(report.frequency)

    # Email delivery
    if recipients and pdf_bytes:
        html_body = _build_html_body(report.name, report_type, report.frequency, next_run)
        try:
            _send_email(recipients, subject, html_body, pdf_bytes, filename)
        except Exception as exc:
            logger.error("Email delivery failed for '%s': %s", report.name, exc)
            raise

    # Slack delivery
    if slack_webhook:
        _send_slack(slack_webhook, report.name, report_type, kpis)


# ── Public API ────────────────────────────────────────────────────────────────

def run_due_reports() -> None:
    """Execute all scheduled reports whose next_run_at is due. Called hourly by Celery."""
    try:
        from app.db.session import SessionLocal
        db = SessionLocal()
        now = datetime.now(timezone.utc)

        try:
            reports = db.query(ScheduledReport).filter(
                ScheduledReport.is_active.is_(True),
                (ScheduledReport.next_run_at.is_(None)) | (ScheduledReport.next_run_at <= now),
            ).all()

            for report in reports:
                try:
                    _execute_report(report, db)
                    report.last_run_at = now
                    report.next_run_at = _get_next_run(report.frequency, now)
                    report.last_status = "success"
                    report.last_error = None
                    db.commit()
                    logger.info("Report '%s' (%s) sent OK", report.name, getattr(report, "report_type", "custom"))
                except Exception as exc:
                    report.last_status = "error"
                    report.last_error = str(exc)[:500]
                    try:
                        db.commit()
                    except Exception:
                        logger.exception("Fallo persistiendo estado de error del informe '%s'", report.name)
                        db.rollback()
                    logger.error("Report '%s' failed: %s", report.name, exc, exc_info=True)
        finally:
            db.close()

    except Exception as exc:
        logger.error("run_due_reports crashed: %s", exc, exc_info=True)


def execute_report_now(report_id: str, db) -> dict:
    """Execute a single report immediately (called from the /run endpoint)."""
    report = db.query(ScheduledReport).filter(ScheduledReport.id == report_id).first()
    if not report:
        return {"ok": False, "error": "Informe no encontrado"}
    try:
        _execute_report(report, db)
        report.last_run_at = datetime.now(timezone.utc)
        report.last_status = "success"
        report.last_error = None
        db.commit()
        recipients = []
        try:
            recipients = json.loads(report.recipients or "[]")
        except Exception:
            logger.warning("No se pudieron parsear los destinatarios del informe '%s'", report.name)
        return {"ok": True, "recipients": recipients, "report_type": getattr(report, "report_type", "custom")}
    except Exception as exc:
        report.last_status = "error"
        report.last_error = str(exc)[:500]
        try:
            db.commit()
        except Exception:
            logger.exception("Fallo persistiendo estado de error del informe '%s'", report.name)
            db.rollback()
        return {"ok": False, "error": str(exc)}
