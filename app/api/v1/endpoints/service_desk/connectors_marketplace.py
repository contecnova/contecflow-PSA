"""Service Desk curated connectors marketplace (MVP).

Auditoria 2026-08 (hallazgo 22). Este fichero era una **segunda puerta** al
mismo marketplace que `/api/v1/integrations/*`, con sus propias consultas
escritas a mano, y era la peor de las dos: no validaba los parametros de
sincronizacion, no sembraba el catalogo y creaba instalaciones **sin
configuracion**, que quien las consume no puede usar. El detalle esta en la
cabecera de `app/services/marketplace_service.py`.

Las consultas viven ahi ahora, compartidas con la otra puerta. La forma de las
respuestas de estas tres rutas **no cambia**: son API publicada.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_any_manager
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services import marketplace_service as svc

router = APIRouter()


class ConnectorInstallIn(BaseModel):
    connector_id: str
    name: str = Field(..., min_length=1, max_length=100)
    sync_direction: str = "bidirectional"
    sync_frequency: str = "hourly"
    #: Auditoria 2026-08: no existia, asi que la instalacion se guardaba sin
    #: credenciales y la integracion nacia muerta. Es opcional para no romper a
    #: quien ya llamaba sin ella.
    config: dict | None = None


@router.get("/connectors/marketplace", summary="Marketplace curado de conectores Service Desk")
def list_connectors(
    category: str | None = Query(None),
    certified_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIListResponse.ok(items=svc.catalogo_para_service_desk(
        db, current_user, category=category, certified_only=certified_only))


@router.get("/connectors/installed", summary="Conectores instalados para la organización")
def list_installed_connectors(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIListResponse.ok(
        items=svc.instalados_para_service_desk(db, current_user))


@router.post("/connectors/install", summary="Instalar conector desde marketplace")
def install_connector(
    payload: ConnectorInstallIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    inst = svc.instalar_por_id(db, current_user, payload.model_dump())
    return APIResponse.ok(data={"ok": True, "instance_id": inst.id})
