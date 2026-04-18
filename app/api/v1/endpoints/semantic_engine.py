"""
semantic_engine.py — API del motor de asignacion semantica (thin router)
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.schemas.semantic_engine import SemConfigPatch
from app.db.session import get_db
from app.core.deps import get_current_user
import app.services.semantic_engine_service as _svc

router = APIRouter()

# Alias kept for backward compatibility with tests that patch this symbol
def _get_assigner(db):
    return _svc.get_assigner(db)

def _cache_item_embedding(db, item_id, item_type, text, user_id):
    return _svc.cache_item_embedding(db, item_id, item_type, text, user_id)




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
    _svc.save_config(db, cfg)
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
    return _svc.enrich_suggestion(db, result)


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
        candidates = _svc.get_project_member_ids(db, project_id)
    priority = data.get("priority", "medium")
    assigner = _svc.get_assigner(db)
    result   = assigner.suggest_for_task(title, desc, candidates, priority=priority)
    return _svc.enrich_suggestion(db, result)


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
    return _svc.list_profiles_with_users(db)


@router.post("/profiles")
def create_or_update_profile(data: dict = Body(...),
                              db: Session = Depends(get_db),
                              _=Depends(get_current_user)):
    user_id      = data.get("user_id")
    profile_text = data.get("profile_text", "")
    if not user_id:
        raise HTTPException(400, "user_id requerido")
    return _svc.upsert_profile(
        db,
        user_id=user_id,
        profile_text=profile_text,
        max_load=data.get("max_load"),
        is_available=data.get("is_available", True),
    )


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
    return _svc.get_stats(db)


@router.post("/record-assignment")
def record_assignment(data: dict = Body(...),
                      db: Session = Depends(get_db),
                      cu=Depends(get_current_user)):
    return _svc.record_assignment(db, data, cu.id)
