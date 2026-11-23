"""
Change Management Service — RFC planning, approval workflows, rollout automation.

Capabilities:
  - RFC (Request for Change) creation & workflow
  - Risk assessment (IA-based)
  - Change planning with dependencies + rollout sequencing
  - CAB (Change Advisory Board) approval workflow
  - Rollback planning & automation
  - Post-change validation
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from enum import Enum

from sqlalchemy.orm import Session
from app.core.segundo_plano import encolar
from app.services.ai_provider_service import call_ai
from app.core.constantes import NOMBRE_DEL_PRODUCTO
from app.core.codigos_de_error import ErrorConCodigo
from app.core.config import settings  # topes de tokens de IA (19-11-2026)

_log = logging.getLogger(__name__)


def _esc(valor) -> str:
    """Texto escapado para el HTML de los correos (auditoria 2026-11-22, 4.3)."""
    import html
    return html.escape(str(valor if valor is not None else ""))


def _notify_change_stakeholders(
    db: Session,
    change_id: str,
    subject: str,
    body_html: str,
) -> None:
    """Send email + Slack notifications to the change requester and approver."""
    try:
        from app.models.service_desk import ITSMChangeRequest
        from app.models.user import User
        from app.services.notification_service import NotificationService

        change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
        if not change:
            return

        # Auditoria 2026-08: aqui habia `change.assigned_to_id`, y esa columna
        # **no existe** en `sd_change_requests` — quien lleva el cambio es
        # `owner_id`. Reventaba con `AttributeError`, asi que **ningun aviso a
        # los interesados de un cambio llegaba nunca**: ni al solicitante, ni al
        # aprobador, ni al responsable.
        recipient_ids = {
            uid for uid in
            [change.requester_id, change.approver_id, change.owner_id]
            if uid
        }
        for uid in recipient_ids:
            user = db.query(User).filter(User.id == uid).first()
            if user and user.email:
                encolar(NotificationService.send_email, to=user.email, subject=subject, html_body=body_html)

        # Auditoria 2026-11-22 (servicios m-z, 4.3): el webhook de Slack de la
        # empresa del cambio (credencial `slack.webhook_url` o su ajuste
        # `SLACK_WEBHOOK_URL`), nunca el global: los asuntos de todas las
        # empresas iban al mismo canal.
        from app.services.integration_credentials_service import secreto_propio_de_la_organizacion
        webhook = secreto_propio_de_la_organizacion(
            db, "slack", "webhook_url", "SLACK_WEBHOOK_URL", change.organization_id)
        if webhook:
            # Auditoria 2026-11 (hallazgo 23): habia un tercer cliente de Slack,
            # asincrono, en `notification_service`, y este era su unico uso (con
            # un `run_until_complete` que revienta dentro de un bucle en marcha).
            # El de `integrations` es sincrono y pasa la guarda SSRF.
            from app.services.integrations import send_slack_message
            send_slack_message(webhook, subject)
    except Exception as exc:
        _log.warning("Could not send change notification for %s: %s", change_id, exc)

class ChangeType(str, Enum):
    standard = "standard"       # Pre-approved template
    normal = "normal"           # Normal CAB approval
    emergency = "emergency"     # Emergency (limited approval)
    pilot = "pilot"             # Pilot/test change


# Auditoria 2026-08 (hallazgo 22): aqui habia un segundo enum `ChangeStatus`,
# con nueve valores entre ellos `in_approval`, y **no lo usaba nadie** — ni este
# modulo, cuyas funciones importan el del modelo (`ITSMChangeRequest.status`), ni
# ningun otro fichero de `app/` o de `tests/`, comprobado.
#
# Lo que si hacia era esconder un defecto: era el **unico sitio del repositorio
# donde `in_approval` existia**, y tres consumidores del enum del MODELO
# escribian `ChangeStatus.in_approval` creyendo que estaba. El del modelo no lo
# tiene —su estado de espera del CAB es `cab_review`—, asi que la pasada de
# scoring del CAB respondia 500 siempre y su tarea programada fallaba en cada
# tic. El detalle esta en el comentario de `ESTADOS_PENDIENTES_DE_CAB` en
# `change_impact_service.py`.
#
# Dos enums con el mismo nombre y valores distintos, uno de ellos muerto, es una
# trampa: se importa el que no toca y el interprete no se queja hasta que se
# accede al miembro que falta.


class RiskLevel(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


def _t(db, clave: str, **datos) -> str:
    """Texto de este servicio en el idioma de la empresa del contexto (`db.info`)."""
    from app.services.textos_de_salida_servicios_m_z import texto_para
    return texto_para(db, clave, org_id=db.info.get("organization_id"), **datos)


def assess_change_risk_ai(
    db: Session,
    title: str,
    description: str,
    impact_areas: list[str],
    affected_cis: list[str],
    rollback_plan: str,
    user_id: str | None = None,
    organization_id: str | None = None,
) -> dict:
    """
    Use IA to assess change risk automatically.

    Returns: {
        "risk_level": "critical" | "high" | "medium" | "low",
        "risk_score": 0-100,
        "factors": list[str],
        "mitigation_suggestions": list[str],
        "recommended_approval_level": "emergency" | "normal" | "standard",
        "estimated_duration_minutes": int,
    }
    """
    system_prompt = """You are a Change Management expert. Analyze the following change request and:

    1. Assess risk level (critical/high/medium/low) based on:
       - Impact areas affected
       - Number of dependent systems
       - Rollback plan quality
       - Complexity indicators

    2. Identify risk factors
    3. Suggest mitigations
    4. Recommend approval level
    5. Estimate duration

    Respond ONLY with valid JSON:
    {
        "risk_level": "high",
        "risk_score": 75,
        "factors": ["list of identified risks"],
        "mitigation_suggestions": ["list of mitigations"],
        "recommended_approval_level": "normal",
        "estimated_duration_minutes": 120
    }"""

    change_content = f"""
    Title: {title}
    Description: {description}
    Impact Areas: {', '.join(impact_areas or ['unknown'])}
    Affected CIs: {', '.join(affected_cis or ['unknown'])}
    Rollback Plan: {rollback_plan}
    """

    ai_response = call_ai(
        db,
        messages=[{"role": "user", "content": change_content}],
        system=system_prompt,
        module="change_management",
        # Auditoria 2026-11-22 (4.3): usuario y empresa de la llamada.
        user_id=user_id,
        organization_id=organization_id,
        max_tokens=settings.AI_BRIEF_ANSWER_MAX_TOKENS,
    )

    try:
        result = json.loads(ai_response)
    except (json.JSONDecodeError, ValueError):
        # Fallback if AI returns non-JSON
        result = {
            "risk_level": "high",
            "risk_score": 50,
            "factors": [_t(db, "cambio_rollout.ia.no_evaluable")],
            "mitigation_suggestions": [_t(db, "cambio_rollout.ia.revision_manual")],
            "recommended_approval_level": "normal",
            "estimated_duration_minutes": 120,
        }

    return result


def create_rollout_plan(
    db: Session,
    change_id: str,
    affected_cis: list[str],
    rollback_plan: str,
    estimated_duration_minutes: int,
) -> dict:
    """
    Generate automated rollout plan.

    Returns: {
        "phases": [
            {
                "phase": 1,
                "name": "Pre-change validation",
                "duration_minutes": 15,
                "steps": ["...", "..."],
                "validation_checks": ["..."],
                "rollback_if_fails": bool,
            },
            ...
        ],
        "total_estimated_minutes": int,
        "maintenance_window_start": datetime,
        "maintenance_window_end": datetime,
    }
    """
    phases = [
        {
            "phase": 1,
            "name": _t(db, "cambio_rollout.fase.1.nombre"),
            "duration_minutes": 10,
            "steps": [
                _t(db, "cambio_rollout.fase.1.paso.1"),
                _t(db, "cambio_rollout.fase.1.paso.2"),
                _t(db, "cambio_rollout.fase.1.paso.3"),
                _t(db, "cambio_rollout.fase.1.paso.4"),
            ],
            "validation_checks": [_t(db, "cambio_rollout.fase.1.check.1"), _t(db, "cambio_rollout.fase.1.check.2"), _t(db, "cambio_rollout.fase.1.check.3")],
            "rollback_if_fails": True,
        },
        {
            "phase": 2,
            "name": _t(db, "cambio_rollout.fase.2.nombre"),
            "duration_minutes": 10,
            "steps": [
                _t(db, "cambio_rollout.fase.2.paso.1"),
                _t(db, "cambio_rollout.fase.2.paso.2"),
                _t(db, "cambio_rollout.fase.2.paso.3"),
                _t(db, "cambio_rollout.fase.2.paso.4"),
            ],
            "validation_checks": [_t(db, "cambio_rollout.fase.2.check.1"), _t(db, "cambio_rollout.fase.2.check.2")],
            "rollback_if_fails": True,
        },
        {
            "phase": 3,
            "name": _t(db, "cambio_rollout.fase.3.nombre"),
            "duration_minutes": int(estimated_duration_minutes),
            "steps": [
                _t(db, "cambio_rollout.fase.3.paso.1"),
                _t(db, "cambio_rollout.fase.3.paso.2"),
                _t(db, "cambio_rollout.fase.3.paso.3"),
                _t(db, "cambio_rollout.fase.3.paso.4"),
            ],
            "validation_checks": [_t(db, "cambio_rollout.fase.3.check.1"), _t(db, "cambio_rollout.fase.3.check.2")],
            "rollback_if_fails": True,
        },
        {
            "phase": 4,
            "name": _t(db, "cambio_rollout.fase.4.nombre"),
            "duration_minutes": 15,
            "steps": [
                _t(db, "cambio_rollout.fase.4.paso.1"),
                _t(db, "cambio_rollout.fase.4.paso.2"),
                _t(db, "cambio_rollout.fase.4.paso.3"),
                _t(db, "cambio_rollout.fase.4.paso.4"),
            ],
            "validation_checks": [_t(db, "cambio_rollout.fase.4.check.1"), _t(db, "cambio_rollout.fase.4.check.2")],
            "rollback_if_fails": True,
        },
        {
            "phase": 5,
            "name": _t(db, "cambio_rollout.fase.5.nombre"),
            "duration_minutes": 5,
            "steps": [
                _t(db, "cambio_rollout.fase.5.paso.1"),
                _t(db, "cambio_rollout.fase.5.paso.2"),
                _t(db, "cambio_rollout.fase.5.paso.3"),
                _t(db, "cambio_rollout.fase.5.paso.4"),
            ],
            "validation_checks": [_t(db, "cambio_rollout.fase.5.check.1")],
            "rollback_if_fails": False,
        },
    ]

    total_minutes = sum(p["duration_minutes"] for p in phases)
    now = datetime.now(timezone.utc)

    return {
        "phases": phases,
        "total_estimated_minutes": total_minutes,
        "maintenance_window_start": now,
        "maintenance_window_end": now + timedelta(minutes=total_minutes + 30),
    }


def generate_rollback_automation_script(
    change_id: str,
    rollback_plan: str,
    affected_cis: list[str],
) -> str:
    """
    Generate bash/Python script for automated rollback.

    Returns script content that can be executed.

    Auditoria 2026-11-22 (servicios m-z, 4.3): el numero del cambio iba tal
    cual dentro de `echo "..."` y de la ruta del log, y el plan de marcha
    atras (texto libre del cambio) se pegaba como ordenes: un `$(...)` en
    cualquiera de los dos se ejecutaba al lanzar el script. Ahora el
    identificador solo admite `[A-Za-z0-9._-]` y el plan sale como
    comentarios: quien lo ejecuta revisa y activa cada paso.
    """
    import re
    change_id = re.sub(r"[^A-Za-z0-9._-]", "_", str(change_id or ""))[:64] or "unknown"
    rollback_plan = "\n".join(
        "# " + linea.replace("\r", "") for linea in str(rollback_plan or "").splitlines()
    ) or "# (no rollback plan)"
    script = f"""#!/bin/bash
