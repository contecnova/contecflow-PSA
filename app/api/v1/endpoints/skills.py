from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import Optional, List
from datetime import date
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_hr
from app.models.user import User, UserRole
from app.models.resources import Skill, UserSkill, SkillHistory

router = APIRouter()

LEVEL_LABELS = {"basic": "Básico", "intermediate": "Intermedio", "advanced": "Avanzado", "expert": "Experto"}
CAT_LABELS = {"technical": "Técnico", "language": "Idioma", "methodology": "Metodología", "tool": "Herramienta", "soft": "Habilidad blanda", "certification": "Certificación"}


class SkillIn(BaseModel):
    name: str
    category: str
    description: Optional[str] = None

class UserSkillIn(BaseModel):
    skill_id: str
    level: str
    years_experience: Optional[float] = None
    certified: bool = False
    cert_name: Optional[str] = None
    cert_expiry: Optional[date] = None
    notes: Optional[str] = None

class StaffingQuery(BaseModel):
    skill_ids: List[str]
    min_level: str = "basic"
    available_from: Optional[date] = None
    available_weeks: int = 1


# ── Skill catalog ─────────────────────────────────────────────────────────────

@router.get("/catalog", summary="Catálogo de skills")
def get_catalog(
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Skill).filter(Skill.is_active == True)
    if category:
        q = q.filter(Skill.category == category)
    skills = q.order_by(Skill.category, Skill.name).all()
    return [{
        "id": s.id, "name": s.name, "category": s.category,
        "category_label": CAT_LABELS.get(s.category, s.category),
        "description": s.description,
        "user_count": len(s.user_skills),
    } for s in skills]


