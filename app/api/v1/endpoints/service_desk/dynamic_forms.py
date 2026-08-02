"""Service Desk — Dynamic ticket forms, config history, and import wizard endpoints."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.core.responses import APIResponse, APIListResponse
from app.db.session import get_db
from app.models.client_portal import ClientUser
from app.models.clients import Client
from app.models.settings import AppSetting
from app.models.service_desk import ConfigurationItem, ServiceItem
from app.models.user import User
from app.services.service_desk.portal_auth_service import get_current_portal_client

router = APIRouter()

_RULES_KEY = "sd.dynamic_forms.rules"
_HISTORY_KEY = "sd.dynamic_forms.history"
_MAX_HISTORY = 30


class DynamicRulesIn(BaseModel):
    fields: list[dict] = Field(default_factory=list)
    routing_hints: list[dict] = Field(default_factory=list)
    cmdb_context_enabled: bool = True
    customer_context_enabled: bool = True
    reason: Optional[str] = None


class ImportPreviewIn(BaseModel):
    csv_text: str = Field(..., min_length=1)
    mapping: dict[str, str | dict] = Field(default_factory=dict, description="csv column -> dynamic field mapping")


class ImportApplyIn(BaseModel):
    generated_fields: list[dict] = Field(default_factory=list)
    merge_mode: str = Field("upsert", pattern="^(upsert|replace)$")
    reason: Optional[str] = None


class RollbackIn(BaseModel):
    snapshot_id: str


class DiffIn(BaseModel):
    left_snapshot_id: Optional[str] = None
    right_snapshot_id: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_setting(db: Session, key: str, org_id: Optional[str]) -> Optional[AppSetting]:
    return (
        db.query(AppSetting)
        .filter(AppSetting.key == key, AppSetting.organization_id == org_id)
        .first()
    )


def _get_json(db: Session, key: str, org_id: Optional[str], fallback):
    row = _get_setting(db, key, org_id)
    if not row or not row.value:
        return fallback
    try:
        return json.loads(row.value)
    except Exception:
        return fallback


def _set_json(db: Session, key: str, org_id: Optional[str], value: dict | list, description: str) -> None:
    payload = json.dumps(value, ensure_ascii=False)
    row = _get_setting(db, key, org_id)
    if row:
        row.value = payload
        row.description = description
    else:
        db.add(AppSetting(
            key=key,
            organization_id=org_id,
            value=payload,
            description=description,
        ))


def _default_rules() -> dict:
    return {
        "version": 1,
        "updated_at": _now_iso(),
        "updated_by": None,
        "cmdb_context_enabled": True,
        "customer_context_enabled": True,
        "fields": [
            {
                "id": "affected_environment",
                "label": "Entorno afectado",
                "type": "select",
                "required": False,
                "options": ["produccion", "preproduccion", "desarrollo"],
                "visible_when": {"field": "ticket_type", "in": ["incident", "change"]},
            },
            {
                "id": "business_impact_details",
                "label": "Impacto de negocio",
                "type": "textarea",
                "required": False,
                "visible_when": {"field": "impact", "in": ["enterprise", "department"]},
            },
            {
                "id": "requested_due_date",
                "label": "Fecha objetivo",
                "type": "date",
                "required": False,
                "visible_when": {"field": "ticket_type", "in": ["service_request", "change"]},
            },
        ],
        "routing_hints": [
            {"when": {"field": "ticket_type", "equals": "incident"}, "set": {"queue": "incident_l1"}},
            {"when": {"field": "impact", "equals": "enterprise"}, "set": {"priority": "p2_high"}},
        ],
    }


def _append_history(db: Session, org_id: Optional[str], snapshot: dict) -> None:
    history = _get_json(db, _HISTORY_KEY, org_id, fallback=[])
    if not isinstance(history, list):
        history = []
    history.insert(0, snapshot)
    history = history[:_MAX_HISTORY]
    _set_json(db, _HISTORY_KEY, org_id, history, "Service Desk dynamic forms configuration history")


def _save_rules_with_history(db: Session, org_id: Optional[str], new_rules: dict, user_id: Optional[str], reason: Optional[str]) -> dict:
    current = _get_json(db, _RULES_KEY, org_id, fallback=_default_rules())
    if not isinstance(current, dict):
        current = _default_rules()

    snapshot = {
        "snapshot_id": str(uuid4()),
        "created_at": _now_iso(),
        "created_by": user_id,
        "reason": reason or "manual_update",
        "rules": current,
    }
    _append_history(db, org_id, snapshot)

    payload = {
        "version": int(current.get("version", 1)) + 1,
        "updated_at": _now_iso(),
        "updated_by": user_id,
        "cmdb_context_enabled": bool(new_rules.get("cmdb_context_enabled", True)),
        "customer_context_enabled": bool(new_rules.get("customer_context_enabled", True)),
        "fields": list(new_rules.get("fields") or []),
        "routing_hints": list(new_rules.get("routing_hints") or []),
    }
    _set_json(db, _RULES_KEY, org_id, payload, "Service Desk dynamic forms rules")
    db.commit()
    return payload


def _visible_options(values: list[str]) -> list[str]:
    uniq = []
    seen = set()
    for v in values:
        x = (v or "").strip()
        if not x:
            continue
        k = x.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(x)
    return uniq[:20]


def _normalize_mapping_rule(rule: str | dict | None, fallback_col: str) -> tuple[str, str, Optional[str], Optional[str]]:
    """Return (field_id, field_type, data_source, data_attribute)."""
    field_id = fallback_col.strip().lower().replace(" ", "_")
    field_type = "text"
    data_source = None
    data_attribute = None

    if isinstance(rule, str):
        clean = rule.strip()
        if clean:
            field_id = clean.lower().replace(" ", "_")
            if clean.startswith("ci."):
                field_id = clean.replace(".", "_").lower()
                field_type = "context_ci"
                data_source = "ci"
                data_attribute = clean.split(".", 1)[1]
            elif clean.startswith("service."):
                field_type = "context_service"
                data_source = "service"
                data_attribute = clean.split(".", 1)[1]
            elif clean.startswith("client."):
                field_type = "context_client"
                data_source = "client"
                data_attribute = clean.split(".", 1)[1]
    elif isinstance(rule, dict):
        explicit_id = str(rule.get("id") or "").strip()
        if explicit_id:
            field_id = explicit_id.lower().replace(" ", "_")
        source = str(rule.get("source") or "").strip().lower()
        attr = str(rule.get("attribute") or "").strip().lower() or None
        if source in {"ci", "service", "client"}:
            field_type = f"context_{source}"
            data_source = source
            data_attribute = attr

    # Heuristic fallback by column name for frictionless onboarding.
    col_l = fallback_col.strip().lower().replace(" ", "_")
    if field_type == "text":
        if col_l.startswith("ci_") or col_l in {"ci", "ci_name", "configuration_item", "configuration_item_code"}:
            field_type = "context_ci"
            data_source = "ci"
            data_attribute = col_l.replace("ci_", "") or "name"
        elif col_l.startswith("service_") or col_l in {"service", "service_name"}:
            field_type = "context_service"
            data_source = "service"
            data_attribute = col_l.replace("service_", "") or "name"
        elif col_l.startswith("client_") or col_l in {"client", "client_name"}:
            field_type = "context_client"
            data_source = "client"
            data_attribute = col_l.replace("client_", "") or "name"

    return field_id, field_type, data_source, data_attribute


def _pick(obj: object, attr: str, default: str = "") -> str:
    value = getattr(obj, attr, None)
    return str(value or default)


def _context_options_payload(
    db: Session,
    *,
    current_user: Optional[User] = None,
    portal_client: Optional[ClientUser] = None,
    client_id: Optional[str] = None,
    service_item_id: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 40,
) -> dict:
    qn = (q or "").strip().lower()

    service_q = db.query(ServiceItem).filter(ServiceItem.is_active.is_(True))
    if portal_client is not None:
        service_q = service_q.filter(ServiceItem.is_visible_to_clients.is_(True))
    if service_item_id:
        service_q = service_q.filter(ServiceItem.id == service_item_id)
    services = service_q.order_by(ServiceItem.name.asc()).limit(max(5, limit)).all()

    clients = []
    if portal_client is not None:
        if portal_client.client_org_id:
            c = db.query(Client).filter(Client.id == portal_client.client_org_id).first()
            if c:
                clients = [c]
    else:
        client_q = db.query(Client)
        if client_id:
            client_q = client_q.filter(Client.id == client_id)
        clients = client_q.order_by(Client.name.asc()).limit(max(5, limit)).all()

    ci_q = db.query(ConfigurationItem)
    if portal_client is not None:
        project_ids = portal_client.get_project_ids()
        if project_ids:
            ci_q = ci_q.filter(ConfigurationItem.project_id.in_(project_ids))
        elif portal_client.client_org_id:
            ci_q = ci_q.filter(ConfigurationItem.project_id.is_(None))
    if qn:
        ci_q = ci_q.filter(
            (ConfigurationItem.name.ilike(f"%{qn}%"))
            | (ConfigurationItem.code.ilike(f"%{qn}%"))
            | (ConfigurationItem.environment.ilike(f"%{qn}%"))
        )
    cis = ci_q.order_by(ConfigurationItem.name.asc()).limit(max(5, limit)).all()

    return {
        "clients": [
            {
                "id": c.id,
                "name": _pick(c, "name"),
            }
            for c in clients
            if (not qn) or (qn in _pick(c, "name").lower())
        ][:limit],
        "services": [
            {
                "id": s.id,
                "name": _pick(s, "name"),
                "ticket_type": str(getattr(s, "ticket_type", "") or ""),
            }
            for s in services
            if (not qn) or (qn in _pick(s, "name").lower())
        ][:limit],
        "cis": [
            {
                "id": ci.id,
                "code": _pick(ci, "code"),
                "name": _pick(ci, "name"),
                "ci_type": str(getattr(ci, "ci_type", "") or ""),
                "status": str(getattr(ci, "status", "") or ""),
                "environment": _pick(ci, "environment"),
                "project_id": getattr(ci, "project_id", None),
            }
            for ci in cis
        ][:limit],
    }


@router.get("/dynamic-forms", summary="Obtener configuración de formulario dinámico de tickets")
def get_dynamic_forms(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    org_id = getattr(current_user, "organization_id", None)
    rules = _get_json(db, _RULES_KEY, org_id, fallback=None)
    if not isinstance(rules, dict):
        rules = _default_rules()
        _set_json(db, _RULES_KEY, org_id, rules, "Service Desk dynamic forms rules")
        db.commit()
    return APIResponse.ok(data=rules)


@router.get("/dynamic-forms/public", summary="Obtener configuración dinámica para portal cliente")
def get_dynamic_forms_public(
    db: Session = Depends(get_db),
    _client=Depends(get_current_portal_client),
):
    # Portal clients currently use the global baseline rules.
    rules = _get_json(db, _RULES_KEY, None, fallback=None)
    if not isinstance(rules, dict):
        rules = _default_rules()
        _set_json(db, _RULES_KEY, None, rules, "Service Desk dynamic forms rules")
        db.commit()
    return APIResponse.ok(data=rules)


@router.get("/dynamic-forms/context-options", summary="Opciones contextuales para campos dinámicos (clientes/servicios/CI)")
def get_dynamic_forms_context_options(
    client_id: Optional[str] = None,
    service_item_id: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 40,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    _ = org_id
    return APIResponse.ok(data=_context_options_payload(
        db,
        current_user=current_user,
        client_id=client_id,
        service_item_id=service_item_id,
        q=q,
        limit=max(5, min(limit, 200)),
    ))


@router.get("/dynamic-forms/public/context-options", summary="Opciones contextuales para portal cliente")
def get_dynamic_forms_public_context_options(
    service_item_id: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 40,
    db: Session = Depends(get_db),
    client=Depends(get_current_portal_client),
):
    return APIResponse.ok(data=_context_options_payload(
        db,
        portal_client=client,
        service_item_id=service_item_id,
        q=q,
        limit=max(5, min(limit, 200)),
    ))


@router.put("/dynamic-forms", summary="Guardar configuración de formulario dinámico")
def put_dynamic_forms(payload: DynamicRulesIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    org_id = getattr(current_user, "organization_id", None)
    rules = _save_rules_with_history(
        db,
        org_id,
        {
            "fields": payload.fields,
            "routing_hints": payload.routing_hints,
            "cmdb_context_enabled": payload.cmdb_context_enabled,
            "customer_context_enabled": payload.customer_context_enabled,
        },
        user_id=current_user.id,
        reason=payload.reason,
    )
    return APIResponse.ok(data={"ok": True, "rules": rules})


@router.get("/dynamic-forms/history", summary="Historial de configuración de formulario dinámico")
def get_dynamic_forms_history(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    org_id = getattr(current_user, "organization_id", None)
    history = _get_json(db, _HISTORY_KEY, org_id, fallback=[])
    if not isinstance(history, list):
        history = []
    return APIListResponse.ok(items=history)


@router.post("/dynamic-forms/diff", summary="Comparar dos snapshots de configuración dinámica")
def diff_dynamic_forms(payload: DiffIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    org_id = getattr(current_user, "organization_id", None)
    history = _get_json(db, _HISTORY_KEY, org_id, fallback=[])
    if not isinstance(history, list):
        history = []

    current_rules = _get_json(db, _RULES_KEY, org_id, fallback=_default_rules())
    if not isinstance(current_rules, dict):
        current_rules = _default_rules()

    by_id = {str(x.get("snapshot_id")): x for x in history if x.get("snapshot_id")}

    left = by_id.get(payload.left_snapshot_id) if payload.left_snapshot_id else None
    right = by_id.get(payload.right_snapshot_id) if payload.right_snapshot_id else None

    left_rules = (left or {}).get("rules") if left else current_rules
    right_rules = (right or {}).get("rules") if right else current_rules
    if not isinstance(left_rules, dict) or not isinstance(right_rules, dict):
        raise HTTPException(status_code=400, detail="Snapshots inválidos para diff")

    left_fields = {str(f.get("id")): f for f in (left_rules.get("fields") or []) if f.get("id")}
    right_fields = {str(f.get("id")): f for f in (right_rules.get("fields") or []) if f.get("id")}

    added = [right_fields[k] for k in right_fields.keys() - left_fields.keys()]
    removed = [left_fields[k] for k in left_fields.keys() - right_fields.keys()]
    changed = []
    for fid in sorted(left_fields.keys() & right_fields.keys()):
        if left_fields[fid] != right_fields[fid]:
            changed.append({
                "id": fid,
                "before": left_fields[fid],
                "after": right_fields[fid],
            })

    left_hints = left_rules.get("routing_hints") or []
    right_hints = right_rules.get("routing_hints") or []

    return APIResponse.ok(data={
        "left": {
            "snapshot_id": payload.left_snapshot_id,
            "version": left_rules.get("version"),
        },
        "right": {
            "snapshot_id": payload.right_snapshot_id,
            "version": right_rules.get("version"),
        },
        "summary": {
            "fields_added": len(added),
            "fields_removed": len(removed),
            "fields_changed": len(changed),
            "routing_hints_changed": left_hints != right_hints,
        },
        "fields": {
            "added": added,
            "removed": removed,
            "changed": changed,
        },
        "routing_hints": {
            "before": left_hints,
            "after": right_hints,
        },
    })


@router.post("/dynamic-forms/rollback", summary="Restaurar una configuración anterior del formulario dinámico")
def rollback_dynamic_forms(payload: RollbackIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    org_id = getattr(current_user, "organization_id", None)
    history = _get_json(db, _HISTORY_KEY, org_id, fallback=[])
    if not isinstance(history, list):
        history = []

    match = next((x for x in history if x.get("snapshot_id") == payload.snapshot_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    restored = match.get("rules")
    if not isinstance(restored, dict):
        raise HTTPException(status_code=400, detail="Snapshot is invalid")

    rules = _save_rules_with_history(
        db,
        org_id,
        restored,
        user_id=current_user.id,
        reason=f"rollback:{payload.snapshot_id}",
    )
    return APIResponse.ok(data={"ok": True, "rules": rules})


@router.post("/dynamic-forms/import/preview", summary="Wizard: previsualizar importación y mapeo de campos dinámicos")
def preview_dynamic_forms_import(payload: ImportPreviewIn, current_user: User = Depends(require_admin)):
    _ = current_user
    stream = io.StringIO(payload.csv_text)
    try:
        reader = csv.DictReader(stream)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"CSV inválido: {exc}")

    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV sin cabeceras")

    rows = []
    for i, row in enumerate(reader):
        rows.append(row)
        if i >= 199:
            break

    generated = []
    mapping = payload.mapping or {}
    for col in reader.fieldnames:
        field_id, mapped_type, data_source, data_attribute = _normalize_mapping_rule(mapping.get(col), col)
        values = _visible_options([str(r.get(col, "")) for r in rows])
        inferred_type = mapped_type
        if inferred_type == "text":
            inferred_type = "select" if 1 < len(values) <= 12 else "text"
        generated.append({
            "source_column": col,
            "id": field_id,
            "label": col,
            "type": inferred_type,
            "required": False,
            "options": values if inferred_type == "select" else [],
            "visible_when": None,
            "data_source": data_source,
            "data_attribute": data_attribute,
        })

    return APIResponse.ok(data={
        "columns": reader.fieldnames,
        "row_count": len(rows),
        "generated_fields": generated,
        "sample_rows": rows[:5],
    })


@router.post("/dynamic-forms/import/apply", summary="Wizard: aplicar importación/mapeo de campos dinámicos")
def apply_dynamic_forms_import(payload: ImportApplyIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    org_id = getattr(current_user, "organization_id", None)
    current = _get_json(db, _RULES_KEY, org_id, fallback=_default_rules())
    if not isinstance(current, dict):
        current = _default_rules()

    existing_fields = list(current.get("fields") or [])
    incoming_fields = list(payload.generated_fields or [])

    if payload.merge_mode == "replace":
        merged = incoming_fields
    else:
        by_id = {str(f.get("id")): f for f in existing_fields if f.get("id")}
        for f in incoming_fields:
            fid = str(f.get("id") or "").strip()
            if not fid:
                continue
            by_id[fid] = f
        merged = list(by_id.values())

    rules = _save_rules_with_history(
        db,
        org_id,
        {
            "fields": merged,
            "routing_hints": current.get("routing_hints") or [],
            "cmdb_context_enabled": bool(current.get("cmdb_context_enabled", True)),
            "customer_context_enabled": bool(current.get("customer_context_enabled", True)),
        },
        user_id=current_user.id,
        reason=payload.reason or f"import:{payload.merge_mode}",
    )
    return APIResponse.ok(data={"ok": True, "rules": rules, "field_count": len(merged)})
