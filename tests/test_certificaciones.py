"""Certificaciones y cumplimiento continuo (migración 212, 24-11-2026, docs/CERTIFICACIONES.md).

Lo crítico:
- carga y validación del contenido (`app/data/certificaciones`) y siembra idempotente
  por empresa, puesta al día de lo no editado y migración del GRC (ISO 27001 y SOC 2);
- `aplica_si` y la regla de generación (las sucesoras heredan dependencias);
- generación desde plantilla: programa, proyecto con tareas, declaración, enlaces
  tarea↔control y documentos con aprobación;
- segregación de funciones (implanta/evalúa, implanta/prueba, corrige/cierra, hace/verifica);
- aislamiento por empresa;
- acceso temporal del auditor (token, caducidad, revocación, registro);
- relojes NIS2 (24 h, 72 h, 1 mes) y sus avisos;
- guardas de la API, migración y catálogo BPM.

Las pruebas usan un contenido mínimo propio (fixture `contenido`) para no depender del
tamaño del real, salvo las que validan precisamente el real.
"""
from __future__ import annotations

import importlib.util
import textwrap
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.conftest import auth

REPO = Path(__file__).resolve().parents[1]
BASE = "/api/v1/certificaciones"


# ── Contenido mínimo ─────────────────────────────────────────────────────────

MARCOS = """
- clave: iso27001
  nombre: ISO/IEC 27001:2022
  version: '2022'
  publico: false
  niveles: [clausulas, anexo_a]
- clave: tisax
  nombre: TISAX
  version: ISA 6
  publico: false
  niveles: [AL2, AL3, prototipos]
- clave: nis2
  nombre: NIS2
  version: 2022/2555
  publico: true
  niveles: [medidas, notificacion]
"""

CONTROLES = """
- clave_comun: politica-control-acceso
  titulo: Política de control de acceso
  descripcion: Redacción propia.
  dominio: accesos
  evidencia_sugerida: [Política aprobada]
  medible_por_plataforma: mfa_cobertura
  correspondencias:
  - {marco: iso27001, id_control: A.5.15, nivel: anexo_a}
  - {marco: tisax, id_control: 4.1.1, nivel: AL2}
- clave_comun: autenticacion-segura
  titulo: Autenticación segura
  descripcion: Redacción propia.
  dominio: accesos
  evidencia_sugerida: []
  medible_por_plataforma: null
  correspondencias:
  - {marco: iso27001, id_control: A.8.5, nivel: anexo_a}
  # Los demás ids del GRC (`marcos_de_cumplimiento`): así la migración no crea controles «grc-…».
  - {marco: iso27001, id_control: A.5.17, nivel: anexo_a}
  - {marco: iso27001, id_control: A.5.18, nivel: anexo_a}
  - {marco: iso27001, id_control: A.5.33, nivel: anexo_a}
  - {marco: iso27001, id_control: A.8.15, nivel: anexo_a}
- clave_comun: zona-prototipos
  titulo: Zona de prototipos
  descripcion: Redacción propia.
  dominio: prototipos
  evidencia_sugerida: []
  medible_por_plataforma: null
  correspondencias:
  - {marco: tisax, id_control: 8.1.1, nivel: prototipos}
- clave_comun: notificacion-24h
  titulo: Alerta temprana
  descripcion: Redacción propia.
  dominio: incidentes
  evidencia_sugerida: []
  medible_por_plataforma: null
  correspondencias:
  - {marco: nis2, id_control: 23.4.a, nivel: notificacion}
"""

PLANTILLA = """
clave: mini
nombre: Programa mínimo
marcos: [iso27001, tisax]
parametros:
- {clave: nivel_tisax, tipo: opcion, opciones: [ninguno, AL2, AL3], por_defecto: AL3}
- {clave: proteccion_prototipos, tipo: booleano, opciones: null, por_defecto: true}
- {clave: num_sedes, tipo: entero, opciones: null, por_defecto: 1}
fases:
- clave: arranque
  nombre: Arranque y alcance
  tareas:
  - clave: t1
    nombre: Constituir el comité
    raci: {R: responsable_cumplimiento, A: direccion, C: [ti], I: []}
    dias: 5
    depende_de: []
    controles: [politica-control-acceso]
    entregables: [Acta]
  - clave: t2
    nombre: Proteger prototipos
    raci: {R: ti, A: direccion, C: [], I: []}
    dias: 3
    depende_de: [t1]
    controles: [zona-prototipos]
    entregables: []
    aplica_si: "nivel_tisax == 'AL3' and proteccion_prototipos == true"
  - clave: t3
    nombre: Implantar autenticación
    raci: {R: ti, A: responsable_seguridad, C: [], I: [direccion]}
    dias: 4
    depende_de: [t2]
    controles: [autenticacion-segura, politica-control-acceso]
    entregables: []
riesgos:
- {clave: r1, titulo: Falta de patrocinio, probabilidad: media, impacto: alto, mitigacion: Comité mensual}
documentos:
- {clave: politica-control-acceso, nombre: Política de control de acceso, tipo: politica, controles: [politica-control-acceso]}
"""


