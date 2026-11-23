"""Quién ve y quién gestiona cada reunión, y cómo se serializa.

Visible = quien la creó, participantes con usuario, responsables de sus
acciones, el jefe del proyecto vinculado, o `reuniones.ver_todas`. Gestor =
quien la creó, el jefe del proyecto o `reuniones.ver_todas`. Fuera de lo
visible: 404 (no se confirma que exista). Listados, búsqueda, Nexus y
descargas pasan todos por aquí.
"""
from __future__ import annotations
import logging

import json
from typing import Optional

from sqlalchemy import exists, or_
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error


def _cap(db: Session, usuario, capacidad: str) -> bool:
    if getattr(usuario, "is_superadmin", False):
        return True
    from app.core.capacidades import tiene
    try:
        return tiene(db, usuario, capacidad)
    except Exception:
        logging.getLogger(__name__).debug("_cap: excepcion ignorada", exc_info=True)
        return False


def ve_todas(db: Session, usuario) -> bool:
    return _cap(db, usuario, "reuniones.ver_todas")


def filtro_visibles(db: Session, usuario):
    """Expresión SQL de las reuniones que ve `usuario` (None = todas)."""
    from app.models.ai_chat import AIMeeting, AIMeetingAction
    from app.models.project import Project
    from app.models.reuniones import AIMeetingParticipant
    if ve_todas(db, usuario):
        return None
    uid = usuario.id
    return or_(
        AIMeeting.created_by == uid,
        exists().where(AIMeetingParticipant.meeting_id == AIMeeting.id, AIMeetingParticipant.user_id == uid),
        exists().where(AIMeetingAction.meeting_id == AIMeeting.id, AIMeetingAction.assignee_id == uid),
        exists().where(Project.id == AIMeeting.project_id, Project.pm_id == uid),
    )


def visibles(db: Session, usuario):
    from app.models.ai_chat import AIMeeting
    q = db.query(AIMeeting)
    f = filtro_visibles(db, usuario)
    return q.filter(f) if f is not None else q


def es_gestor(db: Session, usuario, reunion) -> bool:
    if ve_todas(db, usuario) or reunion.created_by == usuario.id:
        return True
    if reunion.project_id:
        from app.models.project import Project
        p = db.get(Project, reunion.project_id)
        return bool(p and p.pm_id == usuario.id)
    return False


def puede_escuchar(db: Session, usuario, reunion) -> bool:
    """El audio: quien gestiona o quien estuvo (no basta ser responsable de una acción)."""
    if es_gestor(db, usuario, reunion):
        return True
    return any(p.user_id == usuario.id for p in reunion.participantes)


def obtener(db: Session, usuario, reunion_id: str):
    reunion = visibles(db, usuario).filter_by(id=reunion_id).first()
    if reunion is None:
        raise error(404, "reunion_no_encontrada")
    return reunion


def obtener_gestionable(db: Session, usuario, reunion_id: str):
    reunion = obtener(db, usuario, reunion_id)
    if not es_gestor(db, usuario, reunion):
        raise error(403, "sin_permiso", detail="Solo quien gestiona la reunión puede hacer esto")
    return reunion


def bloqueo_legal(db: Session, reunion):
    from app.db.bloqueo_legal import _bloqueo_de, bloqueos_activos
    return _bloqueo_de("meetings", reunion, bloqueos_activos(db, reunion.organization_id))


def _json(texto, defecto=None):
    try:
        return json.loads(texto) if texto else (defecto if defecto is not None else [])
    except ValueError:
        return defecto if defecto is not None else []


def _iso(v) -> Optional[str]:
    return v.isoformat() if v is not None and hasattr(v, "isoformat") else (str(v) if v else None)


def consentimiento_completo(reunion) -> bool:
    if not reunion.consent_required:
        return True
    # Todos han respondido; un «no» no bloquea: sus segmentos se tachan antes de analizar.
    return all(p.consent is not None for p in reunion.participantes)


