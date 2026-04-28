from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.service_desk import ProblemIn
from app.services.service_desk import problem_management_service as svc
from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback

router = APIRouter()


class ProblemCorrelationIn(BaseModel):
    ticket_ids: list[str] = Field(..., min_length=2)
    category: str = Field('recurrent_incidents', min_length=2, max_length=120)
    priority: str = Field('p2_high', min_length=2, max_length=20)
    auto_rca: bool = True


class LinkIncidentsIn(BaseModel):
    ticket_ids: list[str] = Field(..., min_length=1)


class ProblemToChangeIn(BaseModel):
    change_type: str = Field('normal', pattern='^(standard|normal|emergency)$')
    planned_start: Optional[str] = None
    planned_end: Optional[str] = None


class PromoteToKEDBIn(BaseModel):
    workaround: Optional[str] = None
    review_days: int = Field(90, ge=7, le=365)
    auto_kb: bool = True


class ApproveRCAIn(BaseModel):
    evidence: Optional[str] = None


class MarkKEDBReviewedIn(BaseModel):
    extend_days: int = Field(90, ge=7, le=365)


@router.get('/problems', summary='Listar problemas (Problem Management)')
def list_problems(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.service_desk.problem_service import list_problems_payload

    return {
        'items': list_problems_payload(db, current_user, page, page_size),
        'page': page,
        'page_size': page_size,
    }


@router.post('/problems', summary='Crear problema manual', status_code=201)
def create_problem(
    payload: ProblemIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    problem = svc.create_problem(db, current_user=current_user, payload=payload)
    _commit_or_rollback(db)
    db.refresh(problem)
    return {'id': problem.id, 'number': problem.number}


@router.post('/problems/correlation', summary='Crear problema desde correlación de incidentes', status_code=201)
def create_problem_by_correlation(
    payload: ProblemCorrelationIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    problem = svc.create_problem_from_correlation(
        db,
        ticket_ids=payload.ticket_ids,
        category=payload.category,
        priority=payload.priority,
        auto_rca=payload.auto_rca,
    )
    _commit_or_rollback(db)
    db.refresh(problem)
    return {'id': problem.id, 'number': problem.number}


@router.post('/problems/{problem_id}/rca', summary='RCA wizard IA para problema')
def suggest_problem_rca(
    problem_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.service_desk.problem_service import get_scoped_problem_or_404

    problem = get_scoped_problem_or_404(db, current_user, problem_id)
    suggestion = svc.suggest_root_cause(db, problem=problem)
    _commit_or_rollback(db)
    return {'ok': True, 'suggestion': suggestion}


@router.get('/problems/{problem_id}/linked-incidents', summary='Listar incidentes vinculados al problema')
def linked_incidents(
    problem_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {'items': svc.get_linked_incidents(db, problem_id=problem_id, current_user=current_user)}


@router.post('/problems/{problem_id}/link-incidents', summary='Vincular incidentes al problema')
def link_incidents(
    problem_id: str,
    payload: LinkIncidentsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = svc.link_incidents_to_problem(
        db,
        problem_id=problem_id,
        ticket_ids=payload.ticket_ids,
        current_user=current_user,
    )
    _commit_or_rollback(db)
    return {'ok': True, **result}


@router.post('/problems/{problem_id}/create-change', summary='Crear RFC desde problema', status_code=201)
def create_change_from_problem(
    problem_id: str,
    payload: ProblemToChangeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = svc.close_problem_to_change(
            db,
            problem_id=problem_id,
            current_user=current_user,
            change_type=payload.change_type,
            planned_start=payload.planned_start,
            planned_end=payload.planned_end,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _commit_or_rollback(db)
    return {'ok': True, **result}


# ── KEDB lifecycle endpoints ──────────────────────────────────────────────────


@router.post('/problems/{problem_id}/promote-kedb', summary='Promover problema a Known Error (KEDB)')
def promote_problem_to_kedb(
    problem_id: str,
    payload: PromoteToKEDBIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Promote a Problem to the Known Error Database (KEDB).

    - Sets status to known_error
    - Stamps kedb_published_at and review expiry
    - Optionally auto-creates a published KB article from the workaround
    """
    from app.services.service_desk.problem_service import get_scoped_problem_or_404
    from app.services.service_desk.known_error_service import promote_to_known_error

    problem = get_scoped_problem_or_404(db, current_user, problem_id)
    try:
        result = promote_to_known_error(
            db,
            problem,
            workaround=payload.workaround,
            review_days=payload.review_days,
            auto_kb=payload.auto_kb,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _commit_or_rollback(db)
    return {'ok': True, 'kedb_entry': result}


@router.post('/problems/{problem_id}/approve-rca', summary='Aprobar RCA de problema')
def approve_problem_rca(
    problem_id: str,
    payload: ApproveRCAIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Mark the Root Cause Analysis as approved.

    Stamps rca_approved_by and rca_approved_at. Optionally records evidence.
    """
    from app.services.service_desk.problem_service import get_scoped_problem_or_404
    from app.services.service_desk.known_error_service import approve_rca

    if current_user.role not in ('admin', 'support'):
        raise HTTPException(status_code=403, detail='Only admin/support can approve RCA')

    problem = get_scoped_problem_or_404(db, current_user, problem_id)
    result = approve_rca(db, problem, approver_user_id=current_user.id, evidence=payload.evidence)
    _commit_or_rollback(db)
    return {'ok': True, **result}


@router.post('/problems/{problem_id}/kedb-review', summary='Registrar revisión manual de KEDB')
def kedb_mark_reviewed(
    problem_id: str,
    payload: MarkKEDBReviewedIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record a manual review of a Known Error entry and extend its review window."""
    from app.services.service_desk.problem_service import get_scoped_problem_or_404
    from app.services.service_desk.known_error_service import mark_kedb_reviewed

    problem = get_scoped_problem_or_404(db, current_user, problem_id)
    result = mark_kedb_reviewed(db, problem, extend_days=payload.extend_days)
    _commit_or_rollback(db)
    return {'ok': True, **result}


@router.get('/problems/{problem_id}/kedb-effectiveness', summary='Recalcular efectividad de un Known Error')
def kedb_effectiveness(
    problem_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recompute and return the effectiveness score for a specific KEDB entry."""
    from app.services.service_desk.problem_service import get_scoped_problem_or_404
    from app.services.service_desk.known_error_service import recompute_effectiveness

    problem = get_scoped_problem_or_404(db, current_user, problem_id)
    score = recompute_effectiveness(db, problem)
    _commit_or_rollback(db)
    return {'problem_id': problem_id, 'problem_number': problem.number, 'effectiveness_score': score}


@router.get('/known-errors', summary='Listar Known Errors (KEDB)')
def list_known_errors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all active KEDB entries."""
    from app.services.service_desk.known_error_service import get_known_errors, serialize_known_error

    entries = get_known_errors(db)
    return {'items': [serialize_known_error(p) for p in entries], 'total': len(entries)}


@router.get('/known-errors/stats', summary='Estadísticas del KEDB')
def kedb_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return aggregate KEDB statistics."""
    from app.services.service_desk.known_error_service import get_kedb_stats

    return get_kedb_stats(db)


@router.post('/known-errors/run-expiry-scan', summary='Ejecutar escaneo de KEDB caducado (admin)', status_code=200)
def run_kedb_expiry_scan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Demote expired KEDB entries back to investigating status."""
    from app.services.service_desk.known_error_service import run_kedb_expiry_scan as _scan

    if current_user.role != 'admin':
        raise HTTPException(status_code=403, detail='Admin only')
    result = _scan(db)
    _commit_or_rollback(db)
    return result


@router.post('/known-errors/run-effectiveness-scan', summary='Recalcular efectividad de todos los Known Errors (admin)')
def run_kedb_effectiveness_scan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch-recompute effectiveness scores for all active KEDB entries."""
    from app.services.service_desk.known_error_service import run_kedb_effectiveness_scan as _scan

    if current_user.role != 'admin':
        raise HTTPException(status_code=403, detail='Admin only')
    result = _scan(db)
    _commit_or_rollback(db)
    return result
