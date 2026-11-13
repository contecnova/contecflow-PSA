"""
jira_service.py — la UNICA capa de servicio de Jira.

Auditoria 2026-11 (#34). Jira estaba implementado tres veces: `endpoints/jira.py`
(credenciales en `app_settings`), `endpoints/jira_integration.py` +
`service_desk/jira_sync_service.py` (tabla `sd_jira_configs`) y la tarea
periodica del worker, cada uno con su cliente HTTP, sus mapas de estado y
prioridad y su prueba de conexion. Ahora, aqui:

  * configuracion: `sd_jira_configs` (`JiraConfig`). La de las tareas de
    proyecto es la fila `usar_para_tareas` de la organizacion (migracion 159);
    las demas son las conexiones del service desk. En `app_settings` solo queda
    el secreto del webhook entrante, que es de la organizacion, no de una conexion.
  * cliente: `cliente_jira` / `llamar_a_jira` (URL validada contra SSRF,
    `cliente_httpx`, errores sin el cuerpo remoto).
  * mapas: `JIRA_STATUS_MAP`, `JIRA_PRIORITY_MAP` (Jira -> tarea),
    `TAREA_A_JIRA_PRIORIDAD`, y los del ticket (`TICKET_A_JIRA_*`, `JIRA_A_TICKET_ESTADO`).
  * prueba de conexion: `probar_conexion`.

Los endpoints (`/jira/*`, `/integrations/jira/*`, `/integrations-hub/jira/*`)
y `service_desk/jira_sync_service.py` delegan aqui.
"""
from __future__ import annotations

import datetime
import logging
from typing import Optional, List

from sqlalchemy.orm import Session

from app.models.jira_integration import JiraConfig
from app.models.settings import AppSetting
from app.models.task import Task
from app.core.encryption import encrypt_value, decrypt_value
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)

#: Secreto del webhook entrante de Jira, uno por organizacion (auditoria 2026-11 #14).
JIRA_WEBHOOK_SECRET_KEY = "jira_webhook_secret"  # noqa: S105

_SENSITIVE_SETTING_KEYS = {JIRA_WEBHOOK_SECRET_KEY}


# ── Inbound webhook authentication ──────────────────────────────────────────────

def verify_jira_webhook(body: bytes, token_header: Optional[str], signature_header: Optional[str],
                        secret: Optional[str] = None) -> bool:
    """Authenticate an inbound Jira webhook against ``secret``.

    Jira Cloud does not sign native webhooks, so we support either:
      * a shared secret in ``X-Atlassian-Webhook-Token`` (configure a Jira
        automation rule to send it), or
      * an HMAC-SHA256 of the raw body in ``X-Hub-Signature-256`` (``sha256=``
        prefixed), for setups that proxy/sign the payload.

    Constant-time comparison throughout. Returns False when the secret is empty
    (fail-closed).

    Auditoria 2026-11 (#14): el secreto era UNO global (`JIRA_WEBHOOK_SECRET`)
    que todas las organizaciones tenian que conocer para configurar su Jira, y
    el evento buscaba la tarea/ticket por clave sin organizacion: un cliente
    podia mover tareas de otro. Ahora el secreto es de cada organizacion
    (`organizacion_del_webhook`) y el global ya no autentica nada.
    """
    import hmac
    import hashlib

    if not secret:
        return False
    if token_header and hmac.compare_digest(secret.encode(), token_header.strip().encode()):
        return True
    if signature_header and signature_header.startswith("sha256="):
        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected.encode(), signature_header.strip().encode()):
            return True
    return False


