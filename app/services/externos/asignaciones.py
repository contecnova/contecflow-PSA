"""Asignar un externo a un proyecto = hacerle miembro; terminar = dejar de serlo.

`crear` valida que persona y tarifa son del proveedor, que las fechas caen en
la ventana de la persona y crea (o reactiva) su `ProjectMember` con papel,
dedicacion y fechas. `terminar` cierra la asignacion y, si no le queda otra
activa en ese proyecto, desactiva el miembro: deja de ver el proyecto y de
poder imputar en el (`_assert_project_membership` exige miembro activo).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error


def _miembro(db: Session, a, worker, role, allocation_pct):
    from app.models.project import ProjectMember, ProjectMemberRole
    papel = ProjectMemberRole(role) if role else ProjectMemberRole.developer
    m = db.query(ProjectMember).filter(ProjectMember.project_id == a.project_id,
                                       ProjectMember.user_id == worker.user_id).first()
    if m is None:
        m = ProjectMember(project_id=a.project_id, user_id=worker.user_id, organization_id=a.organization_id)
        db.add(m)
    m.is_active = True
    m.role = papel
    if allocation_pct:
        m.allocation_pct = int(allocation_pct)
    m.start_date = a.start_date
    m.end_date = a.end_date
    m.notes = (f"Externo · {a.subcontractor.name}" if a.subcontractor else "Externo")[:500]
    db.flush()
    return m


def crear(db: Session, sub, payload, actor) -> dict:
    from app.models.enterprise import SubcontractorAssignment, SubcontractorRate, SubcontractorWorker
    from app.models.project import Project
    from app.services.audit import audit_log
    datos = payload.model_dump()
    role = datos.pop("member_role", None)
    allocation = datos.pop("allocation_pct", None)
    if not db.query(Project.id).filter(Project.id == datos["project_id"]).first():
        raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    # Migracion 189: a una empresa no se le asigna nada como unidad por aqui. Sin
    # persona es trabajo externalizado: un paquete de trabajo (`proveedores.paquetes`).
    if not datos.get("worker_id"):
        raise ErrorDeDominio(422, "La asignación necesita una persona del proveedor; para externalizar trabajo "
                                  "a la empresa crea un paquete de trabajo.", code="proveedor_asignacion_sin_persona")
    from app.services.proveedores.ficha import exigir_activo
    exigir_activo(sub)
    worker = None
    if datos.get("worker_id"):
        worker = db.query(SubcontractorWorker).filter(
            SubcontractorWorker.id == datos["worker_id"], SubcontractorWorker.subcontractor_id == sub.id,
            SubcontractorWorker.is_active == True).first()  # noqa: E712
        if worker is None:
            raise ErrorDeDominio(400, "La persona no es de este proveedor o está de baja.",
                                 code="externo_persona_no_valida")
        ini, fin = datos.get("start_date"), datos.get("end_date")
        if (worker.available_from and ini and ini < worker.available_from) or \
           (worker.available_until and fin and fin > worker.available_until) or \
           (worker.available_until and not fin):
            if worker.available_until and not fin:
                datos["end_date"] = worker.available_until
            else:
                raise ErrorDeDominio(400, "Las fechas de la asignación salen de la disponibilidad de la persona.",
                                     code="externo_fuera_de_ventana",
                                     params={"desde": str(worker.available_from or ""),
                                             "hasta": str(worker.available_until or "")})
    if datos.get("rate_id"):
        ok = db.query(SubcontractorRate.id).filter(
            SubcontractorRate.id == datos["rate_id"], SubcontractorRate.subcontractor_id == sub.id,
            SubcontractorRate.is_active == True).first()  # noqa: E712
        if not ok:
            raise ErrorDeDominio(400, "La tarifa no es de este proveedor.", code="externo_tarifa_no_valida")
    a = SubcontractorAssignment(subcontractor_id=sub.id, organization_id=actor.organization_id, **datos)
    a.subcontractor = sub
    db.add(a)
    db.flush()
    if worker is not None:
        if not worker.user_id:
            from app.services.externos.ciclo import crear_usuario
            user, _ = crear_usuario(db, sub, {"name": worker.name, "email": worker.email, "role": worker.role,
                                              "cost_rate": worker.cost_rate, "currency": worker.currency,
                                              "weekly_capacity_hours": worker.weekly_capacity_hours,
                                              "internal_owner_id": worker.internal_owner_id}, actor, False)
            worker.user_id = user.id
            worker.has_access = False
        a.project_member_id = _miembro(db, a, worker, role, allocation).id
    audit_log(db, actor, "CREATE", "subcontractor_assignments", a.id, sub.name,
              new_values={"project_id": a.project_id, "worker_id": a.worker_id, "rate_id": a.rate_id,
                          "project_member_id": a.project_member_id})
    db.commit()
    return {"ok": True, "id": a.id, "project_member_id": a.project_member_id}


def terminar(db: Session, a, fecha: Optional[date], actor, auditar: bool = True) -> None:
    """Cierra la asignacion (no confirma) y, si procede, el miembro del proyecto."""
    from app.models.enterprise import SubcontractorAssignment
    from app.models.project import ProjectMember
    from app.services.audit import audit_log
    hoy = timeutil.today()
    fin = fecha or hoy
    if a.end_date is None or a.end_date > fin:
        a.end_date = fin
    a.is_active = False
    a.ended_at = hoy
    w = a.worker
    if w is not None and w.user_id:
        otra = db.query(SubcontractorAssignment.id).filter(
            SubcontractorAssignment.id != a.id, SubcontractorAssignment.worker_id == w.id,
            SubcontractorAssignment.project_id == a.project_id,
            SubcontractorAssignment.is_active == True).first()  # noqa: E712
        if not otra:
            m = db.query(ProjectMember).filter(ProjectMember.project_id == a.project_id,
                                               ProjectMember.user_id == w.user_id).first()
            if m is not None:
                m.is_active = False
                m.end_date = a.end_date
    if auditar:
        audit_log(db, actor, "UPDATE", "subcontractor_assignments", a.id, "terminada",
                  new_values={"end_date": str(a.end_date)})


def terminar_por_id(db: Session, sub_id: Optional[str], assignment_id: str, fecha, actor) -> dict:
    from app.models.enterprise import SubcontractorAssignment
    q = db.query(SubcontractorAssignment).filter(SubcontractorAssignment.id == assignment_id)
    if sub_id:
        q = q.filter(SubcontractorAssignment.subcontractor_id == sub_id)
    a = q.first()
    if a is None:
        raise error(404, "no_encontrado", detail="Asignación no encontrada", que="asignacion")
    if not a.is_active:
        raise ErrorDeDominio(409, "La asignación ya está terminada.", code="externo_asignacion_terminada")
    terminar(db, a, fecha, actor)
    db.commit()
    return {"ok": True, "id": a.id, "end_date": str(a.end_date)}
