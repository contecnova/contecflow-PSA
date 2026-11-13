"""
incident_assignment_service.py — recomendacion de agente o cola por reglas ponderadas.

Puntua a cada candidato por:
  - patrones historicos de asignacion por categoria y palabras clave
  - carga de trabajo y capacidad actuales
  - coincidencia de habilidades (skills.py)
  - urgencia de la prioridad
  - guardias

Auditoria 2026-11: decia usar «un clasificador LightGBM entrenado cuando esta
disponible». No habia ninguno: solo se comprobaba si la libreria se podia
importar, y la pantalla enseñaba «LightGBM ON» por tenerla instalada. Es un
puntuador por reglas y asi se declara (`lgbm_available` queda en falso por
compatibilidad con quien lo lea).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from app.models.settings import AppSetting
from app.core.errores import ErrorDeDominio

# Ningun modelo entrenado: el metodo es por reglas (ver la cabecera).
_LGBM_AVAILABLE = False

_KEY_ASSIGNMENT_STATS = "sd.ml_assignment.stats"
_KEY_ASSIGNMENT_MODEL = "sd.ml_assignment.model_meta"
logger = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _capacity_to_slots(raw_capacity: Any) -> int:
    """Convert weekly capacity value into coarse ticket slots.

    Some environments may carry unexpected values (None/empty/non-numeric)
    from legacy imports; keep endpoint resilient and return a sensible default.
    """
    try:
        hours = float(raw_capacity)
    except (TypeError, ValueError):
        hours = 40.0
    if hours <= 0:
        hours = 40.0
    return max(1, int(hours // 4) or 10)


def recommend_assignment(
    db: Session,
    *,
    ticket_id: str,
    title: str,
    description: str,
    priority: str,
    ticket_type: str,
    org_id: Optional[str],
    candidate_agents: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Recommend assignment for a ticket.

    candidate_agents format:
      [{
        "user_id": str,
        "name": str,
        "active_tickets": int,
        "capacity": int,
        "specializations": [str],
        "is_on_call": bool,
        "group_id": Optional[str],
      }]

    Returns:
      {
        recommended_user_id, recommended_name, confidence, all_scores,
        method_used, reasoning
      }
    """
    from app.models.service_desk import AgentGroupMember, Ticket
    from app.services.service_desk.ml_routing_service import (
        get_routing_candidates,
        predict_best_agent,
    )

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise ErrorDeDominio(status_code=404, detail="Ticket no encontrado")

    members: list[Any] = []
    if ticket.assigned_group_id:
        members = (
            db.query(AgentGroupMember)
            .filter(AgentGroupMember.group_id == ticket.assigned_group_id)
            .all()
        )
    elif candidate_agents:
        class _MemberProxy:
            def __init__(self, user_id: str):
                self.user_id = user_id

        members = [_MemberProxy(str(a.get("user_id"))) for a in candidate_agents if a.get("user_id")]
    else:
        all_members = db.query(AgentGroupMember).all()
        seen: set[str] = set()
        for m in all_members:
            if m.user_id in seen:
                continue
            seen.add(m.user_id)
            members.append(m)

    if not members:
        return {
            "recommended_user_id": None,
            "recommended_name": None,
            "confidence": 0.0,
            "all_scores": [],
            "recommendations": [],
            "method_used": "no_candidates",
            "reasoning": "No candidate agents available",
            "lgbm_available": _LGBM_AVAILABLE,
        }

    ranked = get_routing_candidates(db, ticket, members)
    best_user_id = predict_best_agent(db, ticket, members)
    best = next((c for c in ranked if c.get("user_id") == best_user_id), ranked[0] if ranked else None)

    if not best:
        return {
            "recommended_user_id": None,
            "recommended_name": None,
            "confidence": 0.0,
            "all_scores": [],
            "recommendations": [],
            "method_used": "no_candidates",
            "reasoning": "No eligible candidates",
            "lgbm_available": _LGBM_AVAILABLE,
        }

    scores = [
        {
            "user_id": c.get("user_id"),
            "name": c.get("user_name"),
            "score": c.get("composite_score", 0.0),
            "available": c.get("available", False),
            "components": c.get("components", {}),
        }
        for c in ranked
    ]

    # Record stat
    stats: dict = _get_setting(db, _KEY_ASSIGNMENT_STATS, org_id)
    stats["total_recommendations"] = stats.get("total_recommendations", 0) + 1
    stats["last_recommendation_at"] = _iso_now()
    _set_setting(db, _KEY_ASSIGNMENT_STATS, org_id, stats)

    return {
        "recommended_user_id": best.get("user_id"),
        "recommended_name": best.get("user_name"),
        "confidence": best.get("composite_score", 0.0),
        "all_scores": scores,
        "recommendations": scores,
        "method_used": "ml_score_v2",
        "reasoning": (
            "Top score ML: "
            f"availability={best.get('components', {}).get('availability')}, "
            f"historical_speed={best.get('components', {}).get('historical_speed')}, "
            f"historical_csat={best.get('components', {}).get('historical_csat')}, "
            f"skill_match={best.get('components', {}).get('skill_match')}"
        ),
        "lgbm_available": _LGBM_AVAILABLE,
    }


