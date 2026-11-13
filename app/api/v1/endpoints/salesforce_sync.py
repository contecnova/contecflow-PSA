from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_any_manager
from app.core.responses import APIResponse
from app.models.user import User
from app.services import salesforce_service

router = APIRouter(tags=["Integrations", "Salesforce"])

# Se conserva el nombre: la tabla vive ahora en el servicio.
STAGE_MAP = salesforce_service.STAGE_MAP


@router.post(
    "/integrations/salesforce/sync-opportunities",
    summary="Sync Salesforce opportunities -> Pipeline",
)
def sync_salesforce_opportunities(
    instance_id: str = Query(..., description="IntegrationInstance ID for Salesforce"),
    direction: str = Query(default="inbound", description="inbound|outbound|bidirectional"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    org_id = getattr(current_user, "organization_id", None)
    # Las comprobaciones (instancia, conector, credenciales) siguen en la
    # peticion: sus 404/400/503 los necesita quien pulsa el boton.
    salesforce_service.preparar_sincronizacion(db, instance_id, org_id)

    # Segunda auditoria 2026-11 (n.º 20): la consulta a Salesforce (20 s) y el
    # volcado al pipeline van al worker. Con cola: 202 `{status: "queued"}`;
    # el resultado queda en el estado de sincronizacion de la instancia. Las
    # credenciales no viajan por la cola: el worker las vuelve a leer.
    from app.core.segundo_plano import EN_COLA, encolar, respuesta_en_cola
    resultado = encolar(salesforce_service.sincronizar_oportunidades,
                        instance_id=instance_id, direction=direction, org_id=org_id,
                        _organizacion=org_id, _sesion=db)
    if resultado is EN_COLA:
        return respuesta_en_cola(direction=direction)
    return APIResponse.ok(data=resultado)
