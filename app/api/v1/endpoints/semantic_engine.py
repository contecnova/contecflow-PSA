"""
semantic_engine.py — API del motor de asignacion semantica (thin router)
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel
import json

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
import app.services.semantic_engine_service as _svc

router = APIRouter()

# Alias kept for backward compatibility with tests that patch this symbol
def _get_assigner(db):
    return _svc.get_assigner(db)

def _cache_item_embedding(db, item_id, item_type, text, user_id):
    return _svc.cache_item_embedding(db, item_id, item_type, text, user_id)


class SemConfigPatch(BaseModel):
    engine_mode: str | None = None
    threshold_ticket: float | None = None
    threshold_task: float | None = None
    threshold_expert_cache: float | None = None
    load_balance_weight: float | None = None
    threshold_critical: float | None = None
    threshold_high: float | None = None
    threshold_medium: float | None = None
    threshold_low: float | None = None
    history_decay_days: float | None = None
    auto_assign_tickets: bool | None = None
    auto_assign_tasks: bool | None = None
    local_model_name: str | None = None


# ── Configuracion ─────────────────────────────────────────────────────────────

@router.get("/config")
def get_config(db: Session = Depends(get_db), _=Depends(get_current_user)):
    cfg = _svc.get_or_create_config(db)
    return _svc.serialize_config(cfg)


@router.patch("/config")
def update_config(data: SemConfigPatch = Body(...),
                  db: Session = Depends(get_db),
                  _=Depends(get_current_user)):
    cfg = _svc.get_or_create_config(db)
    allowed = {"engine_mode", "threshold_ticket", "threshold_task",
               "threshold_expert_cache", "load_balance_weight",
               "threshold_critical", "threshold_high", "threshold_medium",
               "threshold_low", "history_decay_days",
               "auto_assign_tickets", "auto_assign_tasks", "local_model_name"}
    payload = data.model_dump(exclude_unset=True)
    if "engine_mode" in payload:
        payload["engine_mode"] = str(payload["engine_mode"]).strip().lower()
        if payload["engine_mode"] not in _svc.VALID_ENGINE_MODES:
            raise HTTPException(400, f"engine_mode inválido. Use uno de: {', '.join(sorted(_svc.VALID_ENGINE_MODES))}")
    for k, v in payload.items():
        if k in allowed and hasattr(cfg, k):
            setattr(cfg, k, v)
    db.commit()
    db.refresh(cfg)
    return {"ok": True, "config": _svc.serialize_config(cfg)}


# ── Sugerencia de asignacion ──────────────────────────────────────────────────

@router.post("/suggest/ticket")
def suggest_ticket_assignee(data: dict = Body(...),
                             db: Session = Depends(get_db),
                             cu=Depends(get_current_user)):
    title = data.get("title", "")
    desc  = data.get("description", "")
    if not title:
        raise HTTPException(400, "title requerido")
    candidates = data.get("candidate_user_ids")
    priority   = data.get("priority", "medium")
    assigner   = _svc.get_assigner(db)
    result     = assigner.suggest_for_ticket(title, desc, candidates, priority=priority)
    if result.get("suggested_user_id"):
        u = db.query(User).filter(User.id == result["suggested_user_id"]).first()
        result["suggested_user_name"] = u.full_name if u else None
    if result.get("top_scores"):
        enriched = {}
        for uid, score in result["top_scores"].items():
            u = db.query(User).filter(User.id == uid).first()
            enriched[uid] = {"score": score, "name": u.full_name if u else uid}
        result["top_candidates"] = enriched
    return result


@router.post("/suggest/task")
def suggest_task_assignee(data: dict = Body(...),
                          db: Session = Depends(get_db),
                          cu=Depends(get_current_user)):
    title      = data.get("title", "")
    desc       = data.get("description", "")
    if not title:
        raise HTTPException(400, "title requerido")
    project_id = data.get("project_id")
    candidates = data.get("candidate_user_ids")
    if project_id and not candidates:
        from app.models.project import ProjectMember
        members    = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id).all()
        candidates = [m.user_id for m in members]
    priority = data.get("priority", "medium")
    assigner = _svc.get_assigner(db)
    result   = assigner.suggest_for_task(title, desc, candidates, priority=priority)
    if result.get("suggested_user_id"):
        u = db.query(User).filter(User.id == result["suggested_user_id"]).first()
        result["suggested_user_name"] = u.full_name if u else None
    if result.get("top_scores"):
        enriched = {}
        for uid, score in result["top_scores"].items():
            u = db.query(User).filter(User.id == uid).first()
            enriched[uid] = {"score": score, "name": u.full_name if u else uid}
        result["top_candidates"] = enriched
    return result


# ── Estimacion de esfuerzo ────────────────────────────────────────────────────

@router.post("/estimate/effort")
def estimate_effort(data: dict = Body(...),
                    db: Session = Depends(get_db),
                    _=Depends(get_current_user)):
    title     = data.get("title", "")
    desc      = data.get("description", "")
    role_hint = data.get("role_hint", "default")
    assigner  = _svc.get_assigner(db)
    return assigner.estimate_effort(title, desc, role_hint)


@router.post("/estimate/sprint-backlog")
def estimate_sprint_backlog(data: dict = Body(...),
                            db: Session = Depends(get_db),
                            _=Depends(get_current_user)):
    tasks      = data.get("tasks", [])
    capacity_h = data.get("team_capacity_hours", 80)
    return _svc.estimate_sprint_backlog(tasks, capacity_h, db)


# ── Priorizacion de cola ──────────────────────────────────────────────────────

@router.post("/prioritize")
def prioritize_queue(data: dict = Body(...),
                     db: Session = Depends(get_db),
                     _=Depends(get_current_user)):
    items    = data.get("items", [])
    assigner = _svc.get_assigner(db)
    return {"prioritized": assigner.prioritize_queue(items)}


# ── Perfiles de usuario ───────────────────────────────────────────────────────

@router.get("/profiles")
def list_profiles(db: Session = Depends(get_db), _=Depends(get_current_user)):
    from app.models.semantic_engine import SemProfile
    profiles = db.query(SemProfile).all()
    result   = []
    for p in profiles:
        u = db.query(User).filter(User.id == p.user_id).first()
        result.append({
            "id":           p.id,
            "user_id":      p.user_id,
            "user_name":    u.full_name if u else None,
            "profile_text": p.profile_text[:200] if p.profile_text else "",
            "has_embedding": bool(p.embedding),
            "open_tickets": p.open_tickets,
            "open_tasks":   p.open_tasks,
            "max_load":     p.max_load,
            "is_available": p.is_available,
        })
    return result


@router.post("/profiles")
def create_or_update_profile(data: dict = Body(...),
                              db: Session = Depends(get_db),
                              _=Depends(get_current_user)):
    from app.models.semantic_engine import SemProfile
    user_id      = data.get("user_id")
    profile_text = data.get("profile_text", "")
    if not user_id:
        raise HTTPException(400, "user_id requerido")

    profile = db.query(SemProfile).filter(SemProfile.user_id == user_id).first()
    if not profile:
        profile = SemProfile(user_id=user_id)
        db.add(profile)

    profile.profile_text = profile_text
    profile.max_load     = data.get("max_load", profile.max_load or 10)
    profile.is_available = data.get("is_available", True)

    if profile_text:
        assigner = _svc.get_assigner(db)
        emb      = assigner._encode_single(profile_text)
        profile.embedding = json.dumps(emb)

    db.commit()
    db.refresh(profile)
    return {"ok": True, "has_embedding": bool(profile.embedding)}


@router.post("/profiles/auto-generate")
def auto_generate_profiles(db: Session = Depends(get_db),
                            _=Depends(get_current_user)):
    return _svc.auto_generate_profiles(db)


@router.post("/profiles/rebuild-embeddings")
def rebuild_embeddings(db: Session = Depends(get_db),
                       _=Depends(get_current_user)):
    assigner = _svc.get_assigner(db)
    n = assigner.rebuild_profiles()
    return {"rebuilt": n}


# ── Feedback de experto ───────────────────────────────────────────────────────

@router.post("/feedback")
def record_feedback(data: dict = Body(...),
                    db: Session = Depends(get_db),
                    cu=Depends(get_current_user)):
    item_id              = data.get("item_id", "")
    item_type            = data.get("item_type", "ticket")
    item_text            = data.get("item_text", "")
    correct_user_id      = data.get("correct_user_id", "")
    original_engine_mode = data.get("original_engine_mode", "")
    confirmed            = bool(data.get("confirmed", False))
    if not item_text or not correct_user_id:
        raise HTTPException(400, "item_text y correct_user_id requeridos")
    assigner = _get_assigner(db)
    corrected_by = cu.id
    if original_engine_mode == "llm" and confirmed:
        corrected_by = f"manager_confirm:{cu.id}"
    assigner.record_feedback(item_id, item_type, item_text,
                             correct_user_id, corrected_by)
    _cache_item_embedding(db, item_id, item_type, item_text, correct_user_id)
    llm_confirmed = original_engine_mode == "llm" and confirmed
    return {"ok": True, "persisted_as_expert": llm_confirmed}


# ── Estadisticas ──────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats(db: Session = Depends(get_db), _=Depends(get_current_user)):
    from app.models.semantic_engine import (SemAssignment, SemProfile,
                                            SemFeedback, SemEmbeddingCache)
    from sqlalchemy import func

    total    = db.query(func.count(SemAssignment.id)).scalar() or 0
    accepted = db.query(func.count(SemAssignment.id)).filter(
        SemAssignment.was_accepted == True).scalar() or 0
    rejected = db.query(func.count(SemAssignment.id)).filter(
        SemAssignment.was_accepted == False).scalar() or 0
    pending  = db.query(func.count(SemAssignment.id)).filter(
        SemAssignment.was_accepted == None).scalar() or 0
    profiles   = db.query(func.count(SemProfile.id)).scalar() or 0
    cache_size = db.query(func.count(SemEmbeddingCache.id)).scalar() or 0
    feedback   = db.query(func.count(SemFeedback.id)).scalar() or 0

    accuracy = round(accepted / (accepted + rejected) * 100) \
               if (accepted + rejected) > 0 else None

    by_mode_rows = db.query(
        SemAssignment.engine_mode,
        func.count(SemAssignment.id)
    ).group_by(SemAssignment.engine_mode).all()

    return {
        "total_suggestions": total,
        "accepted":          accepted,
        "rejected":          rejected,
        "pending":           pending,
        "accuracy_pct":      accuracy,
        "profiles":          profiles,
        "cache_size":        cache_size,
        "expert_feedback":   feedback,
        "by_mode":           {r[0]: r[1] for r in by_mode_rows},
    }


@router.post("/record-assignment")
def record_assignment(data: dict = Body(...),
                      db: Session = Depends(get_db),
                      cu=Depends(get_current_user)):
    from app.models.semantic_engine import SemAssignment, SemProfile
    sa = SemAssignment(
        item_type         = data.get("item_type", "ticket"),
        item_id           = data.get("item_id", ""),
        item_title        = data.get("item_title", "")[:500],
        suggested_user_id = data.get("suggested_user_id"),
        accepted_user_id  = data.get("accepted_user_id"),
        was_accepted      = data.get("was_accepted"),
        confidence        = data.get("confidence"),
        top_scores        = json.dumps(data.get("top_scores", {})),
        engine_mode       = data.get("engine_mode"),
        estimated_hours   = data.get("estimated_hours"),
        complexity        = data.get("complexity"),
        reasoning         = data.get("reasoning", "")[:1000],
        needs_review      = data.get("needs_review", False),
        created_by        = cu.id,
    )
    db.add(sa)
    if data.get("accepted_user_id"):
        p = db.query(SemProfile).filter(
            SemProfile.user_id == data["accepted_user_id"]).first()
        if p:
            if data.get("item_type") == "ticket":
                p.open_tickets = max(0, (p.open_tickets or 0) + 1)
            else:
                p.open_tasks = max(0, (p.open_tasks or 0) + 1)
    db.commit()
    return {"ok": True}
