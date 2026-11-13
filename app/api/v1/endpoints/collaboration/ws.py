"""WebSocket gateway for collaboration realtime events.

Subscribes a connected user to:
  - org:<org_id>             (org-wide broadcasts)
  - workspace:<ws_id>        (workspace updates)
  - user:<user_id>           (personal notifications)
  - conv:<conversation_id>   (joined dynamically per the conversations the user can see)

Auth: same WS ticket scheme used by the rest of the app.

Rate limit: token bucket por usuario sobre eventos *enviados desde* el cliente
(typing, presence, ping). Default 60 eventos / 30 s. Se cierra el socket si
se excede de forma sostenida.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, publicar_contexto_de_tenant
from app.services.ws_service import get_active_user_by_id
from app.api.v1.endpoints.ws import (
    _consume_ws_ticket,
    separar_identidad,
    usuario_en_su_organizacion_activa,
)
from app.services.collaboration._bus import (
    bus, conv_channel, org_channel, user_channel, workspace_channel,
)
from app.services.collaboration.workspaces import (
    get_or_create_workspace, list_conversations_for_user,
)
from app.core.background import spawn
from app.core.async_db import run_db

router = APIRouter(tags=["Collaboration"])
log = logging.getLogger(__name__)


# ── Per-user token bucket ────────────────────────────────────────────────────
class _Bucket:
    __slots__ = ("tokens", "max", "last", "rate")

    def __init__(self, capacity: int = 60, refill_per_second: float = 2.0):
        self.tokens = float(capacity)
        self.max = float(capacity)
        self.last = time.monotonic()
        self.rate = refill_per_second

    def take(self, n: float = 1.0) -> bool:
        now = time.monotonic()
        self.tokens = min(self.max, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False


_buckets: dict[str, _Bucket] = {}


def _bucket_for(user_id: str) -> _Bucket:
    b = _buckets.get(user_id)
    if not b:
        b = _Bucket()
        _buckets[user_id] = b
    return b



# ── Mensajes que envía el cliente ────────────────────────────────────────────
#
# Auditoría 2026-08 (hallazgo 18). `collaboration_ws` eran 176 líneas de
# complejidad 39. La mayor parte estaba en su `consumer()`: una cadena de
# `elif t == ...` sobre el tipo de mensaje, mezclada con el control de caudal y
# la revalidación del usuario.
#
# El despacho por tipo sale aquí, a funciones con nombre y una tabla. Antes no
# había forma de probarlo: el bucle sólo existía dentro del `async def` del
# endpoint, y ningún test abría el socket — el manejo de mensajes del chat en
# tiempo real tenía cobertura CERO. Ahora se prueba con dobles, sin socket.
#
# El estado que comparten los manejadores va en `_ConexionColab`, que también
# encapsula el `resync` porque es un cierre del endpoint (necesita re-suscribir
# el bus, y eso pertenece al ciclo de vida de la conexión, no al mensaje).


async def _msg_ping(ses: "_ConexionColab", payload: dict) -> None:
    """Latido del cliente. Cuenta como un token del caudal, como cualquier otro."""
    await ses.enviar({"type": "pong"})


async def _msg_typing(ses: "_ConexionColab", payload: dict) -> None:
    """«Está escribiendo» en una conversación.

    Sin `conversation_id` no hay canal al que publicarlo, así que se ignora en
    silencio: es un evento decorativo y un cliente mal escrito no debe recibir un
    error por él.

    Auditoría 2026-08: el `conversation_id` llega del cliente y **no se
    comprobaba**. Se publicaba en `conv_channel(cid)` fuera cual fuera, así que
    un usuario podía inyectar un «está escribiendo» a su nombre en la
    conversación de otra organización. No leía nada —la suscripción sí está
    acotada por pertenencia—, pero escribía en un canal ajeno.

    La comprobación se hace contra los canales a los que esta conexión ESTÁ
    suscrita, que el servidor ya calculó en `canales()` a partir de las
    conversaciones del usuario. Es más barato que volver a base en cada pulsación
    de tecla —y esto llega una vez por tecla— y usa la misma fuente de verdad.
    """
    cid = payload.get("conversation_id")
    if not cid:
        return
    canal = conv_channel(cid)
    if canal not in (ses.channels or []):
        log.debug(
            "collab ws: user=%s intento publicar typing en una conversacion a la "
            "que no esta suscrito (%s)", ses.user.id, cid)
        return
    await bus.publish(canal, {
        "type": "typing", "conversation_id": cid,
        "payload": {"user_id": ses.user.id, "active": bool(payload.get("active", True))},
    })


async def _msg_presence(ses: "_ConexionColab", payload: dict) -> None:
    """Cambio de disponibilidad, difundido a toda la organización."""
    status = payload.get("status", "online")
    await bus.publish(org_channel(ses.org), {
        "type": "presence.updated",
        "payload": {"user_id": ses.user.id, "status": status},
    })


async def _msg_resync(ses: "_ConexionColab", payload: dict) -> None:
    """El cliente acaba de crear o unirse a una conversación nueva."""
    await ses.resync()


# Tipo de mensaje → manejador. Añadir un tipo es añadir su función y una línea
# aquí; antes era otra rama más en la cadena de `elif`.
_MENSAJES = {
    "ping": _msg_ping,
    "typing": _msg_typing,
    "presence": _msg_presence,
    "resync": _msg_resync,
}


async def _manejar_mensaje(ses: "_ConexionColab", payload: dict) -> None:
    """Despacha un mensaje del cliente.

    Un tipo desconocido se ignora, como antes: un cliente de una versión más
    nueva puede enviar mensajes que este servidor todavía no entiende, y cerrarle
    la conexión por eso sería peor que no hacer nada. Se registra en debug para
    que deje rastro en lugar de desaparecer.
    """
    manejador = _MENSAJES.get(payload.get("type"))
    if manejador is None:
        log.debug("collab ws: tipo de mensaje no reconocido: %r", payload.get("type"))
        return
    await manejador(ses, payload)


# Resultados posibles del control de caudal, para que el bucle no tenga que
# interpretar un booleano ambiguo.
_CAUDAL_OK = "ok"
_CAUDAL_LIMITADO = "limitado"
_CAUDAL_CERRAR = "cerrar"

# Incumplimientos consecutivos tras los que se cierra la conexión. Un pico
# aislado se avisa; la insistencia se corta.
_MAX_INCUMPLIMIENTOS = 5
# Cada cuantos mensajes del cliente se revalida su acceso, y cada cuanto se
# revalida aunque este inactivo. Un token de WS vale toda la conexion, asi que
# sin esto un usuario desactivado seguiria recibiendo eventos hasta colgar.
_MENSAJES_ENTRE_REVALIDACIONES = 10
_SEGUNDOS_ENTRE_REVALIDACIONES = 30
# Freno tras avisar de exceso de caudal, para que un cliente desbocado no
# consuma el bucle a toda velocidad.
_ESPERA_TRAS_LIMITE = 0.5

# ── La conexión, como objeto ─────────────────────────────────────────────────
#
# Auditoría 2026-08 (hallazgo 18). El endpoint tenía SEIS corrutinas anidadas
# —producer, revalidación, resync, control de caudal, consumer y watchdog— todas
# cerrando sobre `websocket`, `db`, `user`, `sub` y `channels`. 176 líneas,
# complejidad 39.
#
# Los cierres pasan a métodos de esta clase. El estado que compartían es ahora
# estado del objeto, así que se ve declarado en un sitio en lugar de deducirse de
# qué variable captura cada cierre. `sub` y `channels` son mutables a propósito:
# `resync` los reemplaza cuando el usuario entra en una conversación nueva.
#
# Efecto colateral que importa: el manejo de mensajes del chat en tiempo real
# tenía cobertura CERO —sólo existía dentro del `async def` del endpoint y ningún
# test abría el socket—. Como métodos se prueban con dobles, sin socket.


class _ConexionColab:
    """Una conexión de colaboración en curso.

    Reúne lo que las seis corrutinas del endpoint compartían por cierre.
    """

    __slots__ = ("websocket", "db", "user", "ws_obj", "sub", "channels", "cerrojo", "org")

    def __init__(self, websocket, db, user, ws_obj, org=None):
        self.websocket = websocket
        self.db = db
        self.user = user
        self.ws_obj = ws_obj
        # Segunda auditoría 2026-11 (#7): la empresa activa resuelta al abrir.
        # Se guarda aparte porque un `commit` expira `user` y al recargarlo
        # `organization_id` vuelve a ser la de ficha.
        self.org = org or getattr(user, "organization_id", None)
        self.sub = None
        self.channels: list[str] = []
        self.cerrojo = asyncio.Lock()

    async def en_bd(self, fn, *args):
        """`fn(*args)` en el pool de hilos, de una en una por conexion.

        Auditoria 2026-11: `canales()` y la revalidacion consultaban la BD dentro
        del bucle de eventos. En el pool, `watchdog` y `consumer` podrian usar la
        misma sesion desde dos hilos a la vez (no es thread-safe): el cerrojo
        las pone en fila.
        """
        async with self.cerrojo:
            return await run_db(fn, *args)

    # ── Envío ────────────────────────────────────────────────────────────────
    async def enviar(self, obj: dict) -> None:
        await self.websocket.send_text(json.dumps(obj))

    # ── Suscripción al bus ───────────────────────────────────────────────────
    def canales(self) -> list[str]:
        """Canales a los que debe estar suscrito este usuario ahora mismo.

        Se recalcula en cada `resync` porque la lista de conversaciones cambia
        mientras la conexión está abierta.
        """
        if self.db is not None:
            usuario_en_su_organizacion_activa(self.db, self.user, self.org)
        conv_list = list_conversations_for_user(self.db, self.user)
        return [
            org_channel(self.org),
            workspace_channel(self.ws_obj.id),
            user_channel(self.user.id),
        ] + [conv_channel(c["id"]) for c in conv_list]

    async def suscribir(self) -> None:
        self.channels = await self.en_bd(self.canales)
        self.sub = await bus.subscribe(self.channels)

    async def resync(self) -> None:
        """Re-suscribe a las conversaciones actuales del usuario.

        Útil tras crear o unirse a un grupo mientras está conectado. Si el
        conjunto de canales no ha cambiado no se toca la suscripción: cerrarla y
        reabrirla perdería los eventos publicados entre medias.
        """
        nuevos = await self.en_bd(self.canales)
        if set(nuevos) == set(self.channels):
            return
        await self.sub.close()
        self.channels = nuevos
        self.sub = await bus.subscribe(self.channels)
        # `spawn` conserva la referencia: asyncio sólo guarda una débil y el GC
        # podía llevarse este productor a medias (auditoría 2026-08, P2-15).
        spawn(self.producer(), name="collab-ws-producer")

    async def cerrar_suscripcion(self) -> None:
        if self.sub is None:
            return
        try:
            await self.sub.close()
        except Exception:
            log.debug("collab ws: cierre de suscripción best-effort ignorado", exc_info=True)

    # ── Las tres corrutinas de la conexión ───────────────────────────────────
    async def producer(self) -> None:
        """Reenvía al cliente todo lo que llega del bus."""
        async for event in self.sub:
            try:
                await self.websocket.send_text(json.dumps(event, default=str))
            except Exception:
                log.debug("producer: excepcion ignorada", exc_info=True)
                return

    async def usuario_sigue_activo(self) -> bool:
        """Revalida el acceso contra la base.

        Un token de WebSocket es válido durante toda la conexión, así que sin
        esto un usuario desactivado seguiría recibiendo eventos hasta que
        colgase. Se comprueba cada 10 mensajes y, además, cada 30 segundos aunque
        esté inactivo.
        """
        revalidado = await self.en_bd(get_active_user_by_id, self.db, self.user.id)
        if revalidado is not None and revalidado.is_active and self.org:
            # Segunda auditoría 2026-11 (#7): la pertenencia a la empresa activa
            # también se revalida; si se la han retirado, se corta.
            await self.en_bd(usuario_en_su_organizacion_activa, self.db, revalidado, self.org)
            if getattr(revalidado, "organization_id", None) != self.org:
                revalidado = None
        if not revalidado or not revalidado.is_active:
            log.warning("collab ws closing user=%s: access revoked", self.user.id)
            try:
                await self.websocket.close(code=4403)
            except Exception:
                log.debug("usuario_sigue_activo: fallo best-effort ignorado", exc_info=True)
            return False
        return True

    async def controlar_caudal(self, bucket, incumplimientos: int) -> tuple[str, int]:
        """Aplica el control de caudal a un mensaje entrante.

        Devuelve (resultado, incumplimientos) en lugar de un booleano: el bucle
        necesita distinguir «pasa», «avisa y descarta» y «cierra», y con un
        booleano esa tercera decisión quedaba enterrada dentro del control.
        """
        if bucket.take(1.0):
            return _CAUDAL_OK, 0

        incumplimientos += 1
        try:
            await self.enviar({"type": "rate_limited"})
        except Exception:
            log.debug("controlar_caudal: excepcion ignorada", exc_info=True)
            return _CAUDAL_CERRAR, incumplimientos
        if incumplimientos > _MAX_INCUMPLIMIENTOS:
            log.warning(
                "collab ws closing user=%s for sustained rate-limit breaches", self.user.id
            )
            try:
                await self.websocket.close(code=4429)
            except Exception:
                log.debug("collab ws: cierre por rate-limit fallido", exc_info=True)
            return _CAUDAL_CERRAR, incumplimientos
        return _CAUDAL_LIMITADO, incumplimientos

    async def consumer(self) -> None:
        """Bucle de mensajes del cliente."""
        bucket = _bucket_for(self.user.id)
        incumplimientos = 0
        desde_revalidacion = 0
        while True:
            try:
                raw = await self.websocket.receive_text()
            except WebSocketDisconnect:
                return
            try:
                payload = json.loads(raw)
            except Exception:  # noqa: S112 — un mensaje mal formado no cierra la conexión
                log.debug("consumer: excepcion ignorada", exc_info=True)
                continue

            desde_revalidacion += 1
            if desde_revalidacion >= _MENSAJES_ENTRE_REVALIDACIONES:
                if not await self.usuario_sigue_activo():
                    return
                desde_revalidacion = 0

            resultado, incumplimientos = await self.controlar_caudal(bucket, incumplimientos)
            if resultado == _CAUDAL_CERRAR:
                return
            if resultado == _CAUDAL_LIMITADO:
                await asyncio.sleep(_ESPERA_TRAS_LIMITE)
                continue

            await _manejar_mensaje(self, payload)

    async def watchdog(self) -> None:
        """Revalidación periódica incluso si el cliente está inactivo."""
        while True:
            await asyncio.sleep(_SEGUNDOS_ENTRE_REVALIDACIONES)
            if not await self.usuario_sigue_activo():
                return


async def _abrir_conexion(websocket: WebSocket, ticket: Optional[str], db: Session):
    """Autentica el handshake y devuelve la conexión lista, o None si se rechazó.

    Cada rechazo cierra el socket con su propio código para que el cliente pueda
    distinguirlos: 4401 falta o caduca el ticket, 4403 el usuario no puede operar
    en el módulo.
    """
    if not ticket:
        await websocket.close(code=4401)
        return None
    user_id, org_activa = separar_identidad(await _consume_ws_ticket(ticket))
    if not user_id:
        await websocket.close(code=4401)
        return None

    user = await run_db(get_active_user_by_id, db, user_id)
    if not user:
        await websocket.close(code=4403)
        return None
    # Segunda auditoría 2026-11 (#7): la empresa ACTIVA del ticket, no la de ficha.
    await run_db(usuario_en_su_organizacion_activa, db, user, org_activa)

    # Sin organización —por ejemplo un superadmin de plataforma— no hay ámbito de
    # chat. Se cierra con 4403 tras aceptar, en lugar de propagar una
    # HTTPException que el cliente vería como un 500.
    if not getattr(user, "organization_id", None):
        log.info("collab ws: user=%s sin organización — chat no disponible", user_id)
        await websocket.accept()
        await websocket.close(code=4403)
        return None

    # Contexto de tenant en la sesión, a partir de aquí y para toda la conexión.
    #
    # Auditoría 2026-08. Esta sesión es un `SessionLocal()` creado a mano, y
    # `info` estaba vacío durante toda la vida del WebSocket. Con `is_superadmin`
    # ausente, las TRES capas de aislamiento se saltan por la rama de «sesión no
    # inicializada (job de fondo / test)»: `TenantSession.query()`,
    # `TenantSession.execute()` y el escuchador `do_orm_execute`. Es decir, el
    # chat en tiempo real corría con el aislamiento por organización apagado y
    # todo dependía de que cada consulta llevara su filtro explícito.
    #
    # Se pone DESPUÉS de resolver el usuario a propósito: `get_active_user_by_id`
    # busca por id sin saber todavía de qué organización es, así que tiene que
    # correr sin filtrar. A partir de aquí ya se conoce, y se acota.
    publicar_contexto_de_tenant(db, user)
    org_resuelta = user.organization_id

    try:
        ws_obj = await run_db(get_or_create_workspace, db, user)
    except Exception as exc:
        log.warning("collab ws: get_or_create_workspace falló para user=%s: %s", user_id, exc)
        await websocket.accept()
        await websocket.close(code=4403)
        return None

    await websocket.accept()
    conexion = _ConexionColab(websocket, db, user, ws_obj, org=org_resuelta)
    await conexion.suscribir()
    return conexion


async def _correr_conexion(conexion: "_ConexionColab") -> None:
    """Lanza las tres corrutinas y las cancela en cuanto una termina.

    En cuanto cualquiera acaba —el cliente cuelga, se revoca el acceso, hay un
    error— hay que cancelar las otras: sin eso el productor sigue vivo
    consumiendo del bus tras la desconexión, que es una fuga de recursos por cada
    cliente que se va.
    """
    tasks = [
        asyncio.create_task(conexion.producer()),
        asyncio.create_task(conexion.consumer()),
        asyncio.create_task(conexion.watchdog()),
    ]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        # Drenar las excepciones evita el ruido de «Task exception was never
        # retrieved», que enterraba errores reales entre avisos del recolector.
        for t in done:
            exc = t.exception()
            if exc:
                log.debug("collab ws task ended: %s", exc)
        for t in pending:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                log.debug("collab ws: cancelación best-effort ignorada", exc_info=True)
    finally:
        await conexion.cerrar_suscripcion()


@router.websocket("/ws")
async def collaboration_ws(
    websocket: WebSocket,
    ticket: Optional[str] = Query(default=None),
):
    """Puerta de entrada del chat en tiempo real.

    Auditoría 2026-08 (hallazgo 18). Antes eran 176 líneas de complejidad 39 con
    seis corrutinas anidadas cerrando sobre el mismo estado. Ahora el handshake,
    el ciclo de vida y el manejo de mensajes están separados, y esas tres piezas
    se pueden probar por separado — antes no había ninguna forma de hacerlo.
    """
    db: Session = SessionLocal()
    try:
        conexion = await _abrir_conexion(websocket, ticket, db)
        if conexion is None:
            return
        await _correr_conexion(conexion)
    finally:
        db.close()
