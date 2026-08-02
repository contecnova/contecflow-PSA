"""
absence_service.py — Lógica de negocio para ausencias.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.resources import Absence, AbsenceStatus, AbsenceType
from app.models.settings import Holiday
from app.models.user import User
from app.core.config import settings as app_settings
from app.models.user import UserRole
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


# ── Queries ────────────────────────────────────────────────────────────────────

def list_absences(
    db: Session,
    *,
    is_superadmin: bool,
    organization_id: Optional[str],
    user_role: str,
    current_user_id: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[Absence]:

    q = db.query(Absence).options(joinedload(Absence.user)).filter(Absence.is_active == True)
    if not is_superadmin and organization_id:
        org_user_ids = db.query(User.id).filter(
            User.organization_id == organization_id
        ).scalar_subquery()
        q = q.filter(Absence.user_id.in_(org_user_ids))

    if user_role in (UserRole.employee, UserRole.subcontractor):
        q = q.filter(Absence.user_id == current_user_id)
    elif user_id:
        q = q.filter(Absence.user_id == user_id)

    if date_from:
        q = q.filter(Absence.end_date >= date_from)
    if date_to:
        q = q.filter(Absence.start_date <= date_to)
    if status:
        q = q.filter(Absence.status == status)

    return q.order_by(Absence.start_date.desc()).limit(limit).all()


def get_my_absences(db: Session, user_id: str) -> list[Absence]:
    return (
        db.query(Absence)
        .options(joinedload(Absence.user), joinedload(Absence.approver))
        .filter(Absence.user_id == user_id, Absence.is_active == True)
        .order_by(Absence.start_date.desc())
        .all()
    )


def get_vacation_balance(db: Session, user_id: str, year: int) -> dict:

    try:
        from app.models.advanced_config import UserVacationBalance
        bal = db.query(UserVacationBalance).filter(
            UserVacationBalance.user_id == user_id,
            UserVacationBalance.year == year,
        ).first()
        entitled = bal.days_entitled if bal else app_settings.DEFAULT_VACATION_DAYS_PER_YEAR
        carried = bal.days_carried_over if bal else 0
    except Exception:
        entitled = app_settings.DEFAULT_VACATION_DAYS_PER_YEAR
        carried = 0

    year_start = date(year, 1, 1)
    year_end = date(year + 1, 1, 1)

    taken = db.query(func.sum(Absence.working_days)).filter(
        Absence.user_id == user_id,
        Absence.is_active == True,
        Absence.type == AbsenceType.vacation,
        Absence.status == AbsenceStatus.approved,
        Absence.start_date >= year_start,
        Absence.start_date < year_end,
    ).scalar() or 0

    pending = db.query(func.sum(Absence.working_days)).filter(
        Absence.user_id == user_id,
        Absence.is_active == True,
        Absence.type == AbsenceType.vacation,
        Absence.status == AbsenceStatus.pending,
        Absence.start_date >= year_start,
        Absence.start_date < year_end,
    ).scalar() or 0

    return {
        "year": year,
        "days_entitled": entitled,
        "days_carried": round(carried, 1),
        "days_taken": round(float(taken), 1),
        "days_pending": round(float(pending), 1),
        "days_remaining": round(entitled + carried - float(taken) - float(pending), 1),
    }


def get_overlap(
    db: Session,
    user_id: str,
    start_date: date,
    end_date: date,
    exclude_id: Optional[str] = None,
) -> Optional[Absence]:
    q = db.query(Absence).filter(
        Absence.user_id == user_id,
        Absence.is_active == True,
        Absence.status.in_([AbsenceStatus.pending, AbsenceStatus.approved]),
        Absence.start_date <= end_date,
        Absence.end_date >= start_date,
    )
    if exclude_id:
        q = q.filter(Absence.id != exclude_id)
    return q.first()


def get_holidays(db: Session) -> list[Holiday]:
    return db.query(Holiday).all()


def get_holidays_for_period(db: Session, start: date, end: date) -> list[Holiday]:
    return db.query(Holiday).filter(
        Holiday.date >= str(start),
        Holiday.date <= str(end),
    ).all()


def get_absence_for_user(db: Session, absence_id: str, user_id: str) -> Optional[Absence]:
    return db.query(Absence).filter(
        Absence.id == absence_id,
        Absence.user_id == user_id,
        Absence.is_active == True,
    ).first()


def get_absence_by_id(db: Session, absence_id: str) -> Optional[Absence]:
    return db.query(Absence).filter(Absence.id == absence_id, Absence.is_active == True).first()


def get_team_absences(
    db: Session,
    *,
    month: Optional[str] = None,
    user_id: Optional[str] = None,
    status: Optional[str] = None,
) -> list[Absence]:

    q = db.query(Absence).options(joinedload(Absence.user), joinedload(Absence.approver)).filter(Absence.is_active == True)
    if month:
        year, m = int(month.split("-")[0]), int(month.split("-")[1])
        month_start = date(year, m, 1)
        month_end = date(year, m, 28) + timedelta(days=4)
        month_end = month_end.replace(day=1) - timedelta(days=1)
        q = q.filter(Absence.start_date <= month_end, Absence.end_date >= month_start)
    if user_id:
        q = q.filter(Absence.user_id == user_id)
    if status:
        q = q.filter(Absence.status == status)
    return q.order_by(Absence.start_date.desc()).limit(200).all()


def get_pending_absences(db: Session) -> list[Absence]:
    return (
        db.query(Absence)
        .options(joinedload(Absence.user))
        .filter(Absence.is_active == True)
        .filter(Absence.status == AbsenceStatus.pending)
        .order_by(Absence.start_date)
        .all()
    )


def get_calendar_data(
    db: Session, month_start: date, month_end: date
) -> tuple[list[Absence], list[Holiday]]:
    absences = (
        db.query(Absence)
        .options(joinedload(Absence.user))
        .filter(
            Absence.is_active == True,
            Absence.status == AbsenceStatus.approved,
            Absence.start_date <= month_end,
            Absence.end_date >= month_start,
        )
        .all()
    )
    holidays = get_holidays_for_period(db, month_start, month_end)
    return absences, holidays


def get_user_year_absences(
    db: Session, user_id: str, year: int
) -> list[Absence]:
    year_start = date(year, 1, 1)
    year_end = date(year + 1, 1, 1)
    return db.query(Absence).filter(
        Absence.user_id == user_id,
        Absence.is_active == True,
        Absence.status == AbsenceStatus.approved,
        Absence.start_date >= year_start,
        Absence.start_date < year_end,
    ).all()


# ── Mutations ──────────────────────────────────────────────────────────────────

def create_absence(
    db: Session,
    *,
    user_id: str,
    type: str,
    start_date: date,
    end_date: date,
    reason: Optional[str],
    working_days: float,
) -> Absence:
    absence = Absence(
        user_id=user_id,
        type=type,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        working_days=working_days,
    )
    db.add(absence)
    db.commit()
    db.refresh(absence)
    return absence


def cancel_absence(db: Session, absence: Absence) -> None:
    absence.status = AbsenceStatus.cancelled
    absence.is_active = False
    db.commit()


def update_absence(
    db: Session,
    absence: Absence,
    *,
    type: str,
    start_date: date,
    end_date: date,
    reason: Optional[str],
    working_days: float,
) -> Absence:
    absence.type = type
    absence.start_date = start_date
    absence.end_date = end_date
    absence.reason = reason
    absence.working_days = working_days
    db.commit()
    db.refresh(absence)
    return absence


def review_absence(
    db: Session,
    absence: Absence,
    *,
    approved: bool,
    approver_id: str,
    rejection_reason: Optional[str],
) -> Absence:
    absence.status = AbsenceStatus.approved if approved else AbsenceStatus.rejected
    absence.approved_by = approver_id
    absence.approved_at = datetime.now(timezone.utc)
    absence.rejection_reason = rejection_reason
    db.commit()
    return absence


# ── Label constants ─────────────────────────────────────────────────────────────

TYPE_LABELS = {
    "vacation": "Vacaciones", "sick": "Baja médica", "personal": "Asunto personal",
    "training": "Formación", "maternity": "Maternidad", "paternity": "Paternidad", "other": "Otro",
}
STATUS_CFG = {
    "pending": {"label": "Pendiente", "color": "#ffb800"},
    "approved": {"label": "Aprobada", "color": "#00e5a0"},
    "rejected": {"label": "Rechazada", "color": "#ff4757"},
    "cancelled": {"label": "Cancelada", "color": "#7a8aaa"},
}


def count_working_days(start, end, holidays: list) -> float:
    """Count working days between two dates excluding weekends and holidays."""
    holiday_dates = set()
    for h in holidays:
        if isinstance(h, date):
            holiday_dates.add(h)
        elif hasattr(h, "date"):
            holiday_dates.add(h.date)
        elif isinstance(h, str):
            try:
                holiday_dates.add(date.fromisoformat(h))
            # intentional: best-effort fallback, log noise outweighs diagnostic value
            except Exception:
                logger.debug("count_working_days: fallo best-effort ignorado", exc_info=True)
    count = 0
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in holiday_dates:
            count += 1
        current += timedelta(days=1)
    return float(count)


def serialize_absence(a) -> dict:
    return {
        "id": a.id,
        "user_id": a.user_id,
        "user_name": a.user.full_name if a.user else "—",
        "type": a.type,
        "type_label": TYPE_LABELS.get(a.type, a.type),
        "status": a.status,
        "status_label": STATUS_CFG.get(a.status, {}).get("label", a.status),
        "status_color": STATUS_CFG.get(a.status, {}).get("color", "#7a8aaa"),
        "start_date": str(a.start_date),
        "end_date": str(a.end_date),
        "working_days": a.working_days,
        "reason": a.reason,
        "approved_by": a.approver.full_name if a.approver else None,
        "approved_at": str(a.approved_at)[:10] if a.approved_at else None,
        "rejection_reason": a.rejection_reason,
        "created_at": str(a.created_at)[:10] if a.created_at else None,
    }
