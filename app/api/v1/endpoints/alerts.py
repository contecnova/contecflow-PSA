from fastapi import APIRouter, Depends, BackgroundTasks, Query, Response
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin, require_any_manager
from app.models.user import User
from app.schemas.alerts import AlertOut
from app.services.pagination_service import paginate_query
from app.services.alert_service import (
    AlertEngine,
    get_alerts_query,
    mark_alert_read,
    resolve_alert as svc_resolve_alert,
    run_alert_engine as svc_run_alert_engine,
)

router = APIRouter()


# ── API Endpoints ─────────────────────────────────────────────────────────────

@router.get("", response_model=List[AlertOut], summary="Listar alertas activas")
def list_alerts(
    resolved: bool = False,
    severity: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = get_alerts_query(db, resolved, severity, current_user)
    items, _, _ = paginate_query(q, page, page_size, response)
    return items


@router.post("/run", summary="Ejecutar motor de alertas manualmente")
def run_alert_engine(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = svc_run_alert_engine(db)
    return {"message": f"Motor de alertas ejecutado. {result['alerts_generated']} nuevas alertas generadas."}


@router.patch("/{alert_id}/read", summary="Marcar alerta como leída")
def mark_read(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mark_alert_read(db, alert_id)
    return {"ok": True}


@router.patch("/{alert_id}/resolve", summary="Resolver alerta")
def resolve_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    svc_resolve_alert(db, alert_id, current_user.id)
    return {"ok": True}
