"""Certificaciones traducidas (24-11-2026, barrido de traducciones; docs/CERTIFICACIONES_CONTENIDO.md §9).

Vigilante: el contenido de `app/data/certificaciones/` no puede volver a quedar solo en
castellano.

- Cada texto visible de marcos, controles y plantillas tiene traducción en
  `i18n/en.yaml` y `i18n/zh.yaml`, no vacía y distinta del castellano (salvo
  nombres propios y códigos de la lista blanca).
- Cada esqueleto `documentos/<clave>.md` tiene `documentos/en/` y `documentos/zh/`
  con los mismos marcadores `{{...}}`.
- Los roles RACI de las plantillas tienen nombre en `textos_de_salida` (no se
  escriben crudos en la descripción de las tareas).
- `traducir` no toca identificadores (`clave`, `marco`, `nivel`...).
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from app.services.certificaciones import traduccion

RAIZ = Path(__file__).resolve().parents[1] / "app" / "data" / "certificaciones"
CAMPOS_DE_TEXTO = {"nombre", "version", "descripcion", "titulo", "evidencia_sugerida", "entregables", "mitigacion"}
# Iguales en todos los idiomas: nombres de normas, versiones y siglas.
IGUALES_PERMITIDOS = re.compile(r"^[A-Z0-9/:.,\-\s()、]+$|^ISA/IEC 62443$|^ISO/IEC 27001:2022$")


def _textos() -> set[str]:
    salida: set[str] = set()

    def recorrer(obj, campo=None):
        if isinstance(obj, dict):
            for k, v in obj.items():
                recorrer(v, k)
        elif isinstance(obj, list):
            for v in obj:
                recorrer(v, campo)
        elif isinstance(obj, str) and campo in CAMPOS_DE_TEXTO:
            salida.add(obj)

    for ruta in [RAIZ / "marcos.yaml", RAIZ / "controles.yaml", *sorted((RAIZ / "plantillas").glob("*.yaml"))]:
        recorrer(yaml.safe_load(ruta.read_text(encoding="utf8")))
    return salida


def test_cada_texto_tiene_traduccion_en_y_zh():
    textos = _textos()
    assert len(textos) > 1000
    for idioma in traduccion.IDIOMAS:
        cat = traduccion.catalogo_de(idioma)
        faltan = sorted(t for t in textos if not (cat.get(t) or "").strip())
        assert not faltan, f"{idioma}: {len(faltan)} textos sin traducir, p. ej. {faltan[:5]}"
        iguales = sorted(t for t in textos if cat[t] == t and not IGUALES_PERMITIDOS.match(t))
        assert not iguales, f"{idioma}: {len(iguales)} textos copiados sin traducir, p. ej. {iguales[:5]}"
        sobran = sorted(set(cat) - textos)
        assert not sobran, f"{idioma}: {len(sobran)} entradas que ya no existen en el castellano: {sobran[:5]}"


def test_en_no_lleva_castellano_y_zh_lleva_chino():
    textos = _textos()
    en, zh = traduccion.catalogo_de("en"), traduccion.catalogo_de("zh")
    con_acentos = [t for t in textos if re.search(r"[áéíóúñ¿¡]", en[t])]
    assert not con_acentos, con_acentos[:5]
    sin_chino = [t for t in textos if not re.search(r"[一-鿿]", zh[t]) and not IGUALES_PERMITIDOS.match(t)
                 and t not in {"RCM"}]
    assert not sin_chino, sin_chino[:5]


def test_documentos_traducidos_con_los_mismos_marcadores():
    marcador = re.compile(r"\{\{[^}]+\}\}")
    for ruta in sorted((RAIZ / "documentos").glob("*.md")):
        original = ruta.read_text(encoding="utf8")
        for idioma in traduccion.IDIOMAS:
            traducido = RAIZ / "documentos" / idioma / ruta.name
            assert traducido.is_file(), f"falta documentos/{idioma}/{ruta.name}"
            texto = traducido.read_text(encoding="utf8")
            assert set(marcador.findall(texto)) == set(marcador.findall(original)), f"{idioma}/{ruta.name}"
            assert traduccion.documento(ruta.stem, idioma, original) == texto
        assert traduccion.documento(ruta.stem, "es", original) == original


def test_roles_raci_con_nombre_en_cada_idioma():
    from app.services.textos_de_salida import TEXTOS
    roles: set[str] = set()
    for ruta in (RAIZ / "plantillas").glob("*.yaml"):
        for fase in yaml.safe_load(ruta.read_text(encoding="utf8")).get("fases") or []:
            for tarea in fase.get("tareas") or []:
                raci = tarea.get("raci") or {}
                roles.update(r for r in [raci.get("R"), raci.get("A"), *(raci.get("C") or []), *(raci.get("I") or [])] if r)
    for rol in roles:
        variantes = TEXTOS.get(f"cert.generacion.rol.{rol}")
        assert variantes and all(variantes.get(i) for i in ("es", "en", "zh")), rol


def test_traducir_respeta_identificadores_y_respaldo():
    marco = yaml.safe_load((RAIZ / "marcos.yaml").read_text(encoding="utf8"))[0]
    fuera = traduccion.traducir({"clave": marco["clave"], "nombre": marco["nombre"], "version": marco["version"],
                                 "marco": marco["nombre"], "niveles": marco["niveles"]}, "en")
    assert fuera["clave"] == marco["clave"] and fuera["niveles"] == marco["niveles"]
    assert fuera["marco"] == marco["nombre"]  # campo identificador: no se traduce
    assert fuera["version"] == traduccion.catalogo_de("en")[marco["version"]]
    assert traduccion.traducir({"nombre": marco["version"]}, "es") == {"nombre": marco["version"]}
    assert traduccion.traducir({"nombre": "Texto propio de la empresa"}, "zh") == {"nombre": "Texto propio de la empresa"}


def test_la_api_devuelve_la_biblioteca_en_el_idioma_de_la_cabecera(client, admin_token):
    from tests.conftest import auth
    cab = {**auth(admin_token), "X-Idioma": "en"}
    r = client.get("/api/v1/certificaciones/catalogo/marcos", headers=cab)
    assert r.status_code == 200, r.text
    nombres = {m["clave"]: m["nombre"] for m in r.json()["data"]}
    if "sox" in nombres:
        assert nombres["sox"] == "Sarbanes-Oxley Act (SOX)"
    r_es = client.get("/api/v1/certificaciones/catalogo/marcos", headers={**auth(admin_token), "X-Idioma": "es"})
    nombres_es = {m["clave"]: m["nombre"] for m in r_es.json()["data"]}
    if "sox" in nombres_es:
        assert nombres_es["sox"] == "Ley Sarbanes-Oxley (SOX)"
