"""
semantic_engine.py — API del motor de asignacion semantica (thin router)
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.schemas.semantic_engine import SemConfigPatch
from app.db.session import get_db
from app.core.deps import get_current_user, requiere_capacidad
from app.core.responses import APIListResponse, APIResponse
import app.services.semantic_engine_service as _svc
from app.core.config import settings
from app.core.codigos_de_error import error_http, desde_valor

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
    return APIResponse.ok(data=_svc.serialize_config(cfg))


@router.patch("/config")
def update_config(data: SemConfigPatch = Body(...),
                  db: Session = Depends(get_db),
                  _=Depends(requiere_capacidad("ia.asignacion_config"))):
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
            raise error_http(400, "campo_no_valido_opciones", detail=f"engine_mode inválido. Use uno de: {', '.join(sorted(_svc.VALID_ENGINE_MODES))}", campo="engine_mode", opciones=', '.join(sorted(_svc.VALID_ENGINE_MODES)))

    # Normalize backend/model relationship without schema changes:
    # local_model_name="tfidf" is the explicit persisted toggle for TF-IDF mode.
    backend = payload.pop("embeddings_backend", None)
    if backend == "tfidf":
        payload["local_model_name"] = "tfidf"
    elif backend == "transformer":
        model_name = (payload.get("local_model_name") or cfg.local_model_name or "").strip()
        payload["local_model_name"] = model_name if model_name and model_name.lower() != "tfidf" else settings.EMBEDDING_MODEL_NAME

    if "local_model_name" in payload and isinstance(payload["local_model_name"], str):
        payload["local_model_name"] = payload["local_model_name"].strip()

    for k, v in payload.items():
        if k in allowed and hasattr(cfg, k):
            setattr(cfg, k, v)
    _svc.save_config(db, cfg)
    return APIResponse.ok(data={"ok": True, "config": _svc.serialize_config(cfg)})


# ── Sugerencia de asignacion ──────────────────────────────────────────────────

def _candidate_users_for_org(db: Session, current_user, explicit_candidates=None) -> list:
    """Resuelve candidatos por defecto: si no hay lista explícita, devuelve
    todos los users activos de la organización del current_user. Superadmin
    sin filtro. Antes este endpoint leía perfiles globalmente sin filtro org,
    permitiendo sugerir users de otra organización."""
    if explicit_candidates:
        return explicit_candidates
    from app.services import semantic_engine_service as _sem_svc

    return _sem_svc.ids_de_usuarios_del_ambito(db, current_user)


@router.post("/suggest/ticket")
def suggest_ticket_assignee(data: dict = Body(...),
                             db: Session = Depends(get_db),
    _rol = Depends(requiere_capacidad("ia.usar")),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
                             cu=Depends(get_current_user)):
    title = data.get("title", "")
    desc  = data.get("description", "")
    if not title:
        raise error_http(400, "campo_obligatorio", detail="title requerido", campo="title")
    candidates = _candidate_users_for_org(db, cu, data.get("candidate_user_ids"))
    priority   = data.get("priority", "medium")
    assigner   = _svc.get_assigner(db)
    result     = assigner.suggest_for_ticket(title, desc, candidates, priority=priority)
    return APIResponse.ok(data=_svc.enrich_suggestion(
        db, result,
        organization_id=getattr(cu, "organization_id", None),
        is_superadmin=bool(getattr(cu, "is_superadmin", False)),
    ))


@router.post("/suggest/task")
def suggest_task_assignee(data: dict = Body(...),
                          db: Session = Depends(get_db),
    _rol = Depends(requiere_capacidad("ia.usar")),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
                          cu=Depends(get_current_user)):
    title      = data.get("title", "")
    desc       = data.get("description", "")
    if not title:
        raise error_http(400, "campo_obligatorio", detail="title requerido", campo="title")
    project_id = data.get("project_id")
    candidates = data.get("candidate_user_ids")
    if project_id and not candidates:
        candidates = _svc.get_project_member_ids(db, project_id)
    candidates = _candidate_users_for_org(db, cu, candidates)
    priority = data.get("priority", "medium")
    assigner = _svc.get_assigner(db)
    result   = assigner.suggest_for_task(title, desc, candidates, priority=priority)
    return APIResponse.ok(data=_svc.enrich_suggestion(
        db, result,
        organization_id=getattr(cu, "organization_id", None),
        is_superadmin=bool(getattr(cu, "is_superadmin", False)),
    ))


# ── Estimacion de esfuerzo ────────────────────────────────────────────────────

@router.post("/estimate/effort")
def estimate_effort(data: dict = Body(...),
                    db: Session = Depends(get_db),
    _rol = Depends(requiere_capacidad("ia.usar")),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
                    _=Depends(get_current_user)):
    title     = data.get("title", "")
    desc      = data.get("description", "")
    role_hint = data.get("role_hint", "default")
    assigner  = _svc.get_assigner(db)
    return APIResponse.ok(data=assigner.estimate_effort(title, desc, role_hint))


@router.post("/estimate/sprint-backlog")
def estimate_sprint_backlog(data: dict = Body(...),
                            db: Session = Depends(get_db),
    _rol = Depends(requiere_capacidad("ia.usar")),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
                            _=Depends(get_current_user)):
    tasks      = data.get("tasks", [])
    # Default: 2 semanas × DEFAULT_WEEKLY_CAPACITY_HOURS. Antes hardcoded a 80,
    # ignorando la configuración global de capacity (40h/semana × 2 = 80, casual).
    # 18-11-2026: la capacidad semanal de la empresa, no la global del entorno.
    from app.services.settings_service.por_empresa import capacidad_semanal_de_empresa
    _default_h = capacidad_semanal_de_empresa(db) * 2
    capacity_h = data.get("team_capacity_hours", _default_h)
    return APIResponse.ok(data=_svc.estimate_sprint_backlog(tasks, capacity_h, db))


# ── Priorizacion de cola ──────────────────────────────────────────────────────

@router.post("/prioritize")
def prioritize_queue(data: dict = Body(...),
                     db: Session = Depends(get_db),
    _rol = Depends(requiere_capacidad("ia.rrhh")),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
                     _=Depends(get_current_user)):
    """Puntúa una lista dada (uso de integraciones). La pantalla usa `/review-queue`."""
    items    = data.get("items", [])
    assigner = _svc.get_assigner(db)
    return APIResponse.ok(data={"prioritized": assigner.prioritize_queue(items)})


@router.get("/review-queue", summary="Sugerencias pendientes de la empresa, las más útiles de revisar primero")
def review_queue(limit: int = 50, db: Session = Depends(get_db),
                 _rol=Depends(requiere_capacidad("ia.asignacion"))):
    """23-11-2026: el `ActiveLearningPrioritizer` aplicado a las sugerencias sin
    veredicto: un experto confirma o corrige las primeras (`POST /feedback`)."""
    return APIListResponse.ok(items=_svc.cola_de_revision(db, limit))


# ── Perfiles de usuario ───────────────────────────────────────────────────────

@router.get("/profiles")
def list_profiles(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return APIListResponse.ok(items=_svc.list_profiles_with_users(db))


@router.post("/profiles")
def create_or_update_profile(data: dict = Body(...),
                              db: Session = Depends(get_db),
    _rol = Depends(requiere_capacidad("ia.asignacion_config")),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
                              cu=Depends(get_current_user)):
    user_id      = data.get("user_id")
    profile_text = data.get("profile_text", "")
    if not user_id:
        raise error_http(400, "campo_obligatorio", detail="user_id requerido", campo="user_id")
    try:
        return APIResponse.ok(data=_svc.upsert_profile(
            db,
            user_id=user_id,
            profile_text=profile_text,
            max_load=data.get("max_load"),
            is_available=data.get("is_available", True),
            current_user=cu,
        ))
    except PermissionError as e:
        raise desde_valor(403, e)


@router.post("/profiles/auto-generate")
def auto_generate_profiles(db: Session = Depends(get_db),
                            cu=Depends(requiere_capacidad("ia.asignacion_config"))):
    return APIResponse.ok(data=_svc.auto_generate_profiles(
        db,
        organization_id=getattr(cu, "organization_id", None),
        is_superadmin=bool(getattr(cu, "is_superadmin", False)),
    ))


@router.post("/profiles/rebuild-embeddings")
def rebuild_embeddings(db: Session = Depends(get_db),
                       _=Depends(requiere_capacidad("ia.asignacion_config"))):
    assigner = _svc.get_assigner(db)
    n = assigner.rebuild_profiles()
    return APIResponse.ok(data={"rebuilt": n})


# ── Feedback de experto ───────────────────────────────────────────────────────

@router.post("/feedback")
def record_feedback(data: dict = Body(...),
                    db: Session = Depends(get_db),
    # 23-11-2026: «Corregir asignación» en tareas y tickets; la hacen quienes
    # asignan con IA (dirección, PM y RRHH), no solo dirección y RRHH.
    _rol = Depends(requiere_capacidad("ia.asignacion")),
                    cu=Depends(get_current_user)):
    """Corrige (o confirma) la persona de una asignación de la IA.

    23-11-2026: antes guardaba `corrected_by = "manager_confirm:<uuid>"` (52
    caracteres) en una columna `String(36)` con FK a `users.id`. Ahora
    `corrected_by` es el id y el tipo va en `correction_kind`
    (`semantic_engine_service.corregir_asignacion`).
    """
    return APIResponse.ok(data=_svc.corregir_asignacion(db, cu, data))


# ── Estadisticas ──────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return APIResponse.ok(data=_svc.get_stats(db))


@router.post("/record-assignment")
def record_assignment(data: dict = Body(...),
                      db: Session = Depends(get_db),
    # 23-11-2026: quien pide la sugerencia (`ia.usar`) registra que la aceptó; antes
    # pedía `ia.rrhh` y a un PM le fallaba en silencio (el bucle nunca tenía datos).
    # El veredicto lo pone el servidor y el ítem tiene que ser de la empresa.
    _rol = Depends(requiere_capacidad("ia.usar")),
                      cu=Depends(get_current_user)):
    return APIResponse.ok(data=_svc.record_assignment(db, data, cu.id))
