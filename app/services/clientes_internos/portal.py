"""Portal interno (docs/CLIENTES_INTERNOS.md §5): lo de MIS unidades internas.

Mismo login (SSO) que el resto de la aplicación; capacidad `interno.portal`.
Cada función recibe el id de la unidad y comprueba que quien llama es de ella
(`unidades.exigir_papel`): sin pertenencia, 403 `interno_sin_acceso`. Costes,
presupuesto y cargos solo para `responsable`, `finanzas` y dirección. Firmar
hitos, solo el responsable; firmar UAT, responsable o usuario clave.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.codigos_de_error import error
from app.models.service_desk._enums import ESTADOS_DE_TICKET_CERRADOS
from app.services.audit import audit_log
from app.services.clientes_internos import costes as C
from app.services.clientes_internos import gobierno as G
from app.services.clientes_internos import unidades as U

ACTIVOS = ("planning", "active", "on_hold", "paused")


def _v(x):
    return getattr(x, "value", x)


def _iso(x):
    return x.isoformat() if x else None


def yo(db: Session, usuario) -> dict:
    filas = U.unidades_de(db, usuario)
    return {
        "enabled": bool(filas), "is_direction": U.es_direccion(db, usuario),
        "units": [{"id": u.id, "name": u.name, "internal_type": u.internal_type, "role": p,
                   "can_see_costs": p in U.VEN_COSTES, "can_sign": p in U.FIRMAN,
                   "can_sign_uat": p in U.FIRMAN_UAT} for u, p in filas],
    }


def _hitos_pendientes(db: Session, proyectos: list) -> list:
    from app.models.financial import ProjectMilestone
    ids = [p.id for p in proyectos]
    if not ids:
        return []
    return db.query(ProjectMilestone).filter(ProjectMilestone.project_id.in_(ids), ProjectMilestone.is_active.is_(True),
                                             ProjectMilestone.billing_status == "pending_approval") \
        .order_by(ProjectMilestone.due_date).all()


def _uats(db: Session, proyectos: list) -> list:
    from app.models.client_portal import UATSession
    ids = [p.id for p in proyectos]
    if not ids:
        return []
    return db.query(UATSession).filter(UATSession.project_id.in_(ids)).order_by(UATSession.deadline).all()


def resumen(db: Session, usuario, cid: str) -> dict:
    from app.models.service_desk.tickets import Ticket
    unidad, p = U.exigir_papel(db, usuario, cid)
    proyectos = C.proyectos_de(db, unidad)
    presupuesto = None
    if p in U.VEN_COSTES:
        from app.services.clientes_internos.presupuesto import estado
        presupuesto = estado(db, unidad)
    owner = unidad.business_owner
    sla = G.sla(db, unidad)
    return {
        "unit": {"id": unidad.id, "name": unidad.name, "internal_type": unidad.internal_type,
                 "finance_mode": unidad.finance_mode, "business_owner_name": owner.full_name if owner else None},
        "role": p,
        "projects_active": sum(1 for x in proyectos if _v(x.status) in ACTIVOS),
        "milestones_pending": len(_hitos_pendientes(db, proyectos)),
        "uat_pending": sum(1 for s in _uats(db, proyectos) if not (s.client_signed_at or s.internal_signed_by)),
        "tickets_open": db.query(Ticket).filter(Ticket.client_id == unidad.id,
                                                Ticket.status.notin_(ESTADOS_DE_TICKET_CERRADOS)).count(),
        "sla": {"pct": sla["pct"], "tone": sla["tone"], "total": sla["total"]},
        "satisfaction": G.satisfaccion(db, unidad),
        "budget": presupuesto,
        "warnings": U.avisos(db, unidad, presupuesto) if p in ("responsable", "direccion") else [],
    }


def proyectos(db: Session, usuario, cid: str) -> list[dict]:
    from app.models.financial import ProjectMilestone
    unidad, _ = U.exigir_papel(db, usuario, cid)
    salida = []
    for p in sorted(C.proyectos_de(db, unidad), key=lambda x: (x.name or "").lower()):
        hitos = db.query(ProjectMilestone).filter(ProjectMilestone.project_id == p.id,
                                                  ProjectMilestone.is_active.is_(True)).all()
        hechos = sum(1 for h in hitos if h.is_completed or h.billing_status in ("approved", "invoiced"))
        salida.append({"id": p.id, "code": p.code, "name": p.name, "status": _v(p.status),
                       "progress": round(100 * hechos / len(hitos)) if hitos else None,
                       "start_date": str(p.start_date) if p.start_date else None,
                       "end_date": str(p.end_date_planned) if p.end_date_planned else None,
                       "milestones_pending": sum(1 for h in hitos if h.billing_status == "pending_approval")})
    return salida


def hitos(db: Session, usuario, cid: str) -> list[dict]:
    unidad, p = U.exigir_papel(db, usuario, cid)
    proyectos_ = {x.id: x for x in C.proyectos_de(db, unidad)}
    return [{"id": h.id, "project_id": h.project_id, "project_name": proyectos_[h.project_id].name, "name": h.name,
             "due_date": str(h.due_date) if h.due_date else None, "billing_status": h.billing_status,
             "approval_requested_at": _iso(h.approval_requested_at),
             "can_sign": p in U.FIRMAN and h.approval_requested_by != usuario.id}
            for h in _hitos_pendientes(db, list(proyectos_.values()))]


def _proyecto_de_la_unidad(db: Session, usuario, project_id: str, papeles: tuple):
    from app.models.project import Project
    proyecto = db.get(Project, project_id)
    if proyecto is None or not proyecto.client_id:
        raise error(403, "interno_sin_acceso")
    return U.exigir_papel(db, usuario, proyecto.client_id, papeles)


def firmar_hito(db: Session, usuario, mid: str, aprobado: bool, nota: Optional[str]) -> dict:
    from app.models.financial import ProjectMilestone
    from app.services.milestone_service import decide_milestone_approval
    h = db.query(ProjectMilestone).filter(ProjectMilestone.id == mid, ProjectMilestone.is_active.is_(True)).first()
    if h is None:
        raise error(404, "no_encontrado", detail="Hito no encontrado", que="hito")
    unidad, _ = _proyecto_de_la_unidad(db, usuario, h.project_id, U.FIRMAN)
    if h.billing_status != "pending_approval":
        raise error(409, "interno_hito_no_pendiente")
    if h.approval_requested_by == usuario.id:
        raise error(403, "interno_sod_hito")
    decide_milestone_approval(h.id, aprobado, nota, usuario, db)
    audit_log(db, usuario, "APPROVE" if aprobado else "REJECT", "project_milestone", h.id, h.name,
              metadata={"channel": "internal_portal", "client_id": unidad.id, "note": nota})
    db.commit()
    return {"id": h.id, "billing_status": h.billing_status}


def uat(db: Session, usuario, cid: str) -> list[dict]:
    unidad, p = U.exigir_papel(db, usuario, cid)
    proyectos_ = {x.id: x for x in C.proyectos_de(db, unidad)}
    salida = []
    for s in _uats(db, list(proyectos_.values())):
        firmada = bool(s.client_signed_at or s.internal_signed_by)
        salida.append({"id": s.id, "code": s.code, "project_id": s.project_id,
                       "project_name": proyectos_[s.project_id].name, "title": s.title, "status": _v(s.status),
                       "deadline": str(s.deadline) if s.deadline else None, "test_environment": s.test_environment,
                       "signed": firmada, "can_sign": p in U.FIRMAN_UAT and not firmada})
    return salida


def firmar_uat(db: Session, usuario, sid: str, resultado: str, notas: Optional[str]) -> dict:
    from app.models.client_portal import UATSession, UATStatus
    s = db.get(UATSession, sid)
    if s is None:
        raise error(404, "no_encontrado", detail="UAT no encontrada", que="uat")
    unidad, _ = _proyecto_de_la_unidad(db, usuario, s.project_id, U.FIRMAN_UAT)
    if resultado not in ("passed", "failed", "conditional"):
        raise error(422, "interno_resultado_no_valido", valor=resultado)
    if s.client_signed_at or s.internal_signed_by:
        raise error(409, "interno_uat_ya_firmada")
    ahora = datetime.now(timezone.utc)
    s.client_result = UATStatus(resultado)
    s.status = UATStatus(resultado)
    s.client_notes = (notas or "").strip() or None
    s.internal_signed_by = usuario.id
    s.client_signed_at = ahora
    s.completed_at = ahora
    audit_log(db, usuario, "APPROVE" if resultado != "failed" else "REJECT", "uat_session", s.id, s.title,
              metadata={"channel": "internal_portal", "client_id": unidad.id, "result": resultado})
    db.commit()
    return {"id": s.id, "status": resultado, "signed": True}


def tickets(db: Session, usuario, cid: str) -> list[dict]:
    from app.models.service_desk.tickets import Ticket
    unidad, _ = U.exigir_papel(db, usuario, cid)
    filas = db.query(Ticket).filter(Ticket.client_id == unidad.id).order_by(Ticket.created_at.desc()).limit(200).all()
    return [{"id": t.id, "number": t.number, "title": t.title, "status": _v(t.status), "priority": _v(t.priority),
             "created_at": _iso(t.created_at), "resolved_at": _iso(t.resolved_at),
             "sla_resolution_breached": bool(t.sla_resolution_breached)} for t in filas]


def sla(db: Session, usuario, cid: str, desde: Optional[date] = None, hasta: Optional[date] = None) -> dict:
    unidad, _ = U.exigir_papel(db, usuario, cid)
    return G.sla(db, unidad, desde, hasta)


def coste(db: Session, usuario, cid: str, year: Optional[int] = None) -> dict:
    from app.services.clientes_internos.presupuesto import estado
    unidad, _ = U.exigir_papel(db, usuario, cid, U.VEN_COSTES)
    hoy = timeutil.today()
    year = year or hoy.year
    hasta = min(date(year, 12, 31), hoy)
    d = C.coste(db, unidad, date(year, 1, 1), hasta)
    d["year"] = year
    d["budget"] = estado(db, unidad, year, hasta=hasta, consumido=d["total"])
    return d


def cargos(db: Session, usuario, cid: str) -> list[dict]:
    from app.services.clientes_internos.cargos import listar
    unidad, _ = U.exigir_papel(db, usuario, cid, U.VEN_COSTES)
    return listar(db, usuario, client_id=unidad.id, solo_emitidos=True)


def peticiones(db: Session, usuario, cid: str) -> dict:
    from app.services.clientes_internos import peticiones as P
    unidad, _ = U.exigir_papel(db, usuario, cid)
    return P.listar(db, usuario, unidad)


def pedir(db: Session, usuario, cid: str, datos: dict) -> dict:
    from app.services.clientes_internos import peticiones as P
    unidad, _ = U.exigir_papel(db, usuario, cid)
    return P.pedir(db, usuario, unidad, datos)


def valorar(db: Session, usuario, cid: str, datos: dict) -> dict:
    unidad, p = U.exigir_papel(db, usuario, cid)
    if p == "direccion":
        raise error(403, "interno_sin_acceso")
    return G.valorar(db, usuario, unidad, datos.get("score"), datos.get("comment"), datos.get("survey_type") or "nps")


def adopcion(db: Session, usuario, cid: str) -> list[dict]:
    unidad, _ = U.exigir_papel(db, usuario, cid)
    return G.adopcion(db, unidad)


def beneficios(db: Session, usuario, cid: str) -> list[dict]:
    unidad, _ = U.exigir_papel(db, usuario, cid)
    return G.beneficios(db, [p.id for p in C.proyectos_de(db, unidad)])
