from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin, require_internal_user
from app.db.session import get_db
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIResponse, APIListResponse
from app.schemas.service_desk import ProblemIn
from app.services.service_desk import problem_management_service as svc
from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)
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


# ── RCA Wizard payloads ───────────────────────────────────────────────────────

class WizardStartIn(BaseModel):
    template: str = Field(
        ...,
        min_length=3,
        max_length=36,
        description="Built-in slug (five_whys|fishbone|itil_standard) or UUID of a custom ProblemRcaTemplate",
    )


class RcaTemplateCreateIn(BaseModel):
    name: str = Field(..., min_length=3, max_length=255)
    template_type: str = Field(..., pattern="^(five_whys|fishbone|itil_standard|custom)$")
    steps_json: str = Field(..., description="JSON array of {step, label, prompt} objects")
    description: Optional[str] = None


class RcaTemplateUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = None
    steps_json: Optional[str] = None
    is_active: Optional[bool] = None


class WizardStepIn(BaseModel):
    step: int = Field(..., ge=1, description="Step number (1-based)")
    answer: str = Field(..., min_length=5, max_length=4000, description="Analyst's answer for this step")


class WizardAIAssistIn(BaseModel):
    step: int = Field(..., ge=1, description="Step number to get AI assistance for")


@router.get('/problems', summary='Listar problemas (Problem Management)')
def list_problems(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.service_desk.problem_service import list_problems_payload

    try:
        return APIListResponse.ok(
            items=list_problems_payload(db, current_user, page, page_size),
            page=page, page_size=page_size,
        )
    except Exception:
        logger.exception("problem_management.list_problems failed for user_id=%s", getattr(current_user, "id", None))
        return APIListResponse.ok(items=[], page=page, page_size=page_size)


@router.post('/problems', summary='Crear problema manual', status_code=201)
def create_problem(
    payload: ProblemIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    problem = svc.create_problem(db, current_user=current_user, payload=payload)
    _commit_or_rollback(db)
    db.refresh(problem)
    return APIResponse.ok(data={'id': problem.id, 'number': problem.number})


@router.post('/problems/correlation', summary='Crear problema desde correlación de incidentes', status_code=201)
def create_problem_by_correlation(
    payload: ProblemCorrelationIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
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
    return APIResponse.ok(data={'id': problem.id, 'number': problem.number})


@router.post('/problems/{problem_id}/rca', summary='RCA wizard IA para problema')
def suggest_problem_rca(
    problem_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    from app.services.service_desk.problem_service import get_scoped_problem_or_404

    problem = get_scoped_problem_or_404(db, current_user, problem_id)
    suggestion = svc.suggest_root_cause(db, problem=problem)
    _commit_or_rollback(db)
    return APIResponse.ok(data={'ok': True, 'suggestion': suggestion})


@router.get('/problems/{problem_id}/linked-incidents', summary='Listar incidentes vinculados al problema')
def linked_incidents(
    problem_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIListResponse.ok(items=svc.get_linked_incidents(db, problem_id=problem_id, current_user=current_user))


@router.post('/problems/{problem_id}/link-incidents', summary='Vincular incidentes al problema')
def link_incidents(
    problem_id: str,
    payload: LinkIncidentsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    result = svc.link_incidents_to_problem(
        db,
        problem_id=problem_id,
        ticket_ids=payload.ticket_ids,
        current_user=current_user,
    )
    _commit_or_rollback(db)
    return APIResponse.ok(data={'ok': True, **result})


@router.post('/problems/{problem_id}/create-change', summary='Crear RFC desde problema', status_code=201)
def create_change_from_problem(
    problem_id: str,
    payload: ProblemToChangeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
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
    return APIResponse.ok(data={'ok': True, **result})


# ── KEDB lifecycle endpoints ──────────────────────────────────────────────────


@router.post('/problems/{problem_id}/promote-kedb', summary='Promover problema a Known Error (KEDB)')
def promote_problem_to_kedb(
    problem_id: str,
    payload: PromoteToKEDBIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
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
    return APIResponse.ok(data={'ok': True, 'kedb_entry': result})


@router.post('/problems/{problem_id}/approve-rca', summary='Aprobar RCA de problema')
def approve_problem_rca(
    problem_id: str,
    payload: ApproveRCAIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
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
    return APIResponse.ok(data={'ok': True, **result})


@router.post('/problems/{problem_id}/kedb-review', summary='Registrar revisión manual de KEDB')
def kedb_mark_reviewed(
    problem_id: str,
    payload: MarkKEDBReviewedIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    """Record a manual review of a Known Error entry and extend its review window."""
    from app.services.service_desk.problem_service import get_scoped_problem_or_404
    from app.services.service_desk.known_error_service import mark_kedb_reviewed

    problem = get_scoped_problem_or_404(db, current_user, problem_id)
    result = mark_kedb_reviewed(db, problem, extend_days=payload.extend_days)
    _commit_or_rollback(db)
    return APIResponse.ok(data={'ok': True, **result})


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
    return APIResponse.ok(data={'problem_id': problem_id, 'problem_number': problem.number, 'effectiveness_score': score})


@router.get('/known-errors', summary='Listar Known Errors (KEDB)')
def list_known_errors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all active KEDB entries."""
    from app.services.service_desk.known_error_service import get_known_errors, serialize_known_error

    entries = get_known_errors(db)
    return APIListResponse.ok(items=[serialize_known_error(p) for p in entries], total=len(entries))


@router.get('/known-errors/{known_error_id}/tickets',
            summary='Tickets vinculados a un Known Error')
def known_error_tickets(
    known_error_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Auditoria 2026-08 (hallazgo 37): esta ruta **no existia** y la interfaz
    la llamaba. El modelo si estaba — la tabla de union
    `sd_known_error_tickets`—, solo faltaba exponerlo.

    Va **despues** de `/known-errors/stats` y de los dos `run-*-scan`: FastAPI
    resuelve por orden de declaracion y un `/{known_error_id}` declarado antes
    se tragaria esas rutas literales. Es el defecto de 3.g y no se repite.
    """
    from app.services.service_desk.known_error_service import (
        tickets_de_un_error_conocido,
    )

    items = tickets_de_un_error_conocido(db, current_user, known_error_id)
    return APIListResponse.ok(items=items, total=len(items))


@router.get('/known-errors/stats', summary='Estadísticas del KEDB')
def kedb_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return aggregate KEDB statistics."""
    from app.services.service_desk.known_error_service import get_kedb_stats

    return APIResponse.ok(data=get_kedb_stats(db))


@router.post('/known-errors/run-expiry-scan', summary='Ejecutar escaneo de KEDB caducado (admin)', status_code=200)
def run_kedb_expiry_scan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    """Demote expired KEDB entries back to investigating status."""
    from app.services.service_desk.known_error_service import run_kedb_expiry_scan as _scan

    if current_user.role != 'admin':
        raise HTTPException(status_code=403, detail='Admin only')
    result = _scan(db)
    _commit_or_rollback(db)
    return APIResponse.ok(data=result)


@router.post('/known-errors/run-effectiveness-scan', summary='Recalcular efectividad de todos los Known Errors (admin)')
def run_kedb_effectiveness_scan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    """Batch-recompute effectiveness scores for all active KEDB entries."""
    from app.services.service_desk.known_error_service import run_kedb_effectiveness_scan as _scan

    if current_user.role != 'admin':
        raise HTTPException(status_code=403, detail='Admin only')
    result = _scan(db)
    _commit_or_rollback(db)
    return APIResponse.ok(data=result)


# ── RCA Wizard endpoints (ITSM-P06) ──────────────────────────────────────────


@router.get('/rca/templates', summary='Listar templates RCA disponibles')
def list_rca_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all available RCA templates from DB (with built-in fallback)."""
    from app.services.service_desk.rca_wizard_service import list_available_templates

    return APIListResponse.ok(items=list_available_templates(db))


@router.post('/rca/templates', summary='Crear template RCA personalizado (admin)', status_code=201)
def create_rca_template(
    payload: RcaTemplateCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    """Create a custom RCA template stored in sd_problem_rca_templates."""
    import json
    # Validate steps_json is valid JSON array
    try:
        steps = json.loads(payload.steps_json)
        if not isinstance(steps, list) or not steps:
            raise ValueError('steps_json must be a non-empty JSON array')
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f'Invalid steps_json: {exc}')

    tpl = svc.create_rca_template(
        db,
        current_user=current_user,
        name=payload.name,
        template_type=payload.template_type,
        steps_json=payload.steps_json,
        description=payload.description,
    )
    _commit_or_rollback(db)
    return APIResponse.ok(data={'ok': True, 'id': tpl.id, 'name': tpl.name, 'total_steps': len(steps)})


@router.put('/rca/templates/{template_id}', summary='Actualizar template RCA (admin)')
def update_rca_template(
    template_id: str,
    payload: RcaTemplateUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    """Update a non-system custom RCA template."""

    tpl = svc.get_rca_template(db, template_id=template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail='RCA template not found')
    if tpl.is_system:
        raise HTTPException(status_code=403, detail='System templates cannot be modified')

    if payload.name is not None:
        tpl.name = payload.name
    if payload.description is not None:
        tpl.description = payload.description
    if payload.steps_json is not None:
        import json
        try:
            steps = json.loads(payload.steps_json)
            if not isinstance(steps, list) or not steps:
                raise ValueError('steps_json must be a non-empty JSON array')
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail=f'Invalid steps_json: {exc}')
        tpl.steps_json = payload.steps_json
    if payload.is_active is not None:
        tpl.is_active = payload.is_active

    _commit_or_rollback(db)
    return APIResponse.ok(data={'ok': True, 'id': tpl.id})


@router.delete('/rca/templates/{template_id}', summary='Eliminar template RCA custom (admin)')
def delete_rca_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_admin),
):
    """Desactiva una plantilla RCA propia. Las del sistema no se borran.

    Auditoría 2026-09: el resumen de esta ruta dice «(admin)» **desde que se
    escribió**, y no había ninguna guarda que lo exigiera. El único control era
    `enforce_abac`, que es fail-open: sin políticas activas —el caso por
    defecto— cualquier usuario autenticado podía desactivar las plantillas de
    análisis de causa raíz de su organización.

    Esto no es una decisión de producto nueva: es la que ya estaba escrita en
    la propia ruta, aplicada.
    """
    enforce_abac(db, current_user, "sd_rca_template", template_id, action="delete")
    tpl = svc.get_rca_template(db, template_id=template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail='RCA template not found')
    if tpl.is_system:
        raise HTTPException(status_code=403, detail='System templates cannot be deleted')

    tpl.is_active = False
    _commit_or_rollback(db)
    return APIResponse.ok(data={'ok': True, 'id': tpl.id, 'deactivated': True})


@router.post('/problems/{problem_id}/rca-wizard/start', summary='Iniciar wizard RCA guiado')
def start_rca_wizard(
    problem_id: str,
    payload: WizardStartIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    """
    Initialise (or reset) the RCA wizard for this problem.

    Selecting a template generates the step prompts. Any previous wizard state
    is discarded. Returns the initial wizard state with all step prompts.
    """
    from app.services.service_desk.problem_service import get_scoped_problem_or_404
    from app.services.service_desk.rca_wizard_service import start_wizard

    problem = get_scoped_problem_or_404(db, current_user, problem_id)
    state = start_wizard(db, problem, template=payload.template)
    _commit_or_rollback(db)
    return APIResponse.ok(data={'ok': True, 'wizard': state})


@router.get('/problems/{problem_id}/rca-wizard', summary='Ver estado actual del wizard RCA')
def get_rca_wizard_state(
    problem_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the current RCA wizard state including answered steps and AI hints."""
    from app.services.service_desk.problem_service import get_scoped_problem_or_404
    from app.services.service_desk.rca_wizard_service import get_wizard_state

    problem = get_scoped_problem_or_404(db, current_user, problem_id)
    state = get_wizard_state(problem)
    # state is None when not yet started — 200 so frontend avoids console 404
    return APIResponse.ok(data={'wizard': state})


@router.post('/problems/{problem_id}/rca-wizard/step', summary='Enviar respuesta de un paso del wizard')
def submit_rca_wizard_step(
    problem_id: str,
    payload: WizardStepIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    """
    Record the analyst's answer for a specific step.

    Steps can be answered in any order and re-submitted to correct answers.
    Returns the updated wizard state.
    """
    from app.services.service_desk.problem_service import get_scoped_problem_or_404
    from app.services.service_desk.rca_wizard_service import submit_wizard_step

    problem = get_scoped_problem_or_404(db, current_user, problem_id)
    state = submit_wizard_step(db, problem, step_num=payload.step, answer=payload.answer)
    _commit_or_rollback(db)
    return APIResponse.ok(data={'ok': True, 'wizard': state})


@router.post('/problems/{problem_id}/rca-wizard/ai-assist', summary='Obtener sugerencia IA para un paso del wizard')
def rca_wizard_ai_assist(
    problem_id: str,
    payload: WizardAIAssistIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    """
    Request an AI-generated hint for a specific wizard step.

    The hint considers the problem context, previous answers, and the step prompt.
    The hint is persisted in the step's ai_hint field and returned.
    """
    from app.services.service_desk.problem_service import get_scoped_problem_or_404
    from app.services.service_desk.rca_wizard_service import ai_assist_step

    problem = get_scoped_problem_or_404(db, current_user, problem_id)
    result = ai_assist_step(db, problem, step_num=payload.step)
    _commit_or_rollback(db)
    return APIResponse.ok(data={'ok': True, **result})


@router.post('/problems/{problem_id}/rca-wizard/complete', summary='Finalizar wizard RCA y derivar campos')
def complete_rca_wizard(
    problem_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    """
    Finalise the RCA wizard.

    Requires all steps to be answered. Derives and writes:
      - problem.root_cause   — synthesized from wizard answers
      - problem.rca_type     — AI-classified (hardware|software|process|human|network|unknown)
      - problem.workaround   — from ITIL step 4 (when applicable)

    Marks the wizard as completed. Returns the derived RCA fields.
    """
    from app.services.service_desk.problem_service import get_scoped_problem_or_404
    from app.services.service_desk.rca_wizard_service import complete_wizard

    problem = get_scoped_problem_or_404(db, current_user, problem_id)
    try:
        result = complete_wizard(db, problem)
    # intentional: chained re-raise preserves context
    except (HTTPException, ErrorDeDominio):
        raise
    except Exception as exc:
        logger.warning('complete_rca_wizard: unexpected error: %s', exc)
        raise HTTPException(status_code=500, detail='Error finalizing RCA wizard')
    _commit_or_rollback(db)
    return APIResponse.ok(data={'ok': True, 'rca': result})