def _acotar_a_la_organizacion(q, org_id: Optional[str]):
    """Acota una consulta de tickets a una organizacion.

    `Ticket` NO tiene columna `organization_id`: el alcance se deduce del
    proyecto. Y el `outerjoin` con `project_id IS NULL` es deliberado — un
    ticket sin proyecto es interno del service desk y pertenece a la
    organizacion que pregunta, asi que un `join` normal lo perderia.

    Estaba escrito dos veces identico dentro de `get_assignment_stats`.
    """
    if not org_id:
        return q
    from sqlalchemy import or_ as _or

    from app.models.project import Project as _Project
    from app.models.service_desk import Ticket

    return q.outerjoin(_Project, Ticket.project_id == _Project.id).filter(
        _or(Ticket.project_id.is_(None), _Project.organization_id == org_id)
    )


def _intentar(db: Session, descripcion: str, org_id: Optional[str], accion, por_defecto):
    """Ejecuta `accion()` y, si falla, deshace la transaccion y devuelve el defecto.

    El `rollback` no es cosmetico: sin el, una consulta fallida deja la sesion en
    transaccion abortada y las SIGUIENTES fallan tambien, asi que un panel se
    quedaria entero en blanco por un solo problema. El `try` alrededor del
    `rollback` es porque si tampoco se puede deshacer no queda nada que hacer y
    logueando ahi se encadenarian los errores.

    Este bloque estaba escrito CUATRO veces identico dentro de
    `get_assignment_stats`.
    """
    try:
        return accion()
    except Exception as exc:
        logger.warning("SD assignment stats: %s (org=%s): %s", descripcion, org_id, exc)
        try:
            db.rollback()
        # intentional: cleanup path, logging would cascade
        except Exception:
            logger.debug("get_assignment_stats: fallo best-effort ignorado", exc_info=True)
        return por_defecto


def _agentes_del_service_desk(db: Session, org_id: Optional[str]) -> list:
    """Los miembros de cualquier grupo de agentes, con su usuario y su grupo."""
    from app.models.service_desk import AgentGroupMember
    from app.models.user import User

    def consulta():
        q = db.query(AgentGroupMember).options(
            joinedload(AgentGroupMember.user),
            joinedload(AgentGroupMember.group),
        ).join(User, AgentGroupMember.user_id == User.id)
        if org_id:
            q = q.filter(User.organization_id == org_id)
        return q.all()

    return _intentar(db, "failed loading agent members", org_id, consulta, [])


def _carga_por_agente(db: Session, org_id: Optional[str], estados_cerrados: list) -> dict:
    """Cuantos tickets abiertos tiene cada agente, en una sola consulta."""
    from sqlalchemy import func as sqlfunc

    from app.models.service_desk import Ticket

    def consulta():
        q = (
            db.query(Ticket.assigned_to_user_id, sqlfunc.count(Ticket.id).label("cnt"))
            .filter(Ticket.assigned_to_user_id.isnot(None))
            .filter(Ticket.status.notin_(estados_cerrados))
        )
        q = _acotar_a_la_organizacion(q, org_id).group_by(Ticket.assigned_to_user_id)
        return {row.assigned_to_user_id: int(row.cnt or 0) for row in q.all()}

    return _intentar(db, "failed loading ticket load map", org_id, consulta, {})


