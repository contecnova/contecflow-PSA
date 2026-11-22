"""Métricas de gestión de vulnerabilidades, superficies, listas agrupadas,
exposición a Internet y vistas guardadas (§11.6-11.7 del diseño).

- Activo = CI con software desplegado (instancia viva). Máquina = activo de
  tipo servidor, VM, endpoint, contenedor o nube. Interno = no expuesto a
  Internet.
- MTTP = media de `closed_at − first_seen_at` de los hallazgos resueltos en el
  periodo; antigüedad media = media de `ahora − first_seen_at` de los vivos.
- Impacto = prioridad del hallazgo con los rangos de `risk_settings.impact_ranges`.
"""
from __future__ import annotations

import ipaddress
import json
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.audit import audit_log
from app.services.cmdb_software.riesgo import calculo as calc

SUPERFICIES = ("internal", "internet", "container", "cloud_vm", "serverless")
PUERTOS_PUBLICOS = {21, 22, 23, 25, 53, 80, 110, 143, 389, 443, 445, 465, 587, 993, 995, 1433, 1521, 2375, 3000,
                    3306, 3389, 5000, 5432, 5601, 5900, 6379, 8000, 8080, 8443, 8888, 9000, 9200, 11211, 27017}
EXPOSICIONES = ("internet", "internal", "isolated")
COLUMNAS = ("priority", "risk", "vuln", "severity", "cvss", "epss", "kev", "sla", "software", "machine", "surface",
            "status", "detected_by", "controls", "attempts", "first_seen")


def _pct(a: int, b: int) -> Optional[float]:
    return round(100.0 * a / b, 1) if b else None


def _media(valores: list[float]) -> Optional[float]:
    return round(sum(valores) / len(valores), 1) if valores else None


def metricas(db: Session, org, tipo: Optional[str], id_: Optional[str], dias: int = 90) -> dict:
    from app.models.cmdb_software import VulnerabilityFinding
    tipo, id_ = calc.comprobar_ambito(tipo, id_)
    dias = max(1, min(int(dias or 90), 3650))
    ctx = calc.contexto(db, org)
    momento = calc.ahora()
    rangos = ctx.conf["impact_ranges"]
    # Activos del ámbito: CIs de las instancias vivas del ámbito
    campo = calc._CAMPO.get(tipo)
    activos: set = set()
    expuestos: set = set()
    for iid, amb in ctx.inst_ambitos.items():
        if campo and id_ not in amb[campo]:
            continue
        i = ctx.instancias[iid]
        activos |= amb["cis"]
        if i.exposure == "internet":
            expuestos |= amb["cis"]
    for ci_id in list(activos):
        if calc.atributos_ci(ctx.cis.get(ci_id)).get("exposure") == "internet":
            expuestos.add(ci_id)
    sub = calc.filtrar(ctx, tipo, id_)
    vivos = [h for h in sub.hallazgos if not h.aceptado]
    con_vulns: set = set()
    for h in vivos:
        con_vulns |= h.cis
    con_vulns &= activos
    maquinas = {c for c in activos if c in ctx.cis and getattr(ctx.cis[c].ci_type, "value", ctx.cis[c].ci_type)
                in calc.MAQUINAS}
    internos = activos - expuestos
    # MTTP: resueltos en el periodo (del ámbito)
    desde = momento - timedelta(days=dias)
    resueltos = calc._q(db, VulnerabilityFinding, org).filter(VulnerabilityFinding.status == "resolved",
                                                             VulnerabilityFinding.closed_at >= desde).all()
    if tipo != "org":
        ids_ambito = _ids_de_hallazgos_cerrados(ctx, resueltos, tipo, id_)
        resueltos = [f for f in resueltos if f.id in ids_ambito]
    mttp = [(calc._utc(f.closed_at) - calc._utc(f.first_seen_at)).total_seconds() / 86400
            for f in resueltos if f.closed_at and f.first_seen_at]
    edades = [(momento - calc._utc(h.f.first_seen_at)).total_seconds() / 86400 for h in vivos if h.f.first_seen_at]
    so_sin_soporte = {ctx.instancias[iid].ci_id for iid, _p, det in sub.eol
                      if iid in ctx.instancias and ctx.instancias[iid].ci_id
                      and (ctx.prods.get(ctx.instancias[iid].product_id) is not None
                           and ctx.prods[ctx.instancias[iid].product_id].category == "os")}
    impacto = {"high": 0, "medium": 0, "low": 0}
    for h in vivos:
        p = h.f.priority_score or 0
        impacto["high" if p >= rangos["high_from"] else "medium" if p >= rangos["medium_from"] else "low"] += 1
    estado = {"new": sum(1 for h in vivos if h.f.status == "open"),
              "in_progress": sum(1 for h in vivos if h.f.status in ("triaged", "in_progress", "mitigated")),
              "resolved": len(resueltos), "accepted": sum(1 for h in sub.hallazgos if h.aceptado)}
    return {"days": dias, "assets": len(activos), "assets_with_vulns": len(con_vulns),
            "pct_assets_with_vulns": _pct(len(con_vulns), len(activos)),
            "internal_assets": len(internos), "internal_with_vulns": len(con_vulns & internos),
            "pct_internal_with_vulns": _pct(len(con_vulns & internos), len(internos)),
            "machines": len(maquinas), "machines_with_vulns": len(con_vulns & maquinas),
            "pct_machines_with_vulns": _pct(len(con_vulns & maquinas), len(maquinas)),
            "density_per_asset": round(len(vivos) / len(activos), 2) if activos else None,
            "density_per_machine": round(sum(1 for h in vivos if h.cis & maquinas) / len(maquinas), 2)
            if maquinas else None,
            "mttp_days": _media(mttp), "mttp_sample": len(mttp), "avg_age_unpatched_days": _media(edades),
            "os_unsupported": len(so_sin_soporte), "by_impact": impacto,
            "impact_ranges": {"high_from": rangos["high_from"], "medium_from": rangos["medium_from"]},
            "by_state": estado}


