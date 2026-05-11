"""Performance Reviews — Evaluaciones de rendimiento 360°."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_hr, require_any_manager
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.models.performance import (
    ReviewCycleStatus, ReviewStatus, ReviewQuestion,
)
from app.services import performance_service
from app.services.performance_service import (
    serialize_review as _ser_review,
    serialize_question as _ser_question,
)
from app.schemas.performance import (
    ReviewCycleIn as CycleIn,
    PerformanceReviewIn as ReviewIn,
    ReviewQuestionIn,
    ReviewQuestionUpdate,
    Campaign360In,
    DevPlanIn, DevPlanUpdate, DevGoalIn, DevGoalUpdate,
)

router = APIRouter(tags=["Performance Reviews"])


def _is_perf_privileged_viewer(user: User) -> bool:
    if getattr(user, "is_superadmin", False):
        return True
    return user.role in ("admin", "hr")


def _can_view_subject(current_user: User, target_user: User) -> bool:
    if _is_perf_privileged_viewer(current_user):
        return True
    if current_user.id == target_user.id:
        return True
    return bool(target_user.manager_id and target_user.manager_id == current_user.id)


def _can_view_review(current_user: User, review, db: Session) -> bool:
    if _is_perf_privileged_viewer(current_user):
        return True
    if review.reviewee_id == current_user.id or review.reviewer_id == current_user.id:
        return True
    reviewee = db.query(User).filter(User.id == review.reviewee_id).first()
    return bool(reviewee and reviewee.manager_id == current_user.id)


def _can_view_campaign(current_user: User, camp, db: Session) -> bool:
    if _is_perf_privileged_viewer(current_user):
        return True
    if current_user.id == camp.subject_id or current_user.id == camp.created_by:
        return True
    subject = db.query(User).filter(User.id == camp.subject_id).first()
    return bool(subject and subject.manager_id == current_user.id)


# ── Cycles ────────────────────────────────────────────────────────────────────

@router.get("/cycles", summary="Listar ciclos de evaluación")
def list_cycles(
    response: Response,
    db: Session = Depends(get_db), cu: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    cycles, total = performance_service.list_cycles(db, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(total)
    # Lista plana por retrocompat (el frontend ya consume el array). El total
    # va en el header para que paginadores futuros puedan leerlo.
    return [{"id": c.id, "name": c.name, "status": c.status,
             "start_date": str(c.start_date) if c.start_date else None,
             "end_date": str(c.end_date) if c.end_date else None,
             "total_reviews": len(c.reviews),
             "pending": sum(1 for r in c.reviews if r.status == ReviewStatus.pending),
             "submitted": sum(1 for r in c.reviews if r.status == ReviewStatus.submitted),
             } for c in cycles]


@router.post("/cycles", summary="Crear ciclo", status_code=201)
def create_cycle(payload: CycleIn, db: Session = Depends(get_db),
                 cu: User = Depends(require_admin_or_hr)):
    c = performance_service.create_cycle(db, created_by=cu.id, **payload.model_dump())
    return {"id": c.id, "name": c.name}


@router.post("/cycles/{cycle_id}/activate", summary="Activar ciclo")
def activate_cycle(cycle_id: str, db: Session = Depends(get_db),
                   cu: User = Depends(require_admin_or_hr)):
    c = performance_service.get_cycle(db, cycle_id)
    if not c:
        raise HTTPException(404, "Ciclo no encontrado")
    if c.status != ReviewCycleStatus.draft:
        raise HTTPException(400, f"Solo se puede activar un ciclo en estado 'draft', actual: '{c.status}'")
    performance_service.activate_cycle(db, c)
    return {"status": "active"}


@router.post("/cycles/{cycle_id}/close", summary="Cerrar ciclo")
def close_cycle(cycle_id: str, db: Session = Depends(get_db),
                cu: User = Depends(require_admin_or_hr)):
    c = performance_service.get_cycle(db, cycle_id)
    if not c:
        raise HTTPException(404, "Ciclo no encontrado")
    if c.status != ReviewCycleStatus.active:
        raise HTTPException(400, f"Solo se puede cerrar un ciclo activo, actual: '{c.status}'")
    performance_service.close_cycle(db, c)
    return {"status": "closed"}


# ── Questions (configurable per cycle) ────────────────────────────────────────

@router.get("/cycles/{cycle_id}/questions", summary="Listar preguntas del ciclo")
def list_cycle_questions(cycle_id: str, db: Session = Depends(get_db),
                         cu: User = Depends(get_current_user)):
    c = performance_service.get_cycle(db, cycle_id)
    if not c:
        raise HTTPException(404, "Ciclo no encontrado")
    return [_ser_question(q) for q in performance_service.list_questions(db, cycle_id)]


@router.post("/cycles/{cycle_id}/questions", summary="Añadir pregunta al ciclo", status_code=201)
def add_cycle_question(cycle_id: str, payload: ReviewQuestionIn,
                       db: Session = Depends(get_db),
                       cu: User = Depends(require_admin_or_hr)):
    c = performance_service.get_cycle(db, cycle_id)
    if not c:
        raise HTTPException(404, "Ciclo no encontrado")
    try:
        q = performance_service.add_question(db, c, payload.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    db.refresh(q)
    return _ser_question(q)


@router.patch("/questions/{question_id}", summary="Actualizar pregunta")
def update_cycle_question(question_id: str, payload: ReviewQuestionUpdate,
                          db: Session = Depends(get_db),
                          cu: User = Depends(require_admin_or_hr)):
    q = db.query(ReviewQuestion).filter(ReviewQuestion.id == question_id).first()
    if not q:
        raise HTTPException(404, "Pregunta no encontrada")
    try:
        q = performance_service.update_question(db, q, payload.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    db.refresh(q)
    return _ser_question(q)


@router.delete("/questions/{question_id}", summary="Eliminar pregunta", status_code=204)
def delete_cycle_question(question_id: str, db: Session = Depends(get_db),
                          cu: User = Depends(require_admin_or_hr)):
    enforce_abac(db, cu, "performance_question", question_id, action="delete")
    q = db.query(ReviewQuestion).filter(ReviewQuestion.id == question_id).first()
    if not q:
        raise HTTPException(404, "Pregunta no encontrada")
    try:
        performance_service.delete_question(db, q)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return None


@router.post("/cycles/{cycle_id}/questions/seed-default",
             summary="Sembrar preguntas por defecto en el ciclo")
def seed_default_questions(cycle_id: str, db: Session = Depends(get_db),
                           cu: User = Depends(require_admin_or_hr)):
    c = performance_service.get_cycle(db, cycle_id)
    if not c:
        raise HTTPException(404, "Ciclo no encontrado")
    if c.status != ReviewCycleStatus.draft:
        raise HTTPException(400, "Solo se pueden añadir preguntas a ciclos en borrador")
    performance_service.seed_default_questions_for_cycle(db, c)
    db.commit()
    return [_ser_question(q) for q in performance_service.list_questions(db, cycle_id)]


@router.post("/cycles/{cycle_id}/clone-questions/{source_cycle_id}",
             summary="Clonar preguntas desde otro ciclo")
def clone_cycle_questions(cycle_id: str, source_cycle_id: str,
                          db: Session = Depends(get_db),
                          cu: User = Depends(require_admin_or_hr)):
    dest = performance_service.get_cycle(db, cycle_id)
    if not dest:
        raise HTTPException(404, "Ciclo destino no encontrado")
    if dest.status != ReviewCycleStatus.draft:
        raise HTTPException(400, "Solo se pueden añadir preguntas a ciclos en borrador")
    src = performance_service.get_cycle(db, source_cycle_id)
    if not src:
        raise HTTPException(404, "Ciclo origen no encontrado")
    n = performance_service.clone_questions(db, source_cycle_id=source_cycle_id, dest_cycle=dest)
    db.commit()
    return {"cloned": n}


# ── Eligible reviewers ────────────────────────────────────────────────────────

@router.get(
    "/cycles/{cycle_id}/eligible-reviewers/{reviewee_id}/{review_type}",
    summary="Listar evaluadores elegibles para una persona y tipo de revisión",
)
def list_eligible_reviewers(cycle_id: str, reviewee_id: str, review_type: str,
                            db: Session = Depends(get_db),
                            cu: User = Depends(require_admin_or_hr)):
    if review_type not in ("self", "manager", "peer", "upward"):
        raise HTTPException(422, "review_type debe ser self|manager|peer|upward")
    reviewee = db.query(User).filter(User.id == reviewee_id).first()
    if not reviewee:
        raise HTTPException(404, "Persona evaluada no encontrada")

    users = performance_service.eligible_reviewers(db, reviewee=reviewee, review_type=review_type)

    # Razón de bloqueo para que la UI pueda explicar por qué un tipo está deshabilitado
    reason = None
    if not users:
        if review_type == "manager":
            reason = "Esta persona no tiene manager configurado en el organigrama"
        elif review_type == "peer":
            if not reviewee.team and not reviewee.department:
                reason = "Esta persona no tiene equipo ni departamento asignado"
            else:
                reason = "No hay otras personas en su equipo/departamento"
        elif review_type == "upward":
            reason = "Esta persona no tiene reportes directos"

    return {
        "review_type": review_type,
        "reviewee_id": reviewee_id,
        "reason_blocked": reason,
        "users": [
            {"id": u.id, "full_name": u.full_name, "email": u.email,
             "department": u.department, "team": u.team, "job_title": u.job_title}
            for u in users
        ],
    }


# ── Reviews ───────────────────────────────────────────────────────────────────

@router.get("/cycles/{cycle_id}/reviews", summary="Evaluaciones de un ciclo")
def list_reviews(
    cycle_id: str, response: Response,
    db: Session = Depends(get_db), cu: User = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    reviews, total = performance_service.list_cycle_reviews(
        db, cycle_id, limit=limit, offset=offset,
    )
    reviews = [r for r in reviews if _can_view_review(cu, r, db)]
    response.headers["X-Total-Count"] = str(total)
    return [_ser_review(r) for r in reviews]


@router.get("/my-reviews", summary="Mis evaluaciones pendientes")
def my_reviews(db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    reviews = performance_service.list_my_pending_reviews(db, cu.id)
    return [_ser_review(r) for r in reviews]


@router.post("/cycles/{cycle_id}/reviews", summary="Crear evaluación", status_code=201)
def create_review(cycle_id: str, payload: dict,
                  db: Session = Depends(get_db), cu: User = Depends(require_admin_or_hr)):
    if not payload.get("reviewee_id") or not payload.get("reviewer_id"):
        raise HTTPException(422, "reviewee_id y reviewer_id son obligatorios")
    try:
        r = performance_service.create_review(
            db, cycle_id=cycle_id,
            reviewee_id=payload["reviewee_id"],
            reviewer_id=payload["reviewer_id"],
            review_type=payload.get("review_type", "peer"),
            validate_eligibility=bool(payload.get("validate_eligibility", True)),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": r.id}


@router.patch("/reviews/{review_id}", summary="Guardar evaluación")
def save_review(review_id: str, payload: ReviewIn,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    r = performance_service.get_review(db, review_id)
    if not r:
        raise HTTPException(404, "Evaluación no encontrada")
    if r.reviewer_id != cu.id:
        raise HTTPException(403, "Solo el evaluador puede modificar esta evaluación")
    c = performance_service.get_cycle(db, r.cycle_id)
    if c and c.status == ReviewCycleStatus.closed:
        raise HTTPException(400, "El ciclo de evaluación ya está cerrado")
    r = performance_service.save_review(db, r, payload.model_dump(exclude_unset=True))
    return _ser_review(r)


@router.post("/reviews/{review_id}/submit", summary="Enviar evaluación")
def submit_review(review_id: str, db: Session = Depends(get_db),
                  cu: User = Depends(get_current_user)):
    r = performance_service.get_review(db, review_id)
    if not r:
        raise HTTPException(404, "Evaluación no encontrada")
    if r.reviewer_id != cu.id:
        raise HTTPException(403, "Acceso denegado")
    c = performance_service.get_cycle(db, r.cycle_id)
    if c and c.status == ReviewCycleStatus.closed:
        raise HTTPException(400, "El ciclo de evaluación ya está cerrado")
    performance_service.submit_review(db, r)
    return {"status": "submitted"}


@router.get("/users/{user_id}/history", summary="Histórico de evaluaciones de un usuario")
def user_review_history(user_id: str, db: Session = Depends(get_db),
                        cu: User = Depends(get_current_user)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(404, "Usuario no encontrado")
    if not _can_view_subject(cu, target):
        raise HTTPException(403, "Acceso denegado")
    reviews = performance_service.get_user_review_history(db, user_id)
    return [_ser_review(r) for r in reviews]


# ── 360° Campaigns ────────────────────────────────────────────────────────────

@router.get("/cycles/{cycle_id}/campaigns",
            summary="Listar campañas 360° del ciclo")
def list_cycle_campaigns(
    cycle_id: str, response: Response,
    db: Session = Depends(get_db), cu: User = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    c = performance_service.get_cycle(db, cycle_id)
    if not c:
        raise HTTPException(404, "Ciclo no encontrado")
    campaigns, total = performance_service.list_cycle_campaigns(
        db, cycle_id, limit=limit, offset=offset,
    )
    campaigns = [camp for camp in campaigns if _can_view_campaign(cu, camp, db)]
    response.headers["X-Total-Count"] = str(total)
    return [
        performance_service.serialize_campaign(camp)
        for camp in campaigns
    ]


@router.post("/cycles/{cycle_id}/campaigns",
             summary="Crear campaña 360° con sus evaluadores",
             status_code=201)
def create_campaign(cycle_id: str, payload: Campaign360In,
                    db: Session = Depends(get_db),
                    cu: User = Depends(require_any_manager)):
    # Self-service: PM / Team Lead solo pueden lanzar campañas para sus
    # reportes directos. Admin / HR pueden hacerlo para cualquiera.
    if not performance_service.can_launch_campaign_for(
        db, current_user=cu, subject_id=payload.subject_id
    ):
        raise HTTPException(403, "Solo puedes lanzar campañas para tus reportes directos")
    try:
        camp = performance_service.create_campaign(
            db,
            cycle_id=cycle_id,
            subject_id=payload.subject_id,
            created_by=cu.id,
            self_review=payload.self_review,
            manager_reviewer_id=payload.manager_reviewer_id,
            peer_reviewer_ids=payload.peer_reviewer_ids,
            upward_reviewer_ids=payload.upward_reviewer_ids,
            anonymity_threshold=payload.anonymity_threshold,
            auto_activate=payload.auto_activate,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return performance_service.serialize_campaign(camp)


@router.post("/campaigns/{campaign_id}/close", summary="Cerrar campaña 360°")
def close_campaign(campaign_id: str, db: Session = Depends(get_db),
                   cu: User = Depends(require_admin_or_hr)):
    camp = performance_service.get_campaign(db, campaign_id)
    if not camp:
        raise HTTPException(404, "Campaña no encontrada")
    performance_service.close_campaign(db, camp)
    return performance_service.serialize_campaign(camp)


@router.get("/campaigns/{campaign_id}/dashboard",
            summary="Dashboard 360° agregado y anonimizado")
def campaign_dashboard(campaign_id: str, db: Session = Depends(get_db),
                       cu: User = Depends(get_current_user)):
    camp = performance_service.get_campaign(db, campaign_id)
    if not camp:
        raise HTTPException(404, "Campaña no encontrada")
    if not _can_view_campaign(cu, camp, db):
        raise HTTPException(403, "Acceso denegado")
    return performance_service.aggregate_campaign(db, camp)


@router.get("/campaigns/{campaign_id}/dashboard.pdf",
            summary="Exportar dashboard 360° a PDF")
def campaign_dashboard_pdf(campaign_id: str, db: Session = Depends(get_db),
                           cu: User = Depends(require_admin_or_hr)):
    camp = performance_service.get_campaign(db, campaign_id)
    if not camp:
        raise HTTPException(404, "Campaña no encontrada")
    dashboard = performance_service.aggregate_campaign(db, camp)
    from app.services.campaign_pdf import generate_campaign_pdf
    pdf_bytes = generate_campaign_pdf(dashboard)
    subject = (camp.subject.full_name if camp.subject else "subject").replace(" ", "_")
    filename = f"360_{subject}_{camp.id[:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/campaigns/{campaign_id}/reviews",
            summary="Listar evaluaciones individuales de una campaña")
def campaign_reviews(campaign_id: str, db: Session = Depends(get_db),
                     cu: User = Depends(require_admin_or_hr)):
    camp = performance_service.get_campaign(db, campaign_id)
    if not camp:
        raise HTTPException(404, "Campaña no encontrada")
    return [_ser_review(r) for r in (camp.reviews or [])]


@router.get("/users/{user_id}/360-history",
            summary="Histórico 360° de un subject a lo largo de varios ciclos")
def user_360_history(user_id: str, db: Session = Depends(get_db),
                     cu: User = Depends(get_current_user)):
    # El propio interesado puede consultar su histórico; managers/HR/admin
    # pueden consultar el de cualquiera.
    is_priv = cu.is_superadmin or cu.role in ("admin", "hr", "pm", "team_lead")
    if not is_priv and cu.id != user_id:
        raise HTTPException(403, "Solo puedes consultar tu propio histórico")
    return performance_service.history_360_for_subject(db, user_id)


# ── KPIs y recordatorios automáticos ────────────────────────────────────────

@router.get("/kpis", summary="KPIs agregados de evaluaciones de la organización")
def org_kpis(db: Session = Depends(get_db),
             cu: User = Depends(require_admin_or_hr)):
    from app.services import perf_reminder_service
    return perf_reminder_service.org_perf_kpis(db)


@router.get("/cycles/{cycle_id}/kpis", summary="KPIs operativos de un ciclo")
def cycle_kpis(cycle_id: str, db: Session = Depends(get_db),
               cu: User = Depends(require_any_manager)):
    from app.services import perf_reminder_service
    data = perf_reminder_service.cycle_kpis(db, cycle_id)
    if not data:
        raise HTTPException(404, "Ciclo no encontrado")
    return data


@router.post("/admin/run-reminders",
             summary="Disparar recordatorios manualmente (admin)")
def admin_run_reminders(db: Session = Depends(get_db),
                        cu: User = Depends(require_admin_or_hr)):
    from app.services import perf_reminder_service
    return perf_reminder_service.send_pending_review_reminders(db)


# ── Development Plans (plan de acción tras 360°) ────────────────────────────

@router.get("/users/{user_id}/dev-plans",
            summary="Planes de desarrollo de una persona")
def list_user_plans(user_id: str, db: Session = Depends(get_db),
                    cu: User = Depends(get_current_user)):
    from app.services import dev_plan_service
    is_priv = cu.is_superadmin or cu.role in ("admin", "hr")
    if not is_priv and cu.id != user_id:
        # Manager? lo permitimos si es manager directo
        target = db.query(User).filter(User.id == user_id).first()
        if not target or target.manager_id != cu.id:
            raise HTTPException(403, "No tienes acceso a estos planes")
    plans = dev_plan_service.list_plans_for_subject(db, user_id)
    return [dev_plan_service.serialize_plan(p) for p in plans]


@router.get("/dev-plans/{plan_id}", summary="Detalle de un plan de desarrollo")
def get_dev_plan(plan_id: str, db: Session = Depends(get_db),
                 cu: User = Depends(get_current_user)):
    from app.services import dev_plan_service
    plan = dev_plan_service.get_plan(db, plan_id)
    if not plan:
        raise HTTPException(404, "Plan no encontrado")
    if not dev_plan_service.can_view_plan(current_user=cu, plan=plan, db=db):
        raise HTTPException(403, "Sin permisos para ver este plan")
    return dev_plan_service.serialize_plan(plan)


@router.post("/dev-plans", summary="Crear plan de desarrollo", status_code=201)
def create_dev_plan(payload: DevPlanIn, db: Session = Depends(get_db),
                    cu: User = Depends(get_current_user)):
    from app.services import dev_plan_service
    # Solo el subject, su manager o admin/HR pueden crear
    target = db.query(User).filter(User.id == payload.subject_id).first()
    if not target:
        raise HTTPException(404, "Persona no encontrada")
    is_priv = cu.is_superadmin or cu.role in ("admin", "hr")
    if not is_priv and cu.id != payload.subject_id and target.manager_id != cu.id:
        raise HTTPException(403, "Solo puedes crear planes propios o de tus reportes directos")
    plan = dev_plan_service.create_plan(
        db, subject_id=payload.subject_id, created_by=cu.id,
        title=payload.title, summary=payload.summary,
        campaign_id=payload.campaign_id, cycle_id=payload.cycle_id,
        target_date=payload.target_date, next_review_at=payload.next_review_at,
        goals=[g.model_dump() for g in (payload.goals or [])],
    )
    return dev_plan_service.serialize_plan(plan)


@router.patch("/dev-plans/{plan_id}", summary="Actualizar plan de desarrollo")
def patch_dev_plan(plan_id: str, payload: DevPlanUpdate,
                   db: Session = Depends(get_db),
                   cu: User = Depends(get_current_user)):
    from app.services import dev_plan_service
    plan = dev_plan_service.get_plan(db, plan_id)
    if not plan:
        raise HTTPException(404, "Plan no encontrado")
    if not dev_plan_service.can_edit_plan(current_user=cu, plan=plan, db=db):
        raise HTTPException(403, "Sin permisos para editar este plan")
    plan = dev_plan_service.update_plan(db, plan, payload.model_dump(exclude_unset=True))
    return dev_plan_service.serialize_plan(plan)


@router.post("/dev-plans/{plan_id}/goals",
             summary="Añadir objetivo al plan", status_code=201)
def add_dev_goal(plan_id: str, payload: DevGoalIn,
                 db: Session = Depends(get_db),
                 cu: User = Depends(get_current_user)):
    from app.services import dev_plan_service
    plan = dev_plan_service.get_plan(db, plan_id)
    if not plan:
        raise HTTPException(404, "Plan no encontrado")
    if not dev_plan_service.can_edit_plan(current_user=cu, plan=plan, db=db):
        raise HTTPException(403, "Sin permisos")
    g = dev_plan_service.add_goal(db, plan, payload.model_dump(exclude_unset=True))
    return dev_plan_service.serialize_goal(g)


@router.patch("/dev-goals/{goal_id}", summary="Actualizar objetivo")
def patch_dev_goal(goal_id: str, payload: DevGoalUpdate,
                   db: Session = Depends(get_db),
                   cu: User = Depends(get_current_user)):
    from app.services import dev_plan_service
    from app.models.performance import DevGoal
    enforce_abac(db, cu, "dev_goal", goal_id, action="update")
    g = db.query(DevGoal).filter(DevGoal.id == goal_id).first()
    if not g:
        raise HTTPException(404, "Objetivo no encontrado")
    if not dev_plan_service.can_edit_plan(current_user=cu, plan=g.plan, db=db):
        raise HTTPException(403, "Sin permisos")
    g = dev_plan_service.update_goal(db, g, payload.model_dump(exclude_unset=True))
    return dev_plan_service.serialize_goal(g)


@router.delete("/dev-goals/{goal_id}", summary="Eliminar objetivo", status_code=204)
def remove_dev_goal(goal_id: str, db: Session = Depends(get_db),
                    cu: User = Depends(get_current_user)):
    from app.services import dev_plan_service
    from app.models.performance import DevGoal
    enforce_abac(db, cu, "dev_goal", goal_id, action="delete")
    g = db.query(DevGoal).filter(DevGoal.id == goal_id).first()
    if not g:
        raise HTTPException(404, "Objetivo no encontrado")
    if not dev_plan_service.can_edit_plan(current_user=cu, plan=g.plan, db=db):
        raise HTTPException(403, "Sin permisos")
    dev_plan_service.delete_goal(db, g)
    return None
