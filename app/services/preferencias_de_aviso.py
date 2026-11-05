"""Qué avisos quiere cada usuario y por qué canal (revisión 2026-11).

Por cada tipo de aviso (`NotificationType`), «app» y «correo». Por defecto, todo
activado. Se guarda en `user_preferences.extra["notifications"]`.

El filtro de la aplicación está en UN sitio: un escuchador `before_flush` que
descarta los avisos nuevos que el usuario no quiere. Así vale para todas las
vías que crean avisos (hoy ocho), también las futuras. El correo se filtra
donde el aviso lo manda (`quiere(..., "email")`).
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.enterprise import Notification, NotificationType
from app.models.user import UserPreference

CANALES = ("app", "email")
# Tipos que tambien se mandan por correo (el resto solo existe en la aplicacion).
CON_CORREO = {"approval_requested"}


def _de(db: Session, user_id: str) -> dict:
    cache = db.info.setdefault("_preferencias_de_aviso", {})
    if user_id not in cache:
        fila = db.query(UserPreference.extra).filter(UserPreference.user_id == user_id).first()
        try:
            extra = json.loads(fila[0]) if fila and fila[0] else {}
        except ValueError:
            extra = {}
        cache[user_id] = extra.get("notifications") or {}
    return cache[user_id]


def quiere(db: Session, user_id: str, tipo, canal: str) -> bool:
    tipo = getattr(tipo, "value", tipo) or "system"
    return bool((_de(db, user_id).get(tipo) or {}).get(canal, True))


def _extra(db: Session, user_id: str) -> dict:
    fila = db.query(UserPreference.extra).filter(UserPreference.user_id == user_id).first()
    try:
        return json.loads(fila[0]) if fila and fila[0] else {}
    except ValueError:
        return {}


def leer(db: Session, user_id: str) -> dict:
    prefs = _de(db, user_id)
    return {"types": [{"type": t.value, "channels": ["app", "email"] if t.value in CON_CORREO else ["app"]}
                      for t in NotificationType],
            "preferences": {t.value: {c: (prefs.get(t.value) or {}).get(c, True) for c in CANALES}
                            for t in NotificationType},
            # Resumen diario por correo de lo no leído (revisión 2026-11). Por defecto, no.
            "digest": bool(_extra(db, user_id).get("notifications_digest", False))}


def guardar(db: Session, user_id: str, preferencias: dict, digest: Optional[bool] = None) -> dict:
    validos = {t.value for t in NotificationType}
    limpias = {t: {c: bool(v.get(c, True)) for c in CANALES}
               for t, v in (preferencias or {}).items() if t in validos and isinstance(v, dict)}
    fila = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if fila is None:
        fila = UserPreference(user_id=user_id)
        db.add(fila)
    try:
        extra = json.loads(fila.extra) if fila.extra else {}
    except ValueError:
        extra = {}
    extra["notifications"] = limpias
    if digest is not None:
        extra["notifications_digest"] = bool(digest)
    fila.extra = json.dumps(extra)
    db.commit()
    db.info.pop("_preferencias_de_aviso", None)
    return leer(db, user_id)


@event.listens_for(Session, "before_flush")
def _descartar_avisos_no_deseados(session, flush_context, instances) -> None:
    for obj in list(session.new):
        if isinstance(obj, Notification) and obj.user_id and not quiere(session, obj.user_id, obj.type, "app"):
            session.expunge(obj)
