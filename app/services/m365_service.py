"""
Service helpers for Microsoft 365 integration endpoints.
Encapsulates database queries used by the m365 router.

23-11-2026 (auditoría 2026-11-22, 03 A-MP3): credenciales de Graph POR EMPRESA.
Antes todo salía con `AZURE_TENANT_ID/CLIENT_ID/CLIENT_SECRET` globales: una
sola aplicación de Azure (permisos de aplicación sobre TODO su tenant) servía a
todas las empresas, y equipos, canales, sitios y buzones de ese tenant eran
alcanzables desde cualquier empresa. Ahora:

- Cada empresa guarda su `ms_graph` (tenant, client id y secreto cifrado) en el
  almacén de credenciales (`integration_credentials_service`) y el token se pide
  y se cachea por (tenant, client id, huella del secreto) de ESA empresa:
  `credenciales_de_graph`.
- Los `AZURE_*` del entorno son la «credencial de plataforma»: solo se usan si
  el operador lo activa explícitamente (`M365_PLATFORM_CREDENTIALS_ENABLED`) y
  la empresa no tiene credencial propia. Una credencial propia a medias NO se
  completa con la de plataforma (sería mezclar tenants): cuenta como no
  configurada.
- `tenant_id` va en la ruta del token: se valida (GUID o dominio) para que no
  se pueda inyectar ruta ni consulta. Los identificadores de Graph que llegan
  de fuera (equipo, canal, sitio) pasan por `id_de_graph`.

Documentado en docs/seguridad/entrada_y_salida.md («Microsoft 365 / Graph»).
"""
import hashlib
import re
import threading
import time
from typing import Optional
from urllib.parse import quote

import httpx
from datetime import date

from sqlalchemy.orm import Session
from app.models.task import ESTADOS_DE_TAREA_TERMINADOS
from app.core.config import settings
from app.models.financial import ProjectMilestone
from app.models.task import Task
from app.core.errores import ErrorDeDominio
from app.services.settings_service import outbound_http_timeout
from app.core.codigos_de_error import error

GRAPH_BASE = f"{settings.MICROSOFT_GRAPH_BASE}/v1.0"

#: Campo del almacén `ms_graph` -> ajuste por empresa equivalente (AppSetting).
_CAMPOS = (("tenant_id", "AZURE_TENANT_ID"), ("client_id", "AZURE_CLIENT_ID"),
           ("client_secret", "AZURE_CLIENT_SECRET"))
#: GUID del tenant o dominio (`contoso.onmicrosoft.com`): nada que cambie la ruta.
_TENANT = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
#: Identificador de Graph (equipo, canal `19:...@thread.tacv2`, sitio `host,guid,guid`).
_ID_DE_GRAPH = re.compile(r"^[A-Za-z0-9@:._,!=-]{1,400}$")

_tokens: dict[tuple[str, str, str], tuple[float, str]] = {}
_tokens_lock = threading.Lock()


def _plataforma() -> Optional[dict]:
    """La credencial de plataforma (`AZURE_*`), solo si está activada a propósito."""
    if not getattr(settings, "M365_PLATFORM_CREDENTIALS_ENABLED", False):
        return None
    if settings.AZURE_TENANT_ID and settings.AZURE_CLIENT_ID and settings.AZURE_CLIENT_SECRET:
        return {"tenant_id": settings.AZURE_TENANT_ID, "client_id": settings.AZURE_CLIENT_ID,
                "client_secret": settings.AZURE_CLIENT_SECRET, "origen": "plataforma"}
    return None


def credenciales_de_graph(db: Optional[Session], org_id: Optional[str]) -> Optional[dict]:
    """`{tenant_id, client_id, client_secret, origen}` de la empresa, o `None`.

    `origen` es `empresa` (su credencial cifrada o sus ajustes) o `plataforma`
    (los `AZURE_*`, solo con `M365_PLATFORM_CREDENTIALS_ENABLED`)."""
    if db is not None and org_id:
        from app.services.integration_credentials_service import secreto_propio_de_la_organizacion
        propias = {campo: secreto_propio_de_la_organizacion(db, "ms_graph", campo, ajuste, org_id)
                   for campo, ajuste in _CAMPOS}
        if all(propias.values()):
            return {**propias, "origen": "empresa"}
        if any(propias.values()):
            return None  # a medias: nunca se completa con la de plataforma
    return _plataforma()


