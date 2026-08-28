"""Publica la zona horaria del usuario de la petición, como dependencia.

Auditoría 2026-08 (hallazgo P2-14). Quedaban 198 `date.today()` repartidos por
la capa de servicios, y cada uno decidía el borde del día con la zona del
SERVIDOR. El caso que fallaba: un empleado en México (UTC−6) imputa a las 23:30
del día 28; el servidor corre en UTC, donde ya son las 05:30 del 29, así que su
día 28 quedaba vacío y el 29 con horas que no trabajó.

── Por qué una dependencia y no un middleware ────────────────────────────────
La zona correcta es la del usuario autenticado, y en este proyecto la
autenticación vive en una dependencia de FastAPI. Los middlewares de Starlette
corren ANTES de que se resuelvan las dependencias, así que un middleware no tiene
usuario que consultar. Es exactamente el error que hacía que `ABACMiddleware` no
comprobase nada (ver `app/core/abac_dependency.py`): aquí no se repite.

── Por qué `async def`, y no es un detalle de estilo ─────────────────────────
FastAPI ejecuta las dependencias SÍNCRONAS en un hilo del threadpool. Un
`ContextVar` fijado en un hilo trabajador se pierde al volver, así que una
versión `def` de esta función no publicaría nada y el fallo sería SILENCIOSO:
`today()` seguiría devolviendo el día del servidor y todo parecería correcto.
Medido antes de construir nada encima, con las cuatro combinaciones:

    dependencia sync  → endpoint sync    zona NO visible
    dependencia sync  → endpoint async   zona NO visible
    dependencia async → endpoint sync    zona visible
    dependencia async → endpoint async   zona visible
    dependencia async → servicio llamado por el endpoint   zona visible

La última fila es la que importa: el contexto llega hasta las funciones de
servicio profundas, que es donde están los `date.today()`. Hay un test que fija
las cinco filas (`tests/test_timezone_context.py`) para que nadie convierta esta
función en `def` sin que salte algo.

── Tolerante a propósito ─────────────────────────────────────────────────────
Se registra sobre los routers completos, así que también cuelga de rutas
públicas —login, webhooks firmados, health—. Si no hay token válido no lanza
401: deja la zona en UTC, que es el comportamiento anterior. Quien tiene que
rechazar al anónimo es la guarda de cada endpoint, no esta capa. Y cualquier
error resolviendo la zona degrada a UTC en lugar de tumbar la petición: una zona
mal escrita en la ficha de una organización no puede ser una caída.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.timeutil import UTC, set_current_zone, zone_for_user
from app.db.session import get_db

logger = logging.getLogger("contecflow.timezone")

_bearer = HTTPBearer(auto_error=False)


async def bind_request_timezone(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> None:
    """Resuelve `usuario → organización → UTC` y la publica en el contexto.

    DEBE seguir siendo `async def`. Ver la cabecera del módulo: en versión
    síncrona el `ContextVar` se fija en un hilo del threadpool y se pierde, sin
    error visible.

    No se restaura la zona al terminar y es correcto: cada petición se atiende en
    su propia tarea con su propia copia del contexto, así que no hay nada que
    contaminar. Lo que sí necesita restauración son los bloques acotados dentro
    de una misma tarea, y para eso está `using_zone`.
    """
    try:
        token = credentials.credentials if credentials else request.cookies.get("access_token")
        if not token:
            set_current_zone(UTC)
            return

        # Import diferido: `app.core.security` arrastra configuración pesada y
        # esta dependencia se evalúa en cada petición.
        from app.core.security import decode_token

        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            set_current_zone(UTC)
            return

        user_id = payload.get("sub")
        if not user_id:
            set_current_zone(UTC)
            return

        from app.models.user import User

        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            set_current_zone(UTC)
            return

        organization = None
        org_id = getattr(user, "organization_id", None)
        # Sólo se consulta la organización si el usuario no tiene zona propia:
        # la suya manda, así que en ese caso la consulta sería trabajo tirado en
        # cada petición.
        if org_id and not getattr(user, "timezone", None):
            from app.models.mfa import Organization

            organization = db.query(Organization).filter(Organization.id == org_id).first()

        set_current_zone(zone_for_user(user, organization))
    except Exception:  # noqa: BLE001 — degradar, nunca tumbar la petición
        # Una zona mal configurada o un token raro no pueden ser un 500. UTC es
        # el comportamiento anterior, así que degradar no rompe nada.
        logger.warning("No se pudo resolver la zona de la petición; se usa UTC", exc_info=True)
        set_current_zone(UTC)
