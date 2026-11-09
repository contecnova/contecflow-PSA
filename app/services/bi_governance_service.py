from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.models.user import User
import logging

logger = logging.getLogger(__name__)

FIELD_SENSITIVITY_KEY = "bi.governance.field_sensitivity"
LINEAGE_KEY = "bi.governance.data_lineage"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _setting_row(db: Session, key: str, organization_id: Optional[str]) -> Optional[AppSetting]:
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if organization_id:
        q = q.filter(AppSetting.organization_id == organization_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    return q.first()


def _get_json(db: Session, key: str, organization_id: Optional[str], default: Any) -> Any:
    row = _setting_row(db, key, organization_id)
    if not row or not row.value:
        return default
    try:
        return json.loads(row.value)
    except Exception:
        return default


def _set_json(db: Session, key: str, organization_id: Optional[str], value: Any, description: str) -> None:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    row = _setting_row(db, key, organization_id)
    if row is None:
        row = AppSetting(key=key, organization_id=organization_id, value=payload, description=description)
        db.add(row)
    else:
        row.value = payload
        if not row.description:
            row.description = description
    db.commit()


def log_bi_access(
    db: Session,
    *,
    organization_id: Optional[str],
    current_user: User,
    entity_type: str,
    entity_id: str,
    action: str,
    ip_address: Optional[str],
    user_agent: Optional[str],
    before_state: Optional[dict[str, Any]] = None,
    after_state: Optional[dict[str, Any]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Un acceso a datos de BI, en el registro de auditoría de la plataforma.

    Revisión 2026-11: se guardaba en un JSON diario de `app_settings`, recortado
    a 3.000 eventos, y sólo lo escribía un botón de consola con un evento
    inventado: ningún acceso real quedaba registrado. Ahora va a `audit_logs`
    (con su cadena a prueba de manipulación) desde los accesos reales: ejecutar
    y exportar informes, y el Data Explorer.
    """
    from app.services.audit import audit_log
    try:
        fila = audit_log(db, current_user, action, f"bi:{entity_type}", resource_id=str(entity_id)[:36],
                         resource_name=str(entity_id)[:255], old_values=before_state, new_values=after_state,
                         metadata=extra, ip_address=ip_address, user_agent=(user_agent or "")[:500] or None)
        if organization_id and not getattr(fila, "organization_id", None):
            fila.organization_id = organization_id
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("No se pudo registrar el acceso BI %s %s", entity_type, entity_id, exc_info=True)
        return {}
    return _fila_de_acceso(fila)


def registrar_acceso(db: Session, request, usuario: User, entity_type: str, entity_id: str,
                     action: str = "view", extra: Optional[dict[str, Any]] = None) -> None:
    """Atajo para los endpoints que leen datos de BI: IP real y navegador de la petición."""
    from app.core.network import extract_client_ip
    log_bi_access(db, organization_id=getattr(usuario, "organization_id", None), current_user=usuario,
                  entity_type=entity_type, entity_id=entity_id, action=action,
                  ip_address=extract_client_ip(request) if request is not None else None,
                  user_agent=request.headers.get("user-agent") if request is not None else None, extra=extra)


def _fila_de_acceso(f) -> dict[str, Any]:
    import json as _json

    def _j(v):
        try:
            return _json.loads(v) if v else None
        except ValueError:
            return None
    return {
        "id": f.id,
        "timestamp": f.created_at.isoformat() if f.created_at else datetime.now(timezone.utc).isoformat(),
        "user_id": f.user_id, "user_name": f.user_name,
        "entity_type": (f.resource or "").removeprefix("bi:"), "entity_id": f.resource_name or f.resource_id,
        "action": (f.action or "").lower(), "ip_address": f.ip_address, "user_agent": f.user_agent,
        "before_state": _j(f.old_values), "after_state": _j(f.new_values), "extra": _j(f.metadata_) or {},
    }


def get_access_history(
    db: Session,
    *,
    organization_id: Optional[str],
    days: int = 30,
    user_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Accesos BI de los últimos `days` días (la sesión acota la empresa)."""
    from app.models.enterprise import AuditLog
    desde = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    q = db.query(AuditLog).filter(AuditLog.resource.like("bi:%"), AuditLog.created_at >= desde)
    if user_id:
        q = q.filter(AuditLog.user_id == user_id)
    if entity_type:
        q = q.filter(AuditLog.resource == f"bi:{entity_type}")
    if action:
        q = q.filter(AuditLog.action == action.upper())
    q = q.order_by(AuditLog.created_at.desc())
    if limit:
        q = q.limit(limit)
    return [_fila_de_acceso(f) for f in q.all()]


def list_lineage(db: Session, *, organization_id: Optional[str], target_table: Optional[str] = None) -> list[dict[str, Any]]:
    rows = _get_json(db, LINEAGE_KEY, organization_id, default=[])
    if target_table:
        rows = [r for r in rows if r.get("target_table") == target_table]
    rows.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return rows


def track_data_lineage(
    db: Session,
    *,
    organization_id: Optional[str],
    current_user: User,
    source_table: str,
    target_table: str,
    transformation_sql: str,
) -> dict[str, Any]:
    rows = _get_json(db, LINEAGE_KEY, organization_id, default=[])
    existing = next(
        (r for r in rows if r.get("source_table") == source_table and r.get("target_table") == target_table),
        None,
    )
    now = _iso_now()
    if existing:
        existing["transformation_sql"] = transformation_sql
        existing["updated_at"] = now
        item = existing
    else:
        item = {
            "id": str(uuid.uuid4()),
            "source_table": source_table,
            "target_table": target_table,
            "transformation_sql": transformation_sql,
            "created_by": current_user.id,
            "created_at": now,
            "updated_at": now,
        }
        rows.append(item)

    _set_json(db, LINEAGE_KEY, organization_id, rows, description="BI governance data lineage")
    return item


def list_field_sensitivity(
    db: Session,
    *,
    organization_id: Optional[str],
    dataset_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    rows = _get_json(db, FIELD_SENSITIVITY_KEY, organization_id, default=[])
    if dataset_id:
        rows = [r for r in rows if r.get("dataset_id") == dataset_id]
    rows.sort(key=lambda x: (x.get("dataset_id", ""), x.get("field_name", "")))
    return rows


def upsert_field_sensitivity(
    db: Session,
    *,
    organization_id: Optional[str],
    dataset_id: str,
    field_name: str,
    sensitivity_level: str,
    pii_fields: list[str],
    requires_approval: bool,
    current_user: User,
) -> dict[str, Any]:
    levels = {"public", "internal", "confidential", "restricted"}
    if sensitivity_level not in levels:
        raise ValueError("invalid_sensitivity_level")

    rows = _get_json(db, FIELD_SENSITIVITY_KEY, organization_id, default=[])
    now = _iso_now()
    existing = next(
        (r for r in rows if r.get("dataset_id") == dataset_id and r.get("field_name") == field_name),
        None,
    )

    if existing:
        existing.update(
            {
                "sensitivity_level": sensitivity_level,
                "pii_fields": pii_fields,
                "requires_approval": bool(requires_approval),
                "updated_at": now,
                "updated_by": current_user.id,
            }
        )
        item = existing
    else:
        item = {
            "id": str(uuid.uuid4()),
            "dataset_id": dataset_id,
            "field_name": field_name,
            "sensitivity_level": sensitivity_level,
            "pii_fields": pii_fields,
            "requires_approval": bool(requires_approval),
            "created_at": now,
            "updated_at": now,
            "created_by": current_user.id,
            "updated_by": current_user.id,
        }
        rows.append(item)

    _set_json(db, FIELD_SENSITIVITY_KEY, organization_id, rows, description="BI governance field sensitivity")
    return item
