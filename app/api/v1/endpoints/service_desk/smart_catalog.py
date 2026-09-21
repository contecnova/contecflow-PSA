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


def _render_context(ticket, current_user, service_item_id: str) -> dict:
    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
        "ticket_title": ticket.title,
        "ticket_description": ticket.description,
        "service_item_id": service_item_id,
        "requester_name": ticket.requester_name or "",
        "requester_email": ticket.requester_email or "",
        "requester_user_id": ticket.requester_user_id or "",
        "assignee_user_id": ticket.assigned_to_user_id or "",
        "current_user_id": current_user.id,
        "project_id": ticket.project_id,
    }


def _execute_step(step: dict, context: dict) -> dict:
    from app.services import bookings_service as _provision_exec

    step_type = str(step.get("type", "")).lower()
    if step_type in {
        "provision_identity",
        "create_ad_user",
        "disable_ad_user",
        "assign_license",
        "revoke_license",
    }:
        cfg = dict(step)
        if step_type != "provision_identity":
            cfg["operation"] = step_type
        out = _provision_exec._execute_provision_action(cfg, context)
        return {"type": step_type, "provider": "ad", **out}

    if step_type in {"terraform", "terraform_apply", "terraform_destroy", "terraform_plan"}:
        cfg = dict(step)
        if step_type != "terraform":
            cfg["command"] = step_type.replace("terraform_", "")
        out = _provision_exec._execute_terraform_action(cfg, context)
        return {"type": step_type, "provider": "terraform", **out}

    if step_type in {"ansible", "ansible_playbook"}:
        out = _provision_exec._execute_ansible_action(step, context)
        return {"type": step_type, "provider": "ansible", **out}

    return {"type": step_type, "status": "unknown"}


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
    from datetime import datetime, timezone

    org_id = getattr(current_user, "organization_id", None)
    config = svc.configuracion_de_aprovisionamiento(db, service_item_id, org_id)

    if not config.get("enabled"):
        return APIResponse.ok(data={"status": "skipped", "reason": "Provisioning not enabled for this service"})

    from app.models.service_desk import Ticket

    ticket = org_scoped_or_404(db, Ticket, payload.ticket_id, current_user, detail="Ticket not found")

    steps_done = []
    context = _render_context(ticket, current_user, service_item_id)
    for step in config.get("steps", []):
        step_type = step.get("type", "")
        step_content = step.get("content", "")
        try:
            if step_type == "comment":
                svc.anotar_comentario_de_aprovisionamiento(
                    db, ticket, current_user, step_content,
                    nombre_del_bot=NOMBRE_DEL_BOT_DE_APROVISIONAMIENTO)
                steps_done.append({"type": step_type, "status": "ok"})
            elif step_type == "status_change":
                anterior = str(ticket.status)
                ticket.status = step.get("target_status", ticket.status)
                svc.anotar_en_el_historial_del_ticket(
                    db, ticket, current_user, campo="status",
                    valor_anterior=anterior, valor_nuevo=str(ticket.status))
                steps_done.append({"type": step_type, "status": "ok"})
            elif step_type == "assign_group":
                ticket.assigned_group = step.get("group", ticket.assigned_group)
                steps_done.append({"type": step_type, "status": "ok"})
            else:
                provider_result = _execute_step(step, context)
                step_ok = bool(provider_result.get("ok", False))
                steps_done.append({
                    "type": step_type,
                    "status": "ok" if step_ok else "error",
                    "provider": provider_result.get("provider"),
                    "result": provider_result,
                })

                svc.anotar_en_el_historial_del_ticket(
                    db, ticket, current_user, campo="provisioning_step",
                    valor_nuevo=svc.resumen_de_paso(step_type, provider_result))
        except Exception as exc:
            steps_done.append({"type": step_type, "status": "error", "error": str(exc)})

    if config.get("notify_on_provision"):
        svc.anotar_en_el_historial_del_ticket(
            db, ticket, current_user, campo="provisioning",
            valor_nuevo=(
                f"Auto-provisioned via service {service_item_id} "
                f"at {datetime.now(timezone.utc).isoformat()}"
            ))

    db.commit()
    return APIResponse.ok(data={
        "ticket_id": payload.ticket_id,
        "service_item_id": service_item_id,
        "steps_executed": steps_done,
        "status": "completed",
    })
