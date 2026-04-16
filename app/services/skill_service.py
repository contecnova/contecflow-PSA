import uuid
from typing import Optional, List

from sqlalchemy.orm import Session, joinedload

from app.models.resources import Skill, UserSkill, SkillHistory
from app.models.user import User


# ── Skill catalog ──────────────────────────────────────────────────────────────

def get_catalog(db: Session, category: Optional[str] = None) -> List[Skill]:
    q = db.query(Skill).filter(Skill.is_active == True)
    if category:
        q = q.filter(Skill.category == category)
    return q.order_by(Skill.category, Skill.name).all()


def get_skill_by_id(db: Session, skill_id: str) -> Optional[Skill]:
    return db.query(Skill).filter(Skill.id == skill_id).first()


def get_skill_by_name(db: Session, name: str) -> Optional[Skill]:
    return db.query(Skill).filter(Skill.name == name).first()


def create_skill(db: Session, data: dict) -> Skill:
    s = Skill(**data)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def update_skill(db: Session, skill: Skill, data: dict) -> Skill:
    for k, v in data.items():
        setattr(skill, k, v)
    db.commit()
    db.refresh(skill)
    return skill


def deactivate_skill(db: Session, skill: Skill) -> None:
    skill.is_active = False
    db.commit()


# ── User skills ────────────────────────────────────────────────────────────────

def get_user_skills(db: Session, user_id: str) -> List[UserSkill]:
    return (
        db.query(UserSkill)
        .options(joinedload(UserSkill.skill))
        .filter(UserSkill.user_id == user_id)
        .all()
    )


def get_user_skill_by_skill_id(db: Session, user_id: str, skill_id: str) -> Optional[UserSkill]:
    return db.query(UserSkill).filter(
        UserSkill.user_id == user_id, UserSkill.skill_id == skill_id
    ).first()


def get_user_skill_by_id(db: Session, user_skill_id: str) -> Optional[UserSkill]:
    return db.query(UserSkill).filter(UserSkill.id == user_skill_id).first()


def upsert_user_skill(
    db: Session, user_id: str, payload: dict, recorded_by: str
) -> tuple:
    """
    Returns (user_skill, was_updated: bool).
    If the user already has the skill, updates it and records a history entry if level changed.
    Otherwise creates a new UserSkill and a history entry.
    """
    skill_id = payload["skill_id"]
    existing = get_user_skill_by_skill_id(db, user_id, skill_id)
    if existing:
        old_level = existing.level
        for k, v in payload.items():
            setattr(existing, k, v)
        if str(old_level) != str(payload["level"]):
            db.add(SkillHistory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                skill_id=skill_id,
                old_level=old_level,
                new_level=payload["level"],
                notes="Actualizado desde edición de skills",
                recorded_by=recorded_by,
            ))
        db.commit()
        db.refresh(existing)
        return existing, True
    us = UserSkill(user_id=user_id, **payload)
    db.add(us)
    db.add(SkillHistory(
        id=str(uuid.uuid4()),
        user_id=user_id,
        skill_id=skill_id,
        old_level=None,
        new_level=payload["level"],
        notes="Skill añadido inicialmente",
        recorded_by=recorded_by,
    ))
    db.commit()
    db.refresh(us)
    return us, False


def remove_user_skill(db: Session, us: UserSkill) -> None:
    db.delete(us)
    db.commit()


# ── Staffing search ────────────────────────────────────────────────────────────

def search_by_skills(db: Session, ids: List[str], min_level: str) -> List[dict]:
    level_order = {"basic": 1, "intermediate": 2, "advanced": 3, "expert": 4}
    min_score = level_order.get(min_level, 1)

    user_skill_data = (
        db.query(
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
        )
        .join(User, User.id == UserSkill.user_id)
        .join(Skill, Skill.id == UserSkill.skill_id)
        .filter(UserSkill.skill_id.in_(ids), User.is_active == True)
        .all()
    )

    users_data: dict = {}
    for row in user_skill_data:
        if row.user_id not in users_data:
            users_data[row.user_id] = {
                "user_id": row.user_id,
                "user_name": row.full_name,
                "department": row.department,
                "role": row.role,
                "matching_skills": [],
                "skill_count": 0,
            }
        score = level_order.get(row.level, 1)
        if score >= min_score:
            users_data[row.user_id]["matching_skills"].append({
                "skill_id": row.skill_id,
                "skill_name": row.skill_name,
                "level": row.level,
                "years_experience": row.years_experience,
                "certified": row.certified,
            })
            users_data[row.user_id]["skill_count"] += 1

    result = [
        u for u in users_data.values()
        if len({s["skill_id"] for s in u["matching_skills"]}) == len(ids)
    ]
    result.sort(key=lambda x: x["skill_count"], reverse=True)
    return result


# ── Skills matrix ──────────────────────────────────────────────────────────────

def get_skills_matrix(db: Session) -> dict:
    users = db.query(User).filter(User.is_active == True).order_by(User.full_name).all()
    skills = (
        db.query(Skill)
        .filter(Skill.is_active == True)
        .order_by(Skill.category, Skill.name)
        .all()
    )
    user_skills = db.query(UserSkill).all()
    return {"users": users, "skills": skills, "user_skills": user_skills}


# ── Skill history ──────────────────────────────────────────────────────────────

def get_skill_history(
    db: Session, user_id: str, skill_id: Optional[str] = None
) -> List[SkillHistory]:
    q = db.query(SkillHistory).filter(SkillHistory.user_id == user_id)
    if skill_id:
        q = q.filter(SkillHistory.skill_id == skill_id)
    return q.order_by(SkillHistory.recorded_at.desc()).limit(100).all()


def record_skill_assessment(
    db: Session,
    user_id: str,
    skill_id: str,
    new_level: str,
    notes: Optional[str],
    recorded_by: str,
) -> SkillHistory:
    us = get_user_skill_by_skill_id(db, user_id, skill_id)
    old_level = us.level if us else None
    entry = SkillHistory(
        id=str(uuid.uuid4()),
        user_id=user_id,
        skill_id=skill_id,
        old_level=old_level,
        new_level=new_level,
        notes=notes,
        recorded_by=recorded_by,
    )
    db.add(entry)
    if us:
        us.level = new_level
    db.commit()
    return entry
