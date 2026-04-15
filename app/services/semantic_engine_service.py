"""
Semantic engine service — business logic extracted from semantic_engine.py router.
"""
from sqlalchemy.orm import Session
import json


VALID_ENGINE_MODES = {"semantic", "llm", "hybrid", "rules_only"}


def get_assigner(db: Session):
    from app.services.semantic_classifier import SemanticAssigner
    return SemanticAssigner(db)


def get_or_create_config(db: Session):
    from app.models.semantic_engine import SemConfig
    cfg = db.query(SemConfig).first()
    if not cfg:
        cfg = SemConfig()
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def serialize_config(cfg) -> dict:
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
        "local_model_name":       cfg.local_model_name,
    }


def cache_item_embedding(db: Session, item_id: str, item_type: str,
                         text: str, user_id: str):
    """Save the embedding of a resolved item into the cache."""
    from app.models.semantic_engine import SemEmbeddingCache
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


def auto_generate_profiles(db: Session) -> dict:
    """Auto-generate semantic profiles for all active users."""
    from app.models.semantic_engine import SemProfile
    from app.models.service_desk import Ticket
    from app.models.task import Task
    from app.models.user import User

    users = db.query(User).filter(User.is_active == True).all()
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