@pytest.fixture()
def contenido(tmp_path, monkeypatch):
    raiz = tmp_path / "certificaciones"
    (raiz / "plantillas").mkdir(parents=True)
    (raiz / "documentos").mkdir()
    (raiz / "marcos.yaml").write_text(textwrap.dedent(MARCOS), encoding="utf8")
    (raiz / "controles.yaml").write_text(textwrap.dedent(CONTROLES), encoding="utf8")
    (raiz / "plantillas" / "mini.yaml").write_text(textwrap.dedent(PLANTILLA), encoding="utf8")
    (raiz / "documentos" / "politica-control-acceso.md").write_text("# Política de {{empresa}}\n", encoding="utf8")
    from app.services.certificaciones import catalogo
    monkeypatch.setattr(catalogo, "RAIZ", raiz)
    catalogo._CACHE.update(firma=None, datos=None)
    yield raiz
    catalogo._CACHE.update(firma=None, datos=None)


def _usuario(db, uid):
    from app.models.user import User
    u = db.get(User, uid)
    if not u.organization_id:
        u.organization_id = "1"
        db.commit()
    return u


def _otra_empresa(db):
    from app.models.mfa import Organization
    from app.models.user import User, UserRole, UserStatus
    from tests.conftest import HASH_DE_PRUEBA
    if db.get(Organization, "org-cert-b") is None:
        db.add(Organization(id="org-cert-b", name="Otra", slug="otra-cert", is_active=True))
        db.add(User(id="cert-b-admin", username="cert_b_admin", email="b@cert.test", full_name="B Admin",
                    role=UserRole.admin, status=UserStatus.active, is_active=True, organization_id="org-cert-b",
                    hashed_password=HASH_DE_PRUEBA, weekly_capacity_hours=40.0, currency="EUR"))
        db.commit()
    return db.get(User, "cert-b-admin")


def _programa(db, usuario, marcos=("iso27001",)):
    from app.services.certificaciones import programas
    return programas.crear(db, usuario, {"nombre": "Programa de prueba",
                                          "objetivos": [{"marco": m} for m in marcos]})


def _fila(db, programa, clave):
    from app.models.certificaciones import CertAplicabilidad, CertControl
    return (db.query(CertAplicabilidad).join(CertControl, CertControl.id == CertAplicabilidad.control_id)
            .filter(CertAplicabilidad.programa_id == programa.id, CertControl.clave_comun == clave,
                    CertAplicabilidad.sede == "").one())


# ── Carga y validación del contenido ─────────────────────────────────────────

def test_el_contenido_real_carga_sin_errores():
    from app.services.certificaciones import catalogo
    catalogo._CACHE.update(firma=None, datos=None)
    d = catalogo.cargar(forzar=True)
    assert d["errores"] == [], d["errores"][:10]
    assert {"iso27001", "tisax", "nis2", "sox", "jsox", "iec62443"} <= set(d["marcos"])
    assert len(d["controles"]) >= 200
    assert {"iso27001", "programa_integrado"} <= set(d["plantillas"])
    assert all(c["medible_por_plataforma"] in (None, *catalogo.MEDIDAS) for c in d["controles"].values())


def test_la_validacion_rechaza_lo_que_esta_mal(tmp_path):
    from app.services.certificaciones import catalogo
    (tmp_path / "plantillas").mkdir()
    (tmp_path / "marcos.yaml").write_text("- {clave: iso27001, nombre: ISO, niveles: [anexo_a]}\n", encoding="utf8")
    (tmp_path / "controles.yaml").write_text(textwrap.dedent("""
        - clave_comun: a
          titulo: A
          correspondencias: [{marco: desconocido, id_control: X}]
        - clave_comun: b
          titulo: B
          correspondencias: [{marco: iso27001, id_control: A.1, nivel: AL9}]
        - clave_comun: b
          titulo: B repetido
    """), encoding="utf8")
    (tmp_path / "plantillas" / "mal.yaml").write_text(textwrap.dedent("""
        clave: mal
        nombre: Mal
        marcos: [iso27001]
        parametros: [{clave: p, tipo: opcion, opciones: [x], por_defecto: y}]
        fases:
        - clave: f
          nombre: F
          tareas:
          - {clave: t, nombre: T, raci: {R: [a, b], A: x}, depende_de: [nada], controles: [zz], aplica_si: "p ~ 1"}
    """), encoding="utf8")
    d = catalogo.validar(tmp_path)
    texto = "\n".join(d["errores"])
    assert "marco desconocido" in texto
    assert "nivel AL9" in texto
    assert "clave repetida b" in texto
    assert "plantillas/mal.yaml" in texto
    assert "mal" not in d["plantillas"]


