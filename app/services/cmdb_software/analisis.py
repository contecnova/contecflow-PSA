"""Análisis: catálogo con cifras, ficha, dónde se usa, árbol, impacto, fin de vida,
deriva, licencias, cuadro de mando, vista por máquina, grafo y exportación.

Todo de solo lectura y acotado a la empresa.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.cmdb_software import (SoftwareBaseline, SoftwareComponent, SoftwareInstance,
                                      SoftwareInstanceRelation, SoftwareProduct, SoftwareProductLicense,
                                      SoftwareVersion, Vulnerability, VulnerabilityException, VulnerabilityFinding)
from app.models.service_desk.cmdb import CIRelation, ConfigurationItem
from app.services.cmdb_software import ajustes, catalogo as cat, configuracion as cfg, identificadores as ids
from app.services.cmdb_software import licencias as lic
from app.services.cmdb_software.correlacion import ABIERTOS, ORDEN_SEV, VIVOS
from app.services.cmdb_software.versiones import Version, cumple, valida


def _q(db, modelo, org):
    q = db.query(modelo)
    return q.filter(modelo.organization_id == org) if org else q


def _valor(x):
    return getattr(x, "value", x)


def _ci_breve(c: Optional[ConfigurationItem]) -> Optional[dict]:
    if c is None:
        return None
    return {"id": c.id, "code": c.code, "name": c.name, "ci_type": _valor(c.ci_type), "hostname": c.hostname,
            "ip_address": c.ip_address, "environment": c.environment, "criticality": c.criticality,
            "owner_user_id": c.owner_user_id, "status": _valor(c.status)}


def _peor(severidades) -> Optional[str]:
    vals = [s for s in severidades if s]
    return max(vals, key=lambda s: ORDEN_SEV.get(s, 0)) if vals else None


class _Ciclos:
    """Memoriza el ciclo de vida (versión exacta o rama) de (producto, versión)."""

    def __init__(self, db, org, avisar_dias: int = 90):
        self.db, self.org, self.memo = db, org, {}
        self.hoy = date.today()
        self.limite = self.hoy + timedelta(days=avisar_dias)

    def estado(self, product_id: str, version: Optional[str]) -> dict:
        clave = (product_id, version)
        if clave not in self.memo:
            fila = cat.ciclo_de_vida(self.db, self.org, product_id, version)
            estado = None
            if fila is not None:
                if fila.eol_date and fila.eol_date < self.hoy:
                    estado = "eol"
                elif fila.support_end and fila.support_end < self.hoy:
                    estado = "unsupported"
                elif (fila.eol_date and fila.eol_date <= self.limite) or (fila.support_end and fila.support_end <= self.limite):
                    estado = "soon"
            self.memo[clave] = {"lifecycle": estado,
                                "eol_date": fila.eol_date.isoformat() if fila is not None and fila.eol_date else None,
                                "support_end": fila.support_end.isoformat() if fila is not None and fila.support_end
                                else None, "cycle": fila.cycle if fila is not None else None}
        return self.memo[clave]


def _hallazgos_vivos_por(db, org, campo) -> dict:
    filas = (_q(db, VulnerabilityFinding, org).with_entities(campo, VulnerabilityFinding.severity, func.count())
             .filter(VulnerabilityFinding.status.in_(VIVOS), campo.isnot(None))
             .group_by(campo, VulnerabilityFinding.severity).all())
    salida: dict = {}
    for k, sev, n in filas:
        d = salida.setdefault(k, {"count": 0, "worst": None})
        d["count"] += n
        d["worst"] = _peor([d["worst"], sev])
    return salida


# ── Catálogo ─────────────────────────────────────────────────────────────────

def listar_productos(db: Session, org, q: Optional[str] = None, categoria: Optional[str] = None,
                     origen: Optional[str] = None, ciclo: Optional[str] = None, incluir_retirados: bool = False,
                     solo_aplicaciones: bool = False, pagina: int = 1, por_pagina: int = 50) -> dict:
    consulta = _q(db, SoftwareProduct, org)
    if not incluir_retirados:
        consulta = consulta.filter(SoftwareProduct.is_active.is_(True))
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.filter(or_(SoftwareProduct.name.ilike(patron), SoftwareProduct.vendor_name.ilike(patron),
                                       SoftwareProduct.match_key.ilike(patron), SoftwareProduct.aliases.ilike(patron)))
    if categoria:
        consulta = consulta.filter(SoftwareProduct.category.in_(categoria.split(",")))
    if origen:
        consulta = consulta.filter(SoftwareProduct.origin.in_(origen.split(",")))
    if ciclo:
        consulta = consulta.filter(SoftwareProduct.lifecycle_status == ciclo)
    if solo_aplicaciones:
        consulta = consulta.filter(or_(SoftwareProduct.origin.in_(("purchased", "saas", "in_house")),
                                       SoftwareProduct.category.notin_(("library",))))
    total = consulta.count()
    filas = consulta.order_by(SoftwareProduct.name).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    ids_ = [p.id for p in filas]
    versiones = dict(_q(db, SoftwareVersion, org).with_entities(SoftwareVersion.product_id, func.count())
                     .filter(SoftwareVersion.product_id.in_(ids_ or [""])).group_by(SoftwareVersion.product_id).all())
    instancias = dict(_q(db, SoftwareInstance, org).with_entities(SoftwareInstance.product_id, func.count())
                      .filter(SoftwareInstance.product_id.in_(ids_ or [""]), SoftwareInstance.is_active.is_(True))
                      .group_by(SoftwareInstance.product_id).all())
    maquinas = dict(_q(db, SoftwareInstance, org).with_entities(SoftwareInstance.product_id,
                                                                func.count(func.distinct(SoftwareInstance.ci_id)))
                    .filter(SoftwareInstance.product_id.in_(ids_ or [""]), SoftwareInstance.is_active.is_(True))
                    .group_by(SoftwareInstance.product_id).all())
    usado_en = dict(_q(db, SoftwareComponent, org).with_entities(SoftwareComponent.component_product_id,
                                                                 func.count(func.distinct(SoftwareComponent.parent_version_id)))
                    .filter(SoftwareComponent.component_product_id.in_(ids_ or [""]))
                    .group_by(SoftwareComponent.component_product_id).all())
    hallazgos = _hallazgos_vivos_por(db, org, VulnerabilityFinding.product_id)
    return {"items": [cat.serializar_producto(p, {
        "versions_count": versiones.get(p.id, 0), "instances_count": instancias.get(p.id, 0),
        "machines_count": maquinas.get(p.id, 0), "used_in_count": usado_en.get(p.id, 0),
        "open_findings": hallazgos.get(p.id, {}).get("count", 0),
        "worst_severity": hallazgos.get(p.id, {}).get("worst")}) for p in filas],
        "total": total, "page": pagina, "page_size": por_pagina}


def ficha(db: Session, org, p: SoftwareProduct) -> dict:
    from app.models.user import User
    conf = ajustes.leer(db, org)
    ciclos = _Ciclos(db, org, int(conf.get("eol_warning_days") or 90))
    versiones = _q(db, SoftwareVersion, org).filter(SoftwareVersion.product_id == p.id).all()
    versiones.sort(key=lambda v: Version(v.version), reverse=True)
    inst = _q(db, SoftwareInstance, org).filter(SoftwareInstance.product_id == p.id).all()
    cis = {c.id: c for c in _q(db, ConfigurationItem, org).filter(
        ConfigurationItem.id.in_([i.ci_id for i in inst if i.ci_id] or [""]))}
    por_version_inst: dict = {}
    for i in inst:
        if i.is_active:
            por_version_inst[i.version_id] = por_version_inst.get(i.version_id, 0) + 1
    comps_por_version = dict(_q(db, SoftwareComponent, org).with_entities(SoftwareComponent.parent_version_id,
                                                                          func.count())
                             .filter(SoftwareComponent.parent_version_id.in_([v.id for v in versiones] or [""]))
                             .group_by(SoftwareComponent.parent_version_id).all())
    hallazgos_inst = _hallazgos_vivos_por(db, org, VulnerabilityFinding.instance_id)
    hallazgos_ver = _hallazgos_vivos_por(db, org, VulnerabilityFinding.parent_version_id)
    # Dónde se usa como componente
    usado = []
    for c, pv, pp in (db.query(SoftwareComponent, SoftwareVersion, SoftwareProduct)
                      .join(SoftwareVersion, SoftwareVersion.id == SoftwareComponent.parent_version_id)
                      .join(SoftwareProduct, SoftwareProduct.id == SoftwareVersion.product_id)
                      .filter(SoftwareComponent.component_product_id == p.id,
                              *( [SoftwareComponent.organization_id == org] if org else []))
                      .limit(500)):
        usado.append({"product_id": pp.id, "product_name": pp.name, "version_id": pv.id, "version": pv.version,
                      "component_version": c.component_version, "direct": c.direct, "relation": c.relation,
                      **ciclos.estado(p.id, c.component_version)})
    dueno = db.get(User, p.owner_user_id) if p.owner_user_id else None
    resumen_hallazgos = (_q(db, VulnerabilityFinding, org).with_entities(VulnerabilityFinding.severity, func.count())
                         .filter(VulnerabilityFinding.status.in_(VIVOS),
                                 or_(VulnerabilityFinding.product_id == p.id,
                                     VulnerabilityFinding.parent_version_id.in_([v.id for v in versiones] or [""])))
                         .group_by(VulnerabilityFinding.severity).all())
    return {
        "product": cat.serializar_producto(p, {"owner_name": dueno.full_name if dueno else None}),
        "versions": [cat.serializar_version(v, {"instances_count": por_version_inst.get(v.id, 0),
                                                "components_count": comps_por_version.get(v.id, 0),
                                                "open_findings": hallazgos_ver.get(v.id, {}).get("count", 0),
                                                **ciclos.estado(p.id, v.version)}) for v in versiones],
        "instances": [cat.serializar_instancia(i, p, cis.get(i.ci_id), {
            "open_findings": hallazgos_inst.get(i.id, {}).get("count", 0),
            "worst_severity": hallazgos_inst.get(i.id, {}).get("worst"), **ciclos.estado(p.id, i.version)})
            for i in inst],
        "used_in": usado,
        "licenses": cat.licencias_de(db, org, p),
        "baselines": [cat.serializar_linea_base(b) for b in _q(db, SoftwareBaseline, org)
                      .filter(SoftwareBaseline.product_id == p.id)],
        "findings_by_severity": {s: n for s, n in resumen_hallazgos},
    }


# ── Dónde se usa ─────────────────────────────────────────────────────────────

_CONSULTA = re.compile(r"^\s*(?P<nombre>.+?)\s*(?P<op><=|>=|==|=|<|>|~|!=)\s*(?P<version>[\w.\-+:~]+)\s*$")
_OPS = {"<": "lt", "<=": "le", "=": "eq", "==": "eq", ">=": "ge", ">": "gt", "~": "prefix", "!=": "ne"}


def productos_que_casan(db: Session, org, texto: str) -> list[SoftwareProduct]:
    texto = (texto or "").strip()
    if not texto:
        return []
    p = ids.parsear_purl(texto)
    if p:
        clave = "purl:" + p.clave()
        return _q(db, SoftwareProduct, org).filter(SoftwareProduct.match_key == clave).all()
    c = ids.parsear_cpe(texto)
    if c:
        return _q(db, SoftwareProduct, org).filter(SoftwareProduct.cpe_vendor == c.vendor,
                                                   SoftwareProduct.cpe_product == c.product).all()
    patron = f"%{texto}%"
    candidatos = _q(db, SoftwareProduct, org).filter(or_(
        SoftwareProduct.name.ilike(patron), SoftwareProduct.purl_name.ilike(patron),
        SoftwareProduct.cpe_product.ilike(patron), SoftwareProduct.aliases.ilike(patron))).all()
    base = ids.conocido(texto)
    if base:
        d = ids.CONOCIDOS[base]
        candidatos += _q(db, SoftwareProduct, org).filter(SoftwareProduct.cpe_vendor == d["cpe"][0],
                                                          SoftwareProduct.cpe_product == d["cpe"][1]).all()
    exacto = ids.normalizar_texto(texto)
    unicos = {x.id: x for x in candidatos}
    # Primero los que se llaman exactamente así («php» antes que «phpunit»).
    return sorted(unicos.values(), key=lambda x: (ids.normalizar_texto(x.name) != exacto
                                                  and ids.normalizar_texto(x.purl_name) != exacto, x.name))


def donde_se_usa(db: Session, org, q: str, op: Optional[str] = None, version: Optional[str] = None,
                 entorno: Optional[str] = None, exactos: bool = False, limite: int = 2000) -> dict:
    """«¿Dónde está nginx?», «¿qué usa PHP < 8.2?», «pkg:npm/lodash»."""
    m = _CONSULTA.match(q or "")
    if m and not version:
        q, op, version = m.group("nombre"), _OPS[m.group("op")], m.group("version")
    op = op or "eq"
    productos = productos_que_casan(db, org, q)
    if exactos and productos:
        exacto = ids.normalizar_texto(q)
        iguales = [p for p in productos if exacto in (ids.normalizar_texto(p.name), ids.normalizar_texto(p.purl_name))]
        productos = iguales or productos
    conf = ajustes.leer(db, org)
    ciclos = _Ciclos(db, org, int(conf.get("eol_warning_days") or 90))
    prod_ids = [p.id for p in productos]
    nombres = {p.id: p.name for p in productos}
    instancias_q = _q(db, SoftwareInstance, org).filter(SoftwareInstance.product_id.in_(prod_ids or [""]),
                                                        SoftwareInstance.is_active.is_(True))
    if entorno:
        instancias_q = instancias_q.filter(SoftwareInstance.environment == entorno)
    instancias = [i for i in instancias_q.limit(limite) if cumple(i.version, op, version)]
    comps = [c for c in _q(db, SoftwareComponent, org).filter(
        SoftwareComponent.component_product_id.in_(prod_ids or [""])).limit(limite)
        if cumple(c.component_version, op, version)]
    versiones_padre = {v.id: v for v in _q(db, SoftwareVersion, org).filter(
        SoftwareVersion.id.in_({c.parent_version_id for c in comps} or {""}))}
    productos_padre = {p.id: p for p in _q(db, SoftwareProduct, org).filter(
        SoftwareProduct.id.in_({v.product_id for v in versiones_padre.values()} or {""}))}
    # Dónde corren las versiones de software que lo llevan
    inst_padre = _q(db, SoftwareInstance, org).filter(SoftwareInstance.version_id.in_(list(versiones_padre) or [""]),
                                                      SoftwareInstance.is_active.is_(True))
    if entorno:
        inst_padre = inst_padre.filter(SoftwareInstance.environment == entorno)
    inst_padre = inst_padre.all()
    cis = {c.id: c for c in _q(db, ConfigurationItem, org).filter(
        ConfigurationItem.id.in_({i.ci_id for i in instancias + inst_padre if i.ci_id} or {""}))}
    hallazgos = _hallazgos_vivos_por(db, org, VulnerabilityFinding.instance_id)
    salida_inst = []
    for i in instancias:
        config = json.loads(i.config_json) if i.config_json else {}
        salida_inst.append({**cat.serializar_instancia(i, None, cis.get(i.ci_id)), "product_name": nombres.get(i.product_id),
                            "config_summary": {k: config.get(k) for k in ("ports", "tls_protocols", "modules",
                                                                         "server_tokens", "upstreams") if k in config},
                            "open_findings": hallazgos.get(i.id, {}).get("count", 0),
                            **ciclos.estado(i.product_id, i.version)})
    por_padre: dict = {}
    for c in comps:
        pv = versiones_padre.get(c.parent_version_id)
        pp = productos_padre.get(pv.product_id) if pv else None
        if not pv or not pp:
            continue
        d = por_padre.setdefault(pv.id, {"product_id": pp.id, "product_name": pp.name, "origin": pp.origin,
                                         "version_id": pv.id, "version": pv.version, "components": [],
                                         "machines": []})
        d["components"].append({"component_id": c.id, "name": nombres.get(c.component_product_id),
                                "version": c.component_version, "direct": c.direct, "relation": c.relation,
                                **ciclos.estado(c.component_product_id, c.component_version)})
    for i in inst_padre:
        d = por_padre.get(i.version_id)
        if d is not None and i.ci_id:
            d["machines"].append({**(_ci_breve(cis.get(i.ci_id)) or {}), "instance_id": i.id,
                                  "environment": i.environment})
    maquinas = {i.ci_id for i in instancias if i.ci_id} | {i.ci_id for i in inst_padre if i.ci_id}
    distribucion: dict = {}
    for v in [i.version for i in instancias] + [c.component_version for c in comps]:
        distribucion[v or "?"] = distribucion.get(v or "?", 0) + 1
    return {"query": q, "op": op, "version": version,
            "products": [{"id": p.id, "name": p.name, "category": p.category, "match_key": p.match_key}
                         for p in productos],
            "instances": salida_inst, "software": list(por_padre.values()),
            "machines": [_ci_breve(cis[c]) for c in maquinas if c in cis],
            "versions": dict(sorted(distribucion.items(), key=lambda kv: Version(kv[0]), reverse=True)),
            "summary": {"instances": len(salida_inst), "software": len(por_padre), "machines": len(maquinas),
                        "components": len(comps)}}


# ── Árbol de dependencias ────────────────────────────────────────────────────

def arbol(db: Session, org, v: SoftwareVersion) -> dict:
    conf = ajustes.leer(db, org)
    ciclos = _Ciclos(db, org, int(conf.get("eol_warning_days") or 90))
    p = db.get(SoftwareProduct, v.product_id)
    comps = _q(db, SoftwareComponent, org).filter(SoftwareComponent.parent_version_id == v.id).all()
    prods = {x.id: x for x in _q(db, SoftwareProduct, org).filter(
        SoftwareProduct.id.in_({c.component_product_id for c in comps} or {""}))}
    hallazgos = _hallazgos_vivos_por(db, org, VulnerabilityFinding.component_id)
    hijos: dict = {}
    for c in comps:
        hijos.setdefault(c.via_component_id if c.via_component_id else None, []).append(c)
    ids_ = {c.id for c in comps}
    raices = [c for c in comps if not c.via_component_id or c.via_component_id not in ids_]

    def nodo(c, profundidad=0, vistos=frozenset()):
        prod = prods.get(c.component_product_id)
        familia = lic.familia_de_expresion(c.license_spdx or (prod.license_spdx if prod else None))
        evaluacion = lic.evaluar(c.license_spdx or (prod.license_spdx if prod else None), p.distribution if p else None,
                                 p.origin if p else None, conf.get("licenses_allowed"), conf.get("licenses_denied"),
                                 p.license_spdx if p else None)
        return {"id": c.id, "product_id": c.component_product_id, "name": prod.name if prod else None,
                "category": prod.category if prod else None, "version": c.component_version,
                "relation": c.relation, "scope": c.scope, "direct": c.direct, "purl": c.purl,
                "license": c.license_spdx or (prod.license_spdx if prod else None), "license_family": familia,
                "license_issue": evaluacion,
                "open_findings": hallazgos.get(c.id, {}).get("count", 0),
                "worst_severity": hallazgos.get(c.id, {}).get("worst"),
                **ciclos.estado(c.component_product_id, c.component_version),
                "children": [nodo(h, profundidad + 1, vistos | {c.id}) for h in hijos.get(c.id, [])
                             if h.id not in vistos and profundidad < 25]}
    orden = {"runtime": 0, "language": 0, "base_image": 1, "framework": 2, "service": 3, "driver": 4, "library": 5}
    raices.sort(key=lambda c: (orden.get(c.relation, 9), not c.direct, (prods.get(c.component_product_id).name
                                                                     if prods.get(c.component_product_id) else "")))
    instancias = _q(db, SoftwareInstance, org).filter(SoftwareInstance.version_id == v.id,
                                                      SoftwareInstance.is_active.is_(True)).all()
    cis = {c.id: c for c in _q(db, ConfigurationItem, org).filter(
        ConfigurationItem.id.in_({i.ci_id for i in instancias if i.ci_id} or {""}))}
    return {"product": cat.serializar_producto(p) if p else None, "version": cat.serializar_version(v),
            "tree": [nodo(c) for c in raices],
            "summary": {"components": len(comps), "direct": sum(1 for c in comps if c.direct),
                        "transitive": sum(1 for c in comps if not c.direct)},
            "deployed_on": [{**cat.serializar_instancia(i, p, cis.get(i.ci_id))} for i in instancias]}


# ── Impacto ──────────────────────────────────────────────────────────────────

def cis_afectados_por_fallo(db: Session, org, origen: set[str], profundidad: int = 4) -> set[str]:
    """CIs que caen si caen los de `origen` (mismas reglas que el impacto de la CMDB):
    quien depende de él, lo que aloja y aquello de lo que forma parte."""
    rels = _q(db, CIRelation, org).all()
    arriba: dict[str, set[str]] = {}
    for r in rels:
        tipo = _valor(r.relation_type)
        if tipo == "depends_on":
            arriba.setdefault(r.target_ci_id, set()).add(r.source_ci_id)
        elif tipo in ("hosts",):
            arriba.setdefault(r.source_ci_id, set()).add(r.target_ci_id)
        elif tipo == "part_of":
            arriba.setdefault(r.source_ci_id, set()).add(r.target_ci_id)
    vistos = set(origen)
    frontera = set(origen)
    for _ in range(profundidad):
        nueva = set()
        for c in frontera:
            nueva |= arriba.get(c, set()) - vistos
        if not nueva:
            break
        vistos |= nueva
        frontera = nueva
    return vistos


def impacto(db: Session, org, product_id: Optional[str] = None, instance_id: Optional[str] = None,
            vulnerability_id: Optional[str] = None, finding_id: Optional[str] = None) -> dict:
    """Software, versiones, máquinas, servicios, clientes y responsables afectados."""
    from app.models.clients import Client
    from app.models.project import Project
    from app.models.user import User
    instancias: dict[str, SoftwareInstance] = {}
    versiones_padre: set[str] = set()
    productos_afectados: set[str] = set()
    hallazgos = []
    if finding_id or vulnerability_id:
        q = _q(db, VulnerabilityFinding, org)
        q = q.filter(VulnerabilityFinding.id == finding_id) if finding_id else q.filter(
            VulnerabilityFinding.vulnerability_id == vulnerability_id, VulnerabilityFinding.status.in_(VIVOS))
        hallazgos = q.all()
        for f in hallazgos:
            productos_afectados.add(f.product_id)
            if f.instance_id:
                i = db.get(SoftwareInstance, f.instance_id)
                if i is not None:
                    instancias[i.id] = i
            if f.parent_version_id:
                versiones_padre.add(f.parent_version_id)
    if product_id:
        productos_afectados.add(product_id)
        for i in _q(db, SoftwareInstance, org).filter(SoftwareInstance.product_id == product_id,
                                                      SoftwareInstance.is_active.is_(True)):
            instancias[i.id] = i
        versiones_padre |= {c.parent_version_id for c in _q(db, SoftwareComponent, org).filter(
            SoftwareComponent.component_product_id == product_id)}
    if instance_id:
        i = cat.instancia(db, org, instance_id)
        instancias[i.id] = i
        productos_afectados.add(i.product_id)
        # Quien depende de esta instancia (relaciones entre instancias), en cascada
        frontera = {i.id}
        for _ in range(4):
            nuevos = {r.source_instance_id for r in _q(db, SoftwareInstanceRelation, org).filter(
                SoftwareInstanceRelation.target_instance_id.in_(frontera))} - set(instancias)
            for x in _q(db, SoftwareInstance, org).filter(SoftwareInstance.id.in_(nuevos or {""})):
                instancias[x.id] = x
            if not nuevos:
                break
            frontera = nuevos
    for i in _q(db, SoftwareInstance, org).filter(SoftwareInstance.version_id.in_(versiones_padre or {""}),
                                                  SoftwareInstance.is_active.is_(True)):
        instancias[i.id] = i
    prods = {p.id: p for p in _q(db, SoftwareProduct, org).filter(SoftwareProduct.id.in_(
        {i.product_id for i in instancias.values()} | productos_afectados
        | {v.product_id for v in _q(db, SoftwareVersion, org).filter(SoftwareVersion.id.in_(versiones_padre or {""}))}
        or {""}))}
    vers = {v.id: v for v in _q(db, SoftwareVersion, org).filter(SoftwareVersion.id.in_(versiones_padre or {""}))}
    hosts = {i.ci_id for i in instancias.values() if i.ci_id}
    propios = {i.own_ci_id for i in instancias.values() if i.own_ci_id}
    servicios = {i.service_ci_id for i in instancias.values() if i.service_ci_id} | {
        p.service_ci_id for p in prods.values() if p.service_ci_id}
    arriba = cis_afectados_por_fallo(db, org, hosts | propios)
    todos_cis = arriba | servicios
    cis = {c.id: c for c in _q(db, ConfigurationItem, org).filter(ConfigurationItem.id.in_(todos_cis or {""}))}
    servicios_ci = [c for c in cis.values() if c.id in servicios or _valor(c.ci_type) in ("service", "application")]
    clientes = {i.client_id for i in instancias.values() if i.client_id}
    proyectos = {c.project_id for c in cis.values() if c.project_id} | {p.project_id for p in prods.values()
                                                                        if p.project_id}
    for pr in _q(db, Project, org).filter(Project.id.in_(proyectos or {""})):
        if getattr(pr, "client_id", None):
            clientes.add(pr.client_id)
    responsables = {i.owner_user_id for i in instancias.values() if i.owner_user_id} | {
        p.owner_user_id for p in prods.values() if p.owner_user_id} | {
        c.owner_user_id for c in cis.values() if c.owner_user_id}
    return {
        "software": [{"product_id": prods[v.product_id].id, "product_name": prods[v.product_id].name,
                      "version_id": v.id, "version": v.version} for v in vers.values() if v.product_id in prods],
        "affected_products": [{"id": p, "name": prods[p].name} for p in productos_afectados if p in prods],
        "instances": [cat.serializar_instancia(i, prods.get(i.product_id), cis.get(i.ci_id)) for i in instancias.values()],
        "machines": [_ci_breve(cis[c]) for c in hosts if c in cis],
        "impacted_cis": [_ci_breve(c) for c in cis.values() if c.id not in hosts],
        "services": [_ci_breve(c) for c in servicios_ci],
        "clients": [{"id": c.id, "name": c.name} for c in _q(db, Client, org).filter(Client.id.in_(clientes or {""}))],
        "owners": [{"id": u.id, "name": u.full_name} for u in db.query(User).filter(User.id.in_(responsables or {""}))],
        "summary": {"software": len(vers), "instances": len(instancias), "machines": len(hosts),
                    "services": len(servicios_ci), "clients": len(clientes), "findings": len(hallazgos)},
    }


# ── Fin de vida ──────────────────────────────────────────────────────────────

def fin_de_vida(db: Session, org, dias: Optional[int] = None, solo_produccion: bool = False) -> dict:
    conf = ajustes.leer(db, org)
    ciclos = _Ciclos(db, org, int(dias if dias is not None else conf.get("eol_warning_days") or 90))
    prods = {p.id: p for p in _q(db, SoftwareProduct, org)}
    instancias, componentes = [], []
    q = _q(db, SoftwareInstance, org).filter(SoftwareInstance.is_active.is_(True), SoftwareInstance.status != "retired")
    if solo_produccion:
        q = q.filter(SoftwareInstance.environment == "prod")
    lista = q.all()
    cis = {c.id: c for c in _q(db, ConfigurationItem, org).filter(
        ConfigurationItem.id.in_({i.ci_id for i in lista if i.ci_id} or {""}))}
    for i in lista:
        e = ciclos.estado(i.product_id, i.version)
        if e["lifecycle"]:
            instancias.append({**cat.serializar_instancia(i, prods.get(i.product_id), cis.get(i.ci_id)), **e})
    for c in _q(db, SoftwareComponent, org):
        e = ciclos.estado(c.component_product_id, c.component_version)
        if e["lifecycle"]:
            pv = db.get(SoftwareVersion, c.parent_version_id)
            pp = prods.get(pv.product_id) if pv else None
            componentes.append({"component_id": c.id, "name": prods[c.component_product_id].name
                                if c.component_product_id in prods else None, "version": c.component_version,
                                "parent_product_id": pp.id if pp else None, "parent_product_name": pp.name if pp else None,
                                "parent_version": pv.version if pv else None, **e})
    cuenta = {"eol": 0, "unsupported": 0, "soon": 0}
    for x in instancias + componentes:
        cuenta[x["lifecycle"]] += 1
    return {"instances": instancias, "components": componentes, "summary": cuenta}


# ── Deriva y líneas base ─────────────────────────────────────────────────────

def deriva(db: Session, org) -> dict:
    prods = {p.id: p for p in _q(db, SoftwareProduct, org)}
    instancias = _q(db, SoftwareInstance, org).filter(SoftwareInstance.is_active.is_(True)).all()
    cis = {c.id: c for c in _q(db, ConfigurationItem, org).filter(
        ConfigurationItem.id.in_({i.ci_id for i in instancias if i.ci_id} or {""}))}
    lineas = {}
    for b in _q(db, SoftwareBaseline, org).filter(SoftwareBaseline.is_active.is_(True)):
        lineas.setdefault(b.product_id, []).append(b)
    con_deriva, incumplen = [], []
    for i in instancias:
        base = json.loads(i.baseline_config_json) if i.baseline_config_json else None
        actual = json.loads(i.config_json) if i.config_json else {}
        if i.drift_detected_at:
            con_deriva.append({**cat.serializar_instancia(i, prods.get(i.product_id), cis.get(i.ci_id)),
                               "changed_keys": cfg.diferencias(base, actual)})
        for b in lineas.get(i.product_id, []):
            if b.environment and b.environment != i.environment:
                continue
            fallos = cfg.evaluar_linea_base(actual, json.loads(b.rules_json))
            if fallos:
                incumplen.append({"instance_id": i.id, "instance_name": i.name,
                                  "product_name": prods[i.product_id].name if i.product_id in prods else None,
                                  "ci_name": cis[i.ci_id].name if i.ci_id in cis else None,
                                  "environment": i.environment, "baseline_id": b.id, "baseline_name": b.name,
                                  "baseline_approved": bool(b.approved_at), "violations": fallos})
    return {"drift": con_deriva, "violations": incumplen,
            "summary": {"drift": len(con_deriva), "violations": sum(len(x["violations"]) for x in incumplen),
                        "instances_with_violations": len(incumplen)}}


# ── Licencias ────────────────────────────────────────────────────────────────

def licencias(db: Session, org) -> dict:
    conf = ajustes.leer(db, org)
    prods = {p.id: p for p in _q(db, SoftwareProduct, org)}
    vers = {v.id: v for v in _q(db, SoftwareVersion, org)}
    por_familia: dict = {f: 0 for f in lic.FAMILIAS}
    problemas = []
    for c in _q(db, SoftwareComponent, org):
        comp = prods.get(c.component_product_id)
        pv = vers.get(c.parent_version_id)
        padre = prods.get(pv.product_id) if pv else None
        licencia = c.license_spdx or (comp.license_spdx if comp else None)
        familia = lic.familia_de_expresion(licencia)
        por_familia[familia] += 1
        r = lic.evaluar(licencia, padre.distribution if padre else None, padre.origin if padre else None,
                        conf.get("licenses_allowed"), conf.get("licenses_denied"),
                        padre.license_spdx if padre else None)
        if r and c.scope not in ("dev", "test"):
            problemas.append({"component_id": c.id, "name": comp.name if comp else None, "version": c.component_version,
                              "license": licencia, **r, "parent_product_id": padre.id if padre else None,
                              "parent_product_name": padre.name if padre else None,
                              "parent_version": pv.version if pv else None,
                              "parent_distribution": padre.distribution if padre else None})
    problemas.sort(key=lambda x: (x["level"] != "conflict", x.get("parent_product_name") or ""))
    return {"by_family": por_familia, "issues": problemas[:2000],
            "summary": {"conflicts": sum(1 for p in problemas if p["level"] == "conflict"),
                        "warnings": sum(1 for p in problemas if p["level"] == "warning")}}


# ── Cuadro de mando ──────────────────────────────────────────────────────────

def cuadro_de_mando(db: Session, org) -> dict:
    from datetime import datetime, timezone
    ahora = datetime.now(timezone.utc)
    vivos = _q(db, VulnerabilityFinding, org).filter(VulnerabilityFinding.status.in_(VIVOS))
    por_sev = dict(vivos.with_entities(VulnerabilityFinding.severity, func.count())
                   .group_by(VulnerabilityFinding.severity).all())
    por_estado = dict(_q(db, VulnerabilityFinding, org).with_entities(VulnerabilityFinding.status, func.count())
                      .group_by(VulnerabilityFinding.status).all())
    fuera = vivos.filter(VulnerabilityFinding.sla_due_at < ahora).count()
    kev = vivos.join(Vulnerability, Vulnerability.id == VulnerabilityFinding.vulnerability_id).filter(
        Vulnerability.kev.is_(True)).count()
    top = (vivos.with_entities(VulnerabilityFinding.product_id, func.count(), func.max(VulnerabilityFinding.priority_score))
           .group_by(VulnerabilityFinding.product_id)
           .order_by(func.max(VulnerabilityFinding.priority_score).desc()).limit(10).all())
    nombres = {p.id: p.name for p in _q(db, SoftwareProduct, org).filter(
        SoftwareProduct.id.in_([t[0] for t in top] or [""]))}
    eol = fin_de_vida(db, org)
    der = deriva(db, org)
    lic_ = licencias(db, org)
    sin_dueno = _q(db, SoftwareProduct, org).filter(SoftwareProduct.is_active.is_(True),
                                                    SoftwareProduct.owner_user_id.is_(None),
                                                    SoftwareProduct.origin.in_(("purchased", "saas", "in_house"))).count()
    excepciones = dict(_q(db, VulnerabilityException, org).with_entities(VulnerabilityException.status, func.count())
                       .group_by(VulnerabilityException.status).all())
    conf = ajustes.leer(db, org)
    return {
        "products": _q(db, SoftwareProduct, org).filter(SoftwareProduct.is_active.is_(True)).count(),
        "applications": _q(db, SoftwareProduct, org).filter(SoftwareProduct.is_active.is_(True),
                                                             SoftwareProduct.origin.in_(("purchased", "saas", "in_house"))).count(),
        "versions": _q(db, SoftwareVersion, org).count(),
        "instances": _q(db, SoftwareInstance, org).filter(SoftwareInstance.is_active.is_(True)).count(),
        "components": _q(db, SoftwareComponent, org).count(),
        "machines": _q(db, SoftwareInstance, org).filter(SoftwareInstance.is_active.is_(True))
        .with_entities(func.count(func.distinct(SoftwareInstance.ci_id))).scalar() or 0,
        "findings_live": sum(por_sev.values()), "findings_by_severity": por_sev, "findings_by_status": por_estado,
        "findings_out_of_sla": fuera, "findings_kev": kev,
        "findings_possible": vivos.filter(VulnerabilityFinding.score_detail.like('%"possible": true%')).count(),
        "scanners": _escaneos(db, org),
        "top_products": [{"product_id": t[0], "name": nombres.get(t[0]), "findings": t[1], "max_priority": t[2]}
                         for t in top],
        "eol": eol["summary"], "eol_in_production": sum(1 for x in eol["instances"]
                                                        if x["environment"] == "prod" and x["lifecycle"] in ("eol", "unsupported")),
        "drift": der["summary"], "licenses": lic_["summary"], "products_without_owner": sin_dueno,
        "exceptions": excepciones, "last_sync_at": conf.get("last_sync_at"),
        "sources_active": [f for f in ("osv", "nvd", "ghsa", "epss", "kev", "eol") if conf.get(f"{f}_enabled")],
        "last_sync_status": conf.get("last_sync_status"),
    }


def _escaneos(db: Session, org) -> dict:
    """Conexiones de escaneo: cuántas, activas y la última ejecución (para los avisos de la pantalla)."""
    from app.models.cmdb import CMDBDiscoveryProvider
    from app.services.cmdb_software.escaneos import TIPOS
    filas = (db.query(CMDBDiscoveryProvider).filter(CMDBDiscoveryProvider.provider_type.in_(TIPOS),
                                                    *([CMDBDiscoveryProvider.organization_id == org] if org else []))
             .all())
    ultima = max((f.last_run_at for f in filas if f.last_run_at), default=None)
    return {"total": len(filas), "active": sum(1 for f in filas if f.is_active),
            "last_run_at": ultima.isoformat() if ultima else None,
            "with_errors": sum(1 for f in filas if f.last_run_status == "error")}


# ── Vista por máquina ────────────────────────────────────────────────────────

def maquina(db: Session, org, ci_id: str) -> dict:
    from app.models.alm import ALMAsset
    from app.models.cmdb import CMDBChangelog
    from app.models.service_desk.tickets import Ticket
    from app.models.service_desk._enums import ESTADOS_DE_TICKET_EN_CURSO
    c = cat.ci(db, org, ci_id)
    conf = ajustes.leer(db, org)
    ciclos = _Ciclos(db, org, int(conf.get("eol_warning_days") or 90))
    instancias = _q(db, SoftwareInstance, org).filter(SoftwareInstance.ci_id == c.id).all()
    prods = {p.id: p for p in _q(db, SoftwareProduct, org).filter(
        SoftwareProduct.id.in_({i.product_id for i in instancias} or {""}))}
    hallazgos = _hallazgos_vivos_por(db, org, VulnerabilityFinding.instance_id)
    comps_por_version = dict(_q(db, SoftwareComponent, org).with_entities(SoftwareComponent.parent_version_id,
                                                                          func.count())
                             .filter(SoftwareComponent.parent_version_id.in_({i.version_id for i in instancias
                                                                              if i.version_id} or {""}))
                             .group_by(SoftwareComponent.parent_version_id).all())
    lineas = {}
    for b in _q(db, SoftwareBaseline, org).filter(SoftwareBaseline.is_active.is_(True),
                                                  SoftwareBaseline.product_id.in_(list(prods) or [""])):
        lineas.setdefault(b.product_id, []).append(b)
    salida_inst = []
    for i in instancias:
        actual = json.loads(i.config_json) if i.config_json else {}
        fallos = []
        for b in lineas.get(i.product_id, []):
            if not b.environment or b.environment == i.environment:
                fallos += cfg.evaluar_linea_base(actual, json.loads(b.rules_json))
        salida_inst.append({**cat.serializar_instancia(i, prods.get(i.product_id), c),
                            "open_findings": hallazgos.get(i.id, {}).get("count", 0),
                            "worst_severity": hallazgos.get(i.id, {}).get("worst"),
                            "components_count": comps_por_version.get(i.version_id, 0),
                            "baseline_violations": fallos, **ciclos.estado(i.product_id, i.version)})
    relaciones = [cat.serializar_relacion(r) for r in _q(db, SoftwareInstanceRelation, org).filter(or_(
        SoftwareInstanceRelation.source_instance_id.in_([i.id for i in instancias] or [""]),
        SoftwareInstanceRelation.target_ci_id == c.id))]
    activos = [{"id": a.id, "name": a.name, "type": _valor(a.type), "serial_number": a.serial_number,
                "asset_tag": a.asset_tag, "status": _valor(a.status), "os": a.os,
                "warranty_expiry": a.warranty_expiry.isoformat() if a.warranty_expiry else None,
                "eol_date": a.eol_date.isoformat() if a.eol_date else None}
               for a in _q(db, ALMAsset, org).filter(ALMAsset.ci_id == c.id)]
    licencias_ids = {i.license_id for i in instancias if i.license_id}
    for pl in _q(db, SoftwareProductLicense, org).filter(SoftwareProductLicense.product_id.in_(list(prods) or [""])):
        licencias_ids.add(pl.license_id)
    from app.models.alm import ALMLicense
    licencias_ = [{"id": l.id, "name": l.name, "status": _valor(l.status),
                   "expiry_date": l.expiry_date.isoformat() if l.expiry_date else None}
                  for l in _q(db, ALMLicense, org).filter(ALMLicense.id.in_(licencias_ids or {""}))]
    tickets = _q(db, Ticket, org).filter(Ticket.ci_id == c.id, Ticket.status.in_(ESTADOS_DE_TICKET_EN_CURSO)).count() \
        if hasattr(Ticket, "ci_id") else 0
    historial = [{"field": h.field, "old_value": h.old_value, "new_value": h.new_value, "summary": h.summary,
                  "created_at": h.created_at.isoformat() if h.created_at else None}
                 for h in _q(db, CMDBChangelog, org).filter(CMDBChangelog.item_id == c.id,
                                                            CMDBChangelog.field.like("software%"))
                 .order_by(CMDBChangelog.created_at.desc()).limit(30)]
    sevs = dict(_q(db, VulnerabilityFinding, org).with_entities(VulnerabilityFinding.severity, func.count())
                .filter(VulnerabilityFinding.status.in_(VIVOS), or_(
                    VulnerabilityFinding.instance_id.in_([i.id for i in instancias] or [""]),
                    VulnerabilityFinding.parent_version_id.in_([i.version_id for i in instancias if i.version_id] or [""])))
                .group_by(VulnerabilityFinding.severity).all())
    return {"ci": _ci_breve(c), "instances": salida_inst, "relations": relaciones, "assets": activos,
            "licenses": licencias_, "open_tickets": tickets, "software_history": historial,
            "findings_by_severity": sevs}


# ── Grafo ────────────────────────────────────────────────────────────────────

_TIPO_CI = {"application": "application", "web_server": "service", "app_server": "service", "middleware": "service",
            "database": "database", "container_image": "container", "os": "server", "runtime": "module",
            "language": "module", "framework": "module", "library": "module", "tool": "module", "other": "other"}
_REL_GRAFO = {"depends_on": "depends_on", "runs_on": "hosts", "connects_to": "connects_to",
              "publishes_via": "connects_to", "uses_database": "depends_on", "uses_runtime": "depends_on",
              "part_of": "part_of"}


def grafo(db: Session, org, product_id: Optional[str] = None, instance_id: Optional[str] = None,
          ci_id: Optional[str] = None, componentes: int = 25) -> dict:
    """Nodos y aristas con la forma de `CMDBTopologyGraph` (`id, name, ci_type, is_center`; `source, target, rel_type`)."""
    nodos: dict[str, dict] = {}
    aristas: list[dict] = []

    def n_ci(c: ConfigurationItem, centro=False):
        nodos.setdefault(f"ci:{c.id}", {"id": f"ci:{c.id}", "name": c.name, "ci_type": _valor(c.ci_type),
                                        "status": _valor(c.status), "criticality": c.criticality,
                                        "hostname": c.hostname, "is_center": centro, "kind": "ci", "ref_id": c.id})

    def n_inst(i: SoftwareInstance, p: Optional[SoftwareProduct], centro=False):
        nodos.setdefault(f"in:{i.id}", {"id": f"in:{i.id}", "name": f"{p.name if p else '?'} {i.version or ''}".strip(),
                                        "ci_type": _TIPO_CI.get(p.category if p else "other", "other"),
                                        "status": "operational" if i.status == "running" else "maintenance",
                                        "criticality": i.criticality or (p.criticality if p else None),
                                        "is_center": centro, "kind": "instance", "ref_id": i.id,
                                        "environment": i.environment})

    def n_prod(p: SoftwareProduct, version: Optional[str] = None, centro=False, ref=None):
        clave = f"pv:{ref}" if ref else f"pr:{p.id}"
        nodos.setdefault(clave, {"id": clave, "name": f"{p.name} {version or ''}".strip(),
                                 "ci_type": _TIPO_CI.get(p.category, "other"), "criticality": p.criticality,
                                 "is_center": centro, "kind": "product" if not ref else "component", "ref_id": p.id})
        return clave

    def arista(a, b, tipo):
        if a in nodos and b in nodos and a != b:
            aristas.append({"source": a, "target": b, "rel_type": tipo})

    def componentes_de(version_id: str, destino: str):
        for c in _q(db, SoftwareComponent, org).filter(SoftwareComponent.parent_version_id == version_id,
                                                       SoftwareComponent.direct.is_(True)).limit(componentes):
            p = db.get(SoftwareProduct, c.component_product_id)
            if p:
                clave = n_prod(p, c.component_version, ref=c.id)
                arista(clave, destino, "part_of")

    def relaciones_de(i: SoftwareInstance):
        for r in _q(db, SoftwareInstanceRelation, org).filter(or_(SoftwareInstanceRelation.source_instance_id == i.id,
                                                                  SoftwareInstanceRelation.target_instance_id == i.id)):
            for otro_id in (r.source_instance_id, r.target_instance_id):
                if otro_id and otro_id != i.id:
                    otro = db.get(SoftwareInstance, otro_id)
                    if otro is not None:
                        n_inst(otro, db.get(SoftwareProduct, otro.product_id))
            if r.target_ci_id:
                destino_ci = db.get(ConfigurationItem, r.target_ci_id)
                if destino_ci is not None:
                    n_ci(destino_ci)
            destino = f"in:{r.target_instance_id}" if r.target_instance_id else f"ci:{r.target_ci_id}"
            arista(f"in:{r.source_instance_id}", destino, _REL_GRAFO.get(r.relation_type, "depends_on"))

    if ci_id:
        c = cat.ci(db, org, ci_id)
        n_ci(c, centro=True)
        for i in _q(db, SoftwareInstance, org).filter(SoftwareInstance.ci_id == c.id, SoftwareInstance.is_active.is_(True)):
            n_inst(i, db.get(SoftwareProduct, i.product_id))
            arista(f"ci:{c.id}", f"in:{i.id}", "hosts")
            relaciones_de(i)
    elif instance_id:
        i = cat.instancia(db, org, instance_id)
        n_inst(i, db.get(SoftwareProduct, i.product_id), centro=True)
        if i.ci_id:
            host = db.get(ConfigurationItem, i.ci_id)
            if host is not None:
                n_ci(host)
                arista(f"ci:{host.id}", f"in:{i.id}", "hosts")
        relaciones_de(i)
        if i.version_id:
            componentes_de(i.version_id, f"in:{i.id}")
    elif product_id:
        p = cat.producto(db, org, product_id)
        centro = n_prod(p, centro=True)
        for i in _q(db, SoftwareInstance, org).filter(SoftwareInstance.product_id == p.id,
                                                      SoftwareInstance.is_active.is_(True)).limit(100):
            n_inst(i, p)
            arista(f"in:{i.id}", centro, "part_of")
            if i.ci_id:
                host = db.get(ConfigurationItem, i.ci_id)
                if host is not None:
                    n_ci(host)
                    arista(f"ci:{host.id}", f"in:{i.id}", "hosts")
        for c, pv in (db.query(SoftwareComponent, SoftwareVersion)
                      .join(SoftwareVersion, SoftwareVersion.id == SoftwareComponent.parent_version_id)
                      .filter(SoftwareComponent.component_product_id == p.id,
                              *([SoftwareComponent.organization_id == org] if org else [])).limit(50)):
            padre = db.get(SoftwareProduct, pv.product_id)
            if padre:
                clave = n_prod(padre, pv.version, ref=f"v{pv.id}")
                arista(centro, clave, "part_of")
        ultima = _q(db, SoftwareVersion, org).filter(SoftwareVersion.product_id == p.id).all()
        ultima.sort(key=lambda v: Version(v.version), reverse=True)
        if ultima:
            componentes_de(ultima[0].id, centro)
    return {"nodes": list(nodos.values()), "edges": aristas}


# ── Exportación ──────────────────────────────────────────────────────────────

def exportar_hallazgos_csv(db: Session, org) -> str:
    from app.services.cmdb_software.gestion import serializar
    salida = io.StringIO()
    w = csv.writer(salida)
    w.writerow(["vuln_id", "severity", "priority", "status", "kev", "cvss", "epss", "product", "affected_version",
                "fixed_version", "inside", "machine", "environment", "first_seen", "sla_due", "sla_breached",
                "ticket", "change", "problem", "task"])
    for f in _q(db, VulnerabilityFinding, org).order_by(VulnerabilityFinding.priority_score.desc().nullslast()):
        d = serializar(db, f, org=org)
        w.writerow([d["vuln_id"], d["severity"], d["priority_score"], d["status"], d["kev"], d["cvss_score"],
                    d["epss_score"], d["product_name"], d["affected_version"], d["fixed_version"],
                    f"{d['parent_product_name'] or ''} {d['parent_version'] or ''}".strip(), d["ci_name"],
                    d["environment"], d["first_seen_at"], d["sla_due_at"], d["sla_breached"], d["ticket_id"],
                    d["change_id"], d["problem_id"], d["task_id"]])
    return salida.getvalue()


def exportar_inventario_csv(db: Session, org) -> str:
    conf = ajustes.leer(db, org)
    ciclos = _Ciclos(db, org, int(conf.get("eol_warning_days") or 90))
    salida = io.StringIO()
    w = csv.writer(salida)
    w.writerow(["product", "vendor", "category", "origin", "version", "purl", "cpe", "machine", "hostname", "ip",
                "environment", "status", "install_path", "config_path", "ports", "exposure", "lifecycle", "eol_date"])
    prods = {p.id: p for p in _q(db, SoftwareProduct, org)}
    cis = {c.id: c for c in _q(db, ConfigurationItem, org)}
    for i in _q(db, SoftwareInstance, org).filter(SoftwareInstance.is_active.is_(True)):
        p = prods.get(i.product_id)
        c = cis.get(i.ci_id)
        e = ciclos.estado(i.product_id, i.version)
        w.writerow([p.name if p else "", p.vendor_name if p else "", p.category if p else "", p.origin if p else "",
                    i.version or "", ids.construir_purl(p.purl_type, p.purl_namespace, p.purl_name, i.version)
                    if p and p.purl_name else "", ids.construir_cpe(p.cpe_vendor, p.cpe_product, i.version)
                    if p and p.cpe_vendor else "", c.name if c else "", c.hostname if c else "",
                    c.ip_address if c else "", i.environment, i.status, i.install_path or "", i.config_path or "",
                    " ".join(str(x) for x in json.loads(i.ports or "[]")), i.exposure, e["lifecycle"] or "",
                    e["eol_date"] or ""])
    return salida.getvalue()


# ── Para otros módulos ───────────────────────────────────────────────────────

def resumen_de_cis(db: Session, org, ci_ids: list[str]) -> dict:
    """Software de unos CIs, para el análisis de impacto de un cambio y para incidentes."""
    if not ci_ids:
        return {"instances": [], "open_findings": 0, "critical_findings": 0, "eol_instances": 0}
    conf = ajustes.leer(db, org)
    ciclos = _Ciclos(db, org, int(conf.get("eol_warning_days") or 90))
    instancias = _q(db, SoftwareInstance, org).filter(SoftwareInstance.ci_id.in_(ci_ids),
                                                      SoftwareInstance.is_active.is_(True)).all()
    prods = {p.id: p for p in _q(db, SoftwareProduct, org).filter(
        SoftwareProduct.id.in_({i.product_id for i in instancias} or {""}))}
    hallazgos = _hallazgos_vivos_por(db, org, VulnerabilityFinding.instance_id)
    vivos = _q(db, VulnerabilityFinding, org).filter(VulnerabilityFinding.status.in_(ABIERTOS), or_(
        VulnerabilityFinding.instance_id.in_([i.id for i in instancias] or [""]),
        VulnerabilityFinding.parent_version_id.in_([i.version_id for i in instancias if i.version_id] or [""])))
    salida = []
    eol = 0
    for i in instancias:
        e = ciclos.estado(i.product_id, i.version)
        eol += int(e["lifecycle"] in ("eol", "unsupported"))
        salida.append({"instance_id": i.id, "ci_id": i.ci_id, "product": prods[i.product_id].name
                       if i.product_id in prods else None, "version": i.version, "environment": i.environment,
                       "open_findings": hallazgos.get(i.id, {}).get("count", 0), "lifecycle": e["lifecycle"]})
    return {"instances": salida, "open_findings": vivos.count(),
            "critical_findings": vivos.filter(VulnerabilityFinding.severity.in_(("critical", "high"))).count(),
            "eol_instances": eol}
