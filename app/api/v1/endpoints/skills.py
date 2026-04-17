from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_hr
from app.models.user import User, UserRole
from app.services import skill_service
from app.schemas.skills import SkillIn, UserSkillIn, StaffingQuery

router = APIRouter()

LEVEL_LABELS = {"basic": "Básico", "intermediate": "Intermedio", "advanced": "Avanzado", "expert": "Experto"}
CAT_LABELS = {"technical": "Técnico", "language": "Idioma", "methodology": "Metodología", "tool": "Herramienta", "soft": "Habilidad blanda", "certification": "Certificación"}


# ── Skill catalog ─────────────────────────────────────────────────────────────

@router.get("/catalog", summary="Catálogo de skills")
def get_catalog(
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    skills = skill_service.get_catalog(db, category)
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
    if skill_service.get_skill_by_name(db, payload.name):
        raise HTTPException(400, "Ya existe un skill con ese nombre")
    s = skill_service.create_skill(db, payload.model_dump())
    return {"id": s.id, "name": s.name, "category": s.category}


@router.patch("/catalog/{skill_id}", summary="Actualizar skill")
def update_skill(
    skill_id: str,
    payload: SkillIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    s = skill_service.get_skill_by_id(db, skill_id)
    if not s:
        raise HTTPException(404, "Skill no encontrado")
    s = skill_service.update_skill(db, s, payload.model_dump())
    return {"id": s.id, "name": s.name}


@router.delete("/catalog/{skill_id}", summary="Eliminar skill")
def delete_skill(
    skill_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    s = skill_service.get_skill_by_id(db, skill_id)
    if not s:
        raise HTTPException(404, "Skill no encontrado")
    skill_service.deactivate_skill(db, s)
    return {"ok": True}


# ── User skills ───────────────────────────────────────────────────────────────

@router.get("/users/{user_id}", summary="Skills de un usuario")
def get_user_skills(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    skills = skill_service.get_user_skills(db, user_id)
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
    us, updated = skill_service.upsert_user_skill(db, user_id, payload.model_dump(), current_user.id)
    if updated:
        return {"id": us.id, "message": "Skill actualizado"}
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
    us = skill_service.get_user_skill_by_id(db, skill_id)
    if not us:
        raise HTTPException(404, "No encontrado")
    skill_service.remove_user_skill(db, us)
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
    ids = [s.strip() for s in skill_ids.split(",") if s.strip()]
    result = skill_service.search_by_skills(db, ids, min_level)
    for user in result:
        for sk in user["matching_skills"]:
            sk["level_label"] = LEVEL_LABELS.get(sk["level"], sk["level"])
    return result


@router.get("/matrix", summary="Matriz de skills del equipo")
def get_skills_matrix(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    """Returns a matrix of users × skills."""
    data = skill_service.get_skills_matrix(db)
    users = data["users"]
    skills = data["skills"]
    user_skills = data["user_skills"]

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
    entries = skill_service.get_skill_history(db, user_id, skill_id)
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
    skill_id  = payload.get("skill_id")
    new_level = payload.get("new_level")
    notes     = payload.get("notes")
    if not skill_id or not new_level:
        raise HTTPException(400, "skill_id y new_level son obligatorios")
    entry = skill_service.record_skill_assessment(db, user_id, skill_id, new_level, notes, cu.id)
    return {
        "id": entry.id,
        "old_level": str(entry.old_level) if entry.old_level else None,
        "new_level": entry.new_level,
    }
