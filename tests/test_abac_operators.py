"""Los 15 operadores de condición ABAC, uno por uno.

Auditoría 2026-08 (P3-18). `evaluate_condition` eran 89 líneas de complejidad 26
con los operadores en una cadena de `elif`. Es la función que decide si una
política ABAC se cumple, así que **decide accesos**.

Ahora cada operador es una función y `_OPERADORES` la tabla. La equivalencia se
verificó cruzando los 17 operadores (los 15 reales, uno inexistente y la ausencia
del campo) por 17 juegos de valores —cadenas, listas, números, `None`, tipos
incompatibles y una regex mal formada—: **289 combinaciones, resultado idéntico**.

Estos tests fijan las decisiones que no son obvias y que un refactor podría
cambiar sin que se note: la asimetría entre `in` y `not_in` sobre listas, la
insensibilidad a mayúsculas de `contains` sólo en cadenas, y el trato de `None`.
"""
from __future__ import annotations

import pytest

from app.services.abac import ABACEngine


def _evaluar(valor, operador, esperado):
    regla = {"attribute": "x", "value": esperado}
    if operador is not None:
        regla["operator"] = operador
    return ABACEngine.evaluate_condition(valor, regla)


# ── La tabla ──────────────────────────────────────────────────────────────────

def test_la_tabla_cubre_los_quince_operadores():
    """Un operador que se ofrezca en el panel de políticas y no esté aquí
    devuelve False, es decir la condición no se cumple — y en una política de
    denegación eso significa PERMITIR."""
    assert set(ABACEngine._OPERADORES) == {
        "equals", "not_equals", "in", "not_in", "contains", "not_contains",
        "starts_with", "ends_with", "regex", "gte", "lte", "gt", "lt",
        "is_empty", "is_not_empty",
    }


def test_un_operador_inexistente_no_cumple_la_condicion():
    assert _evaluar("madrid", "operador_inventado", "madrid") is False


def test_sin_operador_se_asume_equals():
    """El valor por defecto del original, conservado."""
    assert _evaluar("madrid", None, "madrid") is True
    assert _evaluar("madrid", None, "barcelona") is False


# ── Igualdad ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("valor,esperado,resultado", [
    ("madrid", "madrid", True),
    ("madrid", "barcelona", False),
    ("MADRID", "madrid", False),   # `equals` SÍ distingue mayúsculas
    (5, 5, True),
])
def test_equals(valor, esperado, resultado):
    assert _evaluar(valor, "equals", esperado) is resultado


def test_not_equals_es_la_negacion_de_equals():
    assert _evaluar("madrid", "not_equals", "barcelona") is True
    assert _evaluar("madrid", "not_equals", "madrid") is False


# ── Pertenencia, y su asimetría ───────────────────────────────────────────────

def test_in_con_una_lista_basta_con_que_uno_coincida():
    assert _evaluar(["a", "b"], "in", ["b", "c"]) is True
    assert _evaluar(["a", "b"], "in", ["c", "d"]) is False


def test_not_in_con_una_lista_exige_que_ninguno_coincida():
    """No es la negación de `in`: es `all(not ...)`, no `not any(...)`.

    Con `["a","b"]` contra `["b","c"]`, `in` da True y `not_in` da False — pero
    la diferencia importa cuando sólo algunos coinciden, y ahí una implementación
    ingenua se equivoca.
    """
    assert _evaluar(["a", "b"], "not_in", ["c", "d"]) is True
    assert _evaluar(["a", "b"], "not_in", ["b", "c"]) is False


def test_in_con_un_valor_suelto():
    assert _evaluar("a", "in", ["a", "b"]) is True
    assert _evaluar("z", "in", ["a", "b"]) is False


# ── Contención, y su asimetría por tipo ───────────────────────────────────────

def test_contains_en_cadena_ignora_mayusculas():
    assert _evaluar("Madrid Centro", "contains", "madrid") is True
    assert _evaluar("madrid centro", "contains", "MADRID") is True