def test_aplica_si_gramatica_y_evaluacion():
    from app.services.certificaciones import expresiones as e
    p = {"num_sedes": 3, "tiene_ot": True, "cotiza_en": "japon", "sl_objetivo": "SL3"}
    assert e.evaluar("num_sedes > 1", p)
    assert e.evaluar("tiene_ot == true and sl_objetivo in ['SL3', 'SL4']", p)
    assert not e.evaluar("cotiza_en in ['eeuu', 'ambos']", p)
    assert e.evaluar("cotiza_en == 'eeuu' or num_sedes >= 3", p)
    assert e.evaluar(None, p)
    assert e.validar("tiene_ot == true", {"tiene_ot"}) is None
    assert e.validar("otro == true", {"tiene_ot"}) is not None
    assert e.validar("x in 3", None) is not None


# ── Siembra, sincronización y GRC ────────────────────────────────────────────

def test_siembra_idempotente_y_puesta_al_dia_sin_pisar_lo_editado(db, contenido):
    from app.models.certificaciones import CertControl, CertCorrespondencia, CertMarco
    from app.services.certificaciones import catalogo
    admin = _usuario(db, "admin-test-id")
    catalogo.sembrar(db, "1")
    db.commit()
    n_controles = db.query(CertControl).filter(CertControl.organization_id == "1").count()
    n_corr = db.query(CertCorrespondencia).filter(CertCorrespondencia.organization_id == "1").count()
    inf = catalogo.sembrar(db, "1")
    db.commit()
    assert inf["controles_creados"] == 0 and inf["correspondencias_creadas"] == 0
    assert db.query(CertControl).filter(CertControl.organization_id == "1").count() == n_controles
    assert db.query(CertCorrespondencia).filter(CertCorrespondencia.organization_id == "1").count() == n_corr

    # Un control editado por la empresa no se pisa; uno sin editar se pone al día.
    editado = db.query(CertControl).filter(CertControl.clave_comun == "autenticacion-segura").one()
    catalogo.editar_control(db, admin, editado.id, {"titulo": "Mi título"})
    (contenido / "controles.yaml").write_text(textwrap.dedent(CONTROLES).replace("Redacción propia.", "Nueva."),
                                              encoding="utf8")
    catalogo._CACHE.update(firma=None, datos=None)
    catalogo.sembrar(db, "1")
    db.commit()
    assert db.query(CertControl).filter(CertControl.clave_comun == "autenticacion-segura").one().titulo == "Mi título"
    assert db.query(CertControl).filter(CertControl.clave_comun == "zona-prototipos").one().descripcion == "Nueva."
    # La versión del marco se guarda al cambiar.
    (contenido / "marcos.yaml").write_text(textwrap.dedent(MARCOS).replace("version: '2022'", "version: '2027'"),
                                           encoding="utf8")
    catalogo._CACHE.update(firma=None, datos=None)
    catalogo.sembrar(db, "1")
    db.commit()
    iso = db.query(CertMarco).filter(CertMarco.organization_id == "1", CertMarco.clave == "iso27001").one()
    assert iso.version == "2027" and iso.version_anterior == "2022"


def test_marcos_del_grc_entran_en_la_biblioteca_y_sus_evidencias_se_enlazan(db, contenido):
    from app.models.certificaciones import CertCorrespondencia, CertEvidencia, CertMarco
    from app.models.governance import ComplianceEvidence
    from app.services.certificaciones import catalogo
    db.add(ComplianceEvidence(organization_id="1", framework="ISO27001", control_id="ISO27001-A.9.2",
                              evidence_type="policy", title="Política vieja", artifact_hash="a" * 64))
    db.add(ComplianceEvidence(organization_id="1", framework="SOC2", control_id="SOC2-CC6.1",
                              evidence_type="report", title="Informe SOC2"))
    db.commit()
    catalogo.sembrar(db, "1")
    db.commit()
    soc2 = db.query(CertMarco).filter(CertMarco.organization_id == "1", CertMarco.clave == "soc2").one()
    assert db.query(CertCorrespondencia).filter(CertCorrespondencia.marco_id == soc2.id).count() == 4
    enlazadas = db.query(CertEvidencia).filter(CertEvidencia.organization_id == "1",
                                               CertEvidencia.origen == "grc").all()
    assert len(enlazadas) == 2
    # SOC2 CC6.1 cuelga del control común de ISO A.8.5 (autenticación segura).
    from app.models.certificaciones import CertControl
    soc = next(e for e in enlazadas if e.titulo == "Informe SOC2")
    assert db.get(CertControl, soc.control_id).clave_comun == "autenticacion-segura"
    # Idempotente y sin tocar la tabla del GRC.
    catalogo.sembrar(db, "1")
    db.commit()
    assert db.query(CertEvidencia).filter(CertEvidencia.origen == "grc").count() == 2
    assert db.query(ComplianceEvidence).count() == 2


