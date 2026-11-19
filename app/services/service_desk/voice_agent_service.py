"""
voice_agent_service.py — IVR / Voice Agent service for Service Desk.

Provides:
  - Session management for voice calls (create, update, close)
  - Intent classification by keyword rules
  - Entity extraction from transcripts
  - Auto-ticket creation from voice sessions
  - DTMF menu tree configuration

Auditoria 2026-11: no hay telefonia ni reconocimiento de voz: los turnos llegan
ya transcritos por la API (de una centralita externa o del simulador de la
pantalla). Decia tener un respaldo con LLM que no existia.

All state stored as AppSetting JSON blobs (no new DB tables).
"""
from __future__ import annotations
import logging

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.core.config import settings as app_settings
from app.core.codigos_de_error import ErrorConCodigo

_SESSIONS_KEY = "sd.voice_agent.sessions"
_CONFIG_KEY = "sd.voice_agent.config"

_DEFAULT_CONFIG: Dict[str, Any] = {
    "greeting": "Bienvenido al servicio de soporte. Diga su solicitud o pulse 1 para incidencias, 2 para consultas, 3 para urgencias.",
    "max_silence_seconds": 10,
    "language": app_settings.DEFAULT_LANGUAGE,
    "dtmf_menu": {
        "1": {"intent": "incident", "label": "Incidencia"},
        "2": {"intent": "query", "label": "Consulta"},
        "3": {"intent": "urgent", "label": "Urgente"},
        "0": {"intent": "agent", "label": "Hablar con agente"},
    },
    "intent_keywords": {
        "incident": ["error", "no funciona", "caído", "falla", "problema", "roto", "bloqueado"],
        "query": ["cómo", "información", "consulta", "pregunta", "saber", "explicar"],
        "urgent": ["urgente", "crítico", "emergencia", "parado", "crisis"],
        "agent": ["agente", "persona", "humano", "operador"],
    },
}

