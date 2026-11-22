"""Ajustes del índice de riesgo (`sw_config.risk_settings`, JSON).

Fórmula documentada en `docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md` §11.2-11.3.
Sin fila o sin valor, `DEFECTO`. Se validan al guardar (pesos entre 0 y 1 que
suman 1, saturaciones > 0, multiplicadores entre 0 y 2, rangos de impacto en
orden, objetivo 0-100) y cada cambio queda en la auditoría
(`sw_risk_settings`, antes y después). Lo cambia quien tiene `software.config`.
"""
from __future__ import annotations

import copy
import json
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error

FACTORES = ("vulnerabilities", "exploitation", "exposure", "configuration", "eol", "signals")

DEFECTO: dict = {
    "weights": {"vulnerabilities": 0.35, "exploitation": 0.20, "exposure": 0.15, "configuration": 0.10, "eol": 0.10,
                "signals": 0.10},
    "saturation": {"vulnerabilities": 5.0, "exploitation": 2.0, "exposure": 3.0, "configuration": 10.0, "eol": 5.0,
                   "signals": 3.0},
    "exposure": {"internet": 1.0, "internal": 0.7, "isolated": 0.4},
    "criticality": {"critical": 1.0, "high": 0.85, "medium": 0.7, "low": 0.5},
    "exploit": {"w_kev": 0.5, "w_epss": 0.5, "w_attempts": 0.5, "epss_threshold": 0.5},
    "age": {"w_age": 0.25, "age_cap_days": 180},
    "impact_ranges": {"high_from": 70.0, "medium_from": 40.0},
    "target": 30.0,
    "history_days": 730,
    "alerts": {"kev_new": True, "index_above": None, "sla_due_days": 3, "roles": ["admin"], "user_ids": [],
               "email": False},
}

#: Reducción por defecto de cada tipo de control compensatorio.
REDUCCION_POR_TIPO = {"waf": 0.5, "ips": 0.5, "virtual_patch": 0.7, "isolation": 0.8, "edr": 0.3,
                      "segmentation": 0.5, "other": 0.3}
ROLES = ("admin", "pm", "team_lead", "hr", "employee", "finance", "member")


def _fila(db: Session, org: Optional[str], crear: bool = False):
    from app.services.cmdb_software import ajustes as base
    return base.fila(db, org, crear=crear)


def _mezclar(base: dict, otro: dict) -> dict:
    salida = copy.deepcopy(base)
    for k, v in (otro or {}).items():
        if k in salida and isinstance(salida[k], dict) and isinstance(v, dict):
            salida[k] = _mezclar(salida[k], v)
        elif k in salida:
            salida[k] = v
    return salida


def leer(db: Session, org: Optional[str]) -> dict:
    c = _fila(db, org)
    guardado: dict = {}
    if c is not None and getattr(c, "risk_settings", None):
        try:
            guardado = json.loads(c.risk_settings) or {}
        except ValueError:
            guardado = {}
    return _mezclar(DEFECTO, guardado)


def con_defectos(db: Session, org: Optional[str]) -> dict:
    return {**leer(db, org), "defaults": copy.deepcopy(DEFECTO)}


def _numero(campo: str, v, minimo: float, maximo: float) -> float:
    try:
        n = float(v)
    except (TypeError, ValueError):
        raise error(422, "swr_ajuste_no_valido", campo=campo)
    if not minimo <= n <= maximo or n != n:
        raise error(422, "swr_ajuste_no_valido", campo=campo)
    return n


def validar(a: dict) -> dict:
    """Valida un ajuste completo (ya mezclado con los valores por defecto)."""
    s = copy.deepcopy(a)
    for f in FACTORES:
        s["weights"][f] = _numero(f"weights.{f}", s["weights"].get(f, 0), 0.0, 1.0)
        s["saturation"][f] = _numero(f"saturation.{f}", s["saturation"].get(f, 1), 0.01, 10000.0)
    suma = round(sum(s["weights"][f] for f in FACTORES), 4)
    if abs(suma - 1.0) > 0.001:
        raise error(422, "swr_pesos_no_suman", suma=suma)
    for grupo in ("exposure", "criticality"):
        for k in DEFECTO[grupo]:
            s[grupo][k] = _numero(f"{grupo}.{k}", s[grupo].get(k), 0.0, 2.0)
    for k in ("w_kev", "w_epss", "w_attempts"):
        s["exploit"][k] = _numero(f"exploit.{k}", s["exploit"].get(k), 0.0, 5.0)
    s["exploit"]["epss_threshold"] = _numero("exploit.epss_threshold", s["exploit"].get("epss_threshold"), 0.0, 1.0)
    s["age"]["w_age"] = _numero("age.w_age", s["age"].get("w_age"), 0.0, 5.0)
    s["age"]["age_cap_days"] = int(_numero("age.age_cap_days", s["age"].get("age_cap_days"), 1, 3650))
    r = s["impact_ranges"]
    r["high_from"] = _numero("impact_ranges.high_from", r.get("high_from"), 0.0, 100.0)
    r["medium_from"] = _numero("impact_ranges.medium_from", r.get("medium_from"), 0.0, 100.0)
    if r["high_from"] <= r["medium_from"]:
        raise error(422, "swr_rangos_de_impacto")
    try:
        s["target"] = _numero("target", s.get("target"), 0.0, 100.0)
    except Exception:
        raise error(422, "swr_objetivo_no_valido")
    s["history_days"] = int(_numero("history_days", s.get("history_days"), 30, 3650))
    al = s["alerts"]
    al["kev_new"] = bool(al.get("kev_new"))
    al["email"] = bool(al.get("email"))
    al["index_above"] = None if al.get("index_above") in (None, "") else _numero("alerts.index_above",
                                                                                 al["index_above"], 0, 100)
    al["sla_due_days"] = None if al.get("sla_due_days") in (None, "") else int(_numero("alerts.sla_due_days",
                                                                                       al["sla_due_days"], 0, 365))
    roles = al.get("roles") or []
    if not isinstance(roles, list) or any(r not in ROLES for r in roles):
        raise error(422, "swr_ajuste_no_valido", campo="alerts.roles")
    al["roles"] = list(dict.fromkeys(roles))
    ids = al.get("user_ids") or []
    if not isinstance(ids, list):
        raise error(422, "swr_ajuste_no_valido", campo="alerts.user_ids")
    al["user_ids"] = [str(x)[:36] for x in ids if x][:100]
    return s


def guardar(db: Session, org: Optional[str], datos: dict, usuario=None) -> dict:
    """Mezcla, valida, guarda y audita. No confirma."""
    from app.services.audit import audit_log
    antes = leer(db, org)
    limpio = {k: v for k, v in (datos or {}).items() if k in DEFECTO}
    nuevo = validar(_mezclar(antes, limpio))
    c = _fila(db, org, crear=True)
    c.risk_settings = json.dumps(nuevo)
    if usuario is not None:
        c.updated_by = usuario.id
    db.flush()
    audit_log(db, usuario, "UPDATE", "sw_risk_settings", c.id, "Índice de riesgo", old_values=antes, new_values=nuevo)
    return con_defectos(db, org)
