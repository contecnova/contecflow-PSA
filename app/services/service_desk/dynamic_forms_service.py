"""Formularios dinamicos de tickets: reglas, historial y opciones de contexto.

Auditoria 2026-08 (hallazgo 22). Todo esto vivia en
`endpoints/service_desk/dynamic_forms.py`: los tres ayudantes de `AppSetting`,
el historial de configuracion, y el selector de opciones de contexto que
consulta servicios, clientes y elementos de configuracion.

Los cuerpos se mueven **verbatim**. Los modelos Pydantic se quedan en el
endpoint, que es donde tienen sentido: son el contrato de entrada de las rutas.

Los ayudantes de `AppSetting` **si** filtraban por organizacion desde el
principio, asi que aqui no hay guarda nueva. La que si es nueva vino con el
selector: se le puso el filtro explicito por organizacion al descubrir que
`get_current_client` no publicaba el contexto de tenant en la sesion, con lo que
el portal recibia los clientes y los elementos de configuracion de **todas** las
organizaciones (ver `tests/test_portal_contexto_de_tenant.py`).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.client_portal import ClientUser
from app.models.clients import Client
from app.models.service_desk import ConfigurationItem, ServiceItem
from app.models.settings import AppSetting
from app.models.user import User


_RULES_KEY = "sd.dynamic_forms.rules"
_HISTORY_KEY = "sd.dynamic_forms.history"
_MAX_HISTORY = 30


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

    # La organizacion del sujeto, sea un usuario interno o del portal. Las tres
    # consultas de abajo se acotan con ella de forma EXPLICITA.
    #
    # Auditoria 2026-08: no lo estaban, y dependian del filtro implicito de
    # `TenantSession`. Este selector es alcanzable desde el portal, y
    # `get_current_client` no publicaba el contexto de tenant en la sesion, asi
    # que en ese camino no habia filtro de ninguna clase: un usuario del portal
    # recibia los clientes y los elementos de configuracion de TODAS las
    # organizaciones. El contexto ya se publica (ver `client_portal.py`), y este
    # filtro es lo que hace que no dependa de ello.
    sujeto = portal_client if portal_client is not None else current_user
    org_id = getattr(sujeto, "organization_id", None)

    service_q = db.query(ServiceItem).filter(
        ServiceItem.is_active.is_(True),
        ServiceItem.organization_id == org_id,
    )
    if portal_client is not None:
        service_q = service_q.filter(ServiceItem.is_visible_to_clients.is_(True))
    if service_item_id:
        service_q = service_q.filter(ServiceItem.id == service_item_id)
    services = service_q.order_by(ServiceItem.name.asc()).limit(max(5, limit)).all()

    clients = []
    if portal_client is not None:
        if portal_client.client_org_id:
            c = (
                db.query(Client)
                .filter(
                    Client.id == portal_client.client_org_id,
                    Client.organization_id == org_id,
                )
                .first()
            )
            if c:
                clients = [c]
    else:
        client_q = db.query(Client).filter(Client.organization_id == org_id)
        if client_id:
            client_q = client_q.filter(Client.id == client_id)
        clients = client_q.order_by(Client.name.asc()).limit(max(5, limit)).all()

    ci_q = db.query(ConfigurationItem).filter(
        ConfigurationItem.organization_id == org_id)
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
