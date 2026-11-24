"""Revisión BPM 23-11-2026 (migración 204, docs/BPM.md): lo que faltaba, medido.

Compuertas inclusivas y uniones paralelas, temporizadores de borde y SLA,
subprocesos, llamadas, errores, mensajes, versionado (retirar), formularios y
variables tipadas, asignación, segregación de funciones, suspender, migrar,
acciones automáticas con reintentos, simulación, XXE, aislamiento y RGPD.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.bpmn_process import BPMNInstance, BPMNInstanceStep, BPMNProcess, BPMNProcessVersion
from app.services import bpmn_engine as motor
from tests.conftest import auth

_CAB = ('<?xml version="1.0" encoding="UTF-8"?><bpmn:definitions '
        'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:contecflow="http://contecflow.io/schema/bpmn/1.0" id="D" targetNamespace="x">')
_FIN = "</bpmn:process></bpmn:definitions>"


def _xml(cuerpo: str, extra: str = "") -> str:
    return _CAB + extra + '<bpmn:process id="P" isExecutable="true">' + cuerpo + _FIN


INCLUSIVA = _xml("""
  <bpmn:startEvent id="S"/>
  <bpmn:inclusiveGateway id="Split" default="f_def"/>
  <bpmn:userTask id="A" name="A"/><bpmn:userTask id="B" name="B"/><bpmn:userTask id="C" name="C"/>
  <bpmn:inclusiveGateway id="Join"/>
  <bpmn:userTask id="Fin" name="Fin"/>
  <bpmn:endEvent id="E"/>
  <bpmn:sequenceFlow id="f0" sourceRef="S" targetRef="Split"/>
  <bpmn:sequenceFlow id="fa" sourceRef="Split" targetRef="A"><bpmn:conditionExpression>importe &gt; 100</bpmn:conditionExpression></bpmn:sequenceFlow>
  <bpmn:sequenceFlow id="fb" sourceRef="Split" targetRef="B"><bpmn:conditionExpression>urgente == true</bpmn:conditionExpression></bpmn:sequenceFlow>
  <bpmn:sequenceFlow id="f_def" sourceRef="Split" targetRef="C"/>
  <bpmn:sequenceFlow id="ja" sourceRef="A" targetRef="Join"/>
  <bpmn:sequenceFlow id="jb" sourceRef="B" targetRef="Join"/>
  <bpmn:sequenceFlow id="jc" sourceRef="C" targetRef="Join"/>
  <bpmn:sequenceFlow id="f9" sourceRef="Join" targetRef="Fin"/>
  <bpmn:sequenceFlow id="f10" sourceRef="Fin" targetRef="E"/>""")

BORDE = _xml("""
  <bpmn:startEvent id="S"/>
  <bpmn:userTask id="T" name="Revisar" contecflow:dueIn="P1D"/>
  <bpmn:boundaryEvent id="Tmo" name="Escalar" attachedToRef="T"><bpmn:timerEventDefinition><bpmn:timeDuration>PT4H</bpmn:timeDuration></bpmn:timerEventDefinition></bpmn:boundaryEvent>
  <bpmn:userTask id="Esc" name="Escalado"/>
  <bpmn:endEvent id="E1"/><bpmn:endEvent id="E2"/>
  <bpmn:sequenceFlow id="a" sourceRef="S" targetRef="T"/>
  <bpmn:sequenceFlow id="b" sourceRef="T" targetRef="E1"/>
  <bpmn:sequenceFlow id="c" sourceRef="Tmo" targetRef="Esc"/>
  <bpmn:sequenceFlow id="d" sourceRef="Esc" targetRef="E2"/>""")

SUBPROCESO_Y_ERROR = _xml("""
  <bpmn:startEvent id="S"/>
  <bpmn:subProcess id="Sub" name="Revisión">
    <bpmn:startEvent id="S2"/>
    <bpmn:userTask id="R" name="Revisar dentro"/>
    <bpmn:exclusiveGateway id="G" default="ok"/>
    <bpmn:endEvent id="Err"><bpmn:errorEventDefinition errorRef="E_RECH"/></bpmn:endEvent>
    <bpmn:endEvent id="E2"/>
    <bpmn:sequenceFlow id="i1" sourceRef="S2" targetRef="R"/>
    <bpmn:sequenceFlow id="i2" sourceRef="R" targetRef="G"/>
    <bpmn:sequenceFlow id="ko" sourceRef="G" targetRef="Err"><bpmn:conditionExpression>rechazado == true</bpmn:conditionExpression></bpmn:sequenceFlow>
    <bpmn:sequenceFlow id="ok" sourceRef="G" targetRef="E2"/>
  </bpmn:subProcess>
  <bpmn:boundaryEvent id="Cap" attachedToRef="Sub"><bpmn:errorEventDefinition errorRef="E_RECH"/></bpmn:boundaryEvent>
  <bpmn:userTask id="Despues" name="Después"/>
  <bpmn:userTask id="Corregir" name="Corregir"/>
  <bpmn:endEvent id="E"/><bpmn:endEvent id="EK"/>
  <bpmn:sequenceFlow id="a" sourceRef="S" targetRef="Sub"/>
  <bpmn:sequenceFlow id="b" sourceRef="Sub" targetRef="Despues"/>
  <bpmn:sequenceFlow id="c" sourceRef="Despues" targetRef="E"/>
  <bpmn:sequenceFlow id="d" sourceRef="Cap" targetRef="Corregir"/>
  <bpmn:sequenceFlow id="e" sourceRef="Corregir" targetRef="EK"/>""", '<bpmn:error id="E_RECH" errorCode="rechazo"/>')

MENSAJE = _xml("""
  <bpmn:startEvent id="S"/>
  <bpmn:intermediateCatchEvent id="M" name="Pago"><bpmn:messageEventDefinition messageRef="Msg"/></bpmn:intermediateCatchEvent>
  <bpmn:endEvent id="E"/>
  <bpmn:sequenceFlow id="a" sourceRef="S" targetRef="M"/>
  <bpmn:sequenceFlow id="b" sourceRef="M" targetRef="E"/>""", '<bpmn:message id="Msg" name="pago_recibido"/>')

FORMULARIO = _xml("""
  <bpmn:startEvent id="S"/>
  <bpmn:userTask id="F" name="Datos" contecflow:formFields='[{"name":"importe","type":"number","required":true},{"name":"urgente","type":"boolean"}]'/>
  <bpmn:endEvent id="E"/>
  <bpmn:sequenceFlow id="a" sourceRef="S" targetRef="F"/>
  <bpmn:sequenceFlow id="b" sourceRef="F" targetRef="E"/>""")

APROBACION = _xml("""
  <bpmn:startEvent id="S"/>
  <bpmn:userTask id="Ap" name="Aprobar" contecflow:approval="true"/>
  <bpmn:endEvent id="E"/>
  <bpmn:sequenceFlow id="a" sourceRef="S" targetRef="Ap"/>
  <bpmn:sequenceFlow id="b" sourceRef="Ap" targetRef="E"/>""")

ACCION = _xml("""
  <bpmn:startEvent id="S"/>
  <bpmn:serviceTask id="Set" name="Fijar" contecflow:action="set" contecflow:actionConfig='{"variables":{"estado":"alta de ${nombre}"}}'/>
  <bpmn:userTask id="T" name="Siguiente"/>
  <bpmn:endEvent id="E"/>
  <bpmn:sequenceFlow id="a" sourceRef="S" targetRef="Set"/>
  <bpmn:sequenceFlow id="b" sourceRef="Set" targetRef="T"/>
  <bpmn:sequenceFlow id="c" sourceRef="T" targetRef="E"/>""")

LINEAL = _xml("""
  <bpmn:startEvent id="S"/><bpmn:userTask id="T" name="Tarea"/><bpmn:endEvent id="E"/>
  <bpmn:sequenceFlow id="a" sourceRef="S" targetRef="T"/><bpmn:sequenceFlow id="b" sourceRef="T" targetRef="E"/>""")


def _proceso(client, token, xml, nombre="Proceso", **extra):
    r = client.post("/api/v1/bpmn-processes", headers=auth(token),
                    json={"name": nombre, "category": "admin", "bpmn_xml": xml, **extra})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _arrancar(client, token, pid, variables=None, **extra):
    return client.post(f"/api/v1/bpmn-processes/{pid}/instances", headers=auth(token),
                       json={"variables": variables or {}, **extra})


def _activo(inst, nombre):
    return next(s for s in inst["steps"] if s["status"] == "active" and s["name"] == nombre)


def _completar(client, token, inst, nombre, **payload):
    paso = _activo(inst, nombre)
    r = client.post(f"/api/v1/bpmn-instances/{inst['id']}/steps/{paso['id']}/complete", headers=auth(token),
                    json=payload)
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ── Compuertas ──────────────────────────────────────────────────────────────

def test_inclusiva_reparte_por_las_condiciones_y_la_union_espera_solo_a_las_activadas(client, pm_token, db):
    pid = _proceso(client, pm_token, INCLUSIVA)
    inst = _arrancar(client, pm_token, pid, {"importe": 500, "urgente": True}).json()["data"]
    assert sorted(inst["active_steps"]) == ["A", "B"], "C es la de por defecto: no se toma si otra se cumple"
    inst = _completar(client, pm_token, inst, "A")
    assert "Fin" not in inst["active_steps"], "la unión inclusiva no esperó a B"
    inst = _completar(client, pm_token, inst, "B")
    assert inst["active_steps"] == ["Fin"]


def test_inclusiva_con_una_sola_rama_no_se_queda_colgada(client, pm_token, db):
    pid = _proceso(client, pm_token, INCLUSIVA)
    inst = _arrancar(client, pm_token, pid, {"importe": 5, "urgente": False}).json()["data"]
    assert inst["active_steps"] == ["C"]
    inst = _completar(client, pm_token, inst, "C")
    assert inst["active_steps"] == ["Fin"]


def test_inclusiva_sin_condiciones_es_decision_de_varias_salidas(client, pm_token, db):
    xml = INCLUSIVA.replace("<bpmn:conditionExpression>importe &gt; 100</bpmn:conditionExpression>", "") \
        .replace("<bpmn:conditionExpression>urgente == true</bpmn:conditionExpression>", "") \
        .replace(' default="f_def"', "")
    pid = _proceso(client, pm_token, xml)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    paso = next(s for s in inst["steps"] if s["status"] == "active")
    assert paso["wait_kind"] == "decision" and paso["multiple"] is True
    r = client.post(f"/api/v1/bpmn-instances/{inst['id']}/steps/{paso['id']}/complete", headers=auth(pm_token),
                    json={"flow_ids": ["fa", "f_def"]})
    assert r.status_code == 200, r.text
    assert sorted(r.json()["data"]["active_steps"]) == ["A", "C"]


def test_la_union_paralela_cuenta_flujos_y_no_fichas(db):
    """Dos fichas por el mismo flujo de entrada no cierran una unión de dos entradas."""
    g = motor.leer(_xml("""
      <bpmn:startEvent id="S"/><bpmn:parallelGateway id="J"/><bpmn:endEvent id="E"/>
      <bpmn:userTask id="X" name="X"/>
      <bpmn:sequenceFlow id="a" sourceRef="S" targetRef="J"/><bpmn:sequenceFlow id="b" sourceRef="X" targetRef="J"/>
      <bpmn:sequenceFlow id="c" sourceRef="J" targetRef="E"/><bpmn:sequenceFlow id="d" sourceRef="S" targetRef="X"/>"""))
    assert set(g.nodos["J"].entradas) == {"a", "b"}


# ── Temporizadores, SLA y escalado ─────────────────────────────────────────

def test_el_borde_de_temporizador_interrumpe_y_escala(client, pm_token, db):
    pid = _proceso(client, pm_token, BORDE)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    tarea = _activo(inst, "Revisar")
    assert tarea["sla_due_at"] is not None
    borde = db.query(BPMNInstanceStep).filter(BPMNInstanceStep.element_id == "Tmo").one()
    assert borde.status == "active" and borde.wait_kind == "timer"
    borde.due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert motor.vencer_temporizadores(db)["timers_fired"] == 1
    d = client.get(f"/api/v1/bpmn-instances/{inst['id']}", headers=auth(pm_token)).json()["data"]
    assert d["active_steps"] == ["Escalado"]
    assert next(s for s in d["steps"] if s["element_id"] == "T")["status"] == "cancelled"


def test_el_plazo_vencido_se_escala_una_vez(client, pm_token, db):
    pid = _proceso(client, pm_token, BORDE)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    paso = db.query(BPMNInstanceStep).filter(BPMNInstanceStep.instance_id == inst["id"],
                                             BPMNInstanceStep.element_id == "T").one()
    paso.sla_due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert motor.escalar_plazos(db) == 1
    assert motor.escalar_plazos(db) == 0
    bandeja = client.get("/api/v1/bpmn-instances/inbox", headers=auth(pm_token)).json()["items"]
    assert next(p for p in bandeja if p["instance_id"] == inst["id"])["overdue"] is True


# ── Subprocesos, errores, mensajes y llamadas ──────────────────────────────

def test_el_subproceso_termina_y_sigue_fuera(client, pm_token, db):
    pid = _proceso(client, pm_token, SUBPROCESO_Y_ERROR)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    assert sorted(inst["active_steps"]) == ["Revisar dentro", "Revisión"]
    inst = _completar(client, pm_token, inst, "Revisar dentro")
    assert inst["active_steps"] == ["Después"]


def test_el_error_del_subproceso_lo_captura_su_borde(client, pm_token, db):
    pid = _proceso(client, pm_token, SUBPROCESO_Y_ERROR)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    inst = _completar(client, pm_token, inst, "Revisar dentro", variables={"rechazado": True})
    assert inst["status"] == "running" and inst["active_steps"] == ["Corregir"]


def test_el_mensaje_por_clave_de_negocio_despierta_la_instancia(client, pm_token, db):
    pid = _proceso(client, pm_token, MENSAJE)
    inst = _arrancar(client, pm_token, pid, business_key="PED-1").json()["data"]
    assert inst["status"] == "running" and inst["business_key"] == "PED-1"
    r = client.post("/api/v1/bpmn-instances/messages", headers=auth(pm_token),
                    json={"message": "pago_recibido", "business_key": "PED-1", "variables": {"importe": 10}})
    assert r.status_code == 200, r.text
    d = client.get(f"/api/v1/bpmn-instances/{inst['id']}", headers=auth(pm_token)).json()["data"]
    assert d["status"] == "completed" and d["variables"]["importe"] == 10
    r = client.post("/api/v1/bpmn-instances/messages", headers=auth(pm_token),
                    json={"message": "pago_recibido", "business_key": "PED-1"})
    assert r.status_code == 404


def test_la_llamada_arranca_la_hija_y_sigue_al_terminar(client, pm_token, db):
    hija = _proceso(client, pm_token, LINEAL, nombre="Hija")
    clave = db.query(BPMNProcess).filter(BPMNProcess.id == hija).one().key
    client.post(f"/api/v1/bpmn-processes/{hija}/versions/1/publish", headers=auth(pm_token))
    padre = _proceso(client, pm_token, _xml(f"""
      <bpmn:startEvent id="S"/><bpmn:callActivity id="C" name="Llamar" calledElement="{clave}"/>
      <bpmn:userTask id="T2" name="Después"/><bpmn:endEvent id="E"/>
      <bpmn:sequenceFlow id="a" sourceRef="S" targetRef="C"/><bpmn:sequenceFlow id="b" sourceRef="C" targetRef="T2"/>
      <bpmn:sequenceFlow id="c" sourceRef="T2" targetRef="E"/>"""), nombre="Padre")
    inst = _arrancar(client, pm_token, padre).json()["data"]
    assert inst["active_steps"] == ["Llamar"] and len(inst["children"]) == 1
    hija_inst = client.get(f"/api/v1/bpmn-instances/{inst['children'][0]['id']}", headers=auth(pm_token)).json()["data"]
    _completar(client, pm_token, hija_inst, "Tarea", variables={"resultado": "ok"})
    d = client.get(f"/api/v1/bpmn-instances/{inst['id']}", headers=auth(pm_token)).json()["data"]
    assert d["active_steps"] == ["Después"] and d["variables"]["resultado"] == "ok"


# ── Versionado ──────────────────────────────────────────────────────────────

def test_retirar_la_version_impide_arrancar_y_la_instancia_sigue_en_la_suya(client, pm_token, db):
    pid = _proceso(client, pm_token, LINEAL)
    url = f"/api/v1/bpmn-processes/{pid}"
    assert client.post(f"{url}/versions/1/publish", headers=auth(pm_token)).status_code == 200
    inst = _arrancar(client, pm_token, pid).json()["data"]
    r = client.post(f"{url}/versions/1/retire", headers=auth(pm_token))
    assert r.status_code == 200 and r.json()["data"]["state"] == "retired"
    assert _arrancar(client, pm_token, pid).status_code == 409
    fin = _completar(client, pm_token, inst, "Tarea")
    assert fin["status"] == "completed" and fin["version"] == 1
    v = db.query(BPMNProcessVersion).filter(BPMNProcessVersion.process_id == pid).one()
    assert v.retired_by_user_id is not None


def test_migrar_una_instancia_a_otra_version_compatible(client, pm_token, db):
    pid = _proceso(client, pm_token, LINEAL)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    client.post(f"/api/v1/bpmn-processes/{pid}/versions", headers=auth(pm_token),
                json={"bpmn_xml": LINEAL.replace('name="Tarea"', 'name="Tarea v2"')})
    r = client.post(f"/api/v1/bpmn-instances/{inst['id']}/migrate", headers=auth(pm_token), json={"version": 2})
    assert r.status_code == 200 and r.json()["data"]["version"] == 2
    incompatible = LINEAL.replace('id="T"', 'id="T9"').replace('targetRef="T"', 'targetRef="T9"').replace('sourceRef="T"', 'sourceRef="T9"')
    client.post(f"/api/v1/bpmn-processes/{pid}/versions", headers=auth(pm_token), json={"bpmn_xml": incompatible})
    assert client.post(f"/api/v1/bpmn-instances/{inst['id']}/migrate", headers=auth(pm_token),
                       json={"version": 3}).status_code == 409


# ── Formularios, variables y asignación ────────────────────────────────────

def test_el_formulario_valida_tipos_y_obligatorios(client, pm_token, db):
    pid = _proceso(client, pm_token, FORMULARIO)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    paso = _activo(inst, "Datos")
    assert [c["name"] for c in paso["form"]] == ["importe", "urgente"]
    url = f"/api/v1/bpmn-instances/{inst['id']}/steps/{paso['id']}/complete"
    assert client.post(url, headers=auth(pm_token), json={"variables": {"urgente": True}}).status_code == 422
    assert client.post(url, headers=auth(pm_token), json={"variables": {"importe": "mucho"}}).status_code == 422
    assert client.post(url, headers=auth(pm_token), json={"variables": {"importe": 1, "otra": 1}}).status_code == 422
    r = client.post(url, headers=auth(pm_token), json={"variables": {"importe": "1200", "urgente": "true"}})
    assert r.status_code == 200 and r.json()["data"]["variables"] == {"importe": 1200.0, "urgente": True}


def test_las_variables_declaradas_se_tipan_al_arrancar(client, pm_token, db):
    pid = _proceso(client, pm_token, LINEAL, variables_schema=[{"name": "dias", "type": "integer", "personal": False}])
    assert _arrancar(client, pm_token, pid, {"dias": "tres"}).status_code == 422
    inst = _arrancar(client, pm_token, pid, {"dias": "3"}).json()["data"]
    assert inst["variables"]["dias"] == 3


def test_asignada_a_una_persona_solo_la_ve_ella(client, pm_token, dev_token, db):
    from app.models.user import User
    dev = db.query(User).filter(User.role == "employee").first()
    pid = _proceso(client, pm_token, LINEAL.replace('name="Tarea"', f'name="Tarea" contecflow:assignee="{dev.email}"'))
    inst = _arrancar(client, pm_token, pid).json()["data"]
    paso = _activo(inst, "Tarea")
    assert paso["assignee_user_id"] == dev.id
    assert [p["id"] for p in client.get("/api/v1/bpmn-instances/inbox", headers=auth(dev_token)).json()["items"]] == [paso["id"]]
    # Reasignar a nadie: queda libre y queda en la auditoría.
    r = client.post(f"/api/v1/bpmn-instances/{inst['id']}/steps/{paso['id']}/assign", headers=auth(pm_token),
                    json={"user_id": None})
    assert r.status_code == 200
    from app.models.enterprise import AuditLog
    assert db.query(AuditLog).filter(AuditLog.resource_id == inst["id"], AuditLog.action == "REASSIGN").count() == 1


def test_un_empleado_no_reasigna(client, pm_token, dev_token, db):
    pid = _proceso(client, pm_token, LINEAL)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    paso = _activo(inst, "Tarea")
    assert client.post(f"/api/v1/bpmn-instances/{inst['id']}/steps/{paso['id']}/assign", headers=auth(dev_token),
                       json={"user_id": None}).status_code == 403


# ── Segregación de funciones ───────────────────────────────────────────────

def test_quien_publica_no_aprueba_si_la_empresa_lo_exige(client, pm_token, db, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "BPMN_SEGREGACION_DE_FUNCIONES", True)
    pid = _proceso(client, pm_token, APROBACION)
    client.post(f"/api/v1/bpmn-processes/{pid}/versions/1/publish", headers=auth(pm_token))
    inst = _arrancar(client, pm_token, pid).json()["data"]
    paso = _activo(inst, "Aprobar")
    r = client.post(f"/api/v1/bpmn-instances/{inst['id']}/steps/{paso['id']}/complete", headers=auth(pm_token),
                    json={"variables": {"aprobado": True}})
    assert r.status_code == 403 and r.json()["code"] == "bpm_segregacion_de_funciones"
    monkeypatch.setattr(settings, "BPMN_SEGREGACION_DE_FUNCIONES", False)
    assert client.post(f"/api/v1/bpmn-instances/{inst['id']}/steps/{paso['id']}/complete", headers=auth(pm_token),
                       json={"variables": {"aprobado": True}}).status_code == 200


# ── Suspender ──────────────────────────────────────────────────────────────

def test_suspendida_no_se_completa_y_reanudada_si(client, pm_token, db):
    pid = _proceso(client, pm_token, LINEAL)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    paso = _activo(inst, "Tarea")
    assert client.post(f"/api/v1/bpmn-instances/{inst['id']}/suspend", headers=auth(pm_token)).status_code == 200
    url = f"/api/v1/bpmn-instances/{inst['id']}/steps/{paso['id']}/complete"
    assert client.post(url, headers=auth(pm_token)).status_code == 409
    assert client.post(f"/api/v1/bpmn-instances/{inst['id']}/resume", headers=auth(pm_token)).status_code == 200
    assert client.post(url, headers=auth(pm_token)).json()["data"]["status"] == "completed"


# ── Acciones automáticas ───────────────────────────────────────────────────

def test_la_accion_set_se_ejecuta_sola(client, pm_token, db):
    pid = _proceso(client, pm_token, ACCION)
    inst = _arrancar(client, pm_token, pid, {"nombre": "Ana"}).json()["data"]
    assert inst["active_steps"] == ["Siguiente"]
    assert inst["variables"]["estado"] == "alta de Ana"


def test_la_accion_que_falla_reintenta_y_acaba_en_incidente(client, pm_token, db, monkeypatch):
    from app.services import bpmn_acciones

    def falla(*a, **k):
        raise RuntimeError("caido")

    monkeypatch.setattr(bpmn_acciones, "ejecutar", falla)
    pid = _proceso(client, pm_token, ACCION.replace('contecflow:action="set"', 'contecflow:action="set" contecflow:retries="1"'))
    inst = _arrancar(client, pm_token, pid).json()["data"]
    paso = db.query(BPMNInstanceStep).filter(BPMNInstanceStep.instance_id == inst["id"],
                                             BPMNInstanceStep.element_id == "Set").one()
    assert paso.wait_kind == "retry" and paso.attempts == 1
    paso.due_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    motor.ejecutar_trabajos(db, instancia_id=inst["id"])
    db.refresh(paso)
    assert paso.wait_kind == "incident"
    monkeypatch.undo()
    r = client.post(f"/api/v1/bpmn-instances/{inst['id']}/steps/{paso.id}/retry", headers=auth(pm_token))
    assert r.status_code == 200 and r.json()["data"]["active_steps"] == ["Siguiente"]


def test_una_accion_desconocida_no_se_publica(client, pm_token, db):
    pid = _proceso(client, pm_token, ACCION.replace('contecflow:action="set"', 'contecflow:action="ejecutar_python"'))
    r = client.post(f"/api/v1/bpmn-processes/{pid}/versions/1/publish", headers=auth(pm_token))
    assert r.status_code == 422


def test_un_script_task_nunca_ejecuta_codigo(client, pm_token, db):
    xml = LINEAL.replace('<bpmn:userTask id="T" name="Tarea"/>',
                         '<bpmn:scriptTask id="T" name="Tarea" scriptFormat="python"><bpmn:script>import os</bpmn:script></bpmn:scriptTask>')
    pid = _proceso(client, pm_token, xml)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    paso = _activo(inst, "Tarea")
    assert paso["wait_kind"] == "task" and paso["result"]["automatic"] is False


# ── Simulación ─────────────────────────────────────────────────────────────

def test_la_simulacion_detecta_la_union_paralela_colgada(client, pm_token, db):
    colgada = _xml("""
      <bpmn:startEvent id="S"/><bpmn:exclusiveGateway id="G" default="x"/>
      <bpmn:userTask id="A" name="A"/><bpmn:userTask id="B" name="B"/>
      <bpmn:parallelGateway id="J" name="Unión"/><bpmn:endEvent id="E"/>
      <bpmn:sequenceFlow id="s" sourceRef="S" targetRef="G"/>
      <bpmn:sequenceFlow id="x" sourceRef="G" targetRef="A"/>
      <bpmn:sequenceFlow id="y" sourceRef="G" targetRef="B"><bpmn:conditionExpression>v == 1</bpmn:conditionExpression></bpmn:sequenceFlow>
      <bpmn:sequenceFlow id="a" sourceRef="A" targetRef="J"/><bpmn:sequenceFlow id="b" sourceRef="B" targetRef="J"/>
      <bpmn:sequenceFlow id="e" sourceRef="J" targetRef="E"/>""")
    pid = _proceso(client, pm_token, colgada)
    d = client.post(f"/api/v1/bpmn-processes/{pid}/simulate", headers=auth(pm_token), json={}).json()["data"]
    assert d["completed"] is False and d["stuck"][0]["element_id"] == "J"
    assert db.query(BPMNInstance).filter(BPMNInstance.process_id == pid).count() == 0
    ok = client.post(f"/api/v1/bpmn-processes/{pid}/simulate", headers=auth(pm_token), json={}).json()["data"]
    assert [p["element_id"] for p in ok["path"]][:3] == ["S", "G", "A"]


def test_la_simulacion_de_la_inclusiva_llega_al_final(db):
    d = motor.simular(INCLUSIVA, {"importe": 500, "urgente": True})
    recorrido = [p["element_id"] for p in d["path"]]
    assert d["completed"] is True and recorrido[-1] == "E"
    assert recorrido.count("Join") == 1 and recorrido.count("Fin") == 1, "la unión pasó dos veces"


# ── Seguridad: XXE y aislamiento ──────────────────────────────────────────

@pytest.mark.parametrize("xml", [
    '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
    '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"><bpmn:process id="P">&x;</bpmn:process></bpmn:definitions>',
    '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
    '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"><bpmn:process id="P">&b;</bpmn:process></bpmn:definitions>',
    '<?xml version="1.0"?><!DOCTYPE d SYSTEM "http://evil.invalid/x.dtd">'
    '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"><bpmn:process id="P"/></bpmn:definitions>',
])
def test_EL_HALLAZGO_xxe_ni_dtd_se_guardan_ni_se_ejecutan(client, pm_token, db, xml):
    r = client.post("/api/v1/bpmn-processes", headers=auth(pm_token),
                    json={"name": "XXE", "category": "admin", "bpmn_xml": xml})
    assert r.status_code == 422
    assert [p.code for p in motor.leer(xml).problemas] == ["invalid_xml"]


def test_otra_empresa_no_ve_ni_gobierna_la_instancia(client, pm_token, db):
    pid = _proceso(client, pm_token, LINEAL)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    fila = db.query(BPMNInstance).filter(BPMNInstance.id == inst["id"]).one()
    fila.organization_id = "org-ajena"
    db.commit()
    for ruta in ("suspend", "cancel", "resume"):
        assert client.post(f"/api/v1/bpmn-instances/{inst['id']}/{ruta}", headers=auth(pm_token)).status_code == 404
    assert client.post(f"/api/v1/bpmn-instances/{inst['id']}/migrate", headers=auth(pm_token),
                       json={"version": 1}).status_code == 404
    assert inst["id"] not in [i["id"] for i in client.get("/api/v1/bpmn-instances", headers=auth(pm_token)).json()["items"]]


def test_el_subcontratista_no_usa_bpm(client, pm_token, sub_token, db):
    assert client.get("/api/v1/bpmn-instances/metrics", headers=auth(sub_token)).status_code == 403
    assert client.get("/api/v1/bpmn-instances/inbox", headers=auth(sub_token)).status_code == 403


# ── GRC: auditoría, métricas, retención y RGPD ────────────────────────────

def test_publicar_retirar_iniciar_y_cancelar_quedan_en_la_auditoria(client, pm_token, db):
    from app.models.enterprise import AuditLog
    pid = _proceso(client, pm_token, LINEAL)
    client.post(f"/api/v1/bpmn-processes/{pid}/versions/1/publish", headers=auth(pm_token))
    inst = _arrancar(client, pm_token, pid).json()["data"]
    client.post(f"/api/v1/bpmn-instances/{inst['id']}/cancel", headers=auth(pm_token))
    client.post(f"/api/v1/bpmn-processes/{pid}/versions/1/retire", headers=auth(pm_token))
    acciones = {a for (a,) in db.query(AuditLog.action).filter(AuditLog.resource_id.in_([pid, inst["id"]])).all()}
    assert {"PUBLISH", "RETIRE", "CREATE", "CANCEL"} <= acciones


def test_las_metricas_cuentan_atascadas_y_fuera_de_plazo(client, pm_token, db):
    pid = _proceso(client, pm_token, BORDE)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    paso = db.query(BPMNInstanceStep).filter(BPMNInstanceStep.instance_id == inst["id"],
                                             BPMNInstanceStep.element_id == "T").one()
    paso.sla_due_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    m = client.get("/api/v1/bpmn-instances/metrics", headers=auth(pm_token), params={"process_id": pid}).json()["data"]
    assert m["overdue_tasks"] == 1 and m["stuck_count"] == 1 and m["stuck"][0]["reason"] == "overdue"


def test_la_retencion_conoce_las_instancias_terminadas():
    from app.db.bloqueo_legal import TIPOS
    assert "bpmn_instances" in TIPOS and "started_by_user_id" in TIPOS["bpmn_instances"].campos


def test_rgpd_copia_y_supresion_de_variables_personales(client, pm_token, db):
    from app.models.user import User
    from app.services import bpmn_gobierno
    pm = db.query(User).filter(User.role == "pm").first()
    pid = _proceso(client, pm_token, LINEAL, variables_schema=[{"name": "dni", "type": "string", "personal": True}])
    inst = _arrancar(client, pm_token, pid, {"dni": "12345678Z", "contacto": pm.email, "importe": 3}).json()["data"]
    copia = bpmn_gobierno.copia(db, pm.id)
    assert any(i["variables"].get("dni") == "12345678Z" for i in copia["bpm_instances"])
    informe = bpmn_gobierno.suprimir(db, pm)
    db.commit()
    v = motor._variables(db.query(BPMNInstance).filter(BPMNInstance.id == inst["id"]).one())
    assert v["dni"] == bpmn_gobierno.SUPRIMIDO and v["contacto"] == bpmn_gobierno.SUPRIMIDO and v["importe"] == 3
    assert informe["instances"] >= 1