def test_importar_texto_oficial_corrige_ids_sin_perder_el_enlace(db, contenido):
    from app.models.certificaciones import CertCorrespondencia
    from app.services.certificaciones import catalogo
    admin = _usuario(db, "admin-test-id")
    catalogo.sembrar(db, "1")
    db.commit()
    r = catalogo.importar_texto_oficial(db, admin, [
        {"marco": "tisax", "id_control": "4.1.1", "texto_oficial": "Texto con licencia", "id_control_nuevo": "4.1.1a"},
        {"marco": "tisax", "id_control": "9.9.9", "texto_oficial": "no casa"}])
    assert r["actualizados"] == 1 and r["renombrados"] == 1 and len(r["sin_casar"]) == 1
    c = db.query(CertCorrespondencia).filter(CertCorrespondencia.id_control == "4.1.1a").one()
    assert c.id_semilla == "4.1.1" and c.texto_oficial == "Texto con licencia"
    catalogo.sembrar(db, "1")
    db.commit()
    assert db.query(CertCorrespondencia).filter(CertCorrespondencia.organization_id == "1",
                                                CertCorrespondencia.id_control.in_(("4.1.1", "4.1.1a"))).count() == 1


# ── Generación desde plantilla ───────────────────────────────────────────────

def test_las_sucesoras_heredan_las_dependencias_de_lo_que_no_aplica(contenido):
    from app.services.certificaciones import catalogo, generacion
    p = catalogo.plantilla("mini")
    fases, deps = generacion.tareas_que_aplican(p, {"nivel_tisax": "AL2", "proteccion_prototipos": False,
                                                    "num_sedes": 1})
    claves = [t["clave"] for f in fases for t in f["tareas"]]
    assert claves == ["t1", "t3"]
    assert deps["t3"] == ["t1"]
    _f, deps = generacion.tareas_que_aplican(p, {"nivel_tisax": "AL3", "proteccion_prototipos": True, "num_sedes": 1})
    assert deps["t3"] == ["t2"] and deps["t2"] == ["t1"]


def test_objetivos_y_parametros_segun_el_alcance(contenido):
    from app.core.errores import ErrorDeDominio
    from app.services.certificaciones import catalogo, generacion
    p = catalogo.plantilla("mini")
    params = generacion.parametros(p, {"nivel_tisax": "AL2"})
    assert params == {"nivel_tisax": "AL2", "proteccion_prototipos": True, "num_sedes": 1}
    tisax = next(o for o in generacion.objetivos(p, {**params, "proteccion_prototipos": False}) if o["marco"] == "tisax")
    assert tisax["niveles"] == ["AL2"]
    assert all(o["marco"] != "tisax" for o in generacion.objetivos(p, {"nivel_tisax": "ninguno"}))
    integ = {"marcos": ["sox", "jsox", "iec62443", "nis2"]}
    o = generacion.objetivos(integ, {"cotiza_en": "japon", "tiene_ot": False, "desarrolla_producto": True,
                                     "entidad_nis2": "no", "sl_objetivo": "SL2"})
    assert [x["marco"] for x in o] == ["jsox", "iec62443"]
    assert o[1]["niveles"] == ["2-1", "4-1", "4-2"] and o[1]["sl_objetivo"] == "SL2"
    with pytest.raises(ErrorDeDominio):
        generacion.parametros(p, {"nivel_tisax": "AL9"})
    with pytest.raises(ErrorDeDominio):
        generacion.parametros(p, {"desconocido": 1})