def test_contains_en_lista_es_pertenencia_exacta():
    """En lista NO ignora mayúsculas: es `in`, no comparación de texto."""
    assert _evaluar(["a", "b"], "contains", "a") is True
    assert _evaluar(["A", "b"], "contains", "a") is False


def test_contains_en_otro_tipo_no_contiene_nada():
    assert _evaluar(5, "contains", "5") is False


def test_not_contains_refleja_las_mismas_reglas():
    assert _evaluar("madrid", "not_contains", "barcelona") is True
    assert _evaluar("madrid centro", "not_contains", "MADRID") is False
    assert _evaluar(["a"], "not_contains", "b") is True


# ── Prefijos, sufijos y regex ─────────────────────────────────────────────────

def test_starts_with_y_ends_with_convierten_a_texto():
    assert _evaluar("madrid", "starts_with", "mad") is True
    assert _evaluar("madrid", "ends_with", "rid") is True
    assert _evaluar(12345, "starts_with", "123") is True, (
        "convierte a texto, así que funciona con números"
    )


def test_regex_ancla_al_principio():
    """`re.match`, no `re.search`: «abc» al final de la cadena no coincide."""
    assert _evaluar("abc123", "regex", r"abc\d+") is True
    assert _evaluar("xxabc123", "regex", r"abc\d+") is False


def test_una_regex_mal_formada_LANZA_y_es_deliberado():
    """No se captura, y es la decisión correcta.

    `enforce_abac` recoge la excepción, **deniega por defecto** y registra un
    error con la política culpable. Devolver `False` aquí sería peor de dos
    maneras: se perdería el aviso al administrador de que su regex está rota, y
    «la regla no se cumple» no es lo mismo que «no se pudo evaluar» — en una
    política de denegación, no cumplirse significa PERMITIR.
    """
    import re as _re

    with pytest.raises(_re.error):
        _evaluar("abc", "regex", "[[")


# ── Comparaciones ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("op,valor,esperado,resultado", [
    ("gte", 10, 5, True), ("gte", 5, 5, True), ("gte", 4, 5, False),
    ("lte", 4, 5, True), ("lte", 5, 5, True), ("lte", 6, 5, False),
    ("gt", 6, 5, True), ("gt", 5, 5, False),
    ("lt", 4, 5, True), ("lt", 5, 5, False),
])
def test_comparaciones(op, valor, esperado, resultado):
    assert _evaluar(valor, op, esperado) is resultado


def test_comparar_tipos_incompatibles_no_cumple_en_vez_de_lanzar():
    """Un `TypeError` sí se captura: comparar texto con número es un dato mal
    configurado, no una política rota."""
    assert _evaluar("texto", "gt", 5) is False
    assert _evaluar("texto", "lt", 5) is False


# ── Vacío ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("valor,vacio", [
    ("", True), ([], True), ("algo", False), (["a"], False),
])
def test_is_empty_y_su_contrario(valor, vacio):
    assert _evaluar(valor, "is_empty", None) is vacio
    assert _evaluar(valor, "is_not_empty", None) is (not vacio)


# ── None: el caso que se resuelve antes de la tabla ───────────────────────────

def test_un_atributo_ausente_solo_cumple_not_equals():
    """Si el usuario no tiene el atributo, la única condición que se cumple es
    «no es igual a X». Cualquier otra sería afirmar algo sobre un dato que no
    existe."""
    assert _evaluar(None, "not_equals", "algo") is True
    assert _evaluar(None, "equals", "algo") is False
    assert _evaluar(None, "in", ["algo"]) is False
    assert _evaluar(None, "is_empty", None) is False, (
        "con valor esperado None, ni not_equals se cumple"
    )


def test_atributo_ausente_y_valor_esperado_ausente_no_cumple_nada():
    assert _evaluar(None, "not_equals", None) is False
