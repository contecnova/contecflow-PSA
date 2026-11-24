"""Expresión `aplica_si` de las plantillas (docs/CERTIFICACIONES_CONTENIDO.md §2.4).

Gramática: `<parametro> <op> <literal>` unidas con `and` u `or`, sin paréntesis
(`and` antes que `or`). Operadores: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`.
Literales: `true`, `false`, enteros, `'texto'` y listas `['a', 'b']`.

No usa `eval`: se trocea y se interpreta aquí. `validar` devuelve el error (o
None) y `evaluar` el booleano con los parámetros del programa.
"""
from __future__ import annotations

import re
from typing import Any, Optional

_COMPARACION = re.compile(
    r"^\s*(?P<p>[A-Za-z_][A-Za-z0-9_]*)\s*(?P<op>==|!=|>=|<=|>|<|\bin\b)\s*(?P<lit>.+?)\s*$")
_OPERADORES = ("==", "!=", ">=", "<=", ">", "<", "in")


class ExpresionNoValida(ValueError):
    pass


def _literal(texto: str) -> Any:
    t = texto.strip()
    if t == "true":
        return True
    if t == "false":
        return False
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
        return t[1:-1]
    if t.startswith("[") and t.endswith("]"):
        dentro = t[1:-1].strip()
        if not dentro:
            return []
        return [_literal(x) for x in _partir_lista(dentro)]
    raise ExpresionNoValida(f"literal no válido: {texto}")


def _partir_lista(texto: str) -> list[str]:
    partes, actual, comilla = [], "", None
    for ch in texto:
        if comilla:
            actual += ch
            if ch == comilla:
                comilla = None
        elif ch in "'\"":
            comilla = ch
            actual += ch
        elif ch == ",":
            partes.append(actual)
            actual = ""
        else:
            actual += ch
    partes.append(actual)
    return [p for p in (x.strip() for x in partes) if p]


def _partir(texto: str, palabra: str) -> list[str]:
    """Parte por `and`/`or` fuera de comillas y corchetes."""
    partes, actual, comilla, nivel = [], "", None, 0
    i = 0
    patron = f" {palabra} "
    while i < len(texto):
        ch = texto[i]
        if comilla:
            if ch == comilla:
                comilla = None
        elif ch in "'\"":
            comilla = ch
        elif ch == "[":
            nivel += 1
        elif ch == "]":
            nivel -= 1
        elif nivel == 0 and texto.startswith(patron, i):
            partes.append(actual)
            actual = ""
            i += len(patron)
            continue
        actual += ch
        i += 1
    partes.append(actual)
    return partes


def _analizar(expr: str) -> list[list[tuple[str, str, Any]]]:
    """Forma normal disyuntiva: [[(param, op, literal), …and…], …or…]."""
    if not isinstance(expr, str) or not expr.strip():
        raise ExpresionNoValida("expresión vacía")
    salida = []
    for disyuncion in _partir(f" {expr.strip()} ", "or"):
        conj = []
        for parte in _partir(f" {disyuncion.strip()} ", "and"):
            m = _COMPARACION.match(parte)
            if not m:
                raise ExpresionNoValida(f"comparación no válida: {parte.strip()}")
            op = m.group("op").strip()
            if op not in _OPERADORES:
                raise ExpresionNoValida(f"operador no válido: {op}")
            lit = _literal(m.group("lit"))
            if op == "in" and not isinstance(lit, list):
                raise ExpresionNoValida("`in` necesita una lista")
            conj.append((m.group("p"), op, lit))
        salida.append(conj)
    return salida


def validar(expr: str, parametros: Optional[set] = None) -> Optional[str]:
    """None si la expresión es válida (y solo usa parámetros conocidos); si no, el motivo."""
    try:
        arbol = _analizar(expr)
    except ExpresionNoValida as e:
        return str(e)
    if parametros is not None:
        for conj in arbol:
            for p, _op, _lit in conj:
                if p not in parametros:
                    return f"parámetro desconocido: {p}"
    return None


def _compara(valor, op: str, lit) -> bool:
    try:
        if op == "==":
            return valor == lit
        if op == "!=":
            return valor != lit
        if op == "in":
            return valor in lit
        if valor is None:
            return False
        return {">": valor > lit, ">=": valor >= lit, "<": valor < lit, "<=": valor <= lit}[op]
    except TypeError:
        return False


def evaluar(expr: Optional[str], parametros: dict) -> bool:
    """Sin expresión, aplica. Con una no válida, ExpresionNoValida (la plantilla ya se validó al cargar)."""
    if expr is None or (isinstance(expr, str) and not expr.strip()):
        return True
    return any(all(_compara(parametros.get(p), op, lit) for p, op, lit in conj) for conj in _analizar(expr))
