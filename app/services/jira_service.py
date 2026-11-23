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
from urllib.parse import quote
from typing import Optional, List

from sqlalchemy.orm import Session

from app.models.jira_integration import JiraConfig
from app.models.settings import AppSetting
from app.models.task import Task
from app.core.encryption import encrypt_value, decrypt_value
from app.core.codigos_de_error import error

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


_SECRETOS_DESCIFRADOS: dict = {}


def _secreto_descifrado(cifrado: str) -> Optional[str]:
    """Caché por proceso del secreto en claro, por su valor cifrado (rotar el
    secreto cambia el cifrado: la entrada vieja deja de usarse)."""
    if cifrado not in _SECRETOS_DESCIFRADOS:
        if len(_SECRETOS_DESCIFRADOS) > 1024:
            _SECRETOS_DESCIFRADOS.clear()
        _SECRETOS_DESCIFRADOS[cifrado] = decrypt_value(cifrado)
    return _SECRETOS_DESCIFRADOS[cifrado]


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
        # Auditoría 22-11-2026 (baja): sin `?org=` se descifraban (KMS incluido)
        # los secretos de todas las empresas en CADA webhook. Ahora cada valor
        # cifrado se descifra una vez por proceso (`_secreto_descifrado`); la
        # URL que da la pantalla lleva `?org=` y acota a una sola fila.
        secreto = _secreto_descifrado(fila.value) if fila.value else None
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
        raise error(400, "jira_config_de_empresa", detail="El secreto del webhook de Jira es de una organización")
    secreto = _secrets.token_urlsafe(32)
    set_setting(db, JIRA_WEBHOOK_SECRET_KEY, secreto, org_id)
    db.commit()
    return secreto


# §5 (auditoría 22-11-2026): `tiene_secreto_de_webhook` (sin uso) retirada.

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


#: A57 (auditoría 22-11-2026): la categoría del estado (`status.statusCategory.key`,
#: igual en todos los idiomas y flujos de Jira Cloud: `new`, `indeterminate`,
#: `done`). Un Jira en castellano («Tareas por hacer», «En curso», «Listo») o con
#: estados propios ya no devuelve las tareas a `todo` en cada sincronización.
JIRA_CATEGORIA_A_ESTADO = {"new": "todo", "indeterminate": "in_progress", "done": "done"}


def estado_de_tarea(nombre_en_jira: Optional[str], defecto: Optional[str] = None) -> Optional[str]:
    return JIRA_STATUS_MAP.get((nombre_en_jira or "").strip().lower(), defecto)


def estado_de_incidencia(estado: Optional[dict]) -> Optional[str]:
    """Estado de tarea para el objeto `status` de una incidencia de Jira: por el
    nombre si es uno conocido (más fino: `in review`, `blocked`, `cancelled`) y,
    si no, por la categoría. None si no hay ni una cosa ni otra (se deja el actual)."""
    estado = estado or {}
    por_nombre = estado_de_tarea(estado.get("name"))
    if por_nombre:
        return por_nombre
    return JIRA_CATEGORIA_A_ESTADO.get(((estado.get("statusCategory") or {}).get("key") or "").lower())


def prioridad_de_tarea(nombre_en_jira: Optional[str], defecto: Optional[str] = None) -> Optional[str]:
    return JIRA_PRIORITY_MAP.get((nombre_en_jira or "").strip().lower(), defecto)


# ── AppSetting helpers ─────────────────────────────────────────────────────────

def _es_cifrado(valor: Optional[str]) -> bool:
    return bool(valor) and str(valor).startswith(("v2:", "kmsv1:"))


def _descifrar(valor: Optional[str]) -> Optional[str]:
    """M96 (auditoría 22-11-2026): si no se descifra un valor CIFRADO (clave
    retirada), None; antes `decrypt_value(x) or x` mandaba el criptograma a Jira
    como token. Lo antiguo sin cifrar se usa tal cual."""
    if not valor:
        return None
    dec = decrypt_value(valor)
    if dec is None and _es_cifrado(valor):
        logger.error("Jira: no se pudo descifrar un secreto guardado (¿clave retirada?)")
        return None
    return dec if dec is not None else valor


def _en_claro(key: str, value: Optional[str]) -> Optional[str]:
    if value and key in _SENSITIVE_SETTING_KEYS:
        return _descifrar(value)
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
    return _descifrar(config.jira_api_token_enc or "") or ""


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
        raise error(400, "jira_config_de_empresa", detail="La configuración de Jira es de una organización")
    config = configuracion_de_tareas(db, org_id)
    if config is None:
        config = JiraConfig(name=NOMBRE_DE_LA_CONEXION_DE_TAREAS, organization_id=org_id,
                            usar_para_tareas=True)
        db.add(config)
    config.jira_base_url = (jira_url or "").rstrip("/")
    config.jira_email = jira_email
    # M96: sin token nuevo se conserva el guardado (antes, guardar sin teclearlo lo borraba).
    if jira_api_token:
        config.jira_api_token_enc = encrypt_value(jira_api_token)
    config.jira_project_key = jira_project_key
    config.is_active = True
    db.commit()
    return config


