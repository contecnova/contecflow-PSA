"""
Jira SM Sync Service — bidirectional synchronisation between Contecflow tickets and Jira issues.

Responsibilities:
  - Push: ticket create/update/comment → Jira REST API
  - Pull: Jira webhook events or polled diff → update local tickets
  - Conflict resolution: last-write-wins with manual override flag
  - Audit: every event written to JiraSyncLog

Auditoria 2026-11 (#34): el cliente HTTP, los mapas de estado/prioridad y el
token descifrado son los de `services/jira_service.py` (la unica capa de Jira);
aqui queda solo lo propio del ticket (cuerpo de la incidencia, registro, enlaces).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.models.jira_integration import (
    JiraConfig,
    JiraFieldMap,
    JiraSyncDirection,
    JiraSyncEventType,
    JiraSyncLog,
    JiraSyncMap,
    JiraSyncStatus,
)
from app.models.service_desk import Ticket, TicketComment, TicketPriority, TicketStatus
from app.core.metrics import track_external_call
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)

# ── Mapas y cliente: los de `jira_service` ────────────────────────────────────

from app.services import jira_service as _jira  # noqa: E402

_DEFAULT_PRIORITY_MAP = _jira.TICKET_A_JIRA_PRIORIDAD
_DEFAULT_STATUS_MAP = _jira.TICKET_A_JIRA_ESTADO
_JIRA_TO_TICKET_STATUS = _jira.JIRA_A_TICKET_ESTADO
jira_token_en_claro = _jira.token_en_claro


def jira_base_url_segura(config) -> str:
    """La URL de Jira validada contra SSRF (esquema, hosts locales y redes privadas)."""
    from app.core.outbound_url import validate_outbound_url

    return validate_outbound_url((config.jira_base_url or "").rstrip("/"), field="jira_base_url")


def _jira_client(config: JiraConfig, db=None) -> httpx.Client:
    """El cliente de `jira_service` con las credenciales de la configuracion."""
    from app.services.settings_service import outbound_http_timeout

    return _jira.cliente_de_configuracion(config, timeout=outbound_http_timeout(db, default=15.0))


# ── Helpers ────────────────────────────────────────────────────────────────────


def _resolve_priority(config: JiraConfig, ticket_priority: str) -> str:
    pmap = json.loads(config.priority_map_json) if config.priority_map_json else {}
    merged = {**_DEFAULT_PRIORITY_MAP, **pmap}
    return merged.get(ticket_priority, "Medium")


def _resolve_status_to_jira(config: JiraConfig, ticket_status: str) -> str:
    smap = json.loads(config.status_map_json) if config.status_map_json else {}
    merged = {**_DEFAULT_STATUS_MAP, **smap}
    return merged.get(ticket_status, "Open")


def _resolve_issue_type(config: JiraConfig, ticket_type: str) -> str:
    mapping = {
        "incident": config.jira_issue_type_incident,
        "service_request": config.jira_issue_type_service_request,
        "change": config.jira_issue_type_change,
        "problem": config.jira_issue_type_problem,
    }
    return mapping.get(ticket_type, "Incident")


def _build_issue_body(config: JiraConfig, ticket: Ticket, field_maps: list[JiraFieldMap]) -> dict:
    fields: dict = {
        "project": {"key": config.jira_project_key},
        "summary": f"[CF-{ticket.number}] {ticket.title}",
        "description": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": ticket.description or ""}],
                }
            ],
        },
        "issuetype": {"name": _resolve_issue_type(config, ticket.ticket_type.value)},
        "priority": {"name": _resolve_priority(config, ticket.priority.value)},
    }
    # Apply custom field maps
    for fm in field_maps:
        if not fm.is_active:
            continue
        val = getattr(ticket, fm.contecflow_field, None)
        if val is not None:
            fields[fm.jira_field_id] = str(val)
    return {"fields": fields}


def _write_log(
    db: Session,
    config_id: str,
    ticket_id: Optional[str],
    jira_key: Optional[str],
    event_type: JiraSyncEventType,
    direction: JiraSyncDirection,
    payload: Optional[dict],
    response: Optional[dict],
    success: bool,
    error: Optional[str] = None,
) -> None:
    log = JiraSyncLog(
        config_id=config_id,
        ticket_id=ticket_id,
        jira_issue_key=jira_key,
        event_type=event_type,
        direction=direction,
        payload_json=json.dumps(payload) if payload else None,
        response_json=json.dumps(response) if response else None,
        success=success,
        error_message=error,
    )
    db.add(log)
    # No commit here — caller handles transaction


# ── Push: Contecflow → Jira ────────────────────────────────────────────────────


def push_ticket_to_jira(db: Session, config: JiraConfig, ticket: Ticket) -> JiraSyncMap:
    """
    Create or update a Jira issue from a Contecflow ticket.
    Returns the JiraSyncMap entry (created or updated).
    """
    field_maps: list[JiraFieldMap] = (
        db.query(JiraFieldMap)
        .filter(JiraFieldMap.config_id == config.id, JiraFieldMap.is_active == True)
        .all()
    )

    existing_map: Optional[JiraSyncMap] = (
        db.query(JiraSyncMap)
        .filter(JiraSyncMap.config_id == config.id, JiraSyncMap.ticket_id == ticket.id)
        .first()
    )

    body = _build_issue_body(config, ticket, field_maps)

    try:
        with _jira_client(config, db=db) as client, track_external_call("jira"):
            if existing_map and existing_map.jira_issue_key:
                # UPDATE existing issue
                resp = client.put(
                    f"/rest/api/3/issue/{existing_map.jira_issue_key}",
                    content=json.dumps(body),
                )
                resp.raise_for_status()
                response_data = resp.json() if resp.content else {}
                jira_key = existing_map.jira_issue_key
                event = JiraSyncEventType.updated
            else:
                # CREATE new issue
                resp = client.post("/rest/api/3/issue", content=json.dumps(body))
                resp.raise_for_status()
                response_data = resp.json()
                jira_key = response_data.get("key", "")
                event = JiraSyncEventType.created

                existing_map = JiraSyncMap(
                    config_id=config.id,
                    ticket_id=ticket.id,
                    jira_issue_key=jira_key,
                    jira_issue_id=response_data.get("id"),
                )
                db.add(existing_map)

        existing_map.sync_status = JiraSyncStatus.synced
        existing_map.last_synced_at = datetime.now(timezone.utc)
        existing_map.last_ticket_updated_at = ticket.updated_at or ticket.created_at
        existing_map.sync_error = None

        _write_log(
            db, config.id, ticket.id, jira_key, event,
            JiraSyncDirection.contecflow_to_jira, body, response_data, True,
        )
        db.flush()
        return existing_map

    except httpx.HTTPStatusError as exc:
        # Sin el cuerpo de la respuesta remota (auditoria 2026-11 #25).
        error_msg = f"HTTP {exc.response.status_code}"
        logger.error("Jira push failed for ticket %s: %s", ticket.number, error_msg)
        if existing_map:
            existing_map.sync_status = JiraSyncStatus.error
            existing_map.sync_error = error_msg
        _write_log(
            db, config.id, ticket.id, None, JiraSyncEventType.error,
            JiraSyncDirection.contecflow_to_jira, body, None, False, error_msg,
        )
        db.flush()
        raise
    except Exception as exc:
        error_msg = str(exc)
        logger.exception("Unexpected Jira push error for ticket %s", ticket.number)
        _write_log(
            db, config.id, ticket.id, None, JiraSyncEventType.error,
            JiraSyncDirection.contecflow_to_jira, body, None, False, error_msg,
        )
        db.flush()
        raise


def empujar_ticket_confirmado(db: Session, config: JiraConfig, ticket: Ticket) -> JiraSyncMap:
    """Empuje manual: `push_ticket_to_jira` y confirma. Cualquier fallo deshace y es un 502."""
    try:
        sync_map = push_ticket_to_jira(db, config, ticket)
        db.commit()
        return sync_map
    except Exception as exc:
        db.rollback()
        raise ErrorDeDominio(502, f"Jira push failed: {exc}") from exc


def push_comment_to_jira(
    db: Session, config: JiraConfig, sync_map: JiraSyncMap, comment: TicketComment
) -> None:
    """Sync a public comment from Contecflow to the linked Jira issue."""
    if not config.sync_comments:
        return

    body = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": f"[Contecflow] {comment.body}"}
                    ],
                }
            ],
        }
    }

    try:
        with _jira_client(config, db=db) as client, track_external_call("jira"):
            resp = client.post(
                f"/rest/api/3/issue/{sync_map.jira_issue_key}/comment",
                content=json.dumps(body),
            )
            resp.raise_for_status()
        _write_log(
            db, config.id, comment.ticket_id, sync_map.jira_issue_key,
            JiraSyncEventType.comment_synced, JiraSyncDirection.contecflow_to_jira,
            {"comment_id": comment.id}, None, True,
        )
    except Exception as exc:
        _write_log(
            db, config.id, comment.ticket_id, sync_map.jira_issue_key,
            JiraSyncEventType.error, JiraSyncDirection.contecflow_to_jira,
            {"comment_id": comment.id}, None, False, str(exc),
        )
        logger.warning("Failed to push comment to Jira: %s", exc)


# ── Pull: Jira → Contecflow ────────────────────────────────────────────────────


def pull_jira_issue(
    db: Session, config: JiraConfig, jira_issue_key: str
) -> Optional[dict]:
    """Fetch a single Jira issue and return its fields dict."""
    try:
        with _jira_client(config, db=db) as client, track_external_call("jira"):
            resp = client.get(f"/rest/api/3/issue/{jira_issue_key}")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("Failed to pull Jira issue %s: %s", jira_issue_key, exc)
        return None


def apply_jira_update_to_ticket(
    db: Session,
    config: JiraConfig,
    sync_map: JiraSyncMap,
    jira_fields: dict,
) -> None:
    """
    Apply changes from a Jira issue onto the linked Contecflow ticket.
    Only updates fields allowed by the config sync flags.
    """
    ticket: Optional[Ticket] = db.query(Ticket).filter(
        Ticket.id == sync_map.ticket_id
    ).first()
    if not ticket:
        logger.warning("Ticket %s not found for Jira sync map %s", sync_map.ticket_id, sync_map.id)
        return

    changed = False

    if config.sync_status_changes:
        jira_status = (jira_fields.get("status", {}).get("name") or "").lower()
        mapped = _JIRA_TO_TICKET_STATUS.get(jira_status)
        if mapped and mapped != ticket.status.value:
            ticket.status = TicketStatus(mapped)
            changed = True

    if config.sync_priority_changes:
        jira_priority = (jira_fields.get("priority", {}).get("name") or "").lower()
        reverse_map = {v.lower(): k for k, v in _DEFAULT_PRIORITY_MAP.items()}
        if config.priority_map_json:
            custom = json.loads(config.priority_map_json)
            reverse_map.update({v.lower(): k for k, v in custom.items()})
        mapped_p = reverse_map.get(jira_priority)
        if mapped_p and mapped_p != ticket.priority.value:
            from app.services.service_desk.ticket_update_service import cambiar_prioridad
            cambiar_prioridad(db, ticket, TicketPriority(mapped_p))
            changed = True

    if changed:
        sync_map.last_synced_at = datetime.now(timezone.utc)
        sync_map.last_jira_updated_at = datetime.now(timezone.utc)
        sync_map.sync_status = JiraSyncStatus.synced
        _write_log(
            db, config.id, ticket.id, sync_map.jira_issue_key,
            JiraSyncEventType.updated, JiraSyncDirection.jira_to_contecflow,
            jira_fields, None, True,
        )
        db.flush()


# ── Polling loop (called by Celery beat) ──────────────────────────────────────


def run_incremental_sync(db: Session, config_id: str) -> dict:
    """
    Poll all active sync maps for a config and reconcile divergent state.
    Returns summary: {"synced": N, "errors": N, "skipped": N}
    """
    config: Optional[JiraConfig] = db.query(JiraConfig).filter(
        JiraConfig.id == config_id, JiraConfig.is_active == True
    ).first()
    if not config:
        return {"synced": 0, "errors": 0, "skipped": 0}

    maps: list[JiraSyncMap] = (
        db.query(JiraSyncMap)
        .filter(JiraSyncMap.config_id == config_id)
        .all()
    )

    stats = {"synced": 0, "errors": 0, "skipped": 0}

    for sm in maps:
        try:
            jira_data = pull_jira_issue(db, config, sm.jira_issue_key)
            if not jira_data:
                stats["skipped"] += 1
                continue

            jira_fields = jira_data.get("fields", {})
            jira_updated_str = jira_data.get("fields", {}).get("updated")
            if jira_updated_str:
                from dateutil import parser as dtparser
                jira_updated = dtparser.parse(jira_updated_str)
                if sm.last_jira_updated_at and jira_updated <= sm.last_jira_updated_at:
                    stats["skipped"] += 1
                    continue

            if config.sync_direction in (
                JiraSyncDirection.bidirectional,
                JiraSyncDirection.jira_to_contecflow,
            ):
                apply_jira_update_to_ticket(db, config, sm, jira_fields)

            stats["synced"] += 1
        except Exception as exc:
            logger.exception("Sync error for map %s: %s", sm.id, exc)
            sm.sync_status = JiraSyncStatus.error
            sm.sync_error = str(exc)[:500]
            stats["errors"] += 1

    db.commit()
    return stats


# ── Consultas y guardas, movidas del endpoint ────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 22). Las consultas de
# `endpoints/jira_integration.py` estaban ahi, y al moverlas aparecio la misma
# asimetria de siempre dentro del propio fichero: `patch`, `delete`, `test` y
# `sync-log` usaban `org_scoped_or_404`, y en cambio:
#
#   · `push_ticket` buscaba el ticket **y la configuracion de Jira** por id a
#     secas. Una `JiraConfig` lleva las credenciales de un cliente: usar la de
#     otro es empujar tickets con sus credenciales.
#   · `run_manual_sync` pasaba el `config_id` a una tarea de fondo sin
#     comprobar nada, asi que un administrador podia disparar la sincronizacion
#     de la configuracion de otro cliente.
#   · el listado y su `count()` no acotaban: dependian del filtro implicito, y
#     el `count()` sin acotar habria dado un total de otras organizaciones si el
#     filtro no actuara.


from app.models.jira_integration import JiraConfig as _JiraConfig  # noqa: E402
from app.models.jira_integration import JiraSyncLog as _JiraSyncLog  # noqa: E402
from app.models.service_desk import Ticket as _Ticket  # noqa: E402


def _org_de(user) -> "str | None":
    return getattr(user, "organization_id", None)


def listar_configuraciones(db: Session, user, *, page: int, page_size: int):
    """Las configuraciones de Jira de la organizacion, y su total.

    El total se cuenta con el MISMO filtro que la pagina: un total sin acotar
    diria «hay 12» y devolveria 3.
    """
    q = db.query(_JiraConfig).filter(
        _JiraConfig.organization_id == _org_de(user)
    )
    total = q.count()
    filas = (
        q.order_by(_JiraConfig.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return filas, total


def configuracion_propia(db: Session, user, config_id: str) -> _JiraConfig:
    """La configuracion, si es de la organizacion del usuario. 404 si no."""
    fila = (
        db.query(_JiraConfig)
        .filter(
            _JiraConfig.id == config_id,
            _JiraConfig.organization_id == _org_de(user),
        )
        .first()
    )
    if not fila:
        raise ErrorDeDominio(404, "Jira config not found")
    return fila


def configuracion_activa_propia(db: Session, user, config_id: str) -> _JiraConfig:
    """La configuracion activa de la organizacion. 404 si no existe o esta parada.

    Se usa antes de empujar un ticket: la configuracion lleva credenciales, y
    empujar con las de otro cliente es lo que esta guarda impide.
    """
    fila = (
        db.query(_JiraConfig)
        .filter(
            _JiraConfig.id == config_id,
            _JiraConfig.organization_id == _org_de(user),
            _JiraConfig.is_active == True,  # noqa: E712
        )
        .first()
    )
    if not fila:
        raise ErrorDeDominio(404, "Active Jira config not found")
    return fila


def ticket_propio(db: Session, user, ticket_id: str) -> _Ticket:
    """El ticket, si es de la organizacion del usuario. 404 si no."""
    fila = (
        db.query(_Ticket)
        .filter(
            _Ticket.id == ticket_id,
            _Ticket.organization_id == _org_de(user),
        )
        .first()
    )
    if not fila:
        raise ErrorDeDominio(404, "Ticket not found")
    return fila


def registro_de_sincronizacion(db: Session, config: _JiraConfig, *,
                               page: int, page_size: int):
    """El log de una configuracion ya comprobada, y su total.

    No lleva filtro de organizacion y es correcto: se busca por `config_id` de
    una configuracion que ya se verifico que es del usuario, asi que el ambito
    llega por la clave padre.
    """
    q = (
        db.query(_JiraSyncLog)
        .filter(_JiraSyncLog.config_id == config.id)
        .order_by(_JiraSyncLog.occurred_at.desc())
    )
    total = q.count()
    filas = q.offset((page - 1) * page_size).limit(page_size).all()
    return filas, total


def crear_configuracion(db: Session, user, datos: dict) -> _JiraConfig:
    """Guarda una configuracion de Jira nueva para la organizacion del usuario."""
    from app.core.encryption import encrypt_value
    from app.core.outbound_url import validate_outbound_url

    datos = dict(datos)
    para_tareas = bool(datos.pop("usar_para_tareas", False))
    validate_outbound_url(datos.get("jira_base_url") or "", field="jira_base_url")
    if datos.get("jira_api_token_enc"):
        datos["jira_api_token_enc"] = encrypt_value(datos["jira_api_token_enc"])
    fila = _JiraConfig(
        created_by_user_id=user.id,
        organization_id=_org_de(user),
        **datos,
    )
    db.add(fila)
    if para_tareas:
        db.flush()
        _jira.marcar_como_conexion_de_tareas(db, fila)
    db.commit()
    db.refresh(fila)
    return fila


def borrar_configuracion(db: Session, user, config_id: str) -> None:
    fila = configuracion_propia(db, user, config_id)
    db.delete(fila)
    db.commit()


def aplicar_cambios_de_configuracion(db: Session, config: _JiraConfig, cambios: dict) -> _JiraConfig:
    """Aplica el parche a una configuracion ya comprobada.

    Tres campos no se asignan por nombre: el token va a la columna cifrada y los
    dos mapas se serializan. El resto es asignacion directa.
    """
    import json as _json

    from app.core.asignacion import es_asignable
    from app.core.encryption import encrypt_value
    from app.core.outbound_url import validate_outbound_url

    for clave, valor in cambios.items():
        if clave == "jira_api_token":
            config.jira_api_token_enc = encrypt_value(valor) if valor else valor
        elif clave == "status_map":
            config.status_map_json = _json.dumps(valor)
        elif clave == "priority_map":
            config.priority_map_json = _json.dumps(valor)
        elif clave == "usar_para_tareas":
            if valor:
                _jira.marcar_como_conexion_de_tareas(db, config)
            else:
                config.usar_para_tareas = False
        elif es_asignable(config, clave, ("created_by_user_id", "jira_api_token_enc")):
            if clave == "jira_base_url":
                validate_outbound_url(valor or "", field="jira_base_url")
            setattr(config, clave, valor)
    db.commit()
    db.refresh(config)
    return config


def procesar_webhook(db: Session, issue: dict, issue_key: str, org_id: Optional[str] = None) -> dict:
    """Aplica un webhook de Jira a los tickets enlazados con esa incidencia.

    Auditoria 2026-11 (#14): se buscaban los enlaces por clave en TODAS las
    organizaciones, y la clave (`SUP-12`) se repite entre los Jira de distintos
    clientes. Ahora solo los enlaces de configuraciones de `org_id`, la
    organizacion cuyo secreto autentico el webhook. Sin organizacion, nada.
    """
    from app.models.jira_integration import JiraSyncDirection, JiraSyncMap

    if not org_id:
        return {"ok": True, "skipped": "no organization"}
    enlaces = (
        db.query(JiraSyncMap)
        .join(_JiraConfig, _JiraConfig.id == JiraSyncMap.config_id)
        .filter(JiraSyncMap.jira_issue_key == issue_key,
                _JiraConfig.organization_id == org_id)
        .all()
    )
    if not enlaces:
        return {"ok": True, "skipped": "no mapping found"}

    for enlace in enlaces:
        config = (
            db.query(_JiraConfig)
            .filter(
                _JiraConfig.id == enlace.config_id,
                _JiraConfig.organization_id == org_id,
                _JiraConfig.is_active == True,  # noqa: E712
            )
            .first()
        )
        if not config:
            continue
        if config.sync_direction not in (
            JiraSyncDirection.bidirectional,
            JiraSyncDirection.jira_to_contecflow,
        ):
            continue
        apply_jira_update_to_ticket(db, config, enlace, issue.get("fields", {}))

    db.commit()
    return {"ok": True, "processed": len(enlaces)}
