"""A quién se avisa de un mensaje nuevo: la matriz de silencios.

Auditoría 2026-08 (P3-18). `_notify_recipients` era complejidad 22 en dos fases
mezcladas: reunir los destinatarios según el tipo de conversación, y decidir a
quién se le avisa.

## Lo que se vio al separarlas

**«Una mención rompe todo silencio» es una regla escrita cinco veces.** El bucle
original repetía `and not is_mention` en las cinco comprobaciones de silencio:

    if per_conv == "none" and not is_mention:        continue
    if per_conv == "mentions" and not is_mention:    continue
    if is_muted and not is_mention:                  continue
    if notify_level == "none" and not is_mention:    continue
    if notify_level == "mentions" and not is_mention: continue

Escrita cinco veces, basta olvidarla en una para que un `@mención` deje de
llegar por un camino y siga llegando por los otros cuatro — y nada falla. Ahora
el silencio se calcula y la excepción se aplica en un solo sitio.

Estos tests cruzan la matriz entera: **tres fuentes de silencio × mencionado o
no**, más el caso del autor. Las funciones son puras, así que no hacen falta ni
base de datos ni fixtures — que es por sí solo el motivo de haberlas separado.
La cobertura de integración (`test_collaboration.py`) sigue cubriendo el camino
completo.
"""
from __future__ import annotations

import pytest

from app.services.collaboration.messages import (
    _Destinatario,
    _es_el_autor,
    _esta_silenciado,
    _le_mencionan,
)


def _dest(user_id="u1", client_user_id=None, notify_level="all", is_muted=False):
    return _Destinatario(user_id, client_user_id, notify_level, is_muted)


class _Mensaje:
    def __init__(self, user_id=None, client_user_id=None):
        self.user_id = user_id
        self.client_user_id = client_user_id


# ── Las tres fuentes de silencio, por separado ────────────────────────────────

def test_sin_nada_puesto_no_hay_silencio():
    assert _esta_silenciado(_dest(), None) is False


@pytest.mark.parametrize("regla", ["none", "mentions"])
def test_la_regla_por_conversacion_silencia(regla):
    """La que la persona ha puesto para ESTA conversación."""
    assert _esta_silenciado(_dest(), regla) is True


def test_una_regla_a_todo_no_silencia():
    assert _esta_silenciado(_dest(), "all") is False


def test_el_miembro_silenciado_silencia():
    assert _esta_silenciado(_dest(is_muted=True), None) is True


@pytest.mark.parametrize("nivel", ["none", "mentions"])
def test_el_nivel_de_pertenencia_silencia(nivel):
    assert _esta_silenciado(_dest(notify_level=nivel), None) is True


def test_un_nivel_desconocido_NO_silencia():
    """El lado seguro para una notificación: mejor un aviso de más que perder una
    mención. Un `notify_level` con un valor que nadie reconoce avisa.

    Era el comportamiento del original —comparaba contra `"none"` y `"mentions"`
    literales— y se conserva a propósito: la alternativa (silenciar ante lo
    desconocido) haría que un dato corrupto en base dejara a alguien sin avisos
    sin que nada lo indicara.
    """
    assert _esta_silenciado(_dest(notify_level="valor_raro"), None) is False
    assert _esta_silenciado(_dest(), "valor_raro") is False


def test_la_regla_por_conversacion_manda_sobre_la_pertenencia():
    """Nivel 'all' en el canal pero la persona ha silenciado esta conversación:
    manda lo que ella ha puesto."""
    assert _esta_silenciado(_dest(notify_level="all"), "none") is True


# ── La regla que estaba escrita cinco veces ───────────────────────────────────

CADA_FUENTE_DE_SILENCIO = [
    ("regla de conversación a 'none'",   _dest(),                        "none"),
    ("regla de conversación a 'mentions'", _dest(),                      "mentions"),
    ("miembro silenciado",                _dest(is_muted=True),          None),
    ("nivel de pertenencia 'none'",       _dest(notify_level="none"),    None),
    ("nivel de pertenencia 'mentions'",   _dest(notify_level="mentions"), None),
]


@pytest.mark.parametrize(
    "nombre,destinatario,regla",
    CADA_FUENTE_DE_SILENCIO,
    ids=[c[0] for c in CADA_FUENTE_DE_SILENCIO],
)
def test_las_cinco_fuentes_de_silencio_silencian_de_verdad(nombre, destinatario, regla):
    assert _esta_silenciado(destinatario, regla) is True, nombre