# ── Hub de integraciones (`/integrations-hub/jira/*`) ─────────────────────────
# Segunda auditoria 2026-11 (#23): el hub guardaba sus credenciales en
# `integration_configs` (tipo jira), aparte de la conexion de las tareas. Ahora
# lee y escribe la misma `JiraConfig` (`usar_para_tareas`) de la organizacion.

def config_del_hub(config: Optional[JiraConfig]) -> dict:
    """La conexion como la ve el formulario del hub, sin el token."""
    if config is None:
        return {"configured": False}
    return {
        "configured": True, "id": config.id, "name": config.name,
        "base_url": config.jira_base_url or "", "email": config.jira_email or "",
        "project_key": config.jira_project_key or "", "has_token": bool(config.jira_api_token_enc),
        "is_active": config.is_active is not False,
        "last_sync_at": str(config.last_full_sync_at)[:16] if config.last_full_sync_at else None,
    }


def credenciales_del_hub(db: Session, org_id: Optional[str]) -> dict:
    """`{base_url, email, api_token}` de la conexion activa de la organizacion (404 si no hay)."""
    config = configuracion_de_tareas(db, org_id)
    if config is None or config.is_active is False:
        raise error(404, "integracion_no_configurada", detail="Jira no está configurado en esta organización", nombre="Jira")
    c = credenciales(config)
    return {"base_url": c["jira_url"] or "", "email": c["jira_email"] or "",
            "api_token": c["jira_api_token"] or "", "project_key": c["jira_project_key"] or ""}


def guardar_desde_hub(db: Session, org_id: Optional[str], *, base_url: str, email: str,
                      api_token: Optional[str] = None, project_key: Optional[str] = None,
                      name: Optional[str] = None, user_id: Optional[str] = None) -> JiraConfig:
    """Crea o actualiza la conexion de la organizacion. Sin `api_token`, conserva el guardado."""
    from app.core.outbound_url import validate_outbound_url

    validate_outbound_url(base_url or "", field="base_url")
    if not org_id:
        raise error(400, "jira_config_de_empresa", detail="La configuración de Jira es de una organización")
    config = configuracion_de_tareas(db, org_id)
    if config is None:
        if not api_token:
            raise error(422, "jira_falta_token", detail="Falta el API token de Jira")
        config = JiraConfig(name=name or NOMBRE_DE_LA_CONEXION_DE_TAREAS, organization_id=org_id,
                            usar_para_tareas=True, created_by_user_id=user_id,
                            jira_project_key=project_key or "")
        db.add(config)
    if name:
        config.name = name
    config.jira_base_url = (base_url or "").rstrip("/")
    config.jira_email = email
    if api_token:
        config.jira_api_token_enc = encrypt_value(api_token)
    if project_key is not None:
        config.jira_project_key = project_key
    config.is_active = True
    db.commit()
    return config


