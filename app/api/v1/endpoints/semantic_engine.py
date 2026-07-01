"""
semantic_engine.py — API del motor de asignacion semantica (thin router)
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.schemas.semantic_engine import SemConfigPatch
from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_hr
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
                  _=Depends(require_admin_or_hr)):
    cfg = _svc.get_or_create_config(db)
    allowed = {"engine_mode", "threshold_ticket", "threshold_task",
               "threshold_expert_cache", "load_balance_weight",
               "threshold_critical", "threshold_high", "threshold_medium",
               "threshold_low", "history_decay_days",
               "auto_assign_tickets", "auto_assign_tasks", "local_model_name", "embeddings_backend"}
    payload = data.model_dump(exclude_unset=True)
    if "engine_mode" in payload:
        payload["engine_mode"] = str(payload["engine_mode"]).strip().lower()
        if payload["engine_mode"] not in _svc.VALID_ENGINE_MODES:
            raise HTTPException(400, f"engine_mode inválido. Use uno de: {', '.join(sorted(_svc.VALID_ENGINE_MODES))}")

    # Normalize backend/model relationship without schema changes:
    # local_model_name="tfidf" is the explicit persisted toggle for TF-IDF mode.
    backend = payload.pop("embeddings_backend", None)
    if backend == "tfidf":
        payload["local_model_name"] = "tfidf"
    elif backend == "transformer":
        model_name = (payload.get("local_model_name") or cfg.local_model_name or "").strip()
        payload["local_model_name"] = model_name if model_name and model_name.lower() != "tfidf" else "all-MiniLM-L6-v2"

    if "local_model_name" in payload and isinstance(payload["local_model_name"], str):
        payload["local_model_name"] = payload["local_model_name"].strip()

    for k, v in payload.items():
        if k in allowed and hasattr(cfg, k):
            setattr(cfg, k, v)
    _svc.save_config(db, cfg)
    return {"ok": True, "config": _svc.serialize_config(cfg)}


# ── Sugerencia de asignacion ──────────────────────────────────────────────────

def _candidate_users_for_org(db: Session, current_user, explicit_candidates=None) -> list:
    """Resuelve candidatos por defecto: si no hay lista explícita, devuelve
    todos los users activos de la organización del current_user. Superadmin
    sin filtro. Antes este endpoint leía perfiles globalmente sin filtro org,
    permitiendo sugerir users de otra organización."""
    if explicit_candidates:
        return explicit_candidates
    if bool(getattr(current_user, "is_superadmin", False)):
        return None  # None == sin restricción, el assigner usa todos
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        return None
    from app.models.user import User
    return [u.id for u in db.query(User.id).filter(
        User.is_active == True, User.organization_id == org_id
    ).all()] or ["__none__"]


@router.post("/suggest/ticket")
def suggest_ticket_assignee(data: dict = Body(...),
                             db: Session = Depends(get_db),
                             cu=Depends(get_current_user)):
    title = data.get("title", "")
    desc  = data.get("description", "")
    if not title:
        raise HTTPException(400, "title requerido")
    candidates = _candidate_users_for_org(db, cu, data.get("candidate_user_ids"))
    priority   = data.get("priority", "medium")
    assigner   = _svc.get_assigner(db)
    result     = assigner.suggest_for_ticket(title, desc, candidates, priority=priority)
    return _svc.enrich_suggestion(
        db, result,
        organization_id=getattr(cu, "organization_id", None),
        is_superadmin=bool(getattr(cu, "is_superadmin", False)),
    )


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
    candidates = _candidate_users_for_org(db, cu, candidates)
    priority = data.get("priority", "medium")
    assigner = _svc.get_assigner(db)
    result   = assigner.suggest_for_task(title, desc, candidates, priority=priority)
    return _svc.enrich_suggestion(
        db, result,
        organization_id=getattr(cu, "organization_id", None),
        is_superadmin=bool(getattr(cu, "is_superadmin", False)),
    )


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
    # Default: 2 semanas × DEFAULT_WEEKLY_CAPACITY_HOURS. Antes hardcoded a 80,
    # ignorando la configuración global de capacity (40h/semana × 2 = 80, casual).
    from app.core.config import settings as _s  # noqa: PLC0415
    _default_h = float(getattr(_s, "DEFAULT_WEEKLY_CAPACITY_HOURS", 40.0) or 40.0) * 2
    capacity_h = data.get("team_capacity_hours", _default_h)
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
                              cu=Depends(get_current_user)):
    user_id      = data.get("user_id")
    profile_text = data.get("profile_text", "")
    if not user_id:
        raise HTTPException(400, "user_id requerido")
    try:
        return _svc.upsert_profile(
            db,
            user_id=user_id,
            profile_text=profile_text,
            max_load=data.get("max_load"),
            is_available=data.get("is_available", True),
            current_user=cu,
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.post("/profiles/auto-generate")
def auto_generate_profiles(db: Session = Depends(get_db),
                            cu=Depends(require_admin_or_hr)):
    return _svc.auto_generate_profiles(
        db,
        organization_id=getattr(cu, "organization_id", None),
        is_superadmin=bool(getattr(cu, "is_superadmin", False)),
    )


@router.post("/profiles/rebuild-embeddings")
def rebuild_embeddings(db: Session = Depends(get_db),
                       _=Depends(require_admin_or_hr)):
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
