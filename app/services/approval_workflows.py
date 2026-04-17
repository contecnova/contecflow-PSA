"""Shared approval workflow lookup helpers."""

from sqlalchemy.orm import Session
from app.models.billing_reports import ApprovalWorkflow


def find_default_workflow(entity_type: str, db: Session):

    return db.query(ApprovalWorkflow).filter(
        ApprovalWorkflow.entity_type == entity_type,
        ApprovalWorkflow.is_default == True,
        ApprovalWorkflow.is_active == True,
    ).first()