def _ids_de_hallazgos_cerrados(ctx, filas, tipo, id_) -> set:
    campo = calc._CAMPO[tipo]
    salida = set()
    for f in filas:
        if tipo == "application" and f.product_id == id_:
            salida.add(f.id)
            continue
        amb = ctx.inst_ambitos.get(f.instance_id) if f.instance_id else None
        if amb is not None and id_ in amb[campo]:
            salida.add(f.id)
    return salida


# ── Superficies ──────────────────────────────────────────────────────────────

def superficies(db: Session, org) -> dict:
    ctx = calc.contexto(db, org)
    salida = {s: {"assets": set(), "findings": 0, "critical_high": 0} for s in SUPERFICIES}
    for iid, amb in ctx.inst_ambitos.items():
        i = ctx.instancias[iid]
        for ci_id in amb["cis"]:
            for s in calc.superficies_de_ci(ctx.cis.get(ci_id), i.exposure):
                salida[s]["assets"].add(ci_id)
    for h in ctx.hallazgos:
        if h.aceptado:
            continue
        for s in h.superficies:
            salida[s]["findings"] += 1
            salida[s]["critical_high"] += int(h.severidad in ("critical", "high"))
    return {s: {"assets": len(d["assets"]), "findings": d["findings"], "critical_high": d["critical_high"]}
            for s, d in salida.items()}


def hallazgos(db: Session, org, superficie: Optional[str] = None, agrupar: Optional[str] = None,
              severidad: Optional[str] = None, estado: Optional[str] = "live", q: Optional[str] = None,
              kev: Optional[bool] = None, pagina: int = 1, por_pagina: int = 50) -> dict:
    from app.services.cmdb_software.gestion import serializar
    if superficie and superficie not in SUPERFICIES:
        raise error(422, "swr_ajuste_no_valido", campo="surface")
    ctx = calc.contexto(db, org)
    lista = ctx.hallazgos
    if estado == "live" or not estado:
        lista = [h for h in lista if not h.aceptado] if estado == "live" else lista
    elif estado == "accepted":
        lista = [h for h in lista if h.aceptado]
    else:
        lista = [h for h in lista if h.f.status == estado]
    if superficie:
        lista = [h for h in lista if superficie in h.superficies]
    if severidad:
        sevs = set(severidad.split(","))
        lista = [h for h in lista if h.severidad in sevs]
    if kev:
        lista = [h for h in lista if h.kev]
    if q:
        t = q.strip().lower()
        lista = [h for h in lista if t in ((h.v.vuln_id if h.v else "") + " " + (h.v.title or "" if h.v else "") + " "
                                           + (ctx.prods[h.f.product_id].name if h.f.product_id in ctx.prods else "")
                                           + " " + " ".join(ctx.cis[c].name for c in h.cis if c in ctx.cis)).lower()]
    pagina, por_pagina = max(1, pagina), max(1, min(por_pagina, 500))
    if agrupar == "cve":
        grupos: dict = {}
        for h in lista:
            g = grupos.setdefault(h.f.vulnerability_id, {
                "vulnerability_id": h.f.vulnerability_id, "vuln_id": h.v.vuln_id if h.v else None,
                "title": h.v.title if h.v else None, "severity": h.severidad,
                "cvss_score": h.v.cvss_score if h.v else None, "epss_score": h.v.epss_score if h.v else None,
                "kev": h.kev, "assets": set(), "findings": 0, "max_risk": 0.0, "products": set()})
            g["assets"] |= h.cis
            g["findings"] += 1
            g["max_risk"] = max(g["max_risk"], h.r)
            if h.f.product_id in ctx.prods:
                g["products"].add(ctx.prods[h.f.product_id].name)
        filas = sorted(grupos.values(), key=lambda g: -g["max_risk"])
        filas = [{**g, "assets": len(g["assets"]), "products": sorted(g["products"])} for g in filas]
    elif agrupar == "asset":
        grupos = {}
        for h in lista:
            for ci_id in h.cis or {None}:
                ci = ctx.cis.get(ci_id)
                clave = ci_id or "-"
                g = grupos.setdefault(clave, {
                    "ci_id": ci_id, "ci_name": ci.name if ci else None, "ci_hostname": ci.hostname if ci else None,
                    "surface": sorted(calc.superficies_de_ci(ci, h.f.exposure)), "exposure": h.f.exposure,
                    "findings": 0, "critical": 0, "high": 0, "max_risk": 0.0})
                g["findings"] += 1
                g["critical"] += int(h.severidad == "critical")
                g["high"] += int(h.severidad == "high")
                g["max_risk"] = max(g["max_risk"], h.r)
                if h.f.exposure == "internet":
                    g["exposure"] = "internet"
        filas = sorted(grupos.values(), key=lambda g: -g["max_risk"])
    else:
        lista = sorted(lista, key=lambda h: (-h.r, -(h.f.priority_score or 0)))
        trozo = lista[(pagina - 1) * por_pagina: pagina * por_pagina]
        items = []
        for h in trozo:
            d = serializar(db, h.f, v=h.v, org=org)
            d.update(risk_points=h.r, surface=sorted(h.superficies), detected_by=calc._json(h.f.detected_by, []) or [],
                     controls_active=1 if h.detalle.get("reduction") else 0, exploit_attempts=h.intentos)
            items.append(d)
        return {"items": items, "total": len(lista)}
    return {"items": filas[(pagina - 1) * por_pagina: pagina * por_pagina], "total": len(filas)}


