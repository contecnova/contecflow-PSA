import json
from typing import Optional

from sqlalchemy.orm import Session

from app.models.billing_reports import ImportJob, WorkflowExecution
from app.services.pagination_service import ConCabeceras, paginate_query
import logging

logger = logging.getLogger(__name__)


def get_import_jobs(db: Session, page: int, page_size: int, response: Optional[ConCabeceras] = None) -> list[dict]:
    q = db.query(ImportJob).order_by(ImportJob.started_at.desc())
    jobs, _, _ = paginate_query(q, page, page_size, response)
    return [{
        "id": j.id,
        "entity_type": j.entity_type,
        "filename": j.filename,
        "status": j.status,
        "total_rows": j.total_rows,
        "succeeded": j.succeeded,
        "failed_rows": j.failed_rows,
        "started_at": str(j.started_at)[:16],
        "completed_at": str(j.completed_at)[:16] if j.completed_at else None,
    } for j in jobs]


def get_workflow_executions(
    db: Session,
    wf_id: str,
    page: int,
    page_size: int,
    response: Optional[ConCabeceras] = None,
) -> list[dict]:
    q = db.query(WorkflowExecution).filter(
        WorkflowExecution.workflow_id == wf_id
    ).order_by(WorkflowExecution.started_at.desc())
    execs, _, _ = paginate_query(q, page, page_size, response)
    return [{
        "id": e.id,
        "status": e.status,
        "current_step": e.current_step,
        "steps_log": json.loads(e.steps_log) if e.steps_log else [],
        "error": e.error,
        "started_at": str(e.started_at)[:16],
        "completed_at": str(e.completed_at)[:16] if e.completed_at else None,
    } for e in execs]
