from fastapi import APIRouter, Depends, BackgroundTasks, Query, Response
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import (
    get_current_user,
    require_admin,
    require_any_manager,
    require_internal_user,
)
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.schemas.alerts import AlertOut
from app.services.pagination_service import paginate_query
from app.services.alert_service import (
    get_alerts_query,
    mark_alert_read,
    resolve_alert as svc_resolve_alert,
    run_alert_engine as svc_run_alert_engine,
)

router = APIRouter()


# ── API Endpoints ─────────────────────────────────────────────────────────────

@router.get("", response_model=APIListResponse[AlertOut], summary="Listar alertas activas")
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
    items, total, _ = paginate_query(q, page, page_size, response)
    # Revisión 2026-11: la unidad de cada tipo sale de su configuración (antes la pantalla
    # ponía € a los presupuestos, que son %, y % a los plazos, que son días).
    from app.models.advanced_config import AlertConfig
    from app.services.advanced_config_service import DEFAULT_ALERT_CONFIGS
    unidades = {d[0]: d[4] for d in DEFAULT_ALERT_CONFIGS}
    unidades.update({c.alert_type: c.threshold_unit for c in db.query(AlertConfig).all() if c.threshold_unit})
    salida = [{**AlertOut.model_validate(a, from_attributes=True).model_dump(),
               "unit": unidades.get(str(getattr(a.alert_type, "value", a.alert_type)))} for a in items]
    return APIListResponse.ok(items=salida, total=total, page=page, page_size=page_size)


@router.post("/run", summary="Ejecutar motor de alertas manualmente")
def run_alert_engine(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = svc_run_alert_engine(db)
    return APIResponse.ok(data={"message": f"Motor de alertas ejecutado. {result['alerts_generated']} nuevas alertas generadas."})


@router.patch("/{alert_id}/read", summary="Marcar alerta como leída")
def mark_read(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    enforce_abac(db, current_user, "alert", alert_id, action="update")
    mark_alert_read(db, alert_id, current_user)
    return APIResponse.ok(data={"ok": True})


@router.patch("/{alert_id}/resolve", summary="Resolver alerta")
def resolve_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "alert", alert_id, action="update")
    svc_resolve_alert(db, alert_id, current_user.id, current_user)
    return APIResponse.ok(data={"ok": True})
