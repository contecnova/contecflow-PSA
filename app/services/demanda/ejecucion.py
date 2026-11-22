"""Qué pasa cuando un expediente termina.

Dos vías, las dos configurables en el flujo:

1. **Ejecución manual** de un expediente aprobado (`execution`: `backlog`,
   `new_project`, `portfolio`): alguien con `demanda.gestionar` elige; el
   expediente pasa a `done`.
2. **Acciones automáticas al cerrar** (`on_close_actions`:
   `[{action, when: approved|rejected|any, params}]`): crear proyecto,
   petición de cambio del proyecto, propuesta de cartera, tarea, ticket del
   service desk, cambio ITSM, Executive Summary y petición de compra
   (`create_purchase`: ticket en la cola de compras de ALM, `ALM_PURCHASE_GROUP_ID`).

Lo creado lleva como aprobador a quien tomó la decisión final de verdad (no al
cliente ni a quien ejecuta), y cada acción queda en `executed_actions` y en el
log del expediente. Un fallo en una acción automática no deshace el cierre:
queda anotado con `ok: false`.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.demanda import definicion as D
from app.services.demanda.acceso import Actor, puede_gestionar
from app.services.demanda.motor import ahora, datos_de, flujo_de, jload, registrar

logger = logging.getLogger(__name__)


def _valor(req, alias: str):
    defn = flujo_de(req)
    clave = D.campo_de_politica(defn, alias)
    v = datos_de(req).get(clave) if clave else None
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _descripcion(req) -> str:
    datos = datos_de(req)
    defn = flujo_de(req)
    partes = [f"{D.nombre(c.get('label'))}: {datos[c['key']]}" for c in D.campos(defn)
              if c.get("type") in ("textarea", "text") and not D.vacio(datos.get(c["key"]))]
    return (f"Expediente {req.code}\n\n" + "\n\n".join(partes))[:20000]


def _decisor_final(db: Session, req) -> Optional[str]:
    from app.models.demanda import DemandTransition
    t = db.query(DemandTransition).filter(DemandTransition.request_id == req.id,
                                          DemandTransition.actor_user_id.isnot(None),
                                          DemandTransition.decision.in_(("approve", "complete", "fast_track",
                                                                         "vote_approve"))) \
        .order_by(DemandTransition.seq.desc()).first()
    return t.actor_user_id if t else None


def _usuario(db: Session, uid: Optional[str]):
    from app.models.user import User
    return db.query(User).filter(User.id == uid).first() if uid else None


# ── Acciones ────────────────────────────────────────────────────────────────

def _crear_proyecto(db: Session, req, actor: Actor, params: dict) -> str:
    from app.models.project import Project
    from app.services.numbering import next_numbered_code
    from app.services.settings_service import get_runtime_str
    p = Project(organization_id=req.organization_id,
                code=next_numbered_code(db, "project", prefix="PRJ", padding=4),
                name=(params.get("name") or req.title)[:255], description=_descripcion(req),
                project_type=get_runtime_str(db, "DEFAULT_PROJECT_TYPE", req.organization_id),
                client_id=req.client_id, pm_id=params.get("pm_id"), budget_amount=_valor(req, "coste"),
                budget_hours=_valor(req, "esfuerzo"), created_by=actor.id if actor.kind == "user" else None)
    db.add(p)
    db.flush()
    req.result_project_id = p.id
    return p.id


def _crear_cr(db: Session, req, actor: Actor, params: dict) -> str:
    from app.models.resources import ChangeRequest, ChangeRequestStatus
    from app.services.change_service import _next_code
    if not req.project_id:
        raise error(422, "dem_ejecucion_exige_proyecto")
    decisor = _decisor_final(db, req)
    cr = ChangeRequest(organization_id=req.organization_id, code=_next_code(db), project_id=req.project_id,
                       title=req.title[:255], description=_descripcion(req),
                       justification=datos_de(req).get("justificacion"), cost_impact=_valor(req, "coste"),
                       status=ChangeRequestStatus.approved, requested_by=req.requester_user_id,
                       reviewed_by=decisor, approved_by=decisor, approved_at=ahora().date(),
                       submitted_at=(req.submitted_at or ahora()).date(),
                       resolution_notes=f"Aprobada en el flujo de demanda {req.code}")
    db.add(cr)
    db.flush()
    req.result_change_request_id = cr.id
    return cr.id


def _crear_propuesta(db: Session, req, actor: Actor, params: dict) -> str:
    from app.models.portfolio import PortfolioProposal
    p = PortfolioProposal(organization_id=req.organization_id, title=req.title[:255], description=_descripcion(req),
                          requested_by=req.requester_user_id, client_id=req.client_id,
                          estimated_budget=_valor(req, "coste"), estimated_hours=_valor(req, "esfuerzo"),
                          status="approved", decision_note=f"Aprobada en el flujo de demanda {req.code}")
    db.add(p)
    db.flush()
    req.result_proposal_id = p.id
    return p.id


def _crear_tarea(db: Session, req, actor: Actor, params: dict) -> str:
    from app.models.task import Task
    from app.services.numbering import next_numbered_code
    proyecto = params.get("project_id") or req.project_id or req.result_project_id
    if not proyecto:
        raise error(422, "dem_ejecucion_exige_proyecto")
    t = Task(organization_id=req.organization_id, code=next_numbered_code(db, "task", prefix="TSK", padding=5),
             project_id=proyecto, title=(params.get("title") or req.title)[:500], description=_descripcion(req),
             assignee_id=params.get("assignee_id"))
    db.add(t)
    db.flush()
    return t.id


def _crear_ticket(db: Session, req, actor: Actor, params: dict) -> str:
    from app.schemas.service_desk import TicketCreateIn
    from app.models.service_desk._enums import TicketType
    from app.services.service_desk.ticket_creation_service import build_internal_ticket
    solicitante = req.requester_user_id or (actor.id if actor.kind == "user" else None) or req.created_by_user_id
    if not solicitante:
        raise error(422, "dem_accion_sin_solicitante")
    t = build_internal_ticket(db, TicketCreateIn(title=(params.get("title") or req.title)[:250],
                                                 description=_descripcion(req),
                                                 ticket_type=params.get("ticket_type") or TicketType.service_request.value,
                                                 project_id=req.project_id, client_id=req.client_id,
                                                 service_item_id=req.scope_ref_id if req.scope_kind == "service"
                                                 else None,
                                                 ci_id=req.scope_ref_id if req.scope_kind == "asset" else None,
                                                 source="portal", tags="demanda"), solicitante)
    db.flush()
    return t.id


def _crear_cambio_itsm(db: Session, req, actor: Actor, params: dict) -> str:
    from app.services.service_desk.change_service import create_change_record
    datos = datos_de(req)
    usuario = _usuario(db, _decisor_final(db, req)) or (actor.user if actor.kind == "user" else None) \
        or _usuario(db, req.requester_user_id)
    if usuario is None:
        raise error(422, "dem_accion_sin_solicitante")
    tipo = {"estandar": "standard", "urgente": "emergency"}.get(str(datos.get("tipo_cambio")), "normal")
    c = create_change_record(db, usuario, {
        "title": req.title[:250], "description": _descripcion(req), "change_type": tipo,
        "risk": {"alto": "high", "bajo": "low"}.get(str(datos.get("riesgo")), "medium"),
        "implementation_plan": datos.get("plan_implantacion") or "", "rollback_plan": datos.get("plan_marcha_atras")
        or "", "business_justification": datos.get("justificacion") or "",
        "planned_start": datos.get("ventana") or None})
    db.flush()
    return c.id


def _resumen(db: Session, req, actor: Actor, params: dict) -> str:
    from app.services.demanda.resumen_ejecutivo import generar
    docs = generar(db, req, actor, config=params or None)
    return ",".join(d.id for d in docs)


def _compra(db: Session, req, actor: Actor, params: dict) -> str:
    """Petición de compra: el mismo camino que ALM (ticket en la cola de compras
    `ALM_PURCHASE_GROUP_ID`, `alm_integracion._comun.abrir_ticket`), con el importe,
    el proveedor y el centro de coste del expediente en los campos del ticket."""
    from app.services.alm_integracion import _comun as alm
    solicitante = req.requester_user_id or (actor.id if actor.kind == "user" else None) or req.created_by_user_id
    if not solicitante:
        raise error(422, "dem_accion_sin_solicitante")
    datos = datos_de(req)
    t = alm.abrir_ticket(db, titulo=f"Compra: {params.get('title') or req.title}", descripcion=_descripcion(req),
                         solicitante_id=solicitante, grupo_ajuste="ALM_PURCHASE_GROUP_ID",
                         org_id=req.organization_id, project_id=req.project_id,
                         service_item_id=req.scope_ref_id if req.scope_kind == "service" else None,
                         ci_id=req.scope_ref_id if req.scope_kind == "asset" else None,
                         campos={"demand_request": req.code, "importe": _valor(req, "coste"),
                                 "proveedor": datos.get("proveedor"), "centro_coste": datos.get("centro_coste")})
    db.flush()
    return t.id


ACCIONES = {"create_project": _crear_proyecto, "create_change_request": _crear_cr,
            "create_portfolio_proposal": _crear_propuesta, "create_task": _crear_tarea, "create_ticket": _crear_ticket,
            "create_itsm_change": _crear_cambio_itsm, "executive_summary": _resumen, "create_purchase": _compra}
MODO_A_ACCION = {"backlog": "create_change_request", "new_project": "create_project",
                 "portfolio": "create_portfolio_proposal"}


def _anotar(req, accion: str, ok: bool, ident: Optional[str] = None, motivo: Optional[str] = None) -> None:
    hechas = jload(req.executed_actions, [])
    hechas.append({"action": accion, "ok": ok, "id": ident, "error": motivo, "at": ahora().isoformat()})
    req.executed_actions = json.dumps(hechas, ensure_ascii=False)


def acciones_al_cerrar(db: Session, req, actor: Actor, estado: str) -> None:
    """Las `on_close_actions` del flujo que tocan con este cierre. No commitea."""
    for a in flujo_de(req).get("on_close_actions") or []:
        cuando = a.get("when", "approved")
        if cuando not in ("any", estado) or a.get("action") not in ACCIONES:
            continue
        try:
            with db.begin_nested():
                ident = ACCIONES[a["action"]](db, req, actor, a.get("params") or {})
            _anotar(req, a["action"], True, ident)
            registrar(db, req, actor, "action", estado_previo=req.status,
                      datos={"action": a["action"], "id": ident})
        except Exception as exc:
            codigo = getattr(exc, "code", None) or type(exc).__name__
            logger.warning("demanda %s: la acción %s falló: %s", req.code, a.get("action"), exc)
            _anotar(req, a["action"], False, motivo=str(codigo))


def ejecutar(db: Session, actor: Actor, req, modo: str, params: dict) -> dict:
    """Ejecución manual de un expediente aprobado. Commitea."""
    if not puede_gestionar(actor):
        raise error(403, "capacidad_requerida", capacidad="demanda.gestionar")
    if req.status != "approved":
        raise error(409, "dem_no_aprobada")
    if req.result_kind:
        raise error(409, "dem_ya_ejecutada")
    modos = flujo_de(req).get("execution") or list(D.MODOS_DE_EJECUCION)
    if modo not in modos or modo not in MODO_A_ACCION:
        raise error(422, "dem_ejecucion_no_valida", modo=modo)
    ident = ACCIONES[MODO_A_ACCION[modo]](db, req, actor, params or {})
    req.result_kind = modo
    req.status = "done"
    req.closed_at = ahora()
    _anotar(req, MODO_A_ACCION[modo], True, ident)
    registrar(db, req, actor, "execute", estado_previo="approved", datos={"mode": modo, "id": ident})
    db.commit()
    return {"mode": modo, "id": ident}
