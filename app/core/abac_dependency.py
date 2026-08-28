"""Aplicación de ABAC por ruta, como dependencia de FastAPI.

Auditoría 2026-08 (hallazgos P1-5 y P1-25). Sustituye a `ABACMiddleware`, que
declaraba hacer esto y no hacía nada.

── Por qué el middleware no podía funcionar y esto sí ────────────────────────
`ABACMiddleware` leía `request.state.user` y se saltaba la comprobación cuando
era None. Nadie poblaba ese atributo nunca, porque la autenticación de este
proyecto vive en una dependencia de FastAPI (`app/core/deps.py`) y las
dependencias se resuelven DESPUÉS de los middlewares de Starlette. El resultado
eran 110 prefijos declarados como cubiertos por ABAC y comprobados cero veces.

Una dependencia no tiene ese problema: corre en la misma fase que
`get_current_user`, así que el usuario autenticado está disponible por
construcción. Es el mecanismo del framework para esto.

── Por qué una dependencia global y no 261 llamadas ──────────────────────────
Los 45 prefijos que declaraban cobertura sin tenerla suman 261 rutas en 33
ficheros. Añadir `enforce_abac(...)` a mano en cada una habría multiplicado por
261 la ocasión de olvidarse y habría dejado la cobertura otra vez dependiendo de
la disciplina de quien escribe el endpoint. Registrando esta dependencia una vez
sobre los routers v1 y v2, el mapa `ABAC_COVERED_PREFIXES` vuelve a ser
configuración de verdad: añadir un prefijo al mapa basta para que se aplique.

Las llamadas explícitas a `enforce_abac()` que ya existen en 233 endpoints se
mantienen y no molestan: pasan el `resource_id` concreto, que esta dependencia no
puede conocer, así que aportan grano más fino. La doble evaluación es inocua
—misma comprobación, idempotente— y el early-out de `enforce_abac` (una consulta
barata cuando la organización no tiene políticas activas, el caso por defecto)
evita que cueste algo en la práctica.

── Semántica ─────────────────────────────────────────────────────────────────
Sigue siendo FAIL-OPEN, igual que `enforce_abac`: sin políticas ABAC activas no
restringe nada. Esta dependencia NO es un control de autorización y no sustituye
al filtro de tenant (estructural, fail-closed) ni al RBAC. Lo que arregla es que
una política que un cliente define de verdad se aplique donde el mapa dice que se
aplica.

Sobre `action`: informativo, como antes. `enforce_abac()` no lo pasa a
`evaluate_access()`; solo alimenta log y métrica. El mapa lo conserva para no
perder la intención declarada.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.abac_registry import ABAC_COVERED_PREFIXES
from app.db.session import get_db

logger = logging.getLogger("contecflow.abac.dependency")

_bearer = HTTPBearer(auto_error=False)


def _resolve_coverage(path: str) -> Optional[tuple[str, str]]:
    """(resource_type, action) del prefijo más específico que matchee, o None."""
    best: Optional[tuple[str, str]] = None
    best_len = -1
    for prefix, entry in ABAC_COVERED_PREFIXES.items():
        if path == prefix or path.startswith(prefix + "/"):
            if len(prefix) > best_len:
                best, best_len = entry, len(prefix)
    return best


def apply_abac_for_route(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> None:
    """Aplica las políticas ABAC del prefijo de esta ruta, si hay usuario.

    Resuelve el usuario de forma TOLERANTE a propósito: si no hay token válido no
    lanza 401, simplemente no aplica ABAC. Esta dependencia se registra sobre los
    routers completos, así que también cuelga de rutas públicas por diseño —
    login, webhooks firmados con HMAC, health—. Exigir autenticación aquí las
    rompería. Quien tiene que rechazar al anónimo es la guarda propia de cada
    endpoint (`get_current_user`), no esta capa.
    """
    coverage = _resolve_coverage(request.url.path)
    if coverage is None:
        return

    token = credentials.credentials if credentials else request.cookies.get("access_token")
    if not token:
        return

    # Import diferido: app.core.security importa configuración pesada y esta
    # dependencia se evalúa en cada request.
    from app.core.security import decode_token

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return

    user_id = payload.get("sub")
    if not user_id:
        return

    from app.models.user import User

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if user is None:
        return

    resource_type, action = coverage
    enforce_abac(db, user, resource_type, resource_id=None, action=action)