def organizacion_del_webhook(db: Session, body: bytes, token_header: Optional[str],
                             signature_header: Optional[str], org_hint: Optional[str] = None) -> Optional[str]:
    """La organizacion cuyo secreto de webhook de Jira autentica la peticion, o None.

    `org_hint` (el `?org=` de la URL) solo acota la busqueda: lo que identifica
    a la organizacion es su secreto. Sin coincidencia, None (403 arriba).
    """
    from app.db.session import sin_filtro_de_tenant

    if not token_header and not signature_header:
        return None
    with sin_filtro_de_tenant(db):
        q = db.query(AppSetting).filter(
            AppSetting.key == JIRA_WEBHOOK_SECRET_KEY,
            AppSetting.organization_id.isnot(None),
        )
        if org_hint:
            q = q.filter(AppSetting.organization_id == org_hint)
        filas = q.all()
    for fila in filas:
        secreto = decrypt_value(fila.value) if fila.value else None
        if secreto and verify_jira_webhook(body, token_header, signature_header, secreto):
            # Una empresa desactivada no recibe webhooks (revision 2026-11b).
            from app.db.session import exigir_organizacion_activa
            exigir_organizacion_activa(db, fila.organization_id)
            return fila.organization_id
    return None


def generar_secreto_de_webhook(db: Session, org_id: str) -> str:
    """Crea (o rota) el secreto del webhook de Jira de la organizacion. Lo devuelve una vez."""
    import secrets as _secrets

    if not org_id:
        raise ErrorDeDominio(400, "El secreto del webhook de Jira es de una organización")
    secreto = _secrets.token_urlsafe(32)
    set_setting(db, JIRA_WEBHOOK_SECRET_KEY, secreto, org_id)
    db.commit()
    return secreto


def tiene_secreto_de_webhook(db: Session, org_id: Optional[str]) -> bool:
    if not org_id:
        return False
    return db.query(AppSetting.id).filter(
        AppSetting.key == JIRA_WEBHOOK_SECRET_KEY, AppSetting.organization_id == org_id,
    ).first() is not None

# ── Mapas Jira <-> Contecflow (un solo sitio) ──────────────────────────────────
#
# Auditoria 2026-11 (#34): la sincronizacion periodica tenia su copia
# (`To Do`/`In Progress`... en mayusculas exactas, con `Blocked`), el endpoint
# de empuje la suya de prioridades y el service desk las del ticket. Las claves
# de Jira van en minusculas: se busca con `estado_de_tarea`/`prioridad_de_tarea`.

#: Estado de Jira -> estado de tarea.
JIRA_STATUS_MAP = {
    "to do":       "todo",
    "open":        "todo",
    "backlog":     "backlog",
    "in progress": "in_progress",
    "in review":   "in_review",
    "blocked":     "blocked",
    "done":        "done",
    "closed":      "done",
    "resolved":    "done",
    "cancelled":   "cancelled",
    "won't fix":   "cancelled",
}

#: Prioridad de Jira -> prioridad de tarea.
JIRA_PRIORITY_MAP = {
    "blocker":  "critical",
    "critical": "critical",
    "highest":  "critical",
    "high":     "high",
    "medium":   "medium",
    "low":      "low",
    "lowest":   "low",
    "trivial":  "low",
}

#: Prioridad de tarea -> prioridad de Jira (al crear la incidencia).
TAREA_A_JIRA_PRIORIDAD = {
    "critical": "Highest", "high": "High", "medium": "Medium", "low": "Low", "none": "Medium",
}

#: Prioridad de ticket -> prioridad de Jira (la configuracion puede sobrescribirla).
TICKET_A_JIRA_PRIORIDAD: dict[str, str] = {
    "p1_critical": "Highest",
    "p2_high": "High",
    "p3_medium": "Medium",
    "p4_low": "Low",
}

#: Estado de ticket -> estado de Jira (la configuracion puede sobrescribirlo).
TICKET_A_JIRA_ESTADO: dict[str, str] = {
    "new": "Open",
    "assigned": "In Progress",
    "in_progress": "In Progress",
    "pending_client": "Waiting for customer",
    "pending_third": "Waiting for support",
    "resolved": "Resolved",
    "closed": "Closed",
    "cancelled": "Cancelled",
}

