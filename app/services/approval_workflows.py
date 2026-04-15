"""Shared approval workflow lookup helpers."""

from sqlalchemy.orm import Session


def find_default_workflow(entity_type: str, db: Session):
    from app.models.billing_reports import ApprovalWorkflow

    return db.query(ApprovalWorkflow).filter(
        ApprovalWorkflow.entity_type == entity_type,
        ApprovalWorkflow.is_default == True,
        ApprovalWorkflow.is_active == True,
    ).first()
