"""Entradas al catálogo: SBOM y dependencias, CSV, agente, escáneres y Activos.

Conciliación (sin duplicar):

- producto: por clave (`identificadores.clave_de_producto`) y alias;
- versión: producto + texto;
- componente: versión de software + producto + versión + componente vía;
- instancia: CI + producto + ruta de instalación (o clave externa, o nombre).

Cada importación deja `sw_sbom_imports` y una entrada de auditoría con las
cifras.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.cmdb_software import (SoftwareComponent, SoftwareInstance, SoftwareProduct, SoftwareSbomImport,
                                      SoftwareVersion)
from app.models.service_desk.cmdb import ConfigurationItem
from app.services.audit import audit_log
from app.services.cmdb_software import catalogo as cat
from app.services.cmdb_software import configuracion as cfg
from app.services.cmdb_software import formatos

TAMANO_MAXIMO_MB = 25


def _sha(contenido: bytes | str) -> str:
    datos = contenido.encode() if isinstance(contenido, str) else contenido
    return hashlib.sha256(datos).hexdigest()


def comprobar_fichero(contenido: bytes) -> None:
    if not contenido:
        raise error(422, "sw_fichero_vacio")
    if len(contenido) > TAMANO_MAXIMO_MB * 1024 * 1024:
        raise error(413, "sw_fichero_demasiado_grande", max=TAMANO_MAXIMO_MB)


# ── Componentes de una versión de software ───────────────────────────────────

def aplicar_componentes(db: Session, org, v: SoftwareVersion, componentes: list[dict], fuente: str,
                        formato: str, usuario=None, reemplazar: bool = False, nombre: Optional[str] = None,
                        sha256: Optional[str] = None) -> dict:
    """Upsert de la composición de `v`. Con `reemplazar`, quita lo que ya no viene (de esa fuente)."""
    imp = SoftwareSbomImport(organization_id=org, version_id=v.id, kind="components", format=formato,
                             filename=nombre, sha256=sha256, created_by=getattr(usuario, "id", None))
    db.add(imp)
    db.flush()
    existentes = {(c.component_product_id, c.component_version or ""): c
                  for c in cat._q(db, SoftwareComponent, org).filter(SoftwareComponent.parent_version_id == v.id)}
    vistos: set = set()
    por_ref: dict[str, SoftwareComponent] = {}
    creados = actualizados = productos_nuevos = 0
    pendientes_via: list[tuple[SoftwareComponent, str]] = []
    for c in componentes:
        if not c.get("name"):
            continue
        prod, nuevo = cat.buscar_o_crear_producto(db, org, c["name"], c.get("purl"), c.get("type"),
                                                  c.get("namespace"), c.get("cpe"), c.get("category"),
                                                  licencia=c.get("license"), usuario=usuario)
        productos_nuevos += int(nuevo)
        clave = (prod.id, c.get("version") or "")
        fila = existentes.get(clave)
        if fila is None:
            fila = SoftwareComponent(organization_id=org, parent_version_id=v.id, component_product_id=prod.id,
                                     component_version=c.get("version"), source=fuente)
            db.add(fila)
            existentes[clave] = fila
            creados += 1
        else:
            actualizados += 1
        fila.relation = c.get("relation") or ("base_image" if prod.category == "container_image" else
                                              prod.category if prod.category in cat.RELACIONES_COMPONENTE
                                              else "library")
        fila.scope = c.get("scope") if c.get("scope") in cat.AMBITOS else "required"
        fila.direct = bool(c.get("direct", True))
        fila.purl = (c.get("purl") or None) and c["purl"][:500]
        fila.license_spdx = (c.get("license") or prod.license_spdx or None) and (c.get("license") or prod.license_spdx)[:200]
        fila.sbom_import_id = imp.id
        vistos.add(clave)
        por_ref[c.get("ref") or f"{prod.id}@{c.get('version')}"] = fila
        if c.get("via"):
            pendientes_via.append((fila, c["via"]))
        if c.get("version"):
            cat.asegurar_version(db, org, prod, c["version"])
    db.flush()
    for fila, via in pendientes_via:
        padre = por_ref.get(via)
        fila.via_component_id = padre.id if padre is not None and padre.id != fila.id else None
    quitados = 0
    if reemplazar:
        for clave, fila in list(existentes.items()):
            if clave not in vistos and fila.source in (fuente, "sbom", "lockfile", "scan", "agent"):
                for hijo in cat._q(db, SoftwareComponent, org).filter(SoftwareComponent.via_component_id == fila.id):
                    hijo.via_component_id = None
                db.delete(fila)
                quitados += 1
    imp.total, imp.created, imp.updated, imp.removed = len(componentes), creados, actualizados, quitados
    imp.summary_json = json.dumps({"new_products": productos_nuevos})
    db.flush()
    audit_log(db, usuario, "IMPORT", "sw_components", v.id, f"{formato}: {nombre or ''}".strip(),
              metadata={"import_id": imp.id, "total": imp.total, "created": creados, "updated": actualizados,
                        "removed": quitados, "new_products": productos_nuevos, "sha256": sha256})
    return {"import_id": imp.id, "format": formato, "total": imp.total, "created": creados, "updated": actualizados,
            "removed": quitados, "new_products": productos_nuevos}


def importar_fichero_de_componentes(db: Session, org, v: SoftwareVersion, contenido: bytes, nombre: Optional[str],
                                    formato: Optional[str], usuario=None, reemplazar: bool = False) -> dict:
    """SBOM o fichero de dependencias, o informe de Trivy/Grype (que trae también avisos)."""
    from app.services.cmdb_software import escaneres
    comprobar_fichero(contenido)
    sha = _sha(contenido)
    try:
        datos = json.loads(contenido.decode("utf-8-sig", errors="replace")) if contenido.lstrip()[:1] in (b"{", b"[") \
            else None
    except ValueError:
        datos = None
    if escaneres.es_informe(datos):
        tipo, componentes, avisos = escaneres.leer_informe(contenido)
        resultado = aplicar_componentes(db, org, v, componentes, "scan", tipo, usuario, reemplazar, nombre, sha)
        from app.services.cmdb_software.avisos import guardar_avisos
        resultado["vulnerabilities"] = guardar_avisos(db, org, avisos, tipo)
        return resultado
    try:
        r = formatos.leer(contenido, nombre, formato)
    except formatos.FormatoNoReconocido:
        raise error(422, "sw_formato_no_reconocido", nombre=nombre or formato or "?")
    except Exception as e:  # noqa: BLE001 - un fichero roto es un 422, no un 500
        raise error(422, "sw_fichero_no_valido", detalle=type(e).__name__)
    fuente = "sbom" if r.formato in ("cyclonedx", "spdx") else "lockfile"
    return aplicar_componentes(db, org, v, r.componentes, fuente, r.formato, usuario, reemplazar, nombre, sha)


def importar_ficheros_de_componentes(db: Session, org, v: SoftwareVersion, ficheros: list[tuple[str, bytes]],
                                     formato: Optional[str], usuario=None, reemplazar: bool = False) -> dict:
    """Uno o varios ficheros (o un zip): pom.xml con su padre, requirements + lock o `pip freeze`…"""
    if len(ficheros) == 1 and not (ficheros[0][0] or "").lower().endswith(".zip") \
            and ficheros[0][1][:4] != b"PK\x03\x04":
        nombre, contenido = ficheros[0]
        return importar_fichero_de_componentes(db, org, v, contenido, nombre, formato, usuario, reemplazar)
    for _n, contenido in ficheros:
        comprobar_fichero(contenido)
    try:
        r = formatos.leer_varios(ficheros)
    except formatos.FormatoNoReconocido as e:
        raise error(422, "sw_formato_no_reconocido", nombre=str(e))
    if not r.componentes and r.ignorados:
        raise error(422, "sw_formato_no_reconocido", nombre=", ".join(r.ignorados[:5]))
    sha = _sha(b"".join(c for _n, c in ficheros))
    nombres = ", ".join(n for n, _c in ficheros)[:300]
    resultado = aplicar_componentes(db, org, v, r.componentes, "lockfile", r.formato[:30], usuario, reemplazar,
                                    nombres, sha)
    resultado["ignored"] = r.ignorados
    resultado["unknown_version"] = sum(1 for c in r.componentes if not c.get("version"))
    return resultado


# ── CSV de catálogo e instancias ─────────────────────────────────────────────

CSV_COLUMNAS = ("name", "vendor", "category", "origin", "version", "purl", "cpe", "license", "criticality",
                "host", "environment", "install_path", "config_path", "ports", "exposure", "instance_name",
                "eol_date", "support_end")


def buscar_ci(db: Session, org, texto: Optional[str]) -> Optional[ConfigurationItem]:
    """CI por código, nombre, hostname o IP (sin distinguir mayúsculas)."""
    if not texto:
        return None
    t = str(texto).strip()
    from sqlalchemy import func, or_
    return (cat._q(db, ConfigurationItem, org)
            .filter(ConfigurationItem.is_active.is_(True),
                    or_(func.lower(ConfigurationItem.name) == t.lower(), func.lower(ConfigurationItem.code) == t.lower(),
                        func.lower(ConfigurationItem.hostname) == t.lower(), ConfigurationItem.ip_address == t))
            .first())


def importar_csv(db: Session, org, contenido: bytes, usuario=None) -> dict:
    comprobar_fichero(contenido)
    texto = contenido.decode("utf-8-sig", errors="replace")
    muestra = texto[:2000]
    delimitador = ";" if muestra.count(";") > muestra.count(",") else ","
    lector = csv.DictReader(io.StringIO(texto), delimiter=delimitador)
    resumen = {"rows": 0, "products_created": 0, "versions": 0, "instances_created": 0, "instances_updated": 0,
               "errors": []}
    for n, fila in enumerate(lector, start=2):
        fila = {(k or "").strip().lower(): (v or "").strip() for k, v in fila.items()}
        if not (fila.get("name") or fila.get("purl")):
            continue
        resumen["rows"] += 1
        try:
            with db.begin_nested():
                prod, nuevo = cat.buscar_o_crear_producto(db, org, fila.get("name"), fila.get("purl") or None, None,
                                                          None, fila.get("cpe") or None,
                                                          fila.get("category") or None, fila.get("origin") or None,
                                                          fila.get("license") or None, fila.get("vendor") or None,
                                                          usuario)
                if nuevo:
                    resumen["products_created"] += 1
                    if fila.get("criticality") in cat.CRITICIDADES:
                        prod.criticality = fila["criticality"]
                v = cat.asegurar_version(db, org, prod, fila.get("version"))
                if v is not None:
                    resumen["versions"] += 1
                    for k in ("eol_date", "support_end"):
                        if fila.get(k):
                            setattr(v, k, cat._fecha(fila[k]))
                            v.lifecycle_source = "import"
                host = buscar_ci(db, org, fila.get("host"))
                if fila.get("host") and host is None:
                    resumen["errors"].append({"row": n, "error": "sw_ci_no_encontrado", "value": fila.get("host")})
                if host is not None:
                    datos = {"product_id": prod.id, "version": fila.get("version") or None, "ci_id": host.id,
                             "environment": fila.get("environment") or "prod",
                             "install_path": fila.get("install_path") or None,
                             "config_path": fila.get("config_path") or None,
                             "name": fila.get("instance_name") or None,
                             "ports": [p for p in (fila.get("ports") or "").replace(";", " ").replace(",", " ").split()],
                             "exposure": fila.get("exposure") or "internal"}
                    existente = _instancia_existente(db, org, prod.id, host.id, datos.get("install_path"),
                                                     None, datos.get("name"))
                    if existente is None:
                        cat.crear_instancia(db, org, datos, usuario, origen="csv", auditar=False)
                        resumen["instances_created"] += 1
                    else:
                        cat.actualizar_instancia(db, org, existente, datos, usuario, origen="csv", auditar=False)
                        resumen["instances_updated"] += 1
        except Exception as e:  # noqa: BLE001 - una fila mala no tumba el resto
            codigo = getattr(e, "code", None) or type(e).__name__
            resumen["errors"].append({"row": n, "error": codigo})
    imp = SoftwareSbomImport(organization_id=org, kind="catalog", format="csv", total=resumen["rows"],
                             created=resumen["products_created"] + resumen["instances_created"],
                             updated=resumen["instances_updated"], status="partial" if resumen["errors"] else "ok",
                             summary_json=json.dumps(resumen)[:20000], created_by=getattr(usuario, "id", None),
                             sha256=_sha(contenido))
    db.add(imp)
    db.flush()
    audit_log(db, usuario, "IMPORT", "sw_catalog", imp.id, "csv", metadata={k: v for k, v in resumen.items()
                                                                           if k != "errors"} | {"errors": len(resumen["errors"])})
    resumen["errors"] = resumen["errors"][:100]
    return resumen


def _instancia_existente(db, org, product_id, ci_id, ruta, clave_externa, nombre) -> Optional[SoftwareInstance]:
    q = cat._q(db, SoftwareInstance, org).filter(SoftwareInstance.product_id == product_id,
                                                SoftwareInstance.ci_id == ci_id,
                                                SoftwareInstance.is_active.is_(True))
    if clave_externa:
        fila = q.filter(SoftwareInstance.external_key == clave_externa).first()
        if fila:
            return fila
    if ruta:
        fila = q.filter(SoftwareInstance.install_path == ruta).first()
        if fila:
            return fila
    if nombre:
        fila = q.filter(SoftwareInstance.name == nombre).first()
        if fila:
            return fila
    candidatas = q.all()
    return candidatas[0] if len(candidatas) == 1 and not ruta else None


# ── Inventario del agente (o de un conector de escaneo) ─────────────────────

def aplicar_inventario(db: Session, org, ci_id: str, inventario: dict, origen: str = "agent", usuario=None) -> dict:
    """``{complete, instances: [{name, version, category, purl, cpe, install_path, config_path, ports,
    config, config_text, config_format, components, sbom, environment, exposure}]}`` sobre el CI `ci_id`."""
    instancias = inventario.get("instances") or []
    resumen = {"created": 0, "updated": 0, "stopped": 0, "components": 0}
    vistas: set = set()
    for d in instancias[:500]:
        if not isinstance(d, dict) or not (d.get("name") or d.get("purl")):
            continue
        prod, _ = cat.buscar_o_crear_producto(db, org, d.get("name"), d.get("purl"), None, None, d.get("cpe"),
                                              d.get("category"), d.get("origin"), d.get("license"), d.get("vendor"))
        clave = d.get("key") or f"{ci_id}:{prod.id}:{d.get('install_path') or ''}"
        existente = _instancia_existente(db, org, prod.id, ci_id, d.get("install_path"), clave, d.get("instance_name"))
        datos = {"product_id": prod.id, "ci_id": ci_id, "version": d.get("version"),
                 "install_path": d.get("install_path"), "config_path": d.get("config_path"),
                 "ports": d.get("ports") or [], "external_key": clave, "name": d.get("instance_name") or d.get("name"),
                 "status": "running"}
        for k in ("environment", "exposure"):
            if d.get(k):
                datos[k] = d[k]
        if d.get("config") or d.get("config_text"):
            datos.update(config=d.get("config"), config_text=d.get("config_text"), config_format=d.get("config_format"))
        if existente is None:
            inst = cat.crear_instancia(db, org, datos, usuario, origen=origen, auditar=False)
            resumen["created"] += 1
        else:
            inst = cat.actualizar_instancia(db, org, existente, datos, usuario, origen=origen, auditar=False)
            if inst.status != "running":
                inst.status = "running"
            resumen["updated"] += 1
        vistas.add(inst.id)
        comps = d.get("components")
        sbom = d.get("sbom")
        if (comps or sbom) and inst.version_id:
            v = cat.version(db, org, inst.version_id)
            if sbom:
                try:
                    r = formatos.leer(json.dumps(sbom) if isinstance(sbom, (dict, list)) else str(sbom))
                    comps = r.componentes
                except Exception:  # noqa: BLE001 - un SBOM roto del agente no tumba el check-in
                    comps = comps or []
            if comps:
                normal = [c if "ref" in c else formatos._componente(c.get("name") or "", c.get("version"),
                                                                     c.get("type") or "generic", c.get("namespace"),
                                                                     c.get("purl"), c.get("license"))
                          for c in comps if isinstance(c, dict)]
                r2 = aplicar_componentes(db, org, v, normal, "agent", "agent", usuario, reemplazar=True)
                resumen["components"] += r2["total"]
    if inventario.get("complete"):
        for inst in cat._q(db, SoftwareInstance, org).filter(SoftwareInstance.ci_id == ci_id,
                                                             SoftwareInstance.source == origen,
                                                             SoftwareInstance.status == "running",
                                                             SoftwareInstance.is_active.is_(True)):
            if inst.id not in vistas:
                inst.status = "stopped"
                resumen["stopped"] += 1
                cat._changelog_ci(db, ci_id, usuario, "updated", "software", inst.name, None,
                                  f"Software no informado por el agente: {inst.name or inst.product_id}")
    db.flush()
    audit_log(db, usuario, "IMPORT", "sw_inventory", ci_id, origen, metadata=resumen)
    return resumen


def procesar_checkin(db: Session, org, ci_id: Optional[str], payload: dict) -> Optional[dict]:
    """Gancho del check-in del agente de la CMDB (`software_inventory`)."""
    inventario = payload.get("software_inventory")
    if not inventario or not ci_id:
        return None
    return aplicar_inventario(db, org, ci_id, inventario, origen="agent")


# ── Conciliación desde Activos (ALM) ─────────────────────────────────────────

def importar_desde_alm(db: Session, org, usuario=None) -> dict:
    """Instalaciones de ALM (licencia × activo con CI) → productos e instancias del catálogo.

    No duplica: el producto por nombre normalizado (y se vincula la licencia);
    la instancia por CI + producto (y se enlaza la instalación).
    """
    from app.models.alm import ALMAsset, ALMLicense, ALMSoftwareInstall
    from app.models.cmdb_software import SoftwareProductLicense
    resumen = {"installs": 0, "products_created": 0, "licenses_linked": 0, "instances_created": 0,
               "instances_linked": 0, "without_ci": 0}
    q = (db.query(ALMSoftwareInstall, ALMLicense, ALMAsset)
         .join(ALMLicense, ALMLicense.id == ALMSoftwareInstall.license_id)
         .join(ALMAsset, ALMAsset.id == ALMSoftwareInstall.asset_id)
         .filter(ALMSoftwareInstall.is_active.is_(True)))
    if org:
        q = q.filter(ALMSoftwareInstall.organization_id == org)
    for inst_alm, lic, activo in q.all():
        resumen["installs"] += 1
        nombre = lic.product_name or lic.name
        fabricante = lic.vendor.name if getattr(lic, "vendor", None) else None
        prod, nuevo = cat.buscar_o_crear_producto(db, org, nombre, categoria="application", origen="purchased",
                                                  fabricante=fabricante, usuario=usuario)
        if nuevo:
            prod.alm_vendor_id = lic.vendor_id
            resumen["products_created"] += 1
        if not cat._q(db, SoftwareProductLicense, org).filter(SoftwareProductLicense.product_id == prod.id,
                                                              SoftwareProductLicense.license_id == lic.id).first():
            db.add(SoftwareProductLicense(organization_id=org, product_id=prod.id, license_id=lic.id,
                                          created_by=getattr(usuario, "id", None)))
            resumen["licenses_linked"] += 1
        if not activo.ci_id:
            resumen["without_ci"] += 1
            continue
        existente = cat._q(db, SoftwareInstance, org).filter(SoftwareInstance.alm_install_id == inst_alm.id).first() \
            or _instancia_existente(db, org, prod.id, activo.ci_id, None, None, None)
        version_txt = inst_alm.version or lic.version
        if existente is None:
            cat.crear_instancia(db, org, {"product_id": prod.id, "ci_id": activo.ci_id, "version": version_txt,
                                          "license_id": lic.id, "alm_install_id": inst_alm.id,
                                          "name": nombre}, usuario, origen="alm", auditar=False)
            resumen["instances_created"] += 1
        else:
            existente.alm_install_id = existente.alm_install_id or inst_alm.id
            existente.license_id = existente.license_id or lic.id
            resumen["instances_linked"] += 1
    db.flush()
    audit_log(db, usuario, "IMPORT", "sw_catalog", None, "alm", metadata=resumen)
    return resumen


def productos_duplicados(db: Session, org, limite: int = 100) -> list[dict]:
    """Productos que parecen el mismo: mismo nombre normalizado o mismo CPE con claves distintas."""
    from app.services.cmdb_software.identificadores import normalizar_texto
    grupos: dict[str, list[SoftwareProduct]] = {}
    for p in cat._q(db, SoftwareProduct, org).filter(SoftwareProduct.is_active.is_(True)).all():
        claves = {f"n:{normalizar_texto(p.name)}"}
        if p.cpe_vendor and p.cpe_product:
            claves.add(f"c:{p.cpe_vendor}:{p.cpe_product}")
        for k in claves:
            grupos.setdefault(k, []).append(p)
    salida, vistos = [], set()
    for k, lista in grupos.items():
        unicos = {p.id: p for p in lista}
        if len(unicos) < 2:
            continue
        ids_ = tuple(sorted(unicos))
        if ids_ in vistos:
            continue
        vistos.add(ids_)
        salida.append({"reason": "same_cpe" if k.startswith("c:") else "same_name",
                       "products": [{"id": p.id, "name": p.name, "match_key": p.match_key, "category": p.category}
                                    for p in unicos.values()]})
        if len(salida) >= limite:
            break
    return salida
