"""Ask-the-Data: cuando un filtro no encuentra nada, los valores que SÍ existen (revisión 2026-11).

Lo que contecintelligence tenía. «Tickets en estado abierto» da cero filas si
en la base el estado se llama `open`: la consulta es correcta y la respuesta,
vacía y engañosa. Aquí:

1. se sacan de la consulta del modelo los filtros con un valor literal
   (`col = 'x'`, `col IN (...)`, `col LIKE/ILIKE '...'`), mirando su árbol
   (`json_serialize_sql` de DuckDB, igual que la verificación);
2. para cada uno se consultan los valores distintos que hay de verdad en esa
   columna, **de la empresa** (la misma validación y el mismo filtro de
   empresa que cualquier consulta);
3. se ordenan por parecido con lo buscado.

Sólo se aceptan columnas que existen en el esquema publicado de esa tabla: el
nombre nunca llega de fuera sin comprobar.
"""
from __future__ import annotations

import difflib
import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _esquema() -> dict[str, set[str]]:
    from app.services.ask_the_data import _SCHEMA_HINT
    tablas = {}
    for m in re.finditer(r"^(\w+)\(([^)]*)\)", _SCHEMA_HINT, re.M):
        tablas[m.group(1)] = {c.strip().split()[0].lower() for c in m.group(2).split(",") if c.strip()}
    return tablas


def _tablas_del_from(nodo: Any, salida: dict) -> None:
    if isinstance(nodo, dict):
        if nodo.get("type") == "BASE_TABLE" and nodo.get("table_name"):
            salida[(nodo.get("alias") or nodo["table_name"]).lower()] = nodo["table_name"].lower()
        for v in nodo.values():
            _tablas_del_from(v, salida)
    elif isinstance(nodo, list):
        for v in nodo:
            _tablas_del_from(v, salida)


def _constante(n: dict) -> Optional[str]:
    if n.get("class") != "CONSTANT":
        return None
    v = n.get("value") or {}
    if v.get("is_null") or (v.get("type") or {}).get("id") != "VARCHAR":
        return None
    return v.get("value")


def filtros_literales(sql: str) -> list[dict]:
    """[{table, column, op, values}] de los filtros de texto con valor fijo."""
    from app.services.ask_verificacion import _arbol, _recorrer
    arbol = _arbol(sql)
    if not arbol:
        return []
    alias: dict[str, str] = {}
    _tablas_del_from(arbol.get("from_table"), alias)
    esquema = _esquema()

    def tabla_de(columna_ref: dict) -> tuple[Optional[str], Optional[str]]:
        nombres = [c.lower() for c in columna_ref.get("column_names") or []]
        if not nombres:
            return None, None
        col = nombres[-1]
        if len(nombres) > 1:
            tabla = alias.get(nombres[-2])
        else:
            candidatas = [t for t in set(alias.values()) if col in esquema.get(t, set())]
            tabla = candidatas[0] if len(candidatas) == 1 else None
        if tabla is None or col not in esquema.get(tabla, set()):
            return None, None
        return tabla, col

    salida, vistos = [], set()
    for n in _recorrer(arbol.get("where_clause")):
        op, ref, valores = None, None, []
        if n.get("class") == "COMPARISON" and n.get("type") == "COMPARE_EQUAL":
            for a, b in ((n.get("left"), n.get("right")), (n.get("right"), n.get("left"))):
                if (a or {}).get("class") == "COLUMN_REF" and _constante(b or {}) is not None:
                    op, ref, valores = "=", a, [_constante(b)]
        elif n.get("class") == "OPERATOR" and n.get("type") == "COMPARE_IN":
            hijos = n.get("children") or []
            if hijos and hijos[0].get("class") == "COLUMN_REF":
                valores = [v for v in (_constante(h) for h in hijos[1:]) if v is not None]
                op, ref = ("in", hijos[0]) if valores else (None, None)
        elif n.get("class") == "FUNCTION" and n.get("function_name") in ("~~", "~~*"):
            hijos = n.get("children") or []
            if len(hijos) == 2 and hijos[0].get("class") == "COLUMN_REF" and _constante(hijos[1]) is not None:
                op, ref, valores = "like", hijos[0], [_constante(hijos[1])]
        if not op:
            continue
        tabla, col = tabla_de(ref)
        if tabla and (tabla, col, op) not in vistos:
            vistos.add((tabla, col, op))
            salida.append({"table": tabla, "column": col, "op": op, "values": valores})
    return salida


def _existentes(tabla: str, columna: str, org_id: Optional[str], limite: int) -> list[str]:
    from app.services.ask_the_data import _execute_on_olap, validate_sql
    if columna not in _esquema().get(tabla, set()):
        return []
    sql, params = validate_sql(
        f"SELECT DISTINCT CAST({columna} AS VARCHAR) AS v FROM {tabla} WHERE {columna} IS NOT NULL "  # noqa: S608 — columna del esquema
        f"LIMIT {int(limite)}", org_id)
    return [str(f["v"]) for f in _execute_on_olap(sql, params) if f.get("v") not in (None, "")]


def _parecido(buscado: str, real: str, op: str) -> float:
    b, r = buscado.lower(), real.lower()
    if op == "like":
        b = b.strip("%_")
        if b and b in r:
            return 1.0
    return difflib.SequenceMatcher(None, b, r).ratio()


def pistas(sql: str, org_id: Optional[str], *, max_valores: int, min_parecido: float,
           max_leidos: int = 500) -> list[dict]:
    """Para cada filtro literal: lo buscado, si existe, los valores reales más parecidos y una muestra."""
    salida = []
    for f in filtros_literales(sql):
        try:
            reales = _existentes(f["table"], f["column"], org_id, max_leidos)
        except Exception:
            logger.warning("ask_valores_reales: no se pudo leer %s.%s", f["table"], f["column"], exc_info=True)
            continue   # no se inventa: sin lectura, sin pista
        conjunto = {r.lower() for r in reales}
        for buscado in f["values"]:
            existe = (buscado.lower() in conjunto) if f["op"] != "like" else any(
                _parecido(buscado, r, "like") == 1.0 for r in reales)
            orden = sorted(reales, key=lambda r: _parecido(buscado, r, f["op"]), reverse=True)
            cercanos = [r for r in orden if _parecido(buscado, r, f["op"]) >= min_parecido][:max_valores]
            salida.append({"table": f["table"], "column": f["column"], "op": f["op"], "searched": buscado,
                           "exists": existe, "closest": cercanos, "sample": sorted(reales)[:max_valores],
                           "distinct_values_read": len(reales)})
    return salida


def como_feedback(lista: list[dict]) -> str:
    """El texto que se le da al modelo para que reintente con valores reales."""
    lineas = ["La consulta no devolvió filas. Estos filtros usan valores que no existen en los datos:"]
    for p in lista:
        if p["exists"]:
            continue
        reales = p["closest"] or p["sample"]
        lineas.append(f"- {p['table']}.{p['column']} {p['op']} '{p['searched']}': valores que existen: "
                      + json.dumps(reales, ensure_ascii=False))
    lineas.append("Reescribe la consulta usando exactamente uno de los valores que existen.")
    return "\n".join(lineas)
