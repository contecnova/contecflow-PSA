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

Configuracion en `AppSetting`; las sesiones, en `sd_voice_sessions` (migracion 200).
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

#: Clave antigua (hasta la migracion 200 las sesiones vivian aqui); ya no se escribe.
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


# ── Sesiones (migracion 200: tabla `sd_voice_sessions`) ────────────────────────
#
# Antes todas las sesiones de la empresa iban en UN blob JSON de `AppSetting`
# (`sd.voice_agent.sessions`): telefono y transcripcion en claro, sin retencion
# ni supresion, y dos llamadas a la vez se pisaban. Ahora una fila por llamada,
# con el numero y la transcripcion cifrados y la huella HMAC del numero para
# buscar (bloqueo legal y RGPD). La forma del diccionario que devuelve la API
# no cambia.


def huella_del_numero(numero: Optional[str]) -> Optional[str]:
    """HMAC-SHA256 (con `SECRET_KEY`) del numero normalizado: busca sin guardar el numero en claro."""
    import hashlib
    import hmac
    limpio = re.sub(r"[^\d+]", "", numero or "")
    if not limpio:
        return None
    clave = (getattr(app_settings, "SECRET_KEY", "") or "").encode()
    return hmac.new(clave, limpio.encode(), hashlib.sha256).hexdigest()


def _cifrar_json(valor: Any) -> str:
    from app.core.encryption import encrypt_value
    return encrypt_value(json.dumps(valor, ensure_ascii=False, separators=(",", ":")))


def _descifrar_json(valor: Optional[str], respaldo):
    if not valor:
        return respaldo
    from app.core.encryption import decrypt_value
    try:
        return json.loads(decrypt_value(valor) or "null") or respaldo
    except Exception:
        logging.getLogger(__name__).warning("voz: no se pudo descifrar una sesion")
        return respaldo


def _iso(fecha) -> Optional[str]:
    return fecha.isoformat() if fecha else None


def _a_dict(fila) -> Dict[str, Any]:
    from app.core.encryption import decrypt_value
    salida = {
        "id": fila.id,
        "caller_id": (decrypt_value(fila.caller_id_enc) if fila.caller_id_enc else None)
        or (f"***{fila.caller_id_last4}" if fila.caller_id_last4 else None),
        "channel": fila.channel,
        "status": fila.status,
        "intent": fila.intent,
        "entities": _descifrar_json(fila.entities_enc, {}),
        "transcript": _descifrar_json(fila.transcript_enc, []),
        "ticket_id": fila.ticket_id,
        "created_at": _iso(fila.created_at),
        "updated_at": _iso(fila.updated_at),
    }
    if fila.resolution:
        salida["resolution"] = fila.resolution
    if fila.closed_at:
        salida["closed_at"] = _iso(fila.closed_at)
    return salida


def _sesion(db: Session, org_id: Optional[str], session_id: str):
    from app.models.service_desk import VoiceSession
    q = db.query(VoiceSession).filter(VoiceSession.id == session_id)
    q = q.filter(VoiceSession.organization_id == org_id) if org_id else q.filter(VoiceSession.organization_id.is_(None))
    fila = q.first()
    if fila is None:
        raise ErrorConCodigo("no_encontrado", detail=f"Session {session_id!r} not found", que="sesion")
    return fila


def create_session(db: Session, org_id: Optional[str], caller_id: str, channel: str = "phone") -> Dict[str, Any]:
    from app.core.encryption import encrypt_value
    from app.models.service_desk import VoiceSession
    if not org_id:
        # `sd_voice_sessions.organization_id` es obligatoria: sin empresa no hay sesion.
        raise ErrorConCodigo("empresa_requerida")
    digitos = re.sub(r"\D", "", caller_id or "")
    ahora = datetime.now(timezone.utc)
    fila = VoiceSession(
        id=str(uuid.uuid4()), organization_id=org_id,
        caller_id_hash=huella_del_numero(caller_id), caller_id_last4=digitos[-4:] or None,
        caller_id_enc=encrypt_value(caller_id) if caller_id else None,
        channel=channel, status="active", entities_enc=_cifrar_json({}), transcript_enc=_cifrar_json([]),
        created_at=ahora, updated_at=ahora,
    )
    db.add(fila)
    db.commit()
    cfg = get_config(db, org_id)
    return {"session": _a_dict(fila), "greeting": cfg.get("greeting", _DEFAULT_CONFIG["greeting"])}