def test_generar_crea_programa_proyecto_declaracion_enlaces_y_documentos(db, contenido):
    from app.models.certificaciones import CertAplicabilidad, CertControlTarea, CertEvidencia
    from app.models.documents import Document
    from app.models.task import Task
    from app.services.certificaciones import generacion
    admin = _usuario(db, "admin-test-id")
    r = generacion.generar(db, admin, {"plantilla": "mini", "nombre": "TISAX planta", "empresa": "ACME",
                                       "parametros": {"nivel_tisax": "AL3", "num_sedes": 3}})
    pid = r["programa"]["id"]
    assert r["project_id"] and r["tareas"] == 3
    tareas = db.query(Task).filter(Task.project_id == r["project_id"]).all()
    assert {t.title for t in tareas} == {"Constituir el comité", "Proteger prototipos", "Implantar autenticación"}
    filas = db.query(CertAplicabilidad).filter(CertAplicabilidad.programa_id == pid).all()
    # iso (2 controles) + tisax AL2/AL3/prototipos (política y prototipos): 3 controles únicos.
    assert len(filas) == 3
    assert db.query(CertControlTarea).filter(CertControlTarea.aplicabilidad_id.in_([f.id for f in filas])).count() == 4
    docs = db.query(Document).filter(Document.project_id == r["project_id"]).all()
    assert len(docs) == 1 and docs[0].requires_approval and "ACME" in (docs[0].description or "")
    ev = db.query(CertEvidencia).filter(CertEvidencia.programa_id == pid, CertEvidencia.origen == "plantilla").one()
    assert ev.document_id == docs[0].id
    assert r["programa"]["alcance"]["sedes"] == ["Sede 1", "Sede 2", "Sede 3"]


def test_la_evidencia_documental_solo_cuenta_aprobada_y_caduca(db, contenido):
    from app.models.certificaciones import CertEvidencia
    from app.models.documents import ApprovalStatus, Document
    from app.services.certificaciones import comun, evidencias, generacion
    admin = _usuario(db, "admin-test-id")
    r = generacion.generar(db, admin, {"plantilla": "mini", "parametros": {}})
    ev = db.query(CertEvidencia).filter(CertEvidencia.programa_id == r["programa"]["id"]).first()
    cfg = comun.config(db, "1")
    assert evidencias.estado(db, ev, cfg) == "pendiente_aprobacion"
    doc = db.get(Document, ev.document_id)
    doc.approval_status = ApprovalStatus.approved
    db.commit()
    assert evidencias.estado(db, ev, cfg) == "valida"
    ev.caduca_el = date.today() - timedelta(days=1)
    db.commit()
    assert evidencias.estado(db, ev, cfg) == "caducada"


# ── Segregación de funciones ─────────────────────────────────────────────────

def test_quien_implanta_no_da_por_eficaz_ni_prueba(db, contenido):
    from app.core.errores import ErrorDeDominio
    from app.services.certificaciones import programas
    admin, pm = _usuario(db, "admin-test-id"), _usuario(db, "pm-test-id")
    p = _programa(db, admin)
    fila = _fila(db, p, "politica-control-acceso")
    programas.editar_fila(db, pm, fila.id, {"estado": "implantado"})
    with pytest.raises(ErrorDeDominio) as e:
        programas.evaluar_eficacia(db, pm, fila.id, "eficaz")
    assert e.value.status_code == 403
    with pytest.raises(ErrorDeDominio):
        programas.registrar_prueba(db, pm, fila.id, {"tipo": "eficacia_operativa", "resultado": "superada"})
    assert programas.registrar_prueba(db, admin, fila.id, {"tipo": "eficacia_operativa", "resultado": "superada",
                                                          "poblacion": 25, "muestra": 5})["probado_por"] == admin.id
    assert programas.evaluar_eficacia(db, admin, fila.id, "eficaz")["eficacia"] == "eficaz"


def test_quien_corrige_no_cierra_y_quien_hace_no_verifica(db, contenido):
    from app.core.errores import ErrorDeDominio
    from app.services.certificaciones import auditorias
    admin, pm = _usuario(db, "admin-test-id"), _usuario(db, "pm-test-id")
    p = _programa(db, admin)
    a = auditorias.crear(db, admin, {"programa_id": p.id, "tipo": "interna"})
    h = auditorias.crear_hallazgo(db, admin, a["id"], {"tipo": "nc_menor", "titulo": "Sin MFA"})
    x = auditorias.crear_accion(db, admin, h["id"], {"plan": "Exigir MFA", "responsable_id": "pm-test-id"})
    auditorias.marcar_hecha(db, pm, x["id"])
    with pytest.raises(ErrorDeDominio):
        auditorias.verificar(db, pm, x["id"], True, None)
    auditorias.verificar(db, admin, x["id"], True, "comprobado")
    auditorias.marcar_corregido(db, pm, h["id"])
    with pytest.raises(ErrorDeDominio):
        auditorias.cerrar_hallazgo(db, pm, h["id"])
    assert auditorias.cerrar_hallazgo(db, admin, h["id"])["estado"] == "cerrado"


def test_no_se_cierra_una_no_conformidad_con_acciones_sin_verificar(db, contenido):
    from app.core.errores import ErrorDeDominio
    from app.services.certificaciones import auditorias
    admin, pm = _usuario(db, "admin-test-id"), _usuario(db, "pm-test-id")
    p = _programa(db, admin)
    a = auditorias.crear(db, admin, {"programa_id": p.id, "tipo": "certificacion_f2"})
    h = auditorias.crear_hallazgo(db, admin, a["id"], {"tipo": "nc_mayor", "titulo": "Sin copias"})
    auditorias.crear_accion(db, admin, h["id"], {"plan": "Copias diarias"})
    auditorias.marcar_corregido(db, pm, h["id"])
    with pytest.raises(ErrorDeDominio) as e:
        auditorias.cerrar_hallazgo(db, admin, h["id"])
    assert e.value.status_code == 409


