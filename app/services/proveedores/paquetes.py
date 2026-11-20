"""Trabajo externalizado: paquetes de trabajo, tareas externalizadas e informes.

Un paquete asigna a una empresa de outsourcing un proyecto entero, una fase, un
hito, un entregable o un conjunto de tareas. Ciclo: planned -> in_progress ->
delivered -> accepted | rejected (vuelve a in_progress/delivered), o cancelled.
Aceptar exige la UAT superada si el paquete tiene sesion, marca aceptado el
entregable o completado el hito de su alcance y deja su precio cerrado para la
siguiente prevision (`facturacion`).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core import timeutil
from app.core.codigos_de_error import error
from app.services.audit import audit_log
from app.services.proveedores import serializar as ser
from app.services.proveedores.tipos import SCOPE_TYPES, WP_TRANSICIONES, modos


def _contar_tareas(db: Session, ids: list) -> dict:
    from app.models.task import Task
    if not ids:
        return {}
    filas = db.query(Task.supplier_work_package_id, func.count(Task.id)).filter(
        Task.supplier_work_package_id.in_(ids), Task.is_active.isnot(False)).group_by(Task.supplier_work_package_id)
    return dict(filas.all())


def exigir(db: Session, wp_id: str):
    from app.models.proveedores import SupplierWorkPackage
    w = db.query(SupplierWorkPackage).options(joinedload(SupplierWorkPackage.project)).filter(
        SupplierWorkPackage.id == wp_id).first()
    if w is None:
        raise error(404, "no_encontrado", detail="Paquete no encontrado", que="paquete_de_trabajo")
    return w


def _uno(db: Session, w) -> dict:
    return ser.paquete(w, _contar_tareas(db, [w.id]).get(w.id, 0))


def listar(db: Session, sub_id: Optional[str] = None, project_id: Optional[str] = None) -> list:
    from app.models.proveedores import SupplierWorkPackage
    q = db.query(SupplierWorkPackage).options(joinedload(SupplierWorkPackage.project))
    if sub_id:
        q = q.filter(SupplierWorkPackage.subcontractor_id == sub_id)
    if project_id:
        q = q.filter(SupplierWorkPackage.project_id == project_id)
    filas = q.order_by(SupplierWorkPackage.planned_end.is_(None), SupplierWorkPackage.planned_end).all()
    n = _contar_tareas(db, [w.id for w in filas])
    return [ser.paquete(w, n.get(w.id, 0)) for w in filas]


def _validar_alcance(db: Session, w) -> None:
    from app.models.client_portal import UATSession
    from app.models.financial import ProjectMilestone
    from app.models.project import Project, ProjectPhase
    from app.models.resources import Deliverable
    if w.scope_type not in SCOPE_TYPES:
        raise error(422, "proveedor_alcance_no_valido", alcance=w.scope_type)
    if not db.query(Project.id).filter(Project.id == w.project_id).first():
        raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    comprobar = (("phase", "phase_id", ProjectPhase, "fase"), ("milestone", "milestone_id", ProjectMilestone, "hito"),
                 ("deliverable", "deliverable_id", Deliverable, "entregable"))
    for alcance, campo, modelo, que in comprobar:
        valor = getattr(w, campo)
        if w.scope_type == alcance and not valor:
            raise error(422, "campo_obligatorio", campo=campo)
        if valor and not db.query(modelo.id).filter(modelo.id == valor, modelo.project_id == w.project_id).first():
            raise error(404, "no_encontrado", detail="No encontrado en el proyecto", que=que)
    if w.uat_session_id and not db.query(UATSession.id).filter(
            UATSession.id == w.uat_session_id, UATSession.project_id == w.project_id).first():
        raise error(404, "no_encontrado", detail="Sesión UAT no encontrada", que="sesion_uat")
    if w.planned_start and w.planned_end and w.planned_end < w.planned_start:
        raise error(422, "proveedor_fechas_no_validas")


def crear(db: Session, sub, datos: dict, actor) -> dict:
    from app.models.proveedores import SupplierWorkPackage
    from app.services.proveedores import ficha
    ficha.exigir_activo(sub)
    if "outsourcing" not in modos(sub):
        raise error(422, "proveedor_sin_modo", modo="outsourcing", proveedor=sub.name)
    datos = {k: v for k, v in datos.items() if v is not None}
    for campo in ("project_id", "title"):
        if not datos.get(campo):
            raise error(422, "campo_obligatorio", campo=campo)
    w = SupplierWorkPackage(subcontractor_id=sub.id, status="planned", **datos)
    w.scope_type = w.scope_type or "tasks"
    w.currency = w.currency or sub.currency
    _validar_alcance(db, w)
    db.add(w)
    db.flush()
    audit_log(db, actor, "CREATE", "supplier_work_packages", w.id, w.title,
              new_values={"project_id": w.project_id, "scope_type": w.scope_type, "price": w.price})
    db.commit()
    return _uno(db, exigir(db, w.id))


def actualizar(db: Session, w, datos: dict, actor) -> dict:
    if w.status in ("accepted", "cancelled"):
        raise error(409, "proveedor_paquete_cerrado")
    antes = ser.paquete(w)
    for k, v in datos.items():
        setattr(w, k, v)
    _validar_alcance(db, w)
    audit_log(db, actor, "UPDATE", "supplier_work_packages", w.id, w.title,
              old_values={k: antes.get(k) for k in datos},
              new_values={k: (str(v) if hasattr(v, "isoformat") else v) for k, v in datos.items()})
    db.commit()
    return _uno(db, exigir(db, w.id))


def _aceptar_alcance(db: Session, w, actor) -> None:
    from app.models.client_portal import UATSession
    from app.models.financial import ProjectMilestone
    from app.models.resources import Deliverable, DeliverableStatus
    if w.uat_session_id:
        uat = db.get(UATSession, w.uat_session_id)
        estado = getattr(uat.status, "value", uat.status) if uat else None
        if estado not in ("passed", "conditional"):
            raise error(409, "proveedor_uat_pendiente")
    hoy = timeutil.today()
    if w.deliverable_id:
        d = db.get(Deliverable, w.deliverable_id)
        if d is not None:
            d.status = DeliverableStatus.accepted
    if w.milestone_id:
        m = db.get(ProjectMilestone, w.milestone_id)
        if m is not None and not m.is_completed:
            m.is_completed = True
            m.completed_date = hoy
            m.completed_by = actor.id if actor else None


def transicion(db: Session, w, accion: str, actor, motivo: Optional[str] = None) -> dict:
    if accion not in WP_TRANSICIONES:
        raise error(422, "proveedor_accion_no_valida", accion=accion)
    origen, destino = WP_TRANSICIONES[accion]
    if w.status not in origen:
        raise error(409, "proveedor_transicion_no_valida", desde=w.status, accion=accion)
    hoy = timeutil.today()
    if accion == "deliver":
        w.delivered_at = hoy
        w.progress_pct = 100.0
    elif accion == "accept":
        _aceptar_alcance(db, w, actor)
        w.accepted_at = hoy
        w.accepted_by = actor.id if actor else None
        w.rejection_reason = None
    elif accion == "reject":
        if not (motivo or "").strip():
            raise error(422, "campo_obligatorio", campo="reason")
        w.rejection_reason = motivo
        w.rejections = (w.rejections or 0) + 1
    elif accion == "cancel":
        from app.models.task import Task
        # Las tareas externalizadas de un paquete cancelado vuelven a estar sin asignar.
        db.query(Task).filter(Task.supplier_work_package_id == w.id).update(
            {"supplier_id": None, "supplier_work_package_id": None}, synchronize_session=False)
    anterior = w.status
    w.status = destino
    audit_log(db, actor, "APPROVE" if accion == "accept" else ("REJECT" if accion == "reject" else "UPDATE"),
              "supplier_work_packages", w.id, w.title, old_values={"status": anterior},
              new_values={"status": destino, "reason": motivo})
    db.commit()
    return _uno(db, exigir(db, w.id))


def externalizar_tareas(db: Session, w, task_ids: list, actor) -> dict:
    """Las tareas del proyecto del paquete pasan a la empresa (sin asignado)."""
    from app.models.task import Task
    if w.status in ("accepted", "cancelled"):
        raise error(409, "proveedor_paquete_cerrado")
    tareas = db.query(Task).filter(Task.id.in_(task_ids), Task.project_id == w.project_id).all()
    if len(tareas) != len(set(task_ids)):
        raise error(404, "no_encontrado", detail="Alguna tarea no es del proyecto del paquete", que="tarea")
    for t in tareas:
        t.assignee_id = None
        t.supplier_id = w.subcontractor_id
        t.supplier_work_package_id = w.id
    audit_log(db, actor, "ASSIGN", "supplier_work_packages", w.id, w.title,
              new_values={"task_ids": [t.id for t in tareas]})
    db.commit()
    return _uno(db, exigir(db, w.id))


def del_proyecto(db: Session, project_id: str) -> dict:
    from app.models.enterprise import Subcontractor
    from app.models.task import Task
    filas = db.query(Task, Subcontractor.name).join(Subcontractor, Subcontractor.id == Task.supplier_id).filter(
        Task.project_id == project_id, Task.is_active.isnot(False)).all()
    return {
        "work_packages": listar(db, project_id=project_id),
        "tasks": [{"id": t.id, "code": t.code, "title": t.title, "status": getattr(t.status, "value", t.status),
                   "supplier_id": t.supplier_id, "supplier_name": nombre,
                   "supplier_work_package_id": t.supplier_work_package_id} for t, nombre in filas],
    }


# ── Informes de avance y periodicos ─────────────────────────────────────────

def listar_informes(db: Session, sub_id: str) -> list:
    from app.models.proveedores import SupplierReport
    return [ser.informe(r) for r in db.query(SupplierReport).filter(SupplierReport.subcontractor_id == sub_id)
            .order_by(SupplierReport.created_at.desc()).all()]


def crear_informe(db: Session, sub, datos: dict, actor) -> dict:
    """Informe registrado por el responsable interno (el proveedor lo sube desde su portal: `portal`)."""
    from app.models.proveedores import SupplierReport, SupplierWorkPackage
    from app.services.proveedores.portal import _validar_adjuntos_enlace, validar_informe
    datos = {k: v for k, v in datos.items() if v is not None}
    adjuntos = _validar_adjuntos_enlace(datos.pop("attachments", None))
    datos = validar_informe(db, sub, datos)
    wp = db.get(SupplierWorkPackage, datos["work_package_id"]) if datos.get("work_package_id") else None
    r = SupplierReport(subcontractor_id=sub.id, submitted_by=actor.id, status="submitted", submitted_via="internal",
                       attachments=adjuntos or None, **datos)
    db.add(r)
    if wp is not None:
        wp.last_report_at = timeutil.today()
        if r.progress_pct is not None:
            wp.progress_pct = r.progress_pct
    db.flush()
    audit_log(db, actor, "CREATE", "supplier_reports", r.id, sub.name,
              new_values={"work_package_id": r.work_package_id, "service_id": r.service_id,
                          "report_type": r.report_type, "attachments": len(adjuntos)})
    db.commit()
    db.refresh(r)
    return ser.informe(r)


def revisar_informe(db: Session, informe_id: str, notas: Optional[str], actor) -> dict:
    from datetime import datetime, timezone

    from app.models.proveedores import SupplierReport
    r = db.query(SupplierReport).filter(SupplierReport.id == informe_id).first()
    if r is None:
        raise error(404, "no_encontrado", detail="Informe no encontrado", que="informe")
    r.status = "reviewed"
    r.reviewed_by = actor.id
    r.reviewed_at = datetime.now(timezone.utc)
    r.review_notes = notas
    audit_log(db, actor, "APPROVE", "supplier_reports", r.id, "revisado")
    db.commit()
    db.refresh(r)
    return ser.informe(r)
