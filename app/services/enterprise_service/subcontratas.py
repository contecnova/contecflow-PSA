"""Subcontratas: empresas, tarifas, asignaciones, trabajadores, habilidades, horas y facturas.

Parte de `app.services.enterprise_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session
from app.services.settings_service.por_empresa import iva_de_empresa, moneda_de_empresa
from app.models.enterprise import Subcontractor
from app.models.enterprise import SubcontractorWorker
from app.models.enterprise import SubcontractorRate
from app.models.enterprise import SubcontractorAssignment
from app.models.enterprise import SubcontractorTimeLog
from app.models.enterprise import SubcontractorInvoice
from app.models.user import User
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
        # Migracion 189: tipo, modos, ciclo de vida y GRC de la ficha.
        **_clasificacion(s),
    }


def _clasificacion(s) -> dict:
    from app.services.proveedores.serializar import clasificacion
    return clasificacion(s)


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
        "has_access": bool(w.has_access),
        "access_until": str(w.access_until) if w.access_until else None,
        # Migracion 191: contacto del portal del proveedor.
        "supplier_portal": bool(getattr(w, "supplier_portal", False)),
        "internal_owner_id": w.internal_owner_id,
        "internal_owner_name": w.internal_owner.full_name if w.internal_owner_id and w.internal_owner else None,
        "company_name": w.subcontractor.name if w.subcontractor else None,
        # Migracion 178: las habilidades son las del usuario (`user_skills`).
        "skills": _habilidades_del_usuario(w),
        "assignment_count": len(w.assignments or []),
    }


def _habilidades_del_usuario(w) -> list:
    from sqlalchemy.orm import object_session
    from app.models.resources import UserSkill
    db = object_session(w)
    if not w.user_id or db is None:
        return []
    filas = db.query(UserSkill).options(joinedload(UserSkill.skill)).filter(UserSkill.user_id == w.user_id).all()
    return [{
        "id": us.id, "skill_id": us.skill_id,
        "skill_name": us.skill.name if us.skill else None,
        "skill_category": us.skill.category.value if us.skill and us.skill.category else None,
        "level": us.level.value if hasattr(us.level, "value") else us.level,
        "years_experience": us.years_experience, "certified": us.certified,
        "cert_name": us.cert_name, "notes": us.notes,
    } for us in filas]


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
    """Alta de una persona externa con su `User` (ver `externos.ciclo`).

    Responsable interno obligatorio. Con acceso: contrasena temporal (se
    devuelve una vez). Sin acceso: recurso planificable sin credenciales.
    Despues: kit de alta de ALM y, si esta publicado, el proceso BPM
    `subcontractor_onboarding`.
    """
    from app.services.externos import ciclo
    datos = payload.model_dump()
    ciclo.exigir_responsable(db, datos.get("internal_owner_id"))
    con_acceso = datos.pop("has_access", True)
    if con_acceso is None:
        con_acceso = True
    if not datos.get("access_until"):
        datos["access_until"] = datos.get("available_until")
    linked_user, temp_password = ciclo.crear_usuario(db, sub, datos, current_user, con_acceso)
    worker = SubcontractorWorker(subcontractor_id=sub.id, user_id=linked_user.id, has_access=con_acceso,
                                 organization_id=current_user.organization_id, **datos)
    db.add(worker)
    db.flush()
    audit_log(db, current_user, "CREATE", "subcontractor_workers", worker.id, worker.name,
              new_values={"has_access": con_acceso, "internal_owner_id": worker.internal_owner_id,
                          "access_until": str(worker.access_until) if worker.access_until else None})
    ciclo.al_dar_de_alta(db, linked_user, current_user)
    db.commit()
    db.refresh(worker)
    result = serialize_worker(worker)
    result["login_username"] = linked_user.username if con_acceso else None
    if temp_password:
        result["temp_password"] = temp_password
    result["bpm_instance_id"] = ciclo.arrancar_proceso(db, "subcontractor_onboarding", current_user, {
        "worker_id": worker.id, "worker_name": worker.name, "subcontractor": sub.name,
        "internal_owner_id": worker.internal_owner_id})
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
    from app.services.externos.horas import consumo, umbral
    assignments = db.query(SubcontractorAssignment).options(
        joinedload(SubcontractorAssignment.project),
        joinedload(SubcontractorAssignment.rate),
        joinedload(SubcontractorAssignment.worker),
    ).filter(SubcontractorAssignment.subcontractor_id == sub_id).all()
    salida = []
    for a in assignments:
        c = consumo(db, a)
        u = umbral(db, a.organization_id)
        salida.append({
            "id": a.id, "project_id": a.project_id,
            "project_name": a.project.name if a.project else None,
            "project_code": a.project.code if a.project else None,
            "worker_id": a.worker_id, "worker_name": a.worker.name if a.worker else None,
            "rate_id": a.rate_id,
            "rate": {"description": a.rate.description, "cost_rate": a.rate.cost_rate} if a.rate else None,
            "po_number": a.po_number, "po_amount": a.po_amount,
            "hours_contracted": a.hours_contracted, "hours_logged": c["hours_logged"],
            "hours_imputed": c["hours_imputed"], "hours_manual": c["hours_manual"],
            "cost_amount": c["cost_amount"], "po_consumed_pct": c["po_consumed_pct"],
            "consumption_pct": c["consumption_pct"], "threshold_pct": u,
            "alert": bool(c["consumption_pct"] is not None and c["consumption_pct"] >= u),
            "budget_used_pct": c["hours_pct"],
            "start_date": str(a.start_date) if a.start_date else None,
            "end_date": str(a.end_date) if a.end_date else None,
            "is_active": bool(a.is_active), "ended_at": str(a.ended_at) if a.ended_at else None,
            "project_member_id": a.project_member_id,
            "notes": a.notes,
        })
    return salida


def create_subcontractor_assignment(sub_id: str, payload, current_user, db: Session) -> dict:
    """Asignar a proyecto = ProjectMember con persona, fechas y tarifa (`externos.asignaciones`)."""
    from app.services.externos import asignaciones
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()
    if not sub:
        raise ValueError("not_found")
    return asignaciones.crear(db, sub, payload, current_user)


def end_subcontractor_assignment(sub_id, assignment_id: str, end_date, current_user, db: Session) -> dict:
    from app.services.externos import asignaciones
    return asignaciones.terminar_por_id(db, sub_id, assignment_id, end_date, current_user)


def reconcile_invoices(sub_id: str, db: Session) -> list:
    from app.services.externos.conciliacion import conciliar
    return conciliar(db, sub_id)


# ── Subcontractor Workers ─────────────────────────────────────────────────────

def list_all_workers(skill_id, is_active, db: Session) -> list:
    q = db.query(SubcontractorWorker).options(
        joinedload(SubcontractorWorker.assignments),
        joinedload(SubcontractorWorker.subcontractor),
        joinedload(SubcontractorWorker.user),
    )
    if is_active is not None:
        q = q.filter(SubcontractorWorker.is_active == is_active)
    if skill_id:
        from app.models.resources import UserSkill
        q = q.join(UserSkill, UserSkill.user_id == SubcontractorWorker.user_id).filter(UserSkill.skill_id == skill_id)
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


def update_worker(worker_id: str, payload, db: Session, current_user=None) -> dict:
    """Actualiza un trabajador subcontratado y su usuario enlazado, si lo tiene.

    Acceso: activarlo a quien no lo tenia genera contrasena temporal (se
    devuelve una vez); quitarlo revoca sus sesiones. Desactivar (`is_active`
    false) es la baja completa (`externos.ciclo.dar_de_baja`).
    """
    from app.services.externos import ciclo
    worker = db.query(SubcontractorWorker).options(
        joinedload(SubcontractorWorker.assignments),
        joinedload(SubcontractorWorker.user),
    ).filter(
        SubcontractorWorker.id == worker_id,
        SubcontractorWorker.is_active == True,  # noqa: E712
    ).first()
    if not worker:
        raise ValueError("not_found")

    cambios = payload.model_dump(exclude_unset=True)
    if "internal_owner_id" in cambios:
        ciclo.exigir_responsable(db, cambios["internal_owner_id"])
    if cambios.get("is_active") is False:
        ciclo.dar_de_baja(db, worker, current_user)
    cambios.pop("is_active", None)
    acceso_antes = bool(worker.has_access)
    for clave, valor in cambios.items():
        setattr(worker, clave, valor)
    if "access_until" in cambios or "has_access" in cambios:
        worker.access_expiry_notified_at = None

    _sincronizar_usuario_enlazado(db, worker, cambios)

    temporal = None
    if worker.is_active and worker.user_id:
        if worker.has_access and not acceso_antes:
            temporal = ciclo.dar_acceso(db, worker)
        elif acceso_antes and not worker.has_access:
            ciclo.revocar_sesiones(db, worker.user_id)
    if current_user is not None:
        audit_log(db, current_user, "UPDATE", "subcontractor_workers", worker.id, worker.name,
                  new_values={k: str(v) for k, v in cambios.items()})
    db.commit()
    db.refresh(worker)
    result = serialize_worker(worker)
    if temporal:
        result["temp_password"] = temporal
    return result


def delete_worker(worker_id: str, db: Session, current_user=None) -> dict:
    """Baja del trabajador: termina sus asignaciones (deja de ser miembro), abre
    la baja de ALM (licencias y equipos), desactiva su usuario y sus sesiones."""
    from app.services.externos import ciclo
    worker = db.query(SubcontractorWorker).filter(
        SubcontractorWorker.id == worker_id,
        SubcontractorWorker.is_active == True,
    ).first()
    if not worker:
        raise ValueError("not_found")
    ciclo.dar_de_baja(db, worker, current_user)
    db.commit()
    return {"ok": True, "message": "Trabajador dado de baja correctamente"}


def _usuario_del_trabajador(worker_id: str, db: Session) -> str:
    worker = db.query(SubcontractorWorker).filter(
        SubcontractorWorker.id == worker_id,
        SubcontractorWorker.is_active == True,
    ).first()
    if not worker or not worker.user_id:
        raise ValueError("not_found")
    return worker.user_id


_NIVELES = {"basic": "basic", "beginner": "basic", "intermediate": "intermediate",
            "advanced": "advanced", "expert": "expert"}


def add_worker_skill(worker_id: str, payload, db: Session) -> dict:
    """Habilidad del externo = habilidad de su usuario (`user_skills`, migracion
    178): SmartMatch, analisis y prevision la ven como la de cualquiera."""
    from app.models.resources import SkillLevel, UserSkill
    user_id = _usuario_del_trabajador(worker_id, db)
    datos = payload.model_dump(exclude_unset=True)
    nivel = str(datos.pop("level", "intermediate") or "intermediate").lower()
    datos["level"] = SkillLevel(_NIVELES.get(nivel, "intermediate"))
    existing = db.query(UserSkill).filter(UserSkill.user_id == user_id, UserSkill.skill_id == payload.skill_id).first()
    if existing:
        for k, v in datos.items():
            setattr(existing, k, v)
        db.commit()
        return {"ok": True, "id": existing.id, "updated": True}
    us = UserSkill(user_id=user_id, **datos)
    db.add(us)
    db.commit()
    return {"ok": True, "id": us.id, "updated": False}


def remove_worker_skill(worker_id: str, skill_id: str, db: Session) -> dict:
    from app.models.resources import UserSkill
    user_id = _usuario_del_trabajador(worker_id, db)
    us = db.query(UserSkill).filter(UserSkill.user_id == user_id, UserSkill.skill_id == skill_id).first()
    if not us:
        raise ValueError("not_found")
    db.delete(us)
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
    nombres = {w.id: w.name for w in db.query(SubcontractorWorker).filter(SubcontractorWorker.subcontractor_id == sub_id)}
    return [{
        "id": l.id, "log_date": str(l.log_date), "hours": l.hours,
        "description": l.description, "task_reference": l.task_reference,
        "cost_amount": l.cost_amount, "is_invoiced": l.is_invoiced,
        "project_id": l.project_id,
        "project_name": l.project.name if l.project else None,
        "worker_id": l.worker_id, "worker_name": nombres.get(l.worker_id),
        "source": l.source,
    } for l in q.order_by(SubcontractorTimeLog.log_date.desc()).all()]


def create_timelog(sub_id: str, payload: dict, db: Session) -> dict:
    """Parte manual: SOLO para personas externas sin acceso (o importado).

    Quien tiene acceso imputa el mismo (una sola fuente). `hours_logged` de la
    asignacion lo recalcula `externos.horas` al confirmar; el coste sale de la
    tarifa vigente en la fecha.
    """
    import uuid as _uuid
    from datetime import date as _date
    from app.core.errores import ErrorDeDominio
    from app.services.externos.tarifas import tarifa_de_asignacion
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()
    if not sub:
        raise ValueError("not_found")
    assignment_id = payload.get("assignment_id")
    assignment = None
    if assignment_id:
        assignment = db.query(SubcontractorAssignment).filter(
            SubcontractorAssignment.id == assignment_id, SubcontractorAssignment.subcontractor_id == sub_id).first()
        if assignment is None:
            raise ValueError("not_found")
    worker_id = payload.get("worker_id") or (assignment.worker_id if assignment else None)
    if worker_id:
        worker = db.query(SubcontractorWorker).filter(
            SubcontractorWorker.id == worker_id, SubcontractorWorker.subcontractor_id == sub_id).first()
        if worker is None:
            raise ValueError("not_found")
        if worker.has_access:
            raise ErrorDeDominio(400, "Esta persona tiene acceso: imputa ella misma sus horas.",
                                 code="externo_con_acceso_imputa")
    fecha = payload.get("log_date")
    fecha = _date.fromisoformat(fecha) if isinstance(fecha, str) else fecha
    horas = float(payload.get("hours", 0))
    cost_amount = payload.get("cost_amount")
    if not cost_amount and assignment is not None:
        t = tarifa_de_asignacion(db, assignment, fecha or _date.today())
        if t:
            cost_amount = round(horas * t[0], 2)
    source = payload.get("source") if payload.get("source") in ("manual", "import") else "manual"
    log = SubcontractorTimeLog(
        id=str(_uuid.uuid4()), subcontractor_id=sub_id, organization_id=sub.organization_id,
        assignment_id=assignment_id,
        project_id=payload.get("project_id") or (assignment.project_id if assignment else None),
        worker_id=worker_id, source=source,
        log_date=fecha, hours=horas,
        description=payload.get("description"), task_reference=payload.get("task_reference"),
        cost_amount=cost_amount,
    )
    db.add(log)
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
        "description": i.description, "contract_id": i.contract_id, "created_by": i.created_by,
    } for i in invs]


def create_sub_invoice(sub_id: str, payload: dict, current_user, db: Session) -> dict:
    import uuid as _uuid
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()
    if not sub:
        raise ValueError("not_found")
    amount = float(payload.get("amount", 0))
    # 18-11-2026: IVA y moneda por defecto de la empresa del externo, no los globales del entorno.
    tax_pct = float(payload["tax_pct"]) if payload.get("tax_pct") is not None else iva_de_empresa(db, registro=sub)
    total = round(amount * (1 + tax_pct / 100), 2)
    inv = SubcontractorInvoice(
        id=str(_uuid.uuid4()), subcontractor_id=sub_id,
        assignment_id=payload.get("assignment_id"),
        invoice_number=payload.get("invoice_number", f"SUB-INV-{_uuid.uuid4().hex[:6].upper()}"),
        issue_date=payload.get("issue_date"), due_date=payload.get("due_date"),
        amount=amount, tax_pct=tax_pct, total=total,
        currency=payload.get("currency") or sub.currency or moneda_de_empresa(db, registro=sub),
        description=payload.get("description"),
        # Migracion 189: quien la registra no aprueba su estado de cuenta (segregacion).
        created_by=getattr(current_user, "id", None), contract_id=payload.get("contract_id"),
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
    db.commit()  # segunda auditoría 2026-11: el servicio ya había confirmado y la entrada se perdía
    from app.services.externos.ciclo import arrancar_proceso
    instancia = arrancar_proceso(db, "subcontractor_invoice", current_user, {
        "invoice_id": inv.id, "invoice_number": inv.invoice_number, "subcontractor": sub.name,
        "amount": amount, "total": total})
    return {"ok": True, "id": inv.id, "total": total, "bpm_instance_id": instancia}


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
