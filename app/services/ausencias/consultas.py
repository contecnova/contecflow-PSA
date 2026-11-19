"""Lecturas para la pantalla: quién ve una ausencia, su detalle y la bandeja de quien aprueba."""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.ausencias import EventoDeAusencia
from app.models.resources import Absence, AbsenceStatus
from app.services.ausencias import cupos, documentos
from app.core.codigos_de_error import error


def _rol(u) -> str:
    return str(getattr(getattr(u, "role", None), "value", getattr(u, "role", None)) or "")


def visible(db: Session, usuario, absence_id: str) -> Absence:
    """La ausencia si la puede ver: la persona, su sustituto, sus responsables,
    quien la aprueba, RRHH, administración y los jefes de equipo / PM (como el
    calendario de equipo). Si no, 404 (no se filtra que existe)."""
    a = db.query(Absence).filter(Absence.id == absence_id).first()
    if a is None:
        raise error(404, "no_encontrado", detail="Ausencia no encontrada", que="ausencia")
    if (a.user_id == usuario.id or a.substitute_id == usuario.id or usuario.is_superadmin
            or _rol(usuario) in ("admin", "hr", "pm", "team_lead")
            or documentos._es_responsable(db, usuario, a) or documentos._es_aprobador(db, usuario, a)):
        return a
    raise error(404, "no_encontrado", detail="Ausencia no encontrada", que="ausencia")


def _nombres(db: Session, ids) -> dict:
    from app.models.user import User
    ids = {i for i in ids if i}
    return dict(db.query(User.id, User.full_name).filter(User.id.in_(ids)).all()) if ids else {}


def _aprobacion(db: Session, a: Absence) -> Optional[dict]:
    from app.models.billing_reports import ApprovalRequest
    from app.services.approval_engine import pasos as _pasos
    req = db.query(ApprovalRequest).filter(ApprovalRequest.entity_type == "leave", ApprovalRequest.entity_id == a.id) \
        .order_by(ApprovalRequest.created_at.desc()).first()
    if req is None:
        return None
    pasos = _pasos.pasos_de(db, req)
    nombres = _nombres(db, [d.approver_id for d in req.decisions or []])
    return {"id": req.id, "estado": req.status, "paso_actual": req.current_step,
            "pasos": [{"orden": s.step_order, "nombre": s.name, "tipo": getattr(s, "kind", None) or "approve",
                       "aprobador": s.approver_type, "rol": s.approver_role} for s in pasos],
            "decisiones": [{"orden": d.step_order, "decision": d.decision, "nota": d.note,
                            "quien": nombres.get(d.approver_id),
                            "cuando": d.decided_at.isoformat() if getattr(d, "decided_at", None) else None}
                           for d in sorted(req.decisions or [], key=lambda d: (d.step_order, str(d.id)))]}


def _explicacion(db: Session, usuario, a: Absence) -> Optional[dict]:
    from app.services.politicas import servicio
    try:
        e = servicio.explicaciones(db, usuario, "ausencias", a.id)
    except ErrorDeDominio:
        return None
    ultima = (e.get("evaluaciones") or [None])[0]
    return ultima


def detalle(db: Session, usuario, a: Absence) -> dict:
    from app.services.absence_service import serialize_absence
    eventos = db.query(EventoDeAusencia).filter(EventoDeAusencia.absence_id == a.id) \
        .order_by(EventoDeAusencia.created_at, EventoDeAusencia.id).all()
    nombres = _nombres(db, [e.actor_id for e in eventos])
    privado = serialize_absence(a, usuario, db)["private"]
    return {
        "ausencia": serialize_absence(a, usuario, db),
        "linea_de_tiempo": [{"tipo": e.tipo, "quien": nombres.get(e.actor_id),
                             "cuando": e.created_at.isoformat() if e.created_at else None,
                             "datos": {} if privado else json.loads(e.datos or "{}")} for e in eventos],
        **documentos.listar(db, usuario, a),
        "plazas": cupos.reservas_de(db, a.id),
        "posicion_en_espera": cupos.posicion(db, a.id) if a.status == AbsenceStatus.waitlisted else None,
        "aprobacion": _aprobacion(db, a),
        "explicacion": _explicacion(db, usuario, a),
        "puede_gestionar": _puede_gestionar(db, usuario, a),
    }


def _puede_gestionar(db: Session, usuario, a: Absence) -> bool:
    try:
        documentos.exigir_gestion(db, usuario, a)
        return True
    except ErrorDeDominio:
        return False


def bandeja(db: Session, usuario) -> list[dict]:
    """Lo que este usuario tiene que decidir: las solicitudes `leave` en las que
    le toca el paso actual (motor de aprobaciones) y, sin flujo, las pendientes
    de quien depende de él. Con la explicación de las políticas y el impacto en
    la cobertura de los turnos afectados."""
    from app.services.absence_service import serialize_absence
    from app.services.approval_engine._base import responsable_de_nivel
    from app.services.approval_engine import fuentes
    from app.services.approval_engine.requests import get_pending_for_user
    from app.services.ausencias import reglas, turnos
    salida, vistas = [], set()
    for req, paso in get_pending_for_user(db, usuario):
        if req.entity_type != "leave":
            continue
        a = db.query(Absence).filter(Absence.id == req.entity_id).first()
        if a is None or a.user_id == usuario.id:
            continue
        vistas.add(a.id)
        salida.append({"solicitud_id": req.id, "paso": paso.name, "a": a})
    if _rol(usuario) in ("admin", "hr", "pm", "team_lead") or usuario.is_superadmin:
        for a in db.query(Absence).filter(Absence.status == AbsenceStatus.pending, Absence.is_active.is_(True)).all():
            if a.id in vistas or a.user_id == usuario.id or fuentes.estado(db, "leave", a.id) is not None:
                continue
            if _rol(usuario) not in ("admin", "hr") and responsable_de_nivel(db, a.user_id, 1) != usuario.id:
                continue
            salida.append({"solicitud_id": None, "paso": None, "a": a})
    filas = []
    for x in salida:
        a = x["a"]
        ctx = reglas.contexto(db, a)
        con_turno = [d for d in ctx["_ausencia"]["dias"] if d.get("turno")]
        impacto = []
        if con_turno:
            d0, d1 = min(d["fecha"] for d in con_turno), max(d["fecha"] for d in con_turno)
            if (d1 - d0).days < turnos.MAX_DIAS_DE_CUADRANTE:
                mios = {(d["fecha"].isoformat(), d["turno"]) for d in con_turno}
                c = turnos.cobertura(db, d0, d1, simular={"user_id": a.user_id, "dias": con_turno})
                impacto = [y for y in c["celdas"] if (y["fecha"], y["turno_id"]) in mios]
        filas.append({"solicitud_id": x["solicitud_id"], "paso": x["paso"], "sin_flujo": x["solicitud_id"] is None,
                      "ausencia": serialize_absence(a, usuario, db), "explicacion": _explicacion(db, usuario, a),
                      "impacto": impacto, "companeros_ausentes": ctx["companeros_ausentes"],
                      "cobertura_restante": ctx["cobertura_restante"], "saldo_restante": ctx["saldo_restante"],
                      "plazas": cupos.reservas_de(db, a.id)})
    return sorted(filas, key=lambda f: f["ausencia"]["start_date"])
