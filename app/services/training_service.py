"""Service layer for Training & Certifications."""
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from datetime import date
import uuid as _uuid

from app.models.training import Course, CourseEnrollment, Certification


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------

def list_courses(db: Session, category: Optional[str] = None) -> list[Course]:
    q = (
        db.query(Course)
        .options(joinedload(Course.enrollments))
        .filter(Course.is_active == True)  # noqa: E712
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
    return db.query(Course).filter(Course.id == course_id).first()


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
