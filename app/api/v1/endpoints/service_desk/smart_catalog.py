"""Service Desk — Smart Service Catalog REST API.

ML-enhanced recommendations, dynamic form prefill, and provisioning automation.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.core.responses import APIResponse, APIListResponse
from app.core.tenancy import org_scoped_or_404
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk import smart_catalog_service as svc
from app.services.service_desk.smart_catalog_service import (
    auto_prefill_request_form,
    get_popular_services,
    get_smart_recommendations,
    suggest_service_for_query,
)


router = APIRouter(prefix="/catalog/smart", tags=["Smart Service Catalog"])

#: Con qué nombre firma el aprovisionamiento sus comentarios en el ticket.
#: Estaba en duro en medio del bucle de pasos.
NOMBRE_DEL_BOT_DE_APROVISIONAMIENTO = "Provisioning Bot"


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class SuggestIn(BaseModel):
    query: str
    use_ai: Optional[bool] = True


class PrefillIn(BaseModel):
    description: str
    service_id: Optional[str] = None


class ProvisioningConfigIn(BaseModel):
    enabled: bool = False
    steps: list[dict] = []
    auto_assign_group: Optional[str] = None
    notify_on_provision: bool = True
    notes: Optional[str] = None


class ProvisionIn(BaseModel):
    ticket_id: str
    service_item_id: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/popular", summary="Servicios más solicitados por volumen de tickets")
def get_popular(
    weeks: int = Query(4, ge=1, le=52),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIListResponse.ok(items=get_popular_services(db, weeks=weeks, limit=limit))


@router.get("/recommendations", summary="Recomendaciones personalizadas para el usuario actual")
def get_recommendations(
    query: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    recs = get_smart_recommendations(db, user_id=current_user.id, query=query, limit=limit)
    return APIResponse.ok(data={"recommendations": recs, "user_id": current_user.id})


@router.post("/suggest", summary="Sugerir servicio a partir de texto libre (IA + keywords)")
def suggest_service(
    payload: SuggestIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    return APIResponse.ok(data=suggest_service_for_query(db, query=payload.query, use_ai=payload.use_ai))


@router.post("/prefill", summary="Pre-relleno de formulario basado en descripción (ML/patrones)")
def prefill_form(
    payload: PrefillIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    return APIResponse.ok(data=auto_prefill_request_form(db, description=payload.description, service_id=payload.service_id))


@router.get("/services/{service_item_id}/provisioning", summary="Configuración de provisioning automatizado de un servicio")
def get_provisioning(
    service_item_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    config = svc.configuracion_de_aprovisionamiento(db, service_item_id, org_id)
    return APIResponse.ok(data={"service_item_id": service_item_id, "config": config})


@router.put("/services/{service_item_id}/provisioning", summary="Guardar configuración de provisioning automatizado")
def put_provisioning(
    service_item_id: str,
    payload: ProvisioningConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    org_id = getattr(current_user, "organization_id", None)
    svc.guardar_configuracion_de_aprovisionamiento(db, service_item_id, org_id, payload.model_dump())
    return APIResponse.ok(data={"service_item_id": service_item_id, "status": "saved"})


@router.post("/services/{service_item_id}/provision", summary="Disparar provisioning automático para un ticket")
def trigger_provisioning(
    service_item_id: str,
    payload: ProvisionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Execute automated provisioning steps for a service request ticket.

    Supports real external provisioning providers (AD/identity, Terraform,
    Ansible) plus local ticket mutations.
    """
    org_id = getattr(current_user, "organization_id", None)
    config = svc.configuracion_de_aprovisionamiento(db, service_item_id, org_id)

    if not config.get("enabled"):
        return APIResponse.ok(data={"status": "skipped", "reason": "Provisioning not enabled for this service"})

    from app.models.service_desk import Ticket

    ticket = org_scoped_or_404(db, Ticket, payload.ticket_id, current_user, detail="Ticket not found")

    steps_done = svc.ejecutar_pasos_de_aprovisionamiento(
        db, ticket, current_user, service_item_id, config,
        nombre_del_bot=NOMBRE_DEL_BOT_DE_APROVISIONAMIENTO)
    return APIResponse.ok(data={
        "ticket_id": payload.ticket_id,
        "service_item_id": service_item_id,
        "steps_executed": steps_done,
        "status": "completed",
    })