# ── Aislamiento por empresa ──────────────────────────────────────────────────

def test_otra_empresa_no_ve_ni_toca_el_programa(db, contenido):
    from app.core.errores import ErrorDeDominio
    from app.services.certificaciones import catalogo, programas
    admin = _usuario(db, "admin-test-id")
    ajeno = _otra_empresa(db)
    p = _programa(db, admin)
    catalogo.sembrar(db, "org-cert-b")
    db.commit()
    assert [x["id"] for x in programas.listar(db, ajeno)] == []
    with pytest.raises(ErrorDeDominio) as e:
        programas.aplicabilidad(db, ajeno, p.id)
    assert e.value.status_code == 404
    fila = _fila(db, p, "politica-control-acceso")
    with pytest.raises(ErrorDeDominio):
        programas.editar_fila(db, ajeno, fila.id, {"aplica": False, "justificacion": "x"})
    # Cada empresa tiene su biblioteca (únicos por empresa).
    from app.models.certificaciones import CertControl
    assert db.query(CertControl).filter(CertControl.clave_comun == "zona-prototipos").count() == 2


# ── Acceso temporal del auditor ──────────────────────────────────────────────

def _auditor(db, admin, **extra):
    from app.services.certificaciones import externos
    datos = {"nombre": "Ana Auditora", "email": "ana@cert.test", "independencia_declarada": True,
             "nda_firmado_el": date.today().isoformat(), **extra}
    return externos.guardar_auditor(db, admin, datos)


def test_acceso_del_auditor_exige_nda_e_independencia(db, contenido):
    from app.core.errores import ErrorDeDominio
    from app.services.certificaciones import externos
    admin = _usuario(db, "admin-test-id")
    p = _programa(db, admin)
    sin_nda = _auditor(db, admin, nda_firmado_el=None)
    with pytest.raises(ErrorDeDominio):
        externos.conceder(db, admin, {"auditor_id": sin_nda["id"], "programa_id": p.id})
    a = _auditor(db, admin, nombre="Otra")
    with pytest.raises(ErrorDeDominio):
        externos.conceder(db, admin, {"auditor_id": a["id"], "programa_id": p.id, "dias": 400})


def test_el_auditor_ve_solo_su_programa_y_queda_registrado(client, db, contenido):
    from app.models.enterprise import AuditLog
    from app.models.certificaciones import CertAccesoRegistro, CertPaquete
    from app.services.certificaciones import externos
    admin = _usuario(db, "admin-test-id")
    p = _programa(db, admin)
    a = _auditor(db, admin)
    x = externos.conceder(db, admin, {"auditor_id": a["id"], "programa_id": p.id, "dias": 3})
    assert x["token"] and x["url"].endswith(x["token"])
    r = client.get(f"{BASE}/auditor/{x['token']}")
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["programa"]["id"] == p.id and d["solo_lectura"] is True
    assert len(d["declaracion_de_aplicabilidad"]) >= 1
    r = client.get(f"{BASE}/auditor/{x['token']}/paquete")
    assert r.status_code == 200 and r.json()["data"]["signature"]
    assert db.query(CertAccesoRegistro).filter(CertAccesoRegistro.acceso_id == x["id"]).count() == 2
    assert db.query(CertPaquete).filter(CertPaquete.acceso_id == x["id"]).count() == 1
    assert db.query(AuditLog).filter(AuditLog.action == "AUDITOR_READ").count() >= 2
    # Revocado o con un token falso: 401.
    externos.revocar(db, admin, x["id"])
    assert client.get(f"{BASE}/auditor/{x['token']}").status_code == 401
    assert client.get(f"{BASE}/auditor/{'x' * 43}").status_code == 401


def test_el_acceso_caduca(client, db, contenido):
    from app.models.certificaciones import CertAcceso
    from app.services.certificaciones import externos
    admin = _usuario(db, "admin-test-id")
    p = _programa(db, admin)
    x = externos.conceder(db, admin, {"auditor_id": _auditor(db, admin)["id"], "programa_id": p.id, "dias": 1})
    fila = db.get(CertAcceso, x["id"])
    fila.hasta = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert client.get(f"{BASE}/auditor/{x['token']}").status_code == 401


