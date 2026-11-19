"""
Customer NPS + Health Trend endpoints.

Routes:
  POST /nps/{client_id}/responses          — submit NPS score
  GET  /nps/{client_id}/responses          — list NPS history for a client
  GET  /nps/{client_id}/summary            — NPS score summary + trend
  POST /nps/{client_id}/health-snapshot    — record a health snapshot (admin/pm)
  GET  /nps/{client_id}/health             — health history for a client
  GET  /nps/health/trend                   — aggregate health trend across all clients
  GET  /nps/leaderboard                    — top/bottom clients by health score
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_any_manager
from app.core.periodo import CON_HORA, Periodo, periodo
from app.core.responses import APIResponse, APIListResponse
from app.models.user import User, UserRole
from app.services import nps_service
from app.core.constantes import MAX_TAMANO_DE_PAGINA
from app.core.codigos_de_error import error_http

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────

class NPSCreate(BaseModel):
    score:      int = Field(..., ge=0, le=10)
    comment:    Optional[str] = None
    respondent: Optional[str] = None
    source:     str = "manual"


class HealthSnapshotCreate(BaseModel):
    health_score:        float = Field(..., ge=0, le=100)
    nps_component:       Optional[float] = None
    delivery_component:  Optional[float] = None
    budget_component:    Optional[float] = None
    activity_component:  Optional[float] = None
    note:                Optional[str] = None


# ── NPS Routes ───────────────────────────────────────────────────────────

@router.post("/{client_id}/responses", status_code=201)
def submit_nps(
    client_id: str,
    body: NPSCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    _rol: User = Depends(require_any_manager),  # auditoria 2026-09: dominio: salud y satisfaccion de cliente
):
    if not nps_service.client_exists(db, client_id):
        raise error_http(404, "no_encontrado", detail="Cliente no encontrado", que="cliente")

    entry = nps_service.create_nps_entry(
        db,
        client_id  = client_id,
        score      = body.score,
        comment    = body.comment,
        respondent = body.respondent,
        source     = body.source,
    )
    return APIResponse.ok(data={
        "id":        entry.id,
        "score":     entry.score,
        "category":  entry.category,
        "created_at":entry.created_at,
    })


@router.get("/{client_id}/responses")
def list_nps_responses(
    client_id: str,
    limit: int = Query(50, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = nps_service.list_nps_responses(db, client_id, limit)
    return APIListResponse.ok(items=[
        {
            "id":        r.id,
            "score":     r.score,
            "category":  r.category,
            "comment":   r.comment,
            "respondent":r.respondent,
            "source":    r.source,
            "created_at":r.created_at,
        }
        for r in rows
    ])


@router.get("/{client_id}/summary")
def client_nps_summary(
    client_id: str,
    p: Periodo = Depends(periodo(dias_por_defecto=90, granularidades=CON_HORA, serie=True,
                                 alias_dias=("days",), dias_alias_max=365)),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    # Periodo libre (16-11-2026): respuestas con instante -> admite hora. La
    # tendencia sigue p.granularidad (antes, siempre mensual).
    responses = nps_service.get_nps_responses_in_period(db, client_id, p)
    summary   = nps_service.compute_nps_summary(responses, p)
    return APIResponse.ok(data={**summary, "days": p.dias_enteros, "periodo": p.a_dict()})


# ── Health Snapshot Routes ────────────────────────────────────────────────

@router.post("/{client_id}/health-snapshot", status_code=201)
def create_health_snapshot(
    client_id: str,
    body: HealthSnapshotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_any_manager),  # auditoria 2026-09: dominio: salud y satisfaccion de cliente
):
    if current_user.role not in (UserRole.admin, UserRole.pm):
        raise error_http(403, "solo_admin_o_pm", detail="Solo admins/PMs pueden crear snapshots")
    if not nps_service.client_exists(db, client_id):
        raise error_http(404, "no_encontrado", detail="Cliente no encontrado", que="cliente")

    snap = nps_service.create_health_snapshot(
        db,
        client_id           = client_id,
        health_score        = body.health_score,
        nps_component       = body.nps_component,
        delivery_component  = body.delivery_component,
        budget_component    = body.budget_component,
        activity_component  = body.activity_component,
        note                = body.note,
    )
    return APIResponse.ok(data={"id": snap.id, "health_score": snap.health_score, "snapshot_at": snap.snapshot_at})


@router.post("/{client_id}/health-compute", status_code=201)
def auto_compute_health(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_any_manager),  # auditoria 2026-09: dominio: salud y satisfaccion de cliente
):
    """Auto-compute health score from current data signals and save a snapshot."""
    if current_user.role not in (UserRole.admin, UserRole.pm):
        raise error_http(403, "solo_admin_o_pm", detail="Solo admins/PMs pueden computar salud")
    if not nps_service.client_exists(db, client_id):
        raise error_http(404, "no_encontrado", detail="Cliente no encontrado", que="cliente")

    snap = nps_service.compute_and_save_health(db, client_id)
    return APIResponse.ok(data={"id": snap.id, "health_score": snap.health_score, "snapshot_at": snap.snapshot_at})


@router.get("/{client_id}/health")
def client_health_history(
    client_id: str,
    limit: int = Query(30, le=120),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = nps_service.get_health_history(db, client_id, limit)
    return APIListResponse.ok(items=[
        {
            "id":                 r.id,
            "health_score":       r.health_score,
            "nps_component":      r.nps_component,
            "delivery_component": r.delivery_component,
            "budget_component":   r.budget_component,
            "activity_component": r.activity_component,
            "note":               r.note,
            "snapshot_at":        r.snapshot_at,
        }
        for r in rows
    ])


# ── Cross-client trend + leaderboard ─────────────────────────────────────

@router.get("/health/trend")
def health_trend_all(
    p: Periodo = Depends(periodo(dias_por_defecto=90, granularidades=CON_HORA, serie=True,
                                 alias_dias=("days",), dias_alias_max=365)),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Salud media de todos los clientes por tramo del periodo.

    Periodo libre (16-11-2026): antes siempre por semana (``week`` ``%Y-W%W``)
    y solo semanas con datos; ahora por ``p.granularidad`` con todos los tramos
    (``t`` ISO, ``avg_health`` ``None`` sin fotos).
    """
    rows = nps_service.get_health_trend_in_period(db, p)
    return APIListResponse.ok(items=nps_service.health_trend_series(rows, p))


@router.get("/leaderboard")
def health_leaderboard(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return latest health score per client, ordered best-to-worst."""
    rows = nps_service.get_health_leaderboard(db)
    return APIListResponse.ok(items=[
        {
            "client_id":    snap.client_id,
            "client_name":  name,
            "health_score": snap.health_score,
            "snapshot_at":  snap.snapshot_at,
        }
        for snap, name in rows
    ])
