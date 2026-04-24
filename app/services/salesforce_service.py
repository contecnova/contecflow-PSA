"""Service layer for Salesforce sync operations."""
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy.orm import Session
from app.models.marketplace import IntegrationInstance
from app.models.marketplace import IntegrationConnector
from app.models.pipeline import Opportunity


def get_salesforce_instance(db: Session, instance_id: str, org_id: Optional[str]):
    """Return enabled IntegrationInstance for Salesforce, scoped to org."""

    return (
        db.query(IntegrationInstance)
        .filter(
            IntegrationInstance.id == instance_id,
            IntegrationInstance.organization_id == org_id,
            IntegrationInstance.is_enabled == True,
        )
        .first()
    )


def get_salesforce_connector(db: Session, connector_id: str):
    """Return IntegrationConnector with slug=='salesforce'."""

    return (
        db.query(IntegrationConnector)
        .filter(
            IntegrationConnector.id == connector_id,
            IntegrationConnector.slug == "salesforce",
        )
        .first()
    )


def find_opportunity_by_external_id(db: Session, sf_id: str):
    """Return existing Opportunity matched by external_id, or None."""

    if not hasattr(Opportunity, "external_id"):
        return None
    return db.query(Opportunity).filter(Opportunity.external_id == sf_id).first()


def upsert_opportunity(db: Session, sf_opp: dict, mapped_stage: str, close_date: Optional[date]) -> None:
    """Create or update a local Opportunity from a Salesforce record."""

    sf_id = sf_opp.get("Id")
    existing = find_opportunity_by_external_id(db, sf_id)

    if existing:
        existing.name = sf_opp.get("Name", existing.name)
        existing.expected_revenue = sf_opp.get("Amount") or existing.expected_revenue
        existing.stage = mapped_stage
        if close_date and hasattr(existing, "close_date"):
            existing.close_date = close_date
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


def commit_opportunities(db: Session) -> None:
    """Flush upserted opportunities to the database."""
    db.commit()


def update_instance_sync_status(
    db: Session, inst, records: int, errors: List[str]
) -> None:
    """Persist last-sync metadata on the IntegrationInstance."""
    inst.last_sync_at = datetime.utcnow()
    inst.last_sync_status = "error" if errors else "ok"
    inst.last_sync_records = records
    inst.last_error = "; ".join(errors) if errors else None
    db.commit()