# ── Exposición ───────────────────────────────────────────────────────────────

def ip_publica(ip: Optional[str]) -> bool:
    try:
        d = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return False
    return d.is_global


def detectar_exposicion(db: Session, org, usuario=None) -> dict:
    """Puertos públicos en IP pública → `internet` (`exposure_source = ports`). No pisa lo manual ni el CI."""
    from app.models.cmdb_software import SoftwareInstance
    from app.models.service_desk.cmdb import ConfigurationItem
    from app.services.cmdb_software.correlacion import reevaluar
    instancias = calc._q(db, SoftwareInstance, org).filter(SoftwareInstance.is_active.is_(True),
                                                          SoftwareInstance.status != "retired").all()
    cis = {c.id: c for c in calc._q(db, ConfigurationItem, org).filter(
        ConfigurationItem.id.in_({i.ci_id for i in instancias if i.ci_id} or {""}))}
    revisadas = marcadas = 0
    for i in instancias:
        revisadas += 1
        ci = cis.get(i.ci_id)
        if ci is None or i.exposure_source in ("manual", "ci") or i.exposure == "internet":
            continue
        if calc.atributos_ci(ci).get("exposure"):
            continue
        puertos = set()
        for p in calc._json(i.ports, []) or []:
            try:
                puertos.add(int(str(p).split("/")[0]))
            except ValueError:
                continue
        if puertos & PUERTOS_PUBLICOS and ip_publica(ci.ip_address):
            i.exposure, i.exposure_source = "internet", "ports"
            marcadas += 1
    db.flush()
    if marcadas:
        reevaluar(db, org, usuario)
    audit_log(db, usuario, "UPDATE", "sw_exposure", org or "-", "Detección de exposición",
              metadata={"checked": revisadas, "set_internet": marcadas})
    return {"checked": revisadas, "set_internet": marcadas, "unchanged": revisadas - marcadas}


def marcar_ci(db: Session, org, ci_id: str, exposicion: Optional[str], usuario=None) -> dict:
    """Marca la exposición del CI (`attributes.exposure`) y la aplica a sus instancias."""
    from app.models.cmdb_software import SoftwareInstance
    from app.services.cmdb_software import catalogo as cat
    from app.services.cmdb_software.correlacion import reevaluar
    if exposicion not in (None, "", *EXPOSICIONES):
        raise error(422, "swr_exposicion_no_valida", valor=exposicion)
    ci = cat.ci(db, org, ci_id)
    attrs = calc.atributos_ci(ci)
    antes = attrs.get("exposure")
    if exposicion:
        attrs["exposure"] = exposicion
    else:
        attrs.pop("exposure", None)
    ci.attributes = json.dumps(attrs)
    for i in calc._q(db, SoftwareInstance, org).filter(SoftwareInstance.ci_id == ci.id,
                                                      SoftwareInstance.is_active.is_(True)):
        if exposicion:
            i.exposure, i.exposure_source = exposicion, "ci"
        elif i.exposure_source == "ci":
            i.exposure_source = None
    db.flush()
    reevaluar(db, org, usuario)
    audit_log(db, usuario, "UPDATE", "sw_ci_exposure", ci.id, ci.name, old_values={"exposure": antes},
              new_values={"exposure": exposicion or None})
    return {"ci_id": ci.id, "exposure": exposicion or None}