def add_transcript_turn(
    db: Session, org_id: Optional[str], session_id: str, speaker: str, text: str
) -> Dict[str, Any]:
    fila = _sesion(db, org_id, session_id)
    transcript = _descifrar_json(fila.transcript_enc, [])
    transcript.append({"speaker": speaker, "text": text, "ts": _now_iso()})
    fila.transcript_enc = _cifrar_json(transcript)
    # Classify intent from user turns
    if speaker == "user":
        cfg = get_config(db, org_id)
        intent = _classify_intent(text, cfg)
        if intent != "unknown":
            fila.intent = intent
        entidades = _descifrar_json(fila.entities_enc, {})
        entidades.update(_extract_entities(text))
        fila.entities_enc = _cifrar_json(entidades)
    fila.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _a_dict(fila)


def close_session(
    db: Session, org_id: Optional[str], session_id: str, resolution: str = "resolved"
) -> Dict[str, Any]:
    fila = _sesion(db, org_id, session_id)
    fila.status = "closed"
    fila.resolution = resolution
    fila.closed_at = datetime.now(timezone.utc)
    db.commit()
    return _a_dict(fila)


def create_ticket_from_session(
    db: Session, org_id: Optional[str], session_id: str, created_by_id: Any
) -> Dict[str, Any]:
    """Create a real Service Desk ticket from the voice session summary."""
    fila = _sesion(db, org_id, session_id)
    session = _a_dict(fila)

    from app.models.service_desk import Ticket, TicketHistory, TicketImpact, TicketPriority, TicketType, TicketUrgency
    from app.services.sla_service import next_ticket_number

    intent = session.get("intent") or "query"
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

    fila.ticket_id = ticket.id
    fila.updated_at = datetime.now(timezone.utc)
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
    from app.models.service_desk import VoiceSession
    q = db.query(VoiceSession)
    q = q.filter(VoiceSession.organization_id == org_id) if org_id else q.filter(VoiceSession.organization_id.is_(None))
    if status:
        q = q.filter(VoiceSession.status == status)
    return [_a_dict(f) for f in q.order_by(VoiceSession.created_at.desc()).limit(limit).all()]


# ── RGPD (migracion 200) ───────────────────────────────────────────────────────

def sesiones_de_numero(db: Session, numero: Optional[str], org_id: Optional[str] = None) -> list:
    """Sesiones de voz de ese numero (por su huella), en `org_id` si se da."""
    from app.models.service_desk import VoiceSession
    huella = huella_del_numero(numero)
    if not huella:
        return []
    q = db.query(VoiceSession).filter(VoiceSession.caller_id_hash == huella)
    if org_id:
        q = q.filter(VoiceSession.organization_id == org_id)
    return q.order_by(VoiceSession.created_at).all()


def copia_rgpd(db: Session, numero: Optional[str], org_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Copia (art. 15/20) de las sesiones de voz de ese numero."""
    return [_a_dict(f) for f in sesiones_de_numero(db, numero, org_id)]


def suprimir_rgpd(db: Session, numero: Optional[str], org_id: Optional[str] = None) -> int:
    """Borra las sesiones de voz de ese numero (art. 17). El bloqueo legal lo impide (before_flush). No hace commit."""
    filas = sesiones_de_numero(db, numero, org_id)
    for f in filas:
        db.delete(f)
    db.flush()
    return len(filas)


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
