"""Trabajos de fondo por empresa (`app/worker.py`, `en_cada_organizacion`).

- `sondeo` (cada 15 min): Teams y Meet de quien activó «recoger mis
  reuniones», bots para las reuniones de la próxima hora del calendario de
  quien lo pidió, y renovación de la suscripción de Graph.
- `retencion` (diario): audio caducado y transcripciones caducadas, salvo bajo
  bloqueo legal. El resumen y las acciones se quedan (son el registro de trabajo).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_URL = re.compile(r"https://[^\s\"'<>]*(?:teams\.microsoft\.com|teams\.live\.com|zoom\.us|meet\.google\.com|webex\.com)"
                  r"[^\s\"'<>]*", re.I)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _instante(valor):
    """ISO de Graph (`2026-11-19T10:00:00.0000000Z`) a datetime con zona, o None."""
    if not valor:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", str(valor))
    if not m:
        return None
    return datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc)


def _personas(db: Session, campo: str):
    from app.models.reuniones import AIMeetingUserPrefs
    from app.models.user import User
    return (db.query(User).join(AIMeetingUserPrefs, AIMeetingUserPrefs.user_id == User.id)
            .filter(getattr(AIMeetingUserPrefs, campo).is_(True), User.is_active.is_(True)).all())


def sondeo(db: Session, org: str) -> dict:
    from app.services.reuniones import config
    from app.services.reuniones.servicio import guardar_importada
    cfg = config.leer(db, org)
    hecho = {"teams": 0, "meet": 0, "bots": 0, "errores": 0}

    if cfg["teams"]["enabled"]:
        from app.services.reuniones.conectores import teams
        if cfg["teams"]["mode"] == "subscription":
            caduca = _instante(cfg["teams"].get("subscription_expires_at"))
            try:
                if caduca is None or caduca < _ahora() + timedelta(minutes=20):
                    teams.suscribir(db, org)
            except Exception:  # noqa: BLE001
                hecho["errores"] += 1
                logger.warning("reuniones: no se pudo renovar la suscripción de Graph (%s)", org, exc_info=True)
        else:
            for persona in _personas(db, "collect_teams"):
                try:
                    for imp in teams.terminadas_de(db, org, persona.email, horas=6):
                        guardar_importada(db, org, imp, persona)
                        hecho["teams"] += 1
                except Exception:  # noqa: BLE001
                    hecho["errores"] += 1
                    logger.warning("reuniones: sondeo de Teams de %s", persona.id, exc_info=True)

    if cfg["meet"]["enabled"]:
        from app.services.reuniones.conectores import meet
        for persona in _personas(db, "collect_meet"):
            try:
                for imp in meet.terminadas_de(db, org, persona.email, horas=6):
                    guardar_importada(db, org, imp, persona)
                    hecho["meet"] += 1
            except Exception:  # noqa: BLE001
                hecho["errores"] += 1
                logger.warning("reuniones: sondeo de Meet de %s", persona.id, exc_info=True)

    if cfg["bots"]["enabled"] and cfg["bots"].get("contract_reference"):
        hecho["bots"] = _bots_de_calendario(db, org, hecho)
    db.flush()
    return hecho


def _bots_de_calendario(db: Session, org: str, hecho: dict) -> int:
    from app.models.ai_chat import AIMeeting
    from app.models.cab import CalendarEvent
    from app.services.reuniones.servicio import invitar_bot
    from app.models.reuniones import AIMeetingUserPrefs
    from app.models.user import User, UserRole
    n = 0
    ahora = _ahora()
    # 19-11-2026: el bot entra por defecto en las reuniones del calendario de TODA
    # persona interna activa de la empresa; solo se salta a quien lo ha desactivado
    # en «Mis preferencias». Sin contrato ni clave del proveedor, `invitar_bot` no
    # envía nada (RGPD art. 28) y queda como error contado, sin salir datos.
    desactivados = {u for (u,) in db.query(AIMeetingUserPrefs.user_id)
                    .filter(AIMeetingUserPrefs.bot_for_my_calendar.is_(False)).all()}
    personas = (db.query(User).filter(User.organization_id == org, User.is_active.is_(True),
                                      User.role != UserRole.subcontractor).all())
    for persona in personas:
        if persona.id in desactivados:
            continue
        eventos = db.query(CalendarEvent).filter(CalendarEvent.user_id == persona.id,
                                                 CalendarEvent.start_dt >= ahora,
                                                 CalendarEvent.start_dt <= ahora + timedelta(hours=1)).all()
        for ev in eventos:
            m = _URL.search(f"{ev.location or ''} {ev.description or ''}")
            if not m:
                continue
            if db.query(AIMeeting.id).filter(AIMeeting.calendar_event_id == ev.id).first():
                continue
            try:
                invitar_bot(db, persona, {"meeting_url": m.group(0), "title": ev.title,
                                          "join_at": ev.start_dt.isoformat(), "project_id": ev.project_id},
                            calendar_event_id=ev.id)
                n += 1
            except Exception:  # noqa: BLE001
                hecho["errores"] += 1
                logger.warning("reuniones: bot de calendario para %s", ev.id, exc_info=True)
    return n


def retencion(db: Session, org: str) -> dict:
    from app.db.bloqueo_legal import _bloqueo_de, bloqueos_activos
    from app.models.ai_chat import AIMeeting
    from app.models.reuniones import AIMeetingAudio
    from app.services.reuniones import almacen
    from app.services.reuniones.eventos import evento
    ahora = _ahora()
    bloqueos = bloqueos_activos(db, org)
    retenidas: set = set()

    def _bloqueada(reunion) -> bool:
        if reunion.id in retenidas:
            return True
        if _bloqueo_de("meetings", reunion, bloqueos) is not None:
            retenidas.add(reunion.id)
            return True
        return False

    audio = 0
    for trozo in db.query(AIMeetingAudio).filter(AIMeetingAudio.organization_id == org,
                                                 AIMeetingAudio.expires_at < ahora).all():
        if _bloqueada(trozo.meeting):
            continue
        almacen.borrar(trozo.storage_key)
        db.delete(trozo)
        audio += 1

    transcripciones = 0
    for m in db.query(AIMeeting).filter(AIMeeting.organization_id == org, AIMeeting.transcript_expires_at < ahora,
                                        AIMeeting.transcript_purged_at.is_(None)).all():
        if _bloqueada(m):
            continue
        for coleccion in (m.segmentos, m.traducciones):
            for fila in list(coleccion):
                coleccion.remove(fila)
        m.transcript = None
        m.transcript_purged_at = ahora
        evento(db, m, "transcript_purged", None)
        transcripciones += 1

    informe = {"audio_chunks": audio, "transcripts": transcripciones, "held": len(retenidas)}
    if audio or transcripciones:
        from app.services.audit import audit_log
        entrada = audit_log(db, None, "RETENTION_PURGE", "ai_meeting", None, "meeting retention",
                            metadata={"organization_id": org, **informe})
        if getattr(entrada, "organization_id", None) is None:
            entrada.organization_id = org
    db.flush()
    return informe