def campos_configurados(db: Optional[Session], org_id: Optional[str], origen: Optional[str] = None) -> dict:
    """`{AZURE_TENANT_ID: bool, ...}` de la credencial que se usaría (para la pantalla)."""
    if origen is not None:
        return {ajuste: True for _, ajuste in _CAMPOS}
    if db is None or not org_id:
        return {ajuste: False for _, ajuste in _CAMPOS}
    from app.services.integration_credentials_service import secreto_propio_de_la_organizacion
    return {ajuste: bool(secreto_propio_de_la_organizacion(db, "ms_graph", campo, ajuste, org_id))
            for campo, ajuste in _CAMPOS}


def m365_configured(db: Optional[Session] = None, org_id: Optional[str] = None) -> bool:
    return credenciales_de_graph(db, org_id) is not None


def origen_de_credenciales(db: Optional[Session] = None, org_id: Optional[str] = None) -> Optional[str]:
    cred = credenciales_de_graph(db, org_id)
    return cred["origen"] if cred else None


def require_m365(db: Optional[Session] = None, org_id: Optional[str] = None) -> dict:
    cred = credenciales_de_graph(db, org_id)
    if cred is None:
        raise ErrorDeDominio(503, detail={
            "error": "M365_NOT_CONFIGURED",
            "code": "integracion_no_configurada",
            "params": {"nombre": "Microsoft 365"},
            "message": "Configura la credencial «Microsoft 365 / Graph» de la empresa "
                       "(tenant, client id y client secret) en Integraciones",
            "docs_url": "https://learn.microsoft.com/en-us/graph/auth-v2-service",
        })
    return cred


def id_de_graph(valor: str, campo: str = "id") -> str:
    """Un identificador de Graph que llega de fuera, validado y codificado para la ruta."""
    limpio = (valor or "").strip()
    if not _ID_DE_GRAPH.fullmatch(limpio) or ".." in limpio:
        raise error(400, "m365_id_no_valido", detail=f"{campo} no válido", campo=campo)
    return quote(limpio, safe="@:,!=")


def _clave_de_cache(cred: dict) -> tuple[str, str, str]:
    huella = hashlib.sha256(str(cred["client_secret"]).encode()).hexdigest()[:16]
    return (str(cred["tenant_id"]), str(cred["client_id"]), huella)


def _datos_del_token(cred: dict) -> tuple[str, dict]:
    tenant = str(cred.get("tenant_id") or "").strip()
    if not _TENANT.fullmatch(tenant):
        raise error(400, "m365_id_no_valido", detail="tenant_id no válido", campo="tenant_id")
    return (f"{settings.MICROSOFT_OAUTH_BASE}/{tenant}/oauth2/v2.0/token", {
        "grant_type": "client_credentials",
        "client_id": cred["client_id"],
        "client_secret": cred["client_secret"],
        "scope": f"{settings.MICROSOFT_GRAPH_BASE}/.default",
    })


def _del_cache(cred: dict) -> Optional[str]:
    with _tokens_lock:
        guardado = _tokens.get(_clave_de_cache(cred))
    if guardado and guardado[0] > time.monotonic():
        return guardado[1]
    return None


def _a_cache(cred: dict, cuerpo: dict) -> str:
    token = cuerpo["access_token"]
    vida = max(60, int(cuerpo.get("expires_in") or 3600) - 120)
    with _tokens_lock:
        _tokens[_clave_de_cache(cred)] = (time.monotonic() + vida, token)
    return token


def _fallo_de_token():
    return error(502, "servicio_externo_fallo", detail="Error obteniendo token de Azure AD", servicio="Azure AD")


def token_de_graph_sync(cred: dict) -> str:
    """Token de aplicación para esa credencial (cacheado hasta poco antes de caducar)."""
    cacheado = _del_cache(cred)
    if cacheado:
        return cacheado
    url, datos = _datos_del_token(cred)
    with httpx.Client(timeout=outbound_http_timeout(default=15)) as client:
        resp = client.post(url, data=datos)
    if resp.status_code != 200:
        raise _fallo_de_token()
    return _a_cache(cred, resp.json())


