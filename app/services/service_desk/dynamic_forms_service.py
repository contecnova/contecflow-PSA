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
import logging

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


def _get_json_de_ajuste(db: Session, key: str, org_id: Optional[str], fallback):
    row = _get_setting(db, key, org_id)
    if not row or not row.value:
        return fallback
    try:
        return json.loads(row.value)
    except Exception:
        logging.getLogger(__name__).debug("_get_json: excepcion ignorada", exc_info=True)
        return fallback


def _set_json_de_ajuste(db: Session, key: str, org_id: Optional[str], value: dict | list, description: str) -> None:
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


# Migracion 200: las reglas y su historial de cada empresa viven en
# `sd_dynamic_form_rules` / `sd_dynamic_form_rule_history` (antes, blobs JSON
# de `AppSetting`). Las reglas globales del portal (sin empresa) siguen en
# `AppSetting`: no son de nadie y la tabla exige empresa. `_get_json`/`_set_json`
# conservan su firma para el endpoint.

def _fila_de_reglas(db: Session, org_id: str):
    from app.models.service_desk import DynamicFormRule
    return db.query(DynamicFormRule).filter(DynamicFormRule.organization_id == org_id).first()


def _cargar(texto: Optional[str], fallback):
    try:
        return json.loads(texto) if texto else fallback
    except Exception:
        logging.getLogger(__name__).debug("dynamic_forms: JSON ilegible", exc_info=True)
        return fallback


def _get_json(db: Session, key: str, org_id: Optional[str], fallback):
    if not org_id:
        return _get_json_de_ajuste(db, key, org_id, fallback)
    from app.models.service_desk import DynamicFormRuleHistory
    fila = _fila_de_reglas(db, org_id)
    if key == _RULES_KEY:
        return _cargar(fila.regla_json, fallback) if fila else fallback
    if key == _HISTORY_KEY:
        if fila is None:
            return fallback
        filas = (db.query(DynamicFormRuleHistory).filter(DynamicFormRuleHistory.rule_id == fila.id)
                 .order_by(DynamicFormRuleHistory.created_at.desc()).limit(_MAX_HISTORY).all())
        return [{"snapshot_id": h.id, "created_at": h.created_at.isoformat() if h.created_at else None,
                 "created_by": h.created_by, "reason": h.reason, "rules": _cargar(h.regla_json, {})}
                for h in filas]
    return _get_json_de_ajuste(db, key, org_id, fallback)


def _set_json(db: Session, key: str, org_id: Optional[str], value: dict | list, description: str) -> None:
    if not org_id or key not in (_RULES_KEY, _HISTORY_KEY):
        _set_json_de_ajuste(db, key, org_id, value, description)
        return
    from app.models.service_desk import DynamicFormRule
    fila = _fila_de_reglas(db, org_id)
    if key == _RULES_KEY:
        texto = json.dumps(value, ensure_ascii=False)
        quien = value.get("updated_by") if isinstance(value, dict) else None
        version = int(value.get("version", 1)) if isinstance(value, dict) else 1
        if fila is None:
            db.add(DynamicFormRule(organization_id=org_id, regla_json=texto, version=version, updated_by=quien))
        else:
            fila.regla_json, fila.version, fila.updated_by = texto, version, quien
        return
    # El historial se escribe una version cada vez (`_append_history`).
    from app.core.codigos_de_error import ErrorConCodigo
    raise ErrorConCodigo("interno_historial_formularios_dinamicos",
                         detail="el historial de formularios dinamicos se escribe con _append_history")


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


def reglas_o_sembrar(db: Session, org_id: Optional[str]) -> dict:
    """Las reglas de la organizacion (`None`: las globales del portal).

    Si aun no hay, devuelve las de por defecto. Auditoria 2026-11-22 (4.4):
    antes las sembraba y confirmaba dentro del GET (escritura y commit en una
    lectura); ahora se guardan la primera vez que alguien las cambia
    (`_save_rules_with_history` parte de las mismas por defecto).
    """
    rules = _get_json(db, _RULES_KEY, org_id, fallback=None)
    if not isinstance(rules, dict):
        rules = _default_rules()
    return rules


