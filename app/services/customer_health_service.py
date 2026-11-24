"""Salud del cliente: el cálculo ÚNICO (revisión 24-11-2026).

Puntuación compuesta 0-100 de un cliente a partir de cinco componentes, cada
uno 0-100:

=====================  =========================================================
Componente             Medida (todo acotado a la empresa por el filtro de tenant)
=====================  =========================================================
``nps``                NPS de las respuestas ``survey_type = 'nps'`` de los
                       últimos ``HEALTH_NPS_LOOKBACK_DAYS`` días, llevado de
                       [-100, 100] a [0, 100] (``(nps + 100) / 2``). Las
                       valoraciones CSAT (1-5) del portal interno NO cuentan.
``delivery``           Hitos a tiempo / hitos evaluables de los proyectos vivos
                       del cliente. Evaluable: hito activo con ``due_date`` que
                       venció en la ventana (``HEALTH_NPS_LOOKBACK_DAYS``) o que
                       se completó en ella. A tiempo: ``is_completed`` y
                       ``completed_date <= due_date``. Vencido sin completar o
                       completado tarde = fuera de plazo. Completado sin fecha:
                       no medible (se descarta).
``budget``             % de proyectos en curso (activo, en espera, pausado) con
                       ``budget_amount > 0`` cuyo coste real
                       (``margen_de_proyectos.margen_en_bloque``, el cálculo único
                       del panel y la rentabilidad) no supera el presupuesto. La
                       misma regla que «proyectos por encima de presupuesto» del
                       panel.
``ticket_resolution``  Tickets del cliente resueltos/cerrados en los últimos
                       ``HEALTH_TICKET_LOOKBACK_DAYS`` días sin
                       ``sla_resolution_breached``, frente a esos resueltos más
                       los abiertos que ya han incumplido el SLA de resolución.
``portal_activity``    ``HEALTH_PORTAL_BASE_SCORE`` + ``HEALTH_PORTAL_SCORE_PER_SESSION``
                       × sesiones del portal de sus usuarios en la ventana de
                       tickets (tope 100). Sin usuarios del portal: sin datos
                       (no se penaliza a quien no usa el portal).
=====================  =========================================================

**Componentes sin datos** (decisión, estándar de mercado: Gainsight Scorecards y
ChurnZero ChurnScore). Un componente sin datos NO puntúa: se marca
``has_data = False`` y su peso se **reparte proporcionalmente** entre los que sí
tienen datos (``effective_weight = peso / suma de pesos con datos``). Así un
cliente sin proyectos no recibe un 70 inventado en entrega y presupuesto. Si
ningún componente tiene datos, la puntuación es ``HEALTH_DEFAULT_NO_DATA`` y la
categoría ``no_data``. ``data_coverage`` dice qué parte del peso configurado
está medida (0-1).

Pesos y umbrales: ajustes en vivo ``HEALTH_*`` (por empresa). Los pesos no
tienen que sumar 1: se normalizan. Un peso negativo cuenta como 0.

Antes (medido 24-11-2026): entrega leía ``ProjectMilestone.status`` y
``.completed_at`` (no existen) → siempre ``HEALTH_DEFAULT_NO_DATA``; presupuesto
leía ``Project.budget``/``.actual_cost`` (no existen) → 0 % en cuanto había un
proyecto; tickets leía ``Ticket.sla_breached`` (no existe) → 0 en cuanto había
uno resuelto; NPS contaba las CSAT 1-5 como detractores. Los ``hasattr`` y los
``try/except`` lo escondían. Ya no hay ni unos ni otros: un fallo es un fallo.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.core.timeutil import utcnow
from app.models.clients import Client
from app.models.nps import ClientNPS
from app.services.settings_service import get_runtime_namespace

_HEALTH_KEYS = {
    "HEALTH_NPS_LOOKBACK_DAYS": "int",
    "HEALTH_TICKET_LOOKBACK_DAYS": "int",
    "HEALTH_DEFAULT_NO_DATA": "float",
    "HEALTH_PORTAL_BASE_SCORE": "float",
    "HEALTH_PORTAL_SCORE_PER_SESSION": "float",
    "HEALTH_WEIGHT_NPS": "float",
    "HEALTH_WEIGHT_DELIVERY": "float",
    "HEALTH_WEIGHT_BUDGET": "float",
    "HEALTH_WEIGHT_TICKETS": "float",
    "HEALTH_WEIGHT_PORTAL": "float",
    "HEALTH_THRESHOLD_EXCELLENT": "float",
    "HEALTH_THRESHOLD_GOOD": "float",
    "HEALTH_THRESHOLD_AT_RISK": "float",
}

#: Orden y peso de cada componente.
COMPONENTES = (
    ("nps", "HEALTH_WEIGHT_NPS"),
    ("delivery", "HEALTH_WEIGHT_DELIVERY"),
    ("budget", "HEALTH_WEIGHT_BUDGET"),
    ("ticket_resolution", "HEALTH_WEIGHT_TICKETS"),
    ("portal_activity", "HEALTH_WEIGHT_PORTAL"),
)


# ── Funciones puras (sin base de datos; las prueban los tests unitarios) ──────

def nps_de_puntuaciones(puntuaciones: Iterable[int]) -> Optional[float]:
    """NPS clásico: % promotores (9-10) − % detractores (0-6). ``None`` sin respuestas."""
    lista = [p for p in puntuaciones if p is not None]
    if not lista:
        return None
    promotores = sum(1 for p in lista if p >= 9)
    detractores = sum(1 for p in lista if p <= 6)
    return round((promotores - detractores) / len(lista) * 100, 1)


def hito_evaluable(h, desde, hoy) -> Optional[bool]:
    """``True`` a tiempo, ``False`` fuera de plazo, ``None`` si no cuenta en la ventana."""
    if not h.is_active or h.due_date is None:
        return None
    if h.is_completed:
        if h.completed_date is None:
            return None                      # completado sin fecha: no medible
        if not (desde <= h.completed_date <= hoy) and not (desde <= h.due_date <= hoy):
            return None
        return h.completed_date <= h.due_date
    if desde <= h.due_date < hoy:
        return False                         # vencido y sin completar
    return None                              # aún no vence


def componer(valores: Dict[str, Optional[float]], pesos: Dict[str, float],
             por_defecto: float) -> tuple[float, Dict[str, float], float]:
    """Media ponderada con reparto del peso de los componentes sin datos.

    Devuelve ``(puntuación, pesos_efectivos, cobertura)``. Sin ningún componente
    con datos (o con peso 0 todos los medidos): ``por_defecto`` y cobertura 0.
    """
    pesos = {k: max(0.0, float(w or 0)) for k, w in pesos.items()}
    total = sum(pesos.values())
    medidos = {k: v for k, v in valores.items() if v is not None}
    peso_medido = sum(pesos.get(k, 0.0) for k in medidos)
    if not medidos or peso_medido <= 0:
        return float(por_defecto), {k: 0.0 for k in pesos}, 0.0
    efectivos = {k: (pesos[k] / peso_medido if k in medidos else 0.0) for k in pesos}
    puntuacion = sum(medidos[k] * efectivos[k] for k in medidos)
    cobertura = round(peso_medido / total, 4) if total > 0 else 0.0
    return round(max(0.0, min(100.0, puntuacion)), 1), efectivos, cobertura


def categoria(puntuacion: float, s, con_datos: bool = True) -> str:
    if not con_datos:
        return "no_data"
    return ("excellent" if puntuacion >= s.HEALTH_THRESHOLD_EXCELLENT else
            "good" if puntuacion >= s.HEALTH_THRESHOLD_GOOD else
            "at_risk" if puntuacion >= s.HEALTH_THRESHOLD_AT_RISK else
            "critical")


# ── Medidas (una consulta o un bloque por componente) ─────────────────────────

def _medir_nps(db: Session, client_id: str, desde) -> Dict[str, Any]:
    puntuaciones = [s for (s,) in db.query(ClientNPS.score).filter(
        ClientNPS.client_id == client_id,
        ClientNPS.created_at >= desde,
        or_(ClientNPS.survey_type == "nps", ClientNPS.survey_type.is_(None)),
    ).all()]
    nps = nps_de_puntuaciones(puntuaciones)
    return {"value": None if nps is None else round((nps + 100) / 2, 1),
            "responses": len(puntuaciones), "raw_nps": nps}


def _proyectos_del_cliente(db: Session, client_id: str) -> list:
    from app.models.project import Project, ProjectStatus
    return db.query(Project).filter(
        Project.client_id == client_id,
        Project.is_active.is_(True),
        Project.status != ProjectStatus.cancelled,
    ).all()


def _medir_entrega(db: Session, proyectos: list, desde, hoy) -> Dict[str, Any]:
    from app.models.financial import ProjectMilestone
    if not proyectos:
        return {"value": None, "evaluated": 0, "on_time": 0}
    hitos = db.query(ProjectMilestone).filter(
        ProjectMilestone.project_id.in_([p.id for p in proyectos]),
        ProjectMilestone.is_active.is_(True),
        ProjectMilestone.due_date.isnot(None),
    ).all()
    resultados = [r for r in (hito_evaluable(h, desde, hoy) for h in hitos) if r is not None]
    a_tiempo = sum(1 for r in resultados if r)
    return {"value": round(a_tiempo / len(resultados) * 100, 1) if resultados else None,
            "evaluated": len(resultados), "on_time": a_tiempo}


def _medir_presupuesto(db: Session, proyectos: list) -> Dict[str, Any]:
    from app.models.project import ProjectStatus
    from app.services.margen_de_proyectos import margen_en_bloque
    en_curso = (ProjectStatus.active, ProjectStatus.on_hold, ProjectStatus.paused)
    con_presupuesto = [p for p in proyectos
                       if p.status in en_curso and p.budget_amount is not None and p.budget_amount > 0]
    if not con_presupuesto:
        return {"value": None, "projects": 0, "within_budget": 0}
    cifras = margen_en_bloque(db, con_presupuesto)
    dentro = sum(1 for p in con_presupuesto if cifras[p.id]["total_cost"] <= float(p.budget_amount))
    return {"value": round(dentro / len(con_presupuesto) * 100, 1),
            "projects": len(con_presupuesto), "within_budget": dentro}


def _medir_tickets(db: Session, client_id: str, desde) -> Dict[str, Any]:
    from app.models.service_desk import Ticket
    from app.models.service_desk._enums import ESTADOS_DE_TICKET_ABIERTOS, ESTADOS_DE_TICKET_RESUELTOS
    resueltos = db.query(Ticket.sla_resolution_breached).filter(
        Ticket.client_id == client_id,
        Ticket.status.in_(ESTADOS_DE_TICKET_RESUELTOS),
        func.coalesce(Ticket.resolved_at, Ticket.closed_at, Ticket.created_at) >= desde,
    ).all()
    abiertos_incumplidos = db.query(func.count(Ticket.id)).filter(
        Ticket.client_id == client_id,
        Ticket.status.in_(ESTADOS_DE_TICKET_ABIERTOS),
        Ticket.sla_resolution_breached.is_(True),
    ).scalar() or 0
    en_plazo = sum(1 for (b,) in resueltos if not b)
    evaluados = len(resueltos) + abiertos_incumplidos
    return {"value": round(en_plazo / evaluados * 100, 1) if evaluados else None,
            "resolved": len(resueltos), "within_sla": en_plazo, "open_breached": abiertos_incumplidos}


def _medir_portal(db: Session, client_id: str, desde, s) -> Dict[str, Any]:
    # `ClientSession.client_id` apunta a `client_users.id`; la cadena es
    # Client.id <- ClientUser.client_org_id <- ClientSession.client_id.
    from app.models.client_portal import ClientSession, ClientUser
    usuarios = db.query(func.count(ClientUser.id)).filter(ClientUser.client_org_id == client_id).scalar() or 0
    if not usuarios:
        return {"value": None, "portal_users": 0, "sessions": 0}
    sesiones = (db.query(func.count(ClientSession.id))
                .join(ClientUser, ClientUser.id == ClientSession.client_id)
                .filter(ClientUser.client_org_id == client_id, ClientSession.created_at >= desde)
                .scalar() or 0)
    valor = min(100.0, float(s.HEALTH_PORTAL_BASE_SCORE) + sesiones * float(s.HEALTH_PORTAL_SCORE_PER_SESSION))
    return {"value": round(valor, 1), "portal_users": usuarios, "sessions": sesiones}


# ── Cálculo público ───────────────────────────────────────────────────────────

def compute_composite_health(client_id: str, db: Session) -> dict:
    """Salud compuesta del cliente (ver docstring del módulo). 404 si no existe en la empresa."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise error(404, "no_encontrado", detail="Client not found", que="cliente")

    s = get_runtime_namespace(db, _HEALTH_KEYS, org_id=client.organization_id)
    ahora = utcnow()
    hoy = ahora.date()
    desde_nps = ahora - timedelta(days=s.HEALTH_NPS_LOOKBACK_DAYS)
    desde_tickets = ahora - timedelta(days=s.HEALTH_TICKET_LOOKBACK_DAYS)

    proyectos = _proyectos_del_cliente(db, client_id)
    medidas = {
        "nps": _medir_nps(db, client_id, desde_nps),
        "delivery": _medir_entrega(db, proyectos, desde_nps.date(), hoy),
        "budget": _medir_presupuesto(db, proyectos),
        "ticket_resolution": _medir_tickets(db, client_id, desde_tickets),
        "portal_activity": _medir_portal(db, client_id, desde_tickets, s),
    }
    pesos = {k: getattr(s, clave) for k, clave in COMPONENTES}
    valores = {k: medidas[k]["value"] for k, _ in COMPONENTES}
    compuesta, efectivos, cobertura = componer(valores, pesos, s.HEALTH_DEFAULT_NO_DATA)
    con_datos = cobertura > 0

    components: Dict[str, Any] = {}
    for k, _ in COMPONENTES:
        components[k] = {**medidas[k], "weight": pesos[k], "effective_weight": round(efectivos[k], 4),
                         "has_data": valores[k] is not None}

    return {
        "client_id": client_id,
        "composite_score": compuesta,
        "category": categoria(compuesta, s, con_datos),
        "has_data": con_datos,
        "data_coverage": cobertura,
        "components": components,
        "computed_at": ahora.isoformat(),
    }


def actividad_combinada(components: Dict[str, Any]) -> Optional[float]:
    """Tickets + portal en una sola cifra (columna ``activity_component`` de la foto).

    Media ponderada por sus pesos configurados entre los que tienen datos;
    ``None`` si ninguno tiene.
    """
    partes = [(components[k]["value"], max(0.0, float(components[k]["weight"] or 0)))
              for k in ("ticket_resolution", "portal_activity") if components[k]["has_data"]]
    peso = sum(w for _, w in partes)
    if not partes or peso <= 0:
        return None
    return round(sum(v * w for v, w in partes) / peso, 1)


def nota_de_foto(resultado: dict) -> str:
    """Nota neutra de idioma con lo que no cabe en las columnas de la foto."""
    c = resultado["components"]
    sin = [k for k, _ in COMPONENTES if not c[k]["has_data"]]
    return ("auto; tickets={t}; portal={p}; no_data={n}; coverage={cov}".format(
        t=c["ticket_resolution"]["value"] if c["ticket_resolution"]["has_data"] else "-",
        p=c["portal_activity"]["value"] if c["portal_activity"]["has_data"] else "-",
        n=",".join(sin) or "-", cov=resultado["data_coverage"]))