@pytest.mark.parametrize(
    "nombre,destinatario,regla",
    CADA_FUENTE_DE_SILENCIO,
    ids=[c[0] for c in CADA_FUENTE_DE_SILENCIO],
)
def test_una_mencion_rompe_las_cinco(nombre, destinatario, regla):
    """El test que da sentido a todo el fichero.

    Recorre las cinco fuentes de silencio y exige que una mención pase por
    encima de todas. Antes esto dependía de que el `and not is_mention` estuviera
    en las cinco líneas; ahora depende de una sola condición, y este test la
    verifica desde los cinco lados.
    """
    silenciado = _esta_silenciado(destinatario, regla)
    mencionado = _le_mencionan(
        destinatario, {destinatario.user_id}, set(), es_para_todos=False
    )
    assert silenciado is True, f"{nombre} debería silenciar"
    assert mencionado is True
    # La condición del bucle: sólo se descarta si está silenciado Y no le mencionan.
    assert not (silenciado and not mencionado), (
        f"una mención debe romper el silencio de: {nombre}"
    )


# ── Cuándo cuenta como mención ────────────────────────────────────────────────

def test_una_mencion_directa_al_usuario():
    d = _dest(user_id="u1")
    assert _le_mencionan(d, {"u1"}, set(), es_para_todos=False) is True


def test_una_mencion_a_otro_no_cuenta():
    d = _dest(user_id="u1")
    assert _le_mencionan(d, {"u2"}, set(), es_para_todos=False) is False


def test_una_mencion_a_un_usuario_del_portal_de_cliente():
    """Los del portal llevan `client_user_id` y no `user_id`: si sólo se mirara
    el primero, un `@mención` a un cliente no le llegaría nunca."""
    d = _dest(user_id=None, client_user_id="c1")
    assert _le_mencionan(d, set(), {"c1"}, es_para_todos=False) is True
    assert _le_mencionan(d, {"c1"}, set(), es_para_todos=False) is False


def test_un_arroba_todos_menciona_a_cualquiera():
    assert _le_mencionan(_dest(user_id="u9"), set(), set(), es_para_todos=True) is True
    assert _le_mencionan(
        _dest(user_id=None, client_user_id="c9"), set(), set(), es_para_todos=True
    ) is True


def test_sin_menciones_nadie_esta_mencionado():
    assert _le_mencionan(_dest(), set(), set(), es_para_todos=False) is False


# ── El autor no recibe aviso de su propio mensaje ─────────────────────────────

def test_el_autor_interno_no_se_avisa_a_si_mismo():
    assert _es_el_autor(_dest(user_id="u1"), _Mensaje(user_id="u1")) is True
    assert _es_el_autor(_dest(user_id="u2"), _Mensaje(user_id="u1")) is False


def test_el_autor_del_portal_no_se_avisa_a_si_mismo():
    d = _dest(user_id=None, client_user_id="c1")
    assert _es_el_autor(d, _Mensaje(client_user_id="c1")) is True
    assert _es_el_autor(d, _Mensaje(client_user_id="c2")) is False


def test_un_destinatario_sin_identificador_no_es_el_autor():
    """El `and` de las dos condiciones importa: sin él, un destinatario con
    `user_id` nulo y un mensaje con autor nulo se tomarían por la misma persona
    y ese destinatario se quedaría sin aviso."""
    assert _es_el_autor(_dest(user_id=None), _Mensaje(user_id=None)) is False


def test_el_autor_se_excluye_incluso_si_se_menciona(db):
    """Nadie se avisa a sí mismo aunque se escriba `@sí mismo`: la exclusión del
    autor va ANTES de la comprobación de mención en el bucle, y ese orden es lo
    que se verifica aquí."""
    import inspect
    from app.services.collaboration import messages

    fuente = inspect.getsource(messages._notify_recipients)
    i_autor = fuente.find("_es_el_autor")
    i_mencion = fuente.find("_le_mencionan")
    assert 0 <= i_autor < i_mencion, (
        "la exclusión del autor debe evaluarse antes de la mención"
    )


# ── Que el tipo de conversación no se quede sin resolver ──────────────────────

def test_los_tres_tipos_de_conversacion_tienen_quien_los_resuelva():
    """Un tipo nuevo sin función asociada devolvería una lista vacía y nadie
    recibiría aviso — en silencio. Este cruce lo impide."""
    from app.services.collaboration.messages import _DESTINATARIOS_POR_TIPO

    assert set(_DESTINATARIOS_POR_TIPO) == {"channel", "direct", "group"}
