"""RGPD de las reuniones: acceso/portabilidad y supresión de una persona,
también cuando solo fue **hablante** (identificada por su usuario o su correo).

La engancha `cab_service/gdpr.py` (copia y supresión de las solicitudes RGPD)
y `supresion_service.suprimir_persona`; también la usan las rutas
`/meeting-assistant/gdpr/person`. Una reunión bajo bloqueo legal no se toca: se
informa en `held`.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

BORRADO = "[ERASED]"


def _participaciones(db: Session, org: Optional[str], user_id: Optional[str], email: Optional[str]):
    from app.models.reuniones import AIMeetingParticipant
    conds = []
    if user_id:
        conds.append(AIMeetingParticipant.user_id == user_id)
    if email:
        conds.append(func.lower(AIMeetingParticipant.email) == email.strip().lower())
    if not conds:
        return []
    q = db.query(AIMeetingParticipant).filter(or_(*conds))
    if org:
        q = q.filter(AIMeetingParticipant.organization_id == org)
    return q.all()


def hay_datos(db: Session, org, user_id=None, email=None) -> bool:
    return bool(_participaciones(db, org, user_id, email))


def copia(db: Session, org, user_id=None, email=None) -> dict:
    """Sus reuniones, lo que dijo, su consentimiento y sus acciones (art. 15 y 20)."""
    from app.models.ai_chat import AIMeetingAction
    reuniones = []
    for p in _participaciones(db, org, user_id, email):
        m = p.meeting
        dijo = [{"start_ms": s.start_ms, "end_ms": s.end_ms, "text": s.text, "language": s.language}
                for s in m.segmentos if s.participant_id == p.id or (user_id and s.user_id == user_id)]
        acciones = [{"description": a.description, "due_date": a.due_date.isoformat() if a.due_date else None}
                    for a in m.actions if user_id and a.assignee_id == user_id]
        reuniones.append({"meeting_id": m.id, "title": m.title, "origin": m.origin,
                          "meeting_date": m.meeting_date.isoformat() if m.meeting_date else None,
                          "role": p.role, "name": p.name, "email": p.email,
                          "consent": p.consent, "consent_method": p.consent_method,
                          "consent_at": p.consent_at.isoformat() if p.consent_at else None,
                          "said": dijo, "actions": acciones,
                          "audio_held_until": m.audio_expires_at.isoformat() if m.audios and m.audio_expires_at
                          else None})
    if user_id:   # acciones de reuniones en las que no figura como participante
        vistos = {r["meeting_id"] for r in reuniones}
        q = db.query(AIMeetingAction).filter(AIMeetingAction.assignee_id == user_id)
        if org:
            q = q.filter(AIMeetingAction.organization_id == org)
        for a in q.all():
            if a.meeting_id not in vistos:
                reuniones.append({"meeting_id": a.meeting_id, "title": a.meeting.title, "role": "responsable",
                                  "said": [], "actions": [{"description": a.description,
                                                           "due_date": a.due_date.isoformat() if a.due_date else None}]})
    return {"meetings": reuniones, "meetings_count": len(reuniones)}


def suprimir(db: Session, org, user_id=None, email=None) -> dict:
    """Tacha lo que dijo, anonimiza su participación, borra el audio de esas reuniones
    y las traducciones, y pide al proveedor del bot borrar sus medios. No confirma."""
    from app.db.bloqueo_legal import _bloqueo_de, bloqueos_activos
    from app.services.reuniones import almacen
    from app.services.reuniones.eventos import evento
    informe = {"meetings": 0, "segments": 0, "audio_chunks": 0, "held": []}
    bloqueos_por_org: dict = {}
    for p in _participaciones(db, org, user_id, email):
        m = p.meeting
        if m.organization_id not in bloqueos_por_org:
            bloqueos_por_org[m.organization_id] = bloqueos_activos(db, m.organization_id)
        b = _bloqueo_de("meetings", m, bloqueos_por_org[m.organization_id])
        if b is not None:
            informe["held"].append({"meeting_id": m.id, "case": b.case_reference})
            continue
        for s in m.segmentos:
            if s.participant_id == p.id or (user_id and s.user_id == user_id):
                s.text, s.speaker, s.user_id = BORRADO, BORRADO, None
                informe["segments"] += 1
        p.name, p.email, p.user_id, p.consent_by = BORRADO, None, None, None
        for a in list(m.audios):
            almacen.borrar(a.storage_key)
            m.audios.remove(a)
            informe["audio_chunks"] += 1
        for t in list(m.traducciones):
            m.traducciones.remove(t)
        if user_id:
            for a in m.actions:
                if a.assignee_id == user_id:
                    a.assignee_name = BORRADO
        if m.bot_provider and m.bot_id:
            from app.services.reuniones.servicio import _borrar_medios_en_el_proveedor
            _borrar_medios_en_el_proveedor(db, m)
        evento(db, m, "gdpr_erased", None, {"segments": informe["segments"]})
        informe["meetings"] += 1
    db.flush()
    return informe
