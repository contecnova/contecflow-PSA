"""Cartera: intake de propuestas → puntuación → fases (stage-gate) → proyecto.

Proyectos — hub (16-11-2026, rev. 173). La cartera solo agrupaba proyectos que
ya existían. Ahora una idea entra como propuesta y recorre:

  1. **Intake**: título, presupuesto y horas estimadas, ventana de fechas y los
     roles que pide (`roles_needed`: [{role, hours}]).
  2. **Puntuación**: cada criterio activo de la empresa (peso configurable;
     «inverso» si puntúa mejor cuanto más bajo, como el riesgo) recibe un valor
     de 0 a 10. La nota es la media ponderada en 0-100.
  3. **Fases**: se envía a la siguiente fase activa (por orden). Con nota por
     debajo del mínimo de la fase (o `PORTFOLIO_MIN_SCORE_TO_ADVANCE`) no se
     puede enviar. La fase la decide el **motor de aprobaciones** (tipo
     `portfolio_gate`, con el flujo de la fase o el por defecto del tipo,
     políticas incluidas); si la empresa no ha diseñado ninguno, la decide un
     admin o PM desde la pantalla. Superada la última, queda aprobada.
  4. **Proyecto**: una propuesta aprobada se convierte en proyecto (con su
     plantilla si la tiene) y queda enlazada.

La **capacidad** (`capacidad`) compara las horas que pide cada rol con las que
el equipo tiene libres en la ventana: capacidad del calendario de cada persona
(festivos y ausencias) menos lo ya asignado en tareas.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.models.portfolio import PortfolioCriterion, PortfolioGate, PortfolioProposal
from app.core.codigos_de_error import error

TIPO_DE_APROBACION = "portfolio_gate"
_VALOR_MAXIMO = 10.0


def _org(user) -> Optional[str]:
    return getattr(user, "organization_id", None)


def _json(texto, defecto):
    try:
        return json.loads(texto) if texto else defecto
    except ValueError:
        return defecto


# ── Criterios y fases ────────────────────────────────────────────────────────

def criterio_dict(c: PortfolioCriterion) -> dict:
    return {"id": c.id, "name": c.name, "description": c.description, "weight": c.weight,
            "inverse": bool(c.inverse), "sort_order": c.sort_order, "is_active": bool(c.is_active)}


def fase_dict(g: PortfolioGate) -> dict:
    return {"id": g.id, "name": g.name, "description": g.description, "sort_order": g.sort_order,
            "workflow_id": g.workflow_id, "min_score": g.min_score, "is_active": bool(g.is_active)}


def criterios(db: Session, user, solo_activos: bool = False) -> list[PortfolioCriterion]:
    q = db.query(PortfolioCriterion).filter(PortfolioCriterion.organization_id == _org(user))
    if solo_activos:
        q = q.filter(PortfolioCriterion.is_active.is_(True))
    return q.order_by(PortfolioCriterion.sort_order, PortfolioCriterion.name).all()


def fases(db: Session, user, solo_activas: bool = True) -> list[PortfolioGate]:
    q = db.query(PortfolioGate).filter(PortfolioGate.organization_id == _org(user))
    if solo_activas:
        q = q.filter(PortfolioGate.is_active.is_(True))
    return q.order_by(PortfolioGate.sort_order, PortfolioGate.name).all()


def guardar_criterio(db: Session, user, datos: dict, criterio_id: Optional[str] = None) -> dict:
    from app.services.audit import audit_log
    if datos.get("weight") is not None and datos["weight"] < 0:
        raise error(422, "peso_negativo")
    c = _propio(db, user, PortfolioCriterion, criterio_id) if criterio_id else PortfolioCriterion(
        organization_id=_org(user))
    for campo in ("name", "description", "weight", "inverse", "sort_order", "is_active"):
        if campo in datos and datos[campo] is not None:
            setattr(c, campo, datos[campo])
    db.add(c)
    db.flush()
    audit_log(db, user, "UPDATE" if criterio_id else "CREATE", "portfolio_criterion", c.id, c.name)
    db.commit()
    return criterio_dict(c)


def guardar_fase(db: Session, user, datos: dict, fase_id: Optional[str] = None) -> dict:
    from app.models.billing_reports import ApprovalWorkflow
    from app.services.audit import audit_log
    if datos.get("workflow_id") and db.query(ApprovalWorkflow.id).filter(
            ApprovalWorkflow.id == datos["workflow_id"]).first() is None:
        raise error(422, "no_encontrado", detail="Ese flujo de aprobación no existe", que="flujo")
    g = _propio(db, user, PortfolioGate, fase_id) if fase_id else PortfolioGate(organization_id=_org(user))
    for campo in ("name", "description", "sort_order", "workflow_id", "min_score", "is_active"):
        if campo in datos:
            setattr(g, campo, datos[campo])
    db.add(g)
    db.flush()
    audit_log(db, user, "UPDATE" if fase_id else "CREATE", "portfolio_gate", g.id, g.name)
    db.commit()
    return fase_dict(g)


def _propio(db: Session, user, modelo, fila_id: str):
    fila = db.query(modelo).filter(modelo.id == fila_id, modelo.organization_id == _org(user)).first()
    if not fila:
        raise error(404, "no_encontrado_generico")
    return fila


# ── Propuestas ───────────────────────────────────────────────────────────────

def puntuar(valores: dict, lista: list[PortfolioCriterion]) -> Optional[float]:
    """Media ponderada en 0-100. None si no hay criterios con peso o valores."""
    total_peso, suma = 0.0, 0.0
    for c in lista:
        if not c.is_active or not c.weight or c.id not in valores or valores[c.id] is None:
            continue
        v = max(0.0, min(_VALOR_MAXIMO, float(valores[c.id])))
        if c.inverse:
            v = _VALOR_MAXIMO - v
        suma += c.weight * v
        total_peso += c.weight
    if not total_peso:
        return None
    return round(suma / total_peso / _VALOR_MAXIMO * 100, 1)


def _cliente_de(db: Session, client_id: Optional[str]) -> dict:
    """Nombre y tipo (externo/interno, rev. 193) del cliente de la propuesta."""
    if not client_id:
        return {"client_name": None, "client_kind": None}
    from app.models.clients import Client
    fila = db.query(Client.name, Client.kind).filter(Client.id == client_id).first()
    return {"client_name": fila[0] if fila else None, "client_kind": (fila[1] or "externo") if fila else None}


def propuesta_dict(db: Session, p: PortfolioProposal, lista_fases: Optional[list] = None) -> dict:
    from app.services.approval_engine import fuentes
    fases_ = lista_fases or []
    actual = fases_[p.gate_index] if p.gate_index < len(fases_) else None
    return {
        "id": p.id, "title": p.title, "description": p.description, "portfolio_id": p.portfolio_id,
        "requested_by": p.requested_by, "sponsor_id": p.sponsor_id, "client_id": p.client_id,
        **_cliente_de(db, p.client_id),
        "estimated_budget": p.estimated_budget, "estimated_hours": p.estimated_hours,
        "wanted_start": p.wanted_start.isoformat() if p.wanted_start else None,
        "wanted_end": p.wanted_end.isoformat() if p.wanted_end else None,
        "roles_needed": _json(p.roles_needed, []), "scores": _json(p.scores, {}), "score": p.score,
        "status": p.status, "gate_index": p.gate_index, "gates_total": len(fases_),
        "current_gate": fase_dict(actual) if actual else None,
        "approval_status": fuentes.estado(db, TIPO_DE_APROBACION, p.id),
        "decision_note": p.decision_note, "project_id": p.project_id, "template_id": p.template_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def listar(db: Session, user, estado: Optional[str] = None, pagina=None, client_kind: Optional[str] = None):
    from app.core.paginacion import paginar
    q = db.query(PortfolioProposal).filter(PortfolioProposal.organization_id == _org(user))
    if estado:
        q = q.filter(PortfolioProposal.status == estado)
    if client_kind in ("externo", "interno"):
        # Clientes internos (rev. 193): propuestas de unidades internas o de clientes de fuera.
        from sqlalchemy import or_
        from app.models.clients import Client
        internos = db.query(Client.id).filter(Client.kind == "interno")
        q = q.filter(PortfolioProposal.client_id.in_(internos)) if client_kind == "interno" else             q.filter(or_(PortfolioProposal.client_id.is_(None), PortfolioProposal.client_id.notin_(internos)))
    return paginar(q.order_by(PortfolioProposal.created_at.desc()), pagina, "portfolio_proposals.list")


def obtener(db: Session, user, propuesta_id: str) -> PortfolioProposal:
    return _propio(db, user, PortfolioProposal, propuesta_id)


_CAMPOS = ("title", "description", "portfolio_id", "sponsor_id", "client_id", "estimated_budget",
           "estimated_hours", "wanted_start", "wanted_end", "template_id")


def guardar(db: Session, user, datos: dict, propuesta_id: Optional[str] = None) -> dict:
    from app.services.audit import audit_log
    if propuesta_id:
        p = obtener(db, user, propuesta_id)
        if p.status not in ("draft", "in_progress", "rejected"):
            raise error(409, "propuesta_no_editable")
    else:
        p = PortfolioProposal(organization_id=_org(user), requested_by=user.id, status="draft")
    for campo in _CAMPOS:
        if campo in datos:
            setattr(p, campo, datos[campo])
    if p.wanted_start and p.wanted_end and p.wanted_end < p.wanted_start:
        raise error(422, "fecha_fin_anterior_a_inicio", detail="El fin deseado es anterior al inicio")
    if "roles_needed" in datos:
        p.roles_needed = json.dumps([{"role": str(r.get("role") or "").strip(), "hours": float(r.get("hours") or 0)}
                                     for r in (datos["roles_needed"] or []) if str(r.get("role") or "").strip()])
    if "scores" in datos:
        p.scores = json.dumps(datos["scores"] or {})
        p.score = puntuar(datos["scores"] or {}, criterios(db, user, solo_activos=True))
    if p.status == "rejected":
        p.status = "draft"
    db.add(p)
    db.flush()
    audit_log(db, user, "UPDATE" if propuesta_id else "CREATE", "portfolio_proposal", p.id, p.title)
    db.commit()
    return propuesta_dict(db, p, fases(db, user))


def enviar_a_fase(db: Session, user, propuesta_id: str) -> dict:
    """Envía la propuesta a su siguiente fase (abre la aprobación si hay flujo)."""
    from app.services.approval_engine import fuentes
    from app.services.audit import audit_log
    from app.services.settings_service import get_runtime_float

    p = obtener(db, user, propuesta_id)
    lista = fases(db, user)
    if not lista:
        raise error(409, "cartera_sin_fases")
    if p.status not in ("draft", "in_progress"):
        raise error(409, "propuesta_no_enviable")
    if p.gate_index >= len(lista):
        raise error(409, "propuesta_fases_superadas")
    fase = lista[p.gate_index]
    minimo = fase.min_score if fase.min_score is not None else (
        get_runtime_float(db, "PORTFOLIO_MIN_SCORE_TO_ADVANCE", _org(user)) or 0.0)
    if p.score is None or p.score < minimo:
        raise error(422, "propuesta_puntuacion_insuficiente", puntuacion=p.score if p.score is not None else '—', minimo=minimo)
    p.status = "in_review"
    audit_log(db, user, "SUBMIT", "portfolio_proposal", p.id, p.title, new_values={"gate": fase.name})
    db.commit()
    fuentes.abrir(db, TIPO_DE_APROBACION, p.id, f"{p.title} — {fase.name}", user.id,
                  contexto={"score": p.score, "estimated_budget": p.estimated_budget,
                            "estimated_hours": p.estimated_hours, "gate": fase.name},
                  workflow_id=fase.workflow_id)
    db.refresh(p)
    return propuesta_dict(db, p, lista)


def aplicar_decision(db: Session, propuesta_id: str, aprobado: bool, actor, nota: Optional[str] = None) -> None:
    """La decisión de una fase (desde la bandeja o desde la pantalla)."""
    from app.services.audit import audit_log
    p = db.query(PortfolioProposal).filter(PortfolioProposal.id == propuesta_id).first()
    if p is None or p.status != "in_review":
        raise error(409, "propuesta_no_pendiente")
    total = db.query(func.count(PortfolioGate.id)).filter(
        PortfolioGate.organization_id == p.organization_id, PortfolioGate.is_active.is_(True)).scalar() or 0
    p.decision_note = nota
    if aprobado:
        p.gate_index += 1
        p.status = "approved" if p.gate_index >= total else "in_progress"
    else:
        p.status = "rejected"
    audit_log(db, actor, "APPROVE" if aprobado else "REJECT", "portfolio_proposal", p.id, p.title,
              new_values={"status": p.status, "gate_index": p.gate_index})
    db.commit()


def decidir_en_pantalla(db: Session, user, propuesta_id: str, aprobado: bool, nota: Optional[str]) -> dict:
    """Admin o PM deciden la fase cuando no la lleva una solicitud de la bandeja."""
    from app.services.approval_engine import fuentes
    p = obtener(db, user, propuesta_id)
    if fuentes.estado(db, TIPO_DE_APROBACION, p.id) == "pending":
        raise error(409, "fase_decide_flujo")
    aplicar_decision(db, p.id, aprobado, user, nota)
    db.refresh(p)
    return propuesta_dict(db, p, fases(db, user))


def convertir_en_proyecto(db: Session, user, propuesta_id: str, datos: dict) -> dict:
    """Crea el proyecto de una propuesta aprobada (con su plantilla, si la tiene)."""
    from app.models.project import Project
    from app.services.audit import audit_log
    from app.services.numbering import next_numbered_code
    from app.services.settings_service import get_runtime_str

    p = obtener(db, user, propuesta_id)
    if p.status != "approved":
        raise error(409, "propuesta_solo_aprobada_convertible")
    org = _org(user)
    if p.template_id:
        from app.services.plantillas_de_proyecto import instanciar
        creado = instanciar(db, user, p.template_id, {
            "name": datos.get("name") or p.title, "description": p.description,
            "start_date": (p.wanted_start or timeutil.today()).isoformat(),
            "budget_amount": p.estimated_budget, "pm_id": datos.get("pm_id"), "client_id": p.client_id,
        })
        proyecto_id = creado["project_id"]
    else:
        proyecto = Project(
            organization_id=org,
            code=next_numbered_code(db, "project", prefix="PRJ", padding=4),
            name=datos.get("name") or p.title, description=p.description,
            project_type=get_runtime_str(db, "DEFAULT_PROJECT_TYPE", org),
            client_id=p.client_id, pm_id=datos.get("pm_id"),
            start_date=p.wanted_start, end_date_planned=p.wanted_end,
            budget_amount=p.estimated_budget, budget_hours=p.estimated_hours,
            created_by=user.id,
        )
        db.add(proyecto)
        db.flush()
        proyecto_id = proyecto.id
    p.project_id, p.status = proyecto_id, "converted"
    if p.portfolio_id:
        from app.models.portfolio import PortfolioProject
        db.add(PortfolioProject(organization_id=org, portfolio_id=p.portfolio_id, project_id=proyecto_id))
    audit_log(db, user, "CREATE_FROM_PROPOSAL", "projects", proyecto_id, p.title,
              new_values={"proposal_id": p.id})
    db.commit()
    return propuesta_dict(db, p, fases(db, user))


# ── Capacidad ────────────────────────────────────────────────────────────────

def capacidad(db: Session, user, propuesta_id: str) -> dict:
    """Horas que pide cada rol frente a las libres del equipo en la ventana."""
    from app.models.task import Task, TaskStatus
    from app.models.user import User
    from app.services.planificador.calendario import cargar_calendarios
    from app.services.settings_service import get_runtime_int

    p = obtener(db, user, propuesta_id)
    roles = _json(p.roles_needed, [])
    desde = p.wanted_start or timeutil.today()
    semanas = get_runtime_int(db, "RESOURCE_AVAILABILITY_WEEKS", _org(user)) or 1
    hasta = p.wanted_end or (desde + timedelta(weeks=semanas))
    filas = []
    for r in roles:
        nombre = r["role"]
        patron = f"%{nombre}%"
        personas = db.query(User).filter(
            User.organization_id == _org(user), User.is_active.is_(True),
            or_(User.job_title.ilike(patron), User.team.ilike(patron), User.department.ilike(patron)),
        ).all()
        ids = [u.id for u in personas]
        _emp, cals = cargar_calendarios(db, _org(user), ids, desde)
        bruto = sum(cals[u].laborables_en(desde, hasta) * cals[u].horas_por_dia for u in ids if u in cals)
        asignado = 0.0
        if ids:
            for t in db.query(Task).filter(Task.assignee_id.in_(ids), Task.is_active.is_(True),
                                           Task.status.notin_((TaskStatus.done, TaskStatus.cancelled)),
                                           Task.start_date.isnot(None), Task.due_date.isnot(None),
                                           Task.start_date <= hasta, Task.due_date >= desde).all():
                c = cals.get(t.assignee_id)
                total = c.laborables_en(t.start_date, t.due_date) if c else 0
                if total and t.estimated_hours:
                    dentro = c.laborables_en(max(t.start_date, desde), min(t.due_date, hasta))
                    asignado += t.estimated_hours * dentro / total
        libre = max(0.0, bruto - asignado)
        filas.append({"role": nombre, "needed_hours": r["hours"], "people": len(ids),
                      "capacity_hours": round(bruto, 1), "booked_hours": round(asignado, 1),
                      "free_hours": round(libre, 1), "gap_hours": round(max(0.0, r["hours"] - libre), 1)})
    return {"proposal_id": p.id, "from": desde.isoformat(), "to": hasta.isoformat(), "roles": filas,
            "fits": all(f["gap_hours"] == 0 for f in filas)}
