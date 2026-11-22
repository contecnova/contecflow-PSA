"""Definición del flujo de demanda: lectura, nombres por idioma y validación.

El JSON de definición está documentado en docs/FLUJO_DE_DEMANDA.md (§2.2). Aquí
no hay base de datos: solo funciones puras sobre el diccionario, para que el
motor, el configurador y los tests compartan la misma lectura.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

FASES_KIND = ("intake", "work", "review", "approval", "gate", "committee")
MODOS_DE_PASO = ("task", "approval")
TIPOS_DE_ASIGNADO = ("role", "group", "user", "department", "committee", "approval_workflow", "requester",
                     "project_manager", "client_manager", "requester_manager", "department_head", "supplier")
#: Responsables que no necesitan valor (salen del expediente).
SIN_VALOR = ("requester", "project_manager", "client_manager", "requester_manager", "department_head")
DECISIONES = ("approve", "complete", "reject", "return", "request_info", "skip", "hold",
              "fast_track", "to_committee")
#: Las que exigen justificación siempre (el bypass, además, en la puerta).
CON_JUSTIFICACION = ("reject", "return", "request_info", "skip", "hold")
TIPOS_DE_CAMPO = ("text", "textarea", "number", "money", "date", "select", "boolean")
QUORUMS = ("any", "all", "majority")
EVENTOS = ("enter", "decision", "sla_warning", "sla_breach", "info_requested", "closed", "submitted")
DESTINOS_DE_AVISO = ("requester", "assignees", "role", "group", "user", "project_manager", "client_manager",
                     "requester_manager", "department_head", "supplier")
OPERADORES = ("gt", "gte", "lt", "lte", "eq", "ne", "in", "true", "false", "empty", "not_empty")
ETIQUETAS_DE_DOCUMENTO = ("mockup", "regulation", "presentation", "business_case", "technical_study",
                          "cab_security_report", "legal_opinion", "compliance_opinion", "committee_minutes",
                          "executive_summary", "annex", "other")
MODOS_DE_EJECUCION = ("backlog", "new_project", "portfolio")
#: Acciones al terminar (`on_close_actions[].action`), ver `ejecucion.py`.
ACCIONES = ("create_project", "create_change_request", "create_portfolio_proposal", "create_task", "create_ticket",
            "create_itsm_change", "executive_summary", "create_purchase")
CANALES = ("client_portal", "internal_portal", "operator", "supplier_portal")
ALCANCES = ("project", "service", "asset", "none")
FIN_APROBADA = "end:approved"
FIN_RECHAZADA = "end:rejected"

_CLAVE = re.compile(r"^[a-z][a-z0-9_]{0,59}$")


def cargar(texto: Any) -> dict:
    """El diccionario de la definición (acepta texto JSON o dict)."""
    if isinstance(texto, dict):
        return texto
    try:
        datos = json.loads(texto) if texto else {}
    except (TypeError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def nombre(valor: Any, idioma: str = "es") -> str:
    """Un nombre que puede venir como texto o como {es, en, zh…}."""
    if isinstance(valor, dict):
        return str(valor.get(idioma) or valor.get("es") or valor.get("en") or next(iter(valor.values()), "") or "")
    return "" if valor is None else str(valor)


def fases(defn: dict) -> list[dict]:
    return [f for f in (defn.get("phases") or []) if isinstance(f, dict)]


def fase(defn: dict, clave: Optional[str]) -> Optional[dict]:
    return next((f for f in fases(defn) if f.get("key") == clave), None)


def indice(defn: dict, clave: Optional[str]) -> int:
    return next((i for i, f in enumerate(fases(defn)) if f.get("key") == clave), -1)


def siguiente(defn: dict, clave: str) -> str:
    """La clave de la fase que sigue a `clave`, o `end:approved` si es la última."""
    i = indice(defn, clave)
    lista = fases(defn)
    return lista[i + 1]["key"] if 0 <= i < len(lista) - 1 else FIN_APROBADA


def resolver_destino(defn: dict, desde: str, destino: Optional[str], defecto: str) -> str:
    """`next`, una clave de fase o `end:*` → la clave efectiva."""
    destino = destino or defecto
    if destino == "next":
        return siguiente(defn, desde)
    return destino


def pasos(f: dict) -> list[dict]:
    return [p for p in (f.get("steps") or []) if isinstance(p, dict)]


def paso(f: dict, clave: str) -> Optional[dict]:
    return next((p for p in pasos(f) if p.get("key") == clave), None)


def campos(defn: dict) -> list[dict]:
    return [c for c in (defn.get("fields") or []) if isinstance(c, dict)]


def campo(defn: dict, clave: str) -> Optional[dict]:
    return next((c for c in campos(defn) if c.get("key") == clave), None)


def campo_de_politica(defn: dict, alias: str) -> Optional[str]:
    """La clave del campo que el flujo expone al motor de políticas como `alias`."""
    c = next((c for c in campos(defn) if c.get("policy_field") == alias), None)
    return c["key"] if c else (alias if campo(defn, alias) else None)


def decisiones(f: dict) -> list[str]:
    lista = [d for d in (f.get("decisions") or []) if d in DECISIONES]
    if f.get("kind") == "gate":
        for d in ("fast_track", "to_committee"):
            if d not in lista:
                lista.append(d)
    if not lista:
        lista = ["approve", "reject"]
    return lista


def destinos_de_devolucion(defn: dict, f: dict) -> list[str]:
    lista = [k for k in (f.get("return_targets") or []) if fase(defn, k)]
    if lista:
        return lista
    i = indice(defn, f.get("key"))
    return [x["key"] for x in fases(defn)[:max(i, 0)]]


def vacio(valor: Any) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip()) or valor == []


def faltan(datos: dict, claves: list[str], titulo: Optional[str] = None) -> list[str]:
    """Las claves de `claves` sin valor en `datos` (`title` mira el título)."""
    salida = []
    for k in claves or []:
        valor = titulo if k == "title" else (datos or {}).get(k)
        if vacio(valor):
            salida.append(k)
    return salida


# ── Condiciones de la puerta ─────────────────────────────────────────────────

def _numero(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def cumple(condicion: dict, datos: dict) -> bool:
    """Una condición `{field, op, value}` sobre los datos del expediente."""
    actual = (datos or {}).get(condicion.get("field"))
    op = condicion.get("op") or "eq"
    esperado = condicion.get("value")
    if op == "empty":
        return vacio(actual)
    if op == "not_empty":
        return not vacio(actual)
    if op in ("true", "false"):
        verdad = actual in (True, "true", "1", 1, "si", "sí", "yes")
        return verdad if op == "true" else not verdad
    if op == "in":
        opciones = esperado if isinstance(esperado, list) else [x.strip() for x in str(esperado or "").split(",")]
        return str(actual) in [str(x) for x in opciones]
    if op in ("gt", "gte", "lt", "lte"):
        a, b = _numero(actual), _numero(esperado)
        if a is None or b is None:
            return False
        return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[op]
    if op == "ne":
        return str(actual) != str(esperado)
    return str(actual) == str(esperado)


def evaluar_puerta(f: dict, datos: dict) -> tuple[bool, list[str]]:
    """(¿se cumplen las condiciones?, motivos legibles) de la puerta de una fase."""
    puerta = f.get("gate") or {}
    conds = [c for c in (puerta.get("conditions") or []) if isinstance(c, dict) and c.get("field")]
    cumplidas = [c for c in conds if cumple(c, datos)]
    motivos = [f"{c['field']} {c.get('op', 'eq')} {c.get('value', '')}".strip() for c in cumplidas]
    if not conds:
        return False, []
    if (puerta.get("match") or "any") == "all":
        return len(cumplidas) == len(conds), motivos
    return bool(cumplidas), motivos


# ── Validación ───────────────────────────────────────────────────────────────

def _err(errores: list, ruta: str, codigo: str) -> None:
    errores.append({"path": ruta, "code": codigo})


def _destino_valido(defn: dict, destino: Optional[str]) -> bool:
    return destino in (None, "", "next", FIN_APROBADA, FIN_RECHAZADA) or fase(defn, destino) is not None


def validar(defn: Any) -> list[dict]:
    """Errores `{path, code}` de una definición. Lista vacía = válida."""
    errores: list[dict] = []
    if not isinstance(defn, dict):
        return [{"path": "", "code": "definicion_no_es_objeto"}]
    claves_campo = set()
    for i, c in enumerate(campos(defn)):
        ruta = f"fields[{i}]"
        k = c.get("key")
        if not isinstance(k, str) or not _CLAVE.match(k):
            _err(errores, f"{ruta}.key", "clave_invalida")
        elif k in claves_campo:
            _err(errores, f"{ruta}.key", "clave_duplicada")
        claves_campo.add(k)
        if not nombre(c.get("label")):
            _err(errores, f"{ruta}.label", "nombre_obligatorio")
        if c.get("type", "text") not in TIPOS_DE_CAMPO:
            _err(errores, f"{ruta}.type", "tipo_campo_invalido")
        if c.get("owner", "client") not in ("client", "internal"):
            _err(errores, f"{ruta}.owner", "valor_invalido")
    conocidos = claves_campo | {"title"}
    for k in defn.get("submit_required") or []:
        if k not in conocidos:
            _err(errores, "submit_required", "campo_inexistente")
    lista = fases(defn)
    if not lista:
        _err(errores, "phases", "sin_fases")
    claves_fase = set()
    for i, f in enumerate(lista):
        ruta = f"phases[{i}]"
        k = f.get("key")
        if not isinstance(k, str) or not _CLAVE.match(k):
            _err(errores, f"{ruta}.key", "clave_invalida")
        elif k in claves_fase:
            _err(errores, f"{ruta}.key", "clave_duplicada")
        claves_fase.add(k)
        if not nombre(f.get("name")):
            _err(errores, f"{ruta}.name", "nombre_obligatorio")
        if f.get("kind", "approval") not in FASES_KIND:
            _err(errores, f"{ruta}.kind", "kind_invalido")
        if not pasos(f):
            _err(errores, f"{ruta}.steps", "sin_pasos")
        claves_paso = set()
        for j, p in enumerate(pasos(f)):
            rp = f"{ruta}.steps[{j}]"
            pk = p.get("key")
            if not isinstance(pk, str) or not _CLAVE.match(pk):
                _err(errores, f"{rp}.key", "clave_invalida")
            elif pk in claves_paso:
                _err(errores, f"{rp}.key", "clave_duplicada")
            claves_paso.add(pk)
            if p.get("mode", "approval") not in MODOS_DE_PASO:
                _err(errores, f"{rp}.mode", "valor_invalido")
            a = p.get("assignee") or {}
            if a.get("type") not in TIPOS_DE_ASIGNADO:
                _err(errores, f"{rp}.assignee", "asignado_invalido")
            elif a.get("type") not in SIN_VALOR and not a.get("value"):
                _err(errores, f"{rp}.assignee", "asignado_invalido")
            if p.get("quorum", "any") not in QUORUMS:
                _err(errores, f"{rp}.quorum", "valor_invalido")
        for d in f.get("decisions") or []:
            if d not in DECISIONES:
                _err(errores, f"{ruta}.decisions", "decision_invalida")
        for k2 in (f.get("required_fields") or []) + (f.get("internal_editable") or []):
            if k2 not in conocidos:
                _err(errores, f"{ruta}.required_fields", "campo_inexistente")
        for n in f.get("notify") or []:
            if n.get("event") not in EVENTOS or (n.get("to") or {}).get("type") not in DESTINOS_DE_AVISO:
                _err(errores, f"{ruta}.notify", "aviso_invalido")
        sla = f.get("sla_hours")
        if sla not in (None, "") and (_numero(sla) is None or _numero(sla) < 0):
            _err(errores, f"{ruta}.sla_hours", "valor_invalido")
        if f.get("kind") == "gate":
            g = f.get("gate") or {}
            if not g.get("if_true") or not g.get("if_false"):
                _err(errores, f"{ruta}.gate", "gate_sin_destinos")
            for c in g.get("conditions") or []:
                if c.get("op", "eq") not in OPERADORES:
                    _err(errores, f"{ruta}.gate.conditions", "valor_invalido")
    # Destinos: después de conocer todas las fases.
    for i, f in enumerate(lista):
        ruta = f"phases[{i}]"
        for campo_destino in ("on_approve", "on_reject"):
            if not _destino_valido(defn, f.get(campo_destino)):
                _err(errores, f"{ruta}.{campo_destino}", "fase_inexistente")
        for k2 in f.get("return_targets") or []:
            if not fase(defn, k2):
                _err(errores, f"{ruta}.return_targets", "fase_inexistente")
        for k2 in ((f.get("segregation") or {}).get("not_actor_of_phases") or []):
            if not fase(defn, k2):
                _err(errores, f"{ruta}.segregation", "fase_inexistente")
        if f.get("kind") == "gate":
            g = f.get("gate") or {}
            for d in ("if_true", "if_false"):
                if g.get(d) and not _destino_valido(defn, g.get(d)):
                    _err(errores, f"{ruta}.gate.{d}", "fase_inexistente")
    for i, f in enumerate(lista):
        ruta = f"phases[{i}]"
        for c in ((f.get("condition") or {}).get("conditions") or []):
            if c.get("op", "eq") not in OPERADORES:
                _err(errores, f"{ruta}.condition", "valor_invalido")
        esc = (f.get("escalation") or {}).get("to")
        if esc and esc.get("type") not in TIPOS_DE_ASIGNADO:
            _err(errores, f"{ruta}.escalation", "asignado_invalido")
        for dec, destino in (f.get("targets") or {}).items():
            if dec not in DECISIONES or not _destino_valido(defn, destino):
                _err(errores, f"{ruta}.targets", "fase_inexistente")
    for m in defn.get("execution") or []:
        if m not in MODOS_DE_EJECUCION:
            _err(errores, "execution", "valor_invalido")
    for i, a in enumerate(defn.get("on_close_actions") or []):
        if a.get("action") not in ACCIONES:
            _err(errores, f"on_close_actions[{i}].action", "valor_invalido")
        if a.get("when", "approved") not in ("approved", "rejected", "any"):
            _err(errores, f"on_close_actions[{i}].when", "valor_invalido")
    return errores


# ── Simulador ────────────────────────────────────────────────────────────────

def simular(defn: dict, datos: dict, decisiones_forzadas: Optional[dict] = None, maximo: int = 50) -> dict:
    """Recorrido previsto del flujo con unos datos (sin base de datos ni políticas).

    `decisiones_forzadas`: {fase: decisión} para probar ramas (por defecto se
    aprueba; en una puerta se sigue lo que digan las condiciones). Devuelve
    {path: [{phase, name, kind, skipped, decision, reasons}], end, warnings}.
    """
    forzadas = decisiones_forzadas or {}
    camino: list[dict] = []
    avisos: list[str] = []
    actual = fases(defn)[0]["key"] if fases(defn) else FIN_APROBADA
    vistas: dict = {}
    while actual not in (FIN_APROBADA, FIN_RECHAZADA) and len(camino) < maximo:
        f = fase(defn, actual)
        if f is None:
            avisos.append(f"fase_inexistente:{actual}")
            break
        vistas[actual] = vistas.get(actual, 0) + 1
        if vistas[actual] > 3:
            avisos.append(f"bucle:{actual}")
            break
        cond = f.get("condition")
        if cond and cond.get("conditions") and not evaluar_puerta({"gate": cond}, datos)[0]:
            camino.append({"phase": actual, "name": f.get("name"), "kind": f.get("kind"), "skipped": True,
                           "decision": None, "reasons": []})
            actual = siguiente(defn, actual)
            continue
        decision = forzadas.get(actual)
        motivos: list = []
        if f.get("kind") == "gate":
            requerido, motivos = evaluar_puerta(f, datos)
            decision = decision or ("to_committee" if requerido else "fast_track")
            g = f.get("gate") or {}
            destino = g.get("if_true") if decision == "to_committee" else g.get("if_false")
        else:
            decision = decision or "approve"
            if decision == "reject":
                destino = (f.get("targets") or {}).get("reject") or f.get("on_reject") or FIN_RECHAZADA
            elif decision == "return":
                objetivos = destinos_de_devolucion(defn, f)
                destino = objetivos[0] if objetivos else actual
            else:
                destino = (f.get("targets") or {}).get("approve") or f.get("on_approve") or "next"
        camino.append({"phase": actual, "name": f.get("name"), "kind": f.get("kind"), "skipped": False,
                       "decision": decision, "reasons": motivos})
        actual = resolver_destino(defn, actual, destino, "next")
    return {"path": camino, "end": actual, "warnings": avisos}


def diagrama(defn: dict) -> dict:
    """Nodos y aristas del flujo para el diseñador visual (fases, finales y transiciones)."""
    nodos = [{"id": f["key"], "label": f.get("name"), "kind": f.get("kind", "approval"),
              "parallel": bool(f.get("parallel")), "steps": [p.get("key") for p in pasos(f)],
              "conditional": bool(f.get("condition"))} for f in fases(defn) if f.get("key")]
    nodos += [{"id": FIN_APROBADA, "label": {"es": "Aprobada", "en": "Approved", "zh": "已批准"}, "kind": "end"},
              {"id": FIN_RECHAZADA, "label": {"es": "Rechazada", "en": "Rejected", "zh": "已拒绝"}, "kind": "end"}]
    aristas = []
    for f in fases(defn):
        k = f.get("key")
        if not k:
            continue
        if f.get("kind") == "gate":
            g = f.get("gate") or {}
            aristas.append({"from": k, "to": resolver_destino(defn, k, g.get("if_true"), "next"), "label": "to_committee"})
            aristas.append({"from": k, "to": resolver_destino(defn, k, g.get("if_false"), "next"), "label": "fast_track"})
            continue
        aristas.append({"from": k, "to": resolver_destino(defn, k, (f.get("targets") or {}).get("approve")
                                                           or f.get("on_approve"), "next"), "label": "approve"})
        if "reject" in decisiones(f):
            aristas.append({"from": k, "to": resolver_destino(defn, k, (f.get("targets") or {}).get("reject")
                                                               or f.get("on_reject"), FIN_RECHAZADA), "label": "reject"})
        if "return" in decisiones(f):
            for t in destinos_de_devolucion(defn, f):
                aristas.append({"from": k, "to": t, "label": "return"})
        if f.get("condition"):
            aristas.append({"from": k, "to": siguiente(defn, k), "label": "condition_false"})
    return {"nodes": nodos, "edges": aristas}