# Auto-generated rollback script for change {change_id}
# Generated: {datetime.now(timezone.utc).isoformat()}
# CAUTION: Test this before execution!

set -e  # Exit on error

echo "🔄 INITIATING ROLLBACK FOR CHANGE {change_id}"
echo "⏰ Timestamp: $(date -u)"

# Step 1: Notify stakeholders (application-level notifications sent automatically)
echo "📢 Notifying stakeholders via {NOMBRE_DEL_PRODUCTO} notification service..."

# Step 2: Validate rollback pre-conditions
echo "🔍 Validating rollback conditions..."
# Check snapshots exist
# Check connectivity
# Verify no ongoing transactions

# Step 3: Execute rollback
echo "⚙️  Executing rollback steps..."
# Rollback plan from the change record: review each step and uncomment it.
{rollback_plan}

# Step 4: Validate rollback
echo "✅ Validating rollback..."
# Run health checks
# Verify services
# Check data integrity

# Step 5: Document rollback
echo "📝 Documenting rollback..."
echo "Rollback completed at $(date -u)" >> /var/log/changes/rollback_{change_id}.log

echo "✅ ROLLBACK COMPLETED SUCCESSFULLY"
"""
    return script


def check_change_suitability_for_automation(
    db: Session,
    change_id: str,
    risk_level: RiskLevel,
    change_type: ChangeType,
) -> dict:
    """
    Determine if change can be fully automated or requires manual oversight.

    Returns: {
        "can_automate": bool,
        "automation_level": "full" | "partial" | "manual",
        "requires_manual_gates": list[str],
        "reason": str,
    }
    """
    automation_level = "partial"
    requires_manual_gates = []
    can_automate = True

    if risk_level == RiskLevel.critical:
        automation_level = "manual"
        can_automate = False
        requires_manual_gates.append(_t(db, "cambio_rollout.puerta.critico"))

    elif risk_level == RiskLevel.high:
        automation_level = "partial"
        requires_manual_gates.append(_t(db, "cambio_rollout.puerta.alto"))

    if change_type == ChangeType.emergency:
        requires_manual_gates.append(_t(db, "cambio_rollout.puerta.emergencia"))

    return {
        "can_automate": can_automate,
        "automation_level": automation_level,
        "requires_manual_gates": requires_manual_gates,
        "reason": _t(db, "cambio_rollout.motivo_automatizacion", riesgo=risk_level.value, tipo=change_type.value),
    }


# ── Rollout Execution Tracking ────────────────────────────────────────────────

_ROLLOUT_STATE_KEY_PREFIX = "sd.change.rollout."


def _rollout_state_key(change_id: str) -> str:
    return f"{_ROLLOUT_STATE_KEY_PREFIX}{change_id}"


def _get_rollout_state(db: Session, change_id: str) -> dict | None:
    """Load rollout execution state from AppSetting JSON blob."""
    import json as _json
    try:
        from app.models.settings import AppSetting
        row = db.query(AppSetting).filter(AppSetting.key == _rollout_state_key(change_id)).first()
        if not row or not row.value:
            return None
        return _json.loads(row.value)
    except Exception:
        _log.warning("_get_rollout_state: excepcion ignorada", exc_info=True)
        return None


def _save_rollout_state(db: Session, change_id: str, state: dict) -> None:
    import json as _json
    try:
        from app.models.settings import AppSetting
        key = _rollout_state_key(change_id)
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        if row:
            row.value = _json.dumps(state)
        else:
            db.add(AppSetting(key=key, value=_json.dumps(state), description=_t(db, "cambio_rollout.estado_ajuste", cambio=change_id)))
        db.flush()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Could not save rollout state: %s", exc)


def start_rollout_execution(
    db: Session,
    change_id: str,
    rollout_plan: dict,
    current_user,
) -> dict:
    """Persist rollout plan as execution state and mark change as in_progress.

    Each phase gets a status of 'pending'. Does NOT commit — caller must commit.
    """
    import logging
    _log = logging.getLogger(__name__)
    from app.core.codigos_de_error import error
    from app.models.service_desk import ITSMChangeRequest, ChangeStatus
    from app.models.service_desk._enums import ESTADOS_DE_CAMBIO_IMPLANTABLES

    # Auditoria 2026-11-22 (C-SD4): arrancar el despliegue ponia el cambio en
    # `in_progress` sin mirar su estado (aprobaba de hecho un borrador) y, si el
    # cambio no existia, guardaba el estado igualmente y devolvia 201. Ahora:
    # 404 si no existe (en la empresa de la sesion) y 409 si no esta aprobado
    # o programado. El estado se cambia antes de guardar nada.
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if change is None:
        raise error(404, "no_encontrado", detail="Cambio no encontrado", que="cambio")
    estado = getattr(change.status, "value", change.status)
    if estado not in ESTADOS_DE_CAMBIO_IMPLANTABLES:
        raise error(409, "cambio_no_aprobado_para_desplegar", estado=estado)

    phases = rollout_plan.get("phases", [])
    execution_phases = [
        {
            "phase": p["phase"],
            "name": p["name"],
            "status": "pending",      # pending | in_progress | completed | failed | skipped
            "started_at": None,
            "completed_at": None,
            "notes": "",
            "steps": p.get("steps", []),
            "validation_checks": p.get("validation_checks", []),
            "rollback_if_fails": p.get("rollback_if_fails", True),
            "duration_minutes": p.get("duration_minutes", 0),
        }
        for p in phases
    ]

    state = {
        "change_id": change_id,
        "started_by": current_user.id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": "in_progress",  # in_progress | completed | rolled_back | paused
        "current_phase": 1,
        "phases": execution_phases,
        "rollback_triggered": False,
        "rollback_reason": None,
    }

    change.status = ChangeStatus.in_progress
    change.actual_start = datetime.now(timezone.utc)
    _save_rollout_state(db, change_id, state)

    _log.info("Rollout execution started for change %s by %s", change_id, current_user.id)
    return state


#: Estados válidos de una fase de despliegue.
_ESTADOS_DE_FASE = {"in_progress", "completed", "failed", "skipped"}

#: Estados que dan una fase por terminada, del modo que sea.
_FASES_TERMINADAS = {"completed", "skipped"}


def _disparar_rollback(db: Session, change_id: str, state: dict, fase: dict,
                       phase_number: int, notes: str, _log) -> None:
    """Marca el despliegue como revertido y avisa a los interesados.

    Las fases que quedaban por delante pasan a `skipped`, no a `failed`: no
    llegaron a ejecutarse, y decir que fallaron sería falso en el informe.
    """
    motivo = _t(db, "cambio_rollout.rollback.motivo_fase", fase=phase_number, nombre=fase["name"], notas=notes)
    state["overall_status"] = "rolled_back"
    state["rollback_triggered"] = True
    state["rollback_reason"] = motivo

    _log.warning(
        "Rollback triggered automatically: change=%s phase=%d reason=%s",
        change_id, phase_number, notes,
    )
    for p in state["phases"]:
        if p["phase"] > phase_number and p["status"] == "pending":
            p["status"] = "skipped"

    _update_change_status_on_rollback(db, change_id)
    _notify_change_stakeholders(
        db, change_id,
        subject=_t(db, "cambio_rollout.rollback_auto.asunto", producto=NOMBRE_DEL_PRODUCTO, cambio=change_id),
        body_html=_t(db, "cambio_rollout.rollback_auto.cuerpo", cambio=_esc(change_id), motivo=_esc(motivo),
                     fase_nombre=_esc(fase["name"]), fase=phase_number,
                     hora=datetime.now(timezone.utc).isoformat()),
    )


def _avanzar_puntero_y_cerrar(db: Session, change_id: str, state: dict,
                              phase_number: int, phase_status: str) -> None:
    """Mueve el puntero de fase y cierra el despliegue si ya no queda nada."""
    if phase_status == "completed":
        pendientes = [p for p in state["phases"] if p["status"] == "pending"]
        state["current_phase"] = pendientes[0]["phase"] if pendientes else phase_number

    todo_hecho = all(p["status"] in _FASES_TERMINADAS for p in state["phases"])
    if not (todo_hecho and state["overall_status"] == "in_progress"):
        return

    state["overall_status"] = "completed"
    _update_change_status_on_complete(db, change_id)
    _notify_change_stakeholders(
        db, change_id,
        subject=_t(db, "cambio_rollout.completado.asunto", producto=NOMBRE_DEL_PRODUCTO, cambio=change_id),
        body_html=_t(db, "cambio_rollout.completado.cuerpo", cambio=_esc(change_id),
                     hora=datetime.now(timezone.utc).isoformat()),
    )


def advance_rollout_phase(
    db: Session,
    change_id: str,
    phase_number: int,
    phase_status: str,
    notes: str,
    current_user,
) -> dict:
    """Mueve una fase de despliegue a un estado nuevo.

    `phase_status`: 'in_progress' | 'completed' | 'failed' | 'skipped'.
    Si una fase falla y tiene `rollback_if_fails`, dispara la reversión.

    **No confirma la transacción** — quien llama tiene que hacerlo.
    """
    import logging

    _log = logging.getLogger(__name__)

    if phase_status not in _ESTADOS_DE_FASE:
        raise ErrorConCodigo("estado_no_valido_valor", detail=f"Estado de fase inválido: {phase_status}", estado=phase_status)

    state = _get_rollout_state(db, change_id)
    if not state:
        raise ErrorConCodigo("rollout_sin_ejecucion_cambio", detail=f"No hay ejecución de rollout para el cambio {change_id}")

    fase = next((p for p in state["phases"] if p["phase"] == phase_number), None)
    if not fase:
        raise ErrorConCodigo("no_encontrado", detail=f"Fase {phase_number} no encontrada en el plan de rollout", que="fase")

    ahora = datetime.now(timezone.utc).isoformat()
    fase["status"] = phase_status
    fase["notes"] = notes
    # `started_at` sólo la primera vez: volver a marcar «en curso» no reinicia
    # el reloj de una fase que ya empezó.
    if phase_status == "in_progress" and not fase.get("started_at"):
        fase["started_at"] = ahora
    if phase_status in _FASES_TERMINADAS or phase_status == "failed":
        fase["completed_at"] = ahora

    if phase_status == "failed" and fase.get("rollback_if_fails"):
        _disparar_rollback(db, change_id, state, fase, phase_number, notes, _log)
    else:
        _avanzar_puntero_y_cerrar(db, change_id, state, phase_number, phase_status)

    _save_rollout_state(db, change_id, state)
    _log.info(
        "Rollout phase %d/%s: change=%s status=%s",
        phase_number, fase["name"], change_id, phase_status,
    )
    return state


def _update_change_status_on_rollback(db: Session, change_id: str) -> None:
    try:
        from app.models.service_desk import ITSMChangeRequest, ChangeStatus
        change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
        if change:
            change.status = ChangeStatus.closed_failed
            change.actual_end = datetime.now(timezone.utc)
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except Exception:
        _log.debug("_update_change_status_on_rollback: fallo best-effort ignorado", exc_info=True)


def _update_change_status_on_complete(db: Session, change_id: str) -> None:
    try:
        from app.models.service_desk import ITSMChangeRequest, ChangeStatus
        change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
        if change:
            change.status = ChangeStatus.implemented
            change.actual_end = datetime.now(timezone.utc)
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except Exception:
        _log.debug("_update_change_status_on_complete: fallo best-effort ignorado", exc_info=True)


def trigger_change_rollback(
    db: Session,
    change_id: str,
    reason: str,
    current_user,
) -> dict:
    """Manually trigger a rollback for an in-progress change.

    Updates rollout execution state and change status. Does NOT commit.
    """
    import logging
    _log = logging.getLogger(__name__)

    state = _get_rollout_state(db, change_id)
    if state:
        state["overall_status"] = "rolled_back"
        state["rollback_triggered"] = True
        state["rollback_reason"] = reason
        now_iso = datetime.now(timezone.utc).isoformat()
        for p in state["phases"]:
            if p["status"] in {"pending", "in_progress"}:
                p["status"] = "skipped"
                p["completed_at"] = now_iso
        state["rollback_at"] = now_iso
        state["rollback_by"] = current_user.id
        _save_rollout_state(db, change_id, state)

    _update_change_status_on_rollback(db, change_id)
    _notify_change_stakeholders(
        db,
        change_id,
        subject=_t(db, "cambio_rollout.rollback_manual.asunto", producto=NOMBRE_DEL_PRODUCTO, cambio=change_id),
        body_html=_t(db, "cambio_rollout.rollback_manual.cuerpo", cambio=_esc(change_id), motivo=_esc(reason),
                     quien=_esc(current_user.id), hora=datetime.now(timezone.utc).isoformat()),
    )
    _log.warning("Manual rollback triggered: change=%s reason=%s by=%s", change_id, reason, current_user.id)
    return {"change_id": change_id, "rollback_triggered": True, "reason": reason}


def get_rollout_execution_state(db: Session, change_id: str) -> dict | None:
    """Return current rollout execution state, or None if not started."""
    return _get_rollout_state(db, change_id)


# ── Emergency CAB Fast-Track ──────────────────────────────────────────────────

def fast_track_emergency_cab(
    db: Session,
    change_id: str,
    approver_ids: list[str],
    justification: str,
    current_user,
) -> dict:
    """Fast-track an emergency change through CAB bypassing normal queuing.

    Requires at least one approver and a business justification.
    Sets change type to 'emergency' and status to 'approved' with an audit entry.
    Does NOT commit — caller must commit.
    """
    import json as _json
    import logging
    from app.models.service_desk import ITSMChangeRequest, ChangeType, ChangeStatus

    _log = logging.getLogger(__name__)

    if not approver_ids:
        raise ErrorConCodigo("cambio_emergencia_sin_aprobador", detail="Se requiere al menos un aprobador para fast-track de emergencia")
    if not justification or len(justification.strip()) < 10:
        raise ErrorConCodigo("cambio_emergencia_sin_justificacion", detail="Se requiere justificación de negocio para cambios de emergencia")

    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        raise ErrorConCodigo("no_encontrado", detail=f"Cambio {change_id} no encontrado", que="cambio")

    from app.services.approval_engine._base import exigir_que_no_sea_suyo
    exigir_que_no_sea_suyo(db, change.requester_id, current_user, "itsm_change", change.id)
    # Auditoria 2026-11-22 (A-SD19): el fast-track aprobaba el cambio en el
    # acto con una sola persona (quien lo pulsaba); `approver_ids` solo se
    # guardaba en un texto. Ahora es un CAB de emergencia (ECAB): esos
    # aprobadores (sin el solicitante) votan por la via normal y el cambio
    # queda en revision hasta que se alcanza el quorum de la empresa.
    aprobadores = [a for a in dict.fromkeys(approver_ids) if a and a != change.requester_id]
    if not aprobadores:
        raise ErrorConCodigo("cambio_emergencia_sin_aprobador", detail="Se requiere al menos un aprobador distinto del solicitante")
    from app.services.service_desk import cab_workflow_service as cab
    change.change_type = ChangeType.emergency
    cab.start_cab_workflow(db, change_id=change.id, requester=current_user, cab_members=aprobadores)
    emergency_record = {
        "fast_track": True,
        "justification": justification,
        "approver_ids": aprobadores,
        "requested_by": current_user.id,
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    existing_justification = change.business_justification or ""
    change.business_justification = (
        existing_justification
        + f"\n\n{_t(db, 'cambio_rollout.fast_track')}\n{_json.dumps(emergency_record, indent=2)}"
    )

    _log.warning(
        "Emergency CAB fast-track requested: change=%s by=%s approvers=%s",
        change_id, current_user.id, aprobadores,
    )
    return {
        "change_id": change_id,
        "status": getattr(change.status, "value", change.status),
        "change_type": ChangeType.emergency.value,
        "approver_ids": aprobadores,
        "quorum": change.cab_quorum,
        "requested_at": emergency_record["requested_at"],
    }

