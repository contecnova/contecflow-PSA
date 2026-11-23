"""
notifications.py — In-app notification service.

Usage:
    from app.services.notifications import notify_user, notify_role
    notify_user(db, user_id, "task_assigned", "Nueva tarea asignada",
                "Luis te asignó: Fix login bug", resource="tasks", resource_id=task.id)

Multi-worker WebSocket delivery:
    When REDIS_URL is set, notify_user also publishes the notification payload
    to the Redis channel "contecflow:ws:<user_id>" so every worker can push it
    to the client immediately, regardless of which process holds the WS connection.
    Without Redis, the WS polling loop delivers it within ~15 seconds.

Auditoria 2026-11 (hallazgo 23). Las notificaciones vivian en tres modulos:
este (avisos en la aplicacion: fila + empujon por WS), `realtime_notifications`
(una funcion de una linea que empujaba por WS desde codigo asincrono) y
`notification_service` (correo). `realtime_notifications` hacia lo mismo que
`_push_ws_notification` pero desde `async`: se ha traido aqui como
`publish_user_notification` y el modulo se ha borrado. `notification_service`
se queda aparte porque su responsabilidad es otra: el correo saliente.
"""
import json
import logging
import threading
from typing import Optional
from sqlalchemy import event
from sqlalchemy.orm import Session
from app.models.enterprise import Notification
from app.models.user import User
from app.core.config import settings

logger = logging.getLogger(__name__)
_REDIS_URL: Optional[str] = settings.REDIS_URL or ""


_redis_cliente = None
_redis_cerrojo = threading.Lock()


def _redis():
    """Un cliente Redis por proceso (con su pool de conexiones).

    Auditoria 2026-11-22 (03, bajos m-p): antes se abria y cerraba una conexion
    por cada aviso (un `notify_role` a 200 personas = 200 conexiones)."""
    global _redis_cliente
    if _redis_cliente is None:
        with _redis_cerrojo:
            if _redis_cliente is None:
                import redis as sync_redis
                _redis_cliente = sync_redis.from_url(_REDIS_URL, decode_responses=True)
    return _redis_cliente


def _push_ws_notification(user_id: str, payload: dict) -> None:
    """Fire-and-forget: publish notification to Redis WS channel if available."""
    if not _REDIS_URL:
        return
    try:
        from app.services.ws_manager import canal_de_usuario
        _redis().publish(canal_de_usuario(user_id), json.dumps(payload))
    except Exception as exc:
        logger.debug(f"WS Redis push failed (non-critical): {exc}")


_PENDIENTES = "_avisos_ws_pendientes"


def _empujar_al_confirmar(db: Session, user_id: str, payload: dict) -> None:
    """Auditoria 2026-11-22 (03, bajos m-p): el empujon por WebSocket sale
    cuando la transaccion se confirma. Antes salia al hacer `db.add`, y si la
    peticion fallaba despues el usuario veia un aviso que no existia."""
    db.info.setdefault(_PENDIENTES, []).append((user_id, payload))


@event.listens_for(Session, "after_commit")
def _tras_confirmar(sesion) -> None:
    for user_id, payload in sesion.info.pop(_PENDIENTES, None) or ():
        _push_ws_notification(user_id, payload)


@event.listens_for(Session, "after_rollback")
def _tras_deshacer(sesion) -> None:
    sesion.info.pop(_PENDIENTES, None)


async def publish_user_notification(user_id: str, payload: dict) -> None:
    """Empuja `payload` por WebSocket desde codigo asincrono (sin fila en BD).

    Con Redis llega a todos los workers; sin Redis, a las conexiones de este.
    """
    from app.services.ws_manager import manager
    await manager.publish(user_id, payload)


NOTIFICATION_ICONS = {
    "task_assigned":     ("🎯", "#00d4ff"),
    "task_mentioned":    ("💬", "#7c3aed"),
    "task_due_soon":     ("⏰", "#ffb800"),
    "task_overdue":      ("🔴", "#ff4757"),
    "sprint_started":    ("⚡", "#00d4ff"),
    "sprint_ending":     ("🏁", "#ffb800"),
    "expense_approved":  ("✅", "#00e5a0"),
    "expense_rejected":  ("❌", "#ff4757"),
    "milestone_approved": ("✅", "#00e5a0"),
    "milestone_rejected": ("❌", "#ff4757"),
    "ticket_assigned":   ("🎫", "#00d4ff"),
    "ticket_replied":    ("💬", "#7c3aed"),
    "ticket_resolved":   ("✓",  "#00e5a0"),
    "ticket_created":    ("🎫", "#7a8aaa"),
    "ticket_updated":    ("🔄", "#7a8aaa"),
    "ticket_sla_warning":("⏳", "#ffb800"),
    "ticket_sla_breached":("🔴", "#ff4757"),
    "ticket_escalated":  ("⬆️", "#ff6b35"),
    "approval_requested":("📝", "#7c3aed"),
    "project_risk_high": ("⚠️", "#ff4757"),
    "timesheet_reminder":("📋", "#ffb800"),
    "timesheet_approved":("✅", "#00e5a0"),
    "budget_warning":    ("💰", "#ffb800"),
    "mention":           ("@",  "#7c3aed"),
    "automation":        ("⚙️", "#00d4ff"),
    "system":            ("🔔", "#7a8aaa"),
}


