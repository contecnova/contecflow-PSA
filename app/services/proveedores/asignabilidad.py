"""Quien puede recibir trabajo: personas o empresa (una sola regla).

- Freelance: es su persona; se asigna a ella (`assignee_id`), nunca al proveedor.
- Empresa con personas (staff augmentation): la empresa no es asignable; sus
  personas si.
- Empresa externalizada (outsourcing): asignable como unidad (`tasks.supplier_id`
  + paquete opcional), excluyente con `assignee_id`.
- Proveedor suspendido o dado de baja: ni el ni sus personas reciben trabajo nuevo.

Lo aplica un `before_flush` sobre `Task` (pantallas, masivas, IA,
automatizaciones e importaciones pasan por el). Solo mira lo que cambia: una
tarea antigua no se bloquea por guardarse con otro cambio.

Formacion y evaluaciones internas: solo para personas internas o externas cuyo
proveedor lo activa (`training_enabled`).
"""
from __future__ import annotations

from typing import Optional

from app.core.codigos_de_error import error
from app.services.proveedores.tipos import NO_ACTIVOS, modos


def _rechazo(codigo: str, **params):
    return error(422, codigo, **params)


def validar_proveedor_asignable(session, supplier_id: str, project_id: Optional[str] = None,
                                work_package_id: Optional[str] = None) -> None:
    from app.models.enterprise import Subcontractor
    from app.models.proveedores import SupplierWorkPackage
    sub = session.get(Subcontractor, supplier_id)
    if sub is None:
        raise error(404, "no_encontrado", detail="Proveedor no encontrado", que="proveedor")
    if (sub.kind or "company") == "freelance":
        raise _rechazo("proveedor_freelance_asigna_persona", proveedor=sub.name)
    if "outsourcing" not in modos(sub):
        raise _rechazo("proveedor_no_asignable", proveedor=sub.name)
    if (sub.lifecycle_status or "active") in NO_ACTIVOS or sub.is_active is False:
        raise _rechazo("proveedor_no_activo", proveedor=sub.name)
    if work_package_id:
        wp = session.get(SupplierWorkPackage, work_package_id)
        if wp is None or wp.subcontractor_id != sub.id or (project_id and wp.project_id != project_id) \
                or wp.status in ("accepted", "cancelled"):
            raise _rechazo("proveedor_paquete_no_valido")


def validar_persona_asignable(session, user_id: str) -> None:
    """La persona externa de un proveedor suspendido/de baja (o ella de baja) no recibe trabajo."""
    from app.models.enterprise import Subcontractor, SubcontractorWorker
    w = session.query(SubcontractorWorker).filter(SubcontractorWorker.user_id == user_id).first()
    if w is None:
        return
    sub = session.get(Subcontractor, w.subcontractor_id)
    if w.is_active is False or (sub is not None and ((sub.lifecycle_status or "active") in NO_ACTIVOS)):
        raise _rechazo("proveedor_persona_no_asignable", persona=w.name)


def _cambia(obj, atributo: str, nueva: bool) -> bool:
    from sqlalchemy import inspect as _inspect
    if nueva:
        return getattr(obj, atributo, None) is not None
    return _inspect(obj).attrs[atributo].history.has_changes()


def validar_tareas_antes_de_guardar(session, flush_context=None, instances=None) -> None:
    from app.models.task import Task
    candidatos = [o for o in list(session.new) + list(session.dirty) if isinstance(o, Task)]
    if not candidatos:
        return
    with session.no_autoflush:
        for t in candidatos:
            nueva = t in session.new
            cambia_prov = _cambia(t, "supplier_id", nueva) or _cambia(t, "supplier_work_package_id", nueva)
            cambia_persona = _cambia(t, "assignee_id", nueva)
            if not (cambia_prov or cambia_persona):
                continue
            if t.supplier_id and t.assignee_id:
                raise _rechazo("proveedor_asignacion_exclusiva")
            if t.supplier_work_package_id and not t.supplier_id:
                raise _rechazo("proveedor_paquete_no_valido")
            if cambia_prov and t.supplier_id:
                validar_proveedor_asignable(session, t.supplier_id, t.project_id, t.supplier_work_package_id)
            if cambia_persona and t.assignee_id:
                validar_persona_asignable(session, t.assignee_id)


def participa_en_desarrollo(db, user_id: str) -> bool:
    """¿Puede esta persona entrar en formacion y evaluaciones internas?"""
    from app.models.enterprise import Subcontractor, SubcontractorWorker
    w = db.query(SubcontractorWorker).filter(SubcontractorWorker.user_id == user_id).first()
    if w is None:
        return True
    sub = db.get(Subcontractor, w.subcontractor_id)
    return bool(sub is not None and sub.training_enabled)


def exigir_desarrollo_permitido(db, user_id: Optional[str], como_valor: bool = False) -> None:
    """422 si es externo sin `training_enabled`. `como_valor`: lanza `ErrorConCodigo`
    (servicios cuyo endpoint convierte `ValueError`)."""
    if not user_id or participa_en_desarrollo(db, user_id):
        return
    if como_valor:
        from app.core.codigos_de_error import ErrorConCodigo
        raise ErrorConCodigo("externo_sin_desarrollo_interno")
    raise _rechazo("externo_sin_desarrollo_interno")


def _registrar() -> None:
    from sqlalchemy import event
    from sqlalchemy.orm import Session as _Session
    if not event.contains(_Session, "before_flush", validar_tareas_antes_de_guardar):
        event.listen(_Session, "before_flush", validar_tareas_antes_de_guardar)


_registrar()
