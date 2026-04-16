"""Training & Certificaciones."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from datetime import date

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_hr, require_any_manager
from app.models.user import User, UserRole
from app.services import training_service

router = APIRouter(prefix="/training", tags=["Training"])


class CourseIn(BaseModel):
    title: str
    description: Optional[str] = None
    provider: Optional[str] = None
    category: Optional[str] = None
    duration_h: Optional[float] = None
    url: Optional[str] = None
    cost: Optional[float] = None

class EnrollmentIn(BaseModel):
    course_id: str
    user_id: str
    status: str = "planned"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    score: Optional[float] = None
    notes: Optional[str] = None

class CertificationIn(BaseModel):
    user_id: str
    name: str
    issuer: Optional[str] = None
    cert_id: Optional[str] = None
    obtained_at: Optional[date] = None
    expires_at: Optional[date] = None
    url: Optional[str] = None
    notes: Optional[str] = None


from app.services.training_service import (
    serialize_course as _ser_course,
    serialize_enrollment as _ser_enrollment,
    serialize_certification as _ser_cert,
)


@router.get("/courses", summary="Catálogo de cursos")
def list_courses(category: Optional[str] = None, db: Session = Depends(get_db),
                 cu: User = Depends(get_current_user)):
    return [_ser_course(c) for c in training_service.list_courses(db, category=category)]


@router.post("/courses", summary="Crear curso", status_code=201)
def create_course(payload: CourseIn, db: Session = Depends(get_db),
                  cu: User = Depends(require_admin_or_hr)):
    c = training_service.create_course(db, payload.model_dump())
    return {"id": c.id, "title": c.title}


@router.patch("/courses/{course_id}", summary="Editar curso")
def update_course(course_id: str, payload: CourseIn, db: Session = Depends(get_db),
                  cu: User = Depends(require_admin_or_hr)):
    c = training_service.get_course(db, course_id)
    if not c:
        raise HTTPException(404, "Curso no encontrado")
    training_service.update_course(db, c, payload.model_dump(exclude_unset=True))
    return {"id": c.id}


@router.delete("/courses/{course_id}", summary="Eliminar curso")
def delete_course(course_id: str, db: Session = Depends(get_db),
                  cu: User = Depends(require_admin_or_hr)):
    c = training_service.get_course(db, course_id)
    if not c:
        raise HTTPException(404, "Curso no encontrado")
    training_service.soft_delete_course(db, c)
    return {"deleted": True}


@router.get("/enrollments", summary="Inscripciones")
def list_enrollments(user_id: Optional[str] = None, course_id: Optional[str] = None,
                     status: Optional[str] = None, db: Session = Depends(get_db),
                     cu: User = Depends(get_current_user)):
    return [_ser_enrollment(e) for e in training_service.list_enrollments(
        db, user_id=user_id, course_id=course_id, status=status)]


@router.post("/enrollments", summary="Inscribir usuario a curso", status_code=201)
def create_enrollment(payload: EnrollmentIn, db: Session = Depends(get_db),
                      cu: User = Depends(require_any_manager)):
    e = training_service.create_enrollment(db, payload.model_dump())
    return {"id": e.id}


@router.patch("/enrollments/{enroll_id}", summary="Actualizar inscripción")
def update_enrollment(enroll_id: str, payload: EnrollmentIn, db: Session = Depends(get_db),
                      cu: User = Depends(require_any_manager)):
    e = training_service.get_enrollment(db, enroll_id)
    if not e:
        raise HTTPException(404, "Inscripción no encontrada")
    training_service.update_enrollment(db, e, payload.model_dump(exclude_unset=True))
    return {"id": e.id}


@router.delete("/enrollments/{enroll_id}", summary="Eliminar inscripción")
def delete_enrollment(enroll_id: str, db: Session = Depends(get_db),
                      cu: User = Depends(require_any_manager)):
    e = training_service.get_enrollment(db, enroll_id)
    if not e:
        raise HTTPException(404, "Inscripción no encontrada")
    training_service.delete_enrollment(db, e)
    return {"deleted": True}


@router.get("/certifications", summary="Certificaciones de usuarios")
def list_certifications(user_id: Optional[str] = None, expiring_days: Optional[int] = None,
                        db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    certs = [_ser_cert(c) for c in training_service.list_certifications(db, user_id=user_id)]
    if expiring_days is not None:
        certs = [c for c in certs if c["days_until_expiry"] is not None
                 and 0 <= c["days_until_expiry"] <= expiring_days]
    return certs


@router.post("/certifications", summary="Añadir certificación", status_code=201)
def create_certification(payload: CertificationIn, db: Session = Depends(get_db),
                         cu: User = Depends(get_current_user)):
    c = training_service.create_certification(db, payload.model_dump())
    return {"id": c.id}


@router.patch("/certifications/{cert_id}", summary="Editar certificación")
def update_certification(cert_id: str, payload: CertificationIn, db: Session = Depends(get_db),
                         cu: User = Depends(get_current_user)):
    c = training_service.get_certification(db, cert_id)
    if not c:
        raise HTTPException(404, "Certificación no encontrada")
    if c.user_id != cu.id and cu.role not in (UserRole.admin, UserRole.hr):
        raise HTTPException(403, "Solo puedes editar tus propias certificaciones")
    training_service.update_certification(db, c, payload.model_dump(exclude_unset=True))
    return {"id": c.id}


@router.delete("/certifications/{cert_id}", summary="Eliminar certificación")
def delete_certification(cert_id: str, db: Session = Depends(get_db),
                         cu: User = Depends(get_current_user)):
    c = training_service.get_certification(db, cert_id)
    if not c:
        raise HTTPException(404, "Certificación no encontrada")
    if c.user_id != cu.id and cu.role not in (UserRole.admin, UserRole.hr):
        raise HTTPException(403, "Solo puedes eliminar tus propias certificaciones")
    training_service.delete_certification(db, c)
    return {"deleted": True}
