"""Aplicación efectiva de la matriz de permisos GRC.

Auditoría 2026-08 (hallazgo 27). Hasta ahora la matriz era una pantalla de
administración que leía y escribía una tabla que NADIE consultaba:
`grc.check_permission()` decía en su docstring "Used by other API endpoints to
enforce GRC" y tenía cero invocaciones. Desmarcar una casilla no cambiaba nada.

Este módulo la conecta al camino de la petición.

── Por qué una dependencia y no un middleware ────────────────────────────────
Misma razón que en `abac_dependency.py`: la autenticación de este proyecto vive
en una dependencia de FastAPI, y las dependencias se resuelven DESPUÉS de los
middlewares de Starlette. Un middleware no tiene usuario autenticado — así murió
`ABACMiddleware`, comprobando un `request.state.user` que nadie poblaba nunca.

── El modelo: denegación aditiva ─────────────────────────────────────────────
Una fila de la matriz sólo puede QUITAR permiso, nunca darlo. Es decir:

  fila con allowed=False  → 403
  fila con allowed=True   → sigue el resto de controles (RBAC, tenant, ABAC)
  sin fila                → sigue el resto de controles

Esta es la decisión de diseño importante y conviene entender por qué:

  · Si el defecto fuera DENEGAR, activar la matriz habría dejado inaccesibles de
    golpe los dominios sin configurar. Un fallo cerrado es lo correcto para el
    AISLAMIENTO entre clientes (y así está `TenantSession`), pero aquí sería
    romper la aplicación para todo el mundo por una tabla incompleta.
  · Si una fila `allowed=True` CONCEDIERA acceso, la matriz podría escalar
    privilegios por encima del RBAC: un administrador de cliente marcando
    `settings/editar` para el rol `employee` se saltaría `require_admin`. La
    matriz restringe; no promueve.

Así que la matriz es un control que se SUMA a los existentes, y la garantía que
ofrece es real y comprobable: lo que un administrador prohíbe, queda prohibido.

── Salvaguardas ──────────────────────────────────────────────────────────────
1. El superadministrador de plataforma nunca queda bloqueado.
2. El propio módulo `grc` no se puede cerrar a los roles que lo administran: si
   no, desmarcar `grc/ver` dejaría la matriz inaccesible y el sistema sin
   posibilidad de arreglarse desde la interfaz. Es la única regla que la matriz
   no puede sobrescribir, y está aquí, a la vista.
3. Los prefijos sin principal `User` (login, portal de cliente, webhooks
   firmados, SCIM, WebSocket) quedan fuera: ver `grc_catalog.is_exempt`.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import HTTPConnection

from app.core.credenciales_opcionales import credenciales_opcionales, es_websocket
from sqlalchemy.orm import Session

from app.core.grc_catalog import action_for, module_for_path
from app.db.session import get_db

logger = logging.getLogger("contecflow.grc.enforce")


# El módulo que administra la propia matriz. Ninguna fila puede cerrar el acceso
# de lectura a los roles que tienen que poder repararla. Ver salvaguarda 2.
_SELF_GOVERNING_MODULE = "grc"
_ROLES_THAT_ADMINISTER_GRC = frozenset({"admin"})


def _resolve_user(request: Request, credentials, db: Session):
    """Usuario autenticado, o None. Tolerante a propósito.

    Esta dependencia cuelga de los routers completos, así que también de rutas
    públicas. Exigir autenticación aquí las rompería: quien rechaza al anónimo es
    la guarda propia de cada endpoint.
    """
    token = credentials.credentials if credentials else request.cookies.get("access_token")
    if not token:
        return None
    from app.core.security import decode_token

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    from app.models.user import User

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if user is not None:
        # La empresa de la sesión (el token la lleva al elegir empresa).
        request.state.grc_org = payload.get("org") or user.organization_id
    return user


def enforce_grc_matrix(
    request: HTTPConnection,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(credenciales_opcionales),
    db: Session = Depends(get_db),
) -> None:
    """Deniega con 403 si la matriz GRC prohíbe (rol, módulo, acción)."""
    if es_websocket(request):
        return  # se autentica con su ticket; ver app/core/credenciales_opcionales.py
    modulo = module_for_path(request.url.path)
    if modulo is None:
        return  # exento o no es una ruta de dominio

    accion = action_for(request.method, request.url.path)
    if accion is None:
        return

    user = _resolve_user(request, credentials, db)
    if user is None:
        return  # sin usuario: la guarda del endpoint decide

    # Salvaguarda 1 — el superadministrador de plataforma nunca se bloquea.
    if getattr(user, "is_superadmin", False):
        return

    rol = user.role.value if hasattr(user.role, "value") else str(user.role or "")

    # Salvaguarda 2 — la matriz no puede cerrarse a sí misma.
    if modulo == _SELF_GOVERNING_MODULE and rol in _ROLES_THAT_ADMINISTER_GRC:
        return

    from app.services import grc_service

    try:
        fila = grc_service.get_role_permission(db, rol, modulo, accion,
                                               getattr(request.state, "grc_org", None) or user.organization_id)
    except Exception:
        # Un fallo al leer la matriz NO debe abrir ni cerrar la aplicación: los
        # controles reales (RBAC, aislamiento de tenant) siguen en pie, y este es
        # un control aditivo. Se registra en warning para que sea visible.
        logger.warning(
            "GRC: no se pudo leer la matriz para %s/%s/%s", rol, modulo, accion, exc_info=True
        )
        return

    if fila is not None and fila.allowed is False:
        logger.info(
            "GRC denegó %s %s para rol=%s (módulo=%s acción=%s)",
            request.method, request.url.path, rol, modulo, accion,
        )
        raise HTTPException(
            status_code=403,
            detail=(
                f"La política de gobierno de tu organización no permite "
                f"'{accion}' en el módulo '{modulo}' para el rol '{rol}'."
            ),
        )
