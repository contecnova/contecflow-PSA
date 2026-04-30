"""Service Desk — Smart Service Catalog REST API.

ML-enhanced recommendations, dynamic form prefill, and provisioning automation.
"""
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.settings import AppSetting
from app.models.user import User
from app.services.service_desk.smart_catalog_service import (
    auto_prefill_request_form,
    get_popular_services,
    get_smart_recommendations,
    suggest_service_for_query,
)

import json

router = APIRouter(prefix="/catalog/smart", tags=["Smart Service Catalog"])


# ── AppSetting helpers ────────────────────────────────────────────────────────

_PROVISIONING_KEY_PREFIX = "sd.catalog.provisioning."


def _get_provisioning_config(db: Session, service_item_id: str, org_id: Optional[str]) -> dict:
    key = f"{_PROVISIONING_KEY_PREFIX}{service_item_id}"
    row = (
        db.query(AppSetting)
        .filter(AppSetting.key == key, AppSetting.organization_id == org_id)
        .first()
    )
    if not row or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except Exception:
        return {}


def _set_provisioning_config(db: Session, service_item_id: str, org_id: Optional[str], config: dict) -> None:
    key = f"{_PROVISIONING_KEY_PREFIX}{service_item_id}"
    row = (
        db.query(AppSetting)
        .filter(AppSetting.key == key, AppSetting.organization_id == org_id)
        .first()
    )
    payload = json.dumps(config, ensure_ascii=False)
    if not row:
        row = AppSetting(key=key, organization_id=org_id, value=payload,
                         description=f"Provisioning config for service {service_item_id}")
        db.add(row)
    else:
        row.value = payload
    db.commit()


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
    return {"items": get_popular_services(db, weeks=weeks, limit=limit)}


@router.get("/recommendations", summary="Recomendaciones personalizadas para el usuario actual")
def get_recommendations(
    query: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    recs = get_smart_recommendations(db, user_id=current_user.id, query=query, limit=limit)
    return {"recommendations": recs, "user_id": current_user.id}


@router.post("/suggest", summary="Sugerir servicio a partir de texto libre (IA + keywords)")
def suggest_service(
    payload: SuggestIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return suggest_service_for_query(db, query=payload.query, use_ai=payload.use_ai)


@router.post("/prefill", summary="Pre-relleno de formulario basado en descripción (ML/patrones)")
def prefill_form(
    payload: PrefillIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return auto_prefill_request_form(db, description=payload.description, service_id=payload.service_id)


@router.get("/services/{service_item_id}/provisioning", summary="Configuración de provisioning automatizado de un servicio")
def get_provisioning(
    service_item_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    config = _get_provisioning_config(db, service_item_id, org_id)
    return {"service_item_id": service_item_id, "config": config}


@router.put("/services/{service_item_id}/provisioning", summary="Guardar configuración de provisioning automatizado")
def put_provisioning(
    service_item_id: str,
    payload: ProvisioningConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    _set_provisioning_config(db, service_item_id, org_id, payload.model_dump())
    return {"service_item_id": service_item_id, "status": "saved"}


@router.post("/services/{service_item_id}/provision", summary="Disparar provisioning automático para un ticket")
def trigger_provisioning(
    service_item_id: str,
    payload: ProvisionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Execute automated provisioning steps for a service request ticket.

    Supports real external provisioning providers (AD/identity, Terraform,
    Ansible) plus local ticket mutations.
    """
    import uuid as _uuid
    from datetime import datetime, timezone

    org_id = getattr(current_user, "organization_id", None)
    config = _get_provisioning_config(db, service_item_id, org_id)

    if not config.get("enabled"):
        return {"status": "skipped", "reason": "Provisioning not enabled for this service"}

    from app.models.service_desk import Ticket, TicketHistory

    ticket = db.query(Ticket).filter(Ticket.id == payload.ticket_id).first()
    if not ticket:
        from fastapi import HTTPException
        raise HTTPException(404, "Ticket not found")

    steps_done = []
    context = _render_context(ticket, current_user, service_item_id)
    for step in config.get("steps", []):
        step_type = step.get("type", "")
        step_content = step.get("content", "")
        try:
            if step_type == "comment":
                from app.models.service_desk import TicketComment
                comment = TicketComment(
                    id=str(_uuid.uuid4()),
                    ticket_id=ticket.id,
                    body=step_content,
                    is_public=True,
                    is_solution=False,
                    author_user_id=current_user.id,
                    author_name="Provisioning Bot",
                )
                db.add(comment)
                steps_done.append({"type": step_type, "status": "ok"})
            elif step_type == "status_change":
                old = str(ticket.status)
                ticket.status = step.get("target_status", ticket.status)
                db.add(TicketHistory(
                    id=str(_uuid.uuid4()),
                    ticket_id=ticket.id,
                    field_name="status",
                    old_value=old,
                    new_value=str(ticket.status),
                    changed_by_user_id=current_user.id,
                ))
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

                db.add(TicketHistory(
                    id=str(_uuid.uuid4()),
                    ticket_id=ticket.id,
                    field_name="provisioning_step",
                    old_value=None,
                    new_value=json.dumps(
                        {
                            "type": step_type,
                            "ok": step_ok,
                            "provider": provider_result.get("provider"),
                            "status_code": provider_result.get("status_code"),
                            "exit_code": provider_result.get("exit_code"),
                        },
                        ensure_ascii=False,
                    )[:1000],
                    changed_by_user_id=current_user.id,
                ))
        except Exception as exc:
            steps_done.append({"type": step_type, "status": "error", "error": str(exc)})

    if config.get("notify_on_provision"):
        db.add(TicketHistory(
            id=str(_uuid.uuid4()),
            ticket_id=ticket.id,
            field_name="provisioning",
            old_value=None,
            new_value=f"Auto-provisioned via service {service_item_id} at {datetime.now(timezone.utc).isoformat()}",
            changed_by_user_id=current_user.id,
        ))

    db.commit()
    return {
        "ticket_id": payload.ticket_id,
        "service_item_id": service_item_id,
        "steps_executed": steps_done,
        "status": "completed",
    }
