"""
scheduled_reports.py — Lógica de ejecución de informes programados
Invocado por APScheduler cada hora para enviar informes vencidos.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from app.core.config import settings

logger = logging.getLogger("clarive.scheduled_reports")


def _get_next_run(frequency: str, from_dt: Optional[datetime] = None) -> datetime:
    """Calcula la próxima ejecución según la frecuencia."""
    base = from_dt or datetime.now(timezone.utc)
    if frequency == "daily":
        return base + timedelta(days=1)
    elif frequency == "weekly":
        return base + timedelta(weeks=1)
    elif frequency == "monthly":
        # Primer día del siguiente mes a las 08:00
        if base.month == 12:
            return base.replace(year=base.year+1, month=1, day=1, hour=8, minute=0, second=0)
        return base.replace(month=base.month+1, day=1, hour=8, minute=0, second=0)
    return base + timedelta(weeks=1)


def run_due_reports():
    """
    Ejecuta todos los informes programados que tienen next_run_at <= ahora.
    Llamado por APScheduler cada hora.
    """
    try:
        from app.db.session import SessionLocal
        from app.models.billing_reports import ScheduledReport
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        db = SessionLocal()
        now = datetime.now(timezone.utc)

        try:
            reports = db.query(ScheduledReport).filter(
                ScheduledReport.is_active == True,
                (ScheduledReport.next_run_at == None) | (ScheduledReport.next_run_at <= now)
            ).all()

            for report in reports:
                try:
                    _execute_report(report, db)
                    report.last_run_at = now
                    report.next_run_at = _get_next_run(report.frequency, now)
                    db.commit()
                    logger.info(f"Report '{report.name}' sent successfully")
                except Exception as e:
                    logger.error(f"Error executing report '{report.name}': {e}", exc_info=True)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Scheduler error in run_due_reports: {e}", exc_info=True)


def _execute_report(report, db):
    """Genera el PDF y envía el email."""
    from app.services.report_pdf import generate_report_pdf

    # Cargar filtros
    filters = {}
    try:
        filters = json.loads(report.filters_json or "{}")
    except Exception as e:
        logger.warning(f"Failed to parse report filters JSON: {e}")

    # Cargar destinatarios
    recipients = []
    try:
        recipients = json.loads(report.recipients or "[]")
    except Exception as e:
        logger.warning(f"Failed to parse report recipients JSON: {e}")

    if not recipients:
        return

    # Generar datos del informe via la API interna
    metric = report.metric or "hours_by_month"
    data = []
    summary = {}

    try:
        # Llamada interna al endpoint de analytics
        from app.models.imputation import Imputation
        from sqlalchemy import func

        # Informe básico de horas por mes (siempre disponible)
        now = datetime.now(timezone.utc)
        date_from = filters.get("date_from", (now - timedelta(days=90)).strftime("%Y-%m-%d"))
        date_to   = filters.get("date_to",   now.strftime("%Y-%m-%d"))

        from app.db.session import is_postgres
        month_expr = (
            func.to_char(Imputation.date, 'YYYY-MM')
            if is_postgres()
            else func.strftime("%Y-%m", Imputation.date)
        )
        hours_result = db.query(
            month_expr.label("month"),
            func.sum(Imputation.hours).label("hours"),
            func.count(Imputation.id).label("entries"),
        ).filter(
            Imputation.date >= date_from,
            Imputation.date <= date_to,
        ).group_by(month_expr).all()

        data = [{"Mes": r.month, "Horas": round(r.hours, 1), "Entradas": r.entries}
                for r in hours_result]
        total_h = sum(r.hours for r in hours_result)
        summary = {"Total horas": round(total_h, 1), "Período": f"{date_from} / {date_to}"}
    except Exception as e:
        data = [{"Error": str(e)}]

    # Generar PDF
    pdf_bytes = generate_report_pdf(
        title=report.name,
        metric_label=metric.replace("_", " ").title(),
        data=data,
        summary=summary,
        filters=filters,
    )

    # Construir email con PDF adjunto
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders
    import smtplib

    smtp_host = settings.SMTP_HOST
    smtp_user = settings.SMTP_USER

    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
      <div style="background:#0a0e1a; padding:24px; border-radius:8px 8px 0 0;">
        <h1 style="color:#00d4ff; margin:0; font-size:18px;">Clarive — Informe Programado</h1>
      </div>
      <div style="background:#f8fafc; padding:24px; border:1px solid #e2e8f0; border-top:none; border-radius:0 0 8px 8px;">
        <h2 style="color:#1a1a2e; margin:0 0 12px;">{report.name}</h2>
        <p style="color:#6b7280;">Se adjunta el informe generado automáticamente el {datetime.now().strftime('%d/%m/%Y %H:%M')}.</p>
        <p style="color:#6b7280; font-size:13px;">Frecuencia: {report.frequency} · Próximo envío: {_get_next_run(report.frequency).strftime('%d/%m/%Y')}</p>
        <hr style="border:none; border-top:1px solid #e2e8f0; margin:16px 0;">
        <p style="color:#9ca3af; font-size:11px;">Este informe fue generado automáticamente por Clarive. Para cambiar la configuración, accede al módulo de Reportes.</p>
      </div>
    </div>
    """

    if smtp_host and smtp_user:
        smtp_port = settings.SMTP_PORT
        smtp_pass = settings.SMTP_PASS
        smtp_from = settings.SMTP_FROM or smtp_user

        msg = MIMEMultipart()
        msg["Subject"] = f"[Clarive] {report.name} — {datetime.now().strftime('%d/%m/%Y')}"
        msg["From"]    = smtp_from
        msg["To"]      = ", ".join(recipients)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        # Adjuntar PDF
        pdf_part = MIMEBase("application", "pdf")
        pdf_part.set_payload(pdf_bytes)
        encoders.encode_base64(pdf_part)
        safe_name = report.name.replace(" ", "_")[:40]
        pdf_part.add_header("Content-Disposition", "attachment",
                            filename=f"Clarive_{safe_name}_{datetime.now().strftime('%Y%m%d')}.pdf")
        msg.attach(pdf_part)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo(); server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, recipients, msg.as_string())
    else:
        # Sin SMTP configurado — solo log
        logger.warning(
            "[SMTP no configurado] Informe '%s' generado (%d bytes) para: %s",
            report.name, len(pdf_bytes), recipients,
        )


def execute_report_now(report_id: str, db) -> dict:
    """Ejecuta un informe inmediatamente (desde el endpoint /run)."""
    from app.models.billing_reports import ScheduledReport
    report = db.query(ScheduledReport).filter(ScheduledReport.id == report_id).first()
    if not report:
        return {"ok": False, "error": "Informe no encontrado"}
    try:
        _execute_report(report, db)
        report.last_run_at = datetime.now(timezone.utc)
        db.commit()
        return {"ok": True, "recipients": json.loads(report.recipients or "[]")}
    except Exception as e:
        return {"ok": False, "error": str(e)}
