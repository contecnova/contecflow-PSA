"""Listas, «pendientes para mí» y métricas del flujo de demanda (operador).

Las métricas de tiempo descuentan las pausas por información pendiente
(`paused_seconds`): «Pendiente de información» no cuenta en el flujo.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.services.demanda import definicion as D
from app.services.demanda.acceso import Actor
from app.services.demanda.motor import (ABIERTOS, acciones_posibles, ahora, estado_del_plazo, estados_de_la_ronda,
                                        flujo_de, horas_efectivas)
from app.services.demanda.serializacion import resumen


def pendiente_para(db: Session, req, actor: Actor) -> bool:
    if req.status not in ("in_progress", "on_hold"):
        return False
    f = D.fase(flujo_de(req), req.current_phase_key)
    if not f:
        return False
    estados = estados_de_la_ronda(db, req)
    return any(acciones_posibles(db, req, actor, f, p, estados) for p in D.pasos(f))


def listar(db: Session, actor: Actor, org_id: Optional[str], *, estado: Optional[str] = None,
           fase: Optional[str] = None, tipo: Optional[str] = None, para_mi: bool = False, q: Optional[str] = None,
           idioma: str = "es", limite: int = 500) -> list[dict]:
    from app.models.demanda import DemandRequest
    consulta = db.query(DemandRequest).filter(DemandRequest.organization_id == org_id)
    if estado == "open":
        consulta = consulta.filter(DemandRequest.status.in_(ABIERTOS))
    elif estado:
        consulta = consulta.filter(DemandRequest.status == estado)
    if fase:
        consulta = consulta.filter(DemandRequest.current_phase_key == fase)
    if tipo:
        consulta = consulta.filter(DemandRequest.type_key == tipo)
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.filter(DemandRequest.title.ilike(patron) | DemandRequest.code.ilike(patron))
    if para_mi:
        consulta = consulta.filter(DemandRequest.status.in_(("in_progress", "on_hold")))
    filas = consulta.order_by(DemandRequest.created_at.desc()).limit(limite).all()
    if para_mi:
        filas = [r for r in filas if pendiente_para(db, r, actor)]
    cache: dict = {}
    return [resumen(db, r, idioma, cache) for r in filas]


def listar_del_solicitante(db: Session, actor: Actor, idioma: str = "es") -> list[dict]:
    from app.models.demanda import DemandRequest
    consulta = db.query(DemandRequest)
    if actor.kind == "client":
        consulta = consulta.filter(DemandRequest.client_user_id == actor.id)
    else:
        consulta = consulta.filter(DemandRequest.requester_user_id == actor.id)
    cache: dict = {}
    return [resumen(db, r, idioma, cache) for r in consulta.order_by(DemandRequest.created_at.desc()).limit(500)]


def metricas(db: Session, actor: Actor, org_id: Optional[str], idioma: str = "es") -> dict:
    from app.models.demanda import DemandRequest, DemandTransition
    filas = db.query(DemandRequest).filter(DemandRequest.organization_id == org_id).all()
    abiertos = [r for r in filas if r.status in ABIERTOS]
    por_estado: dict = {}
    for r in filas:
        por_estado[r.status] = por_estado.get(r.status, 0) + 1
    por_fase: dict = {}
    for r in abiertos:
        nombre = D.nombre((D.fase(flujo_de(r), r.current_phase_key) or {}).get("name"), idioma) or r.current_phase_key
        por_fase[nombre] = por_fase.get(nombre, 0) + 1
    desde = ahora() - timedelta(days=90)
    cerrados = [r for r in filas if r.closed_at and r.submitted_at and r.closed_at.replace(tzinfo=None)
                >= desde.replace(tzinfo=None)]
    bypass = db.query(DemandTransition).filter(DemandTransition.organization_id == org_id,
                                               DemandTransition.is_bypass.is_(True),
                                               DemandTransition.created_at >= desde).count()
    return {"total": len(filas), "open": len(abiertos),
            "pending_info": sum(1 for r in filas if r.status == "pending_info"),
            "stalled": sum(1 for r in abiertos if estado_del_plazo(r) == "breached"),
            "at_risk": sum(1 for r in abiertos if estado_del_plazo(r) == "warning"),
            "bypass": bypass,
            "avg_effective_hours": round(sum(horas_efectivas(r) for r in cerrados) / len(cerrados), 1)
            if cerrados else None,
            "pending_for_me": sum(1 for r in abiertos if pendiente_para(db, r, actor)),
            "by_status": [{"key": k, "count": v} for k, v in sorted(por_estado.items())],
            "by_phase": [{"name": k, "count": v} for k, v in sorted(por_fase.items(), key=lambda x: -x[1])]}
