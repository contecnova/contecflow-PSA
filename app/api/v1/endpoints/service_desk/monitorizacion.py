"""Service Desk — entrada de alertas de monitorizacion."""
from typing import Optional

from fastapi import APIRouter, Body, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk import monitoring_ingest as svc
from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback

router = APIRouter(tags=["Service Desk - Monitorización"])


@router.post("/events/{source}", summary="Recibir alertas (Alertmanager o formato genérico)")
def recibir(
    source: str,
    payload=Body(...),
    db: Session = Depends(get_db),
    x_contecflow_event_token: Optional[str] = Header(default=None),
):
    """Sin sesion: autentica el token de la organizacion (Credenciales > «Monitoring alerts»)."""
    org_id = svc.organizacion_del_token(db, x_contecflow_event_token)
    cuenta = svc.procesar(db, org_id, source[:50], svc.leer(payload))
    _commit_or_rollback(db)
    return APIResponse.ok(data=cuenta)


@router.get("/events/alerts", summary="Últimas alertas recibidas y su incidencia")
def ultimas(limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return APIListResponse.ok(items=svc.ultimas(db, limit))