def _tickets_sin_asignar(db: Session, org_id: Optional[str], estados_cerrados: list) -> int:
    """Cuantos tickets abiertos no tienen a nadie asignado."""
    from sqlalchemy import func as sqlfunc

    from app.models.service_desk import Ticket

    def consulta():
        q = db.query(sqlfunc.count(Ticket.id)).filter(
            Ticket.assigned_to_user_id.is_(None),
            Ticket.status.notin_(estados_cerrados),
        )
        return int(_acotar_a_la_organizacion(q, org_id).scalar() or 0)

    return _intentar(db, "failed loading unassigned count", org_id, consulta, 0)


def _agregar_agentes(miembros: list, carga: dict) -> list:
    """Un registro por AGENTE, no por pertenencia a grupo.

    Una persona en tres grupos aparece tres veces en `miembros`; sin esta
    agregacion saldria tres veces en el panel y su carga se contaria por
    triplicado. Los nombres de grupo se acumulan como especializaciones.
    """
    agg: dict[str, dict[str, Any]] = {}
    for m in miembros:
        uid = m.user_id
        if not m.user:
            continue
        if uid not in agg:
            nombre = m.user.full_name or m.user.email or uid
            abiertos = carga.get(uid, 0)
            agg[uid] = {
                # `user_id`/`agent_id` y `name`/`agent_name` estan duplicados a
                # proposito: la interfaz lee unos nombres y el modelo de
                # enrutado los otros, y unificarlos romperia uno de los dos.
                "user_id": uid,
                "agent_id": uid,
                "agent_name": nombre,
                "name": nombre,
                "open_tickets": abiertos,
                "active_tickets": abiertos,
                "capacity": _capacity_to_slots(getattr(m.user, "weekly_capacity_hours", 40)),
                "specializations": [],
                "is_on_call": False,
                "groups": [],
            }
        if m.group and m.group.name and m.group.name not in agg[uid]["groups"]:
            agg[uid]["groups"].append(m.group.name)
            # El nombre del grupo vale como etiqueta blanda de especializacion.
            agg[uid]["specializations"].append(m.group.name.lower())

    return sorted(agg.values(), key=lambda a: a["open_tickets"], reverse=True)


def get_assignment_stats(db: Session, *, org_id: Optional[str]) -> dict:
    """Aggregate stats for the ML assignment dashboard.

    Returns counters of past recommendations PLUS real-time agent_loads for SD
    agents (so the UI can render a workload chart and use them as candidates
    for a new recommendation).

    Cada consulta va envuelta en `_intentar`: es un panel, asi que un fallo en
    una parte devuelve esa parte a cero en vez de dejar la pantalla en blanco.
    """
    from app.models.service_desk import TicketStatus

    try:
        stats = _get_setting(db, _KEY_ASSIGNMENT_STATS, org_id)

        # Se llaman «cerrados» y no «activos» como antes: la lista es de estados
        # que NO cuentan como carga de trabajo, y el nombre anterior decia lo
        # contrario de lo que contiene.
        estados_cerrados = [
            TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled,
        ]

        miembros = _agentes_del_service_desk(db, org_id)
        if miembros:
            carga = _carga_por_agente(db, org_id, estados_cerrados)
            agent_loads = _agregar_agentes(miembros, carga)
            total_unassigned = _tickets_sin_asignar(db, org_id, estados_cerrados)
        else:
            agent_loads = []
            total_unassigned = 0

        return {
            **stats,
            "agent_loads": agent_loads,
            "total_unassigned": total_unassigned,
            "lgbm_available": _LGBM_AVAILABLE,
        }
    except Exception as exc:
        logger.exception("SD assignment stats: unexpected error (org=%s): %s", org_id, exc)
        try:
            db.rollback()
        # intentional: cleanup path, logging would cascade
        except Exception:
            logger.debug("get_assignment_stats: fallo best-effort ignorado", exc_info=True)
        return {
            "agent_loads": [],
            "total_unassigned": 0,
            "lgbm_available": _LGBM_AVAILABLE,
        }


def _get_setting(db: Session, key: str, org_id: Optional[str]) -> dict:
    q = db.query(AppSetting).filter(AppSetting.key == key)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except Exception:
        logger.debug("_get_setting: excepcion ignorada", exc_info=True)
        return {}


def _set_setting(db: Session, key: str, org_id: Optional[str], value: dict) -> None:
    payload = json.dumps(value, ensure_ascii=False)
    q = db.query(AppSetting).filter(AppSetting.key == key)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row:
        row = AppSetting(key=key, organization_id=org_id, value=payload, description=f"SD ML Assignment: {key}")
        db.add(row)
    else:
        row.value = payload
    db.commit()