def resumen(db: Session, usuario, m) -> dict:
    from app.models.clients import Client
    cliente = db.get(Client, m.client_id) if m.client_id else None
    return {
        "id": m.id, "title": m.title, "status": m.status, "origin": m.origin or "transcript",
        "platform": m.platform, "project_id": m.project_id,
        "project_name": m.project.name if m.project_id and m.project else None,
        "client_id": m.client_id, "client_name": getattr(cliente, "name", None),
        "meeting_date": _iso(m.meeting_date), "duration_min": m.duration_min,
        "actions_count": len(m.actions), "created_actions": sum(1 for a in m.actions if a.is_created),
        "has_audio": bool(m.audios), "consent_pending": not consentimiento_completo(m),
        "bot_status": m.bot_status, "error_code": m.error_code,
        "created_at": _iso(m.created_at), "can_manage": es_gestor(db, usuario, m),
        "call_id": m.call_id, "conversation_id": m.conversation_id,
    }


def detalle(db: Session, usuario, m, traducido: Optional[dict] = None) -> dict:
    """El detalle; `traducido` (de `traduccion.traducir_reunion`) sustituye los textos."""
    base = resumen(db, usuario, m)
    t = traducido or {}
    acciones_t = {a["id"]: a for a in t.get("actions", [])}
    segmentos_t = {s["id"]: s for s in t.get("segments", [])}
    gestor = base["can_manage"]
    base.update({
        "summary": t.get("summary", m.summary),
        "decisions": t.get("decisions", _json(m.decisions)),
        "risks": t.get("risks", _json(m.risks_mentioned)),
        "open_questions": t.get("open_questions", _json(m.open_questions)),
        "original_language": m.original_language,
        "display_language": t.get("language", m.original_language),
        "translation": t.get("translation", {"status": "original", "reason": None}),
        "participants": [{
            "id": p.id, "user_id": p.user_id, "name": p.name, "email": p.email, "role": p.role,
            "consent": p.consent, "consent_method": p.consent_method, "consent_at": _iso(p.consent_at),
            "language": p.language,
        } for p in m.participantes],
        "segments": [{
            "id": s.id, "order": s.orden, "speaker": s.speaker, "user_id": s.user_id,
            "participant_id": s.participant_id, "start_ms": s.start_ms, "end_ms": s.end_ms,
            "text": segmentos_t.get(s.id, {}).get("text", s.text), "language": s.language,
        } for s in m.segmentos],
        "actions": [{
            "id": a.id, "description": acciones_t.get(a.id, {}).get("description", a.description),
            "assignee_name": a.assignee_name, "assignee_id": a.assignee_id,
            "due_date": a.due_date.date().isoformat() if a.due_date else None,
            "due_date_text": a.due_date_text, "is_created": bool(a.is_created),
            "task_id": a.task_id, "ticket_id": a.ticket_id,
        } for a in m.actions],
        "minutes_document_id": m.minutes_document_id,
        "audio": ({"chunks": len(m.audios), "bytes": sum(x.bytes or 0 for x in m.audios),
                   "expires_at": _iso(m.audio_expires_at)} if m.audios else None),
        "transcript_expires_at": _iso(m.transcript_expires_at),
        "transcript_purged": m.transcript_purged_at is not None,
        "join_url": m.join_url,
        "bot": ({"provider": m.bot_provider, "status": m.bot_status, "bot_id": m.bot_id}
                if m.bot_provider else None),
        "consent": {"required": bool(m.consent_required),
                    "notice_confirmed_by": m.notice_confirmed_by,
                    "notice_confirmed_at": _iso(m.notice_confirmed_at),
                    "complete": consentimiento_completo(m)},
        "permissions": {"manage": gestor, "listen": puede_escuchar(db, usuario, m)},
        "legal_hold": bloqueo_legal(db, m) is not None,
        "events": [{"type": e.tipo, "at": _iso(e.created_at), "actor": e.actor_id,
                    "data": _json(e.datos, {})} for e in m.eventos[-50:]],
    })
    return base
