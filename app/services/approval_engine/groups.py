"""approval_engine.groups — extracted from the former 1827-LOC god-file."""

from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from collections import defaultdict
from sqlalchemy.orm import Session, joinedload
from app.models.user import User
from app.models.billing_reports import FinancialApprovalAuditLog
from app.models.billing_reports import ApprovalRequest
from app.models.billing_reports import ApprovalWorkflow
from app.models.billing_reports import ApprovalDecision
from app.models.billing_reports import ApprovalStep
from app.models.billing_reports import ApprovalGroup
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import func


def list_approval_groups(db: Session) -> list:
    return db.query(ApprovalGroup).order_by(ApprovalGroup.name).all()

def get_approval_group(db: Session, group_id: str):
    return db.query(ApprovalGroup).filter(ApprovalGroup.id == group_id).first()

def create_approval_group(db: Session, name: str, description: Optional[str], member_ids: list, created_by: str):
    g = ApprovalGroup(
        id=str(uuid.uuid4()),
        name=name,
        description=description,
        member_ids=json.dumps(member_ids),
        created_by=created_by,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g

def update_approval_group(db: Session, group_id: str, name: Optional[str], description: Optional[str], member_ids: Optional[list]):
    g = db.query(ApprovalGroup).filter(ApprovalGroup.id == group_id).first()
    if not g:
        return None
    if name is not None:
        g.name = name
    if description is not None:
        g.description = description
    if member_ids is not None:
        g.member_ids = json.dumps(member_ids)
    db.commit()
    db.refresh(g)
    return g

def delete_approval_group(db: Session, group_id: str) -> bool:
    g = db.query(ApprovalGroup).filter(ApprovalGroup.id == group_id).first()
    if not g:
        return False
    db.delete(g)
    db.commit()
    return True

def serialize_approval_group(g) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "description": g.description,
        "member_ids": json.loads(g.member_ids or "[]"),
        "created_by": g.created_by,
        "created_at": str(g.created_at)[:16] if g.created_at else None,
    }
