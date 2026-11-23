"""Flujo de demanda configurable (migración 195, docs/FLUJO_DE_DEMANDA.md).

Cubre la definición (validación, simulador, diagrama, plantillas), el recorrido
completo de la plantilla piloto con segregación, pausas, paralelo, quórum y
bypass justificado, el log inmutable y el versionado de campos.
"""
from __future__ import annotations

import json

import pytest

from app.models.user import User
from app.services.demanda import biblioteca, definicion as D, plantillas
from app.services.demanda.acceso import de_usuario
from app.core.errores import ErrorDeDominio

ORG = "1"


def _ids_de_grupo():
    return {k: f"g-{k}" for k in plantillas.GRUPOS}


# ── Definición (puro) ────────────────────────────────────────────────────────

def test_las_plantillas_de_la_biblioteca_son_validas():
    assert D.validar(plantillas.definicion_piloto(_ids_de_grupo())) == []
    for clave, (_n, _d, constructor) in biblioteca.PLANTILLAS.items():
        if constructor:
            assert D.validar(constructor()[0]) == [], clave


def test_validar_detecta_claves_destinos_y_asignados():
    defn = {"fields": [{"key": "Mal", "label": "x"}],
            "phases": [{"key": "a", "name": "A", "steps": [{"key": "p", "assignee": {"type": "role"}}],
                        "on_approve": "noexiste"}]}
    codigos = {e["code"] for e in D.validar(defn)}
    assert {"clave_invalida", "asignado_invalido", "fase_inexistente"} <= codigos


def test_el_simulador_sigue_la_puerta_y_salta_fases_condicionales():
    defn = plantillas.definicion_piloto(_ids_de_grupo())
    barato = D.simular(defn, {"coste": 1000})
    assert [p["phase"] for p in barato["path"]][-1] == "gobernanza"
    assert barato["path"][-1]["decision"] == "fast_track" and barato["end"] == D.FIN_APROBADA
    caro = D.simular(defn, {"coste": 100000})
    assert caro["path"][-1]["phase"] == "comite"
    cambio, _ = biblioteca._cambio_itil()
    estandar = D.simular(cambio, {"tipo_cambio": "estandar"})
    assert [p["phase"] for p in estandar["path"] if p["skipped"]] == ["cab", "ecab"]


def test_el_diagrama_tiene_las_ramas_de_la_puerta():
    g = D.diagrama(plantillas.definicion_piloto(_ids_de_grupo()))
    etiquetas = {(e["from"], e["label"]) for e in g["edges"]}
    assert ("gobernanza", "to_committee") in etiquetas and ("gobernanza", "fast_track") in etiquetas
    assert ("cab", "return") in etiquetas


# ── Recorrido completo (plantilla piloto) ────────────────────────────────────

def _usuario(db, uid):
    return db.query(User).filter(User.id == uid).first()


def _miembros(db, nombre, ids):
    from app.models.billing_reports import ApprovalGroup
    g = db.query(ApprovalGroup).filter(ApprovalGroup.organization_id == ORG, ApprovalGroup.name == nombre).first()
    g.member_ids = json.dumps(ids)
    db.commit()


@pytest.fixture
def piloto(db):
    plantillas.sembrar_plantilla_piloto(db, ORG, "admin-test-id")
    db.commit()
    _miembros(db, "Triaje de solicitudes", ["pm-test-id"])
    _miembros(db, "Equipo de análisis", ["pm-test-id"])
    _miembros(db, "CAB", ["pm-test-id", "admin-test-id", "hr-test-id"])
    _miembros(db, "Legal", ["admin-test-id"])
    _miembros(db, "Compliance", ["hr-test-id"])
    _miembros(db, "Comité de dirección", ["admin-test-id"])
    return db


def _crear(db, actor, **extra):
    from app.services.demanda import expediente
    datos = {"type_key": "new_feature", "title": "Panel de ventas", "submit": True,
             "data": {"descripcion_funcional": "Un panel", "justificacion": "Vender más",
                      "retorno_esperado": "10 %", "roi_estimado": 10}}
    datos.update(extra)
    return expediente.crear(db, actor, "operator", datos, org_id=ORG)