def desactivar_desde_hub(db: Session, org_id: Optional[str]) -> bool:
    """Para la conexion y borra el token (lo que hacia el borrado de `integration_configs`)."""
    config = configuracion_de_tareas(db, org_id)
    if config is None:
        return False
    config.is_active = False
    config.jira_api_token_enc = ""
    db.commit()
    return True


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
    viewer=None,
) -> dict:
    """
    Create or update NexusPM Tasks from a list of raw Jira issue dicts.
    Returns ``{"created": int, "updated": int, "skipped": int,
    "skipped_without_project": int}``.

    Auditoria 2026-11 (#14): la tarea existente se busca en la organizacion de
    quien sincroniza, no en todas.

    Segunda auditoria 2026-11: sin proyecto se creaba `Task(project_id=None)`
    y la columna es obligatoria: 500 al hacer commit. Ahora:
    - con `project_id`, el proyecto tiene que existir y ser visible para quien
      sincroniza (`scope_projects_query`); si no, 404 antes de tocar nada;
    - sin `project_id`, las tareas ya enlazadas se actualizan y las
      incidencias nuevas se omiten y se cuentan en `skipped_without_project`
      (lo mismo que hace la sincronizacion periodica del worker).
    """
    if project_id:
        from app.models.project import Project
        q_proyecto = db.query(Project.id).filter(Project.id == project_id)
        if org_id:
            q_proyecto = q_proyecto.filter(Project.organization_id == org_id)
        if viewer is not None:
            from app.services.project_service import scope_projects_query
            q_proyecto = scope_projects_query(q_proyecto, db, viewer)
        if q_proyecto.first() is None:
            raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")

    created = updated = skipped = sin_proyecto = 0
    now = datetime.datetime.now(datetime.timezone.utc)

    for iss in issues:
        f = iss.get("fields", {})
        jira_key     = iss["key"]
        jira_id      = iss["id"]
        title        = f.get("summary") or jira_key
        raw_priority = ((f.get("priority") or {}).get("name") or "").lower()
        nm_status    = estado_de_incidencia(f.get("status"))          # A57
        nm_priority  = JIRA_PRIORITY_MAP.get(raw_priority)
        due_date     = _fecha_de_jira(f.get("duedate"))                # M96: fecha, no texto

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
                if nm_status:
                    _aplicar_estado(existing, nm_status)
                if nm_priority:
                    existing.priority   = nm_priority
                existing.jira_issue_id  = jira_id
                existing.jira_synced_at = now
                if due_date:
                    existing.due_date = due_date
            updated += 1
        elif not project_id:
            skipped += 1
            sin_proyecto += 1
        else:
            if not dry_run:
                task = Task(
                    title=title,
                    description=desc_text,
                    status=nm_status or "todo",
                    priority=nm_priority or "medium",
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

    return {"created": created, "updated": updated, "skipped": skipped,
            "skipped_without_project": sin_proyecto}


def _fecha_de_jira(valor) -> Optional[datetime.date]:
    if not valor:
        return None
    if isinstance(valor, datetime.date):
        return valor
    try:
        return datetime.date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _aplicar_estado(task: Task, nuevo: str) -> bool:
    """M96: el estado que llega de Jira pasa por las reglas de transición de la
    tarea (y sus efectos: fecha de cierre…), como desde la pantalla. Si la
    transición no es válida se deja el estado y se anota en el log."""
    from app.core.errores import ErrorDeDominio
    from app.models.task import TaskStatus
    from app.services.tasks.core import apply_status_side_effects, validate_task_transition
    actual = getattr(task.status, "value", task.status)
    if actual == nuevo:
        return False
    try:
        validate_task_transition(TaskStatus(actual), TaskStatus(nuevo))
    except (ErrorDeDominio, ValueError):
        logger.info("Jira: la tarea %s no puede pasar de %s a %s; se deja", task.id, actual, nuevo)
        return False
    task.status = TaskStatus(nuevo)
    apply_status_side_effects(task, TaskStatus(nuevo))
    return True


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
    if nm_status and _aplicar_estado(task, nm_status):   # M96: reglas de transición
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
        raise error(502, "servicio_externo_fallo", detail=f"Jira devolvió HTTP {exc.response.status_code}", servicio="Jira") from exc
    except (httpx.RequestError, PermissionError) as exc:
        logger.warning("Jira %s %s: no se pudo conectar (%s)", method, path, type(exc).__name__)
        raise error(503, "servicio_externo_sin_conexion", detail="No se pudo conectar con Jira", servicio="Jira") from exc
    except ValueError as exc:
        raise error(502, "servicio_externo_respuesta_no_valida", detail="Respuesta de Jira no válida", servicio="Jira") from exc


def probar_conexion(cfg: dict, timeout: float = 10) -> dict:
    """La prueba de conexion (`GET /rest/api/3/myself`). Lanza `ErrorDeDominio` si falla.

    Auditoria 2026-11 (#34): habia una por implementacion (`/jira/test`,
    `/integrations/jira/configs/{id}/test`), cada una con su cliente.
    """
    if not cfg.get("jira_url") or not cfg.get("jira_api_token"):
        raise error(400, "integracion_no_configurada", detail="Jira no configurado. Ve a /jira/config primero.", nombre="Jira")
    data = llamar_a_jira(cfg, "GET", "/rest/api/3/myself", timeout=timeout)
    return {
        "ok": True,
        "account_id": data.get("accountId"),
        "display_name": data.get("displayName"),
        "email": data.get("emailAddress"),
        "comprobaciones": _comprobaciones_de_uso(cfg, timeout),
    }


def _comprobaciones_de_uso(cfg: dict, timeout: float) -> dict:
    """23-11-2026 (auditoría 02 A56/A57, «sin probar contra el servicio real»):
    además de la autenticación (`/myself`), lo que usa la sincronización de
    verdad, cada cosa con su resultado (`True`/`False`, o `None` si no aplica):

    - `proyecto`: `GET /rest/api/3/project/{clave}` (la clave configurada existe
      y la cuenta la ve).
    - `busqueda`: `POST /rest/api/3/search/jql` con `maxResults=1` (la ruta de
      búsqueda que usan la sincronización y el buscador; A56).
    - `estados`: `GET /rest/api/3/status` y que traigan `statusCategory`, que es
      por lo que se mapean (A57; vale para un Jira en cualquier idioma).

    Un fallo aquí no tumba la prueba (la autenticación ya pasó): se informa.
    Solo lectura; nunca crea ni cambia nada en Jira."""
    import httpx

    def _ok(fn) -> bool:
        try:
            return bool(fn())
        except (httpx.HTTPError, PermissionError, ValueError):
            return False
        except Exception:  # ErrorDeDominio del guardia u otro: no válido, sin texto remoto
            logger.debug("prueba de Jira: comprobación fallida", exc_info=True)
            return False

    clave = (cfg.get("jira_project_key") or "").strip()
    jql = f"project = {comillas_jql(clave)}" if clave else "order by created DESC"
    return {
        "proyecto": _ok(lambda: llamar_a_jira_crudo(
            cfg, "GET", f"/rest/api/3/project/{quote(clave, safe='')}", timeout=timeout)) if clave else None,
        "busqueda": _ok(lambda: "issues" in (llamar_a_jira_crudo(
            cfg, "POST", RUTA_DE_BUSQUEDA, json={"jql": jql, "maxResults": 1, "fields": ["status"]},
            timeout=timeout) or {})),
        "estados": _ok(lambda: any(isinstance(e, dict) and e.get("statusCategory") for e in (
            llamar_a_jira_crudo(cfg, "GET", "/rest/api/3/status", timeout=timeout) or []))),
    }


# ── Sincronizacion periodica (worker) ─────────────────────────────────────────

#: A56 (auditoría 22-11-2026): la búsqueda de Jira Cloud es
#: `POST /rest/api/3/search/jql` (las antiguas `/search` e `/issue/search` están
#: retiradas). Pagina con `nextPageToken` hasta `isLast`.
RUTA_DE_BUSQUEDA = "/rest/api/3/search/jql"


def comillas_jql(valor: str) -> str:
    """Un literal JQL entre comillas dobles (M40: la clave de proyecto iba sin escapar)."""
    return '"' + str(valor or "").replace("\\", "\\\\").replace('"', '\\"') + '"'


def buscar_incidencias(cfg: dict, jql: str, fields: list, *, por_pagina: int = 100, tope: int = 5000,
                       timeout: float = 25, crudo: bool = True) -> list:
    """Todas las incidencias de `jql` (hasta `tope`), página a página."""
    llamar = llamar_a_jira_crudo if crudo else llamar_a_jira
    salida: list = []
    token = None
    while len(salida) < tope:
        cuerpo = {"jql": jql, "maxResults": min(por_pagina, tope - len(salida)), "fields": fields}
        if token:
            cuerpo["nextPageToken"] = token
        datos = llamar(cfg, "POST", RUTA_DE_BUSQUEDA, json=cuerpo, timeout=timeout) or {}
        salida.extend(datos.get("issues") or [])
        token = datos.get("nextPageToken")
        if datos.get("isLast", True) or not token:
            break
    return salida


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

    # M40 (auditoría 22-11-2026): ventana RELATIVA (`-65m`): JQL interpreta las
    # fechas absolutas en la zona del usuario de Jira, no en UTC, y la ventana
    # se desplazaba horas. Clave de proyecto entre comillas y paginación.
    jql = f"project = {comillas_jql(cfg['jira_project_key'])} AND updated >= -{int(minutos)}m ORDER BY updated DESC"
    incidencias = buscar_incidencias(cfg, jql, [
        "summary", "status", "priority", "description", "duedate", "assignee", "issuetype", "labels"])
    synced = errors = skipped = 0
    for issue in incidencias:
        try:
            key = issue["key"]
            fields = issue.get("fields", {})
            estado = estado_de_incidencia(fields.get("status"))       # A57: por categoría
            prioridad = prioridad_de_tarea((fields.get("priority") or {}).get("name"))
            due_date = _fecha_de_jira(fields.get("duedate"))
            existing = db.query(Task).filter(
                Task.jira_issue_key == key, Task.organization_id == org_id,
            ).first()
            if existing is None:
                skipped += 1
                continue
            existing.title = fields.get("summary") or key
            if estado:
                _aplicar_estado(existing, estado)
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
        raise error(400, "integracion_no_configurada", detail="Jira no configurado.", nombre="Jira")
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


def marcar_sincronizacion_completa(db: Session, org_id: Optional[str]) -> None:
    """Sella `last_full_sync_at` y confirma (antes lo hacía el endpoint del hub)."""
    from datetime import datetime, timezone
    config = configuracion_de_tareas(db, org_id)
    if config is not None:
        config.last_full_sync_at = datetime.now(timezone.utc)
    db.commit()