#: Estado de Jira -> estado de ticket.
JIRA_A_TICKET_ESTADO: dict[str, str] = {
    "open": "new",
    "in progress": "in_progress",
    "waiting for customer": "pending_client",
    "waiting for support": "pending_third",
    "resolved": "resolved",
    "closed": "closed",
    "done": "resolved",
}


def estado_de_tarea(nombre_en_jira: Optional[str], defecto: Optional[str] = None) -> Optional[str]:
    return JIRA_STATUS_MAP.get((nombre_en_jira or "").strip().lower(), defecto)


def prioridad_de_tarea(nombre_en_jira: Optional[str], defecto: Optional[str] = None) -> Optional[str]:
    return JIRA_PRIORITY_MAP.get((nombre_en_jira or "").strip().lower(), defecto)


# ── AppSetting helpers ─────────────────────────────────────────────────────────

def _en_claro(key: str, value: Optional[str]) -> Optional[str]:
    if value and key in _SENSITIVE_SETTING_KEYS:
        dec = decrypt_value(value)
        return dec if dec is not None else value
    return value


def get_setting(db: Session, key: str, org_id: Optional[str] = None) -> Optional[str]:
    """Return tenant-specific setting, falling back to global row.

    Auditoria 2026-11: la fila de la organizacion se devolvia sin descifrar (el
    token cifrado iba tal cual a Jira). El secreto del webhook no cae al global.
    """
    if org_id:
        row = db.query(AppSetting).filter(
            AppSetting.key == key, AppSetting.organization_id == org_id
        ).first()
        if row:
            return _en_claro(key, row.value)
    if key == JIRA_WEBHOOK_SECRET_KEY:
        return None
    row = db.query(AppSetting).filter(
        AppSetting.key == key, AppSetting.organization_id.is_(None)
    ).first()
    return _en_claro(key, row.value if row else None)


