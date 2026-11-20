"""Catálogo, versiones, composición, instancias, relaciones, líneas base y licencias.

Todo se acota a la empresa (`org`) explícitamente, además del filtro de
tenant de la sesión, para que los trabajos de fondo (sin usuario) tampoco
crucen empresas. Ninguna función confirma: lo hace el endpoint.

Auditoría: cada alta, cambio y baja deja `audit_logs` (recurso `sw_*`). Los
cambios de software en una máquina dejan además una línea en el historial del
CI anfitrión (`cmdb_changelog`), para que la ficha del CI cuente «nginx
1.18.0 → 1.24.0».
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.cmdb import CMDBChangelog
from app.models.cmdb_software import (SoftwareBaseline, SoftwareComponent, SoftwareConfigSnapshot,
                                      SoftwareInstance, SoftwareInstanceRelation, SoftwareProduct,
                                      SoftwareProductLicense, SoftwareVersion)
from app.models.service_desk.cmdb import ConfigurationItem
from app.services.audit import audit_log
from app.services.cmdb_software import configuracion as cfg
from app.services.cmdb_software import identificadores as ids

CATEGORIAS = ("application", "runtime", "language", "framework", "library", "web_server", "app_server", "database",
              "middleware", "os", "container_image", "tool", "other")
ORIGENES = ("purchased", "saas", "open_source", "in_house")
CRITICIDADES = ("low", "medium", "high", "critical")
CICLOS = ("planned", "active", "deprecated", "retired")
DISTRIBUCIONES = ("internal", "saas", "distributed")
ENTORNOS = ("prod", "pre", "test", "dev", "dr")
ESTADOS_INSTANCIA = ("planned", "running", "stopped", "retired")
EXPOSICIONES = ("internet", "internal", "isolated")
RELACIONES = ("depends_on", "runs_on", "connects_to", "publishes_via", "uses_database", "uses_runtime", "part_of")
RELACIONES_COMPONENTE = ("runtime", "language", "framework", "library", "bundled", "base_image", "driver",
                         "build_tool", "plugin", "service")
AMBITOS = ("required", "optional", "dev", "test")


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def _json(v, defecto=None):
    if v in (None, ""):
        return defecto
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return defecto


def _validar(campo: str, valor, permitidos, obligatorio: bool = False):
    if valor in (None, ""):
        if obligatorio:
            raise error(422, "sw_valor_no_valido", campo=campo, valor="")
        return None
    if valor not in permitidos:
        raise error(422, "sw_valor_no_valido", campo=campo, valor=valor)
    return valor


def _fecha(v) -> Optional[date]:
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise error(422, "sw_valor_no_valido", campo="fecha", valor=str(v))


def _q(db: Session, modelo, org: Optional[str]):
    q = db.query(modelo)
    return q.filter(modelo.organization_id == org) if org else q


def _uno(db, modelo, org, id_, codigo):
    obj = _q(db, modelo, org).filter(modelo.id == id_).first() if id_ else None
    if obj is None:
        raise error(404, codigo)
    return obj


def producto(db, org, id_) -> SoftwareProduct:
    return _uno(db, SoftwareProduct, org, id_, "sw_producto_no_encontrado")


def version(db, org, id_) -> SoftwareVersion:
    return _uno(db, SoftwareVersion, org, id_, "sw_version_no_encontrada")


def instancia(db, org, id_) -> SoftwareInstance:
    return _uno(db, SoftwareInstance, org, id_, "sw_instancia_no_encontrada")


def ci(db, org, id_) -> ConfigurationItem:
    return _uno(db, ConfigurationItem, org, id_, "sw_ci_no_encontrado")


def _ci_opcional(db, org, id_) -> Optional[str]:
    return ci(db, org, id_).id if id_ else None


def _changelog_ci(db, ci_id: Optional[str], usuario, accion: str, campo: str, antes, despues, resumen: str) -> None:
    if not ci_id:
        return
    db.add(CMDBChangelog(item_id=ci_id, user_id=getattr(usuario, "id", None), action=accion, field=campo,
                         old_value=None if antes is None else str(antes)[:2000],
                         new_value=None if despues is None else str(despues)[:2000], summary=resumen[:500]))


# ── Productos ────────────────────────────────────────────────────────────────

def serializar_producto(p: SoftwareProduct, extra: Optional[dict] = None) -> dict:
    return {
        "id": p.id, "name": p.name, "category": p.category, "origin": p.origin, "vendor_name": p.vendor_name,
        "alm_vendor_id": p.alm_vendor_id, "description": p.description,
        "purl_type": p.purl_type, "purl_namespace": p.purl_namespace, "purl_name": p.purl_name,
        "purl": ids.construir_purl(p.purl_type, p.purl_namespace, p.purl_name) if p.purl_name else None,
        "cpe_vendor": p.cpe_vendor, "cpe_product": p.cpe_product,
        "cpe": ids.construir_cpe(p.cpe_vendor, p.cpe_product) if p.cpe_vendor else None,
        "match_key": p.match_key, "aliases": _json(p.aliases, []), "license_spdx": p.license_spdx,
        "homepage": p.homepage, "repository_url": p.repository_url, "owner_user_id": p.owner_user_id,
        "project_id": p.project_id, "service_ci_id": p.service_ci_id, "criticality": p.criticality,
        "distribution": p.distribution, "lifecycle_status": p.lifecycle_status, "tags": _json(p.tags, []),
        "notes": p.notes, "is_active": p.is_active,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        **(extra or {}),
    }


def _identificadores(datos: dict, actual: Optional[SoftwareProduct] = None) -> dict:
    """purl/CPE/clave a partir de lo que llega (purl o CPE completos, o sus partes, o el nombre)."""
    salida = {}
    p = ids.parsear_purl(datos.get("purl")) if datos.get("purl") else None
    if p:
        salida.update(purl_type=p.type, purl_namespace=p.namespace, purl_name=p.name)
    for k in ("purl_type", "purl_namespace", "purl_name", "cpe_vendor", "cpe_product"):
        if k in datos and k not in salida:
            salida[k] = (str(datos[k]).strip() or None) if datos[k] is not None else None
    c = ids.parsear_cpe(datos.get("cpe")) if datos.get("cpe") else None
    if c:
        salida.update(cpe_vendor=c.vendor, cpe_product=c.product)
    nombre = datos.get("name") or (actual.name if actual else None)
    conocido = ids.datos_de_conocido(nombre) or ids.datos_de_conocido(salida.get("purl_name"))
    if conocido:
        for k in ("cpe_vendor", "cpe_product", "purl_type", "purl_namespace", "purl_name"):
            if not salida.get(k) and not (actual is not None and getattr(actual, k)):
                salida[k] = conocido[k]

    def val(k):
        return salida.get(k) if k in salida else (getattr(actual, k) if actual is not None else None)
    salida["match_key"] = ids.clave_de_producto(nombre, None, val("purl_type"), val("purl_namespace"),
                                                val("purl_name"), val("cpe_vendor"), val("cpe_product"))
    return salida


def _aplicar_producto(p: SoftwareProduct, datos: dict) -> None:
    if "name" in datos:
        nombre = (datos.get("name") or "").strip()
        if not nombre:
            raise error(422, "sw_nombre_obligatorio")
        p.name = nombre[:200]
    if "category" in datos:
        p.category = _validar("category", datos["category"], CATEGORIAS, True)
    if "origin" in datos:
        p.origin = _validar("origin", datos["origin"], ORIGENES, True)
    if "criticality" in datos:
        p.criticality = _validar("criticality", datos["criticality"], CRITICIDADES, True)
    if "lifecycle_status" in datos:
        p.lifecycle_status = _validar("lifecycle_status", datos["lifecycle_status"], CICLOS, True)
    if "distribution" in datos:
        p.distribution = _validar("distribution", datos["distribution"], DISTRIBUCIONES)
    for k in ("vendor_name", "alm_vendor_id", "description", "license_spdx", "homepage", "repository_url",
              "owner_user_id", "project_id", "service_ci_id", "notes"):
        if k in datos:
            setattr(p, k, (datos[k] if not isinstance(datos[k], str) else (datos[k].strip() or None)))
    for k in ("aliases", "tags"):
        if k in datos:
            v = datos[k]
            setattr(p, k, json.dumps([str(x) for x in v]) if isinstance(v, list) and v else None)


def _comprobar_referencias(db, org, datos: dict) -> None:
    from app.models.alm import ALMVendor
    from app.models.project import Project
    from app.models.user import User
    if datos.get("service_ci_id"):
        ci(db, org, datos["service_ci_id"])
    if datos.get("alm_vendor_id") and not _q(db, ALMVendor, org).filter(ALMVendor.id == datos["alm_vendor_id"]).first():
        raise error(422, "sw_valor_no_valido", campo="alm_vendor_id", valor=datos["alm_vendor_id"])
    if datos.get("project_id") and not _q(db, Project, org).filter(Project.id == datos["project_id"]).first():
        raise error(422, "sw_valor_no_valido", campo="project_id", valor=datos["project_id"])
    if datos.get("owner_user_id") and not db.query(User.id).filter(User.id == datos["owner_user_id"]).first():
        raise error(422, "sw_valor_no_valido", campo="owner_user_id", valor=datos["owner_user_id"])


def por_clave(db, org, clave: str) -> Optional[SoftwareProduct]:
    return _q(db, SoftwareProduct, org).filter(SoftwareProduct.match_key == clave).first()


def crear_producto(db: Session, org, datos: dict, usuario=None, auditar: bool = True) -> SoftwareProduct:
    if not (datos.get("name") or "").strip():
        conocido = ids.datos_de_conocido((ids.parsear_purl(datos.get("purl")) or ids.Purl("generic", "")).name)
        if conocido:
            datos = {**datos, "name": conocido["name"]}
        else:
            raise error(422, "sw_nombre_obligatorio")
    _comprobar_referencias(db, org, datos)
    idents = _identificadores(datos)
    existente = por_clave(db, org, idents["match_key"])
    if existente is not None:
        raise error(409, "sw_producto_duplicado", nombre=existente.name, id=existente.id)
    conocido = ids.datos_de_conocido(datos.get("name"))
    p = SoftwareProduct(organization_id=org, created_by=getattr(usuario, "id", None),
                        category=(conocido or {}).get("category", "application"),
                        origin="open_source" if conocido else "in_house")
    _aplicar_producto(p, {"origin": p.origin, "category": p.category, **datos})
    for k, v in idents.items():
        setattr(p, k, v)
    db.add(p)
    db.flush()
    if auditar:
        audit_log(db, usuario, "CREATE", "sw_product", p.id, p.name, new_values=serializar_producto(p))
    return p


def actualizar_producto(db: Session, org, p: SoftwareProduct, datos: dict, usuario=None) -> SoftwareProduct:
    antes = serializar_producto(p)
    _comprobar_referencias(db, org, datos)
    _aplicar_producto(p, datos)
    if any(k in datos for k in ("purl", "cpe", "purl_type", "purl_namespace", "purl_name", "cpe_vendor",
                                "cpe_product", "name")):
        idents = _identificadores(datos, p)
        otro = por_clave(db, org, idents["match_key"])
        if otro is not None and otro.id != p.id:
            raise error(409, "sw_producto_duplicado", nombre=otro.name, id=otro.id)
        for k, v in idents.items():
            setattr(p, k, v)
    db.flush()
    audit_log(db, usuario, "UPDATE", "sw_product", p.id, p.name, old_values=antes, new_values=serializar_producto(p))
    return p


def retirar_producto(db: Session, p: SoftwareProduct, usuario=None) -> None:
    """Baja lógica: deja de verse en el catálogo; sus hallazgos e historial se conservan."""
    p.is_active = False
    p.lifecycle_status = "retired"
    db.flush()
    audit_log(db, usuario, "DELETE", "sw_product", p.id, p.name)


def buscar_o_crear_producto(db: Session, org, nombre: Optional[str], purl: Optional[str] = None,
                            tipo: Optional[str] = None, espacio: Optional[str] = None, cpe: Optional[str] = None,
                            categoria: Optional[str] = None, origen: Optional[str] = None,
                            licencia: Optional[str] = None, fabricante: Optional[str] = None,
                            usuario=None) -> tuple[SoftwareProduct, bool]:
    """Conciliación: el producto con la misma clave, o uno nuevo (sin auditar cada componente)."""
    datos: dict = {"name": nombre}
    if purl:
        datos["purl"] = purl
    elif tipo and nombre and tipo != "generic":
        datos.update(purl_type=tipo, purl_namespace=espacio, purl_name=nombre)
    elif tipo == "generic" and nombre and not ids.conocido(nombre):
        datos.update(purl_type="generic", purl_namespace=espacio, purl_name=nombre)
    if cpe:
        datos["cpe"] = cpe
    idents = _identificadores(datos)
    p = por_clave(db, org, idents["match_key"])
    if p is None:
        # Alias: el mismo producto con otro nombre (registrado en `aliases`).
        normal = ids.normalizar_texto(nombre)
        if normal:
            for cand in _q(db, SoftwareProduct, org).filter(SoftwareProduct.aliases.isnot(None)).all():
                if normal in {ids.normalizar_texto(a) for a in _json(cand.aliases, [])}:
                    return cand, False
    if p is not None:
        if not p.license_spdx and licencia:
            p.license_spdx = licencia[:200]
        return p, False
    nombre_final = (nombre or idents.get("purl_name") or "?")
    if espacio and idents.get("purl_type") not in (None, "generic") and not nombre_final.startswith(espacio):
        nombre_final = f"{espacio}/{nombre_final}" if idents.get("purl_type") in ("composer", "npm", "golang") \
            else (f"{espacio}:{nombre_final}" if idents.get("purl_type") == "maven" else nombre_final)
    conocido = ids.datos_de_conocido(nombre)
    p = SoftwareProduct(organization_id=org, name=(conocido or {}).get("name", nombre_final)[:200],
                        category=categoria if categoria in CATEGORIAS else (conocido or {}).get("category", "library"),
                        origin=origen if origen in ORIGENES else "open_source",
                        license_spdx=(licencia or None) and licencia[:200], vendor_name=fabricante,
                        created_by=getattr(usuario, "id", None))
    for k, v in idents.items():
        setattr(p, k, v)
    db.add(p)
    db.flush()
    return p, True


def fusionar_productos(db: Session, org, origen: SoftwareProduct, destino: SoftwareProduct, usuario=None) -> dict:
    """Funde `origen` en `destino`: versiones, componentes, instancias, hallazgos y licencias."""
    from app.models.cmdb_software import VulnerabilityFinding
    if origen.id == destino.id:
        raise error(422, "sw_fusion_misma")
    movidas = {"versions": 0, "components": 0, "instances": 0, "findings": 0, "licenses": 0}
    for v in _q(db, SoftwareVersion, org).filter(SoftwareVersion.product_id == origen.id).all():
        igual = _q(db, SoftwareVersion, org).filter(SoftwareVersion.product_id == destino.id,
                                                    SoftwareVersion.version == v.version).first()
        if igual is None:
            v.product_id = destino.id
        else:
            for tabla, col in ((SoftwareComponent, SoftwareComponent.parent_version_id),
                               (SoftwareInstance, SoftwareInstance.version_id)):
                for fila in _q(db, tabla, org).filter(col == v.id).all():
                    setattr(fila, col.key, igual.id)
            db.flush()
            db.delete(v)
        movidas["versions"] += 1
    for c in _q(db, SoftwareComponent, org).filter(SoftwareComponent.component_product_id == origen.id).all():
        c.component_product_id = destino.id
        movidas["components"] += 1
    for i in _q(db, SoftwareInstance, org).filter(SoftwareInstance.product_id == origen.id).all():
        i.product_id = destino.id
        movidas["instances"] += 1
    for f in _q(db, VulnerabilityFinding, org).filter(VulnerabilityFinding.product_id == origen.id).all():
        f.product_id = destino.id
        movidas["findings"] += 1
    for l in _q(db, SoftwareProductLicense, org).filter(SoftwareProductLicense.product_id == origen.id).all():
        if _q(db, SoftwareProductLicense, org).filter(SoftwareProductLicense.product_id == destino.id,
                                                      SoftwareProductLicense.license_id == l.license_id).first():
            db.delete(l)
        else:
            l.product_id = destino.id
        movidas["licenses"] += 1
    alias = set(_json(destino.aliases, [])) | {origen.name} | set(_json(origen.aliases, []))
    destino.aliases = json.dumps(sorted(alias))
    origen.is_active = False
    origen.lifecycle_status = "retired"
    origen.match_key = f"merged:{origen.id}"
    db.flush()
    audit_log(db, usuario, "UPDATE", "sw_product", destino.id, destino.name,
              metadata={"merged_from": origen.id, "merged_name": origen.name, **movidas})
    return movidas


# ── Versiones ────────────────────────────────────────────────────────────────

def serializar_version(v: SoftwareVersion, extra: Optional[dict] = None) -> dict:
    hoy = date.today()
    return {"id": v.id, "product_id": v.product_id, "version": v.version, "cycle": v.cycle,
            "release_date": v.release_date.isoformat() if v.release_date else None,
            "support_end": v.support_end.isoformat() if v.support_end else None,
            "eol_date": v.eol_date.isoformat() if v.eol_date else None,
            "extended_support_end": v.extended_support_end.isoformat() if v.extended_support_end else None,
            "is_latest": v.is_latest, "lifecycle_source": v.lifecycle_source, "notes": v.notes,
            "is_eol": bool(v.eol_date and v.eol_date < hoy),
            "is_unsupported": bool(v.support_end and v.support_end < hoy), **(extra or {})}


def asegurar_version(db: Session, org, p: SoftwareProduct, texto: Optional[str]) -> Optional[SoftwareVersion]:
    texto = (texto or "").strip()[:100]
    if not texto:
        return None
    v = _q(db, SoftwareVersion, org).filter(SoftwareVersion.product_id == p.id, SoftwareVersion.version == texto).first()
    if v is None:
        v = SoftwareVersion(organization_id=org, product_id=p.id, version=texto)
        db.add(v)
        db.flush()
    return v


def _aplicar_version(v: SoftwareVersion, datos: dict) -> None:
    for k in ("cycle", "notes", "lifecycle_source"):
        if k in datos:
            setattr(v, k, (str(datos[k]).strip() or None) if datos[k] is not None else None)
    for k in ("release_date", "support_end", "eol_date", "extended_support_end"):
        if k in datos:
            setattr(v, k, _fecha(datos[k]))
    if "is_latest" in datos:
        v.is_latest = bool(datos["is_latest"])


def crear_version(db: Session, org, p: SoftwareProduct, datos: dict, usuario=None) -> SoftwareVersion:
    texto = (datos.get("version") or "").strip()
    if not texto:
        raise error(422, "sw_version_obligatoria")
    if _q(db, SoftwareVersion, org).filter(SoftwareVersion.product_id == p.id,
                                           SoftwareVersion.version == texto).first():
        raise error(409, "sw_version_duplicada")
    v = SoftwareVersion(organization_id=org, product_id=p.id, version=texto[:100], lifecycle_source="manual")
    _aplicar_version(v, datos)
    db.add(v)
    db.flush()
    audit_log(db, usuario, "CREATE", "sw_version", v.id, f"{p.name} {v.version}", new_values=serializar_version(v))
    return v


def actualizar_version(db: Session, v: SoftwareVersion, datos: dict, usuario=None) -> SoftwareVersion:
    antes = serializar_version(v)
    _aplicar_version(v, datos)
    if "version" in datos and (datos["version"] or "").strip() and datos["version"].strip() != v.version:
        v.version = datos["version"].strip()[:100]
    db.flush()
    audit_log(db, usuario, "UPDATE", "sw_version", v.id, v.version, old_values=antes, new_values=serializar_version(v))
    return v


def borrar_version(db: Session, v: SoftwareVersion, usuario=None) -> None:
    audit_log(db, usuario, "DELETE", "sw_version", v.id, v.version, old_values=serializar_version(v))
    db.delete(v)
    db.flush()


def ciclo_de_vida(db: Session, org, product_id: str, texto: Optional[str]) -> Optional[SoftwareVersion]:
    """La fila que da el ciclo de vida de una versión observada: la exacta, o la de su rama."""
    from app.services.cmdb_software.versiones import en_rama
    if not texto:
        return None
    filas = _q(db, SoftwareVersion, org).filter(SoftwareVersion.product_id == product_id).all()
    exacta = next((f for f in filas if f.version == texto and (f.eol_date or f.support_end)), None)
    if exacta:
        return exacta
    ramas = [f for f in filas if (f.cycle and en_rama(texto, f.cycle)) and (f.eol_date or f.support_end)]
    ramas.sort(key=lambda f: len(f.cycle or ""), reverse=True)
    return ramas[0] if ramas else None


# ── Componentes ──────────────────────────────────────────────────────────────

def serializar_componente(c: SoftwareComponent, prod: Optional[SoftwareProduct] = None) -> dict:
    return {"id": c.id, "parent_version_id": c.parent_version_id, "component_product_id": c.component_product_id,
            "component_name": prod.name if prod else None, "component_category": prod.category if prod else None,
            "component_version": c.component_version, "relation": c.relation, "scope": c.scope, "direct": c.direct,
            "via_component_id": c.via_component_id, "purl": c.purl, "license_spdx": c.license_spdx,
            "source": c.source, "notes": c.notes}


def anadir_componente(db: Session, org, v: SoftwareVersion, datos: dict, usuario=None) -> SoftwareComponent:
    if datos.get("component_product_id"):
        prod = producto(db, org, datos["component_product_id"])
    else:
        if not (datos.get("name") or datos.get("purl")):
            raise error(422, "sw_nombre_obligatorio")
        prod, _ = buscar_o_crear_producto(db, org, datos.get("name"), datos.get("purl"), datos.get("purl_type"),
                                          datos.get("purl_namespace"), datos.get("cpe"), datos.get("category"),
                                          licencia=datos.get("license_spdx"), usuario=usuario)
    version_c = (datos.get("component_version") or datos.get("version") or "").strip() or None
    if version_c is None and datos.get("purl"):
        p = ids.parsear_purl(datos["purl"])
        version_c = p.version if p else None
    c = SoftwareComponent(
        organization_id=org, parent_version_id=v.id, component_product_id=prod.id, component_version=version_c,
        relation=_validar("relation", datos.get("relation") or "library", RELACIONES_COMPONENTE, True),
        scope=_validar("scope", datos.get("scope") or "required", AMBITOS, True),
        direct=bool(datos.get("direct", True)), via_component_id=datos.get("via_component_id"),
        purl=datos.get("purl") or (ids.construir_purl(prod.purl_type, prod.purl_namespace, prod.purl_name, version_c)
                                   if prod.purl_name else None),
        license_spdx=datos.get("license_spdx") or prod.license_spdx, source="manual", notes=datos.get("notes"))
    if c.via_component_id:
        _uno(db, SoftwareComponent, org, c.via_component_id, "sw_componente_no_encontrado")
        c.direct = False
    db.add(c)
    if version_c:
        asegurar_version(db, org, prod, version_c)
    db.flush()
    audit_log(db, usuario, "CREATE", "sw_component", c.id, f"{prod.name} {version_c or ''}".strip(),
              new_values=serializar_componente(c, prod))
    return c


def borrar_componente(db: Session, org, c: SoftwareComponent, usuario=None) -> None:
    audit_log(db, usuario, "DELETE", "sw_component", c.id, c.component_version, old_values=serializar_componente(c))
    for hijo in _q(db, SoftwareComponent, org).filter(SoftwareComponent.via_component_id == c.id).all():
        hijo.via_component_id = None
    db.delete(c)
    db.flush()


# ── Instancias ───────────────────────────────────────────────────────────────

def serializar_instancia(i: SoftwareInstance, prod: Optional[SoftwareProduct] = None,
                         host: Optional[ConfigurationItem] = None, extra: Optional[dict] = None) -> dict:
    return {
        "id": i.id, "product_id": i.product_id, "product_name": prod.name if prod else None,
        "product_category": prod.category if prod else None, "version_id": i.version_id, "version": i.version,
        "name": i.name, "ci_id": i.ci_id, "ci_name": host.name if host else None,
        "ci_hostname": host.hostname if host else None, "ci_ip": host.ip_address if host else None,
        "ci_type": (getattr(host.ci_type, "value", host.ci_type) if host else None),
        "own_ci_id": i.own_ci_id, "environment": i.environment, "status": i.status,
        "install_path": i.install_path, "config_path": i.config_path, "ports": _json(i.ports, []),
        "exposure": i.exposure, "criticality": i.criticality, "owner_user_id": i.owner_user_id,
        "client_id": i.client_id, "service_ci_id": i.service_ci_id, "license_id": i.license_id,
        "alm_install_id": i.alm_install_id, "config_format": i.config_format, "config": _json(i.config_json, None),
        "config_hash": i.config_hash, "baseline_approved_at": i.baseline_approved_at.isoformat()
        if i.baseline_approved_at else None, "drift_detected_at": i.drift_detected_at.isoformat()
        if i.drift_detected_at else None, "source": i.source,
        "last_seen_at": i.last_seen_at.isoformat() if i.last_seen_at else None, "notes": i.notes,
        "is_active": i.is_active, "created_at": i.created_at.isoformat() if i.created_at else None,
        **(extra or {}),
    }


def registrar_configuracion(db: Session, i: SoftwareInstance, config: Optional[dict], origen: str,
                            usuario=None, formato: Optional[str] = None) -> list[str]:
    """Guarda la configuración (ya enmascarada), deja la foto y detecta la deriva. Devuelve las claves cambiadas."""
    nueva = cfg.enmascarar(config) if config else None
    huella = cfg.huella(nueva)
    if huella == i.config_hash:
        return []
    anterior = _json(i.config_json, None)
    cambiadas = cfg.diferencias(anterior, nueva)
    i.config_json = json.dumps(nueva, default=str) if nueva is not None else None
    i.config_hash = huella
    if formato:
        i.config_format = formato
    db.add(SoftwareConfigSnapshot(organization_id=i.organization_id, instance_id=i.id, config_json=i.config_json,
                                  config_hash=huella, version=i.version, changed_keys=json.dumps(cambiadas),
                                  source=origen, created_by=getattr(usuario, "id", None)))
    if i.baseline_config_json:
        base = _json(i.baseline_config_json, {})
        i.drift_detected_at = ahora() if cfg.huella(base) != huella else None
    # Auditoría: QUÉ claves cambian; los valores ya van enmascarados.
    audit_log(db, usuario, "UPDATE", "sw_instance_config", i.id, i.name,
              old_values={"config_hash": anterior and cfg.huella(anterior)}, new_values={"config_hash": huella},
              metadata={"changed_keys": cambiadas[:200], "source": origen})
    return cambiadas


def _aplicar_instancia(db, org, i: SoftwareInstance, datos: dict) -> None:
    from app.models.alm import ALMLicense, ALMSoftwareInstall
    from app.models.clients import Client
    for k, permitidos in (("environment", ENTORNOS), ("status", ESTADOS_INSTANCIA), ("exposure", EXPOSICIONES)):
        if k in datos and datos[k]:
            setattr(i, k, _validar(k, datos[k], permitidos, True))
    if "criticality" in datos:
        i.criticality = _validar("criticality", datos["criticality"], CRITICIDADES)
    for k in ("ci_id", "own_ci_id", "service_ci_id"):
        if k in datos:
            setattr(i, k, _ci_opcional(db, org, datos[k]))
    if "client_id" in datos:
        if datos["client_id"] and not _q(db, Client, org).filter(Client.id == datos["client_id"]).first():
            raise error(422, "sw_valor_no_valido", campo="client_id", valor=datos["client_id"])
        i.client_id = datos["client_id"] or None
    if "license_id" in datos:
        if datos["license_id"] and not _q(db, ALMLicense, org).filter(ALMLicense.id == datos["license_id"]).first():
            raise error(422, "sw_valor_no_valido", campo="license_id", valor=datos["license_id"])
        i.license_id = datos["license_id"] or None
    if "alm_install_id" in datos:
        if datos["alm_install_id"] and not _q(db, ALMSoftwareInstall, org).filter(
                ALMSoftwareInstall.id == datos["alm_install_id"]).first():
            raise error(422, "sw_valor_no_valido", campo="alm_install_id", valor=datos["alm_install_id"])
        i.alm_install_id = datos["alm_install_id"] or None
    for k in ("name", "install_path", "config_path", "owner_user_id", "notes", "external_key"):
        if k in datos:
            setattr(i, k, (str(datos[k]).strip() or None) if datos[k] is not None else None)
    if "ports" in datos:
        puertos = [int(p) for p in (datos["ports"] or []) if str(p).strip().isdigit()]
        i.ports = json.dumps(sorted(set(puertos))) if puertos else None


def crear_instancia(db: Session, org, datos: dict, usuario=None, origen: str = "manual",
                    auditar: bool = True) -> SoftwareInstance:
    p = producto(db, org, datos.get("product_id"))
    i = SoftwareInstance(organization_id=org, product_id=p.id, source=origen, created_by=getattr(usuario, "id", None),
                         last_seen_at=ahora())
    _aplicar_instancia(db, org, i, datos)
    texto = (datos.get("version") or "").strip() or None
    if datos.get("version_id"):
        v = version(db, org, datos["version_id"])
        i.version_id, i.version = v.id, v.version
    elif texto:
        v = asegurar_version(db, org, p, texto)
        i.version_id, i.version = v.id, v.version
    db.add(i)
    db.flush()
    config, formato = cfg.interpretar(datos.get("config"), datos.get("config_text"), datos.get("config_format"),
                                      p.name, datos.get("config_path"))
    if config:
        registrar_configuracion(db, i, config, origen, usuario, formato)
    _changelog_ci(db, i.ci_id, usuario, "updated", "software", None, f"{p.name} {i.version or ''}".strip(),
                  f"Software instalado: {p.name} {i.version or ''}".strip())
    if auditar:
        audit_log(db, usuario, "CREATE", "sw_instance", i.id, i.name or p.name,
                  new_values=serializar_instancia(i, p))
    return i


def actualizar_instancia(db: Session, org, i: SoftwareInstance, datos: dict, usuario=None,
                         origen: str = "manual", auditar: bool = True) -> SoftwareInstance:
    p = producto(db, org, i.product_id)
    antes = serializar_instancia(i, p)
    ci_antes, version_antes = i.ci_id, i.version
    _aplicar_instancia(db, org, i, datos)
    if datos.get("version_id"):
        v = version(db, org, datos["version_id"])
        i.version_id, i.version = v.id, v.version
    elif "version" in datos and (datos["version"] or "").strip() and datos["version"].strip() != i.version:
        v = asegurar_version(db, org, p, datos["version"])
        i.version_id, i.version = v.id, v.version
    if any(k in datos for k in ("config", "config_text")):
        config, formato = cfg.interpretar(datos.get("config"), datos.get("config_text"),
                                          datos.get("config_format") or i.config_format, p.name, i.config_path)
        registrar_configuracion(db, i, config, origen, usuario, formato)
    i.last_seen_at = ahora() if origen != "manual" else i.last_seen_at
    db.flush()
    if version_antes != i.version:
        _changelog_ci(db, i.ci_id, usuario, "updated", f"software:{p.name}", version_antes, i.version,
                      f"{p.name}: {version_antes or '—'} → {i.version or '—'}")
    if ci_antes != i.ci_id:
        _changelog_ci(db, ci_antes, usuario, "updated", "software", p.name, None, f"Software retirado: {p.name}")
        _changelog_ci(db, i.ci_id, usuario, "updated", "software", None, p.name, f"Software instalado: {p.name}")
    if auditar:
        despues = serializar_instancia(i, p)
        cambios = {k for k in despues if antes.get(k) != despues.get(k)} - {"config"}
        if cambios:
            audit_log(db, usuario, "UPDATE", "sw_instance", i.id, i.name or p.name,
                      old_values={k: antes.get(k) for k in cambios}, new_values={k: despues.get(k) for k in cambios})
    return i


def retirar_instancia(db: Session, org, i: SoftwareInstance, usuario=None, motivo: str = "manual") -> None:
    p = producto(db, org, i.product_id)
    i.status = "retired"
    i.is_active = False
    db.flush()
    _changelog_ci(db, i.ci_id, usuario, "updated", "software", f"{p.name} {i.version or ''}".strip(), None,
                  f"Software retirado: {p.name}")
    audit_log(db, usuario, "DELETE", "sw_instance", i.id, i.name or p.name, metadata={"reason": motivo})


def aprobar_linea_base_de_instancia(db: Session, i: SoftwareInstance, usuario=None) -> None:
    if not i.config_json:
        raise error(422, "sw_sin_configuracion")
    i.baseline_config_json = i.config_json
    i.baseline_approved_at = ahora()
    i.baseline_approved_by = getattr(usuario, "id", None)
    i.drift_detected_at = None
    db.flush()
    audit_log(db, usuario, "APPROVE", "sw_instance_baseline", i.id, i.name, metadata={"config_hash": i.config_hash})


def historial_de_configuracion(db: Session, org, i: SoftwareInstance, limite: int = 50) -> list[dict]:
    filas = (_q(db, SoftwareConfigSnapshot, org).filter(SoftwareConfigSnapshot.instance_id == i.id)
             .order_by(SoftwareConfigSnapshot.created_at.desc()).limit(limite).all())
    return [{"id": s.id, "config": _json(s.config_json, None), "config_hash": s.config_hash, "version": s.version,
             "changed_keys": _json(s.changed_keys, []), "source": s.source, "created_by": s.created_by,
             "created_at": s.created_at.isoformat() if s.created_at else None} for s in filas]


# ── Relaciones ───────────────────────────────────────────────────────────────

def serializar_relacion(r: SoftwareInstanceRelation) -> dict:
    return {"id": r.id, "source_instance_id": r.source_instance_id, "target_instance_id": r.target_instance_id,
            "target_ci_id": r.target_ci_id, "relation_type": r.relation_type, "details": r.details}


def crear_relacion(db: Session, org, datos: dict, usuario=None) -> SoftwareInstanceRelation:
    origen = instancia(db, org, datos.get("source_instance_id"))
    tipo = _validar("relation_type", datos.get("relation_type"), RELACIONES, True)
    destino_i = instancia(db, org, datos["target_instance_id"]).id if datos.get("target_instance_id") else None
    destino_c = ci(db, org, datos["target_ci_id"]).id if datos.get("target_ci_id") else None
    if not destino_i and not destino_c:
        raise error(422, "sw_relacion_sin_destino")
    if destino_i == origen.id:
        raise error(422, "sw_relacion_a_si_misma")
    r = SoftwareInstanceRelation(organization_id=org, source_instance_id=origen.id, target_instance_id=destino_i,
                                 target_ci_id=destino_c, relation_type=tipo,
                                 details=(datos.get("details") or None) and str(datos["details"])[:300],
                                 created_by=getattr(usuario, "id", None))
    db.add(r)
    db.flush()
    audit_log(db, usuario, "CREATE", "sw_instance_relation", r.id, tipo, new_values=serializar_relacion(r))
    return r


def borrar_relacion(db: Session, org, relacion_id: str, usuario=None) -> None:
    r = _uno(db, SoftwareInstanceRelation, org, relacion_id, "sw_relacion_no_encontrada")
    audit_log(db, usuario, "DELETE", "sw_instance_relation", r.id, r.relation_type, old_values=serializar_relacion(r))
    db.delete(r)
    db.flush()


# ── Licencias de ALM ─────────────────────────────────────────────────────────

def vincular_licencia(db: Session, org, p: SoftwareProduct, license_id: str, usuario=None) -> SoftwareProductLicense:
    from app.models.alm import ALMLicense
    lic = _q(db, ALMLicense, org).filter(ALMLicense.id == license_id).first()
    if lic is None:
        raise error(404, "sw_licencia_no_encontrada")
    existente = _q(db, SoftwareProductLicense, org).filter(SoftwareProductLicense.product_id == p.id,
                                                           SoftwareProductLicense.license_id == lic.id).first()
    if existente:
        return existente
    v = SoftwareProductLicense(organization_id=org, product_id=p.id, license_id=lic.id,
                               created_by=getattr(usuario, "id", None))
    db.add(v)
    db.flush()
    audit_log(db, usuario, "CREATE", "sw_product_license", v.id, f"{p.name} ↔ {lic.name}",
              new_values={"product_id": p.id, "license_id": lic.id})
    return v


def desvincular_licencia(db: Session, org, p: SoftwareProduct, license_id: str, usuario=None) -> None:
    v = _q(db, SoftwareProductLicense, org).filter(SoftwareProductLicense.product_id == p.id,
                                                   SoftwareProductLicense.license_id == license_id).first()
    if v is None:
        raise error(404, "sw_licencia_no_encontrada")
    audit_log(db, usuario, "DELETE", "sw_product_license", v.id, p.name,
              old_values={"product_id": p.id, "license_id": license_id})
    db.delete(v)
    db.flush()


def licencias_de(db: Session, org, p: SoftwareProduct) -> list[dict]:
    from app.models.alm import ALMLicense
    filas = (db.query(ALMLicense).join(SoftwareProductLicense, SoftwareProductLicense.license_id == ALMLicense.id)
             .filter(SoftwareProductLicense.product_id == p.id))
    if org:
        filas = filas.filter(SoftwareProductLicense.organization_id == org)
    return [{"id": l.id, "name": l.name, "product_name": l.product_name, "version": l.version, "edition": l.edition,
             "type": getattr(l.type, "value", l.type), "status": getattr(l.status, "value", l.status),
             "total_seats": l.total_seats, "expiry_date": l.expiry_date.isoformat() if l.expiry_date else None,
             "vendor_id": l.vendor_id, "contract_id": l.contract_id} for l in filas.all()]


# ── Líneas base de producto ──────────────────────────────────────────────────

def _validar_reglas(reglas: Any) -> list[dict]:
    if not isinstance(reglas, list) or not reglas:
        raise error(422, "sw_linea_base_reglas", detalle="lista vacía")
    salida = []
    for r in reglas:
        if not isinstance(r, dict) or not str(r.get("key") or "").strip():
            raise error(422, "sw_linea_base_reglas", detalle="falta la clave")
        if (r.get("op") or "eq") not in cfg.OPERADORES:
            raise error(422, "sw_linea_base_reglas", detalle=str(r.get("op")))
        if (r.get("severity") or "medium") not in CRITICIDADES:
            raise error(422, "sw_linea_base_reglas", detalle=str(r.get("severity")))
        salida.append({"key": str(r["key"]).strip(), "op": r.get("op") or "eq", "value": r.get("value"),
                       "severity": r.get("severity") or "medium", "description": r.get("description")})
    return salida


def serializar_linea_base(b: SoftwareBaseline) -> dict:
    return {"id": b.id, "product_id": b.product_id, "name": b.name, "rules": _json(b.rules_json, []),
            "environment": b.environment, "is_active": b.is_active, "approved_by": b.approved_by,
            "approved_at": b.approved_at.isoformat() if b.approved_at else None}


def guardar_linea_base(db: Session, org, p: SoftwareProduct, datos: dict, usuario=None,
                       b: Optional[SoftwareBaseline] = None) -> SoftwareBaseline:
    reglas = _validar_reglas(datos.get("rules"))
    nombre = (datos.get("name") or "").strip()
    if not nombre:
        raise error(422, "sw_nombre_obligatorio")
    entorno = _validar("environment", datos.get("environment"), ENTORNOS)
    antes = serializar_linea_base(b) if b else None
    if b is None:
        b = SoftwareBaseline(organization_id=org, product_id=p.id, created_by=getattr(usuario, "id", None))
        db.add(b)
    b.name, b.rules_json, b.environment = nombre[:200], json.dumps(reglas), entorno
    if "is_active" in datos:
        b.is_active = bool(datos["is_active"])
    # Cambiar las reglas retira la aprobación: hay que volver a aprobarlas.
    b.approved_by, b.approved_at = None, None
    db.flush()
    audit_log(db, usuario, "UPDATE" if antes else "CREATE", "sw_baseline", b.id, b.name, old_values=antes,
              new_values=serializar_linea_base(b))
    return b


def aprobar_linea_base(db: Session, b: SoftwareBaseline, usuario) -> None:
    b.approved_by, b.approved_at = usuario.id, ahora()
    db.flush()
    audit_log(db, usuario, "APPROVE", "sw_baseline", b.id, b.name)
