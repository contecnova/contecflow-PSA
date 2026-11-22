"""Riesgo de hallazgos, índice por ámbito, histórico, comparación, plan y eventos.

Fórmula (documentada y configurable, `ajustes.DEFECTO`; §11.2-11.3 del diseño):

Riesgo de un hallazgo (0-100)::

    base   = CVSS × 10 (sin CVSS: critical 90, high 70, medium 50, low 20, unknown 50)
    explot = 1 + w_kev·KEV + w_epss·EPSS + w_attempts·(intentos > 0)
    r      = base × explot × exposición × criticidad × (1 + w_age·min(1, edad/age_cap)) × (1 − reducción)
    r      = min(100, r);  versión desconocida × 0,5

Índice de un ámbito::

    S_f    = 100 × (1 − e^(−P_f / K_f))        (seis factores, ver FACTORES)
    índice = Σ peso_f × S_f

`P_f` de cada factor:

- vulnerabilities: Σ r/100 de los hallazgos vivos no aceptados;
- exploitation: Σ (KEV 1 + EPSS ≥ umbral 0,5 + con intentos 1);
- exposure: activos expuestos a Internet con algún hallazgo alto o crítico;
- configuration: deriva (1 por instancia) + incumplimientos de línea base
  (crítica 1, alta 0,7, media 0,4, baja 0,2);
- eol: instancias sin soporte (prod 1, resto 0,5; sistema operativo × 2);
- signals: intentos de explotación de 30 días (permitido 1, detectado 0,5,
  bloqueado 0,2 por evento).

El riesgo aceptado (hallazgos con excepción aprobada) es el factor
`vulnerabilities` de esos hallazgos, aparte del índice.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.cmdb_software.riesgo import ajustes as aj

FACTORES = aj.FACTORES
AMBITOS = ("org", "client", "service", "machine", "application")
VIVOS_SIN_ACEPTAR = ("open", "triaged", "in_progress", "mitigated")
_BASE_SEV = {"critical": 90, "high": 70, "medium": 50, "low": 20, "none": 0, "unknown": 50}
_PESO_REGLA = {"critical": 1.0, "high": 0.7, "medium": 0.4, "low": 0.2}
_PESO_ACCION = {"allowed": 1.0, "detected": 0.5, "blocked": 0.2}
MAQUINAS = ("server", "virtual_machine", "endpoint", "container", "cloud")
NUBES = ("aws", "azure", "gcp")


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def _utc(d: Optional[datetime]) -> Optional[datetime]:
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _q(db, modelo, org):
    q = db.query(modelo)
    return q.filter(modelo.organization_id == org) if org else q


def _json(v, defecto=None):
    if not v:
        return defecto
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return defecto


def atributos_ci(ci) -> dict:
    a = _json(getattr(ci, "attributes", None), {})
    return a if isinstance(a, dict) else {}


def superficies_de_ci(ci, exposicion: Optional[str]) -> set[str]:
    """Superficies de un activo: internet/internal + contenedor, VM en la nube, serverless."""
    salida = {"internet" if exposicion == "internet" else "internal"}
    if ci is None:
        return salida
    tipo = getattr(ci.ci_type, "value", ci.ci_type)
    attrs = atributos_ci(ci)
    clase = (ci.ci_class or "").lower()
    if "serverless" in clase or "function" in clase or attrs.get("serverless") or attrs.get("runtime_type") == "serverless":
        salida.add("serverless")
    elif tipo == "container" or "container" in clase or "pod" in clase:
        salida.add("container")
    elif tipo == "cloud" or ((ci.discovery_provider or "").lower() in NUBES and tipo in ("virtual_machine", "server")):
        salida.add("cloud_vm")
    return salida


# ── Riesgo de un hallazgo ────────────────────────────────────────────────────

def riesgo_de_hallazgo(conf: dict, vuln, f, criticidad: str, exposicion: str, reduccion: float = 0.0,
                       momento: Optional[datetime] = None) -> tuple[float, dict]:
    momento = momento or ahora()
    base = float(vuln.cvss_score) * 10 if vuln is not None and vuln.cvss_score is not None \
        else float(_BASE_SEV.get(getattr(f, "severity", None) or "unknown", 50))
    ex = conf["exploit"]
    kev = bool(vuln is not None and vuln.kev)
    epss = float(vuln.epss_score or 0) if vuln is not None else 0.0
    intentos = int(getattr(f, "exploit_attempts", 0) or 0)
    explot = 1 + ex["w_kev"] * kev + ex["w_epss"] * epss + ex["w_attempts"] * (intentos > 0)
    expo = conf["exposure"].get(exposicion or "internal", conf["exposure"]["internal"])
    crit = conf["criticality"].get(criticidad or "medium", conf["criticality"]["medium"])
    primera = _utc(getattr(f, "first_seen_at", None)) or momento
    edad = max(0.0, (momento - primera).total_seconds() / 86400)
    f_edad = 1 + conf["age"]["w_age"] * min(1.0, edad / max(1, conf["age"]["age_cap_days"]))
    r = base * explot * expo * crit * f_edad * (1 - min(0.9, max(0.0, reduccion)))
    detalle_prev = _json(getattr(f, "score_detail", None), {}) or {}
    posible = bool(detalle_prev.get("possible"))
    if posible:
        r *= 0.5
    r = round(min(100.0, max(0.0, r)), 1)
    return r, {"base": base, "exploit": round(explot, 3), "exposure": expo, "criticality": crit,
               "age_days": round(edad, 1), "age": round(f_edad, 3), "reduction": round(reduccion, 3),
               "possible": posible, "risk": r}


def reducciones_activas(db: Session, org) -> dict[str, float]:
    """finding_id → reducción combinada de sus controles activos (1 − Π(1 − r), tope 0,9)."""
    from app.models.cmdb_riesgo import CompensatingControl
    hoy = date.today()
    salida: dict[str, float] = {}
    filas = _q(db, CompensatingControl, org).filter(CompensatingControl.status == "active",
                                                    CompensatingControl.expires_at >= hoy).all()
    queda: dict[str, float] = {}
    for c in filas:
        queda[c.finding_id] = queda.get(c.finding_id, 1.0) * (1 - max(0.0, min(0.9, c.reduction or 0)))
    for fid, q in queda.items():
        salida[fid] = round(min(0.9, 1 - q), 3)
    return salida


# ── Contexto de la empresa ───────────────────────────────────────────────────

@dataclass
class Hallazgo:
    f: object
    v: object
    r: float
    detalle: dict
    aceptado: bool
    severidad: str
    kev: bool
    epss: float
    intentos: int
    expuesto: bool
    cis: set = field(default_factory=set)
    clientes: set = field(default_factory=set)
    servicios: set = field(default_factory=set)
    apps: set = field(default_factory=set)
    superficies: set = field(default_factory=set)


@dataclass
class Contexto:
    conf: dict
    hallazgos: list
    instancias: dict          # id → instancia viva
    inst_ambitos: dict        # id → {"cis", "clientes", "servicios", "apps"}
    deriva: list              # [(instance_id, puntos, detalle)]
    eol: list                 # [(instance_id, puntos, detalle)]
    eventos: list             # [(evento, puntos)]
    cis: dict
    prods: dict
    clientes_por_ci: dict


def _cliente_de_proyectos(db, org, cis: dict) -> dict:
    from app.models.project import Project
    proyectos = {c.project_id for c in cis.values() if c.project_id}
    if not proyectos:
        return {}
    por_proyecto = dict(_q(db, Project, org).with_entities(Project.id, Project.client_id)
                        .filter(Project.id.in_(proyectos)).all())
    return {c.id: por_proyecto.get(c.project_id) for c in cis.values() if por_proyecto.get(c.project_id)}


def contexto(db: Session, org, conf: Optional[dict] = None, momento: Optional[datetime] = None) -> Contexto:
    from app.models.cmdb_riesgo import ExploitEvent
    from app.models.cmdb_software import (SoftwareInstance, SoftwareProduct, SoftwareVersion, Vulnerability,
                                          VulnerabilityFinding)
    from app.models.service_desk.cmdb import ConfigurationItem
    from app.services.cmdb_software.analisis import deriva, fin_de_vida
    from app.services.cmdb_software.correlacion import VIVOS
    conf = conf or aj.leer(db, org)
    momento = momento or ahora()
    prods = {p.id: p for p in _q(db, SoftwareProduct, org)}
    cis = {c.id: c for c in _q(db, ConfigurationItem, org).filter(ConfigurationItem.is_active.is_(True))}
    cliente_ci = _cliente_de_proyectos(db, org, cis)
    instancias = {i.id: i for i in _q(db, SoftwareInstance, org).filter(SoftwareInstance.is_active.is_(True),
                                                                        SoftwareInstance.status != "retired")}
    por_version: dict[str, list] = {}
    inst_ambitos: dict[str, dict] = {}
    for i in instancias.values():
        if i.version_id:
            por_version.setdefault(i.version_id, []).append(i)
        p = prods.get(i.product_id)
        inst_ambitos[i.id] = {
            "cis": {i.ci_id} if i.ci_id else set(),
            "clientes": {x for x in (i.client_id, cliente_ci.get(i.ci_id)) if x},
            "servicios": {x for x in (i.service_ci_id, p.service_ci_id if p else None) if x},
            "apps": {i.product_id}}
    versiones = {v.id: v.product_id for v in _q(db, SoftwareVersion, org)}
    hallazgos_q = _q(db, VulnerabilityFinding, org).filter(VulnerabilityFinding.status.in_(VIVOS)).all()
    vulns = {v.id: v for v in _q(db, Vulnerability, org).filter(
        Vulnerability.id.in_({f.vulnerability_id for f in hallazgos_q} or {""}))}
    reducciones = reducciones_activas(db, org)
    lista = []
    for f in hallazgos_q:
        v = vulns.get(f.vulnerability_id)
        detalle_prio = _json(f.score_detail, {}) or {}
        crit = detalle_prio.get("criticality_level") or (prods[f.product_id].criticality if f.product_id in prods
                                                          else "medium")
        r, det = riesgo_de_hallazgo(conf, v, f, crit, f.exposure or "internal", reducciones.get(f.id, 0.0), momento)
        h = Hallazgo(f=f, v=v, r=r, detalle=det, aceptado=f.status == "accepted", severidad=f.severity or "unknown",
                     kev=bool(v is not None and v.kev), epss=float(v.epss_score or 0) if v is not None else 0.0,
                     intentos=int(f.exploit_attempts or 0), expuesto=(f.exposure == "internet"))
        relacionadas = []
        if f.instance_id and f.instance_id in instancias:
            relacionadas = [instancias[f.instance_id]]
        elif f.parent_version_id:
            relacionadas = por_version.get(f.parent_version_id, [])
            if f.parent_version_id in versiones:
                h.apps.add(versiones[f.parent_version_id])
        h.apps.add(f.product_id)
        for i in relacionadas:
            amb = inst_ambitos[i.id]
            h.cis |= amb["cis"]
            h.clientes |= amb["clientes"]
            h.servicios |= amb["servicios"]
            h.apps |= amb["apps"]
        for ci_id in h.cis or {None}:
            h.superficies |= superficies_de_ci(cis.get(ci_id), f.exposure)
        lista.append(h)
    # Configuración: deriva e incumplimientos
    der = deriva(db, org)
    lista_deriva = [(x["id"], 1.0, {"kind": "drift", "changed_keys": x.get("changed_keys")}) for x in der["drift"]]
    for x in der["violations"]:
        for regla in x["violations"]:
            sev = (regla.get("severity") if isinstance(regla, dict) else None) or "medium"
            lista_deriva.append((x["instance_id"], _PESO_REGLA.get(sev, 0.4),
                                 {"kind": "violation", "baseline": x.get("baseline_name"), "rule": regla,
                                  "severity": sev}))
    # Fin de vida
    lista_eol = []
    for x in fin_de_vida(db, org, dias=0)["instances"]:
        if x.get("lifecycle") not in ("eol", "unsupported"):
            continue
        pts = 1.0 if x.get("environment") == "prod" else 0.5
        if x.get("product_category") == "os":
            pts *= 2
        lista_eol.append((x["id"], pts, {"kind": "eol", "lifecycle": x["lifecycle"], "product": x.get("product_name"),
                                         "version": x.get("version"), "eol_date": x.get("eol_date")}))
    # Señales: intentos de explotación de 30 días
    desde = momento - timedelta(days=30)
    eventos = [(e, _PESO_ACCION.get(e.action, 0.5)) for e in _q(db, ExploitEvent, org)
               .filter(ExploitEvent.observed_at >= desde)]
    return Contexto(conf=conf, hallazgos=lista, instancias=instancias, inst_ambitos=inst_ambitos,
                    deriva=lista_deriva, eol=lista_eol, eventos=eventos, cis=cis, prods=prods,
                    clientes_por_ci=cliente_ci)


# ── Ámbitos ──────────────────────────────────────────────────────────────────

def comprobar_ambito(tipo: Optional[str], id_: Optional[str]) -> tuple[str, str]:
    tipo = tipo or "org"
    if tipo not in AMBITOS:
        raise error(422, "swr_ambito_no_valido", ambito=tipo)
    if tipo != "org" and not id_:
        raise error(422, "swr_ambito_no_valido", ambito=tipo)
    return tipo, ("" if tipo == "org" else str(id_))


_CAMPO = {"machine": "cis", "client": "clientes", "service": "servicios", "application": "apps"}


@dataclass
class Subconjunto:
    hallazgos: list
    deriva: list
    eol: list
    eventos: list


def filtrar(ctx: Contexto, tipo: str, id_: str) -> Subconjunto:
    if tipo == "org":
        return Subconjunto(ctx.hallazgos, ctx.deriva, ctx.eol, ctx.eventos)
    campo = _CAMPO[tipo]

    def inst_ok(iid):
        amb = ctx.inst_ambitos.get(iid)
        return amb is not None and id_ in amb[campo]
    cis_del_ambito = set()
    for iid, amb in ctx.inst_ambitos.items():
        if id_ in amb[campo]:
            cis_del_ambito |= amb["cis"]
    if tipo == "machine":
        cis_del_ambito.add(id_)
    return Subconjunto(
        hallazgos=[h for h in ctx.hallazgos if id_ in getattr(h, campo)],
        deriva=[d for d in ctx.deriva if inst_ok(d[0])],
        eol=[d for d in ctx.eol if inst_ok(d[0])],
        eventos=[e for e in ctx.eventos if e[0].ci_id and e[0].ci_id in cis_del_ambito])


# ── Índice ───────────────────────────────────────────────────────────────────

def _s(p: float, k: float) -> float:
    return 100.0 * (1 - math.exp(-max(0.0, p) / max(0.01, k)))


def puntos_de_exploit(h: Hallazgo, conf: dict) -> float:
    return (1.0 if h.kev else 0.0) + (0.5 if h.epss >= conf["exploit"]["epss_threshold"] else 0.0) + \
        (1.0 if h.intentos > 0 else 0.0)


def activos_expuestos(h: Hallazgo) -> set:
    if h.aceptado or not h.expuesto or h.severidad not in ("critical", "high"):
        return set()
    return set(h.cis) or {f"f:{h.f.id}"}


def puntos(sub: Subconjunto, conf: dict, quitar: Optional[set] = None) -> dict:
    quitar = quitar or set()
    vivos = [h for h in sub.hallazgos if not h.aceptado and h.f.id not in quitar]
    expuestos: set = set()
    for h in vivos:
        expuestos |= activos_expuestos(h)
    return {"vulnerabilities": sum(h.r for h in vivos) / 100.0,
            "exploitation": sum(puntos_de_exploit(h, conf) for h in vivos),
            "exposure": float(len(expuestos)),
            "configuration": sum(d[1] for d in sub.deriva),
            "eol": sum(d[1] for d in sub.eol),
            "signals": sum(e[1] for e in sub.eventos)}


def indice_de_puntos(p: dict, conf: dict) -> float:
    return round(sum(conf["weights"][f] * _s(p[f], conf["saturation"][f]) for f in FACTORES), 1)


def indice(sub: Subconjunto, conf: dict) -> dict:
    p = puntos(sub, conf)
    factores = []
    for f in FACTORES:
        s = _s(p[f], conf["saturation"][f])
        factores.append({"key": f, "score": round(s, 1), "points": round(p[f], 3), "weight": conf["weights"][f],
                         "saturation": conf["saturation"][f], "contribution": round(conf["weights"][f] * s, 1)})
    aceptados = [h for h in sub.hallazgos if h.aceptado]
    aceptado = round(_s(sum(h.r for h in aceptados) / 100.0, conf["saturation"]["vulnerabilities"]), 1)
    vivos = [h for h in sub.hallazgos if not h.aceptado]
    expuestos: set = set()
    for h in vivos:
        expuestos |= activos_expuestos(h)
    cuenta = {"findings_live": len(vivos), "findings_accepted": len(aceptados),
              "kev": sum(1 for h in vivos if h.kev), "exploited": sum(1 for h in vivos if h.kev or h.intentos > 0),
              "internet_assets": len(expuestos),
              "drift": sum(1 for d in sub.deriva if d[2]["kind"] == "drift"),
              "violations": sum(1 for d in sub.deriva if d[2]["kind"] == "violation"),
              "eol": len(sub.eol), "exploit_events": len(sub.eventos),
              "controls_active": sum(1 for h in vivos if h.detalle.get("reduction"))}
    return {"score": indice_de_puntos(p, conf), "accepted_score": aceptado, "factors": factores, "counts": cuenta}


def _nombre(db, org, tipo: str, id_: str) -> Optional[str]:
    if tipo == "org":
        from app.models.mfa import Organization
        o = db.get(Organization, org) if org else None
        return getattr(o, "name", None)
    if tipo == "client":
        from app.models.clients import Client
        c = db.get(Client, id_)
        return c.name if c else None
    if tipo in ("machine", "service"):
        from app.models.service_desk.cmdb import ConfigurationItem
        c = db.get(ConfigurationItem, id_)
        return c.name if c else None
    from app.models.cmdb_software import SoftwareProduct
    p = db.get(SoftwareProduct, id_)
    return p.name if p else None


def _ultima_foto(db, org, tipo, id_, antes_de: Optional[date] = None):
    from app.models.cmdb_riesgo import RiskSnapshot
    q = _q(db, RiskSnapshot, org).filter(RiskSnapshot.scope_type == tipo, RiskSnapshot.scope_id == id_)
    if antes_de is not None:
        q = q.filter(RiskSnapshot.day <= antes_de)
    return q.order_by(RiskSnapshot.day.desc()).first()


def nivel(db, org, score: float) -> Optional[str]:
    from app.core.umbrales import nivel_de_riesgo
    try:
        return nivel_de_riesgo(score, db=db, org_id=org)
    except Exception:  # noqa: BLE001 - el nivel es informativo
        return "critical" if score >= 75 else "high" if score >= 50 else "medium" if score >= 25 else "low"


def indice_de_ambito(db: Session, org, tipo: Optional[str], id_: Optional[str],
                     ctx: Optional[Contexto] = None) -> dict:
    tipo, id_ = comprobar_ambito(tipo, id_)
    ctx = ctx or contexto(db, org)
    r = indice(filtrar(ctx, tipo, id_), ctx.conf)
    foto = _ultima_foto(db, org, tipo, id_)
    hace7 = _ultima_foto(db, org, tipo, id_, date.today() - timedelta(days=7))
    return {"scope_type": tipo, "scope_id": id_ or None, "scope_name": _nombre(db, org, tipo, id_), **r,
            "level": nivel(db, org, r["score"]), "target": ctx.conf["target"],
            "evaluated_at": foto.computed_at.isoformat() if foto is not None and foto.computed_at else None,
            "delta_7d": round(r["score"] - hace7.score, 1) if hace7 is not None else None}


def entidades(db: Session, org, ctx: Contexto, tipo: str, internos: Optional[bool] = None) -> list[str]:
    """Ids de las entidades de un tipo de ámbito que tienen algo en la CMDB de software."""
    ids: set = set()
    if tipo == "org":
        return [""]
    campo = _CAMPO[tipo]
    for amb in ctx.inst_ambitos.values():
        ids |= amb[campo]
    for h in ctx.hallazgos:
        ids |= getattr(h, campo)
    if tipo == "client":
        from app.models.clients import Client
        q = _q(db, Client, org).filter(Client.is_active.isnot(False))
        clientes = q.all()
        if internos is not None:
            clientes = [c for c in clientes if (getattr(c, "kind", None) == "interno") == internos]
            ids = {i for i in ids if i in {c.id for c in clientes}} | {c.id for c in clientes}
        else:
            ids |= {c.id for c in clientes}
    return sorted(i for i in ids if i)


def comparar(db: Session, org, tipo: str, internos: Optional[bool] = None, limite: int = 50) -> list[dict]:
    from app.models.cmdb_riesgo import RiskSnapshot
    if tipo not in AMBITOS or tipo == "org":
        raise error(422, "swr_ambito_no_valido", ambito=tipo)
    ctx = contexto(db, org)
    ids = entidades(db, org, ctx, tipo, internos)
    nombres, internas = {}, {}
    if tipo == "client":
        from app.models.clients import Client
        for c in _q(db, Client, org).filter(Client.id.in_(ids or [""])):
            nombres[c.id], internas[c.id] = c.name, getattr(c, "kind", None) == "interno"
    elif tipo in ("machine", "service"):
        nombres = {i: c.name for i, c in ctx.cis.items() if i in set(ids)}
    else:
        nombres = {i: p.name for i, p in ctx.prods.items() if i in set(ids)}
    fotos = {}
    for f in _q(db, RiskSnapshot, org).filter(RiskSnapshot.scope_type == tipo).order_by(RiskSnapshot.day.asc()):
        fotos[f.scope_id] = f
    salida = []
    for i in ids:
        r = indice(filtrar(ctx, tipo, i), ctx.conf)
        foto = fotos.get(i)
        salida.append({"scope_type": tipo, "scope_id": i, "name": nombres.get(i) or i,
                       "is_internal": internas.get(i, False), "score": r["score"], "level": nivel(db, org, r["score"]),
                       "accepted_score": r["accepted_score"], "findings_live": r["counts"]["findings_live"],
                       "evaluated_at": foto.computed_at.isoformat() if foto is not None and foto.computed_at else None})
    salida.sort(key=lambda x: (-x["score"], x["name"] or ""))
    return salida[:max(1, min(int(limite or 50), 1000))]


def historico(db: Session, org, tipo: Optional[str], id_: Optional[str], dias: int = 90) -> list[dict]:
    from app.models.cmdb_riesgo import RiskSnapshot
    tipo, id_ = comprobar_ambito(tipo, id_)
    desde = date.today() - timedelta(days=max(1, min(int(dias or 90), 3650)))
    filas = (_q(db, RiskSnapshot, org).filter(RiskSnapshot.scope_type == tipo, RiskSnapshot.scope_id == id_,
                                              RiskSnapshot.day >= desde).order_by(RiskSnapshot.day.asc()).all())
    return [{"day": f.day.isoformat(), "score": f.score, "accepted_score": f.accepted_score} for f in filas]


# ── Recalcular y guardar la foto del día ─────────────────────────────────────

def recalcular(db: Session, org, usuario=None, disparo: str = "manual") -> dict:
    """Riesgo de cada hallazgo + índice de todos los ámbitos + foto del día. No confirma."""
    from app.models.cmdb_riesgo import RiskSnapshot
    from app.services.audit import audit_log
    momento = ahora()
    hoy = momento.date()
    ctx = contexto(db, org, momento=momento)
    for h in ctx.hallazgos:
        h.f.risk_points = h.r
    existentes = {(f.scope_type, f.scope_id): f for f in _q(db, RiskSnapshot, org).filter(RiskSnapshot.day == hoy)}
    ambitos = 0
    org_score = None
    for tipo in AMBITOS:
        for id_ in entidades(db, org, ctx, tipo):
            r = indice(filtrar(ctx, tipo, id_), ctx.conf)
            if tipo != "org" and not r["counts"]["findings_live"] and not r["counts"]["findings_accepted"] \
                    and not r["counts"]["drift"] and not r["counts"]["violations"] and not r["counts"]["eol"] \
                    and not r["counts"]["exploit_events"]:
                # Ámbito sin nada que medir: foto en 0 solo si ya tenía histórico (para que la curva baje).
                if _ultima_foto(db, org, tipo, id_) is None:
                    continue
            foto = existentes.get((tipo, id_))
            if foto is None:
                foto = RiskSnapshot(organization_id=org, scope_type=tipo, scope_id=id_, day=hoy)
                db.add(foto)
            foto.score, foto.accepted_score = r["score"], r["accepted_score"]
            foto.factors = json.dumps({x["key"]: {"score": x["score"], "points": x["points"]} for x in r["factors"]})
            foto.counts = json.dumps(r["counts"])
            foto.computed_at = momento
            ambitos += 1
            if tipo == "org":
                org_score = r["score"]
    db.flush()
    if disparo == "manual":
        audit_log(db, usuario, "UPDATE", "sw_risk_index", org or "-", "Índice de riesgo",
                  metadata={"scopes": ambitos, "org_score": org_score, "trigger": disparo})
    return {"scopes": ambitos, "evaluated_at": momento.isoformat(), "org_score": org_score}


# ── Plan de reducción ────────────────────────────────────────────────────────

def _acciones(ctx: Contexto, h: Hallazgo) -> list[dict]:
    f = h.f
    prod = ctx.prods.get(f.product_id)
    nombre = prod.name if prod else f.product_id
    maquinas = ", ".join(sorted(ctx.cis[c].name for c in h.cis if c in ctx.cis)) or "—"
    if h.detalle.get("possible"):
        return [{"code": "possible", "params": {"product": nombre, "machines": maquinas}}]
    if f.fixed_version:
        return [{"code": "upgrade", "params": {"product": nombre, "from": f.affected_version or "?",
                                               "to": f.fixed_version, "machines": maquinas}}]
    acciones = [{"code": "no_fix", "params": {"product": nombre}}]
    if prod is not None and prod.lifecycle_status in ("deprecated", "retired"):
        acciones.append({"code": "retire", "params": {"product": nombre, "from": f.affected_version or "?",
                                                      "machines": maquinas}})
    acciones.append({"code": "control", "params": {"machines": maquinas}})
    return acciones


def plan(db: Session, org, tipo: Optional[str], id_: Optional[str], objetivo: Optional[float] = None,
         maximo: int = 200) -> dict:
    from app.services.cmdb_software.gestion import serializar
    tipo, id_ = comprobar_ambito(tipo, id_)
    ctx = contexto(db, org)
    conf = ctx.conf
    if objetivo is None or objetivo == "":
        objetivo = conf["target"]
    try:
        objetivo = float(objetivo)
    except (TypeError, ValueError):
        raise error(422, "swr_objetivo_no_valido")
    if not 0 <= objetivo <= 100:
        raise error(422, "swr_objetivo_no_valido")
    sub = filtrar(ctx, tipo, id_)
    p = puntos(sub, conf)
    actual = indice_de_puntos(p, conf)
    candidatos = {h.f.id: h for h in sub.hallazgos if not h.aceptado}
    activos: dict = {}
    for h in candidatos.values():
        for a in activos_expuestos(h):
            activos[a] = activos.get(a, 0) + 1
    pasos, ahora_idx = [], actual
    while ahora_idx > objetivo and candidatos and len(pasos) < maximo:
        mejor, mejor_idx = None, None
        for h in candidatos.values():
            q = dict(p)
            q["vulnerabilities"] -= h.r / 100.0
            q["exploitation"] -= puntos_de_exploit(h, conf)
            q["exposure"] -= sum(1 for a in activos_expuestos(h) if activos.get(a, 0) == 1)
            idx = indice_de_puntos(q, conf)
            if mejor is None or idx < mejor_idx or (idx == mejor_idx and h.r > mejor.r):
                mejor, mejor_idx = h, idx
        h = mejor
        p["vulnerabilities"] -= h.r / 100.0
        p["exploitation"] -= puntos_de_exploit(h, conf)
        for a in activos_expuestos(h):
            activos[a] -= 1
            if activos[a] == 0:
                p["exposure"] -= 1
        del candidatos[h.f.id]
        impacto = round(ahora_idx - mejor_idx, 2)
        ahora_idx = mejor_idx
        datos = serializar(db, h.f, v=h.v, org=org)
        datos["risk_points"] = h.r
        pasos.append({"finding": datos, "impact": impacto, "score_after": mejor_idx, "actions": _acciones(ctx, h),
                      "remediation": {"ticket_id": h.f.ticket_id, "change_id": h.f.change_id,
                                      "problem_id": h.f.problem_id, "task_id": h.f.task_id}})
    return {"scope_type": tipo, "scope_id": id_ or None, "current": actual, "target": objetivo,
            "reached": ahora_idx <= objetivo, "final_score": ahora_idx, "steps": pasos}


# ── Eventos de riesgo ────────────────────────────────────────────────────────

TIPOS_DE_EVENTO = ("finding", "drift", "violation", "eol", "exploit")


def eventos(db: Session, org, tipo: Optional[str], id_: Optional[str], clase: Optional[str] = None,
            pagina: int = 1, por_pagina: int = 50) -> dict:
    tipo, id_ = comprobar_ambito(tipo, id_)
    ctx = contexto(db, org)
    conf = ctx.conf
    sub = filtrar(ctx, tipo, id_)

    def impacto(factor: str, pts: float) -> float:
        # Contribución lineal al índice (cota superior de lo que sube por sí solo).
        return round(conf["weights"][factor] * 100.0 * pts / conf["saturation"][factor], 2)
    filas = []
    for h in sub.hallazgos:
        if h.aceptado:
            continue
        prod = ctx.prods.get(h.f.product_id)
        ci = next((ctx.cis[c] for c in h.cis if c in ctx.cis), None)
        filas.append({"kind": "finding", "id": h.f.id, "finding_id": h.f.id,
                      "title": (h.v.vuln_id if h.v else "?") + (f" · {h.v.title}" if h.v and h.v.title else ""),
                      "points": impacto("vulnerabilities", h.r / 100.0) + impacto("exploitation", puntos_de_exploit(h, conf)),
                      "severity": h.severidad, "ci_name": ci.name if ci else None,
                      "product_name": prod.name if prod else None,
                      "detail": {"risk": h.r, "kev": h.kev, "attempts": h.intentos, "status": h.f.status},
                      "occurred_at": h.f.first_seen_at.isoformat() if h.f.first_seen_at else None})
    for clase_x, lista, factor in (("config", sub.deriva, "configuration"), ("eol", sub.eol, "eol")):
        for iid, pts, det in lista:
            i = ctx.instancias.get(iid)
            prod = ctx.prods.get(i.product_id) if i else None
            ci = ctx.cis.get(i.ci_id) if i and i.ci_id else None
            filas.append({"kind": det["kind"], "id": f"{det['kind']}:{iid}:{len(filas)}", "finding_id": None,
                          "title": (prod.name if prod else "?") + (f" {i.version}" if i and i.version else ""),
                          "points": impacto(factor, pts), "severity": det.get("severity"),
                          "ci_name": ci.name if ci else None, "product_name": prod.name if prod else None,
                          "detail": det, "occurred_at": (i.drift_detected_at.isoformat() if det["kind"] == "drift"
                                                         and i is not None and i.drift_detected_at else None)})
    for e, pts in sub.eventos:
        ci = ctx.cis.get(e.ci_id) if e.ci_id else None
        filas.append({"kind": "exploit", "id": e.id, "finding_id": e.finding_id, "title": e.vuln_id or "?",
                      "points": impacto("signals", pts), "severity": None, "ci_name": ci.name if ci else e.host,
                      "product_name": None, "detail": {"action": e.action, "count": e.count, "source": e.source},
                      "occurred_at": e.observed_at.isoformat() if e.observed_at else None})
    if clase:
        filas = [x for x in filas if x["kind"] == clase]
    filas.sort(key=lambda x: -x["points"])
    total = len(filas)
    pagina, por_pagina = max(1, pagina), max(1, min(por_pagina, 500))
    return {"items": filas[(pagina - 1) * por_pagina: pagina * por_pagina], "total": total}
