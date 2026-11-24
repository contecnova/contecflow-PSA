"""Comprueba la forma y la coherencia del contenido de Certificaciones (app/data/certificaciones).

Solo lee ficheros YAML y Markdown: no necesita base de datos ni la aplicación.
Ver docs/CERTIFICACIONES_CONTENIDO.md.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

BASE = Path(__file__).resolve().parent.parent / "app" / "data" / "certificaciones"

MARCOS_ESPERADOS = {"iso27001", "tisax", "nis2", "sox", "jsox", "iec62443"}
MEDIBLES = {
    "mfa_cobertura", "recertificacion_accesos", "registro_auditoria_inmutable", "gestion_cambios_cab",
    "copias_seguridad", "politica_contrasenas", "sod_conflictos", "retencion_datos",
    "inventario_activos_cmdb", "gestion_vulnerabilidades", "gestion_incidentes", "revision_proveedores",
}
ROLES = {
    "direccion", "responsable_seguridad", "responsable_cumplimiento", "ti", "ot", "rrhh", "finanzas",
    "auditoria_interna", "propietario_proceso", "proveedor",
}
TIPOS_DOC = {"politica", "procedimiento", "registro"}
TIPOS_PARAM = {"entero", "booleano", "opcion"}
NIVELES_RIESGO_P = {"baja", "media", "alta"}
NIVELES_RIESGO_I = {"bajo", "medio", "alto", "critico"}
KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# <param> <op> <literal>; varias unidas con and/or, sin paréntesis
COND = re.compile(
    r"^(?P<p>[a-z_][a-z0-9_]*)\s*(?P<op>==|!=|>=|<=|>|<|in)\s*"
    r"(?P<v>true|false|-?\d+|'[^']*'|\[\s*'[^']*'(?:\s*,\s*'[^']*')*\s*\])$"
)


def _carga(nombre: str):
    with open(BASE / nombre, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def marcos():
    return _carga("marcos.yaml")


@pytest.fixture(scope="module")
def controles():
    return _carga("controles.yaml")


@pytest.fixture(scope="module")
def plantillas():
    return {p.stem: _carga(f"plantillas/{p.name}") for p in sorted((BASE / "plantillas").glob("*.yaml"))}


def test_marcos(marcos):
    claves = {m["clave"] for m in marcos}
    assert claves == MARCOS_ESPERADOS
    for m in marcos:
        assert m["nombre"] and m["version"]
        assert isinstance(m["publico"], bool)
        assert m["niveles"] and all(isinstance(n, str) for n in m["niveles"])
    publicos = {m["clave"] for m in marcos if m["publico"]}
    assert publicos == {"nis2", "sox", "jsox"}


def test_controles_forma(controles, marcos):
    niveles = {m["clave"]: set(m["niveles"]) for m in marcos}
    vistas = set()
    for c in controles:
        k = c["clave_comun"]
        assert KEBAB.match(k), k
        assert k not in vistas, f"clave duplicada {k}"
        vistas.add(k)
        assert c["titulo"] and c["descripcion"] and c["dominio"]
        assert isinstance(c["evidencia_sugerida"], list) and c["evidencia_sugerida"]
        assert c["medible_por_plataforma"] is None or c["medible_por_plataforma"] in MEDIBLES, k
        assert c["correspondencias"], k
        for x in c["correspondencias"]:
            assert x["marco"] in MARCOS_ESPERADOS, (k, x)
            assert isinstance(x["id_control"], str) and x["id_control"], (k, x)
            if x.get("nivel") is not None:
                assert x["nivel"] in niveles[x["marco"]], (k, x)


def _ids(controles, marco):
    return {x["id_control"] for c in controles for x in c["correspondencias"] if x["marco"] == marco}


def test_cobertura_anexo_a(controles):
    esperado = ({f"A.5.{i}" for i in range(1, 38)} | {f"A.6.{i}" for i in range(1, 9)}
                | {f"A.7.{i}" for i in range(1, 15)} | {f"A.8.{i}" for i in range(1, 35)})
    assert len(esperado) == 93
    assert esperado <= _ids(controles, "iso27001")


def test_cobertura_nis2(controles):
    esperado = {"art.20.1", "art.20.2", "art.21.1", "art.21.3", "art.21.4", "art.23.1", "art.23.2", "art.23.3"}
    esperado |= {f"art.21.2.{x}" for x in "abcdefghij"} | {f"art.23.4.{x}" for x in "abcde"}
    assert esperado <= _ids(controles, "nis2")


def test_cobertura_iec62443(controles):
    ids = _ids(controles, "iec62443")
    sr = ([f"SR 1.{i}" for i in range(1, 14)] + [f"SR 2.{i}" for i in range(1, 13)] + [f"SR 3.{i}" for i in range(1, 10)]
          + [f"SR 4.{i}" for i in range(1, 4)] + [f"SR 5.{i}" for i in range(1, 5)] + ["SR 6.1", "SR 6.2"]
          + [f"SR 7.{i}" for i in range(1, 9)])
    practicas = ([f"SM-{i}" for i in range(1, 14)] + [f"SR-{i}" for i in range(1, 6)] + [f"SD-{i}" for i in range(1, 5)]
                 + ["SI-1", "SI-2"] + [f"SVV-{i}" for i in range(1, 6)] + [f"DM-{i}" for i in range(1, 7)]
                 + [f"SUM-{i}" for i in range(1, 6)] + [f"SG-{i}" for i in range(1, 8)])
    zcr = [f"ZCR {i}" for i in range(1, 8)]
    spe = [f"SPE {i}" for i in range(1, 9)]
    assert set(sr + practicas + zcr + spe) <= ids


def test_cobertura_tisax_prototipos(controles):
    ids = _ids(controles, "tisax")
    assert {"1.1.1", "1.4.1", "1.6.3", "4.2.1", "5.2.9", "5.3.4", "7.1.2"} <= ids
    assert {i for i in ids if i.startswith("8.")}, "faltan los requisitos de protección de prototipos"


def test_cobertura_sox_jsox(controles):
    assert {"Sec.302", "Sec.404(a)", "Sec.404(b)", "Sec.802"} <= _ids(controles, "sox")
    assert {"FIEA-24-4-4", "FIEA-193-2-2"} <= _ids(controles, "jsox")
    for marco in ("sox", "jsox"):
        ids = _ids(controles, marco)
        assert any(i.startswith(("FC-", "FCRP-")) for i in ids), "faltan controles de cierre de periodo"


def _documentos_md():
    return {p.stem for p in (BASE / "documentos").glob("*.md")}


def test_hay_plantilla_por_marco_y_programa_integrado(plantillas):
    assert set(plantillas) == MARCOS_ESPERADOS | {"programa_integrado"}
    assert set(plantillas["programa_integrado"]["marcos"]) == MARCOS_ESPERADOS


@pytest.mark.parametrize("nombre", sorted(MARCOS_ESPERADOS | {"programa_integrado"}))
def test_plantilla_coherente(nombre, plantillas, controles):
    p = plantillas[nombre]
    claves_ctrl = {c["clave_comun"] for c in controles}
    docs_md = _documentos_md()
    assert p["clave"] == nombre and p["nombre"]
    assert set(p["marcos"]) <= MARCOS_ESPERADOS

    params = {}
    for prm in p["parametros"]:
        assert prm["tipo"] in TIPOS_PARAM, prm
        if prm["tipo"] == "opcion":
            assert prm["opciones"], prm
        params[prm["clave"]] = prm

    tareas = {}
    for fase in p["fases"]:
        assert fase["clave"] and fase["nombre"] and fase["tareas"], fase.get("clave")
        for t in fase["tareas"]:
            assert t["clave"] not in tareas, f"tarea duplicada {t['clave']}"
            tareas[t["clave"]] = t
    assert len(p["fases"]) >= 11

    for k, t in tareas.items():
        raci = t["raci"]
        assert raci["R"] in ROLES and raci["A"] in ROLES, k
        assert all(r in ROLES for r in raci.get("C", []) + raci.get("I", [])), k
        assert isinstance(t["dias"], int) and t["dias"] > 0, k
        for d in t["depende_de"]:
            assert d in tareas, f"{k} depende de {d}, que no existe"
        for c in t["controles"]:
            assert c in claves_ctrl, f"{k} usa el control inexistente {c}"
        assert t["entregables"], k
        if t.get("aplica_si"):
            for parte in re.split(r"\s+(?:and|or)\s+", t["aplica_si"]):
                m = COND.match(parte.strip())
                assert m, f"{k}: condición no válida «{parte}»"
                prm = params.get(m["p"])
                assert prm, f"{k}: parámetro {m['p']} no declarado"
                if prm["tipo"] == "opcion":
                    for v in re.findall(r"'([^']*)'", m["v"]):
                        assert v in prm["opciones"], f"{k}: valor {v} no está en {prm['opciones']}"

    # sin ciclos (DFS con colores)
    color: dict[str, int] = {}

    def visita(n: str, camino: list[str]) -> None:
        if color.get(n) == 1:
            raise AssertionError("ciclo: " + " -> ".join(camino + [n]))
        if color.get(n) == 2:
            return
        color[n] = 1
        for d in tareas[n]["depende_de"]:
            visita(d, camino + [n])
        color[n] = 2

    for n in tareas:
        visita(n, [])

    # todo control de los marcos de la plantilla está enlazado a alguna tarea
    usados = {c for t in tareas.values() for c in t["controles"]}
    del_marco = {c["clave_comun"] for c in controles if any(x["marco"] in p["marcos"] for x in c["correspondencias"])}
    assert not (del_marco - usados), f"controles sin tarea: {sorted(del_marco - usados)}"

    for r in p["riesgos"]:
        assert r["clave"] and r["titulo"] and r["mitigacion"]
        assert r["probabilidad"] in NIVELES_RIESGO_P and r["impacto"] in NIVELES_RIESGO_I, r

    for d in p["documentos"]:
        assert d["tipo"] in TIPOS_DOC, d
        assert d["clave"] in docs_md, f"falta documentos/{d['clave']}.md"
        for c in d["controles"]:
            assert c in claves_ctrl, (d["clave"], c)


def test_documentos_markdown():
    docs = sorted((BASE / "documentos").glob("*.md"))
    assert docs
    for p in docs:
        texto = p.read_text(encoding="utf-8")
        assert texto.startswith("# "), p.name
        assert "{{empresa}}" in texto, p.name
        assert "Control de cambios" in texto, p.name