def _append_history(db: Session, org_id: Optional[str], snapshot: dict) -> None:
    if not org_id:
        history = _get_json_de_ajuste(db, _HISTORY_KEY, org_id, fallback=[])
        if not isinstance(history, list):
            history = []
        history.insert(0, snapshot)
        _set_json_de_ajuste(db, _HISTORY_KEY, org_id, history[:_MAX_HISTORY],
                            "Service Desk dynamic forms configuration history")
        return
    from app.models.service_desk import DynamicFormRule, DynamicFormRuleHistory
    fila = _fila_de_reglas(db, org_id)
    if fila is None:
        # Primera vez: la version anterior son las de por defecto; se crea la fila.
        fila = DynamicFormRule(organization_id=org_id, regla_json=json.dumps(snapshot.get("rules") or {},
                                                                              ensure_ascii=False))
        db.add(fila)
        db.flush()
    db.add(DynamicFormRuleHistory(
        id=snapshot.get("snapshot_id") or str(uuid4()), organization_id=org_id, rule_id=fila.id,
        regla_json=json.dumps(snapshot.get("rules") or {}, ensure_ascii=False),
        reason=(snapshot.get("reason") or None) and str(snapshot.get("reason"))[:200],
        created_by=snapshot.get("created_by"), created_at=datetime.now(timezone.utc)))
    db.flush()
    # Se guardan las ultimas `_MAX_HISTORY` versiones (como antes).
    sobran = (db.query(DynamicFormRuleHistory.id).filter(DynamicFormRuleHistory.rule_id == fila.id)
              .order_by(DynamicFormRuleHistory.created_at.desc()).offset(_MAX_HISTORY).all())
    if sobran:
        db.query(DynamicFormRuleHistory).filter(DynamicFormRuleHistory.id.in_([s[0] for s in sobran]))             .delete(synchronize_session=False)


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


#: Las tres fuentes de contexto que un campo puede tomar de otra entidad.
#: Auditoría 2026-09 (hallazgo 18): estaban escritas **tres veces cada una**
#: —una por prefijo de regla de texto, otra por clave de regla de diccionario y
#: otra por heurística de nombre de columna—, en tres cascadas paralelas de
#: `elif`. Como conjunto, las tres formas de reconocerlas comparten la lista.
_FUENTES_DE_CONTEXTO = ("ci", "service", "client")


