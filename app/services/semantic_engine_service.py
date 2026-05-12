"""
Semantic engine service — business logic extracted from semantic_engine.py router.
"""
from sqlalchemy.orm import Session
import json
from app.models.project import ProjectMember
from app.models.semantic_engine import SemConfig
from app.models.semantic_engine import SemEmbeddingCache
from app.models.semantic_engine import SemProfile
from app.models.semantic_engine import SemAssignment, SemFeedback
from app.models.service_desk import Ticket
from app.models.task import Task
from app.models.user import User
from app.services.semantic_classifier import SemanticAssigner
from sqlalchemy import func


VALID_ENGINE_MODES = {"semantic", "llm", "hybrid", "rules_only"}


def resolve_embeddings_backend_and_model(cfg) -> tuple[str, str]:
    """Return normalized embeddings backend and model name for UI/runtime visibility."""
    model = (getattr(cfg, "local_model_name", "") or "").strip()
    if model and model.lower() != "tfidf":
        return "transformer", model
    return "tfidf", "all-MiniLM-L6-v2"


def get_assigner(db: Session):
    return SemanticAssigner(db)


def get_or_create_config(db: Session):
    cfg = db.query(SemConfig).first()
    if not cfg:
        cfg = SemConfig()
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def serialize_config(cfg) -> dict:
    embeddings_backend, effective_model_name = resolve_embeddings_backend_and_model(cfg)
    return {
        "engine_mode":            str(cfg.engine_mode.value if hasattr(cfg.engine_mode, "value") else cfg.engine_mode),
        "threshold_ticket":       cfg.threshold_ticket,
        "threshold_task":         cfg.threshold_task,
        "threshold_expert_cache": cfg.threshold_expert_cache,
        "load_balance_weight":    cfg.load_balance_weight,
        "threshold_critical":     getattr(cfg, "threshold_critical", 0.80),
        "threshold_high":         getattr(cfg, "threshold_high", 0.70),
        "threshold_medium":       getattr(cfg, "threshold_medium", 0.55),
        "threshold_low":          getattr(cfg, "threshold_low", 0.45),
        "history_decay_days":     getattr(cfg, "history_decay_days", 90.0),
        "auto_assign_tickets":    cfg.auto_assign_tickets,
        "auto_assign_tasks":      cfg.auto_assign_tasks,
        "embeddings_backend":     embeddings_backend,
        "local_model_name":       cfg.local_model_name,
        "effective_model_name":   effective_model_name,
    }


def cache_item_embedding(db: Session, item_id: str, item_type: str,
                         text: str, user_id: str):
    """Save the embedding of a resolved item into the cache."""
    import hashlib
    h = hashlib.sha256(" ".join(text.strip().lower().split()).encode()).hexdigest()
    exist = db.query(SemEmbeddingCache).filter(
        SemEmbeddingCache.text_hash == h).first()
    if exist:
        exist.assigned_user_id = user_id
        db.commit()
        return
    assigner = get_assigner(db)
    emb = assigner._encode_single(text)
    cache = SemEmbeddingCache(
        item_type=item_type, item_id=item_id,
        text_hash=h, text_snippet=text[:300],
        embedding=json.dumps(emb), assigned_user_id=user_id,
    )
    db.add(cache)
    db.commit()


def auto_generate_profiles(db: Session, *, organization_id=None, is_superadmin: bool = False) -> dict:
    """Auto-generate semantic profiles for active users.

    Si ``organization_id`` es provisto y el caller no es superadmin, solo
    procesa users de esa organización. Antes este servicio iteraba
    User.is_active=True sin filtro → cross-tenant verificado (9 perfiles en
    2 orgs distintas).
    """
    q = db.query(User).filter(User.is_active == True)
    if organization_id and not is_superadmin:
        q = q.filter(User.organization_id == organization_id)
    users = q.all()
    assigner = get_assigner(db)
    created = updated = 0

    for u in users:
        parts = []
        if u.full_name:  parts.append(u.full_name)
        if u.job_title:  parts.append(u.job_title)
        if u.department: parts.append(u.department)

        resolved = db.query(Ticket).filter(
            Ticket.assigned_to_user_id == u.id,
            Ticket.status.in_(["resolved", "closed"])
        ).order_by(Ticket.resolved_at.desc()).limit(20).all()
        for t in resolved[:5]:
            parts.append(f"Ticket resuelto: {t.title}")

        done = db.query(Task).filter(
            Task.assignee_id == u.id,
            Task.status == "done"
        ).order_by(Task.updated_at.desc()).limit(20).all()
        for t in done[:5]:
            parts.append(f"Tarea completada: {t.title}")

        profile_text = ". ".join(parts)
        if not profile_text.strip():
            continue

        profile = db.query(SemProfile).filter(SemProfile.user_id == u.id).first()
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
    return {"created": created, "updated": updated, "total": created + updated}


def save_config(db: Session, cfg) -> None:
    """Commit and refresh a config object."""
    db.commit()
    db.refresh(cfg)


