"""El manejo de mensajes del chat en tiempo real, probado por primera vez.

Auditoría 2026-08 (P3-18). `collaboration_ws` eran 176 líneas de complejidad 39
con SEIS corrutinas anidadas —producer, revalidación, resync, control de caudal,
consumer y watchdog— todas cerrando sobre `websocket`, `db`, `user`, `sub` y
`channels`.

Eso tenía un coste que no era estético: **el manejo de mensajes tenía cobertura
cero**. Sólo existía dentro del `async def` del endpoint, y ningún test abría el
socket. Cada rama del despacho de tipos, el control de caudal y la revalidación
del acceso eran código en producción que nadie había ejecutado en una prueba.

Ahora esas piezas son métodos de `_ConexionColab` y funciones de módulo, así que
se prueban con dobles: sin socket, sin bus real y sin base de datos.

Lo que se fija aquí es el comportamiento que había ANTES del refactor, leído del
original: un tipo desconocido se ignora, un `typing` sin conversación se ignora,
el exceso de caudal avisa y sólo cierra al insistir, y el acceso se revalida.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.api.v1.endpoints.collaboration import ws as modulo


# ── Dobles ────────────────────────────────────────────────────────────────────

class _WebSocketFalso:
    """Registra lo enviado y el código de cierre, sin red."""

    def __init__(self, entrantes=None):
        self.enviados: list[dict] = []
        self.codigo_cierre = None
        self.aceptado = False
        self._entrantes = list(entrantes or [])

    async def accept(self):
        self.aceptado = True

    async def send_text(self, texto):
        self.enviados.append(json.loads(texto))

    async def close(self, code=1000):
        self.codigo_cierre = code

    async def receive_text(self):
        if not self._entrantes:
            raise modulo.WebSocketDisconnect()
        return self._entrantes.pop(0)


class _UsuarioFalso:
    def __init__(self, uid="u1", org="o1", activo=True):
        self.id = uid
        self.organization_id = org
        self.is_active = activo


class _BusFalso:
    def __init__(self):
        self.publicado: list[tuple[str, dict]] = []

    async def publish(self, canal, evento):
        self.publicado.append((canal, evento))


class _CubetaFalsa:
    """Deja pasar los primeros `permitidos` mensajes y luego rechaza siempre."""

    def __init__(self, permitidos=0):
        self.restantes = permitidos

    def take(self, _n):
        if self.restantes > 0:
            self.restantes -= 1
            return True
        return False


class _SesionFalsa:
    """Lo minimo de una sesion de SQLAlchemy que usa el handshake.

    `info` existe porque `_abrir_conexion` publica ahi el contexto de tenant en
    cuanto resuelve al usuario (auditoria 2026-08): la sesion del WebSocket se
    crea a mano y antes se quedaba sin contexto durante toda la conexion, con lo
    que las tres capas de aislamiento se saltaban.
    """

    def __init__(self):
        self.info: dict = {}

    def close(self) -> None:
        pass


def _conexion(websocket=None, usuario=None, conversaciones=()):
    """Conexión con la base y el workspace a None: los mensajes no los usan.

    `conversaciones` son los ids a los que la conexión está suscrita. Importa
    desde la auditoría 2026-08: `_msg_typing` sólo publica en una conversación
    a la que esta conexión esté suscrita, y antes publicaba en cualquiera.
    """
    con = modulo._ConexionColab(
        websocket or _WebSocketFalso(),
        db=None,
        user=usuario or _UsuarioFalso(),
        ws_obj=None,
    )
    con.channels = [modulo.conv_channel(c) for c in conversaciones]
    return con


@pytest.fixture
def bus_falso(monkeypatch):
    falso = _BusFalso()
    monkeypatch.setattr(modulo, "bus", falso)
    return falso


# ── Que la estructura sigue siendo la que se probó ─────────────────────────────

def test_la_tabla_de_mensajes_cubre_los_cuatro_tipos_del_cliente():
    """El cliente sólo envía estos cuatro. Si alguien añade un tipo sin registrar
    su función, el mensaje se ignoraría en silencio y la interfaz parecería
    funcionar."""
    assert set(modulo._MENSAJES) == {"ping", "typing", "presence", "resync"}


def test_el_endpoint_ya_no_es_una_funcion_gigante():
    """El handshake, el ciclo de vida y el despacho son piezas separadas.

    Sin esto, el refactor se puede deshacer sin que nada se queje.
    """
    for nombre in ("_abrir_conexion", "_correr_conexion", "_manejar_mensaje"):
        assert hasattr(modulo, nombre), f"falta {nombre}"
    for metodo in ("producer", "consumer", "watchdog", "resync",
                   "usuario_sigue_activo", "controlar_caudal"):
        assert hasattr(modulo._ConexionColab, metodo), f"falta el método {metodo}"


# ── Despacho por tipo ─────────────────────────────────────────────────────────

def test_ping_responde_pong():
    ws = _WebSocketFalso()
    asyncio.run(modulo._manejar_mensaje(_conexion(ws), {"type": "ping"}))
    assert ws.enviados == [{"type": "pong"}]


def test_typing_se_publica_en_el_canal_de_la_conversacion(bus_falso):
    con = _conexion(usuario=_UsuarioFalso("u7"), conversaciones=["c9"])
    asyncio.run(modulo._manejar_mensaje(
        con, {"type": "typing", "conversation_id": "c9", "active": True}
    ))
    assert len(bus_falso.publicado) == 1
    canal, evento = bus_falso.publicado[0]
    assert canal == modulo.conv_channel("c9")
    assert evento["type"] == "typing"
    assert evento["payload"] == {"user_id": "u7", "active": True}


def test_typing_sin_conversacion_se_ignora(bus_falso):
    """No hay canal al que publicarlo. Es un evento decorativo, así que un cliente
    mal escrito no debe recibir un error por él."""
    asyncio.run(modulo._manejar_mensaje(_conexion(), {"type": "typing"}))
    assert bus_falso.publicado == []


def test_typing_sin_active_se_asume_activo(bus_falso):
    asyncio.run(modulo._manejar_mensaje(
        _conexion(conversaciones=["c1"]), {"type": "typing", "conversation_id": "c1"}
    ))
    assert bus_falso.publicado[0][1]["payload"]["active"] is True


def test_EL_HALLAZGO_typing_en_una_conversacion_ajena_no_se_publica(bus_falso):
    """Auditoría 2026-08. El `conversation_id` llega del cliente y no se
    comprobaba: se publicaba en `conv_channel(cid)` fuera cual fuera, así que un
    usuario podía inyectar un «está escribiendo» a su nombre en la conversación
    de otra organización.

    La comprobación es contra los canales a los que la conexión está suscrita,
    que el servidor calcula en `canales()` desde las conversaciones del usuario.
    """
    con = _conexion(usuario=_UsuarioFalso("intruso"), conversaciones=["la-mia"])
    asyncio.run(modulo._manejar_mensaje(
        con, {"type": "typing", "conversation_id": "la-de-otra-organizacion"}
    ))
    assert bus_falso.publicado == [], (
        "se publicó un evento en una conversación a la que esta conexión no "
        "está suscrita")


def test_presence_se_difunde_a_toda_la_organizacion(bus_falso):
    con = _conexion(usuario=_UsuarioFalso("u3", org="org42"))
    asyncio.run(modulo._manejar_mensaje(con, {"type": "presence", "status": "away"}))
    canal, evento = bus_falso.publicado[0]
    assert canal == modulo.org_channel("org42")
    assert evento["payload"] == {"user_id": "u3", "status": "away"}


def test_presence_sin_status_se_asume_online(bus_falso):
    asyncio.run(modulo._manejar_mensaje(_conexion(), {"type": "presence"}))
    assert bus_falso.publicado[0][1]["payload"]["status"] == "online"


def test_resync_delega_en_la_conexion():
    """Se subclasea en vez de sustituir el método en la instancia porque
    `_ConexionColab` define `__slots__`: no acepta atributos nuevos, que es
    justamente lo que se quiere de una clase con estado acotado."""
    llamado = []

    class _ConSpy(modulo._ConexionColab):
        async def resync(self):
            llamado.append(True)

    con = _ConSpy(_WebSocketFalso(), db=None, user=_UsuarioFalso(), ws_obj=None)
    asyncio.run(modulo._manejar_mensaje(con, {"type": "resync"}))
    assert llamado == [True]


def test_un_tipo_desconocido_se_ignora_sin_lanzar(bus_falso):
    """Un cliente de una versión más nueva puede enviar tipos que este servidor
    todavía no entiende. Cerrarle la conexión por eso sería peor que no hacer
    nada — es el comportamiento que ya tenía la cadena de `elif`."""
    ws = _WebSocketFalso()
    asyncio.run(modulo._manejar_mensaje(_conexion(ws), {"type": "inventado_v9"}))
    assert ws.enviados == []
    assert bus_falso.publicado == []
    assert ws.codigo_cierre is None


def test_un_mensaje_sin_tipo_se_ignora():
    ws = _WebSocketFalso()
    asyncio.run(modulo._manejar_mensaje(_conexion(ws), {}))
    assert ws.enviados == []


# ── Control de caudal ─────────────────────────────────────────────────────────

def test_el_caudal_deja_pasar_y_reinicia_el_contador():
    con = _conexion()
    resultado, incumplimientos = asyncio.run(
        con.controlar_caudal(_CubetaFalsa(permitidos=1), incumplimientos=3)
    )
    assert resultado == modulo._CAUDAL_OK
    assert incumplimientos == 0, "un mensaje que pasa debe borrar el historial"


def test_el_primer_exceso_avisa_pero_no_cierra():
    ws = _WebSocketFalso()
    con = _conexion(ws)
    resultado, incumplimientos = asyncio.run(
        con.controlar_caudal(_CubetaFalsa(permitidos=0), incumplimientos=0)
    )
    assert resultado == modulo._CAUDAL_LIMITADO
    assert incumplimientos == 1
    assert ws.enviados == [{"type": "rate_limited"}]
    assert ws.codigo_cierre is None, "un pico aislado no debe cortar la conexión"


def test_el_exceso_sostenido_cierra_con_4429():
    ws = _WebSocketFalso()
    con = _conexion(ws)
    resultado, _ = asyncio.run(
        con.controlar_caudal(
            _CubetaFalsa(permitidos=0), incumplimientos=modulo._MAX_INCUMPLIMIENTOS
        )
    )
    assert resultado == modulo._CAUDAL_CERRAR
    assert ws.codigo_cierre == 4429


def test_si_el_aviso_no_se_puede_enviar_se_cierra():
    """El socket ya está roto: seguir el bucle sólo gastaría vueltas."""
    class _WSRoto(_WebSocketFalso):
        async def send_text(self, texto):
            raise ConnectionError("socket cerrado")

    con = _conexion(_WSRoto())
    resultado, _ = asyncio.run(
        con.controlar_caudal(_CubetaFalsa(permitidos=0), incumplimientos=0)
    )
    assert resultado == modulo._CAUDAL_CERRAR


# ── Revalidación del acceso ───────────────────────────────────────────────────

def test_un_usuario_desactivado_cierra_la_conexion_con_4403(monkeypatch):
    """Un token de WebSocket vale toda la conexión, así que sin esta revalidación
    un usuario desactivado seguiría recibiendo eventos hasta colgar."""
    monkeypatch.setattr(modulo, "get_active_user_by_id",
                        lambda db, uid: _UsuarioFalso(uid, activo=False))
    ws = _WebSocketFalso()
    assert asyncio.run(_conexion(ws).usuario_sigue_activo()) is False
    assert ws.codigo_cierre == 4403


def test_un_usuario_borrado_tambien_cierra(monkeypatch):
    monkeypatch.setattr(modulo, "get_active_user_by_id", lambda db, uid: None)
    ws = _WebSocketFalso()
    assert asyncio.run(_conexion(ws).usuario_sigue_activo()) is False
    assert ws.codigo_cierre == 4403


def test_un_usuario_activo_no_cierra_nada(monkeypatch):
    monkeypatch.setattr(modulo, "get_active_user_by_id",
                        lambda db, uid: _UsuarioFalso(uid, activo=True))
    ws = _WebSocketFalso()
    assert asyncio.run(_conexion(ws).usuario_sigue_activo()) is True
    assert ws.codigo_cierre is None


# ── Handshake ─────────────────────────────────────────────────────────────────

def test_sin_ticket_se_cierra_con_4401():
    ws = _WebSocketFalso()
    assert asyncio.run(modulo._abrir_conexion(ws, None, db=None)) is None
    assert ws.codigo_cierre == 4401
    assert not ws.aceptado, "no se acepta un handshake sin credencial"


def test_un_ticket_invalido_se_cierra_con_4401(monkeypatch):
    async def _consumir(_t):
        return None

    monkeypatch.setattr(modulo, "_consume_ws_ticket", _consumir)
    ws = _WebSocketFalso()
    assert asyncio.run(modulo._abrir_conexion(ws, "malo", db=None)) is None
    assert ws.codigo_cierre == 4401


def test_un_usuario_sin_organizacion_se_cierra_con_4403(monkeypatch):
    """Es el caso del superadmin de plataforma: no tiene ámbito de chat. Se cierra
    limpiamente en lugar de propagar una excepción que el cliente vería como 500.
    """
    async def _consumir(_t):
        return "u1"

    monkeypatch.setattr(modulo, "_consume_ws_ticket", _consumir)
    monkeypatch.setattr(modulo, "get_active_user_by_id",
                        lambda db, uid: _UsuarioFalso(uid, org=None))
    ws = _WebSocketFalso()
    assert asyncio.run(modulo._abrir_conexion(ws, "ok", db=_SesionFalsa())) is None
    assert ws.codigo_cierre == 4403


def test_si_falla_el_workspace_se_cierra_con_4403(monkeypatch):
    async def _consumir(_t):
        return "u1"

    def _revienta(db, user):
        raise RuntimeError("workspace no disponible")

    monkeypatch.setattr(modulo, "_consume_ws_ticket", _consumir)
    monkeypatch.setattr(modulo, "get_active_user_by_id", lambda db, uid: _UsuarioFalso(uid))
    monkeypatch.setattr(modulo, "get_or_create_workspace", _revienta)
    ws = _WebSocketFalso()
    assert asyncio.run(modulo._abrir_conexion(ws, "ok", db=_SesionFalsa())) is None
    assert ws.codigo_cierre == 4403


# ── Re-suscripción ────────────────────────────────────────────────────────────

def test_resync_no_toca_la_suscripcion_si_los_canales_no_cambian():
    """Cerrarla y reabrirla perdería los eventos publicados entre medias."""
    class _SubFalsa:
        def __init__(self):
            self.cerrada = False

        async def close(self):
            self.cerrada = True

    class _ConCanalesFijos(modulo._ConexionColab):
        def canales(self):
            return ["b", "a"]  # mismo conjunto que `channels`, otro orden

    con = _ConCanalesFijos(_WebSocketFalso(), db=None, user=_UsuarioFalso(), ws_obj=None)
    con.sub = _SubFalsa()
    con.channels = ["a", "b"]
    asyncio.run(con.resync())
    assert con.sub.cerrada is False, "el orden no es un cambio de canales"
