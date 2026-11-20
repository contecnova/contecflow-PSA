"""SBOM y ficheros de dependencias → lista de componentes normalizada.

Formatos: CycloneDX (JSON y XML), SPDX (JSON y etiqueta-valor),
``composer.lock``, ``package-lock.json`` (v1, v2, v3), ``yarn.lock`` (v1),
``requirements.txt``, ``poetry.lock``, ``Pipfile.lock``, ``pom.xml``,
``go.mod``, ``go.sum``, ``Gemfile.lock``, ``Cargo.lock`` y
``packages.lock.json`` (NuGet).

Cada parseador devuelve ``Resultado(formato, raiz, componentes)``; cada
componente es un dict con ``ref``, ``name``, ``namespace``, ``version``,
``type`` (tipo purl), ``purl``, ``cpe``, ``license``, ``scope``
(required/optional/dev/test), ``direct`` (bool), ``via`` (ref del componente
directo que lo trae, para el árbol) y ``category``.

Seguridad: el XML se lee con `defusedxml` (sin entidades externas); el tamaño
lo limita el endpoint.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.cmdb_software.identificadores import construir_purl, datos_de_conocido, parsear_purl


class FormatoNoReconocido(ValueError):
    pass


@dataclass
class Resultado:
    formato: str
    raiz: dict = field(default_factory=dict)
    componentes: list[dict] = field(default_factory=list)
    #: Ficheros de una importación múltiple que no se reconocieron.
    ignorados: list[str] = field(default_factory=list)


_CATEGORIA_CDX = {"library": "library", "framework": "framework", "application": "application",
                  "container": "container_image", "operating-system": "os", "platform": "runtime",
                  "device": "other", "firmware": "other", "file": "other", "machine-learning-model": "other",
                  "data": "other"}


def _componente(name, version=None, type_="generic", namespace=None, purl=None, license_=None, scope="required",
                ref=None, cpe=None, category=None) -> dict:
    p = parsear_purl(purl) if purl else None
    if p:
        type_, namespace, name = p.type, p.namespace, p.name
        version = version or p.version
    version = (str(version).strip() or None) if version is not None else None
    purl_txt = purl or construir_purl(type_, namespace, name, version)
    if category is None:
        conocido = datos_de_conocido(name) if (type_ or "generic") == "generic" else None
        category = conocido["category"] if conocido else ("container_image" if type_ in ("docker", "oci")
                                                          else "library")
    return {"ref": ref or purl_txt or f"{namespace or ''}/{name}@{version or ''}", "name": name,
            "namespace": namespace, "version": version, "type": (type_ or "generic").lower(), "purl": purl_txt,
            "cpe": cpe, "license": license_, "scope": scope, "direct": True, "via": None, "category": category}


def _calcular_vias(componentes: list[dict], directos: Optional[set], grafo: dict[str, list[str]]) -> None:
    """Marca `direct` y `via` recorriendo el grafo desde los directos.

    `directos` None: los que nadie requiere (aproximación para locks sin raíz).
    """
    refs = {c["ref"] for c in componentes}
    if directos is None:
        requeridos = {d for deps in grafo.values() for d in deps}
        directos = {r for r in refs if r not in requeridos} or refs
    via: dict[str, str] = {}
    for d in directos:
        if d not in refs:
            continue
        cola = [d]
        while cola:
            actual = cola.pop(0)
            for hijo in grafo.get(actual, []):
                if hijo in refs and hijo not in directos and hijo not in via:
                    via[hijo] = d
                    cola.append(hijo)
    for c in componentes:
        c["direct"] = c["ref"] in directos
        c["via"] = via.get(c["ref"]) if not c["direct"] else None


# ── CycloneDX ────────────────────────────────────────────────────────────────

def _licencia_cdx(lics) -> Optional[str]:
    salida = []
    for item in lics or []:
        if not isinstance(item, dict):
            continue
        if item.get("expression"):
            salida.append(item["expression"])
        lic = item.get("license") or {}
        if lic.get("id") or lic.get("name"):
            salida.append(lic.get("id") or lic.get("name"))
    return " AND ".join(dict.fromkeys(salida)) or None


def cyclonedx_json(datos: dict) -> Resultado:
    raiz_c = (datos.get("metadata") or {}).get("component") or {}
    raiz = {"name": raiz_c.get("name"), "version": raiz_c.get("version"), "ref": raiz_c.get("bom-ref")}
    componentes = []

    def recorrer(lista):
        for c in lista or []:
            if not isinstance(c, dict) or not c.get("name"):
                continue
            scope = {"optional": "optional", "excluded": "dev"}.get(c.get("scope") or "", "required")
            componentes.append(_componente(c["name"], c.get("version"), "generic", c.get("group"), c.get("purl"),
                                           _licencia_cdx(c.get("licenses")), scope, c.get("bom-ref"), c.get("cpe"),
                                           _CATEGORIA_CDX.get(c.get("type") or "library")))
            recorrer(c.get("components"))
    recorrer(datos.get("components"))
    grafo = {d.get("ref"): list(d.get("dependsOn") or []) for d in datos.get("dependencies") or [] if d.get("ref")}
    directos = set(grafo.get(raiz["ref"], [])) if raiz.get("ref") and raiz["ref"] in grafo else None
    _calcular_vias(componentes, directos, grafo)
    return Resultado("cyclonedx", raiz, componentes)


def cyclonedx_xml(texto: str) -> Resultado:
    from defusedxml import ElementTree as ET
    arbol = ET.fromstring(texto)

    def local(tag):
        return tag.rsplit("}", 1)[-1]

    def hijo(nodo, nombre):
        for h in list(nodo):
            if local(h.tag) == nombre:
                return h
        return None

    def texto_de(nodo, nombre):
        h = hijo(nodo, nombre)
        return h.text.strip() if h is not None and h.text else None

    componentes = []
    raiz = {}
    meta = hijo(arbol, "metadata")
    if meta is not None and hijo(meta, "component") is not None:
        rc = hijo(meta, "component")
        raiz = {"name": texto_de(rc, "name"), "version": texto_de(rc, "version"), "ref": rc.get("bom-ref")}

    def recorrer(nodo):
        if nodo is None:
            return
        for c in list(nodo):
            if local(c.tag) != "component":
                continue
            lic = []
            lics = hijo(c, "licenses")
            if lics is not None:
                for l in list(lics):
                    if local(l.tag) == "expression" and l.text:
                        lic.append(l.text.strip())
                    elif local(l.tag) == "license":
                        lic.append(texto_de(l, "id") or texto_de(l, "name") or "")
            componentes.append(_componente(texto_de(c, "name") or "", texto_de(c, "version"), "generic",
                                           texto_de(c, "group"), texto_de(c, "purl"),
                                           " AND ".join(x for x in lic if x) or None,
                                           "optional" if c.get("scope") == "optional" else "required",
                                           c.get("bom-ref"), texto_de(c, "cpe"),
                                           _CATEGORIA_CDX.get(c.get("type") or "library")))
            recorrer(hijo(c, "components"))
    recorrer(hijo(arbol, "components"))
    componentes = [c for c in componentes if c["name"]]
    grafo: dict = {}
    deps = hijo(arbol, "dependencies")
    if deps is not None:
        for d in list(deps):
            if d.get("ref"):
                grafo[d.get("ref")] = [x.get("ref") for x in list(d) if x.get("ref")]
    directos = set(grafo.get(raiz.get("ref"), [])) if raiz.get("ref") in grafo else None
    _calcular_vias(componentes, directos, grafo)
    return Resultado("cyclonedx", raiz, componentes)


# ── SPDX ─────────────────────────────────────────────────────────────────────

def _licencia_spdx(valor) -> Optional[str]:
    return None if not valor or valor in ("NOASSERTION", "NONE") else valor


def spdx_json(datos: dict) -> Resultado:
    paquetes = {}
    for p in datos.get("packages") or []:
        purl = cpe = None
        for ref in p.get("externalRefs") or []:
            tipo = (ref.get("referenceType") or "").lower()
            if tipo == "purl":
                purl = ref.get("referenceLocator")
            elif tipo.startswith("cpe"):
                cpe = ref.get("referenceLocator")
        paquetes[p.get("SPDXID")] = _componente(p.get("name") or "", p.get("versionInfo"), "generic", None, purl,
                                                _licencia_spdx(p.get("licenseConcluded"))
                                                or _licencia_spdx(p.get("licenseDeclared")),
                                                "required", p.get("SPDXID"), cpe)
    describe = list(datos.get("documentDescribes") or [])
    grafo: dict[str, list[str]] = {}
    for r in datos.get("relationships") or []:
        tipo = r.get("relationshipType")
        a, b = r.get("spdxElementId"), r.get("relatedSpdxElement")
        if tipo == "DESCRIBES" and a == "SPDXRef-DOCUMENT":
            describe.append(b)
        elif tipo in ("DEPENDS_ON", "CONTAINS", "STATIC_LINK", "DYNAMIC_LINK"):
            grafo.setdefault(a, []).append(b)
        elif tipo in ("DEPENDENCY_OF",):
            grafo.setdefault(b, []).append(a)
        elif tipo in ("DEV_DEPENDENCY_OF", "TEST_DEPENDENCY_OF") and a in paquetes:
            paquetes[a]["scope"] = "dev" if tipo.startswith("DEV") else "test"
            grafo.setdefault(b, []).append(a)
    raiz_id = describe[0] if describe else None
    raiz_c = paquetes.pop(raiz_id, None) if raiz_id else None
    raiz = {"name": raiz_c["name"], "version": raiz_c["version"], "ref": raiz_id} if raiz_c else {}
    componentes = [c for c in paquetes.values() if c["name"]]
    directos = set(grafo.get(raiz_id, [])) if raiz_id in grafo else None
    _calcular_vias(componentes, directos, grafo)
    return Resultado("spdx", raiz, componentes)


def spdx_tag_value(texto: str) -> Resultado:
    paquetes: list[dict] = []
    actual: Optional[dict] = None
    rels: list[tuple[str, str, str]] = []
    describe = None
    for linea in texto.splitlines():
        if ":" not in linea:
            continue
        k, v = linea.split(":", 1)
        k, v = k.strip(), v.strip()
        if k == "PackageName":
            actual = {"name": v}
            paquetes.append(actual)
        elif actual is not None and k == "SPDXID":
            actual["id"] = v
        elif actual is not None and k == "PackageVersion":
            actual["version"] = v
        elif actual is not None and k in ("PackageLicenseConcluded", "PackageLicenseDeclared"):
            actual.setdefault("license", _licencia_spdx(v))
        elif actual is not None and k == "ExternalRef":
            partes = v.split()
            if len(partes) >= 3 and partes[1].lower() == "purl":
                actual["purl"] = partes[2]
            elif len(partes) >= 3 and partes[1].lower().startswith("cpe"):
                actual["cpe"] = partes[2]
        elif k == "Relationship":
            partes = v.split()
            if len(partes) == 3:
                rels.append((partes[0], partes[1], partes[2]))
                if partes[1] == "DESCRIBES" and partes[0] == "SPDXRef-DOCUMENT":
                    describe = partes[2]
        elif k == "DocumentDescribes" or (k == "Relationship" and "DESCRIBES" in v):
            describe = describe or v.split()[0]
    datos = {"packages": [{"SPDXID": p.get("id"), "name": p.get("name"), "versionInfo": p.get("version"),
                           "licenseConcluded": p.get("license"),
                           "externalRefs": ([{"referenceType": "purl", "referenceLocator": p["purl"]}] if p.get("purl")
                                            else []) + ([{"referenceType": "cpe23Type", "referenceLocator": p["cpe"]}]
                                                        if p.get("cpe") else [])} for p in paquetes],
             "documentDescribes": [describe] if describe else [],
             "relationships": [{"spdxElementId": a, "relationshipType": t, "relatedSpdxElement": b} for a, t, b in rels]}
    return spdx_json(datos)


# ── PHP ──────────────────────────────────────────────────────────────────────

def composer_lock(datos: dict) -> Resultado:
    componentes, grafo = [], {}
    for clave, scope in (("packages", "required"), ("packages-dev", "dev")):
        for p in datos.get(clave) or []:
            nombre = p.get("name") or ""
            ns, _, n = nombre.rpartition("/")
            lic = p.get("license")
            c = _componente(n, str(p.get("version") or "").lstrip("v") or None, "composer", ns or None,
                            license_=" OR ".join(lic) if isinstance(lic, list) else lic, scope=scope,
                            ref=nombre.lower())
            componentes.append(c)
            grafo[nombre.lower()] = [k.lower() for k in (p.get("require") or {}) if "/" in k]
    _calcular_vias(componentes, None, grafo)
    return Resultado("composer.lock", {}, componentes)


# ── JavaScript ───────────────────────────────────────────────────────────────

def _npm_nombre(nombre: str) -> tuple[Optional[str], str]:
    if nombre.startswith("@") and "/" in nombre:
        ns, n = nombre.split("/", 1)
        return ns, n
    return None, nombre


def package_lock(datos: dict) -> Resultado:
    componentes, grafo = [], {}
    raiz = {"name": datos.get("name"), "version": datos.get("version")}
    paquetes = datos.get("packages")
    if isinstance(paquetes, dict) and paquetes:
        raiz_p = paquetes.get("") or {}
        directos_n = set((raiz_p.get("dependencies") or {}).keys()) | set((raiz_p.get("devDependencies") or {}).keys()) \
            | set((raiz_p.get("optionalDependencies") or {}).keys())
        por_nombre: dict[str, str] = {}
        for ruta, p in paquetes.items():
            if not ruta or p.get("link"):
                continue
            nombre = p.get("name") or ruta.rsplit("node_modules/", 1)[-1]
            ns, n = _npm_nombre(nombre)
            scope = "dev" if p.get("dev") else ("optional" if p.get("optional") else "required")
            c = _componente(n, p.get("version"), "npm", ns, license_=p.get("license") if isinstance(p.get("license"), str)
                            else None, scope=scope, ref=ruta)
            componentes.append(c)
            por_nombre.setdefault(nombre, ruta)
            grafo[ruta] = list((p.get("dependencies") or {}).keys()) + list((p.get("optionalDependencies") or {}).keys())
        # Las dependencias se resuelven por nombre (anidada si existe, si no la de arriba).
        for ruta, deps in grafo.items():
            resueltas = []
            for d in deps:
                anidada = f"{ruta}/node_modules/{d}"
                resueltas.append(anidada if anidada in paquetes else por_nombre.get(d, f"node_modules/{d}"))
            grafo[ruta] = resueltas
        directos = {f"node_modules/{n}" for n in directos_n}
        _calcular_vias(componentes, directos, grafo)
    else:   # lockfileVersion 1
        def recorrer(deps: dict, ruta_padre: str, via: Optional[str]):
            for nombre, p in (deps or {}).items():
                ns, n = _npm_nombre(nombre)
                ref = f"{ruta_padre}/{nombre}".lstrip("/")
                c = _componente(n, p.get("version"), "npm", ns, scope="dev" if p.get("dev") else "required", ref=ref)
                c["direct"] = via is None and not ruta_padre
                c["via"] = via
                componentes.append(c)
                recorrer(p.get("dependencies"), ref, via or ref)
        recorrer(datos.get("dependencies"), "", None)
    return Resultado("package-lock.json", raiz, componentes)


def yarn_lock(texto: str) -> Resultado:
    componentes, grafo, por_espec = [], {}, {}
    bloque: Optional[dict] = None
    en_deps = False
    for linea in texto.splitlines():
        if not linea.strip() or linea.lstrip().startswith("#"):
            continue
        if not linea.startswith(" "):
            especs = [e.strip().strip('"') for e in linea.rstrip(":").split(",")]
            nombre = especs[0].rsplit("@", 1)[0] if especs[0].count("@") > (1 if especs[0].startswith("@") else 0) \
                else especs[0]
            bloque = {"name": nombre, "especs": especs, "deps": []}
            for e in especs:
                por_espec[e] = bloque
            componentes.append(bloque)
            en_deps = False
        elif bloque is not None:
            s = linea.strip()
            if s.startswith("version "):
                bloque["version"] = s.split(None, 1)[1].strip('"')
            elif s.startswith("dependencies:") or s.startswith("optionalDependencies:"):
                en_deps = True
            elif en_deps and linea.startswith("    "):
                n, _, rango = s.partition(" ")
                bloque["deps"].append(f'{n.strip(chr(34))}@{rango.strip(chr(34))}')
            else:
                en_deps = False
    salida = []
    for b in componentes:
        ns, n = _npm_nombre(b["name"])
        c = _componente(n, b.get("version"), "npm", ns, ref=b["especs"][0])
        salida.append(c)
        grafo[c["ref"]] = [por_espec[d]["especs"][0] for d in b["deps"] if d in por_espec]
    _calcular_vias(salida, None, grafo)
    return Resultado("yarn.lock", {}, salida)


# ── Python ───────────────────────────────────────────────────────────────────

def requirements_txt(texto: str) -> Resultado:
    componentes = []
    for linea in texto.splitlines():
        s = linea.split("#", 1)[0].strip()
        if not s or s.startswith(("-", "git+", "http:", "https:")):
            continue
        s = s.split(";", 1)[0].strip()
        m = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*(===|==|>=|<=|~=|!=|>|<)?\s*([^\s,]+)?", s)
        if not m:
            continue
        nombre, op, version = m.group(1), m.group(3), m.group(4)
        componentes.append(_componente(nombre, version if op in ("==", "===") else None, "pypi", ref=nombre.lower()))
    return Resultado("requirements.txt", {}, componentes)


def _toml(texto: str) -> dict:
    import tomllib
    return tomllib.loads(texto)


def poetry_lock(texto: str) -> Resultado:
    datos = _toml(texto)
    componentes, grafo = [], {}
    for p in datos.get("package") or []:
        nombre = p.get("name") or ""
        grupos = p.get("groups") or [p.get("category") or "main"]
        scope = "dev" if all(g in ("dev", "test", "docs") for g in grupos) else (
            "optional" if p.get("optional") else "required")
        c = _componente(nombre, p.get("version"), "pypi", scope=scope, ref=nombre.lower())
        componentes.append(c)
        grafo[c["ref"]] = [d.lower() for d in (p.get("dependencies") or {})]
    _calcular_vias(componentes, None, grafo)
    return Resultado("poetry.lock", {}, componentes)


def pipfile_lock(datos: dict) -> Resultado:
    componentes = []
    for seccion, scope in (("default", "required"), ("develop", "dev")):
        for nombre, p in (datos.get(seccion) or {}).items():
            version = str((p or {}).get("version") or "").lstrip("=") or None
            componentes.append(_componente(nombre, version, "pypi", scope=scope, ref=nombre.lower()))
    return Resultado("Pipfile.lock", {}, componentes)


# ── Java ─────────────────────────────────────────────────────────────────────

def _pom_info(texto: str) -> dict:
    """Coordenadas, padre, propiedades, dependencyManagement y dependencias de un POM."""
    from defusedxml import ElementTree as ET
    raiz_x = ET.fromstring(texto)

    def local(tag):
        return tag.rsplit("}", 1)[-1]

    def hijo(nodo, nombre):
        for h in list(nodo) if nodo is not None else []:
            if local(h.tag) == nombre:
                return h
        return None

    def txt(nodo, nombre):
        h = hijo(nodo, nombre)
        return h.text.strip() if h is not None and h.text else None

    padre = hijo(raiz_x, "parent")
    info = {"groupId": txt(raiz_x, "groupId") or txt(padre, "groupId"), "artifactId": txt(raiz_x, "artifactId"),
            "version": txt(raiz_x, "version") or txt(padre, "version"),
            "parent": (txt(padre, "groupId"), txt(padre, "artifactId"), txt(padre, "version")) if padre is not None
            else None, "props": {}, "managed": {}, "deps": []}
    pr = hijo(raiz_x, "properties")
    for p in list(pr) if pr is not None else []:
        info["props"][local(p.tag)] = (p.text or "").strip()

    def leer_deps(nodo):
        salida = []
        for d in list(nodo) if nodo is not None else []:
            if local(d.tag) == "dependency" and txt(d, "artifactId"):
                salida.append({"groupId": txt(d, "groupId"), "artifactId": txt(d, "artifactId"),
                               "version": txt(d, "version"), "scope": txt(d, "scope"), "type": txt(d, "type")})
        return salida
    dm = hijo(raiz_x, "dependencyManagement")
    for d in leer_deps(hijo(dm, "dependencies")):
        info["managed"][(d["groupId"], d["artifactId"])] = d
    info["deps"] = leer_deps(hijo(raiz_x, "dependencies"))
    return info


def pom_xml(texto: str, otros: Optional[dict] = None) -> Resultado:
    """`pom.xml` con propiedades (``${x}``, ``${project.version}``…) del propio POM y de sus padres
    si vienen en la misma importación (`otros`: ``"groupId:artifactId"`` → texto), y versiones de
    `dependencyManagement` (propias, de los padres y de BOMs importados en la misma importación)."""
    info = _pom_info(texto)
    poms = {}
    for t in (otros or {}).values():
        try:
            i = _pom_info(t)
            poms[f"{i['groupId']}:{i['artifactId']}"] = i
        except Exception:  # noqa: BLE001 - un POM roto no impide leer el resto
            continue
    cadena = [info]
    visto = set()
    while cadena[-1]["parent"] and len(cadena) < 10:
        g, a, _v = cadena[-1]["parent"]
        clave = f"{g}:{a}"
        if clave in visto or clave not in poms:
            break
        visto.add(clave)
        cadena.append(poms[clave])
    props: dict = {}
    for p in reversed(cadena):          # el hijo manda sobre el padre
        props.update(p["props"])
        props.update({"project.version": p["version"] or "", "project.groupId": p["groupId"] or "",
                      "project.artifactId": p["artifactId"] or "", "pom.version": p["version"] or ""})
    if info["parent"]:
        props.update({"project.parent.version": info["parent"][2] or "", "parent.version": info["parent"][2] or ""})

    def resolver(v):
        for _ in range(5):
            if not v or "${" not in v:
                break
            v = re.sub(r"\$\{([^}]+)\}", lambda m: props.get(m.group(1), m.group(0)), v)
        return v
    gestionadas: dict = {}
    for p in reversed(cadena):
        for clave, d in p["managed"].items():
            # BOM importado (scope import, type pom): sus versiones gestionadas, si viene en la importación.
            if d.get("scope") == "import" and f"{d['groupId']}:{d['artifactId']}" in poms:
                for c2, d2 in poms[f"{d['groupId']}:{d['artifactId']}"]["managed"].items():
                    gestionadas[c2] = d2.get("version")
                continue
            gestionadas[clave] = d.get("version")
    componentes = []
    for d in info["deps"]:
        g, a = resolver(d["groupId"]), resolver(d["artifactId"])
        version = resolver(d["version"]) or resolver(gestionadas.get((d["groupId"], d["artifactId"])))
        if version and "${" in version:
            version = None
        scope = {"test": "test", "provided": "optional", "system": "optional"}.get(d.get("scope") or "compile",
                                                                                 "required")
        componentes.append(_componente(a, version, "maven", g, scope=scope, ref=f"{g}:{a}"))
    raiz = {"name": info["artifactId"], "version": resolver(info["version"])}
    return Resultado("pom.xml", raiz, componentes)


# ── Go ───────────────────────────────────────────────────────────────────────

def _go_nombre(modulo: str) -> tuple[Optional[str], str]:
    ns, _, n = modulo.rpartition("/")
    return (ns or None), n


def go_mod(texto: str) -> Resultado:
    componentes = []
    raiz = {}
    en_require = False
    for linea in texto.splitlines():
        s = linea.strip()
        if s.startswith("module "):
            raiz = {"name": s.split(None, 1)[1]}
        if s.startswith("require ("):
            en_require = True
            continue
        if en_require and s == ")":
            en_require = False
            continue
        if s.startswith("require ") and "(" not in s:
            s = s[len("require "):]
        elif not en_require:
            continue
        partes = s.split("//", 1)
        trozos = partes[0].split()
        if len(trozos) >= 2:
            ns, n = _go_nombre(trozos[0])
            c = _componente(n, trozos[1], "golang", ns, ref=trozos[0])
            c["direct"] = not (len(partes) > 1 and "indirect" in partes[1])
            componentes.append(c)
    return Resultado("go.mod", raiz, componentes)


def go_sum(texto: str) -> Resultado:
    vistos, componentes = set(), []
    for linea in texto.splitlines():
        trozos = linea.split()
        if len(trozos) < 2:
            continue
        modulo, version = trozos[0], trozos[1].split("/go.mod")[0]
        if (modulo, version) in vistos:
            continue
        vistos.add((modulo, version))
        ns, n = _go_nombre(modulo)
        componentes.append(_componente(n, version, "golang", ns, ref=f"{modulo}@{version}"))
    return Resultado("go.sum", {}, componentes)


# ── Ruby, Rust, .NET ─────────────────────────────────────────────────────────

def gemfile_lock(texto: str) -> Resultado:
    componentes, grafo, directos = [], {}, set()
    seccion = None
    actual = None
    for linea in texto.splitlines():
        if linea and not linea.startswith(" "):
            seccion = linea.strip()
            continue
        if seccion == "GEM" or seccion == "GIT" or seccion == "PATH":
            m4 = re.match(r"^    ([^\s(]+) \(([^)]+)\)$", linea)
            m6 = re.match(r"^      ([^\s(]+)", linea)
            if m4:
                actual = m4.group(1)
                componentes.append(_componente(actual, m4.group(2).split("-")[0], "gem", ref=actual))
                grafo[actual] = []
            elif m6 and actual:
                grafo[actual].append(m6.group(1))
        elif seccion == "DEPENDENCIES":
            m = re.match(r"^  ([^\s(!]+)", linea)
            if m:
                directos.add(m.group(1))
    _calcular_vias(componentes, directos or None, grafo)
    return Resultado("Gemfile.lock", {}, componentes)


def cargo_lock(texto: str) -> Resultado:
    datos = _toml(texto)
    componentes, grafo = [], {}
    for p in datos.get("package") or []:
        nombre = p.get("name") or ""
        if not p.get("source"):
            continue   # el propio crate
        c = _componente(nombre, p.get("version"), "cargo", ref=nombre)
        componentes.append(c)
        grafo[nombre] = [d.split()[0] for d in p.get("dependencies") or []]
    _calcular_vias(componentes, None, grafo)
    return Resultado("Cargo.lock", {}, componentes)


def nuget_lock(datos: dict) -> Resultado:
    componentes, vistos, grafo, directos = [], set(), {}, set()
    for _marco, paquetes in (datos.get("dependencies") or {}).items():
        for nombre, p in (paquetes or {}).items():
            if (p or {}).get("type") == "Project":
                continue
            ref = nombre.lower()
            if ref in vistos:
                continue
            vistos.add(ref)
            componentes.append(_componente(nombre, (p or {}).get("resolved"), "nuget", ref=ref))
            grafo[ref] = [d.lower() for d in ((p or {}).get("dependencies") or {})]
            if (p or {}).get("type") == "Direct":
                directos.add(ref)
    _calcular_vias(componentes, directos or None, grafo)
    return Resultado("packages.lock.json", {}, componentes)


# ── Detección ────────────────────────────────────────────────────────────────

FORMATOS = ("cyclonedx", "spdx", "composer.lock", "package-lock.json", "yarn.lock", "requirements.txt",
            "poetry.lock", "Pipfile.lock", "pom.xml", "go.mod", "go.sum", "Gemfile.lock", "Cargo.lock",
            "packages.lock.json")


def leer(contenido: bytes | str, nombre: Optional[str] = None, formato: Optional[str] = None) -> Resultado:
    """Detecta el formato (por `formato`, por el nombre del fichero o por el contenido) y lo parsea."""
    texto = contenido.decode("utf-8-sig", errors="replace") if isinstance(contenido, bytes) else contenido
    base = (nombre or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    f = (formato or "").lower()
    datos = None
    if texto.lstrip().startswith(("{", "[")):
        try:
            datos = json.loads(texto)
        except json.JSONDecodeError:
            datos = None
    if isinstance(datos, dict):
        if f == "cyclonedx" or datos.get("bomFormat") == "CycloneDX":
            return cyclonedx_json(datos)
        if f == "spdx" or "spdxVersion" in datos:
            return spdx_json(datos)
        if f == "composer.lock" or base == "composer.lock" or ("packages" in datos and "content-hash" in datos):
            return composer_lock(datos)
        if f == "package-lock.json" or base in ("package-lock.json", "npm-shrinkwrap.json") or "lockfileVersion" in datos:
            return package_lock(datos)
        if f == "pipfile.lock" or base == "pipfile.lock" or ("_meta" in datos and "default" in datos):
            return pipfile_lock(datos)
        if f == "packages.lock.json" or base == "packages.lock.json":
            return nuget_lock(datos)
    if texto.lstrip().startswith("<"):
        if "<project" in texto[:2000] and ("maven" in texto[:2000] or base == "pom.xml" or f == "pom.xml"):
            return pom_xml(texto)
        if "cyclonedx" in texto[:2000].lower() or f == "cyclonedx":
            return cyclonedx_xml(texto)
    if f == "spdx" or texto.lstrip().startswith("SPDXVersion:"):
        return spdx_tag_value(texto)
    if f == "yarn.lock" or base == "yarn.lock" or "# yarn lockfile v1" in texto[:200]:
        return yarn_lock(texto)
    if f == "poetry.lock" or base == "poetry.lock":
        return poetry_lock(texto)
    if f == "cargo.lock" or base == "cargo.lock":
        return cargo_lock(texto)
    if f == "gemfile.lock" or base == "gemfile.lock" or texto.startswith("GEM\n"):
        return gemfile_lock(texto)
    if f == "go.mod" or base == "go.mod" or texto.lstrip().startswith("module "):
        return go_mod(texto)
    if f == "go.sum" or base == "go.sum" or re.search(r"^\S+ v[\d.]+\S*(/go\.mod)? h1:", texto, re.M):
        return go_sum(texto)
    if f == "requirements.txt" or base.endswith(".txt") or base.startswith("requirements"):
        return requirements_txt(texto)
    if "[[package]]" in texto:
        return poetry_lock(texto) if "python-versions" in texto or "[metadata]" in texto else cargo_lock(texto)
    raise FormatoNoReconocido(nombre or formato or "?")


# ── Importación de varios ficheros (o un zip) ────────────────────────────────

ZIP_MAX_FICHEROS = 300
ZIP_MAX_BYTES = 60 * 1024 * 1024


def expandir(ficheros: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """Abre los .zip (sin rutas absolutas ni ``..``, con límite de ficheros y de tamaño descomprimido)."""
    import io
    import zipfile
    salida: list[tuple[str, bytes]] = []
    for nombre, contenido in ficheros:
        if (nombre or "").lower().endswith(".zip") or contenido[:4] == b"PK\x03\x04":
            try:
                z = zipfile.ZipFile(io.BytesIO(contenido))
            except zipfile.BadZipFile:
                raise FormatoNoReconocido(nombre or "zip")
            total = 0
            for info in z.infolist()[:ZIP_MAX_FICHEROS]:
                ruta = info.filename.replace("\\", "/")
                if info.is_dir() or ruta.startswith("/") or ".." in ruta.split("/"):
                    continue
                total += info.file_size
                if total > ZIP_MAX_BYTES:
                    raise FormatoNoReconocido("zip demasiado grande")
                salida.append((ruta, z.read(info)))
        else:
            salida.append((nombre, contenido))
    return salida


def _clave_paquete(c: dict) -> str:
    from app.services.cmdb_software.identificadores import clave_de_paquete
    return clave_de_paquete(c.get("type"), c.get("namespace"), c.get("name"))


def leer_varios(ficheros: list[tuple[str, bytes]]) -> Resultado:
    """Varios ficheros de una misma versión de software (o un zip con ellos).

    - Los ``pom.xml`` se resuelven juntos: propiedades y `dependencyManagement`
      de sus padres y de los BOM importados que vengan en el mismo lote.
    - Un componente sin versión fija (``requirements.txt`` con ``>=``, un
      ``pom.xml`` sin versión…) toma la de otro fichero del lote para el mismo
      paquete (un lock, un ``pip freeze``). Si nadie la da, queda «versión
      desconocida» y la correlación lo avisa como posible afectado.
    - Lo que no se reconoce se devuelve en `ignorados`.
    """
    lote = expandir(ficheros)
    poms = {n: c.decode("utf-8-sig", errors="replace") for n, c in lote
            if n.replace("\\", "/").rsplit("/", 1)[-1].lower() == "pom.xml" or n.lower().endswith(".pom")}
    formatos_usados, componentes, ignorados, raiz = [], [], [], {}
    for nombre, texto in poms.items():
        r = pom_xml(texto, poms)
        formatos_usados.append(r.formato)
        componentes += r.componentes
        raiz = raiz or r.raiz
    for nombre, contenido in lote:
        if nombre in poms:
            continue
        try:
            r = leer(contenido, nombre)
        except Exception:  # noqa: BLE001 - lo que no se entiende se informa, no se inventa
            ignorados.append(nombre)
            continue
        formatos_usados.append(r.formato)
        componentes += r.componentes
        raiz = raiz or r.raiz
    con_version: dict[str, str] = {}
    for c in componentes:
        if c.get("version"):
            con_version.setdefault(_clave_paquete(c), c["version"])
    unicos: dict[tuple, dict] = {}
    for c in componentes:
        clave = _clave_paquete(c)
        if not c.get("version") and clave in con_version:
            c = {**c, "version": con_version[clave]}
            from app.services.cmdb_software.identificadores import construir_purl
            c["purl"] = construir_purl(c["type"], c.get("namespace"), c["name"], c["version"])
        k = (clave, c.get("version") or "")
        previo = unicos.get(k)
        if previo is None:
            unicos[k] = c
        else:
            # El directo gana al transitivo; se conserva la licencia que haya.
            previo["direct"] = previo.get("direct") or c.get("direct")
            previo["license"] = previo.get("license") or c.get("license")
    # Si un paquete aparece con versión, su entrada sin versión sobra.
    salida = [c for (clave, v), c in unicos.items() if v or clave not in con_version]
    return Resultado("+".join(sorted(set(formatos_usados))) or "multiple", raiz, salida, ignorados)