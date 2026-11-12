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
import logging

import json
import re
from typing import Any

# Patrones de intención en castellano, inglés y chino (los idiomas del producto).
# El chino va aparte: `\b` no marca límites entre caracteres chinos, así que sus
# patrones no llevan límite de palabra (revisión 2026-11: antes una pregunta en
# chino se quedaba siempre en «sin comprobar»).
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

_NUM_ZH = r"[0-9一二三四五六七八九十两]+"
_PERIODO_ZH = re.compile(rf"(?:{_NUM_ZH}月|本月|上个?月|这个月|本周|上周|这周|今年|去年|本季度|上季度|"
                         rf"第[一二三四1-4]季度|今天|昨天|最近{_NUM_ZH}(?:天|周|个月)|过去{_NUM_ZH}(?:天|周|个月)|20\d\d年)")
_DESGLOSE_ZH = re.compile(r"(?:按(?:项目|客户|用户|人员|月|月份|周|年|状态|优先级|类型|阶段|代理)|每个(?:项目|客户|人|月)|"
                          r"各(?:项目|客户|部门|月)|分组|细分)")
_RANKING_ZH = re.compile(rf"(?:前{_NUM_ZH}|排名|排行|最多|最少|最高|最低|最大|最小)")
_PORCENTAJE_ZH = re.compile(r"(?:百分比|比例|比率|占比|％)")
_MEDIA_ZH = re.compile(r"(?:平均|均值)")
_DISTINTOS_ZH = re.compile(r"(?:不同的?|唯一|去重|不重复)")


def _buscar(pregunta: str, *patrones):
    for p in patrones:
        m = p.search(pregunta)
        if m:
            return m
    return None

_COLUMNAS_DE_FECHA = {"date", "year", "quarter", "month", "month_name", "week", "yyyymm", "day_of_week",
                      "date_key", "created_date_key", "closed_date_key", "expected_close_key",
                      "start_date_key", "end_date_key", "start_date", "end_date"}


def _arbol(sql: str) -> dict | None:
    import duckdb
    try:
        crudo = duckdb.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0]
        datos = json.loads(crudo)
    except Exception:
        logging.getLogger(__name__).warning("_arbol: excepcion ignorada", exc_info=True)
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

    periodo = _buscar(pregunta, _PERIODO, _PERIODO_ZH)
    anotar("time_window", bool(periodo), bool(_columnas(donde) & _COLUMNAS_DE_FECHA),
           f"La pregunta acota un periodo («{periodo.group(0) if periodo else ''}») y la consulta no filtra por fecha: "
           "el resultado puede ser de todo el histórico.",
           "Filtra por fecha, como pide la pregunta.", "La pregunta no acota un periodo.")
    desglose = _buscar(pregunta, _DESGLOSE, _DESGLOSE_ZH)
    anotar("breakdown", bool(desglose), agrupa or not agregados,
           f"La pregunta pide un desglose («{desglose.group(0) if desglose else ''}») y la consulta da un total sin agrupar.",
           "Agrupa, como pide el desglose.", "La pregunta no pide un desglose.")
    ranking = _buscar(pregunta, _RANKING, _RANKING_ZH)
    anotar("ranking", bool(ranking), ordena,
           f"La pregunta pide un orden («{ranking.group(0) if ranking else ''}») y la consulta no ordena: "
           "las filas que salen no son las primeras, son las que el motor tenía a mano.",
           "Ordena, como pide el ranking.", "La pregunta no pide un ranking.")
    porcentaje = _buscar(pregunta, _PORCENTAJE, _PORCENTAJE_ZH)
    media = _buscar(pregunta, _MEDIA, _MEDIA_ZH)
    divide = any(n.get("function_name") == "/" or n.get("type") == "OPERATOR_DIVIDE" for n in _recorrer(arbol)) \
        or any(c.endswith(("_pct", "pct", "_rate", "ratio")) for c in _columnas(arbol))
    promedia = any(_nombre(f) in ("avg", "mean") for f in funciones)
    anotar("units", bool(porcentaje or media), (divide if porcentaje else True) and (promedia if media else True),
           "La pregunta pide " + ("un porcentaje" if porcentaje else "una media") +
           " y la consulta devuelve un valor absoluto.",
           "Las unidades encajan con lo que se pregunta.", "La pregunta no pide un porcentaje ni una media.")
    distintos = _buscar(pregunta, _DISTINTOS, _DISTINTOS_ZH)
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
