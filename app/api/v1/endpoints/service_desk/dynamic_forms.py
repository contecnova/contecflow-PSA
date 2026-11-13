"""Service Desk — Dynamic ticket forms, config history, and import wizard endpoints."""
from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.core.responses import APIResponse, APIListResponse
from app.db.session import get_db
from app.models.user import User
from app.core.deps import get_current_portal_client

router = APIRouter()

# Auditoria 2026-08 (hallazgo 22): las claves de `AppSetting`, los ayudantes de
# lectura y escritura, el historial de configuracion y el selector de opciones
# de contexto viven ahora en `services/service_desk/dynamic_forms_service.py`.
# Los cuerpos se movieron verbatim; los modelos Pydantic de abajo se quedan,
# que son el contrato de entrada de las rutas.
from app.services.service_desk.dynamic_forms_service import (
    _HISTORY_KEY,
    _RULES_KEY,
    _context_options_payload,
    _default_rules,
    _get_json,
    _normalize_mapping_rule,
    _save_rules_with_history,
    _visible_options,
    reglas_o_sembrar,
)

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


@router.get("/dynamic-forms", summary="Obtener configuración de formulario dinámico de tickets")
def get_dynamic_forms(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=reglas_o_sembrar(db, org_id))


@router.get("/dynamic-forms/public", summary="Obtener configuración dinámica para portal cliente")
def get_dynamic_forms_public(
    db: Session = Depends(get_db),
    _client=Depends(get_current_portal_client),
):
    # Portal clients currently use the global baseline rules.
    return APIResponse.ok(data=reglas_o_sembrar(db, None))


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