def enrich_suggestion(db: Session, result: dict, *, organization_id=None,
                       is_superadmin: bool = False) -> dict:
    """Add user name fields to a suggestion result dict (mutates in place).

    Multi-tenant: si ``organization_id`` se provee y el caller no es
    superadmin, solo expone full_name de users de esa org. Antes este enrich
    leía cualquier user.id sin filtro → leak menor de full_name cross-tenant.
    """
    def _safe_user(uid):
        if not uid:
            return None
        q = db.query(User).filter(User.id == uid)
        if organization_id and not is_superadmin:
            q = q.filter(User.organization_id == organization_id)
        return q.first()

    if result.get("suggested_user_id"):
        u = _safe_user(result["suggested_user_id"])
        result["suggested_user_name"] = u.full_name if u else None
    if result.get("top_scores"):
        enriched = {}
        for uid, score in result["top_scores"].items():
            u = _safe_user(uid)
            enriched[uid] = {"score": score, "name": u.full_name if u else "(fuera de tu organización)"}
        result["top_candidates"] = enriched
    return result


def get_project_member_ids(db: Session, project_id) -> list:
    """Return user_ids of all members of a project."""
    members = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id).all()
    return [m.user_id for m in members]


def list_profiles_with_users(db: Session) -> list:
    """Return all semantic profiles enriched with user names."""
    from app.models.user import User
    org_id = db.info.get("organization_id")
    is_superadmin = db.info.get("is_superadmin", False)
    query = db.query(SemProfile)
    if not is_superadmin:
        # Non-superadmins without an organisation must see zero rows (not all rows)
        if not org_id:
            return []
        from sqlalchemy import select as sa_select
        user_ids_sq = (
            sa_select(User.id)
            .where(User.organization_id == org_id)
            .scalar_subquery()
        )
        query = query.filter(SemProfile.user_id.in_(user_ids_sq))
    profiles = query.all()
    result = []
    for p in profiles:
        u = db.query(User).filter(User.id == p.user_id).first()
        result.append({
            "id":            p.id,
            "user_id":       p.user_id,
            "user_name":     u.full_name if u else None,
            "profile_text":  p.profile_text[:200] if p.profile_text else "",
            "has_embedding": bool(p.embedding),
            "open_tickets":  p.open_tickets,
            "open_tasks":    p.open_tasks,
            "max_load":      p.max_load,
            "is_available":  p.is_available,
        })
    return result


def upsert_profile(db: Session, user_id, profile_text: str,
                   max_load=None, is_available: bool = True,
                   *, current_user=None) -> dict:
    """Create or update a semantic profile and return status dict.

    Authorization: si ``current_user`` se provee, sólo permite que el propio
    usuario, un admin/HR de su organización o un superadmin modifique el
    perfil. Antes cualquier user autenticado podía editar el perfil de otro
    pasando ``user_id`` en el body.
    """
    if current_user is not None:
        is_super = bool(getattr(current_user, "is_superadmin", False))
        is_self  = str(getattr(current_user, "id", "")) == str(user_id)
        role     = getattr(current_user, "role", None)
        role_val = role.value if hasattr(role, "value") else role
        is_priv  = role_val in ("admin", "hr")
        if not (is_super or is_self or is_priv):
            raise PermissionError("No tienes permisos para modificar este perfil")
        # Validación adicional para admin/hr: solo de su org
        target = db.query(User).filter(User.id == user_id).first()
        if (not is_super and is_priv and target
                and target.organization_id != getattr(current_user, "organization_id", None)):
            raise PermissionError("Solo puedes modificar perfiles de tu organización")

    profile = db.query(SemProfile).filter(SemProfile.user_id == user_id).first()
    if not profile:
        profile = SemProfile(user_id=user_id)
        db.add(profile)
    profile.profile_text = profile_text
    profile.max_load     = max_load if max_load is not None else (profile.max_load or 10)
    profile.is_available = is_available
    if profile_text:
        assigner = get_assigner(db)
        emb = assigner._encode_single(profile_text)
        profile.embedding = json.dumps(emb)
    db.commit()
    db.refresh(profile)
    return {"ok": True, "has_embedding": bool(profile.embedding)}


def get_stats(db: Session) -> dict:
    """Compute and return semantic engine statistics."""
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
    accuracy   = round(accepted / (accepted + rejected) * 100) \
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


def record_assignment(db: Session, data: dict, created_by_id) -> dict:
    """Persist a SemAssignment and update the assignee's load counters."""
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
        created_by        = created_by_id,
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


def estimate_sprint_backlog(tasks: list, capacity_h: float, db: Session) -> dict:
    """Estimate effort for a list of sprint tasks."""
    assigner = get_assigner(db)
    estimates = []
    total_hours = 0.0
    complex_count = 0

    for t in tasks:
        est = assigner.estimate_effort(
            t.get("title", ""),
            t.get("description", ""),
            t.get("role_hint", "default"),
        )
        total_hours += est["base_hours"]
        if est["complexity"] == "complex":
            complex_count += 1
        estimates.append({
            "task_id": t.get("id"),
            "title": t.get("title", "")[:100],
            "story_points": t.get("story_points"),
            **est,
        })

    risk_pct = 10
    if complex_count / max(len(tasks), 1) > 0.3:
        risk_pct += 10
    recommended = round(total_hours * (1 + risk_pct / 100), 1)

    return {
        "estimates": estimates,
        "total_base_hours": round(total_hours, 1),
        "risk_premium_pct": risk_pct,
        "recommended_hours": recommended,
        "capacity_hours": capacity_h,
        "fit_in_sprint": recommended <= capacity_h,
        "utilization_pct": round(recommended / capacity_h * 100) if capacity_h else 0,
        "complex_task_count": complex_count,
    }
