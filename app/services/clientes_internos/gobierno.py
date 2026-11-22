"""Gobierno de las unidades internas (docs/CLIENTES_INTERNOS.md §6).

SLA/OLA por unidad, satisfacción (NPS/CSAT), plan de adopción y formación,
caso de negocio y beneficios por proyecto. Todo cambio deja `audit_log`.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil, umbrales
from app.core.codigos_de_error import error
from app.models.clientes_internos import (ESTADOS_ADOPCION, TIPOS_ADOPCION, TIPOS_BENEFICIO, InternalAdoptionItem,
                                          ProjectBenefit)
from app.services.audit import audit_log


def _v(x):
    return getattr(x, "value", x)


def _periodo(desde: Optional[date], hasta: Optional[date]) -> tuple[date, date]:
    hasta = hasta or timeutil.today()
    return desde or (hasta - timedelta(days=89)), hasta


# ── SLA / OLA ────────────────────────────────────────────────────────────────

def sla(db: Session, unidad, desde: Optional[date] = None, hasta: Optional[date] = None) -> dict:
    """Tickets de la unidad creados en el periodo: resueltos, en plazo de resolución y OLA incumplidos."""
    from app.models.service_desk.tickets import Ticket
    desde, hasta = _periodo(desde, hasta)
    ini = datetime.combine(desde, time.min, tzinfo=timezone.utc)
    fin = datetime.combine(hasta, time.max, tzinfo=timezone.utc)
    tickets = db.query(Ticket).filter(Ticket.client_id == unidad.id, Ticket.created_at >= ini,
                                      Ticket.created_at <= fin).all()
    resueltos = [t for t in tickets if t.resolved_at is not None]
    en_plazo = [t for t in resueltos if not t.sla_resolution_breached]
    por_prioridad: dict = {}
    for t in resueltos:
        p = por_prioridad.setdefault(_v(t.priority), [0, 0])
        p[0] += 1
        p[1] += 0 if t.sla_resolution_breached else 1
    pct = round(100 * len(en_plazo) / len(resueltos), 1) if resueltos else None
    return {"from": str(desde), "to": str(hasta), "total": len(tickets), "resolved": len(resueltos),
            "on_time": len(en_plazo), "pct": pct,
            "tone": umbrales.tono_de("sla", pct, db, unidad.organization_id) if pct is not None else None,
            "ola_breached": sum(1 for t in tickets if getattr(t, "ola_breached", False)),
            "by_priority": [{"priority": k, "total": v[0], "on_time": v[1], "pct": round(100 * v[1] / v[0], 1)}
                            for k, v in sorted(por_prioridad.items())]}


# ── Satisfacción ─────────────────────────────────────────────────────────────

def satisfaccion(db: Session, unidad, con_items: bool = False) -> dict:
    """NPS (0-10) y CSAT (1-5, % de 4 y 5) del último año. Sin nombres de empleados."""
    from app.models.nps import ClientNPS
    desde = datetime.now(timezone.utc) - timedelta(days=365)
    filas = db.query(ClientNPS).filter(ClientNPS.client_id == unidad.id, ClientNPS.created_at >= desde) \
        .order_by(ClientNPS.created_at.desc()).all()
    nps = [r for r in filas if (r.survey_type or "nps") == "nps"]
    csat = [r for r in filas if r.survey_type == "csat"]
    valor_nps = None
    if nps:
        valor_nps = round(100 * (sum(r.score >= 9 for r in nps) - sum(r.score <= 6 for r in nps)) / len(nps), 1)
    valor_csat = round(100 * sum(r.score >= 4 for r in csat) / len(csat), 1) if csat else None
    d = {"nps": valor_nps, "csat": valor_csat, "responses": len(filas),
         "tone": umbrales.tono_de("nps", valor_nps, db, unidad.organization_id) if valor_nps is not None else None}
    if con_items:
        d["items"] = [{"id": r.id, "score": r.score, "survey_type": r.survey_type or "nps", "comment": r.comment,
                       "created_at": r.created_at.isoformat() if r.created_at else None} for r in filas[:200]]
    return d


def valorar(db: Session, usuario, unidad, score, comment: Optional[str], survey_type: str = "nps") -> dict:
    """Una respuesta por persona, unidad y mes (base legal: relación laboral; retención propia)."""
    from app.models.nps import ClientNPS, NPSCategory
    if survey_type not in ("nps", "csat"):
        raise error(422, "interno_resultado_no_valido", valor=survey_type)
    minimo, maximo = (0, 10) if survey_type == "nps" else (1, 5)
    try:
        score = int(score)
    except (TypeError, ValueError):
        raise error(422, "interno_puntuacion_fuera_de_rango", min=minimo, max=maximo)
    if not minimo <= score <= maximo:
        raise error(422, "interno_puntuacion_fuera_de_rango", min=minimo, max=maximo)
    hoy = timeutil.today()
    inicio_mes = datetime(hoy.year, hoy.month, 1, tzinfo=timezone.utc)
    if db.query(ClientNPS).filter(ClientNPS.client_id == unidad.id, ClientNPS.respondent_user_id == usuario.id,
                                  ClientNPS.survey_type == survey_type, ClientNPS.created_at >= inicio_mes).first():
        raise error(409, "interno_ya_valorado")
    equivalente = score if survey_type == "nps" else (score - 1) * 2.5
    categoria = (NPSCategory.promoter if equivalente >= 9 else
                 NPSCategory.passive if equivalente >= 7 else NPSCategory.detractor)
    r = ClientNPS(organization_id=unidad.organization_id, client_id=unidad.id, score=score, category=categoria,
                  comment=(comment or "").strip()[:2000] or None, respondent=None, source="internal_portal",
                  survey_type=survey_type, respondent_user_id=usuario.id)
    db.add(r)
    db.flush()
    audit_log(db, usuario, "CREATE", "internal_satisfaction", str(r.id), unidad.name,
              new_values={"survey_type": survey_type, "score": score})
    db.commit()
    return {"id": r.id, "score": score, "survey_type": survey_type}


# ── Plan de adopción ─────────────────────────────────────────────────────────

def adopcion_dict(db: Session, a: InternalAdoptionItem) -> dict:
    from app.models.project import Project
    p = db.get(Project, a.project_id) if a.project_id else None
    return {"id": a.id, "client_id": a.client_id, "kind": a.kind, "title": a.title,
            "due_date": str(a.due_date) if a.due_date else None, "status": a.status,
            "target_users": a.target_users, "reached_users": a.reached_users, "project_id": a.project_id,
            "project_name": p.name if p else None, "course_id": a.course_id}


def adopcion(db: Session, unidad) -> list[dict]:
    filas = db.query(InternalAdoptionItem).filter(InternalAdoptionItem.client_id == unidad.id) \
        .order_by(InternalAdoptionItem.due_date.is_(None), InternalAdoptionItem.due_date).all()
    return [adopcion_dict(db, a) for a in filas]


_CAMPOS_ADOPCION = ("kind", "title", "due_date", "status", "target_users", "reached_users", "project_id", "course_id")


def guardar_adopcion(db: Session, actor, datos: dict, unidad=None, aid: Optional[str] = None) -> dict:
    if aid:
        a = db.get(InternalAdoptionItem, aid)
        if a is None:
            raise error(404, "no_encontrado", detail="Acción de adopción no encontrada", que="accion_de_adopcion")
    else:
        a = InternalAdoptionItem(organization_id=unidad.organization_id, client_id=unidad.id)
    if datos.get("kind") is not None and datos["kind"] not in TIPOS_ADOPCION:
        raise error(422, "estado_no_valido", estado=datos["kind"])
    if datos.get("status") is not None and datos["status"] not in ESTADOS_ADOPCION:
        raise error(422, "estado_no_valido", estado=datos["status"])
    for campo in _CAMPOS_ADOPCION:
        if campo in datos:
            setattr(a, campo, datos[campo] if datos[campo] != "" else None)
    if not (a.title or "").strip():
        raise error(422, "campo_obligatorio", campo="title")
    db.add(a)
    db.flush()
    audit_log(db, actor, "UPDATE" if aid else "CREATE", "internal_adoption_item", a.id, a.title)
    db.commit()
    return adopcion_dict(db, a)


def borrar_adopcion(db: Session, actor, aid: str) -> None:
    a = db.get(InternalAdoptionItem, aid)
    if a is None:
        raise error(404, "no_encontrado", detail="Acción de adopción no encontrada", que="accion_de_adopcion")
    audit_log(db, actor, "DELETE", "internal_adoption_item", a.id, a.title)
    db.delete(a)
    db.commit()


# ── Caso de negocio y beneficios ─────────────────────────────────────────────

def _consecucion(b: ProjectBenefit) -> Optional[float]:
    if b.target is None or b.actual is None:
        return None
    base = b.baseline or 0.0
    if b.target == base:
        return None
    return round(100 * (b.actual - base) / (b.target - base), 1)


def beneficio_dict(db: Session, b: ProjectBenefit) -> dict:
    from app.models.project import Project
    from app.models.user import User
    p = db.get(Project, b.project_id)
    o = db.get(User, b.owner_id) if b.owner_id else None
    return {"id": b.id, "project_id": b.project_id, "project_name": p.name if p else None, "name": b.name,
            "kind": b.kind, "unit": b.unit, "baseline": b.baseline, "target": b.target, "actual": b.actual,
            "target_date": str(b.target_date) if b.target_date else None,
            "measured_at": str(b.measured_at) if b.measured_at else None, "achievement_pct": _consecucion(b),
            "owner_id": b.owner_id, "owner_name": o.full_name if o else None, "notes": b.notes}


def beneficios(db: Session, project_ids: list[str]) -> list[dict]:
    if not project_ids:
        return []
    filas = db.query(ProjectBenefit).filter(ProjectBenefit.project_id.in_(project_ids)) \
        .order_by(ProjectBenefit.project_id, ProjectBenefit.name).all()
    return [beneficio_dict(db, b) for b in filas]


_CAMPOS_BENEFICIO = ("name", "kind", "unit", "baseline", "target", "actual", "target_date", "measured_at",
                     "owner_id", "notes")


def guardar_beneficio(db: Session, actor, datos: dict, project_id: Optional[str] = None,
                      bid: Optional[str] = None) -> dict:
    from app.models.project import Project
    if bid:
        b = db.get(ProjectBenefit, bid)
        if b is None:
            raise error(404, "no_encontrado", detail="Beneficio no encontrado", que="beneficio")
        antes = beneficio_dict(db, b)
    else:
        p = db.get(Project, project_id)
        if p is None:
            raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
        b = ProjectBenefit(organization_id=p.organization_id, project_id=p.id)
        antes = None
    if datos.get("kind") is not None and datos["kind"] not in TIPOS_BENEFICIO:
        raise error(422, "estado_no_valido", estado=datos["kind"])
    for campo in _CAMPOS_BENEFICIO:
        if campo in datos:
            setattr(b, campo, datos[campo] if datos[campo] != "" else None)
    if not (b.name or "").strip():
        raise error(422, "campo_obligatorio", campo="name")
    db.add(b)
    db.flush()
    audit_log(db, actor, "UPDATE" if bid else "CREATE", "project_benefit", b.id, b.name, old_values=antes,
              new_values=beneficio_dict(db, b))
    db.commit()
    return beneficio_dict(db, b)


def borrar_beneficio(db: Session, actor, bid: str) -> None:
    b = db.get(ProjectBenefit, bid)
    if b is None:
        raise error(404, "no_encontrado", detail="Beneficio no encontrado", que="beneficio")
    audit_log(db, actor, "DELETE", "project_benefit", b.id, b.name)
    db.delete(b)
    db.commit()
