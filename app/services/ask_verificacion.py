"""Verificación de Ask-the-Data: ¿la consulta responde a ESTA pregunta o a otra parecida?

Revisión 2026-11 (lo que contecintelligence ya tenía). Que la consulta se
ejecute y devuelva filas no dice que conteste a lo preguntado: «las horas de
marzo» contestadas con las horas de todo el histórico dan un número real, y más
alto. Se comprueban las maneras de contestar a otra pregunta que no necesitan un
catálogo semántico del cliente:

- **time_window**: la pregunta acota un periodo y la consulta no filtra por fecha.
- **breakdown**: pide un desglose («por proyecto») y la consulta no agrupa.
- **ranking**: pide un «top» o «los que más» y la consulta no ordena.
- **units**: pide un porcentaje o una media y la consulta no divide ni promedia.
- **distinct**: pide elementos distintos y la consulta cuenta filas.

Se mira el árbol de la consulta que generó el modelo (el de DuckDB,
`json_serialize_sql`: sin dependencias nuevas), ANTES de que le añadamos el
filtro de empresa y el LIMIT, que si no harían pasar por buenas consultas que no
filtran nada.

REGLA DE HONESTIDAD: cada comprobación puede decir `skipped`. Si no se ha podido
mirar nada, el veredicto es `not_checked`, nunca `verified`.
"""
from __future__ import annotations

import json
import re
from typing import Any

# Patrones de intención en castellano e inglés (los idiomas del producto que
# preguntan en lenguaje natural; el chino se queda en `skipped`, dicho).
_MESES = r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre|january|february|march|april|may|june|july|august|september|october|november|december"
_PERIODO = re.compile(
    rf"\b(?:{_MESES}|20\d\d|q[1-4]|trimestre|semestre|este mes|el mes pasado|mes pasado|esta semana|semana pasada|"
    r"este año|año pasado|hoy|ayer|últim[oa]s? \d+ (?:días|semanas|meses)|ultim[oa]s? \d+ (?:dias|semanas|meses)|"
    r"this (?:month|week|year|quarter)|last (?:month|week|year|quarter)|today|yesterday|last \d+ (?:days|weeks|months))\b",
    re.I)
_DESGLOSE = re.compile(r"\b(?:por (?:proyecto|cliente|usuario|persona|mes|semana|año|estado|prioridad|tipo|agente|etapa)|"
                       r"desglos\w*|cada (?:proyecto|cliente|persona|mes)|by (?:project|client|user|person|month|week|year|status|priority|type|agent|stage)|"
                       r"per (?:project|client|user|month)|breakdown)\b", re.I)
_RANKING = re.compile(r"\b(?:top ?\d*|ranking|los \d+ (?:más|mas|menos)|l[oa]s? (?:más|mas|menos) \w+|(?:mayor|menor)(?:es)?(?! que)|"
                      r"mejores|peores|highest|lowest|best|worst|most|least)\b", re.I)
_PORCENTAJE = re.compile(r"(?:%|\bporcentaje\b|\bpercentage\b|\btasa\b|\bratio\b|\brate\b|\bproporci[oó]n\b)", re.I)
_MEDIA = re.compile(r"\b(?:media|promedio|average|mean)\b", re.I)
_DISTINTOS = re.compile(r"\b(?:distint[oa]s|únic[oa]s|unic[oa]s|diferentes|distinct|unique)\b", re.I)

_COLUMNAS_DE_FECHA = {"date", "year", "quarter", "month", "month_name", "week", "yyyymm", "day_of_week",
                      "date_key", "created_date_key", "closed_date_key", "expected_close_key",
                      "start_date_key", "end_date_key", "start_date", "end_date"}


def _arbol(sql: str) -> dict | None:
    import duckdb
    try:
        crudo = duckdb.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0]
        datos = json.loads(crudo)
    except Exception:
        return None
    if datos.get("error") or not datos.get("statements"):
        return None
    return datos["statements"][0]["node"]


def _recorrer(nodo: Any):
    if isinstance(nodo, dict):
        yield nodo
        for v in nodo.values():
            yield from _recorrer(v)
    elif isinstance(nodo, list):
        for v in nodo:
            yield from _recorrer(v)


def _columnas(nodo: Any) -> set[str]:
    return {n["column_names"][-1].lower() for n in _recorrer(nodo)
            if n.get("class") == "COLUMN_REF" and n.get("column_names")}