def set_setting(db: Session, key: str, value: str, org_id: Optional[str] = None) -> None:
    """Upsert a setting scoped to *org_id* (or global when None)."""
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if org_id:
        q = q.filter(AppSetting.organization_id == org_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    store_value = encrypt_value(value) if key in _SENSITIVE_SETTING_KEYS and value else value
    if row:
        row.value = store_value
    else:
        db.add(AppSetting(key=key, value=store_value, organization_id=org_id,
                          description=f"Jira integration: {key}"))
    db.flush()


# ── Configuracion (una fuente: `sd_jira_configs`) ─────────────────────────────

#: Nombre con el que se crea la conexion de las tareas desde `POST /jira/config`.
NOMBRE_DE_LA_CONEXION_DE_TAREAS = "Proyectos (tareas)"

_CONFIG_VACIA = {"jira_url": None, "jira_email": None, "jira_api_token": None, "jira_project_key": None}


def token_en_claro(config) -> str:
    """El token de la API de Jira de una `JiraConfig`, descifrado.

    Lo guardado antes de cifrarse (no descifra) se usa tal cual.
    """
    guardado = config.jira_api_token_enc or ""
    return decrypt_value(guardado) or guardado


def credenciales(config) -> dict:
    """La configuracion como la usa `llamar_a_jira`."""
    return {
        "jira_url":         (config.jira_base_url or "").rstrip("/") or None,
        "jira_email":       config.jira_email or None,
        "jira_api_token":   token_en_claro(config) or None,
        "jira_project_key": config.jira_project_key or None,
    }


def configuracion_de_tareas(db: Session, org_id: Optional[str]) -> Optional[JiraConfig]:
    """La conexion de Jira de las tareas de la organizacion (activa o no). Sin organizacion, ninguna.

    Auditoria 2026-11 (#34): antes eran cuatro `app_settings` que caian a la
    fila global si la organizacion no tenia la suya: una organizacion sin Jira
    propio usaba las credenciales globales. Ya no hay global.
    """
    if not org_id:
        return None
    return (
        db.query(JiraConfig)
        .filter(JiraConfig.organization_id == org_id, JiraConfig.usar_para_tareas.is_(True))
        .order_by(JiraConfig.created_at.asc())
        .first()
    )


def get_jira_config(db: Session, org_id: Optional[str] = None) -> dict:
    """La conexion de las tareas de `org_id` (claves `jira_*`); vacia si no hay o esta parada."""
    config = configuracion_de_tareas(db, org_id)
    if config is None or config.is_active is False:
        return dict(_CONFIG_VACIA)
    return credenciales(config)


def marcar_como_conexion_de_tareas(db: Session, config: JiraConfig) -> None:
    """Deja `config` como la unica conexion de tareas de su organizacion."""
    db.query(JiraConfig).filter(
        JiraConfig.organization_id == config.organization_id,
        JiraConfig.id != config.id,
        JiraConfig.usar_para_tareas.is_(True),
    ).update({JiraConfig.usar_para_tareas: False}, synchronize_session="fetch")
    config.usar_para_tareas = True


def save_jira_config(
    db: Session,
    org_id: Optional[str],
    jira_url: str,
    jira_email: str,
    jira_api_token: str,
    jira_project_key: str,
) -> JiraConfig:
    """Crea o actualiza la conexion de las tareas de la organizacion y confirma."""
    from app.core.outbound_url import validate_outbound_url

    # Auditoria 2026-11 (#25): la URL se usa para peticiones del servidor (SSRF).
    validate_outbound_url(jira_url or "", field="jira_url")
    if not org_id:
        raise ErrorDeDominio(400, "La configuración de Jira es de una organización")
    config = configuracion_de_tareas(db, org_id)
    if config is None:
        config = JiraConfig(name=NOMBRE_DE_LA_CONEXION_DE_TAREAS, organization_id=org_id,
                            usar_para_tareas=True)
        db.add(config)
    config.jira_base_url = (jira_url or "").rstrip("/")
    config.jira_email = jira_email
    config.jira_api_token_enc = encrypt_value(jira_api_token) if jira_api_token else ""
    config.jira_project_key = jira_project_key
    config.is_active = True
    db.commit()
    return config


# ── Task helpers ───────────────────────────────────────────────────────────────

def get_task_by_jira_key(db: Session, jira_key: str, org_id: Optional[str]) -> Optional[Task]:
    """La tarea de esa organizacion enlazada con la clave. Sin organizacion, ninguna.

    Auditoria 2026-11 (#14): se buscaba solo por clave, y `PROJ-1` existe en el
    Jira de muchos clientes.
    """
    if not org_id:
        return None
    return db.query(Task).filter(
        Task.jira_issue_key == jira_key, Task.organization_id == org_id,
    ).first()


def _extract_adf_text(node) -> list:
    """Best-effort plain-text extraction from Atlassian Document Format."""
    parts: list = []
    if isinstance(node, dict):
        if node.get("type") == "text":
            parts.append(node.get("text", ""))
        for child in node.get("content", []):
            parts.extend(_extract_adf_text(child))
    return parts


def sync_jira_issues(
    db: Session,
    issues: list,
    project_id: Optional[str],
    current_user_id: str,
    dry_run: bool,
    org_id: Optional[str] = None,
) -> dict:
    """
    Create or update NexusPM Tasks from a list of raw Jira issue dicts.
    Returns ``{"created": int, "updated": int, "skipped": int}``.

    Auditoria 2026-11 (#14): la tarea existente se busca en la organizacion de
    quien sincroniza, no en todas.
    """
    created = updated = skipped = 0
    now = datetime.datetime.now(datetime.timezone.utc)

    for iss in issues:
        f = iss.get("fields", {})
        jira_key     = iss["key"]
        jira_id      = iss["id"]
        title        = f.get("summary") or jira_key
        raw_status   = (f.get("status", {}).get("name") or "").lower()
        raw_priority = (f.get("priority", {}).get("name") or "").lower()
        nm_status    = JIRA_STATUS_MAP.get(raw_status, "todo")
        nm_priority  = JIRA_PRIORITY_MAP.get(raw_priority, "medium")
        due_date     = f.get("duedate")

        desc_adf  = f.get("description")
        desc_text = None
        if desc_adf and isinstance(desc_adf, dict):
            parts = _extract_adf_text(desc_adf)
            desc_text = " ".join(parts).strip() or None

        q = db.query(Task).filter(Task.jira_issue_key == jira_key)
        if org_id:
            q = q.filter(Task.organization_id == org_id)
        existing = q.first()

        if existing:
            if not dry_run:
                existing.status         = nm_status
                existing.priority       = nm_priority
                existing.jira_issue_id  = jira_id
                existing.jira_synced_at = now
                if due_date:
                    existing.due_date = due_date
            updated += 1
        else:
            if not dry_run:
                task = Task(
                    title=title,
                    description=desc_text,
                    status=nm_status,
                    priority=nm_priority,
                    due_date=due_date,
                    project_id=project_id,
                    jira_issue_key=jira_key,
                    jira_issue_id=jira_id,
                    jira_synced_at=now,
                    created_by=current_user_id,
                    organization_id=org_id,
                )
                db.add(task)
            created += 1

    if not dry_run:
        db.commit()

    return {"created": created, "updated": updated, "skipped": skipped}


def get_tasks_for_push(db: Session, project_id: str, statuses: List[str], org_id: Optional[str] = None) -> list:
    """Return tasks in a project without a Jira key, filtered by status."""
    q = db.query(Task).filter(
        Task.project_id == project_id,
        Task.status.in_(statuses),
        Task.jira_issue_key == None,
    )
    if org_id:
        q = q.filter(Task.organization_id == org_id)
    return q.all()


def commit_db(db: Session) -> None:
    """Commit the current session (used after bulk task mutations in the push loop)."""
    db.commit()


def update_task_from_webhook(
    db: Session,
    task: Task,
    nm_status: Optional[str],
    nm_priority: Optional[str],
    event: str,
) -> bool:
    """
    Apply status/priority changes from a Jira webhook event.
    Commits if anything changed.  Returns True when the task was updated.
    """
    changed = False
    if nm_status and task.status != nm_status:
        task.status = nm_status
        changed = True
    if nm_priority and task.priority != nm_priority:
        task.priority = nm_priority
        changed = True
    if event == "jira:issue_deleted":
        task.jira_issue_key = None
        task.jira_issue_id  = None
        changed = True
    if changed:
        task.jira_synced_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()
    return changed


def get_linked_tasks_query(db: Session, project_id: Optional[str], org_id: Optional[str] = None):
    """Return a query for tasks that have a Jira issue key, optionally scoped to a project."""
    q = db.query(Task).filter(Task.jira_issue_key != None)
    if org_id:
        q = q.filter(Task.organization_id == org_id)
    if project_id:
        q = q.filter(Task.project_id == project_id)
    return q


# ── HTTP helper ──────────────────────────────────────────────────────────────

def jira_headers(email: str, token: str) -> dict:
    import base64 as _b64
    creds = _b64.b64encode(f"{email}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def cliente_jira(jira_url: Optional[str], email: Optional[str], token: Optional[str], *,
                 timeout: float = 15, campo: str = "jira_url"):
    """El cliente HTTP de Jira: `httpx.Client` con `base_url` validada contra SSRF.

    Auditoria 2026-11 (#25, #34): el unico sitio que abre conexiones a Jira.
    `cliente_httpx` valida cada redireccion y la IP a la que se conecta.
    """
    from app.core.outbound_url import cliente_httpx, validate_outbound_url

    base = validate_outbound_url((jira_url or "").rstrip("/"), field=campo)
    return cliente_httpx(base_url=base, headers=jira_headers(email or "", token or ""), timeout=timeout)


def cliente_de_configuracion(config, timeout: float = 15):
    """`cliente_jira` con las credenciales de una `JiraConfig`."""
    return cliente_jira(config.jira_base_url, config.jira_email, token_en_claro(config),
                        timeout=timeout, campo="jira_base_url")


def llamar_a_jira_crudo(cfg: dict, method: str, path: str, *, json: Optional[dict] = None,
                         timeout: float = 15):
    """Peticion a la API de Jira de `cfg` (claves `jira_*`) por `cliente_jira`.

    Lanza los errores de httpx tal cual (el worker los quiere para reintentar);
    los endpoints usan `llamar_a_jira`.
    """
    with cliente_jira(cfg.get("jira_url"), cfg.get("jira_email"), cfg.get("jira_api_token"),
                      timeout=timeout) as cliente:
        resp = cliente.request(method, path, json=json)
        resp.raise_for_status()
        return resp.json() if resp.content else {}


def llamar_a_jira(cfg: dict, method: str, path: str, *, json: Optional[dict] = None,
                  timeout: float = 15) -> dict:
    """Como `llamar_a_jira_crudo`, con errores de dominio que no repiten la respuesta remota."""
    import httpx

    try:
        return llamar_a_jira_crudo(cfg, method, path, json=json, timeout=timeout)
    except httpx.HTTPStatusError as exc:
        logger.warning("Jira %s %s -> HTTP %s", method, path, exc.response.status_code)
        raise ErrorDeDominio(502, f"Jira devolvió HTTP {exc.response.status_code}") from exc
    except (httpx.RequestError, PermissionError) as exc:
        logger.warning("Jira %s %s: no se pudo conectar (%s)", method, path, type(exc).__name__)
        raise ErrorDeDominio(503, "No se pudo conectar con Jira") from exc
    except ValueError as exc:
        raise ErrorDeDominio(502, "Respuesta de Jira no válida") from exc


def probar_conexion(cfg: dict, timeout: float = 10) -> dict:
    """La prueba de conexion (`GET /rest/api/3/myself`). Lanza `ErrorDeDominio` si falla.

    Auditoria 2026-11 (#34): habia una por implementacion (`/jira/test`,
    `/integrations/jira/configs/{id}/test`), cada una con su cliente.
    """
    if not cfg.get("jira_url") or not cfg.get("jira_api_token"):
        raise ErrorDeDominio(400, "Jira no configurado. Ve a /jira/config primero.")
    data = llamar_a_jira(cfg, "GET", "/rest/api/3/myself", timeout=timeout)
    return {
        "ok": True,
        "account_id": data.get("accountId"),
        "display_name": data.get("displayName"),
        "email": data.get("emailAddress"),
    }


# ── Sincronizacion periodica (worker) ─────────────────────────────────────────

def organizaciones_con_jira(db: Session) -> list[str]:
    """Las organizaciones con conexion de tareas activa. El worker no tiene sujeto: va explicito."""
    filas = db.query(JiraConfig.organization_id).filter(
        JiraConfig.usar_para_tareas.is_(True),
        JiraConfig.is_active.isnot(False),
        JiraConfig.organization_id.isnot(None),
    ).distinct().all()
    return sorted({f[0] for f in filas if f[0]})


def sincronizar_organizacion(db: Session, org_id: str, *, minutos: int = 65) -> dict:
    """Trae las incidencias recientes del Jira de `org_id` a SUS tareas.

    Auditoria 2026-11 (#14): cada organizacion con su configuracion, y la
    busqueda acotada a ella. Los errores HTTP se propagan (Celery reintenta).

    Solo actualiza tareas ya enlazadas: una tarea necesita proyecto (columna
    obligatoria) y el worker no sabe en cual ponerla. Las incidencias nuevas se
    importan con `POST /jira/sync`, que lleva proyecto.

    Auditoria 2026-11 (#34): usa los mapas comunes. Un estado o prioridad de
    Jira que no se conoce deja el de la tarea como esta (antes la devolvia a
    `todo`/`medium`).
    """
    from app.core.timeutil import utcnow
    from app.models.task import TaskPriority, TaskStatus

    cfg = {k: (v or "").strip() for k, v in get_jira_config(db, org_id).items()}
    if not all(cfg.values()):
        return {"synced": 0, "errors": 0, "skipped": "configuración incompleta"}

    cutoff = (utcnow() - datetime.timedelta(minutes=minutos)).strftime("%Y-%m-%d %H:%M")
    jql = f"project = {cfg['jira_project_key']} AND updated >= '{cutoff}' ORDER BY updated DESC"
    datos = llamar_a_jira_crudo(cfg, "POST", "/rest/api/3/issue/search", timeout=25, json={
        "jql": jql, "maxResults": 100,
        "fields": ["summary", "status", "priority", "description", "duedate", "assignee", "issuetype", "labels"],
    })
    synced = errors = skipped = 0
    for issue in datos.get("issues", []):
        try:
            key = issue["key"]
            fields = issue.get("fields", {})
            estado = estado_de_tarea((fields.get("status") or {}).get("name"))
            prioridad = prioridad_de_tarea((fields.get("priority") or {}).get("name"))
            due_raw = fields.get("duedate")
            due_date = datetime.date.fromisoformat(due_raw) if due_raw else None
            existing = db.query(Task).filter(
                Task.jira_issue_key == key, Task.organization_id == org_id,
            ).first()
            if existing is None:
                skipped += 1
                continue
            existing.title = fields.get("summary") or key
            if estado:
                existing.status = TaskStatus(estado)
            if prioridad:
                existing.priority = TaskPriority(prioridad)
            if due_date:
                existing.due_date = due_date
            synced += 1
        except Exception as exc:
            logger.warning("Jira sync: issue %s omitida: %s", issue.get("key", "?"), exc)
            errors += 1
    return {"synced": synced, "errors": errors, "skipped": skipped}


def empujar_tareas_a_jira(db: Session, *, project_id: str, statuses: List[str],
                          jira_project_key: str, org_id: Optional[str],
                          dry_run: bool = False) -> dict:
    """Crea en Jira una issue por cada tarea del proyecto sin `jira_issue_key`.

    Segunda auditoria 2026-11 (n.º 20): estaba en el endpoint `/jira/push`, una
    llamada a Jira de hasta 15 s por tarea dentro de la peticion. Aqui la puede
    ejecutar el worker (`encolar`); con `dry_run` no llama a Jira y sigue siendo
    sincrona.
    """
    cfg = get_jira_config(db, org_id)
    if not cfg["jira_url"] or not cfg["jira_api_token"]:
        raise ErrorDeDominio(400, "Jira no configurado.")
    tasks = get_tasks_for_push(db, project_id, statuses, org_id=org_id)

    created = skipped = errors = 0
    errs = []
    for task in tasks:
        jira_payload = {
            "fields": {
                "project":   {"key": jira_project_key},
                "summary":   task.title,
                "issuetype": {"name": "Task"},
                "priority":  {"name": TAREA_A_JIRA_PRIORIDAD.get(task.priority or "medium", "Medium")},
            }
        }
        if task.description:
            jira_payload["fields"]["description"] = {
                "type": "doc", "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": task.description}]}]
            }
        if task.due_date:
            jira_payload["fields"]["duedate"] = str(task.due_date)

        if dry_run:
            created += 1
            continue

        try:
            data = llamar_a_jira(cfg, "POST", "/rest/api/3/issue", json=jira_payload, timeout=15)
            task.jira_issue_key = data["key"]
            task.jira_issue_id  = data["id"]
            task.jira_synced_at = datetime.datetime.now(datetime.timezone.utc)
            created += 1
        except Exception as e:
            logger.warning("push_nexus_to_jira: excepcion ignorada", exc_info=True)
            errors += 1
            # Sin el cuerpo de la respuesta remota (auditoria 2026-11 #25).
            errs.append({"task_id": task.id, "error": str(getattr(e, "detail", None) or type(e).__name__)[:100]})

    if not dry_run:
        commit_db(db)

    return {
        "ok": True,
        "dry_run": dry_run,
        "tasks_evaluated": len(tasks),
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "error_details": errs[:10],
    }
