"""
Service helpers for Microsoft 365 integration endpoints.
Encapsulates database queries used by the m365 router.
"""
import httpx
from datetime import date

from sqlalchemy.orm import Session
from app.models.task import ESTADOS_DE_TAREA_TERMINADOS
from app.core.config import settings
from app.models.financial import ProjectMilestone
from app.models.task import Task
from app.core.errores import ErrorDeDominio
from app.services.settings_service import outbound_http_timeout

GRAPH_BASE = f"{settings.MICROSOFT_GRAPH_BASE}/v1.0"


def m365_configured() -> bool:
    return bool(settings.AZURE_TENANT_ID and settings.AZURE_CLIENT_ID and settings.AZURE_CLIENT_SECRET)


def require_m365() -> None:
    if not m365_configured():
        raise ErrorDeDominio(503, detail={
            "error": "M365_NOT_CONFIGURED",
            "message": "Configura las variables de entorno: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET",
            "docs_url": "https://learn.microsoft.com/en-us/graph/auth-v2-service",
        })


async def get_graph_token() -> str:
    url = f"{settings.MICROSOFT_OAUTH_BASE}/{settings.AZURE_TENANT_ID}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": settings.AZURE_CLIENT_ID,
        "client_secret": settings.AZURE_CLIENT_SECRET,
        "scope": f"{settings.MICROSOFT_GRAPH_BASE}/.default",
    }
    async with httpx.AsyncClient(timeout=outbound_http_timeout(default=15)) as client:
        resp = await client.post(url, data=data)
    if resp.status_code != 200:
        raise ErrorDeDominio(502, "Error obteniendo token de Azure AD")
    return resp.json()["access_token"]


def get_graph_token_sync() -> str:
    url = f"{settings.MICROSOFT_OAUTH_BASE}/{settings.AZURE_TENANT_ID}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": settings.AZURE_CLIENT_ID,
        "client_secret": settings.AZURE_CLIENT_SECRET,
        "scope": f"{settings.MICROSOFT_GRAPH_BASE}/.default",
    }
    with httpx.Client(timeout=outbound_http_timeout(default=15)) as client:
        resp = client.post(url, data=data)
    if resp.status_code != 200:
        raise ErrorDeDominio(502, "Error obteniendo token de Azure AD")
    return resp.json()["access_token"]


from app.core.metrics import track_external_call


async def graph_get(path: str) -> dict:
    token = await get_graph_token()
    with track_external_call("ms_graph"):
        async with httpx.AsyncClient(timeout=outbound_http_timeout(default=20)) as client:
            resp = await client.get(f"{GRAPH_BASE}{path}", headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        return resp.json()


async def graph_post(path: str, payload: dict) -> dict:
    token = await get_graph_token()
    with track_external_call("ms_graph"):
        async with httpx.AsyncClient(timeout=outbound_http_timeout(default=20)) as client:
            resp = await client.post(f"{GRAPH_BASE}{path}", json=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        resp.raise_for_status()
        return resp.json()


async def graph_patch(path: str, payload: dict) -> dict:
    token = await get_graph_token()
    with track_external_call("ms_graph"):
        async with httpx.AsyncClient(timeout=outbound_http_timeout(default=20)) as client:
            resp = await client.patch(f"{GRAPH_BASE}{path}", json=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        resp.raise_for_status()
        return resp.json()


async def graph_delete(path: str) -> None:
    token = await get_graph_token()
    with track_external_call("ms_graph"):
        async with httpx.AsyncClient(timeout=outbound_http_timeout(default=20)) as client:
            resp = await client.delete(f"{GRAPH_BASE}{path}", headers={"Authorization": f"Bearer {token}"})
        if resp.status_code not in (200, 204):
            resp.raise_for_status()


def graph_get_sync(path: str) -> dict:
    token = get_graph_token_sync()
    with track_external_call("ms_graph"):
        with httpx.Client(timeout=outbound_http_timeout(default=20)) as client:
            resp = client.get(f"{GRAPH_BASE}{path}", headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        return resp.json()


def graph_post_sync(path: str, payload: dict) -> dict:
    token = get_graph_token_sync()
    with track_external_call("ms_graph"):
        with httpx.Client(timeout=outbound_http_timeout(default=20)) as client:
            resp = client.post(f"{GRAPH_BASE}{path}", json=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        resp.raise_for_status()
        return resp.json()


def _upns_de_la_organizacion(db: Session, user, upns: list[str]) -> set[str]:
    """De `upns`, los que son el correo de un usuario activo de la organizacion de `user`."""
    from sqlalchemy import func
    from app.db.session import _miembros_de
    from app.models.user import User

    org_id = getattr(user, "organization_id", None)
    buscados = {(u or "").strip().lower() for u in upns if (u or "").strip()}
    if not org_id or not buscados:
        return set()
    filas = db.query(func.lower(User.email)).filter(
        func.lower(User.email).in_(buscados),
        User.is_active == True,  # noqa: E712
        _miembros_de(User, org_id),
    ).all()
    return {f[0] for f in filas if f[0]}


def buzon_de_la_organizacion(db: Session, user, upn: str) -> str:
    """El UPN, codificado para la ruta de Graph, si es de un usuario de la organizacion.

    Auditoria 2026-11 (#15): las credenciales de Graph son de aplicacion (sirven
    para CUALQUIER buzon del tenant de Azure), y `user_upn` llegaba libre: un
    administrador de un cliente podia leer o escribir el calendario de
    cualquiera. Ahora solo buzones de usuarios de su organizacion.
    """
    from urllib.parse import quote

    limpio = (upn or "").strip()
    if not limpio or limpio.lower() not in _upns_de_la_organizacion(db, user, [limpio]):
        raise ErrorDeDominio(403, "Ese buzón no es de un usuario de tu organización")
    return quote(limpio, safe="@")


def upns_de_la_organizacion(db: Session, user, upns: list[str]) -> list[str]:
    """Los UPN de la lista que son de usuarios de la organizacion, codificados para Graph."""
    from urllib.parse import quote

    permitidos = _upns_de_la_organizacion(db, user, upns)
    return [quote(u.strip(), safe="@") for u in upns if u.strip().lower() in permitidos]


def get_upcoming_milestones(db: Session, cutoff: date, limit: int = 50) -> list:
    """Return milestones with due_date up to cutoff."""
    return (
        db.query(ProjectMilestone)
        .filter(ProjectMilestone.due_date <= cutoff)
        .limit(limit)
        .all()
    )


def get_active_tasks_for_project(db: Session, project_id: str, limit: int = 200) -> list:
    """Return non-terminal tasks for a project."""
    return (
        db.query(Task)
        .filter(
            Task.project_id == project_id,
            Task.status.notin_(ESTADOS_DE_TAREA_TERMINADOS),
        )
        .limit(limit)
        .all()
    )