def notify_user(
    db: Session,
    user_id: str,
    ntype: str,
    title: str,
    body: Optional[str] = None,
    resource: Optional[str] = None,
    resource_id: Optional[str] = None,
    action_url: Optional[str] = None,
    *,
    aviso: Optional[dict] = None,
) -> Notification:
    """Aviso en la aplicacion (fila + empujon por WebSocket).

    18-11-2026 (auditoria de textos fijos): con `aviso={"titulo": clave,
    "cuerpo": clave_o_None, "params": {...}}` el titulo y el cuerpo se pintan
    en el idioma del destinatario (`textos_de_salida`); `title`/`body` quedan de
    respaldo si la clave no se puede pintar. La clave y los datos tambien van
    en el empujon por WebSocket (`title_key`, `body_key`, `params`).
    """
    icon, color = NOTIFICATION_ICONS.get(ntype, ("🔔", "#7a8aaa"))
    # Si no lo quiere en la aplicacion, ni fila ni empujon por WebSocket.
    from app.services.preferencias_de_aviso import quiere
    if not quiere(db, user_id, ntype, "app"):
        return None
    if aviso:
        title, body = texto_de_aviso(db, user_id, aviso, title, body)
    n = Notification(
        user_id=user_id,
        type=ntype,
        title=title,
        body=body,
        icon=icon,
        color=color,
        resource=resource,
        resource_id=resource_id,
        action_url=action_url,
    )
    db.add(n)
    # Push to WS via Redis (cross-worker) once the row is committed.
    # This is best-effort — the WS polling loop is the guaranteed fallback.
    _empujar_al_confirmar(db, user_id, {
        "type": "notification_push",
        "ntype": ntype,
        "title": title,
        "body": body,
        "resource": resource,
        "resource_id": resource_id,
        "action_url": action_url,
        **({"title_key": aviso.get("titulo"), "body_key": aviso.get("cuerpo"),
            "params": aviso.get("params") or {}} if aviso else {}),
    })
    return n


def texto_de_aviso(db: Session, user_id: str, aviso: dict, title: str, body: Optional[str]):
    """(titulo, cuerpo) de `aviso` en el idioma de `user_id`; si falla, `title`/`body`."""
    try:
        from app.services.formato_regional import idioma_de_salida
        from app.services.textos_de_salida import texto
        idioma = idioma_de_salida(db, user_id=user_id)
        params = aviso.get("params") or {}
        titulo = texto(aviso["titulo"], idioma, **params) if aviso.get("titulo") else title
        cuerpo = texto(aviso["cuerpo"], idioma, **params) if aviso.get("cuerpo") else body
        return titulo, cuerpo
    except Exception:
        logger.debug("texto_de_aviso: se usa el texto de respaldo", exc_info=True)
        return title, body


def notify_role(
    db: Session,
    role: str,
    ntype: str,
    title: str,
    body: Optional[str] = None,
    resource: Optional[str] = None,
    resource_id: Optional[str] = None,
    action_url: Optional[str] = None,
    *,
    organization_id: Optional[str],
    aviso: Optional[dict] = None,
) -> int:
    """Avisa a los usuarios activos de un rol **de una organizacion**.

    Auditoria 2026-11: no filtraba por organizacion; desde un trabajo de fondo
    (sin contexto de tenant) avisaba al rol en todas las empresas. Ahora la
    organizacion es obligatoria y sin ella no se avisa a nadie.
    """
    if not organization_id:
        logger.warning("notify_role(%s) sin organizacion: no se avisa a nadie", role)
        return 0
    users = db.query(User).filter(User.role == role, User.is_active == True,
                                  User.organization_id == organization_id).all()
    for u in users:
        notify_user(db, u.id, ntype, title, body, resource, resource_id, action_url, aviso=aviso)
    return len(users)

