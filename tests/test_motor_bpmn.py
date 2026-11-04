"""El motor BPMN ejecuta los diagramas guardados en /bpm.

Auditoria 2026-11: /bpm era un editor; nada de un diagrama se ejecutaba.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.bpmn_process import BPMNInstanceStep, BPMNProcess
from app.services import bpmn_engine as motor
from tests.conftest import auth

_CAB = ('<?xml version="1.0" encoding="UTF-8"?><bpmn:definitions '
        'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="D" targetNamespace="x">')

APROBACION = _CAB + """
<bpmn:process id="P" isExecutable="true">
  <bpmn:laneSet><bpmn:lane id="L1" name="Project Manager"><bpmn:flowNodeRef>Revisar</bpmn:flowNodeRef></bpmn:lane></bpmn:laneSet>
  <bpmn:startEvent id="S"/>
  <bpmn:userTask id="Revisar" name="Revisar solicitud"/>
  <bpmn:exclusiveGateway id="G" name="¿Aprobada?" default="F_no"/>
  <bpmn:serviceTask id="Alta" name="Dar de alta"/>
  <bpmn:endEvent id="E_ok"/>
  <bpmn:endEvent id="E_no"/>
  <bpmn:sequenceFlow id="F1" sourceRef="S" targetRef="Revisar"/>
  <bpmn:sequenceFlow id="F2" sourceRef="Revisar" targetRef="G"/>
  <bpmn:sequenceFlow id="F_si" sourceRef="G" targetRef="Alta"><bpmn:conditionExpression>${aprobada == true and importe &lt;= 1000}</bpmn:conditionExpression></bpmn:sequenceFlow>
  <bpmn:sequenceFlow id="F_no" sourceRef="G" targetRef="E_no"/>
  <bpmn:sequenceFlow id="F3" sourceRef="Alta" targetRef="E_ok"/>
</bpmn:process></bpmn:definitions>"""

PARALELO = _CAB + """
<bpmn:process id="P" isExecutable="true">
  <bpmn:startEvent id="S"/>
  <bpmn:parallelGateway id="Fork"/>
  <bpmn:task id="A" name="A"/>
  <bpmn:task id="B" name="B"/>
  <bpmn:parallelGateway id="Join"/>
  <bpmn:intermediateCatchEvent id="T" name="Esperar"><bpmn:timerEventDefinition><bpmn:timeDuration>PT2H</bpmn:timeDuration></bpmn:timerEventDefinition></bpmn:intermediateCatchEvent>
  <bpmn:endEvent id="E"/>
  <bpmn:sequenceFlow id="f1" sourceRef="S" targetRef="Fork"/>
  <bpmn:sequenceFlow id="f2" sourceRef="Fork" targetRef="A"/>
  <bpmn:sequenceFlow id="f3" sourceRef="Fork" targetRef="B"/>
  <bpmn:sequenceFlow id="f4" sourceRef="A" targetRef="Join"/>
  <bpmn:sequenceFlow id="f5" sourceRef="B" targetRef="Join"/>
  <bpmn:sequenceFlow id="f6" sourceRef="Join" targetRef="T"/>
  <bpmn:sequenceFlow id="f7" sourceRef="T" targetRef="E"/>