def test_recorrido_del_piloto_con_segregacion_pausa_paralelo_y_bypass(piloto):
    from app.models.demanda import DemandFieldVersion, DemandTransition
    from app.services.demanda import expediente
    from app.services.demanda.motor import decidir, verificar_cadena
    db = piloto
    pidiente = de_usuario(_usuario(db, "dev-test-id"))
    pm, admin, hr = (de_usuario(_usuario(db, u)) for u in ("pm-test-id", "admin-test-id", "hr-test-id"))
    req = _crear(db, pidiente)
    assert req.status == "in_progress" and req.current_phase_key == "solicitud" and req.standalone

    # Pedir información exige justificación y para el reloj; el solicitante la devuelve.
    with pytest.raises(ErrorDeDominio):
        decidir(db, req, pm, "triaje", "request_info")
    decidir(db, req, pm, "triaje", "request_info", justificacion="Falta el ROI detallado")
    assert req.status == "pending_info" and req.paused_since is not None
    expediente.editar(db, pidiente, req, None, {"retorno_esperado": "12 % el primer año"})
    expediente.enviar(db, pidiente, req)
    assert req.status == "in_progress" and req.paused_since is None

    decidir(db, req, pm, "triaje", "approve")
    assert req.current_phase_key == "estudio"
    # Completar el estudio exige los campos de la fase.
    with pytest.raises(ErrorDeDominio):
        decidir(db, req, pm, "estudio_digital", "complete")
    expediente.editar(db, pm, req, None, {
        "viabilidad_tecnica": "Viable", "arquitectura": "Microservicio", "ciberseguridad": "Sin datos sensibles",
        "solucion_tecnica": "Panel BI", "esfuerzo_horas": 300, "coste": 90000, "cronograma": "Q1",
        "retorno_ajustado": "8 %"})
    decidir(db, req, pm, "estudio_digital", "complete")
    assert req.current_phase_key == "cab" and req.client_locked

    # Quien estudió no vota en el CAB de su estudio.
    with pytest.raises(ErrorDeDominio) as e:
        decidir(db, req, pm, "revision_cab", "approve")
    assert e.value.code == "dem_sod_fase_previa"
    decidir(db, req, admin, "revision_cab", "approve")       # 1 de 3: mayoría = 2
    assert req.current_phase_key == "cab"
    decidir(db, req, hr, "revision_cab", "approve")
    assert req.current_phase_key == "normativa"

    # Legal y Compliance en paralelo: hacen falta los dos.
    decidir(db, req, admin, "legal", "approve")
    assert req.current_phase_key == "normativa"
    decidir(db, req, hr, "compliance", "approve")
    assert req.current_phase_key == "gobernanza" and req.committee_required is True

    # Vía rápida con umbrales superados = bypass: justificación obligatoria.
    with pytest.raises(ErrorDeDominio):
        decidir(db, req, pm, "decision_gobernanza", "fast_track")
    decidir(db, req, pm, "decision_gobernanza", "fast_track", justificacion="Urgencia regulatoria")
    assert req.status == "approved"
    bypass = db.query(DemandTransition).filter(DemandTransition.request_id == req.id,
                                               DemandTransition.is_bypass.is_(True)).all()
    assert len(bypass) == 1 and bypass[0].justification == "Urgencia regulatoria"

    # Log íntegro e inmutable; versiones del original y del refinado.
    assert verificar_cadena(db, req)
    t = bypass[0]
    t.justification = "otra"
    with pytest.raises(Exception):
        db.commit()
    db.rollback()
    fuentes = {(v.field, v.source) for v in db.query(DemandFieldVersion).filter(DemandFieldVersion.request_id == req.id)}
    assert ("retorno_esperado", "requester") in fuentes and ("coste", "internal") in fuentes


def test_quien_pide_no_decide_y_la_ficha_se_bloquea(piloto):
    from app.services.demanda import expediente
    from app.services.demanda.motor import decidir
    db = piloto
    pm = de_usuario(_usuario(db, "pm-test-id"))
    req = _crear(db, pm)
    with pytest.raises(ErrorDeDominio):
        decidir(db, req, pm, "triaje", "approve")
    req.client_locked = True
    db.commit()
    with pytest.raises(ErrorDeDominio):
        expediente.editar(db, pm, req, None, {"justificacion": "cambio"})


def test_ejecucion_a_cartera_y_acciones_al_cerrar(piloto):
    from app.models.portfolio import PortfolioProposal
    from app.services.demanda import ejecucion
    from app.services.demanda.motor import cerrar
    db = piloto
    req = _crear(db, de_usuario(_usuario(db, "dev-test-id")))
    admin = de_usuario(_usuario(db, "admin-test-id"))
    cerrar(db, req, admin, "approved", "approve")
    db.commit()
    ejecucion.ejecutar(db, admin, req, "portfolio", {})
    assert req.status == "done" and req.result_proposal_id
    assert db.query(PortfolioProposal).filter(PortfolioProposal.id == req.result_proposal_id).first().status == "approved"


def test_instalar_e_importar_plantillas(db):
    admin = _usuario(db, "admin-test-id")
    res = biblioteca.instalar(db, admin, "compra_por_importe")
    from app.models.demanda import DemandFlow, DemandRequestType
    f = db.query(DemandFlow).filter(DemandFlow.id == res["flow_id"]).first()
    exportado = biblioteca.exportar(db, f, db.query(DemandRequestType).filter(DemandRequestType.flow_id == f.id).all())
    assert exportado["format"] == biblioteca.FORMATO and exportado["types"]
    importado = biblioteca.importar(db, admin, exportado)
    assert importado["flow_id"] != f.id and importado["types"] == []  # la clave del tipo ya existía
    assert biblioteca.instalar(db, admin, "compra_por_importe")["created"] is False


def test_la_api_de_configuracion_es_solo_para_admin(client, admin_token, pm_token):
    from tests.conftest import auth
    assert client.get("/api/v1/demand/flows", headers=auth(pm_token)).status_code == 403
    r = client.post("/api/v1/demand/templates/peticion_rrhh/install", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/demand/flows/simulate", headers=auth(admin_token),
                    json={"definition": biblioteca._rrhh()[0], "data": {}})
    assert r.status_code == 200 and r.json()["data"]["end"] == D.FIN_APROBADA
