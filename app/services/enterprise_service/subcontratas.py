"""Subcontratas: empresas, tarifas, asignaciones, trabajadores, habilidades, horas y facturas.

Parte de `app.services.enterprise_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.enterprise import Subcontractor
from app.models.enterprise import SubcontractorWorker
from app.models.enterprise import SubcontractorRate
from app.models.enterprise import SubcontractorAssignment
from app.models.enterprise import SubcontractorWorkerSkill
from app.models.enterprise import SubcontractorTimeLog
from app.models.enterprise import SubcontractorInvoice
from app.models.user import User, UserRole as ModelUserRole, UserStatus
from app.services.audit import audit_log
from sqlalchemy import func as _func
from sqlalchemy.orm import joinedload
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.enterprise import (
        Subcontractor,
    )


def serialize_subcontractor(s) -> dict:
    return {
        "id": s.id, "code": s.code, "name": s.name, "company": s.company,
        "email": s.email, "phone": s.phone, "country": s.country,
        "vat_number": s.vat_number, "currency": s.currency,
        "is_active": s.is_active, "notes": s.notes,
        "rates": [{
            "id": r.id, "description": r.description,
            "cost_rate": r.cost_rate, "sell_rate": r.sell_rate,
            "currency": r.currency,
            "valid_from": str(r.valid_from) if r.valid_from else None,
            "valid_until": str(r.valid_until) if r.valid_until else None,
        } for r in (s.rates or []) if r.is_active],
        "assignment_count": len(s.assignments or []),
        "worker_count": len([w for w in (s.workers or []) if w.is_active]),
    }


def serialize_worker(w) -> dict:
    return {
        "id": w.id,
        "subcontractor_id": w.subcontractor_id,
        "user_id": w.user_id,
        "login_username": w.user.username if w.user else None,
        "name": w.name,
        "role": w.role,
        "email": w.email,
        "phone": w.phone,
        "cost_rate": w.cost_rate,
        "sell_rate": w.sell_rate,
        "currency": w.currency,
        "available_from": str(w.available_from) if w.available_from else None,
        "available_until": str(w.available_until) if w.available_until else None,
        "weekly_capacity_hours": w.weekly_capacity_hours,
        "is_active": w.is_active,
        "notes": w.notes,
        "skills": [{
            "id": sk.id,
            "skill_id": sk.skill_id,
            "skill_name": sk.skill.name if sk.skill else None,
            "skill_category": sk.skill.category.value if sk.skill and sk.skill.category else None,
            "level": sk.level,
            "years_experience": sk.years_experience,
            "certified": sk.certified,
            "cert_name": sk.cert_name,
            "notes": sk.notes,
        } for sk in (w.skills or []) if sk.is_active],
        "assignment_count": len(w.assignments or []),
    }


# ── Business logic ─────────────────────────────────────────────────────────────

def next_sub_code(db: Session) -> str:
    import re
    from app.models.enterprise import Subcontractor as _Subcontractor  # local import to avoid circular dependency
    max_code = db.query(func.max(_Subcontractor.code)).scalar()
    if max_code:
        m = re.search(r"(\d+)$", max_code)
        next_num = (int(m.group(1)) + 1) if m else 1
    else:
        next_num = 1
    return f"SUB-{next_num:04d}"


def get_subcontractor(db: Session, sub_id: str):
    return db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()


def create_worker_with_user(sub, payload, current_user, db: Session) -> dict:
    """Create a SubcontractorWorker and its linked User record."""
    import re, secrets

    base = re.sub(r"[^a-z0-9]", ".", payload.name.lower().strip())
    base = re.sub(r"\.{2,}", ".", base).strip(".")
    base_username = f"{base}.{sub.code.lower()}"
    username = base_username
    suffix = 0
    while db.query(User).filter(User.username == username).first():
        suffix += 1
        username = f"{base_username}{suffix}"

    email = payload.email
    if email:
        if db.query(User).filter(User.email == email).first():
            email = f"{username}@subcontractor.internal"
    else:
        email = f"{username}@subcontractor.internal"

    name_parts = payload.name.strip().split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else None

    temp_password = secrets.token_urlsafe(12)

    linked_user = User(
        username=username,
        email=email,
        full_name=payload.name,
        first_name=first_name,
        last_name=last_name,
        job_title=payload.role,
        department=sub.name,
        role=ModelUserRole.subcontractor,
        status=UserStatus.active,
        weekly_capacity_hours=payload.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS,
        hourly_rate=payload.cost_rate,
        currency=payload.currency,
        phone=payload.phone,
        is_active=True,
        organization_id=current_user.organization_id,
        hashed_password=get_password_hash(temp_password),
    )
    db.add(linked_user)
    db.flush()

    worker = SubcontractorWorker(
        subcontractor_id=sub.id,
        user_id=linked_user.id,
        weekly_capacity_hours=payload.weekly_capacity_hours,
        **{k: v for k, v in payload.model_dump().items() if k != "weekly_capacity_hours"},
    )
    db.add(worker)
    audit_log(db, current_user, "CREATE", "subcontractor_workers", worker.id, worker.name)
    db.commit()
    db.refresh(worker)
    result = serialize_worker(worker)
    result["login_username"] = linked_user.username
    result["temp_password"] = temp_password
    return result


# ── Subcontractors ────────────────────────────────────────────────────────────

def list_subcontractors(is_active, db: Session) -> list:
    q = db.query(Subcontractor).options(
        joinedload(Subcontractor.rates),
        joinedload(Subcontractor.assignments),
        joinedload(Subcontractor.workers),
    )
    if is_active is not None:
        q = q.filter(Subcontractor.is_active == is_active)
    return [serialize_subcontractor(s) for s in q.order_by(Subcontractor.name).all()]


def create_subcontractor(payload, current_user, db: Session) -> dict:
    sub = Subcontractor(code=next_sub_code(db), **payload.model_dump())
    db.add(sub)
    audit_log(db, current_user, "CREATE", "subcontractors", sub.id, sub.name)
    db.commit()
    db.refresh(sub)
    return serialize_subcontractor(sub)


def update_subcontractor(sub_id: str, payload, db: Session) -> dict:
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()
    if not sub:
        raise ValueError("not_found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(sub, k, v)
    db.commit()
    sub = db.query(Subcontractor).options(
        joinedload(Subcontractor.rates),
        joinedload(Subcontractor.assignments),
        joinedload(Subcontractor.workers),
    ).filter(Subcontractor.id == sub_id).first()
    return serialize_subcontractor(sub)


def delete_subcontractor(sub_id: str, db: Session) -> dict:
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()
    if not sub:
        raise ValueError("not_found")
    dependencies = []
    assignment_count = db.query(_func.count(SubcontractorAssignment.id)).filter(
        SubcontractorAssignment.subcontractor_id == sub_id
    ).scalar() or 0
    if assignment_count > 0:
        dependencies.append(f"{assignment_count} asignaciones")

    worker_count = db.query(_func.count(SubcontractorWorker.id)).filter(
        SubcontractorWorker.subcontractor_id == sub_id,
        SubcontractorWorker.is_active == True,
    ).scalar() or 0
    if worker_count > 0:
        dependencies.append(f"{worker_count} trabajadores activos")

    timelog_count = db.query(_func.count(SubcontractorTimeLog.id)).filter(
        SubcontractorTimeLog.subcontractor_id == sub_id,
        SubcontractorTimeLog.is_active == True,
    ).scalar() or 0
    if timelog_count > 0:
        dependencies.append(f"{timelog_count} partes de horas")

    if dependencies:
        raise ValueError(f"has_dependencies:{', '.join(dependencies)}")

    sub.is_active = False
    db.query(SubcontractorRate).filter(
        SubcontractorRate.subcontractor_id == sub_id,
        SubcontractorRate.is_active == True,
    ).update({"is_active": False}, synchronize_session=False)
    db.query(SubcontractorWorker).filter(
        SubcontractorWorker.subcontractor_id == sub_id,
        SubcontractorWorker.is_active == True,
    ).update({"is_active": False}, synchronize_session=False)
    db.commit()
    return {"ok": True, "message": "Subcontratista eliminado correctamente"}


def add_subcontractor_rate(sub_id: str, payload, db: Session) -> dict:
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()
    if not sub:
        raise ValueError("not_found")
    rate = SubcontractorRate(subcontractor_id=sub_id, **payload.model_dump())
    db.add(rate)
    db.commit()
    return {"id": rate.id, "description": rate.description, "cost_rate": rate.cost_rate, "sell_rate": rate.sell_rate}


def delete_subcontractor_rate(sub_id: str, rate_id: str, db: Session) -> dict:
    rate = db.query(SubcontractorRate).filter(
        SubcontractorRate.id == rate_id,
        SubcontractorRate.subcontractor_id == sub_id,
        SubcontractorRate.is_active == True,
    ).first()
    if not rate:
        raise ValueError("not_found")
    assignments_using_rate = db.query(_func.count(SubcontractorAssignment.id)).filter(
        SubcontractorAssignment.rate_id == rate_id
    ).scalar() or 0
    if assignments_using_rate > 0:
        raise ValueError("has_dependencies")
    rate.is_active = False
    db.commit()
    return {"ok": True, "message": "Tarifa eliminada correctamente"}


def get_subcontractor_assignments(sub_id: str, db: Session) -> list:
    assignments = db.query(SubcontractorAssignment).options(
        joinedload(SubcontractorAssignment.project),
        joinedload(SubcontractorAssignment.rate),
    ).filter(SubcontractorAssignment.subcontractor_id == sub_id).all()
    return [{
        "id": a.id, "project_id": a.project_id,
        "project_name": a.project.name if a.project else None,
        "project_code": a.project.code if a.project else None,
        "rate": {"description": a.rate.description, "cost_rate": a.rate.cost_rate} if a.rate else None,
        "po_number": a.po_number, "po_amount": a.po_amount,
        "hours_contracted": a.hours_contracted, "hours_logged": a.hours_logged,
        "budget_used_pct": round((a.hours_logged / a.hours_contracted) * 100, 1) if a.hours_contracted else None,
        "start_date": str(a.start_date) if a.start_date else None,
        "end_date": str(a.end_date) if a.end_date else None,
        "notes": a.notes,
    } for a in assignments]


def create_subcontractor_assignment(sub_id: str, payload, current_user, db: Session) -> dict:
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()
    if not sub:
        raise ValueError("not_found")
    assignment = SubcontractorAssignment(subcontractor_id=sub_id, **payload.model_dump())
    db.add(assignment)
    audit_log(db, current_user, "CREATE", "subcontractor_assignments", assignment.id, sub.name)
    db.commit()
    return {"ok": True, "id": assignment.id}


# ── Subcontractor Workers ─────────────────────────────────────────────────────

def list_all_workers(skill_id, is_active, db: Session) -> list:
    q = db.query(SubcontractorWorker).options(
        joinedload(SubcontractorWorker.skills).joinedload(SubcontractorWorkerSkill.skill),
        joinedload(SubcontractorWorker.assignments),
        joinedload(SubcontractorWorker.subcontractor),
        joinedload(SubcontractorWorker.user),
    )
    if is_active is not None:
        q = q.filter(SubcontractorWorker.is_active == is_active)
    if skill_id:
        q = q.join(SubcontractorWorkerSkill, SubcontractorWorker.id == SubcontractorWorkerSkill.worker_id).filter(
            SubcontractorWorkerSkill.skill_id == skill_id,
            SubcontractorWorkerSkill.is_active == True,
        )
    result = []
    for w in q.order_by(SubcontractorWorker.name).all():
        d = serialize_worker(w)
        d["company_name"] = w.subcontractor.name if w.subcontractor else None
        d["company_code"] = w.subcontractor.code if w.subcontractor else None
        result.append(d)
    return result


def get_workers_for_subcontractor(sub_id: str, db: Session) -> list:
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()
    if not sub:
        raise ValueError("not_found")
    workers = db.query(SubcontractorWorker).options(
        joinedload(SubcontractorWorker.skills).joinedload(SubcontractorWorkerSkill.skill),
        joinedload(SubcontractorWorker.assignments),
        joinedload(SubcontractorWorker.user),
    ).filter(
        SubcontractorWorker.subcontractor_id == sub_id,
        SubcontractorWorker.is_active == True,
    ).order_by(SubcontractorWorker.name).all()
    return [serialize_worker(w) for w in workers]


#: Campo del trabajador → campo del usuario enlazado. Auditoría 2026-09
#: (hallazgo 18): eran seis `if` idénticos en línea, que es una tabla escrita
#: como código. `name` y `email` no están aquí porque no son copias directas:
#: uno se parte en nombre y apellidos y el otro necesita comprobar duplicados.
_ESPEJO_TRABAJADOR_USUARIO: tuple[tuple[str, str], ...] = (
    ("role", "job_title"),
    ("phone", "phone"),
    ("cost_rate", "hourly_rate"),
    ("currency", "currency"),
    ("is_active", "is_active"),
)


def _sincronizar_usuario_enlazado(db: Session, worker, cambios: dict) -> None:
    """Refleja en el usuario enlazado los campos que comparte con el trabajador.

    Sólo se tocan los campos **presentes** en el payload: `exclude_unset` deja
    fuera los que nadie envió, y no es lo mismo «ponlo a nulo» que «no lo toques».
    """
    if not worker.user_id:
        return
    usuario = db.query(User).filter(User.id == worker.user_id).first()
    if not usuario:
        return

    for campo_trabajador, campo_usuario in _ESPEJO_TRABAJADOR_USUARIO:
        if campo_trabajador in cambios:
            setattr(usuario, campo_usuario, cambios[campo_trabajador])

    # La capacidad semanal sí distingue: un nulo explícito no la borra, porque
    # un usuario sin capacidad declarada no es lo mismo que uno con cero.
    if cambios.get("weekly_capacity_hours") is not None:
        usuario.weekly_capacity_hours = cambios["weekly_capacity_hours"]

    if "name" in cambios:
        usuario.full_name = cambios["name"]
        partes = cambios["name"].strip().split(" ", 1)
        usuario.first_name = partes[0]
        usuario.last_name = partes[1] if len(partes) > 1 else None

    # El correo es identidad: si ya lo tiene otro, **no se cambia y no se
    # levanta error** — el resto de la actualización es válida y el trabajador
    # se queda con el correo que tenía, que es lo que hacía esta función.
    nuevo_correo = cambios.get("email")
    if nuevo_correo:
        ocupado = db.query(User).filter(
            User.email == nuevo_correo, User.id != usuario.id,
        ).first()
        if not ocupado:
            usuario.email = nuevo_correo


def update_worker(worker_id: str, payload, db: Session) -> dict:
    """Actualiza un trabajador subcontratado y su usuario enlazado, si lo tiene."""
    worker = db.query(SubcontractorWorker).options(
        joinedload(SubcontractorWorker.skills).joinedload(SubcontractorWorkerSkill.skill),
        joinedload(SubcontractorWorker.assignments),
        joinedload(SubcontractorWorker.user),
    ).filter(
        SubcontractorWorker.id == worker_id,
        SubcontractorWorker.is_active == True,  # noqa: E712
    ).first()
    if not worker:
        raise ValueError("not_found")

    cambios = payload.model_dump(exclude_unset=True)
    for clave, valor in cambios.items():
        setattr(worker, clave, valor)

    _sincronizar_usuario_enlazado(db, worker, cambios)

    db.commit()
    db.refresh(worker)
    return serialize_worker(worker)


def delete_worker(worker_id: str, db: Session) -> dict:
    worker = db.query(SubcontractorWorker).filter(
        SubcontractorWorker.id == worker_id,
        SubcontractorWorker.is_active == True,
    ).first()
    if not worker:
        raise ValueError("not_found")
    assignment_count = db.query(_func.count(SubcontractorAssignment.id)).filter(
        SubcontractorAssignment.worker_id == worker_id
    ).scalar() or 0
    if assignment_count > 0:
        raise ValueError("has_dependencies")
    worker.is_active = False
    if worker.user_id:
        linked_user = db.query(User).filter(User.id == worker.user_id).first()
        if linked_user:
            linked_user.is_active = False
    db.commit()
    return {"ok": True, "message": "Trabajador eliminado correctamente"}


def add_worker_skill(worker_id: str, payload, db: Session) -> dict:
    worker = db.query(SubcontractorWorker).filter(
        SubcontractorWorker.id == worker_id,
        SubcontractorWorker.is_active == True,
    ).first()
    if not worker:
        raise ValueError("not_found")
    existing = db.query(SubcontractorWorkerSkill).filter(
        SubcontractorWorkerSkill.worker_id == worker_id,
        SubcontractorWorkerSkill.skill_id == payload.skill_id,
        SubcontractorWorkerSkill.is_active == True,
    ).first()
    if existing:
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(existing, k, v)
        db.commit()
        return {"ok": True, "id": existing.id, "updated": True}
    ws = SubcontractorWorkerSkill(worker_id=worker_id, **payload.model_dump())
    db.add(ws)
    db.commit()
    return {"ok": True, "id": ws.id, "updated": False}


def remove_worker_skill(worker_id: str, skill_id: str, db: Session) -> dict:
    ws = db.query(SubcontractorWorkerSkill).filter(
        SubcontractorWorkerSkill.worker_id == worker_id,
        SubcontractorWorkerSkill.skill_id == skill_id,
        SubcontractorWorkerSkill.is_active == True,
    ).first()
    if not ws:
        raise ValueError("not_found")
    ws.is_active = False
    db.commit()
    return {"ok": True, "message": "Skill eliminada correctamente"}


# ── Subcontractor Time Logs ───────────────────────────────────────────────────

def get_timelogs(sub_id: str, project_id, db: Session) -> list:
    q = db.query(SubcontractorTimeLog).filter(
        SubcontractorTimeLog.subcontractor_id == sub_id,
        SubcontractorTimeLog.is_active == True,
    )
    if project_id:
        q = q.filter(SubcontractorTimeLog.project_id == project_id)
    return [{
        "id": l.id, "log_date": str(l.log_date), "hours": l.hours,
        "description": l.description, "task_reference": l.task_reference,
        "cost_amount": l.cost_amount, "is_invoiced": l.is_invoiced,
        "project_id": l.project_id,
        "project_name": l.project.name if l.project else None,
    } for l in q.order_by(SubcontractorTimeLog.log_date.desc()).all()]


def create_timelog(sub_id: str, payload: dict, db: Session) -> dict:
    import uuid as _uuid
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()
    if not sub:
        raise ValueError("not_found")
    cost_amount = payload.get("cost_amount")
    assignment_id = payload.get("assignment_id")
    if not cost_amount and assignment_id:
        assignment = db.query(SubcontractorAssignment).filter(SubcontractorAssignment.id == assignment_id).first()
        if assignment and assignment.rate:
            cost_amount = round(float(payload.get("hours", 0)) * assignment.rate.cost_rate, 2)
    log = SubcontractorTimeLog(
        id=str(_uuid.uuid4()), subcontractor_id=sub_id,
        assignment_id=assignment_id, project_id=payload.get("project_id"),
        log_date=payload.get("log_date"), hours=float(payload.get("hours", 0)),
        description=payload.get("description"), task_reference=payload.get("task_reference"),
        cost_amount=cost_amount,
    )
    db.add(log)
    if assignment_id:
        assignment = db.query(SubcontractorAssignment).filter(SubcontractorAssignment.id == assignment_id).first()
        if assignment:
            assignment.hours_logged = (assignment.hours_logged or 0) + float(payload.get("hours", 0))
    db.commit()
    return {"ok": True, "id": log.id, "cost_amount": cost_amount}


def delete_timelog(sub_id: str, log_id: str, db: Session) -> dict:
    log = db.query(SubcontractorTimeLog).filter(
        SubcontractorTimeLog.id == log_id,
        SubcontractorTimeLog.subcontractor_id == sub_id,
        SubcontractorTimeLog.is_active == True,
    ).first()
    if not log:
        raise ValueError("not_found")
    if log.is_invoiced:
        raise ValueError("already_invoiced")
    log.is_active = False
    db.commit()
    return {"ok": True, "message": "Parte de horas eliminado correctamente"}


# ── Subcontractor Invoices ────────────────────────────────────────────────────

def get_sub_invoices(sub_id: str, db: Session) -> list:
    invs = db.query(SubcontractorInvoice).filter(
        SubcontractorInvoice.subcontractor_id == sub_id
    ).order_by(SubcontractorInvoice.issue_date.desc()).all()
    return [{
        "id": i.id, "invoice_number": i.invoice_number,
        "issue_date": str(i.issue_date), "due_date": str(i.due_date) if i.due_date else None,
        "amount": i.amount, "tax_pct": i.tax_pct, "total": i.total,
        "currency": i.currency, "status": i.status,
        "paid_date": str(i.paid_date) if i.paid_date else None,
        "description": i.description,
    } for i in invs]


def create_sub_invoice(sub_id: str, payload: dict, current_user, db: Session) -> dict:
    import uuid as _uuid
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()
    if not sub:
        raise ValueError("not_found")
    amount = float(payload.get("amount", 0))
    tax_pct = float(payload.get("tax_pct", settings.DEFAULT_TAX_RATE))
    total = round(amount * (1 + tax_pct / 100), 2)
    inv = SubcontractorInvoice(
        id=str(_uuid.uuid4()), subcontractor_id=sub_id,
        assignment_id=payload.get("assignment_id"),
        invoice_number=payload.get("invoice_number", f"SUB-INV-{_uuid.uuid4().hex[:6].upper()}"),
        issue_date=payload.get("issue_date"), due_date=payload.get("due_date"),
        amount=amount, tax_pct=tax_pct, total=total,
        currency=payload.get("currency", sub.currency or settings.DEFAULT_CURRENCY),
        description=payload.get("description"),
    )
    db.add(inv)
    if payload.get("timelog_ids"):
        db.query(SubcontractorTimeLog).filter(
            SubcontractorTimeLog.id.in_(payload["timelog_ids"]),
            SubcontractorTimeLog.subcontractor_id == sub_id,
            SubcontractorTimeLog.is_active == True,
        ).update({"is_invoiced": True, "invoice_id": inv.id}, synchronize_session=False)
    db.commit()
    audit_log(db, current_user, "CREATE", "subcontractor_invoices", inv.id, sub.name)
    return {"ok": True, "id": inv.id, "total": total}


def update_sub_invoice(sub_id: str, inv_id: str, payload: dict, db: Session) -> dict:
    inv = db.query(SubcontractorInvoice).filter(
        SubcontractorInvoice.id == inv_id, SubcontractorInvoice.subcontractor_id == sub_id
    ).first()
    if not inv:
        raise ValueError("not_found")
    for k in ["status", "paid_date", "description"]:
        if k in payload:
            setattr(inv, k, payload[k])
    db.commit()
    return {"ok": True}


# ── Subcontractor Dashboard ───────────────────────────────────────────────────

def get_subcontractors_dashboard(db: Session) -> dict:
    total_subs   = db.query(func.count(Subcontractor.id)).filter(Subcontractor.is_active == True).scalar()
    active_assgn = db.query(func.count(SubcontractorAssignment.id)).scalar()
    pending_invs = db.query(func.count(SubcontractorInvoice.id)).filter(SubcontractorInvoice.status == "received").scalar()
    total_cost   = db.query(func.sum(SubcontractorInvoice.total)).filter(SubcontractorInvoice.status.in_(["approved", "paid"])).scalar() or 0
    pending_cost = db.query(func.sum(SubcontractorInvoice.total)).filter(SubcontractorInvoice.status == "received").scalar() or 0
    total_hours  = db.query(func.sum(SubcontractorTimeLog.hours)).filter(SubcontractorTimeLog.is_active == True).scalar() or 0
    return {
        "total_active_subs": total_subs, "active_assignments": active_assgn,
        "pending_invoices": pending_invs, "total_paid_cost": round(total_cost, 2),
        "pending_approval_cost": round(pending_cost, 2), "total_hours_logged": round(total_hours, 1),
    }