</bpmn:process></bpmn:definitions>"""


def _proceso(client, token, xml, nombre="Proceso"):
    r = client.post("/api/v1/bpmn-processes", headers=auth(token),
                    json={"name": nombre, "category": "custom", "bpmn_xml": xml})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _arrancar(client, token, pid, variables=None):
    return client.post(f"/api/v1/bpmn-processes/{pid}/instances", headers=auth(token),
                       json={"variables": variables or {}})


def _pendiente(inst, nombre):
    return next(s for s in inst["steps"] if s["status"] == "active" and s["name"] == nombre)


def test_EL_HALLAZGO_un_diagrama_se_ejecuta_y_su_tarea_llega_a_la_bandeja(client, pm_token, db):
    pid = _proceso(client, pm_token, APROBACION)
    r = _arrancar(client, pm_token, pid, {"importe": 500})
    assert r.status_code == 200, r.text
    inst = r.json()["data"]
    assert inst["status"] == "running" and inst["active_steps"] == ["Revisar solicitud"]
    bandeja = client.get("/api/v1/bpmn-instances/inbox", headers=auth(pm_token)).json()["items"]
    assert [p["name"] for p in bandeja] == ["Revisar solicitud"]
    assert bandeja[0]["candidate_role"] == "pm"

    paso = _pendiente(inst, "Revisar solicitud")
    r = client.post(f"/api/v1/bpmn-instances/{inst['id']}/steps/{paso['id']}/complete",
                    headers=auth(pm_token), json={"variables": {"aprobada": True}})
    assert r.status_code == 200, r.text
    fin = r.json()["data"]
    assert fin["status"] == "completed"
    recorrido = [s["element_id"] for s in fin["steps"]]
    assert recorrido == ["S", "Revisar", "G", "Alta", "E_ok"]


def test_la_salida_por_defecto_cuando_no_se_cumple_la_condicion(client, pm_token, db):
    pid = _proceso(client, pm_token, APROBACION)
    inst = _arrancar(client, pm_token, pid, {"importe": 5000}).json()["data"]
    paso = _pendiente(inst, "Revisar solicitud")
    fin = client.post(f"/api/v1/bpmn-instances/{inst['id']}/steps/{paso['id']}/complete",
                      headers=auth(pm_token), json={"variables": {"aprobada": True}}).json()["data"]
    assert fin["status"] == "completed"
    assert "E_no" in [s["element_id"] for s in fin["steps"]] and "Alta" not in [s["element_id"] for s in fin["steps"]]


def test_la_tarea_de_la_calle_pm_no_la_completa_un_empleado(client, pm_token, dev_token, db):
    pid = _proceso(client, pm_token, APROBACION)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    paso = _pendiente(inst, "Revisar solicitud")
    assert client.get("/api/v1/bpmn-instances/inbox", headers=auth(dev_token)).json()["items"] == []
    r = client.post(f"/api/v1/bpmn-instances/{inst['id']}/steps/{paso['id']}/complete", headers=auth(dev_token))
    assert r.status_code == 403


def test_paralelo_espera_a_las_dos_ramas_y_el_temporizador_despierta(client, pm_token, db):
    pid = _proceso(client, pm_token, PARALELO)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    assert sorted(inst["active_steps"]) == ["A", "B"]
    a = _pendiente(inst, "A")
    inst = client.post(f"/api/v1/bpmn-instances/{inst['id']}/steps/{a['id']}/complete",
                       headers=auth(pm_token)).json()["data"]
    assert "Esperar" not in inst["active_steps"], "la union no espero a la otra rama"
    b = _pendiente(inst, "B")
    inst = client.post(f"/api/v1/bpmn-instances/{inst['id']}/steps/{b['id']}/complete",
                       headers=auth(pm_token)).json()["data"]
    assert inst["active_steps"] == ["Esperar"]
    assert motor.vencer_temporizadores(db)["timers_fired"] == 0
    paso = db.query(BPMNInstanceStep).filter(BPMNInstanceStep.element_id == "T").one()
    paso.due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert motor.vencer_temporizadores(db)["timers_fired"] == 1
    fin = client.get(f"/api/v1/bpmn-instances/{inst['id']}", headers=auth(pm_token)).json()["data"]
    assert fin["status"] == "completed"


def test_EL_HALLAZGO_lo_que_no_se_soporta_no_arranca(client, pm_token, db):
    xml = APROBACION.replace('<bpmn:serviceTask id="Alta" name="Dar de alta"/>',
                             '<bpmn:subProcess id="Alta" name="Dar de alta"/>')
    pid = _proceso(client, pm_token, xml)
    r = _arrancar(client, pm_token, pid)
    assert r.status_code == 422
    assert "subProcess" in r.text


def test_el_diagrama_de_ejemplo_lineal_se_ejecuta(client, pm_token, db):
    from app.services.bpmn_process_service import build_bpmn_xml
    pid = _proceso(client, pm_token, build_bpmn_xml("lin", "Lineal", ["Inicio", "Preparar", "Enviar", "Fin"]))
    inst = _arrancar(client, pm_token, pid).json()["data"]
    assert inst["active_steps"] == ["Preparar"]


def test_un_bucle_sin_espera_falla_en_vez_de_colgarse(client, pm_token, db):
    xml = _CAB + """<bpmn:process id="P"><bpmn:startEvent id="S"/>
      <bpmn:serviceTask id="X" name="X"/><bpmn:serviceTask id="Y" name="Y"/>
      <bpmn:sequenceFlow id="a" sourceRef="S" targetRef="X"/>
      <bpmn:sequenceFlow id="b" sourceRef="X" targetRef="Y"/>
      <bpmn:sequenceFlow id="c" sourceRef="Y" targetRef="X"/></bpmn:process></bpmn:definitions>"""
    pid = _proceso(client, pm_token, xml)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    assert inst["status"] == "failed" and "bucle" in inst["error"]


def test_otra_organizacion_no_arranca_ni_ve_la_instancia(client, pm_token, db):
    pid = _proceso(client, pm_token, APROBACION)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    proc = db.query(BPMNProcess).filter(BPMNProcess.id == pid).one()
    proc.organization_id = "org-ajena"
    db.commit()
    assert _arrancar(client, pm_token, pid).status_code == 404
    assert client.get(f"/api/v1/bpmn-processes/{pid}", headers=auth(pm_token)).status_code == 404
    assert client.patch(f"/api/v1/bpmn-processes/{pid}", json={"name": "x"}, headers=auth(pm_token)).status_code == 404
    assert client.post(f"/api/v1/bpmn-processes/{pid}/versions", json={"bpmn_xml": APROBACION},
                       headers=auth(pm_token)).status_code == 404


@pytest.mark.parametrize("texto,variables,esperado", [
    ("${a == 'x'}", {"a": "x"}, True),
    ("a != 'x' or b > 3", {"a": "x", "b": 4}, True),
    ("a > 3 && b == true", {"a": 4, "b": "true"}, True),
    ("a > 3", {"a": "no-numero"}, False),
    ("a ~ 3", {"a": 3}, False),
    ("falta == 1", {}, False),
])
def test_condiciones(texto, variables, esperado):
    assert motor.cumple(texto, variables) is esperado