def _funciones(nodo: Any) -> list[dict]:
    return [n for n in _recorrer(nodo) if n.get("class") in ("FUNCTION", "AGGREGATE")]


def _nombre(f: dict) -> str:
    return str(f.get("function_name", "")).lower()


def _consultas(nodo: dict) -> list[dict]:
    """El SELECT y los de sus subconsultas/CTE: un filtro puede estar en una CTE."""
    return [n for n in _recorrer(nodo) if n.get("type") == "SELECT_NODE"]


def verificar(pregunta: str, sql: str, filas: int | None = None) -> dict:
    pregunta = pregunta or ""
    arbol = _arbol(sql or "")
    if arbol is None:
        return {"verdict": "not_checked", "checks": [],
                "detail": "No se pudo analizar la consulta: nada comprobado."}
    selects = _consultas(arbol) or [arbol]
    donde = [s.get("where_clause") for s in selects if s.get("where_clause")]
    agrupa = any(s.get("group_expressions") for s in selects)
    ordena = any(m.get("type") == "ORDER_MODIFIER" for s in selects for m in s.get("modifiers", []))
    funciones = _funciones(arbol)
    agregados = [f for f in funciones if _nombre(f) in ("sum", "count", "avg", "mean", "min", "max", "median")]
    checks = []

    def anotar(nombre, aplica, bien, detalle_mal, detalle_bien, por_que_no):
        if not aplica:
            checks.append({"name": nombre, "status": "skipped", "detail": por_que_no})
        elif bien:
            checks.append({"name": nombre, "status": "ok", "detail": detalle_bien})
        else:
            checks.append({"name": nombre, "status": "warning", "detail": detalle_mal})

    periodo = _PERIODO.search(pregunta)
    anotar("time_window", bool(periodo), bool(_columnas(donde) & _COLUMNAS_DE_FECHA),
           f"La pregunta acota un periodo («{periodo.group(0) if periodo else ''}») y la consulta no filtra por fecha: "
           "el resultado puede ser de todo el histórico.",
           "Filtra por fecha, como pide la pregunta.", "La pregunta no acota un periodo.")
    desglose = _DESGLOSE.search(pregunta)
    anotar("breakdown", bool(desglose), agrupa or not agregados,
           f"La pregunta pide un desglose («{desglose.group(0) if desglose else ''}») y la consulta da un total sin agrupar.",
           "Agrupa, como pide el desglose.", "La pregunta no pide un desglose.")
    ranking = _RANKING.search(pregunta)
    anotar("ranking", bool(ranking), ordena,
           f"La pregunta pide un orden («{ranking.group(0) if ranking else ''}») y la consulta no ordena: "
           "las filas que salen no son las primeras, son las que el motor tenía a mano.",
           "Ordena, como pide el ranking.", "La pregunta no pide un ranking.")
    porcentaje, media = _PORCENTAJE.search(pregunta), _MEDIA.search(pregunta)
    divide = any(n.get("function_name") == "/" or n.get("type") == "OPERATOR_DIVIDE" for n in _recorrer(arbol)) \
        or any(c.endswith(("_pct", "pct", "_rate", "ratio")) for c in _columnas(arbol))
    promedia = any(_nombre(f) in ("avg", "mean") for f in funciones)
    anotar("units", bool(porcentaje or media), (divide if porcentaje else True) and (promedia if media else True),
           "La pregunta pide " + ("un porcentaje" if porcentaje else "una media") +
           " y la consulta devuelve un valor absoluto.",
           "Las unidades encajan con lo que se pregunta.", "La pregunta no pide un porcentaje ni una media.")
    distintos = _DISTINTOS.search(pregunta)
    cuenta_distintos = any(f.get("distinct") for f in agregados) or any(
        m.get("type") == "DISTINCT_MODIFIER" for s in selects for m in s.get("modifiers", []))
    anotar("distinct", bool(distintos), cuenta_distintos,
           "La pregunta pide elementos distintos y la consulta cuenta filas (que pueden repetirse).",
           "Cuenta elementos distintos.", "La pregunta no pide elementos distintos.")

    estados = {c["status"] for c in checks}
    if "warning" in estados:
        veredicto = "warning"
    elif "ok" in estados:
        veredicto = "verified"
    else:
        veredicto = "not_checked"
    return {"verdict": veredicto, "checks": checks}
