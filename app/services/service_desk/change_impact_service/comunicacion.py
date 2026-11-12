"""Plan de comunicacion del cambio: audiencias, canales y avisos.

Parte de `app.services.service_desk.change_impact_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.service_desk import ITSMChangeRequest
from app.core.errores import ErrorDeDominio

from app.services.service_desk.change_impact_service.planes import _set_json_setting
from app.services.service_desk.change_impact_service.riesgo import (
    score_change_risk,
    suggest_maintenance_window,
)


# ══════════════════════════════════════════════════════════════════════════════
# Communications Plan — audiences, channels, timing
# ══════════════════════════════════════════════════════════════════════════════

_COMMS_AUDIENCES: dict[str, dict[str, list[str]]] = {
    # risk_label → {timing_bucket → [audience_dicts]}
    "low": {
        "pre_change": ["IT Operations Team"],
        "post_change": ["IT Operations Team"],
    },
    "medium": {
        "pre_change": ["IT Operations Team", "Service Desk", "Line Manager"],
        "post_change": ["IT Operations Team", "Service Desk"],
    },
    "high": {
        "pre_change": ["IT Operations Team", "Service Desk", "Line Manager", "End Users (affected services)"],
        "during_change": ["IT Operations Team", "Service Desk"],
        "post_change": ["IT Operations Team", "Service Desk", "Line Manager", "End Users (affected services)"],
    },
    "critical": {
        "pre_change": ["IT Operations Team", "Service Desk", "Line Manager", "End Users (affected services)", "Executive Team"],
        "during_change": ["IT Operations Team", "Service Desk", "Executive Team"],
        "post_change": ["IT Operations Team", "Service Desk", "Line Manager", "End Users (affected services)", "Executive Team"],
        "post_incident": ["Executive Team", "Key Stakeholders"],
    },
}

_CHANNEL_MAP: dict[str, str] = {
    "IT Operations Team": "email + IM (Slack/Teams)",
    "Service Desk": "email + ticketing system notification",
    "Line Manager": "email",
    "End Users (affected services)": "email + service portal banner",
    "Executive Team": "email + phone / executive summary",
    "Key Stakeholders": "email",
    "NOC": "IM (Slack/Teams) + monitoring alert",
}


#: El plan de comunicación, declarado. Cada fila es un aviso:
#:
#:    (cuándo, horas antes, público, canal, asunto, mensaje, responsable,
#:     condición)
#:
#: `condición` es `None` —siempre—, `"alto"` —riesgo alto o crítico— o
#: `"critico"`. `canal` a `None` significa «el canal por defecto de ese
#: público», que vive en `_CHANNEL_MAP`.
#:
#: Auditoría 2026-09 (hallazgo 18): eran 260 líneas de llamadas a un ayudante
#: anidado con las condiciones repartidas entre ellas. Un plan de comunicación
#: **es** una tabla, y verla entera es lo que hace falta para revisarla con
#: quien la va a enviar: quién recibe qué, cuándo, y por qué canal.
#:
#: Las llaves dobles `{{...}}` son huecos que rellena quien envía el aviso en
#: el momento; las simples se sustituyen aquí.
_AVISOS_DEL_PLAN: tuple[tuple, ...] = (
    # ── Antes del cambio ─────────────────────────────────────────────────────
    ("T-7d", 168, "Executive Team", None,
     "[CRITICAL CHANGE] {number} — {title}",
     "Se planifica un cambio crítico ({number}): «{title}».\n"
     "Ventana propuesta: {ventana}. Tiempo de inactividad estimado: {parada} min.\n"
     "Se requiere confirmación de disponibilidad y aprobación ejecutiva.",
     "Change Manager", "critico"),

    ("T-72h", 72, "End Users (affected services)", None,
     "[Aviso de mantenimiento] {number} — {title}",
     "Estimado usuario,\nSe realizará un mantenimiento programado ({number}) el {ventana}.\n"
     "Interrupción estimada: {parada} minutos. Disculpe las molestias.",
     "Service Desk / Comms Team", "critico"),

    ("T-48h", 48, "Service Desk", None,
     "[Aviso previo] Cambio {number} — {title}",
     "Notificación de cambio programado ({number}): «{title}».\n"
     "Ventana: {ventana}. Impacto: riesgo {RIESGO}.\n"
     "Prepara guiones de respuesta para consultas de usuarios durante la ventana.",
     "Change Manager", "alto"),

    ("T-48h", 48, "Line Manager", None,
     "[Cambio programado] {number} — {title}",
     "Cambio programado ({number}): «{title}».\n"
     "Ventana: {ventana}. Riesgo: {RIESGO}.\n"
     "Asegúrese de que el equipo técnico esté disponible durante la ventana.",
     "Change Manager", "alto"),

    ("T-24h", 24, "IT Operations Team", None,
     "[Recordatorio] Cambio mañana: {number} — {title}",
     "Recordatorio: mañana se ejecuta el cambio {number}: «{title}».\n"
     "Ventana: {ventana}. Plan de pruebas y rollback deben estar listos.\n"
     "Confirma disponibilidad respondiendo este mensaje.",
     "Change Manager", None),

    ("T-24h", 24, "End Users (affected services)", None,
     "[Recordatorio mantenimiento mañana] {number}",
     "Recordatorio: mañana {ventana} se realizará el mantenimiento {number}.\n"
     "Inactividad estimada: {parada} min. Guarda tu trabajo antes de la ventana.",
     "Service Desk / Comms Team", "alto"),

    ("T-1h", 1, "IT Operations Team", "IM (Slack/Teams) — canal #operations",
     "🔧 1 hora para inicio: {number}",
     "En 1 hora inicia el cambio {number}: «{title}».\n"
     "Confirma presencia en el canal de guardia. Plan de rollback accesible.",
     "Change Manager", None),

    ("T-1h", 1, "Service Desk", "IM (Slack/Teams) — canal #service-desk",
     "⚠️ Cambio iniciará en 1h: {number}",
     "En 1 hora inicia {number}. Activar modo guardia.\n"
     "Cualquier incidente relacionado durante la ventana: escalar a Change Manager.",
     "Change Manager", "alto"),

    # ── Durante el cambio ────────────────────────────────────────────────────
    ("change_start", 0, "IT Operations Team", "IM (Slack/Teams) — canal #operations",
     "▶️ Cambio iniciado: {number}",
     "El cambio {number} ha iniciado a las {{hora_inicio_utc}} UTC.\n"
     "Monitorización activa. Reportar anomalías inmediatamente.",
     "Change Manager", "alto"),

    ("change_midpoint", None, "Executive Team", None,
     "[Status update] Cambio {number} en progreso",
     "El cambio crítico {number} está en progreso.\n"
     "Estado: {{estado_actual}}. Sin anomalías mayores detectadas hasta el momento.",
     "Change Manager", "critico"),

    # ── Después del cambio ───────────────────────────────────────────────────
    ("post_change_success", None, "IT Operations Team", None,
     "✅ Cambio completado: {number}",
     "El cambio {number}: «{title}» se ha completado exitosamente.\n"
     "Todos los tests post-cambio pasaron. Sistemas en estado operacional normal.",
     "Change Manager", None),

    ("post_change_success", None, "End Users (affected services)", None,
     "✅ Mantenimiento finalizado: {number}",
     "El mantenimiento programado {number} ha concluido.\n"
     "Todos los servicios están disponibles con normalidad. Gracias por su paciencia.",
     "Service Desk / Comms Team", "alto"),

    ("post_change_failure_rollback", None, "IT Operations Team",
     "IM (Slack/Teams) — canal #operations (URGENTE)",
     "❌ ROLLBACK iniciado: {number}",
     "El cambio {number} ha activado el plan de rollback.\n"
     "Motivo: {{motivo_rollback}}. Equipo de rollback en acción. ETA: {{eta_minutos}} min.",
     "Change Manager", None),

    ("post_change_failure_rollback", None, "End Users (affected services)", None,
     "[Mantenimiento extendido] {number}",
     "El mantenimiento {number} ha encontrado un inconveniente y se está resolviendo.\n"
     "ETA de restauración: {{eta_restauracion}}. Pedimos disculpas por el tiempo adicional.",
     "Service Desk / Comms Team", "alto"),

    ("post_pir", None, "Executive Team", None,
     "[PIR] Cambio {number} — Informe post-implementación",
     "Se ha completado la Revisión Post-Implementación del cambio {number}.\n"
     "Resultado: {{resultado_pir}}. Informe completo adjunto.",
     "Change Manager", "critico"),
)


def _avisos_aplicables(ctx: dict) -> list[dict]:
    """Los avisos de la tabla que aplican a este cambio, ya numerados."""
    avisos: list[dict] = []
    for cuando, horas, publico, canal, asunto, mensaje, responsable, condicion in _AVISOS_DEL_PLAN:
        if condicion and not ctx[condicion]:
            continue
        avisos.append({
            "id": len(avisos) + 1,
            "timing": cuando,
            "hours_before_change": horas,
            "audience": publico,
            "channel": canal or _CHANNEL_MAP[publico],
            "subject": asunto.format(**ctx),
            "message_template": mensaje.format(**ctx),
            "responsible": responsable,
        })
    return avisos


def generate_comms_plan(
    db: Session,
    change_id: str,
    current_user_id: Optional[str] = None,
) -> dict:
    """Plan de comunicación con públicos, canales y momentos.

    Cubre el antes, el durante —sólo en riesgo alto o crítico— y el después.
    Las plantillas de mensaje se adaptan al nivel de riesgo. Se guarda en
    `AppSetting` para poder consultarlo luego.
    """
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        raise ErrorDeDominio(404, f"Change {change_id} not found")

    riesgo = score_change_risk(db, change)
    etiqueta = riesgo["risk_label"]
    ventana = suggest_maintenance_window(db, change, riesgo["ci_ids_expanded"])
    ventana_texto = ventana.get("window_label", "pendiente de confirmar")

    ctx = {
        "number": change.number,
        "title": change.title,
        "ventana": ventana_texto,
        "parada": change.downtime_minutes or 0,
        "RIESGO": etiqueta.upper(),
        "alto": etiqueta in ("high", "critical"),
        "critico": etiqueta == "critical",
    }
    avisos = _avisos_aplicables(ctx)

    comms_plan = {
        "change_id": change_id,
        "change_number": change.number,
        "change_title": change.title,
        "risk_label": etiqueta,
        "suggested_window": ventana_texto,
        "total_notifications": len(avisos),
        "timeline_buckets": {
            "pre_change": [
                a for a in avisos
                if a["timing"].startswith("T-") or a["timing"] == "change_start"
            ],
            "during_change": [
                a for a in avisos if a["timing"] in ("change_start", "change_midpoint")
            ],
            "post_change": [a for a in avisos if a["timing"].startswith("post_")],
        },
        "notifications": avisos,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "generated_by": current_user_id,
    }

    _set_json_setting(db, f"sd.change.comms.{change_id}", comms_plan)
    db.commit()
    return comms_plan