def _regla_de_texto(clean: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Una regla `fuente.atributo`, como `ci.hostname`. Devuelve (tipo, fuente, atributo)."""
    for fuente in _FUENTES_DE_CONTEXTO:
        if clean.startswith(f"{fuente}."):
            return f"context_{fuente}", fuente, clean.split(".", 1)[1]
    return None, None, None


def _regla_por_nombre_de_columna(col: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Adivina la fuente por el nombre de la columna, para el alta sin fricción.

    Reconoce `ci_algo` y los nombres sueltos (`ci`, `ci_name`, ...). El atributo
    es lo que queda tras el prefijo, y `name` cuando no queda nada: `ci` a secas
    significa «el nombre del CI».
    """
    for fuente in _FUENTES_DE_CONTEXTO:
        sueltos = {fuente, f"{fuente}_name"}
        if fuente == "ci":
            sueltos |= {"configuration_item", "configuration_item_code"}
        if col.startswith(f"{fuente}_") or col in sueltos:
            return f"context_{fuente}", fuente, col.replace(f"{fuente}_", "") or "name"
    return None, None, None


def _normalize_mapping_rule(
    rule: str | dict | None, fallback_col: str,
) -> tuple[str, str, Optional[str], Optional[str]]:
    """Devuelve `(field_id, field_type, data_source, data_attribute)`.

    La regla puede venir como texto (`"ci.hostname"`), como diccionario
    (`{"source": "ci", "attribute": "hostname"}`) o no venir: en ese último
    caso se adivina por el nombre de la columna.
    """
    col = fallback_col.strip().lower().replace(" ", "_")
    field_id = col
    tipo = fuente = atributo = None

    if isinstance(rule, str) and rule.strip():
        limpia = rule.strip()
        field_id = limpia.lower().replace(" ", "_")
        tipo, fuente, atributo = _regla_de_texto(limpia)
        if fuente == "ci":
            # El identificador de un campo de CI lleva guion bajo, no punto:
            # `ci.hostname` es el campo `ci_hostname` del formulario.
            field_id = limpia.replace(".", "_").lower()

    elif isinstance(rule, dict):
        explicito = str(rule.get("id") or "").strip()
        if explicito:
            field_id = explicito.lower().replace(" ", "_")
        declarada = str(rule.get("source") or "").strip().lower()
        if declarada in _FUENTES_DE_CONTEXTO:
            tipo, fuente = f"context_{declarada}", declarada
            atributo = str(rule.get("attribute") or "").strip().lower() or None

    if tipo is None:
        tipo, fuente, atributo = _regla_por_nombre_de_columna(col)

    return field_id, tipo or "text", fuente, atributo


def _valor_de_enum(valor) -> str:
    """El valor de un enum (auditoria 2026-11-22, 4.4: `str()` daba «CIType.server»)."""
    return str(getattr(valor, "value", valor) or "")


def _pick(obj: object, attr: str, default: str = "") -> str:
    value = getattr(obj, attr, None)
    return str(value or default)


def _servicios_visibles(db: Session, org_id, *, portal: bool,
                        service_item_id, limit: int):
    """Elementos de servicio activos de la organización.

    Desde el portal sólo los marcados como visibles para clientes: la lista de
    servicios internos no tiene por qué salir de casa.
    """
    q = db.query(ServiceItem).filter(
        ServiceItem.is_active.is_(True),
        ServiceItem.organization_id == org_id,
    )
    if portal:
        q = q.filter(ServiceItem.is_visible_to_clients.is_(True))
    if service_item_id:
        q = q.filter(ServiceItem.id == service_item_id)
    return q.order_by(ServiceItem.name.asc()).limit(max(5, limit)).all()


def _clientes_visibles(db: Session, org_id, *, portal_client, client_id, limit: int):
    """Clientes que el sujeto puede ver.

    Un usuario del portal ve **el suyo y sólo el suyo**: un selector que le
    ofreciera la lista de clientes de la organización sería una fuga por sí
    mismo.
    """
    if portal_client is not None:
        if not portal_client.client_org_id:
            return []
        propio = db.query(Client).filter(
            Client.id == portal_client.client_org_id,
            Client.organization_id == org_id,
        ).first()
        return [propio] if propio else []

    q = db.query(Client).filter(Client.organization_id == org_id)
    if client_id:
        q = q.filter(Client.id == client_id)
    return q.order_by(Client.name.asc()).limit(max(5, limit)).all()


def _cis_visibles(db: Session, org_id, *, portal_client, qn: str, limit: int):
    """Elementos de configuración visibles, acotados al portal si procede.

    Desde el portal se limitan a los CI de los proyectos del cliente; y si el
    cliente no tiene proyectos asignados, sólo a los que no cuelgan de ninguno.
    """
    q = db.query(ConfigurationItem).filter(ConfigurationItem.organization_id == org_id)

    if portal_client is not None:
        proyectos = portal_client.get_project_ids()
        if proyectos:
            q = q.filter(ConfigurationItem.project_id.in_(proyectos))
        elif portal_client.client_org_id:
            q = q.filter(ConfigurationItem.project_id.is_(None))

    if qn:
        q = q.filter(
            ConfigurationItem.name.ilike(f"%{qn}%")
            | ConfigurationItem.code.ilike(f"%{qn}%")
            | ConfigurationItem.environment.ilike(f"%{qn}%")
        )
    return q.order_by(ConfigurationItem.name.asc()).limit(max(5, limit)).all()


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
    """Las opciones del selector de contexto: clientes, servicios y CI.

    La organizacion del sujeto, sea un usuario interno o del portal, acota las
    tres consultas de forma EXPLICITA.

    Auditoria 2026-08: no lo estaban, y dependian del filtro implicito de
    `TenantSession`. Este selector es alcanzable desde el portal, y
    `get_current_client` no publicaba el contexto de tenant en la sesion, asi
    que en ese camino no habia filtro de ninguna clase: un usuario del portal
    recibia los clientes y los elementos de configuracion de TODAS las
    organizaciones. El contexto ya se publica (ver `client_portal.py`), y este
    filtro es lo que hace que no dependa de ello.
    """
    qn = (q or "").strip().lower()
    sujeto = portal_client if portal_client is not None else current_user
    org_id = getattr(sujeto, "organization_id", None)

    servicios = _servicios_visibles(
        db, org_id, portal=portal_client is not None,
        service_item_id=service_item_id, limit=limit,
    )
    clientes = _clientes_visibles(
        db, org_id, portal_client=portal_client, client_id=client_id, limit=limit,
    )
    cis = _cis_visibles(db, org_id, portal_client=portal_client, qn=qn, limit=limit)

    return {
        "clients": [
            {"id": c.id, "name": _pick(c, "name")}
            for c in clientes
            if (not qn) or (qn in _pick(c, "name").lower())
        ][:limit],
        "services": [
            {
                "id": s.id,
                "name": _pick(s, "name"),
                "ticket_type": _valor_de_enum(getattr(s, "ticket_type", None)),
            }
            for s in servicios
            if (not qn) or (qn in _pick(s, "name").lower())
        ][:limit],
        "cis": [
            {
                "id": ci.id,
                "code": _pick(ci, "code"),
                "name": _pick(ci, "name"),
                "ci_type": _valor_de_enum(getattr(ci, "ci_type", None)),
                "status": _valor_de_enum(getattr(ci, "status", None)),
                "environment": _pick(ci, "environment"),

                "project_id": getattr(ci, "project_id", None),
            }
            for ci in cis
        ][:limit],
    }