async def token_de_graph(cred: dict) -> str:
    cacheado = _del_cache(cred)
    if cacheado:
        return cacheado
    url, datos = _datos_del_token(cred)
    async with httpx.AsyncClient(timeout=outbound_http_timeout(default=15)) as client:
        resp = await client.post(url, data=datos)
    if resp.status_code != 200:
        raise _fallo_de_token()
    return _a_cache(cred, resp.json())


async def get_graph_token(db: Optional[Session] = None, org_id: Optional[str] = None) -> str:
    if db is not None:
        from app.core.async_db import run_db
        cred = await run_db(require_m365, db, org_id)
    else:
        cred = require_m365(None, org_id)
    return await token_de_graph(cred)


def get_graph_token_sync(db: Optional[Session] = None, org_id: Optional[str] = None) -> str:
    return token_de_graph_sync(require_m365(db, org_id))


from app.core.metrics import track_external_call


async def graph_get(path: str, *, db: Optional[Session] = None, org_id: Optional[str] = None) -> dict:
    token = await get_graph_token(db, org_id)
    with track_external_call("ms_graph"):
        async with httpx.AsyncClient(timeout=outbound_http_timeout(default=20)) as client:
            resp = await client.get(f"{GRAPH_BASE}{path}", headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        return resp.json()


async def graph_post(path: str, payload: dict, *, db: Optional[Session] = None,
                     org_id: Optional[str] = None) -> dict:
    token = await get_graph_token(db, org_id)
    with track_external_call("ms_graph"):
        async with httpx.AsyncClient(timeout=outbound_http_timeout(default=20)) as client:
            resp = await client.post(f"{GRAPH_BASE}{path}", json=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        resp.raise_for_status()
        return resp.json()


async def graph_delete(path: str, *, db: Optional[Session] = None, org_id: Optional[str] = None) -> None:
    token = await get_graph_token(db, org_id)
    with track_external_call("ms_graph"):
        async with httpx.AsyncClient(timeout=outbound_http_timeout(default=20)) as client:
            resp = await client.delete(f"{GRAPH_BASE}{path}", headers={"Authorization": f"Bearer {token}"})
        if resp.status_code not in (200, 204):
            resp.raise_for_status()


def graph_get_sync(path: str, *, db: Optional[Session] = None, org_id: Optional[str] = None) -> dict:
    token = get_graph_token_sync(db, org_id)
    with track_external_call("ms_graph"):
        with httpx.Client(timeout=outbound_http_timeout(default=20)) as client:
            resp = client.get(f"{GRAPH_BASE}{path}", headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        return resp.json()


def graph_post_sync(path: str, payload: dict, *, db: Optional[Session] = None,
                    org_id: Optional[str] = None) -> dict:
    token = get_graph_token_sync(db, org_id)
    with track_external_call("ms_graph"):
        with httpx.Client(timeout=outbound_http_timeout(default=20)) as client:
            resp = client.post(f"{GRAPH_BASE}{path}", json=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        resp.raise_for_status()
        return resp.json()


def probar_conexion(db: Session, org_id: Optional[str]) -> dict:
    """Prueba real (23-11-2026): pide el token con la credencial de la empresa y
    lee `/organization` (su propio tenant; permiso `Organization.Read.All`).
    Devuelve qué se ha verificado; nunca el texto de la respuesta remota."""
    cred = credenciales_de_graph(db, org_id)
    if cred is None:
        return {"ok": False, "verificado": "sin_credencial", "origen": None}
    try:
        token = token_de_graph_sync(cred)
    except Exception as exc:  # noqa: BLE001 - se informa la clase, no el texto remoto
        return {"ok": False, "verificado": "nada", "origen": cred["origen"], "error": type(exc).__name__}
    try:
        with httpx.Client(timeout=outbound_http_timeout(db, default=15)) as client:
            resp = client.get(f"{GRAPH_BASE}/organization?$select=id,displayName",
                              headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError as exc:
        return {"ok": False, "verificado": "token", "origen": cred["origen"], "error": type(exc).__name__}
    if resp.status_code != 200:
        return {"ok": False, "verificado": "token", "origen": cred["origen"], "status": resp.status_code}
    org = (resp.json().get("value") or [{}])[0]
    return {"ok": True, "verificado": "token_y_organizacion", "origen": cred["origen"],
            "tenant": org.get("displayName")}


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
        raise error(403, "buzon_de_otra_empresa", detail="Ese buzón no es de un usuario de tu organización")
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
