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

Auditoria 2026-11 (#35). Hay otro sistema de envios programados,
`bi_report_delivery_service.py` (beat `bi-scheduled-delivery`), y NO se fusionan
porque programan cosas distintas: aqui un informe con tipo (KPI OLAP, utilizacion,
pipeline, portfolio o una metrica de la pantalla de Informes) que se maqueta en
PDF por `report_pdf_service` y se guarda en la tabla `scheduled_reports`
(hora/dia de envio, estado del ultimo envio, pantalla de Facturacion/Informes);
alli una consulta del constructor de informes BI (preset) que se exporta como
datos (xlsx/csv/json/pdf tabular), con «enviar solo si cambio» y diff entre
envios, guardada en `app_settings`. Lo que si comparten es la entrega:
`entrega_saliente` (Slack/Teams con URL validada y correo por
`notification_service`, un mensaje por destinatario).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.models.billing_reports import ScheduledReport

logger = logging.getLogger("contecflow.scheduled_reports")


# ── Scheduling helpers ────────────────────────────────────────────────────────

def _get_next_run(frequency: str, from_dt: Optional[datetime] = None, *, send_hour: Optional[int] = None,
                  day_of_week: Optional[int] = None, day_of_month: Optional[int] = None) -> datetime:
    """La próxima vez que toca, a la hora (UTC) y el día configurados.

    Revisión 2026-11: ignoraba `send_hour`, `day_of_week` y `day_of_month` y
    sumaba un día o una semana a la última ejecución.
    """
    import calendar
    base = from_dt or datetime.now(timezone.utc)
    hora = 8 if send_hour is None else int(send_hour)
    cand = base.replace(hour=hora, minute=0, second=0, microsecond=0)
    if frequency == "daily":
        return cand if cand > base else cand + timedelta(days=1)
    if frequency == "monthly":
        dia = int(day_of_month or 1)
        anio, mes = base.year, base.month
        for _ in range(2):
            ultimo = calendar.monthrange(anio, mes)[1]
            c = cand.replace(year=anio, month=mes, day=min(dia, ultimo))
            if c > base:
                return c
            anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
        return c
    # semanal (y por defecto): el día de la semana configurado, lunes si no hay
    dow = 0 if day_of_week is None else int(day_of_week)
    c = cand + timedelta(days=(dow - cand.weekday()) % 7)
    return c if c > base else c + timedelta(weeks=1)


def proxima_ejecucion(report, desde: Optional[datetime] = None) -> datetime:
    return _get_next_run(report.frequency, desde, send_hour=getattr(report, "send_hour", None),
                         day_of_week=getattr(report, "day_of_week", None),
                         day_of_month=getattr(report, "day_of_month", None))


# ── Email sender ──────────────────────────────────────────────────────────────

def _send_email(recipients: list[str], subject: str, html_body: str, pdf_bytes: bytes, filename: str) -> None:
    """Envia el informe por el camino comun (`entrega_saliente`). Lanza si no sale.

    Revisión 2026-11: sin SMTP el envío quedaba como correcto sin enviar nada.
    Auditoria 2026-11 (#35): un mensaje por destinatario, como el informe BI
    (antes uno solo con todos en `To`: cada destinatario veia a los demas).
    """
    from app.services.entrega_saliente import enviar_informe_por_correo

    fallidos = enviar_informe_por_correo(
        recipients, subject, html_body,
        adjunto=(filename, pdf_bytes, "application/pdf") if pdf_bytes else None,
    )
    if fallidos:
        raise RuntimeError(f"El informe no se pudo enviar a {len(fallidos)} de {len(recipients)} destinatarios")
    logger.info("Email sent: %s → %d destinatarios", subject, len(recipients))


# ── Slack sender ──────────────────────────────────────────────────────────────

def _send_slack(webhook_url: str, report_name: str, report_type: str, kpis: dict,
                simbolo: Optional[str] = None) -> None:
    """Resumen del informe a un Incoming Webhook de Slack (`entrega_saliente`). No lanza."""
    from app.services.entrega_saliente import enviar_a_webhook, mensaje_de_slack
    from app.services.formato_regional import formatear_importe, simbolo_de_moneda
    simbolo = simbolo or simbolo_de_moneda()

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
            lines.append(f"• Pipeline ponderado: *{formatear_importe(kpis['pipeline_weighted'], simbolo)}*")
        if kpis.get("hours_mtd") is not None:
            lines.append(f"• Horas imputadas (mes): *{kpis['hours_mtd']}h*")
        if kpis.get("billability_pct") is not None:
            lines.append(f"• Facturabilidad: *{kpis['billability_pct']}%*")
    lines.append(f"_Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')} UTC_")

    r = enviar_a_webhook(webhook_url, mensaje_de_slack("\n".join(lines)))
    if r.ok:
        logger.info("Slack notification sent for '%s': %s", report_name, r.status)
    else:
        logger.warning("Slack send failed for '%s': %s", report_name, r.error)


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

def _destinatarios_de(report) -> list[str]:
    """Los correos del informe, sin duplicados y conservando el orden.

    Las dos listas se leen por separado y cada una tolera su propio JSON roto:
    si `recipients_extra` está corrupto, el informe todavía se puede enviar a
    los destinatarios principales.
    """
    correos: list[str] = []
    for campo in ("recipients", "recipients_extra"):
        try:
            crudo = json.loads(getattr(report, campo, None) or "[]")
        except Exception:
            logger.warning(
                "No se pudieron parsear los destinatarios (%s) del informe '%s'",
                campo, report.name,
            )
            continue
        correos += crudo
    return list(dict.fromkeys(correos))


def _organizacion_del_informe(report, db) -> Optional[str]:
    """La organización de quien creó el informe, que es la que acota sus datos."""
    try:
        from app.models.user import User

        creador = db.query(User).filter(User.id == report.created_by).first()
        return getattr(creador, "organization_id", None) if creador else None
    except Exception:
        logger.exception(
            "Error resolviendo organización del creador del informe '%s'", report.name,
        )
        return None


def _pdf_del_informe(report, db, org_id, report_type: str) -> bytes:
    """El PDF del informe. Si no se puede generar, el envío falla con el motivo.

    Revisión 2026-11: antes caía a un generador antiguo con `data=[]` y se
    enviaba un PDF en blanco como si todo hubiera ido bien.
    """
    from app.services.report_pdf_service import build_report_pdf
    return build_report_pdf(report, db, org_id=org_id)


def _execute_report(report: ScheduledReport, db) -> None:
    """Genera el PDF del informe y lo reparte por correo y por Slack."""
    report_type = getattr(report, "report_type", None) or "custom"
    destinatarios = _destinatarios_de(report)
    org_id = _organizacion_del_informe(report, db)

    # Los KPIs se piden siempre, aunque no haya correo: el resumen de Slack los
    # usa y no depende del PDF.
    kpis: dict = {}
    try:
        from app.services.olap.query_engine import get_kpi_summary

        kpis = get_kpi_summary(org_id)
    except Exception:
        logger.warning("Fallo obteniendo KPIs OLAP para el informe '%s'", report.name)

    from app.services.service_desk.ticket_events import como_organizacion
    with como_organizacion(db, org_id):
        pdf = _pdf_del_informe(report, db, org_id, report_type) if getattr(report, "include_pdf", True) else b""

    if destinatarios and (pdf or not getattr(report, "include_pdf", True)):
        nombre = report.name.replace(" ", "_")[:40]
        try:
            _send_email(
                destinatarios,
                f"[ContecFlow] {report.name} — {datetime.now().strftime('%d/%m/%Y')}",
                _build_html_body(
                    report.name, report_type, report.frequency,
                    proxima_ejecucion(report),
                ),
                pdf,
                f"ContecFlow_{nombre}_{datetime.now().strftime('%Y%m%d')}.pdf",
            )
        except Exception as exc:
            # El correo sí propaga: es la entrega principal, y un informe que
            # no llega tiene que marcar el envío como fallido.
            logger.error("Email delivery failed for '%s': %s", report.name, exc)
            raise

    slack = getattr(report, "slack_webhook", None)
    if slack:
        from app.services.formato_regional import simbolo_de_moneda
        _send_slack(slack, report.name, report_type, kpis, simbolo_de_moneda(db, org_id))


# ── Public API ────────────────────────────────────────────────────────────────

def ejecutar_informes_vencidos(db, now: datetime | None = None) -> dict:
    """Envia los informes programados vencidos que ve esta sesion.

    El worker la llama una vez por organizacion con su contexto publicado
    (segunda auditoria 2026-11, #33). El fallo de un informe queda en su
    `last_status`/`last_error` (con traza en el log) y no para a los demas.
    """
    now = now or datetime.now(timezone.utc)
    reports = db.query(ScheduledReport).filter(
        ScheduledReport.is_active.is_(True),
        (ScheduledReport.next_run_at.is_(None)) | (ScheduledReport.next_run_at <= now),
    ).all()
    enviados = fallidos = 0
    for report in reports:
        try:
            _execute_report(report, db)
            report.last_run_at = now
            report.next_run_at = proxima_ejecucion(report, now)
            report.last_status = "success"
            report.last_error = None
            db.commit()
            enviados += 1
            logger.info("Report '%s' (%s) sent OK", report.name, getattr(report, "report_type", "custom"))
        except Exception as exc:
            fallidos += 1
            logger.error("Report '%s' failed: %s", report.name, exc, exc_info=True)
            db.rollback()
            report.last_status = "error"
            report.last_error = str(exc)[:500]
            db.commit()
    return {"enviados": enviados, "fallidos": fallidos}


def run_due_reports() -> dict:
    """Todos los informes vencidos, en una sesion propia (uso manual y pruebas).

    Antes atrapaba cualquier error («crashed») y lo dejaba en el log: el
    programador lo daba por bueno. Ahora se propaga.
    """
    from app.db.session import worker_db_session
    with worker_db_session() as db:
        return ejecutar_informes_vencidos(db)


def destinatarios_del_informe(report_id: str, db) -> Optional[list]:
    """Los destinatarios del informe, o None si no existe (o no es de la empresa).

    Segunda auditoria 2026-11 (n.º 20): `/run` comprueba el informe y responde
    con sus destinatarios antes de mandar la ejecucion a la cola.
    """
    report = db.query(ScheduledReport).filter(ScheduledReport.id == report_id).first()
    if not report:
        return None
    try:
        return list(json.loads(report.recipients or "[]"))
    except Exception:
        logger.warning("destinatarios_del_informe: recipients ilegible en %s", report_id, exc_info=True)
        return []


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
