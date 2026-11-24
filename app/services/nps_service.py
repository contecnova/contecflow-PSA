"""Service layer for NPS and Client Health Snapshot operations."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.periodo import Periodo, filtro_de_periodo
from app.models.nps import ClientNPS, ClientHealthSnapshot, NPSCategory
from app.models.clients import Client, ClientStatus


#: Solo las respuestas NPS (0-10). Las CSAT (1-5) del portal interno viven en la
#: misma tabla (`survey_type = 'csat'`, rev. 193) y NO son NPS: antes entraban
#: en el resumen, el listado y la salud (medido 24-11-2026).
def solo_nps():
    return or_(ClientNPS.survey_type == "nps", ClientNPS.survey_type.is_(None))


# ── Internal helpers ──────────────────────────────────────────────────────

def _nps_category(score: int) -> NPSCategory:
    if score >= 9:
        return NPSCategory.promoter
    if score >= 7:
        return NPSCategory.passive
    return NPSCategory.detractor


def _compute_nps(responses: List[ClientNPS]) -> Optional[float]:
    if not responses:
        return None
    total = len(responses)
    promoters  = sum(1 for r in responses if r.category == NPSCategory.promoter)
    detractors = sum(1 for r in responses if r.category == NPSCategory.detractor)
    return round((promoters - detractors) / total * 100, 1)


# ── Public service functions ──────────────────────────────────────────────

def client_exists(db: Session, client_id: str) -> bool:
    return get_client(db, client_id) is not None


def get_client(db: Session, client_id: str) -> Optional[Client]:
    """El cliente en la empresa de la sesión (filtro de tenant) o ``None``."""
    return db.query(Client).filter(Client.id == client_id).first()


def create_nps_entry(
    db: Session,
    client_id: str,
    score: int,
    comment: Optional[str],
    respondent: Optional[str],
    source: str,
) -> ClientNPS:
    client = get_client(db, client_id)
    entry = ClientNPS(
        organization_id = client.organization_id if client else None,
        client_id  = client_id,
        score      = score,
        category   = _nps_category(score),
        comment    = comment,
        respondent = respondent,
        source     = source,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_nps_responses(db: Session, client_id: str, limit: int) -> List[ClientNPS]:
    return (
        db.query(ClientNPS)
        .filter(ClientNPS.client_id == client_id, solo_nps())
        .order_by(ClientNPS.created_at.desc())
        .limit(limit)
        .all()
    )


def get_nps_responses_since(db: Session, client_id: str, cutoff: datetime) -> List[ClientNPS]:
    return (
        db.query(ClientNPS)
        .filter(
            ClientNPS.client_id == client_id,
            ClientNPS.created_at >= cutoff,
            solo_nps(),
        )
        .order_by(ClientNPS.created_at)
        .all()
    )


def get_nps_responses_in_period(db: Session, client_id: str, p: Periodo) -> List[ClientNPS]:
    """Respuestas del cliente en ``[p.desde, p.hasta)`` (periodo libre, 16-11-2026)."""
    return (
        db.query(ClientNPS)
        .filter(ClientNPS.client_id == client_id, solo_nps(), filtro_de_periodo(ClientNPS.created_at, p))
        .order_by(ClientNPS.created_at)
        .all()
    )


def compute_nps_summary(responses: List[ClientNPS], p: Optional[Periodo] = None) -> dict:
    """Return NPS + breakdown dict; no db access needed.

    Con ``p`` la tendencia va por tramos del periodo (``t`` ISO, todos los
    tramos, ``nps`` ``None`` donde no hay respuestas: el NPS no se suma). Sin
    ``p``, mensual como antes.
    """
    nps        = _compute_nps(responses)
    promoters  = sum(1 for r in responses if r.category == NPSCategory.promoter)
    passives   = sum(1 for r in responses if r.category == NPSCategory.passive)
    detractors = sum(1 for r in responses if r.category == NPSCategory.detractor)

    if p is not None:
        por_tramo: dict = {}
        for r in responses:
            k = p.clave(r.created_at)
            if k is not None:
                por_tramo.setdefault(k, []).append(r)
        trend = p.rellenar({k: {"nps": _compute_nps(v), "count": len(v)} for k, v in por_tramo.items()},
                           vacio={"nps": None, "count": 0})
    else:
        monthly: dict = {}
        for r in responses:
            key = r.created_at.strftime("%Y-%m")
            monthly.setdefault(key, []).append(r)

        trend = [
            {"month": k, "nps": _compute_nps(v), "count": len(v)}
            for k, v in sorted(monthly.items())
        ]
    return {
        "nps":        nps,
        "total":      len(responses),
        "promoters":  promoters,
        "passives":   passives,
        "detractors": detractors,
        "trend":      trend,
    }


def create_health_snapshot(
    db: Session,
    client_id: str,
    health_score: float,
    nps_component: Optional[float],
    delivery_component: Optional[float],
    budget_component: Optional[float],
    activity_component: Optional[float],
    note: Optional[str],
    user=None,
) -> ClientHealthSnapshot:
    """Foto de salud introducida a mano. Queda en el registro de auditoría (quién y qué)."""
    client = get_client(db, client_id)
    snap = ClientHealthSnapshot(
        organization_id     = client.organization_id if client else None,
        client_id           = client_id,
        health_score        = health_score,
        nps_component       = nps_component,
        delivery_component  = delivery_component,
        budget_component    = budget_component,
        activity_component  = activity_component,
        note                = note,
    )
    db.add(snap)
    db.flush()
    _auditar_foto(db, user, snap, client, "manual")
    db.commit()
    db.refresh(snap)
    return snap


def compute_and_save_health(db: Session, client_id: str, user=None) -> ClientHealthSnapshot:
    """Calcula la salud con el cálculo ÚNICO y guarda la foto con TODOS sus componentes.

    Revisión 24-11-2026. Antes: entrega, presupuesto y actividad fijos a 70 (60 %
    del resultado inventado) y la foto sin componentes. Ahora:
    ``customer_health_service.compute_composite_health`` y, en la foto,
    ``nps_component``, ``delivery_component``, ``budget_component`` tal cual
    (``None`` = sin datos) y ``activity_component`` = tickets + portal
    combinados por sus pesos (la tabla no tiene columna para cada uno; el
    desglose va en ``note``). Quién recalcula queda en auditoría.
    """
    from app.services.customer_health_service import (
        actividad_combinada, compute_composite_health, nota_de_foto)
    client = get_client(db, client_id)
    r = compute_composite_health(client_id, db)
    c = r["components"]
    snap = ClientHealthSnapshot(
        organization_id     = client.organization_id if client else None,
        client_id           = client_id,
        health_score        = r["composite_score"],
        nps_component       = c["nps"]["value"],
        delivery_component  = c["delivery"]["value"],
        budget_component    = c["budget"]["value"],
        activity_component  = actividad_combinada(c),
        note                = nota_de_foto(r),
    )
    db.add(snap)
    db.flush()
    _auditar_foto(db, user, snap, client, "auto", extra={"category": r["category"],
                                                         "data_coverage": r["data_coverage"]})
    db.commit()
    db.refresh(snap)
    return snap


def _auditar_foto(db: Session, user, snap: ClientHealthSnapshot, client, origen: str,
                  extra: Optional[dict] = None) -> None:
    from app.services.audit import audit_log
    audit_log(db, user, "CREATE", "client_health_snapshot", str(snap.id),
              client.name if client else snap.client_id,
              new_values={"origin": origen, "client_id": snap.client_id, "health_score": snap.health_score,
                          "nps_component": snap.nps_component, "delivery_component": snap.delivery_component,
                          "budget_component": snap.budget_component,
                          "activity_component": snap.activity_component, **(extra or {})})


def get_health_history(db: Session, client_id: str, limit: int) -> List[ClientHealthSnapshot]:
    return (
        db.query(ClientHealthSnapshot)
        .filter(ClientHealthSnapshot.client_id == client_id)
        .order_by(ClientHealthSnapshot.snapshot_at.desc())
        .limit(limit)
        .all()
    )


def get_health_trend_in_period(db: Session, p: Periodo) -> List[ClientHealthSnapshot]:
    """Fotos de salud de todos los clientes en ``[p.desde, p.hasta)``."""
    return (
        db.query(ClientHealthSnapshot)
        .filter(filtro_de_periodo(ClientHealthSnapshot.snapshot_at, p))
        .order_by(ClientHealthSnapshot.snapshot_at)
        .all()
    )


def health_trend_series(rows: List[ClientHealthSnapshot], p: Periodo) -> List[dict]:
    """Salud media por tramo (media, no suma; ``None`` en tramos sin fotos)."""
    por_tramo: dict = {}
    for r in rows:
        k = p.clave(r.snapshot_at)
        if k is not None and r.health_score is not None:
            por_tramo.setdefault(k, []).append(r.health_score)
    return p.rellenar({k: {"avg_health": round(sum(v) / len(v), 1), "count": len(v)} for k, v in por_tramo.items()},
                      vacio={"avg_health": None, "count": 0})


def get_health_leaderboard(db: Session):
    """Última foto de cada cliente ACTIVO, de mejor a peor: ``[(foto, nombre)]``.

    Revisión 24-11-2026: antes, dos fotos con el mismo ``snapshot_at`` máximo
    salían duplicadas (se unía por fecha) y entraban clientes desactivados,
    inactivos o perdidos. Ahora la última foto es la de mayor ``id`` entre las de
    fecha máxima (una por cliente) y solo clientes con ``is_active`` y estado
    distinto de ``inactive``/``churned``. Empresa: filtro de tenant en las tres
    tablas (fotos, subconsultas y clientes).
    """
    ultima_fecha = (
        db.query(
            ClientHealthSnapshot.client_id.label("client_id"),
            func.max(ClientHealthSnapshot.snapshot_at).label("latest"),
        )
        .group_by(ClientHealthSnapshot.client_id)
        .subquery()
    )
    ultima_id = (
        db.query(func.max(ClientHealthSnapshot.id).label("id"))
        .join(ultima_fecha,
              (ClientHealthSnapshot.client_id == ultima_fecha.c.client_id)
              & (ClientHealthSnapshot.snapshot_at == ultima_fecha.c.latest))
        .group_by(ClientHealthSnapshot.client_id)
        .subquery()
    )
    return (
        db.query(ClientHealthSnapshot, Client.name)
        .join(ultima_id, ClientHealthSnapshot.id == ultima_id.c.id)
        .join(Client, Client.id == ClientHealthSnapshot.client_id)
        .filter(
            Client.is_active.is_not(False),
            or_(Client.status.is_(None), Client.status.notin_([ClientStatus.inactive, ClientStatus.churned])),
        )
        .order_by(ClientHealthSnapshot.health_score.desc(), Client.name)
        .all()
    )
