"""Service layer for Training & Certifications."""
from sqlalchemy.orm import Session, joinedload
from typing import Optional
import uuid as _uuid

from app.models.training import Course, CourseEnrollment, Certification
from app.core import timeutil


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------

def list_courses(db: Session, category: Optional[str] = None) -> list[Course]:
    q = (
        db.query(Course)
        .options(joinedload(Course.enrollments))
        .filter(Course.is_active == True)
    )
    if category:
        q = q.filter(Course.category == category)
    return q.order_by(Course.title).all()


def create_course(db: Session, data: dict) -> Course:
    c = Course(id=str(_uuid.uuid4()), **data)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def get_course(db: Session, course_id: str) -> Optional[Course]:
    return db.query(Course).filter(
        Course.id == course_id,
        Course.is_active == True,
    ).first()


def update_course(db: Session, course: Course, data: dict) -> Course:
    for k, v in data.items():
        setattr(course, k, v)
    db.commit()
    return course


def soft_delete_course(db: Session, course: Course) -> None:
    course.is_active = False
    db.commit()


# ---------------------------------------------------------------------------
# Enrollments
# ---------------------------------------------------------------------------

def list_enrollments(
    db: Session,
    user_id: Optional[str] = None,
    course_id: Optional[str] = None,
    status: Optional[str] = None,
) -> list[CourseEnrollment]:
    q = db.query(CourseEnrollment).options(
        joinedload(CourseEnrollment.course),
        joinedload(CourseEnrollment.user),
    )
    if user_id:
        q = q.filter(CourseEnrollment.user_id == user_id)
    if course_id:
        q = q.filter(CourseEnrollment.course_id == course_id)
    if status:
        q = q.filter(CourseEnrollment.status == status)
    return q.order_by(CourseEnrollment.created_at.desc()).all()


def create_enrollment(db: Session, data: dict) -> CourseEnrollment:
    e = CourseEnrollment(id=str(_uuid.uuid4()), **data)
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def get_enrollment(db: Session, enroll_id: str) -> Optional[CourseEnrollment]:
    return db.query(CourseEnrollment).filter(CourseEnrollment.id == enroll_id).first()


def update_enrollment(db: Session, enrollment: CourseEnrollment, data: dict) -> CourseEnrollment:
    for k, v in data.items():
        setattr(enrollment, k, v)
    db.commit()
    return enrollment


def delete_enrollment(db: Session, enrollment: CourseEnrollment) -> None:
    db.delete(enrollment)
    db.commit()


# ---------------------------------------------------------------------------
# Certifications
# ---------------------------------------------------------------------------

def list_certifications(
    db: Session, user_id: Optional[str] = None
) -> list[Certification]:
    q = db.query(Certification).options(joinedload(Certification.user))
    if user_id:
        q = q.filter(Certification.user_id == user_id)
    return q.order_by(Certification.expires_at).all()


def create_certification(db: Session, data: dict) -> Certification:
    c = Certification(id=str(_uuid.uuid4()), **data)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def get_certification(db: Session, cert_id: str) -> Optional[Certification]:
    return db.query(Certification).filter(Certification.id == cert_id).first()


def update_certification(db: Session, cert: Certification, data: dict) -> Certification:
    for k, v in data.items():
        setattr(cert, k, v)
    db.commit()
    return cert


def delete_certification(db: Session, cert: Certification) -> None:
    db.delete(cert)
    db.commit()


# ── Serialization helpers ───────────────────────────────────────────────────

def serialize_course(c) -> dict:
    return {
        "id": c.id, "title": c.title, "description": c.description,
        "provider": c.provider, "category": c.category,
        "duration_h": c.duration_h, "url": c.url, "cost": c.cost,
        "enrolled": len(c.enrollments),
    }


def serialize_enrollment(e) -> dict:
    return {
        "id": e.id,
        "course_id": e.course_id,
        "course_title": e.course.title if e.course else None,
        "user_id": e.user_id,
        "user_name": e.user.full_name if e.user else None,
        "status": e.status,
        "start_date": str(e.start_date) if e.start_date else None,
        "end_date": str(e.end_date) if e.end_date else None,
        "score": e.score, "notes": e.notes,
    }


def serialize_certification(c) -> dict:
    today = timeutil.today()
    days_left = (c.expires_at - today).days if c.expires_at else None
    return {
        "id": c.id, "user_id": c.user_id,
        "user_name": c.user.full_name if c.user else None,
        "name": c.name, "issuer": c.issuer, "cert_id": c.cert_id,
        "obtained_at": str(c.obtained_at) if c.obtained_at else None,
        "expires_at": str(c.expires_at) if c.expires_at else None,
        "days_until_expiry": days_left,
        "is_expired": days_left is not None and days_left < 0,
        "expiring_soon": days_left is not None and 0 <= days_left <= 60,
        "url": c.url, "notes": c.notes,
    }
