import json
from datetime import date, datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_any_manager
from app.models.user import User

router = APIRouter(tags=["Integrations", "Salesforce"])


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
    from app.models.marketplace import IntegrationConnector, IntegrationInstance
    from app.models.pipeline import Opportunity

    org_id = getattr(current_user, "organization_id", None)
    inst = db.query(IntegrationInstance).filter(
        IntegrationInstance.id == instance_id,
        IntegrationInstance.organization_id == org_id,
        IntegrationInstance.is_enabled == True,
    ).first()
    if not inst:
        raise HTTPException(404, "Salesforce integration instance not found or disabled")

    conn = db.query(IntegrationConnector).filter(
        IntegrationConnector.id == inst.connector_id,
        IntegrationConnector.slug == "salesforce",
    ).first()
    if not conn:
        raise HTTPException(400, "This instance is not a Salesforce connector")

    try:
        config = json.loads(decrypt_value(inst.encrypted_config) if inst.encrypted_config else "{}")
    except Exception:
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
            errors.append(f"Salesforce API error: {exc}")
            sf_opps = []

        for sf_opp in sf_opps:
            sf_id = sf_opp.get("Id")
            existing_opp = (
                db.query(Opportunity).filter(Opportunity.external_id == sf_id).first()
                if hasattr(Opportunity, "external_id")
                else None
            )

            stage_map = {
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
            mapped_stage = stage_map.get(sf_opp.get("StageName", ""), "lead")

            try:
                close_date = date.fromisoformat(sf_opp["CloseDate"]) if sf_opp.get("CloseDate") else None
            except ValueError:
                close_date = None

            if existing_opp:
                existing_opp.name = sf_opp.get("Name", existing_opp.name)
                existing_opp.expected_revenue = sf_opp.get("Amount") or existing_opp.expected_revenue
                existing_opp.stage = mapped_stage
                if close_date and hasattr(existing_opp, "close_date"):
                    existing_opp.close_date = close_date
            else:
                new_opp = Opportunity(
                    name=sf_opp.get("Name", "Imported from Salesforce"),
                    client_name=sf_opp.get("AccountId", "Salesforce Account"),
                    stage=mapped_stage,
                    expected_revenue=sf_opp.get("Amount") or 0,
                )
                if hasattr(new_opp, "external_id"):
                    new_opp.external_id = sf_id
                if close_date and hasattr(new_opp, "close_date"):
                    new_opp.close_date = close_date
                db.add(new_opp)
            synced_in += 1

        if sf_opps:
            db.commit()

    inst.last_sync_at = datetime.utcnow()
    inst.last_sync_status = "error" if errors else "ok"
    inst.last_sync_records = synced_in + synced_out
    inst.last_error = "; ".join(errors) if errors else None
    db.commit()

    return {
        "ok": not errors,
        "direction": direction,
        "synced_inbound": synced_in,
        "synced_outbound": synced_out,
        "errors": errors,
        "synced_at": str(datetime.utcnow()),
    }
