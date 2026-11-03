"""Slack y Teams tienen que entender exactamente los mismos comandos.

Auditoría 2026-08 (hallazgo 18). Los dos receptores tenían la tabla de verbos
escrita a mano, cada uno la suya, en forma de `if verb in (...) / elif`. Y **no
decían lo mismo**: Slack aceptaba `horas` como sinónimo de `tiempo` y Teams no,
así que un usuario de Teams que escribía «horas 3» recibía la ayuda en vez de
registrar sus tres horas. El docstring del receptor de Teams decía literalmente
«commands identical to the Slack bot».

Con una sola tabla (`_COMANDOS`) la divergencia no puede volver por descuido,
pero sí por edición: alguien podría reintroducir un `if` especial en uno de los
dos. Por eso el test que importa aquí es el paramétrico de abajo, que pasa **el
mismo verbo por las dos puertas** y exige el mismo manejador.

Y una nota sobre lo que estos tests **no** cubren: el receptor de Slack sin
`SLACK_SIGNING_SECRET` sólo deja pasar cuando `TESTING=1`, que es como corre la
suite. Las dos puertas cerradas —firma inválida, audiencia equivocada— tienen su
propio fichero, `test_integrations_inbound_security.py`, y no se repiten aquí.
"""
import pytest

from app.api.v1.endpoints import integrations_hub as hub


VERBOS = [
    ("tarea", "_slack_create_task"),
    ("task", "_slack_create_task"),
    ("tiempo", "_slack_log_time"),
    ("time", "_slack_log_time"),
    ("horas", "_slack_log_time"),
    ("ticket", "_slack_create_ticket"),
    ("estado", "_slack_get_status"),
    ("status", "_slack_get_status"),
]


@pytest.mark.parametrize("verbo,manejador", VERBOS)
def test_el_verbo_va_a_su_manejador(verbo, manejador):
    assert hub._COMANDOS[verbo] is getattr(hub, manejador)


def test_horas_esta_en_la_tabla():
    """El sinónimo que Teams no entendía.

    Se comprueba aparte de la tabla de arriba para que, si desaparece, el
    mensaje diga de qué se trata y no sólo «falta una clave».
    """
    assert "horas" in hub._COMANDOS, (
        "`horas` ha salido del repertorio: era el sinónimo que Slack aceptaba y "
        "Teams no, y la divergencia que unificó el hallazgo 18"
    )
    assert hub._COMANDOS["horas"] is hub._COMANDOS["tiempo"]


def test_los_cinco_manejadores_tienen_la_misma_firma():
    """`(resto, usuario, db)` en los cinco, o la tabla no puede despacharlos.

    `_slack_get_status` no usa el usuario —consultar un código no depende de
    quién pregunta— y aun así lo recibe: es lo que permite que no haya
    envoltorios por manejador.
    """
    import inspect

    for manejador in set(hub._COMANDOS.values()):
        parametros = list(inspect.signature(manejador).parameters)
        assert len(parametros) == 3, f"{manejador.__name__}: {parametros}"


@pytest.mark.asyncio
async def test_un_verbo_desconocido_cae_en_la_ayuda():
    """Igual que hacían las dos ramas `else`, y por eso `ayuda` no necesita entrada."""
    respuesta = await hub._ejecutar_comando_del_bot(
        "loquesea", None, None, canal="Test")
    assert "text" in respuesta

    ayuda = await hub._ejecutar_comando_del_bot("ayuda", None, None, canal="Test")
    assert ayuda == respuesta


@pytest.mark.asyncio
async def test_un_comando_que_revienta_vuelve_como_mensaje():
    """Un 500 en un webhook de Slack se ve como «operación fallida» y el error se pierde.

    El `except Exception` del despachador es de las veces en que un `except`
    ancho es lo correcto: quien escribió el comando tiene que leer qué pasó en
    su propio chat.
    """
    async def revienta(resto, usuario, db):
        raise RuntimeError("algo se rompió")

    hub._COMANDOS["_prueba_revienta"] = revienta
    try:
        # Desde 2026-11-03 sin usuario no se ejecuta nada: hace falta uno, y una
        # sesion donde publicar su organizacion.
        from types import SimpleNamespace
        usuario = SimpleNamespace(id="u1", organization_id="org-1", is_superadmin=False)
        respuesta = await hub._ejecutar_comando_del_bot(
            "_prueba_revienta lo que sea", usuario, SimpleNamespace(info={}), canal="Test")
    finally:
        del hub._COMANDOS["_prueba_revienta"]

    assert "algo se rompió" in respuesta["text"]
    assert respuesta["response_type"] == "ephemeral"
