import logging
import json
from datetime import date
from app.core.timeutil import utcnow
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_any_manager
from app.core.responses import APIResponse
from app.models.user import User
from app.services import salesforce_service

router = APIRouter(tags=["Integrations", "Salesforce"])

STAGE_MAP = {
    "Prospecting": "lead",
    "Qualification": "qualification",
    "Needs Analysis": "qualification",
    "Value Proposition": "proposal",
    "Id. Decision Makers": "proposal",
    "Perception Analysis": "negotiation",
    "Proposal/Price Quote": "proposal",
    "Negotiation/Review": "negotiation",
    "Closed Won": "won",
    "Closed Lost": "lost",
}


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
    from app.core.encryption import decrypt_value

    org_id = getattr(current_user, "organization_id", None)

    inst = salesforce_service.get_salesforce_instance(db, instance_id, org_id)
    if not inst:
        raise HTTPException(404, "Salesforce integration instance not found or disabled")

    conn = salesforce_service.get_salesforce_connector(db, inst.connector_id)
    if not conn:
        raise HTTPException(400, "This instance is not a Salesforce connector")

    try:
        config = json.loads(decrypt_value(inst.encrypted_config) if inst.encrypted_config else "{}")
    except Exception:
        logging.getLogger(__name__).debug("sync_salesforce_opportunities: excepcion ignorada", exc_info=True)
        config = {}

    sf_base = config.get("instance_url", "")
    access_token = config.get("access_token", "")
    if not sf_base or not access_token:
        raise HTTPException(
            503,
            "Salesforce credentials incomplete. Configure instance_url and access_token "
            "in the integration settings.",
        )

    synced_in = 0
    synced_out = 0
    errors: List[str] = []

    if direction in ("inbound", "bidirectional"):
        import httpx

        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(
                    f"{sf_base}/services/data/v57.0/query",
                    params={
                        "q": "SELECT Id,Name,Amount,StageName,CloseDate,AccountId FROM Opportunity WHERE IsClosed=false LIMIT 200"
                    },
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                resp.raise_for_status()
                sf_opps = resp.json().get("records", [])
        except Exception as exc:
            logging.getLogger(__name__).warning("sync_salesforce_opportunities: excepcion ignorada", exc_info=True)
            errors.append(f"Salesforce API error: {exc}")
            sf_opps = []

        for sf_opp in sf_opps:
            mapped_stage = STAGE_MAP.get(sf_opp.get("StageName", ""), "lead")

            try:
                close_date = date.fromisoformat(sf_opp["CloseDate"]) if sf_opp.get("CloseDate") else None
            except ValueError:
                close_date = None

            salesforce_service.upsert_opportunity(db, sf_opp, mapped_stage, close_date)
            synced_in += 1

        if sf_opps:
            salesforce_service.commit_opportunities(db)

    salesforce_service.update_instance_sync_status(db, inst, synced_in + synced_out, errors)

    return APIResponse.ok(data={
        "ok": not errors,
        "direction": direction,
        "synced_inbound": synced_in,
        "synced_outbound": synced_out,
        "errors": errors,
        "synced_at": str(utcnow()),
    })