def test_rgpd_suprimir_auditor_revoca_y_seudonimiza(db, contenido):
    from app.models.certificaciones import CertAcceso, CertAuditor
    from app.services.certificaciones import externos, rgpd
    admin = _usuario(db, "admin-test-id")
    p = _programa(db, admin)
    a = _auditor(db, admin)
    x = externos.conceder(db, admin, {"auditor_id": a["id"], "programa_id": p.id})
    assert rgpd.copia_auditor(db, admin, a["id"])["certification_auditor"]["email"] == "ana@cert.test"
    rgpd.suprimir_auditor(db, admin, a["id"])
    fila = db.get(CertAuditor, a["id"])
    assert fila.nombre == rgpd.BORRADO and fila.email is None and fila.suprimido_en is not None
    assert db.get(CertAcceso, x["id"]).revocado_en is not None


# ── NIS2 ─────────────────────────────────────────────────────────────────────

def test_relojes_nis2_24h_72h_y_un_mes(db, contenido):
    from app.services.certificaciones import comun, nis2
    from app.models.certificaciones import CertIncidente
    admin = _usuario(db, "admin-test-id")
    detectado = datetime.now(timezone.utc) - timedelta(hours=30)
    inc = nis2.crear(db, admin, {"titulo": "Ransomware", "detectado_en": detectado.isoformat()})
    rel = inc["relojes"]
    assert rel["alerta"]["estado"] == "vencido"
    assert rel["notificacion"]["estado"] == "pendiente"
    assert 0 < rel["notificacion"]["segundos_restantes"] <= 42 * 3600
    inc = nis2.comunicar(db, admin, inc["id"], {"tipo": "alerta_temprana", "destinatario": "CSIRT"})
    assert inc["relojes"]["alerta"]["estado"] == "tarde" and inc["estado"] == "alerta_enviada"
    inc = nis2.comunicar(db, admin, inc["id"], {"tipo": "notificacion"})
    assert inc["relojes"]["notificacion"]["estado"] == "cumplido" and inc["estado"] == "notificado"
    fila = db.get(CertIncidente, inc["id"])
    plazos = nis2.plazos(fila, comun.config(db, "1"))
    assert plazos["informe_final"] - comun.aware(fila.notificacion_enviada_en) == timedelta(days=30)
    assert len(nis2.serializar(db, fila, True)["comunicaciones"]) == 2


def test_informe_final_exige_notificacion_y_plantilla_traducida(db, contenido):
    from app.core.errores import ErrorDeDominio
    from app.services.certificaciones import nis2
    admin = _usuario(db, "admin-test-id")
    inc = nis2.crear(db, admin, {"titulo": "Caída", "autoridad": "INCIBE-CERT"})
    with pytest.raises(ErrorDeDominio):
        nis2.comunicar(db, admin, inc["id"], {"tipo": "informe_final"})
    es = nis2.plantilla(db, admin, inc["id"], "alerta_temprana", "es")
    en = nis2.plantilla(db, admin, inc["id"], "alerta_temprana", "en")
    assert inc["codigo"] in es["asunto"] and "INCIBE-CERT" in es["contenido"]
    assert es["contenido"] != en["contenido"]