# ── Vistas guardadas ─────────────────────────────────────────────────────────

def _vista_dict(v, usuario_id) -> dict:
    return {"id": v.id, "name": v.name, "surface": v.surface, "group_by": v.group_by,
            "filters": calc._json(v.filters, {}) or {}, "columns": calc._json(v.columns, []) or [],
            "shared": bool(v.shared), "owner_user_id": v.owner_user_id, "mine": v.owner_user_id == usuario_id}


def vistas(db: Session, org, usuario) -> list[dict]:
    from sqlalchemy import or_
    from app.models.cmdb_riesgo import SavedVulnView
    filas = (calc._q(db, SavedVulnView, org)
             .filter(or_(SavedVulnView.owner_user_id == usuario.id, SavedVulnView.shared.is_(True)))
             .order_by(SavedVulnView.name).all())
    return [_vista_dict(v, usuario.id) for v in filas]


def _validar_vista(d: dict) -> dict:
    salida = {}
    if "name" in d:
        nombre = (d.get("name") or "").strip()
        if len(nombre) < 2:
            raise error(422, "sw_nombre_obligatorio")
        salida["name"] = nombre[:120]
    if "surface" in d:
        if d["surface"] not in (None, "", *SUPERFICIES):
            raise error(422, "swr_ajuste_no_valido", campo="surface")
        salida["surface"] = d["surface"] or None
    if "group_by" in d:
        if d["group_by"] not in (None, "", "none", "cve", "asset"):
            raise error(422, "swr_ajuste_no_valido", campo="group_by")
        salida["group_by"] = None if d["group_by"] in (None, "", "none") else d["group_by"]
    if "filters" in d:
        if not isinstance(d["filters"] or {}, dict):
            raise error(422, "swr_ajuste_no_valido", campo="filters")
        salida["filters"] = json.dumps({str(k)[:40]: str(v)[:200] for k, v in (d["filters"] or {}).items()
                                        if v not in (None, "")})
    if "columns" in d:
        cols = d["columns"] or []
        if not isinstance(cols, list) or any(c not in COLUMNAS for c in cols):
            raise error(422, "swr_ajuste_no_valido", campo="columns")
        salida["columns"] = json.dumps(list(dict.fromkeys(cols)))
    if "shared" in d:
        salida["shared"] = bool(d["shared"])
    return salida


def vista(db, org, id_):
    from app.models.cmdb_riesgo import SavedVulnView
    v = calc._q(db, SavedVulnView, org).filter(SavedVulnView.id == id_).first() if id_ else None
    if v is None:
        raise error(404, "swr_vista_no_encontrada")
    return v


def crear_vista(db: Session, org, datos: dict, usuario) -> dict:
    from app.models.cmdb_riesgo import SavedVulnView
    if "name" not in datos:
        raise error(422, "sw_nombre_obligatorio")
    v = SavedVulnView(organization_id=org, owner_user_id=usuario.id, **_validar_vista(datos))
    db.add(v)
    db.flush()
    if v.shared:
        audit_log(db, usuario, "CREATE", "sw_saved_view", v.id, v.name, new_values=_vista_dict(v, usuario.id))
    return _vista_dict(v, usuario.id)


def cambiar_vista(db: Session, org, id_: str, datos: dict, usuario) -> dict:
    v = vista(db, org, id_)
    if v.owner_user_id != usuario.id:
        raise error(403, "swr_vista_ajena")
    antes = _vista_dict(v, usuario.id)
    for k, val in _validar_vista(datos).items():
        setattr(v, k, val)
    db.flush()
    if v.shared or antes["shared"]:
        audit_log(db, usuario, "UPDATE", "sw_saved_view", v.id, v.name, old_values=antes,
                  new_values=_vista_dict(v, usuario.id))
    return _vista_dict(v, usuario.id)


def borrar_vista(db: Session, org, id_: str, usuario) -> None:
    v = vista(db, org, id_)
    if v.owner_user_id != usuario.id:
        raise error(403, "swr_vista_ajena")
    if v.shared:
        audit_log(db, usuario, "DELETE", "sw_saved_view", v.id, v.name)
    db.delete(v)
    db.flush()