_PRIORITY_MAP = {
    "incident": "medium",
    "query": "low",
    "urgent": "critical",
    "agent": "high",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_json(db: Session, key: str, org_id: Optional[str], *, default=None):
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if org_id:
        q = q.filter(AppSetting.organization_id == org_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row or not row.value:
        return default
    try:
        return json.loads(row.value)
    except Exception:
        logging.getLogger(__name__).debug("_get_json: excepcion ignorada", exc_info=True)
        return default


def _set_json(db: Session, key: str, org_id: Optional[str], value: Any, description: str = "") -> None:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if org_id:
        q = q.filter(AppSetting.organization_id == org_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row:
        row = AppSetting(key=key, organization_id=org_id, description=description, value=payload)
        db.add(row)
    else:
        row.value = payload
    db.commit()


def _classify_intent(text: str, config: Dict[str, Any]) -> str:
    """Rule-based intent classification from transcript text."""
    lower = text.lower()
    kw_map = config.get("intent_keywords", _DEFAULT_CONFIG["intent_keywords"])
    scores: Dict[str, int] = {}
    for intent, keywords in kw_map.items():
        scores[intent] = sum(1 for kw in keywords if kw in lower)
    if not any(scores.values()):
        return "unknown"
    return max(scores, key=scores.get)  # type: ignore[arg-type]


def _extract_entities(text: str) -> Dict[str, Any]:
    """Extract basic entities (CI name, user, priority words) from transcript."""
    entities: Dict[str, Any] = {}
    # ticket ID pattern e.g. INC-1234 or TKT-0042
    m = re.search(r"\b(INC|TKT|CHG|PRB)-\d+\b", text, re.IGNORECASE)
    if m:
        entities["ticket_ref"] = m.group(0).upper()
    # urgency words
    urgency = [w for w in ["urgente", "crítico", "emergencia", "bloqueado"] if w in text.lower()]
    if urgency:
        entities["urgency_words"] = urgency
    # email-like
    em = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
    if em:
        entities["email"] = em.group(0)
    return entities


# ── Public API ──────────────────────────────────────────────────────────────────

def get_config(db: Session, org_id: Optional[str]) -> Dict[str, Any]:
    return _get_json(db, _CONFIG_KEY, org_id, default=_DEFAULT_CONFIG) or _DEFAULT_CONFIG


def update_config(db: Session, org_id: Optional[str], updates: Dict[str, Any]) -> Dict[str, Any]:
    cfg = get_config(db, org_id)
    cfg.update(updates)
    _set_json(db, _CONFIG_KEY, org_id, cfg, "Voice Agent IVR configuration")
    return cfg


def create_session(db: Session, org_id: Optional[str], caller_id: str, channel: str = "phone") -> Dict[str, Any]:
    sessions = _get_json(db, _SESSIONS_KEY, org_id, default={}) or {}
    sid = str(uuid.uuid4())
    session = {
        "id": sid,
        "caller_id": caller_id,
        "channel": channel,
        "status": "active",
        "intent": None,
        "entities": {},
        "transcript": [],
        "ticket_id": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    sessions[sid] = session
    _set_json(db, _SESSIONS_KEY, org_id, sessions, "Voice Agent session store")
    cfg = get_config(db, org_id)
    return {"session": session, "greeting": cfg.get("greeting", _DEFAULT_CONFIG["greeting"])}


def add_transcript_turn(
    db: Session, org_id: Optional[str], session_id: str, speaker: str, text: str
) -> Dict[str, Any]:
    sessions = _get_json(db, _SESSIONS_KEY, org_id, default={}) or {}
    session = sessions.get(session_id)
    if not session:
        raise ErrorConCodigo("no_encontrado", detail=f"Session {session_id!r} not found", que="sesion")
    turn = {"speaker": speaker, "text": text, "ts": _now_iso()}
    session["transcript"].append(turn)
    # Classify intent from user turns
    if speaker == "user":
        cfg = get_config(db, org_id)
        intent = _classify_intent(text, cfg)
        if intent != "unknown":
            session["intent"] = intent
        entities = _extract_entities(text)
        session["entities"].update(entities)
    session["updated_at"] = _now_iso()
    sessions[session_id] = session
    _set_json(db, _SESSIONS_KEY, org_id, sessions, "Voice Agent session store")
    return session


def close_session(
    db: Session, org_id: Optional[str], session_id: str, resolution: str = "resolved"
) -> Dict[str, Any]:
    sessions = _get_json(db, _SESSIONS_KEY, org_id, default={}) or {}
    session = sessions.get(session_id)
    if not session:
        raise ErrorConCodigo("no_encontrado", detail=f"Session {session_id!r} not found", que="sesion")
    session["status"] = "closed"
    session["resolution"] = resolution
    session["closed_at"] = _now_iso()
    sessions[session_id] = session
    _set_json(db, _SESSIONS_KEY, org_id, sessions, "Voice Agent session store")
    return session


def create_ticket_from_session(
    db: Session, org_id: Optional[str], session_id: str, created_by_id: Any
) -> Dict[str, Any]:
    """Create a real Service Desk ticket from the voice session summary."""
    sessions = _get_json(db, _SESSIONS_KEY, org_id, default={}) or {}
    session = sessions.get(session_id)
    if not session:
        raise ErrorConCodigo("no_encontrado", detail=f"Session {session_id!r} not found", que="sesion")

    from app.models.service_desk import Ticket, TicketHistory, TicketImpact, TicketPriority, TicketType, TicketUrgency
    from app.services.sla_service import next_ticket_number

    intent = session.get("intent", "query")
    # «Urgente», «crítico»… mandan aunque la intencion ganadora sea otra: «no
    # funciona, es urgente» empata y se quedaba en incidencia media.
    if intent != "urgent" and (session.get("entities") or {}).get("urgency_words"):
        intent = "urgent"
    transcript_text = " ".join(t["text"] for t in session.get("transcript", []) if t["speaker"] == "user")
    priority_map = {
        "critical": TicketPriority.p1_critical,
        "high": TicketPriority.p2_high,
        "medium": TicketPriority.p3_medium,
        "low": TicketPriority.p4_low,
    }
    urgency = TicketUrgency.high if intent in ("urgent", "agent") else TicketUrgency.medium
    impact = TicketImpact.department if intent == "urgent" else TicketImpact.user
    priority = priority_map.get(_PRIORITY_MAP.get(intent, "medium"), TicketPriority.p3_medium)

    ticket = Ticket(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        number=next_ticket_number(TicketType.incident.value, db),
        ticket_type=TicketType.incident,
        title=(transcript_text[:120] or f"Voice call: {intent}").strip(),
        description=transcript_text or f"Voice session from {session.get('caller_id')}",
        status="new",
        priority=priority,
        urgency=urgency,
        impact=impact,
        support_level="l1",
        requester_name=session.get("caller_id"),
        requester_email=session.get("entities", {}).get("email"),
        source="voice_agent",
        created_by_user_id=str(created_by_id),
    )
    db.add(ticket)
    db.flush()

    db.add(TicketHistory(
        ticket_id=ticket.id,
        field_name="voice_session",
        old_value=None,
        new_value=session_id,
        changed_by_user_id=str(created_by_id),
    ))

    session["ticket_id"] = ticket["id"] if isinstance(ticket, dict) else ticket.id
    sessions[session_id] = session
    _set_json(db, _SESSIONS_KEY, org_id, sessions, "Voice Agent session store")
    db.commit()
    return {
        "id": ticket.id,
        "number": ticket.number,
        "source": ticket.source,
        "channel": session.get("channel", "phone"),
        "caller_id": session.get("caller_id"),
        "intent": intent,
        "priority": ticket.priority.value if hasattr(ticket.priority, "value") else ticket.priority,
        "summary": ticket.title,
        "session_id": session_id,
        "created_at": _now_iso(),
    }


def list_sessions(
    db: Session, org_id: Optional[str], status: Optional[str] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    sessions = _get_json(db, _SESSIONS_KEY, org_id, default={}) or {}
    items = list(sessions.values())
    if status:
        items = [s for s in items if s.get("status") == status]
    items.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return items[:limit]


# ── Llamadas entrantes de Twilio (varias organizaciones) ───────────────────────
#
# Segunda auditoria 2026-11 (#19): la voz era MONO-ORGANIZACION (token global,
# sesion sin organizacion). Ahora la organizacion sale del numero llamado (`To`),
# la firma se verifica con el token de ESA organizacion (o el global si no tiene
# propio, como el SMS) y la llamada se atiende dentro de su contexto de tenant.
# Un numero desconocido, de dos organizaciones o de una desactivada se rechaza.

LLAMADA_ACEPTADA = "aceptada"
LLAMADA_NUMERO_DESCONOCIDO = "numero_desconocido"
LLAMADA_FIRMA_INVALIDA = "firma_invalida"


def verificar_llamada_de_twilio(
    db: Session, url, form: Dict[str, Any], firma: Optional[str],
) -> tuple[str, Optional[str]]:
    """`(veredicto, org_id)` de un webhook de voz de Twilio.

    Con numero conocido la firma se comprueba con el token de su organizacion.
    Con numero desconocido no hay organizacion: la firma se comprueba con el
    token global solo para distinguir a Twilio (rechazo limpio de la llamada)
    de un tercero (403); en ningun caso se atiende la llamada.
    """
    from app.services.entrada_service import organizacion_desactivada
    from app.services.service_desk.sms_service import (
        firma_de_twilio_valida,
        organizacion_del_numero_de_twilio,
        twilio_auth_token_de_la_organizacion,
    )

    org_id = organizacion_del_numero_de_twilio(db, form.get("To"))
    if org_id is not None and organizacion_desactivada(db, org_id):
        org_id = None
    token = twilio_auth_token_de_la_organizacion(db, org_id)
    if not firma_de_twilio_valida(url, form, firma, token):
        return LLAMADA_FIRMA_INVALIDA, None
    if org_id is None:
        logging.getLogger(__name__).warning(
            "Twilio voz: llamada a %r sin organizacion; se rechaza", form.get("To"))
        return LLAMADA_NUMERO_DESCONOCIDO, None
    return LLAMADA_ACEPTADA, org_id


def atender_llamada_de_twilio(db: Session, org_id: str, caller_id: str, call_sid: str) -> Dict[str, Any]:
    """Abre la sesion de voz de la llamada en `org_id` y devuelve `{session_id, config}`."""
    from app.services.service_desk.ticket_events import como_organizacion

    with como_organizacion(db, org_id):
        creada = create_session(db, org_id, caller_id, channel="phone")
        session_id = creada["session"]["id"]
        add_transcript_turn(db, org_id, session_id, "bot", f"Incoming call from {caller_id} (SID: {call_sid})")
        return {"session_id": session_id, "config": get_config(db, org_id)}


def registrar_opcion_de_twilio(db: Session, org_id: str, session_id: Optional[str], digito: str) -> Dict[str, Any]:
    """La opcion DTMF elegida en `org_id`: `{label, queue, language}`.

    El turno se anota solo si la sesion es de esa organizacion; un `session_id`
    ajeno o inexistente no se toca (antes cualquiera escribia en cualquiera).
    """
    from app.services.service_desk.ticket_events import como_organizacion

    with como_organizacion(db, org_id):
        cfg = get_config(db, org_id)
        opcion = (cfg.get("dtmf_menu") or {}).get(digito, {})
        etiqueta = opcion.get("label", "") if isinstance(opcion, dict) else str(opcion)
        cola = opcion.get("intent", "general") if isinstance(opcion, dict) else (opcion or "general")
        if session_id:
            try:
                add_transcript_turn(db, org_id, session_id, "user", f"DTMF selection: {digito} → {etiqueta or cola}")
            except ValueError:
                logging.getLogger(__name__).warning(
                    "Twilio voz: sesion %s no es de la organizacion %s; no se anota", session_id, org_id)
    return {"label": etiqueta, "queue": cola or "general",
            "language": cfg.get("language", app_settings.DEFAULT_LANGUAGE)}