def test_avisos_del_reloj_una_vez_cada_uno(db, contenido):
    from app.services.certificaciones import nis2, trabajos
    admin = _usuario(db, "admin-test-id")
    nis2.crear(db, admin, {"titulo": "Fuga", "detectado_en": (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()})
    primero = trabajos.relojes_nis2(db, "1")["cert_nis2_avisos"]
    assert primero == 1  # solo «alerta, faltan menos de 6 h»
    assert trabajos.relojes_nis2(db, "1")["cert_nis2_avisos"] == 0


# ── Certificados, matriz y panel ─────────────────────────────────────────────

def test_certificado_calcula_el_ciclo_y_tisax_no_pasa_de_tres_anios(db, contenido):
    from app.core.errores import ErrorDeDominio
    from app.services.certificaciones import catalogo, certificados
    admin = _usuario(db, "admin-test-id")
    catalogo.sembrar(db, "1")
    db.commit()
    hoy = date.today()
    c = certificados.guardar(db, admin, {"numero": "ISO-1", "marco": "iso27001", "emitido_el": hoy.isoformat()})
    assert c["valido_hasta"] == hoy.replace(year=hoy.year + 3).isoformat()
    assert c["tipo_proxima"] == "seguimiento_1"
    with pytest.raises(ErrorDeDominio):
        certificados.guardar(db, admin, {"numero": "TX-1", "marco": "tisax", "emitido_el": hoy.isoformat(),
                                         "valido_hasta": hoy.replace(year=hoy.year + 4).isoformat()})


def test_matriz_por_sede_y_estado(db, contenido):
    from app.services.certificaciones import programas
    admin = _usuario(db, "admin-test-id")
    p = _programa(db, admin, ("iso27001",))
    programas.editar(db, admin, p.id, {"alcance": {"sedes": ["Madrid", "Valencia"]}})
    fila = _fila(db, p, "autenticacion-segura")
    programas.dividir_por_sede(db, admin, fila.id, "Valencia")
    m = programas.matriz(db, admin, p.id)
    assert m["sedes"] == ["", "Madrid", "Valencia"] and m["marcos"] == ["iso27001"]
    assert {c["control"] for c in m["controles"]} == {"politica-control-acceso", "autenticacion-segura"}
    assert sum(m["totales_por_marco"]["iso27001"].values()) == 2


# ── API, guardas, migración y BPM ────────────────────────────────────────────

def test_guardas_de_la_api(client, db, contenido, admin_token, dev_token, pm_token):
    assert client.get(f"{BASE}/panel", headers=auth(dev_token)).status_code == 403
    assert client.get(f"{BASE}/panel", headers=auth(pm_token)).status_code == 200
    assert client.get(f"{BASE}/config", headers=auth(pm_token)).status_code == 403
    assert client.get(f"{BASE}/config", headers=auth(admin_token)).status_code == 200
    r = client.post(f"{BASE}/programas/desde-plantilla", headers=auth(pm_token), json={"plantilla": "mini"})
    assert r.status_code == 201, r.text
    assert client.get(f"{BASE}/plantillas", headers=auth(pm_token)).json()["data"][0]["clave"] == "mini"


def test_capacidades_en_backend_y_frontend():
    from app.core.capacidades import CAPACIDADES
    ts = (REPO / "frontend" / "src" / "permisos" / "capacidades.ts").read_text(encoding="utf8")
    for c in ("certificaciones.ver", "certificaciones.gestionar", "certificaciones.auditar",
              "certificaciones.administrar"):
        assert c in CAPACIDADES and f"'{c}'" in ts
    assert "employee" not in CAPACIDADES["certificaciones.ver"].roles


def test_migracion_212_y_213_encadenadas_con_empresa_obligatoria():
    def cargar(nombre):
        spec = importlib.util.spec_from_file_location(nombre, REPO / "alembic" / "versions" / f"{nombre}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    m212 = cargar("212_certificaciones")
    m213 = cargar("213_certificaciones_id_semilla")
    assert m212.down_revision == "211_chat_en_vivo_completo" and m213.down_revision == m212.revision
    from app.models import certificaciones as modelos
    assert m212.TABLAS == modelos.TABLAS
    definicion = m212._definicion()
    from app.db.base import Base
    for tabla in m212.TABLAS:
        cols = {c.name: c for c in definicion[tabla]}
        assert cols["organization_id"].nullable is False, tabla
        assert set(cols) == set(Base.metadata.tables[tabla].c.keys()), tabla


def test_procesos_bpm_de_certificacion_en_el_catalogo():
    from app.services.bpmn_process_service import PROCESS_CATALOGUE
    claves = {e["key"] for e in PROCESS_CATALOGUE}
    assert {"cert_program", "cert_audit_capa", "nis2_incident"} <= claves
    for idioma in ("es", "en", "zh"):
        texto = (REPO / "frontend" / "src" / "pages" / "bpm" / "catalogo" / "textosLineales" / f"{idioma}.ts").read_text(
            encoding="utf8")
        assert '"nis2_incident"' in texto and '"cert_program"' in texto


def test_bloqueo_legal_y_retencion_conocen_las_tablas_del_modulo():
    from app.db.bloqueo_legal import TIPOS
    for clave in ("cert_evidencias", "cert_auditorias", "cert_programas", "cert_incidentes", "cert_auditores",
                  "cert_accesos_registro"):
        assert clave in TIPOS
        tipo = TIPOS[clave]
        modelo = tipo.modelo()
        for campo in tipo.campos:
            assert hasattr(modelo, campo), (clave, campo)


def test_asegurar_sembrado_aguanta_dos_peticiones_a_la_vez(monkeypatch):
    """24-11-2026: la segunda petición que sembraba a la vez daba 500 (único organización+clave)."""
    from sqlalchemy.exc import IntegrityError
    from app.services.certificaciones import catalogo

    estado = {"sembrado": False, "rollback": 0}
    monkeypatch.setattr(catalogo, "sembrado", lambda db, org: estado["sembrado"])

    def sembrar_que_choca(db, org):
        estado["sembrado"] = True          # otra petición ya lo sembró
        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: cert_marcos"))

    monkeypatch.setattr(catalogo, "sembrar", sembrar_que_choca)

    class _Db:
        def commit(self): pass
        def rollback(self): estado["rollback"] += 1

    catalogo.asegurar_sembrado(_Db(), "org-1")
    assert estado["rollback"] == 1
