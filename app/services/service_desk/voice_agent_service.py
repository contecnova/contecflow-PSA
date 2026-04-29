"""
voice_agent_service.py — IVR / Voice Agent service for Service Desk.

Provides:
  - Session management for voice calls (create, update, close)
  - Intent classification (rule-based + LLM-optional fallback)
  - Entity extraction from transcripts
  - Auto-ticket creation from voice sessions
  - DTMF menu tree configuration

All state stored as AppSetting JSON blobs (no new DB tables).
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting

_SESSIONS_KEY = "sd.voice_agent.sessions"
_CONFIG_KEY = "sd.voice_agent.config"

_DEFAULT_CONFIG: Dict[str, Any] = {
    "greeting": "Bienvenido al servicio de soporte. Diga su solicitud o pulse 1 para incidencias, 2 para consultas, 3 para urgencias.",
    "max_silence_seconds": 10,
    "language": "es-ES",
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
        raise ValueError(f"Session {session_id!r} not found")
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
        raise ValueError(f"Session {session_id!r} not found")
    session["status"] = "closed"
    session["resolution"] = resolution
    session["closed_at"] = _now_iso()
    sessions[session_id] = session
    _set_json(db, _SESSIONS_KEY, org_id, sessions, "Voice Agent session store")
    return session


def create_ticket_from_session(
    db: Session, org_id: Optional[str], session_id: str, created_by_id: Any
) -> Dict[str, Any]:
    """Create a Service Desk ticket from the voice session summary."""
    sessions = _get_json(db, _SESSIONS_KEY, org_id, default={}) or {}
    session = sessions.get(session_id)
    if not session:
        raise ValueError(f"Session {session_id!r} not found")
    intent = session.get("intent", "query")
    transcript_text = " ".join(t["text"] for t in session.get("transcript", []) if t["speaker"] == "user")
    ticket = {
        "id": str(uuid.uuid4()),
        "source": "voice_agent",
        "caller_id": session.get("caller_id"),
        "channel": session.get("channel", "phone"),
        "intent": intent,
        "priority": _PRIORITY_MAP.get(intent, "medium"),
        "summary": transcript_text[:200] or f"Llamada de voz: {intent}",
        "entities": session.get("entities", {}),
        "session_id": session_id,
        "created_by": str(created_by_id),
        "created_at": _now_iso(),
    }
    session["ticket_id"] = ticket["id"]
    sessions[session_id] = session
    _set_json(db, _SESSIONS_KEY, org_id, sessions, "Voice Agent session store")
    return ticket


def list_sessions(
    db: Session, org_id: Optional[str], status: Optional[str] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    sessions = _get_json(db, _SESSIONS_KEY, org_id, default={}) or {}
    items = list(sessions.values())
    if status:
        items = [s for s in items if s.get("status") == status]
    items.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return items[:limit]
