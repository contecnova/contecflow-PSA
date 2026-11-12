"""Calendario de cambios: ventanas de congelacion, choques y versiones.

Antes no habia ni calendario ni comprobacion alguna: dos cambios sobre el
mismo servidor a la misma hora, o uno en plena congelacion de fin de año, se
programaban sin aviso. Ahora:

- **congelacion**: un cambio no se programa dentro de una ventana activa,
  salvo que sea de emergencia;
- **choque**: dos cambios aprobados o en marcha que se solapan en el tiempo y
  comparten algun elemento de configuracion (`affected_cis`). Se avisa, no se
  bloquea: a veces es a proposito, y lo decide quien programa;
- **versiones**: agrupan cambios que salen juntos y se ven en el calendario.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.service_desk import ChangeBlackout, ITSMChangeRequest, Release
from app.services.sla_service import aware
from app.core.errores import ErrorDeDominio

#: Estados en los que un cambio ocupa su hueco en el calendario.
OCUPAN = ("approved", "scheduled", "in_progress")


def _cis(change: ITSMChangeRequest) -> set:
    try:
        valor = json.loads(change.affected_cis or "[]")
    except (ValueError, TypeError):
        return set()
    return {str(v) for v in valor} if isinstance(valor, list) else set()


def _v(x):
    return getattr(x, "value", x)


def congelaciones_que_pisa(db: Session, inicio: datetime, fin: datetime) -> list[ChangeBlackout]:
    return db.query(ChangeBlackout).filter(
        ChangeBlackout.is_active == True,  # noqa: E712
        ChangeBlackout.start_at < fin, ChangeBlackout.end_at > inicio,
    ).all()


def choques(db: Session, change: ITSMChangeRequest) -> list[dict]:
    """Otros cambios ocupando el mismo hueco sobre algun CI comun."""
    if not (change.planned_start and change.planned_end):
        return []
    mios = _cis(change)
    if not mios:
        return []
    otros = db.query(ITSMChangeRequest).filter(
        ITSMChangeRequest.id != change.id,
        ITSMChangeRequest.status.in_(OCUPAN),
        ITSMChangeRequest.planned_start < change.planned_end,
        ITSMChangeRequest.planned_end > change.planned_start,
    ).all()
    salida = []
    for o in otros:
        comunes = mios & _cis(o)
        if comunes:
            salida.append({"change_id": o.id, "number": o.number, "title": o.title,
                           "planned_start": aware(o.planned_start).isoformat(),
                           "planned_end": aware(o.planned_end).isoformat(), "cis": sorted(comunes)})
    return salida


def exigir_ventana_libre(db: Session, change: ITSMChangeRequest) -> None:
    """Para programar: fechas validas y fuera de congelacion (salvo emergencia)."""
    if not (change.planned_start and change.planned_end):
        raise ErrorDeDominio(422, "Para programar un cambio hacen falta inicio y fin planificados")
    inicio, fin = aware(change.planned_start), aware(change.planned_end)
    if fin <= inicio:
        raise ErrorDeDominio(422, "El fin planificado tiene que ser posterior al inicio")
    if _v(change.change_type) == "emergency":
        return
    pisadas = congelaciones_que_pisa(db, inicio, fin)
    if pisadas:
        raise ErrorDeDominio(409, "El cambio cae en una ventana de congelación: "
                                 + ", ".join(b.name for b in pisadas))


def calendario(db: Session, desde: datetime, hasta: datetime) -> dict:
    """Cambios, versiones y congelaciones del periodo, con los choques marcados."""
    cambios = db.query(ITSMChangeRequest).filter(
        ITSMChangeRequest.planned_start.isnot(None),
        ITSMChangeRequest.planned_start < hasta,
        or_(ITSMChangeRequest.planned_end.is_(None), ITSMChangeRequest.planned_end > desde),
    ).order_by(ITSMChangeRequest.planned_start).all()
    congelaciones = db.query(ChangeBlackout).filter(
        ChangeBlackout.is_active == True,  # noqa: E712
        ChangeBlackout.start_at < hasta, ChangeBlackout.end_at > desde,
    ).order_by(ChangeBlackout.start_at).all()
    versiones = db.query(Release).filter(
        Release.is_active == True,  # noqa: E712
        Release.planned_date.isnot(None),
        and_(Release.planned_date >= desde, Release.planned_date < hasta),
    ).order_by(Release.planned_date).all()
    return {
        "changes": [{
            "id": c.id, "number": c.number, "title": c.title, "status": _v(c.status),
            "change_type": _v(c.change_type), "risk": _v(c.risk),
            "planned_start": aware(c.planned_start).isoformat(),
            "planned_end": aware(c.planned_end).isoformat() if c.planned_end else None,
            "release_id": c.release_id,
            "conflicts": choques(db, c) if _v(c.status) in OCUPAN else [],
            "in_blackout": bool(c.planned_end and _v(c.change_type) != "emergency" and congelaciones_que_pisa(
                db, aware(c.planned_start), aware(c.planned_end))),
        } for c in cambios],
        "blackouts": [serializar_congelacion(b) for b in congelaciones],
        "releases": [serializar_version(r) for r in versiones],
    }


# ── Congelaciones ────────────────────────────────────────────────────────────

def serializar_congelacion(b: ChangeBlackout) -> dict:
    return {"id": b.id, "name": b.name, "reason": b.reason,
            "start_at": aware(b.start_at).isoformat(), "end_at": aware(b.end_at).isoformat()}


def listar_congelaciones(db: Session) -> list[dict]:
    filas = db.query(ChangeBlackout).filter(ChangeBlackout.is_active == True).order_by(  # noqa: E712
        ChangeBlackout.start_at.desc()).all()
    return [serializar_congelacion(b) for b in filas]


def guardar_congelacion(db: Session, datos: dict, blackout_id: Optional[str] = None) -> ChangeBlackout:
    inicio, fin = aware(datos["start_at"]), aware(datos["end_at"])
    if fin <= inicio:
        raise ErrorDeDominio(422, "La congelación tiene que acabar después de empezar")
    b = db.get(ChangeBlackout, blackout_id) if blackout_id else ChangeBlackout()
    if b is None or (blackout_id and not b.is_active):
        raise ErrorDeDominio(404, "Congelación no encontrada")
    b.name, b.reason, b.start_at, b.end_at = datos["name"], datos.get("reason"), inicio, fin
    db.add(b)
    return b


def borrar_congelacion(db: Session, blackout_id: str) -> None:
    b = db.get(ChangeBlackout, blackout_id)
    if b is None or not b.is_active:
        raise ErrorDeDominio(404, "Congelación no encontrada")
    b.is_active = False


# ── Versiones ────────────────────────────────────────────────────────────────

ESTADOS_DE_VERSION = ("planned", "in_progress", "released", "cancelled")


def serializar_version(r: Release, db: Optional[Session] = None) -> dict:
    datos = {"id": r.id, "name": r.name, "version": r.version, "status": r.status, "notes": r.notes,
             "planned_date": aware(r.planned_date).isoformat() if r.planned_date else None,
             "released_at": aware(r.released_at).isoformat() if r.released_at else None,
             "owner_id": r.owner_id, "owner_name": r.owner.full_name if r.owner else None}
    if db is not None:
        datos["changes"] = [{"id": c.id, "number": c.number, "title": c.title, "status": _v(c.status)}
                            for c in db.query(ITSMChangeRequest).filter(ITSMChangeRequest.release_id == r.id).all()]
    return datos


def listar_versiones(db: Session) -> list[dict]:
    filas = db.query(Release).filter(Release.is_active == True).order_by(Release.planned_date.desc()).all()  # noqa: E712
    return [serializar_version(r, db) for r in filas]


def guardar_version(db: Session, datos: dict, release_id: Optional[str] = None) -> Release:
    r = db.get(Release, release_id) if release_id else Release()
    if r is None or (release_id and not r.is_active):
        raise ErrorDeDominio(404, "Versión no encontrada")
    estado = datos.get("status") or r.status or "planned"
    if estado not in ESTADOS_DE_VERSION:
        raise ErrorDeDominio(422, f"Estado de versión inválido: {estado}")
    if estado == "released":
        pendientes = [c.number for c in db.query(ITSMChangeRequest).filter(
            ITSMChangeRequest.release_id == r.id,
            ITSMChangeRequest.status.notin_(["implemented", "post_review", "closed_success", "closed_failed",
                                              "cancelled"]),
        ).all()] if r.id else []
        if pendientes:
            raise ErrorDeDominio(409, "Faltan cambios por implementar: " + ", ".join(pendientes))
        r.released_at = r.released_at or datetime.now(timezone.utc)
    r.name = datos.get("name") or r.name
    r.version, r.notes, r.owner_id = datos.get("version"), datos.get("notes"), datos.get("owner_id")
    r.planned_date = aware(datos["planned_date"]) if datos.get("planned_date") else None
    r.status = estado
    if not r.name:
        raise ErrorDeDominio(422, "La versión necesita nombre")
    db.add(r)
    return r


def borrar_version(db: Session, release_id: str) -> None:
    r = db.get(Release, release_id)
    if r is None or not r.is_active:
        raise ErrorDeDominio(404, "Versión no encontrada")
    r.is_active = False
    db.query(ITSMChangeRequest).filter(ITSMChangeRequest.release_id == release_id).update(
        {"release_id": None}, synchronize_session=False)
