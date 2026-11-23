from fastapi import APIRouter, Depends, BackgroundTasks, Query, Response
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import (
    get_current_user,
    requiere_capacidad,
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
from app.core.constantes import MAX_TAMANO_DE_PAGINA

router = APIRouter()


# ── API Endpoints ─────────────────────────────────────────────────────────────

@router.get("", response_model=APIListResponse[AlertOut], summary="Listar alertas activas")
def list_alerts(
    resolved: bool = False,
    severity: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = get_alerts_query(db, resolved, severity, current_user)
    items, total, _ = paginate_query(q, page, page_size, response)
    # Revisión 2026-11: la unidad de cada tipo sale de su configuración (antes la pantalla
    # ponía € a los presupuestos, que son %, y % a los plazos, que son días).
    from app.services.alert_service import unidades_por_tipo
    unidades = unidades_por_tipo(db)
    from app.services.textos_guardados import pintar_campo, idioma_del_lector
    idioma = idioma_del_lector(db)   # migracion 200: titulo y descripcion en el idioma de quien mira
    salida = [{**AlertOut.model_validate(a, from_attributes=True).model_dump(),
               "title": pintar_campo(a, "title", idioma=idioma),
               "description": pintar_campo(a, "description", idioma=idioma),
               "unit": unidades.get(str(getattr(a.alert_type, "value", a.alert_type)))} for a in items]
    return APIListResponse.ok(items=salida, total=total, page=page, page_size=page_size)


@router.post("/run", summary="Ejecutar motor de alertas manualmente")
def run_alert_engine(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(requiere_capacidad("alertas.administrar")),
):
    result = svc_run_alert_engine(db)
    return APIResponse.ok(data={"message": f"Motor de alertas ejecutado. {result['alerts_generated']} nuevas alertas generadas."})


@router.patch("/{alert_id}/read", summary="Marcar alerta como leída")
def mark_read(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(requiere_capacidad("alertas.usar")),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    enforce_abac(db, current_user, "alert", alert_id, action="update")
    mark_alert_read(db, alert_id, current_user)
    return APIResponse.ok(data={"ok": True})


@router.patch("/{alert_id}/resolve", summary="Resolver alerta")
def resolve_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("alertas.gestionar")),
):
    enforce_abac(db, current_user, "alert", alert_id, action="update")
    svc_resolve_alert(db, alert_id, current_user.id, current_user)
    return APIResponse.ok(data={"ok": True})
