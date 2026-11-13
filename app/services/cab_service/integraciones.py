"""Integraciones externas (git, calendario, contabilidad, Jira): alta, sincronizacion y datos traidos.

Parte de `app.services.cab_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from app.core.secret_utils import decrypt_config_secrets
from app.models.cab import CalendarEvent
from app.models.task import Task
from app.core.encryption import encrypt_value
from app.core.secret_utils import encrypt_config_secrets
from app.models.cab import IntegrationConfig
from app.models.cab import CalendarEvent as CE
from app.models.cab import CommitLink as CL
from app.models.sprints import Sprint
from app.services.integrations import get_jira_issue
from app.core.errores import ErrorDeDominio


# ─── WebhookTrigger serializer ────────────────────────────────────────────────

def desactivar_integracion(db, integration_id: str) -> dict:
    """Desactiva una integracion OAuth. Es el boton de borrar de la interfaz.

    Auditoria 2026-08 (hallazgo 37): `DELETE /oauth-integrations/{id}` **no
    existia** — habia `GET` y `POST`, asi que se podia configurar una
    integracion y no quitarla.

    **No borra la fila**: `IntegrationConfig` tiene `is_active`, que es la
    convencion de borrado logico de este repositorio, y la fila guarda el
    historial de sincronizacion (`last_sync_at`, `sync_errors`, `last_error`)
    que sirve para diagnosticar. Se desactiva y **se borran los tokens**, que es
    lo que de verdad hay que quitar: dejar un `access_token` de un tercero en
    una fila desactivada es guardar una credencial que ya no se usa.
    """

    fila = (
        db.query(IntegrationConfig)
        .filter(IntegrationConfig.id == integration_id)
        .first()
    )
    if not fila:
        raise ErrorDeDominio(404, "Integración no encontrada")

    fila.is_active = False
    fila.access_token = None
    fila.refresh_token = None
    fila.token_expires_at = None
    db.commit()
    return {"ok": True, "id": integration_id, "deactivated": True}


# ─── Integration sync helpers ─────────────────────────────────────────────────

# Revision 2026-11: `sync_git_commits`, `sync_calendar` y `sync_accounting`
# eran simulaciones: creaban enlaces a commits inventados
# («abc123def456», «developer@empresa.com») en las cinco primeras tareas,
# eventos de calendario que no se enviaban a ningun sitio y una cuenta de
# facturas que no se mandaban. `sync_jira` reescribia el titulo y nunca traia
# el estado. Ahora cada una llama al servicio de verdad, o dice que no puede.

def _config_de(config) -> dict:
    """La configuracion de la integracion, con sus secretos descifrados."""
    from app.core.encryption import decrypt_value
    cfg = decrypt_config_secrets(json.loads(config.config or "{}"))
    if not cfg.get("access_token") and config.access_token:
        cfg["access_token"] = decrypt_value(config.access_token) or config.access_token
    return cfg


def _espera(db: Session) -> float:
    from app.services.settings_service import outbound_http_timeout
    return outbound_http_timeout(db)


def sync_git_commits(db: Session, config, payload: dict):
    """GitHub: trae los pull requests del repositorio y los procesa como el webhook."""
    import httpx
    from app.services.git_service import handle_github_pr
    if config.integration_type != "github":
        return 0, ["GitLab se integra por webhook: Configuración → Git."]
    cfg = _config_de(config)
    repo, token = (cfg.get("repo") or "").strip(), cfg.get("access_token")
    if not repo or not token:
        return 0, ["Faltan el repositorio (owner/repo) o el token."]
    try:
        r = httpx.get(f"https://api.github.com/repos/{repo}/pulls",
                      params={"state": "all", "per_page": 50},
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                      timeout=_espera(db))
    except httpx.HTTPError as exc:
        return 0, [f"GitHub: {exc}"[:200]]
    if r.status_code != 200:
        return 0, [f"GitHub {r.status_code}: {r.text[:150]}"]
    synced = 0
    for pr in r.json():
        pr = dict(pr, merged=bool(pr.get("merged_at")))
        handle_github_pr(db, {"action": "closed" if pr.get("closed_at") else "opened",
                              "pull_request": pr, "repository": {"full_name": repo}})
        synced += 1
    db.flush()
    return synced, []


def sync_calendar(db: Session, config, payload: dict):
    """Google Calendar: publica los sprints con fechas como eventos de dia completo.

    Cada evento se recuerda por su id de Google: la siguiente vez se actualiza
    en vez de duplicarse.
    """
    import httpx
    if config.integration_type != "google_calendar":
        return 0, ["Outlook se integra con Microsoft 365: Configuración → Microsoft 365."]
    cfg = _config_de(config)
    calendario, token = (cfg.get("calendar_id") or "primary").strip(), cfg.get("access_token")
    if not token:
        return 0, ["Falta el token de acceso de Google."]
    base = f"https://www.googleapis.com/calendar/v3/calendars/{calendario}/events"
    cabeceras = {"Authorization": f"Bearer {token}"}
    sprints = db.query(Sprint).filter(Sprint.start_date != None, Sprint.end_date != None).all()
    ya = {e.sprint_id: e for e in db.query(CalendarEvent).filter(
        CalendarEvent.integration_id == config.id, CalendarEvent.sprint_id != None).all()}
    synced, errors = 0, []
    for sprint in sprints:
        cuerpo = {"summary": f"Sprint: {sprint.name}",
                  "start": {"date": sprint.start_date.isoformat()},
                  "end": {"date": (sprint.end_date + timedelta(days=1)).isoformat()}}
        previo = ya.get(sprint.id)
        try:
            if previo:
                r = httpx.put(f"{base}/{previo.external_id}", json=cuerpo, headers=cabeceras, timeout=_espera(db))
            else:
                r = httpx.post(base, json=cuerpo, headers=cabeceras, timeout=_espera(db))
        except httpx.HTTPError as exc:
            errors.append(f"Google: {exc}"[:200])
            continue
        if r.status_code not in (200, 201):
            errors.append(f"Google {r.status_code}: {r.text[:150]}")
            continue
        if previo is None:
            db.add(CalendarEvent(
                integration_id=config.id, external_id=r.json().get("id"),
                title=cuerpo["summary"], all_day=True, sprint_id=sprint.id, project_id=sprint.project_id,
                start_dt=datetime.combine(sprint.start_date, datetime.min.time()),
                end_dt=datetime.combine(sprint.end_date, datetime.min.time()),
                sync_direction="push",
            ))
        synced += 1
    db.flush()
    return synced, errors


def sync_accounting(db: Session, config, payload: dict):
    """Xero / QuickBooks: envia las facturas pendientes (lo mismo que Contabilidad)."""
    from app.services.accounting_hub_service import enviar_facturas_pendientes
    filas = enviar_facturas_pendientes(db, config.integration_type, _config_de(config))
    errores = [f"{f['invoice_number']}: {f.get('error')}"[:200] for f in filas if f["status"] == "error"]
    return sum(1 for f in filas if f["status"] == "synced"), errores


# Auditoria 2026-11 (#34): el mapa comun de `jira_service` (antes, una copia con cuatro estados).
from app.services.jira_service import JIRA_STATUS_MAP as _ESTADO_DESDE_JIRA  # noqa: E402


def sync_jira(db: Session, config, payload: dict):
    """Jira → Contecflow: el estado de cada incidencia enlazada pasa a su tarea."""
    cfg_dict = _config_de(config)
    synced, errors = 0, []
    for task in db.query(Task).filter(Task.jira_issue_key != None).limit(200).all():
        result = get_jira_issue(cfg_dict, task.jira_issue_key)
        if not result.get("ok"):
            errors.append(f"{task.jira_issue_key}: {str(result.get('error', ''))[:100]}")
            continue
        nombre = (result["data"].get("fields", {}).get("status", {}).get("name") or "").lower()
        nuevo = _ESTADO_DESDE_JIRA.get(nombre)
        if nuevo and str(getattr(task.status, "value", task.status)) != nuevo:
            task.status = nuevo
        synced += 1
    db.flush()
    return synced, errors[:5]


# ─── Integrations ─────────────────────────────────────────────────────────────

def list_integrations(db: Session) -> list:
    configs = db.query(IntegrationConfig).options(
        joinedload(IntegrationConfig.creator)
    ).all()
    return [{
        "id": c.id, "integration_type": c.integration_type,
        "name": c.name, "is_active": c.is_active,
        "last_sync_at": str(c.last_sync_at)[:16] if c.last_sync_at else None,
        "sync_errors": c.sync_errors or 0,
        "last_error": c.last_error,
        "config": decrypt_config_secrets(json.loads(c.config)) if c.config else {},
        "has_token": bool(c.access_token),
        "created_by": c.creator.full_name if c.creator else None,
    } for c in configs]


def create_integration(payload, current_user_id: str, db: Session) -> dict:
    existing = db.query(IntegrationConfig).filter(
        IntegrationConfig.integration_type == payload.integration_type
    ).first()
    if existing:
        existing.name = payload.name
        existing.access_token = encrypt_value(payload.access_token) if payload.access_token else None
        existing.refresh_token = encrypt_value(payload.refresh_token) if payload.refresh_token else None
        existing.config = json.dumps(encrypt_config_secrets(payload.config)) if payload.config else None
        existing.is_active = True
        db.commit()
        return {"ok": True, "id": existing.id, "updated": True}

    c = IntegrationConfig(
        integration_type=payload.integration_type,
        name=payload.name,
        access_token=encrypt_value(payload.access_token) if payload.access_token else None,
        refresh_token=encrypt_value(payload.refresh_token) if payload.refresh_token else None,
        config=json.dumps(encrypt_config_secrets(payload.config)) if payload.config else None,
        created_by=current_user_id,
    )
    db.add(c); db.commit()
    return {"ok": True, "id": c.id, "updated": False}


def run_integration_sync(integration_id: str, payload: dict, db: Session) -> dict:
    config = db.query(IntegrationConfig).filter(IntegrationConfig.id == integration_id).first()
    if not config:
        raise ValueError("Integración no encontrada")
    if not config.is_active:
        raise ValueError("Integración inactiva")

    synced = 0
    errors = []
    if config.integration_type in ["github", "gitlab"]:
        synced, errors = sync_git_commits(db, config, payload)
    elif config.integration_type in ["google_calendar", "outlook"]:
        synced, errors = sync_calendar(db, config, payload)
    elif config.integration_type in ["quickbooks", "xero"]:
        synced, errors = sync_accounting(db, config, payload)
    elif config.integration_type == "jira":
        synced, errors = sync_jira(db, config, payload)
    else:
        # Slack y Teams solo envian avisos: no hay nada que sincronizar.
        raise ValueError(f"La integración «{config.integration_type}» no tiene sincronización; usa «Probar».")

    config.last_sync_at = datetime.now(timezone.utc)
    config.sync_errors = len(errors)
    config.last_error = errors[0] if errors else None
    db.commit()
    if errors and not synced:
        # Antes respondia «ok» y la pantalla decia «Sincronización completada».
        raise ValueError(errors[0])
    return {"ok": True, "synced": synced, "errors": errors[:5]}


def get_calendar_events(user_id: str, from_date, to_date, db: Session) -> list:
    q = db.query(CE).options(joinedload(CE.project))
    q = q.filter(CE.user_id == user_id)
    if from_date:
        q = q.filter(CE.start_dt >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        q = q.filter(CE.start_dt <= datetime.combine(to_date, datetime.max.time()))
    events = q.order_by(CE.start_dt).limit(100).all()
    return [{
        "id": e.id, "title": e.title,
        "start_dt": str(e.start_dt)[:16], "end_dt": str(e.end_dt)[:16],
        "all_day": e.all_day, "description": e.description,
        "project_name": e.project.name if e.project else None,
        "sprint_id": e.sprint_id, "milestone_id": e.milestone_id,
    } for e in events]


def get_commit_links(integration_id: str, task_id: Optional[str], db: Session) -> list:
    q = db.query(CL).options(
        joinedload(CL.task).joinedload(Task.project)
    ).filter(CL.integration_id == integration_id)
    if task_id:
        q = q.filter(CL.task_id == task_id)
    links = q.order_by(CL.created_at_ext.desc()).limit(50).all()
    return [{
        "id": l.id, "link_type": l.link_type,
        "task_id": l.task_id,
        "task_code": l.task.code if l.task else None,
        "task_title": l.task.title if l.task else None,
        "project_code": l.task.project.code if l.task and l.task.project else None,
        "external_id": l.external_id,
        "title": l.title, "url": l.url, "author": l.author,
        "state": l.state,
        "synced_at": str(l.synced_at)[:16] if l.synced_at else None,
    } for l in links]
