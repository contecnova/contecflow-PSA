"""Ayudantes compartidos: organizacion de la sesion, alcance de facturas y bloqueo de proyecto.

Parte de `app.services.billing_reports_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from app.models.project import Project
from app.models.billing_reports import Invoice
from app.db.session import is_postgres


_logger = logging.getLogger("app.services.billing_reports_service")


def _tenant_org_id(db: Session):
    return db.info.get("organization_id")


def _is_superadmin(db: Session) -> bool:
    return bool(db.info.get("is_superadmin", False))


def _query_project_for_org(db: Session, project_id: str):
    q = db.query(Project).filter(Project.id == project_id)
    org_id = _tenant_org_id(db)
    if not _is_superadmin(db) and org_id is not None:
        q = q.filter(Project.organization_id == org_id)
    return q


def _lock_project_for_update(db: Session, project_id: str):
    q = _query_project_for_org(db, project_id)
    if is_postgres():
        q = q.with_for_update()
    return q.first()


def _set_serializable_if_postgres(db: Session) -> None:
    # Transaction-level hardening for financial writes in PostgreSQL.
    # Revisión 2026-11: el nivel sólo se puede fijar ANTES de la primera consulta de
    # la transacción, y cuando llega aquí ya se han hecho (cargar el usuario, el
    # `set_config` del RLS): Postgres lo rechazaba y crear una factura o cambiar
    # su estado daba 500. Se cierra la transacción de la petición y el SET va el
    # primero de la nueva, por el driver para no pasar por el evento del RLS.
    if is_postgres():
        db.commit()
        db.connection().exec_driver_sql("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")


def _is_serialization_failure(exc: OperationalError) -> bool:
    code = getattr(getattr(exc, "orig", None), "pgcode", None)
    return str(code) == "40001"


def _scope_invoice_query(db: Session):
    q = db.query(Invoice)
    org_id = _tenant_org_id(db)
    if _is_superadmin(db):
        return q
    if org_id is None:
        return q.filter(Invoice.id == "__no_access__")
    return q.filter(Invoice.organization_id == org_id)