@router.post("/catalog", summary="Crear skill")
def create_skill(
    payload: SkillIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    if db.query(Skill).filter(Skill.name == payload.name).first():
        raise HTTPException(400, "Ya existe un skill con ese nombre")
    s = Skill(**payload.model_dump())
    db.add(s); db.commit(); db.refresh(s)
    return {"id": s.id, "name": s.name, "category": s.category}


@router.patch("/catalog/{skill_id}", summary="Actualizar skill")
def update_skill(
    skill_id: str,
    payload: SkillIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    s = db.query(Skill).filter(Skill.id == skill_id).first()
    if not s: raise HTTPException(404, "Skill no encontrado")
    for k, v in payload.model_dump().items(): setattr(s, k, v)
    db.commit(); db.refresh(s)
    return {"id": s.id, "name": s.name}


@router.delete("/catalog/{skill_id}", summary="Eliminar skill")
def delete_skill(
    skill_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    s = db.query(Skill).filter(Skill.id == skill_id).first()
    if not s: raise HTTPException(404, "Skill no encontrado")
    s.is_active = False; db.commit()
    return {"ok": True}


# ── User skills ───────────────────────────────────────────────────────────────

@router.get("/users/{user_id}", summary="Skills de un usuario")
def get_user_skills(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    skills = db.query(UserSkill).options(
        joinedload(UserSkill.skill)
    ).filter(UserSkill.user_id == user_id).all()

    return [{
        "id": us.id,
        "skill_id": us.skill_id,
        "skill_name": us.skill.name if us.skill else "—",
        "category": us.skill.category if us.skill else "—",
        "category_label": CAT_LABELS.get(us.skill.category, us.skill.category) if us.skill else "—",
        "level": us.level,
        "level_label": LEVEL_LABELS.get(us.level, us.level),
        "years_experience": us.years_experience,
        "certified": us.certified,
        "cert_name": us.cert_name,
        "cert_expiry": str(us.cert_expiry) if us.cert_expiry else None,
        "notes": us.notes,
    } for us in skills]


@router.post("/users/{user_id}", summary="Añadir skill a usuario")
def add_user_skill(
    user_id: str,
    payload: UserSkillIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.admin, UserRole.hr] and current_user.id != user_id:
        raise HTTPException(403, "Solo puedes editar tus propios skills")
    # Check duplicate
    existing = db.query(UserSkill).filter(
        UserSkill.user_id == user_id, UserSkill.skill_id == payload.skill_id
    ).first()
    if existing:
        old_level = existing.level
        for k, v in payload.model_dump().items(): setattr(existing, k, v)
        # Registrar en historial si el nivel cambió
        if str(old_level) != str(payload.level):
            import uuid as _uuid2
            db.add(SkillHistory(
                id=str(_uuid2.uuid4()), user_id=user_id,
                skill_id=payload.skill_id,
                old_level=old_level, new_level=payload.level,
                notes="Actualizado desde edición de skills",
                recorded_by=current_user.id,
            ))
        db.commit(); db.refresh(existing)
        return {"id": existing.id, "message": "Skill actualizado"}
    us = UserSkill(user_id=user_id, **payload.model_dump())
    db.add(us)
    import uuid as _uuid2
    db.add(SkillHistory(
        id=str(_uuid2.uuid4()), user_id=user_id,
        skill_id=payload.skill_id,
        old_level=None, new_level=payload.level,
        notes="Skill añadido inicialmente",
        recorded_by=current_user.id,
    ))
    db.commit(); db.refresh(us)
    return {"id": us.id, "message": "Skill añadido"}


@router.delete("/users/{user_id}/{skill_id}", summary="Eliminar skill de usuario")
def remove_user_skill(
    user_id: str,
    skill_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.admin, UserRole.hr] and current_user.id != user_id:
        raise HTTPException(403, "Acceso denegado")
    us = db.query(UserSkill).filter(UserSkill.id == skill_id).first()
    if not us: raise HTTPException(404, "No encontrado")
    db.delete(us); db.commit()
    return {"ok": True}


# ── Staffing search ───────────────────────────────────────────────────────────

@router.get("/search", summary="Buscar recursos por skills")
def search_by_skills(
    skill_ids: str = Query(..., description="Comma-separated skill IDs"),
    min_level: str = Query("basic"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    """Find users who have all the required skills at minimum level."""
    level_order = {"basic": 1, "intermediate": 2, "advanced": 3, "expert": 4}
    min_score = level_order.get(min_level, 1)
    ids = [s.strip() for s in skill_ids.split(",") if s.strip()]

    # Find users with matching skills
    user_skill_data = db.query(
        UserSkill.user_id,
        UserSkill.skill_id,
        UserSkill.level,
        UserSkill.years_experience,
        UserSkill.certified,
        User.full_name,
        User.department,
        User.role,
        User.is_active,
        Skill.name.label("skill_name"),
    ).join(User, User.id == UserSkill.user_id).join(Skill, Skill.id == UserSkill.skill_id).filter(
        UserSkill.skill_id.in_(ids),
        User.is_active == True,
    ).all()

    # Group by user
    users_data = {}
    for row in user_skill_data:
        if row.user_id not in users_data:
            users_data[row.user_id] = {
                "user_id": row.user_id, "user_name": row.full_name,
                "department": row.department, "role": row.role,
                "matching_skills": [], "skill_count": 0,
            }
        score = level_order.get(row.level, 1)
        if score >= min_score:
            users_data[row.user_id]["matching_skills"].append({
                "skill_id": row.skill_id, "skill_name": row.skill_name,
                "level": row.level, "level_label": LEVEL_LABELS.get(row.level, row.level),
                "years_experience": row.years_experience, "certified": row.certified,
            })
            users_data[row.user_id]["skill_count"] += 1

    # Filter users who have ALL required skills
    result = [u for u in users_data.values() if len(set(s["skill_id"] for s in u["matching_skills"])) == len(ids)]
    result.sort(key=lambda x: x["skill_count"], reverse=True)
    return result


@router.get("/matrix", summary="Matriz de skills del equipo")
def get_skills_matrix(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    """Returns a matrix of users × skills."""
    users = db.query(User).filter(User.is_active == True).order_by(User.full_name).all()
    skills = db.query(Skill).filter(Skill.is_active == True).order_by(Skill.category, Skill.name).all()
    user_skills = db.query(UserSkill).all()

    # Build lookup
    lookup = {(us.user_id, us.skill_id): us for us in user_skills}

    return {
        "skills": [{"id": s.id, "name": s.name, "category": s.category, "category_label": CAT_LABELS.get(s.category, s.category)} for s in skills],
        "users": [{
            "user_id": u.id,
            "user_name": u.full_name,
            "department": u.department,
            "skills": {
                s.id: {
                    "level": lookup[(u.id, s.id)].level if (u.id, s.id) in lookup else None,
                    "level_label": LEVEL_LABELS.get(lookup[(u.id, s.id)].level, "") if (u.id, s.id) in lookup else None,
                    "certified": lookup[(u.id, s.id)].certified if (u.id, s.id) in lookup else False,
                } for s in skills
            }
        } for u in users]
    }

# ── Historial de niveles por usuario/skill ────────────────────────────────────
@router.get("/users/{user_id}/history", summary="Historial de cambios de nivel")
def get_skill_history(
    user_id: str,
    skill_id: Optional[str] = None,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = db.query(SkillHistory).filter(SkillHistory.user_id == user_id)
    if skill_id: q = q.filter(SkillHistory.skill_id == skill_id)
    entries = q.order_by(SkillHistory.recorded_at.desc()).limit(100).all()
    return [
        {
            "id":          e.id,
            "skill_id":    e.skill_id,
            "skill_name":  e.skill.name if e.skill else "—",
            "old_level":   e.old_level,
            "new_level":   e.new_level,
            "notes":       e.notes,
            "recorded_by": e.recorder.full_name if e.recorder else "Sistema",
            "recorded_at": str(e.recorded_at)[:19] if e.recorded_at else None,
        }
        for e in entries
    ]


@router.post("/users/{user_id}/history", summary="Registrar evaluación manual de skill",
             status_code=201)
def record_skill_assessment(
    user_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_hr),
):
    """Registra explícitamente un cambio de nivel evaluado por un manager/RRHH."""
    import uuid as _uuid
    skill_id  = payload.get("skill_id")
    new_level = payload.get("new_level")
    notes     = payload.get("notes")
    if not skill_id or not new_level:
        raise HTTPException(400, "skill_id y new_level son obligatorios")
    # Obtener nivel actual
    us = db.query(UserSkill).filter(
        UserSkill.user_id == user_id, UserSkill.skill_id == skill_id
    ).first()
    old_level = us.level if us else None
    entry = SkillHistory(
        id=str(_uuid.uuid4()),
        user_id=user_id, skill_id=skill_id,
        old_level=old_level, new_level=new_level,
        notes=notes, recorded_by=cu.id,
    )
    db.add(entry)
    # Actualizar nivel actual si existe el UserSkill
    if us:
        us.level = new_level
    db.commit()
    return {"id": entry.id, "old_level": str(old_level) if old_level else None,
            "new_level": new_level}

