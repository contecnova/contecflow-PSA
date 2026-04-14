"""
semantic_engine.py — API del motor de asignacion semantica
Endpoints para:
  - Configuracion del motor (modo, umbrales, auto-asignacion)
  - Sugerencia de asignacion para tickets y tareas
  - Estimacion de esfuerzo
  - Priorizacion de cola
  - Gestion de perfiles de usuario
  - Feedback de experto (correccion manual)
  - Estadisticas y calibracion
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel
import json

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter()
VALID_ENGINE_MODES = {"semantic", "llm", "hybrid", "rules_only"}


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


def _get_assigner(db):
    from app.services.semantic_classifier import SemanticAssigner
    return SemanticAssigner(db)


def _get_or_create_config(db):
    from app.models.semantic_engine import SemConfig
    cfg = db.query(SemConfig).first()
    if not cfg:
        cfg = SemConfig()
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


# ── Configuracion ─────────────────────────────────────────────────────────────

@router.get("/config")
def get_config(db: Session = Depends(get_db), _=Depends(get_current_user)):
    cfg = _get_or_create_config(db)
    return {
        "engine_mode":            str(cfg.engine_mode.value if hasattr(cfg.engine_mode, "value") else cfg.engine_mode),
        "threshold_ticket":       cfg.threshold_ticket,
        "threshold_task":         cfg.threshold_task,
        "threshold_expert_cache": cfg.threshold_expert_cache,
        "load_balance_weight":    cfg.load_balance_weight,
        "threshold_critical":      getattr(cfg, "threshold_critical", 0.80),
        "threshold_high":          getattr(cfg, "threshold_high", 0.70),
        "threshold_medium":        getattr(cfg, "threshold_medium", 0.55),
        "threshold_low":           getattr(cfg, "threshold_low", 0.45),
        "history_decay_days":      getattr(cfg, "history_decay_days", 90.0),
        "auto_assign_tickets":    cfg.auto_assign_tickets,
        "auto_assign_tasks":      cfg.auto_assign_tasks,
        "local_model_name":       cfg.local_model_name,
    }


@router.patch("/config")
def update_config(data: SemConfigPatch = Body(...),
                  db: Session = Depends(get_db),
                  _=Depends(get_current_user)):
    cfg = _get_or_create_config(db)
    allowed = {"engine_mode", "threshold_ticket", "threshold_task",
               "threshold_expert_cache", "load_balance_weight",
               "threshold_critical", "threshold_high", "threshold_medium",
               "threshold_low", "history_decay_days",
               "auto_assign_tickets", "auto_assign_tasks", "local_model_name"}
    payload = data.model_dump(exclude_unset=True)
    if "engine_mode" in payload:
        payload["engine_mode"] = str(payload["engine_mode"]).strip().lower()
        if payload["engine_mode"] not in VALID_ENGINE_MODES:
            raise HTTPException(400, f"engine_mode inválido. Use uno de: {', '.join(sorted(VALID_ENGINE_MODES))}")
    for k, v in payload.items():
        if k in allowed and hasattr(cfg, k):
            setattr(cfg, k, v)
    db.commit()
    db.refresh(cfg)
    return {
        "ok": True,
        "config": {
            "engine_mode": str(cfg.engine_mode.value if hasattr(cfg.engine_mode, "value") else cfg.engine_mode),
            "threshold_ticket": cfg.threshold_ticket,
            "threshold_task": cfg.threshold_task,
            "threshold_expert_cache": cfg.threshold_expert_cache,
            "load_balance_weight": cfg.load_balance_weight,
            "threshold_critical": getattr(cfg, "threshold_critical", 0.80),
            "threshold_high": getattr(cfg, "threshold_high", 0.70),
            "threshold_medium": getattr(cfg, "threshold_medium", 0.55),
            "threshold_low": getattr(cfg, "threshold_low", 0.45),
            "history_decay_days": getattr(cfg, "history_decay_days", 90.0),
            "auto_assign_tickets": cfg.auto_assign_tickets,
            "auto_assign_tasks": cfg.auto_assign_tasks,
            "local_model_name": cfg.local_model_name,
        }
    }


# ── Sugerencia de asignacion ──────────────────────────────────────────────────

@router.post("/suggest/ticket")
def suggest_ticket_assignee(data: dict = Body(...),
                             db: Session = Depends(get_db),
                             cu=Depends(get_current_user)):
    """
    Sugiere el mejor agente para un ticket.
    Body: {title, description, candidate_user_ids (opcional)}
    """
    title    = data.get("title", "")
    desc     = data.get("description", "")
    if not title:
        raise HTTPException(400, "title requerido")
    candidates = data.get("candidate_user_ids")
    priority   = data.get("priority", "medium")
    assigner   = _get_assigner(db)
    result     = assigner.suggest_for_ticket(title, desc, candidates, priority=priority)
    # Enriquecer con nombre del usuario sugerido
    if result.get("suggested_user_id"):
        u = db.query(User).filter(User.id == result["suggested_user_id"]).first()
        result["suggested_user_name"] = u.full_name if u else None
    # Enriquecer top_scores con nombres
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
    """
    Sugiere el mejor miembro de equipo para una tarea.
    Body: {title, description, project_id (opcional), candidate_user_ids (opcional)}
    """
    title      = data.get("title", "")
    desc       = data.get("description", "")
    if not title:
        raise HTTPException(400, "title requerido")
    project_id = data.get("project_id")
    candidates = data.get("candidate_user_ids")
    # Si hay project_id, filtrar por miembros del proyecto
    if project_id and not candidates:
        from app.models.project import ProjectMember
        members    = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id).all()
        candidates = [m.user_id for m in members]
    priority = data.get("priority", "medium")
    assigner = _get_assigner(db)
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
    """
    Estima horas para una tarea segun complejidad.
    Equivalente al EffortEstimator de Ficosa.
    Body: {title, description, role_hint (opcional)}
    """
    title     = data.get("title", "")
    desc      = data.get("description", "")
    role_hint = data.get("role_hint", "default")
    assigner  = _get_assigner(db)
    return assigner.estimate_effort(title, desc, role_hint)


@router.post("/estimate/sprint-backlog")
def estimate_sprint_backlog(data: dict = Body(...),
                            db: Session = Depends(get_db),
                            _=Depends(get_current_user)):
    """
    Estima esfuerzo para un listado de tareas de sprint.
    Equivalente al EffortEstimator en batch de Ficosa.
    Body: {tasks: [{id, title, description, story_points}], team_capacity_hours}
    """
    tasks      = data.get("tasks", [])
    capacity_h = data.get("team_capacity_hours", 80)
    assigner   = _get_assigner(db)

    estimates     = []
    total_hours   = 0.0
    complex_count = 0

    for t in tasks:
        est = assigner.estimate_effort(
            t.get("title", ""),
            t.get("description", ""),
            t.get("role_hint", "default")
        )
        total_hours   += est["base_hours"]
        if est["complexity"] == "complex": complex_count += 1
        estimates.append({
            "task_id":    t.get("id"),
            "title":      t.get("title", "")[:100],
            "story_points": t.get("story_points"),
            **est
        })

    # Prima de riesgo identica a Ficosa
    risk_pct = 10
    if complex_count / max(len(tasks), 1) > 0.3: risk_pct += 10
    recommended = round(total_hours * (1 + risk_pct / 100), 1)

    return {
        "estimates":           estimates,
        "total_base_hours":    round(total_hours, 1),
        "risk_premium_pct":    risk_pct,
        "recommended_hours":   recommended,
        "capacity_hours":      capacity_h,
        "fit_in_sprint":       recommended <= capacity_h,
        "utilization_pct":     round(recommended / capacity_h * 100) if capacity_h else 0,
        "complex_task_count":  complex_count,
    }


# ── Priorizacion de cola ──────────────────────────────────────────────────────

@router.post("/prioritize")
def prioritize_queue(data: dict = Body(...),
                     db: Session = Depends(get_db),
                     _=Depends(get_current_user)):
    """
    Prioriza una cola de tickets/tareas por valor.
    Equivalente al ActiveLearningPrioritizer de Ficosa.
    Body: {items: [{id, title, priority, confidence, assigned_to, ...}]}
    """
    items    = data.get("items", [])
    assigner = _get_assigner(db)
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
            "has_embedding":bool(p.embedding),
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
    """
    Crea o actualiza el perfil semantico de un usuario.
    El profile_text debe describir sus capacidades: rol, skills, experiencia.
    """
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

    # Generar embedding
    if profile_text:
        assigner = _get_assigner(db)
        emb      = assigner._encode_single(profile_text)
        profile.embedding = json.dumps(emb)

    db.commit()
    db.refresh(profile)
    return {"ok": True, "has_embedding": bool(profile.embedding)}


@router.post("/profiles/auto-generate")
def auto_generate_profiles(db: Session = Depends(get_db),
                            _=Depends(get_current_user)):
    """
    Genera perfiles automaticamente para todos los usuarios activos
    basandose en job_title, department y historial de tickets/tareas resueltos.
    """
    from app.models.semantic_engine import SemProfile
    from app.models.service_desk import Ticket
    from app.models.task import Task

    users = db.query(User).filter(User.is_active == True).all()
    assigner = _get_assigner(db)
    created = updated = 0

    for u in users:
        # Construir texto del perfil
        parts = []
        if u.full_name:    parts.append(u.full_name)
        if u.job_title:    parts.append(u.job_title)
        if u.department:   parts.append(u.department)

        # Historial de tickets resueltos (ultimos 20)
        resolved = db.query(Ticket).filter(
            Ticket.assigned_to_user_id == u.id,
            Ticket.status.in_(["resolved", "closed"])
        ).order_by(Ticket.resolved_at.desc()).limit(20).all()
        for t in resolved[:5]:
            parts.append(f"Ticket resuelto: {t.title}")

        # Historial de tareas completadas (ultimas 20)
        done = db.query(Task).filter(
            Task.assignee_id == u.id,
            Task.status == "done"
        ).order_by(Task.updated_at.desc()).limit(20).all()
        for t in done[:5]:
            parts.append(f"Tarea completada: {t.title}")

        profile_text = ". ".join(parts)
        if not profile_text.strip():
            continue

        profile = db.query(SemProfile).filter(
            SemProfile.user_id == u.id).first()
        if not profile:
            profile = SemProfile(user_id=u.id)
            db.add(profile)
            created += 1
        else:
            updated += 1

        profile.profile_text = profile_text
        emb = assigner._encode_single(profile_text)
        profile.embedding = json.dumps(emb)

    db.commit()
    return {"created": created, "updated": updated,
            "total": created + updated}


@router.post("/profiles/rebuild-embeddings")
def rebuild_embeddings(db: Session = Depends(get_db),
                       _=Depends(get_current_user)):
    """Reconstruye todos los embeddings (tras cambiar el modelo)."""
    assigner = _get_assigner(db)
    n = assigner.rebuild_profiles()
    return {"rebuilt": n}


# ── Feedback de experto ───────────────────────────────────────────────────────

@router.post("/feedback")
def record_feedback(data: dict = Body(...),
                    db: Session = Depends(get_db),
                    cu=Depends(get_current_user)):
    """
    Registra una correccion de experto.
    Equivalente a guardar en el Expert Cache de Ficosa.

    Mejora 5: si original_engine_mode == "llm" y confirmed == True,
    el manager está aceptando la sugerencia del LLM — se persiste
    con corrected_by="manager_confirm:<user_id>" para distinguirlo
    de correcciones manuales y para que futuros items similares
    sean resueltos por nivel 1/2 en lugar de llegar al nivel LLM.
    """
    item_id              = data.get("item_id", "")
    item_type            = data.get("item_type", "ticket")
    item_text            = data.get("item_text", "")
    correct_user_id      = data.get("correct_user_id", "")
    original_engine_mode = data.get("original_engine_mode", "")
    confirmed            = bool(data.get("confirmed", False))
    if not item_text or not correct_user_id:
        raise HTTPException(400, "item_text y correct_user_id requeridos")
    assigner = _get_assigner(db)
    # Determinar fuente del feedback para trazabilidad analítica
    corrected_by = cu.id
    if original_engine_mode == "llm" and confirmed:
        # Confirmación explícita de sugerencia LLM → marcar para analytics
        corrected_by = f"manager_confirm:{cu.id}"
    assigner.record_feedback(item_id, item_type, item_text,
                             correct_user_id, corrected_by)
    # Actualizar el historial en la cache de embeddings
    _cache_item_embedding(db, item_id, item_type, item_text, correct_user_id)
    llm_confirmed = original_engine_mode == "llm" and confirmed
    return {"ok": True, "persisted_as_expert": llm_confirmed}


def _cache_item_embedding(db, item_id: str, item_type: str,
                           text: str, user_id: str):
    """Guarda el embedding de un item resuelto en la cache."""
    from app.models.semantic_engine import SemEmbeddingCache
    import hashlib
    h    = hashlib.sha256(" ".join(text.strip().lower().split()).encode()).hexdigest()
    exist = db.query(SemEmbeddingCache).filter(
        SemEmbeddingCache.text_hash == h).first()
    if exist:
        exist.assigned_user_id = user_id
        db.commit()
        return
    assigner = _get_assigner(db)
    emb = assigner._encode_single(text)
    cache = SemEmbeddingCache(
        item_type=item_type, item_id=item_id,
        text_hash=h, text_snippet=text[:300],
        embedding=json.dumps(emb), assigned_user_id=user_id
    )
    db.add(cache)
    db.commit()


# ── Estadisticas ──────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats(db: Session = Depends(get_db), _=Depends(get_current_user)):
    from app.models.semantic_engine import (SemAssignment, SemProfile,
                                            SemFeedback, SemEmbeddingCache)
    from sqlalchemy import func

    total      = db.query(func.count(SemAssignment.id)).scalar() or 0
    accepted   = db.query(func.count(SemAssignment.id)).filter(
        SemAssignment.was_accepted == True).scalar() or 0
    rejected   = db.query(func.count(SemAssignment.id)).filter(
        SemAssignment.was_accepted == False).scalar() or 0
    pending    = db.query(func.count(SemAssignment.id)).filter(
        SemAssignment.was_accepted == None).scalar() or 0
    profiles   = db.query(func.count(SemProfile.id)).scalar() or 0
    cache_size = db.query(func.count(SemEmbeddingCache.id)).scalar() or 0
    feedback   = db.query(func.count(SemFeedback.id)).scalar() or 0

    accuracy = round(accepted / (accepted + rejected) * 100) \
               if (accepted + rejected) > 0 else None

    # Desglose por modo
    by_mode_rows = db.query(
        SemAssignment.engine_mode,
        func.count(SemAssignment.id)
    ).group_by(SemAssignment.engine_mode).all()

    return {
        "total_suggestions":  total,
        "accepted":           accepted,
        "rejected":           rejected,
        "pending":            pending,
        "accuracy_pct":       accuracy,
        "profiles":           profiles,
        "cache_size":         cache_size,
        "expert_feedback":    feedback,
        "by_mode":            {r[0]: r[1] for r in by_mode_rows},
    }


@router.post("/record-assignment")
def record_assignment(data: dict = Body(...),
                      db: Session = Depends(get_db),
                      cu=Depends(get_current_user)):
    """Guarda una asignacion en el historial para calibracion posterior."""
    from app.models.semantic_engine import SemAssignment
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
    # Actualizar carga del usuario asignado
    if data.get("accepted_user_id"):
        from app.models.semantic_engine import SemProfile
        p = db.query(SemProfile).filter(
            SemProfile.user_id == data["accepted_user_id"]).first()
        if p:
            if data.get("item_type") == "ticket":
                p.open_tickets = max(0, (p.open_tickets or 0) + 1)
            else:
                p.open_tasks = max(0, (p.open_tasks or 0) + 1)
    db.commit()
    return {"ok": True}
