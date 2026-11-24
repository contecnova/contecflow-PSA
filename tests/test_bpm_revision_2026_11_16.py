"""Revisión BPM (16-11-2026): lo que se arregló, medido.

Cada test nombra el hallazgo. Ver DOCS.md, «Revisión BPM (16-11-2026)».
"""
from __future__ import annotations

import pytest

from app.models.bpmn_process import BPMNInstance, BPMNProcess, BPMNProcessVersion
from app.services import bpmn_engine as motor
from tests.conftest import auth

_CAB = ('<?xml version="1.0" encoding="UTF-8"?><bpmn:definitions '
        'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="D" targetNamespace="x">')

# Como los del catálogo del frontend (generadorBpmn.ts): compuerta exclusiva con
# salidas etiquetadas y sin condiciones. El editor no deja escribir condiciones.
DECISION = _CAB + """
<bpmn:process id="P" isExecutable="false">
  <bpmn:laneSet><bpmn:lane id="L" name="Project Manager"><bpmn:flowNodeRef>G</bpmn:flowNodeRef></bpmn:lane></bpmn:laneSet>
  <bpmn:startEvent id="S"/>
  <bpmn:exclusiveGateway id="G" name="¿Se aprueba?"/>
  <bpmn:userTask id="Alta" name="Dar de alta"/>
  <bpmn:endEvent id="E_ok"/>
  <bpmn:endEvent id="E_no" name="Rechazada"/>
  <bpmn:sequenceFlow id="f1" sourceRef="S" targetRef="G"/>
  <bpmn:sequenceFlow id="si" name="Sí" sourceRef="G" targetRef="Alta"/>
  <bpmn:sequenceFlow id="no" sourceRef="G" targetRef="E_no"/>
  <bpmn:sequenceFlow id="f2" sourceRef="Alta" targetRef="E_ok"/>
</bpmn:process></bpmn:definitions>"""

NO_EJECUTABLE = _CAB + """<bpmn:process id="P"><bpmn:startEvent id="S"/>
  <bpmn:complexGateway id="Sub" name="Sub"/>
  <bpmn:sequenceFlow id="a" sourceRef="S" targetRef="Sub"/></bpmn:process></bpmn:definitions>"""

SIN_RUTA = _CAB + """<bpmn:process id="P"><bpmn:startEvent id="S"/>
  <bpmn:exclusiveGateway id="G" name="Importe"/>
  <bpmn:endEvent id="A"/><bpmn:endEvent id="B"/>
  <bpmn:sequenceFlow id="f" sourceRef="S" targetRef="G"/>
  <bpmn:sequenceFlow id="x" sourceRef="G" targetRef="A"><bpmn:conditionExpression>importe &gt; 10</bpmn:conditionExpression></bpmn:sequenceFlow>
  <bpmn:sequenceFlow id="y" sourceRef="G" targetRef="B"><bpmn:conditionExpression>importe &lt; 5</bpmn:conditionExpression></bpmn:sequenceFlow>
</bpmn:process></bpmn:definitions>"""


def _proceso(client, token, xml, nombre="Proceso", **extra):
    r = client.post("/api/v1/bpmn-processes", headers=auth(token),
                    json={"name": nombre, "category": "admin", "bpmn_xml": xml, **extra})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _arrancar(client, token, pid, variables=None):
    return client.post(f"/api/v1/bpmn-processes/{pid}/instances", headers=auth(token),
                       json={"variables": variables or {}})


# ── Decisiones manuales ─────────────────────────────────────────────────────

def test_EL_HALLAZGO_la_compuerta_sin_condiciones_es_una_decision_y_no_un_fallo(client, pm_token, db):
    """Antes: «Ninguna condición se cumple» y la instancia fallaba siempre."""
    pid = _proceso(client, pm_token, DECISION)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    assert inst["status"] == "running" and inst["active_steps"] == ["¿Se aprueba?"]

    bandeja = client.get("/api/v1/bpmn-instances/inbox", headers=auth(pm_token)).json()["items"]
    assert len(bandeja) == 1
    paso = bandeja[0]
    assert paso["wait_kind"] == "decision" and paso["human"] is True and paso["candidate_role"] == "pm"
    assert [(o["flow_id"], o["name"]) for o in paso["options"]] == [("si", "Sí"), ("no", "Rechazada")]

    url = f"/api/v1/bpmn-instances/{inst['id']}/steps/{paso['id']}/complete"
    assert client.post(url, headers=auth(pm_token), json={}).status_code == 422
    assert client.post(url, headers=auth(pm_token), json={"flow_id": "f1"}).status_code == 422
    fin = client.post(url, headers=auth(pm_token), json={"flow_id": "no"}).json()["data"]
    assert fin["status"] == "completed"
    assert [s["element_id"] for s in fin["steps"]] == ["S", "G", "E_no"]
    # 23-11-2026 (decisiones de elección múltiple, test_bpm_profesional_2026_11_23):
    # el paso anota la LISTA de salidas elegidas, también cuando es una sola.
    assert fin["steps"][1]["result"] == {"flow_ids": ["no"]}


def test_la_decision_de_la_calle_pm_no_la_toma_un_empleado(client, pm_token, dev_token, db):
    pid = _proceso(client, pm_token, DECISION)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    paso = next(s for s in inst["steps"] if s["status"] == "active")
    assert client.get("/api/v1/bpmn-instances/inbox", headers=auth(dev_token)).json()["items"] == []
    r = client.post(f"/api/v1/bpmn-instances/{inst['id']}/steps/{paso['id']}/complete",
                    headers=auth(dev_token), json={"flow_id": "si"})
    assert r.status_code == 403


# ── Validación con códigos ──────────────────────────────────────────────────

def test_la_validacion_devuelve_problemas_con_codigo(client, pm_token, db):
    pid = _proceso(client, pm_token, NO_EJECUTABLE)
    d = client.get(f"/api/v1/bpmn-processes/{pid}/validation", headers=auth(pm_token)).json()["data"]
    assert d["executable"] is False and d["version"] == 1
    assert [p["code"] for p in d["problems"]] == ["unsupported_element"]
    sub = next(p for p in d["problems"] if p["code"] == "unsupported_element")
    assert (sub["element"], sub["extra"]) == ("Sub", "complexGateway")


def test_el_motor_rechaza_un_xml_con_entidades(db):
    """defusedxml: un DTD con entidades no se expande."""
    xml = '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa">]>' + DECISION.split("?>", 1)[1]
    assert [p.code for p in motor.leer(xml).problemas] == ["invalid_xml"]


def test_EL_HALLAZGO_el_fallo_en_ejecucion_lleva_codigo_traducible(client, pm_token, db):
    pid = _proceso(client, pm_token, SIN_RUTA)
    inst = _arrancar(client, pm_token, pid, {"importe": 7}).json()["data"]
    assert inst["status"] == "failed"
    assert inst["error_code"] == "no_route" and inst["error_params"] == {"element": "Importe"}


# ── Guardar y publicar ──────────────────────────────────────────────────────

@pytest.mark.parametrize("xml", ["esto no es xml", "<a><b/></a>",
                                 '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"/>'])
def test_EL_HALLAZGO_no_se_guarda_un_diagrama_roto(client, pm_token, db, xml):
    """Antes se guardaba y el editor ya no podía abrir el proceso."""
    pid = _proceso(client, pm_token, DECISION)
    r = client.post(f"/api/v1/bpmn-processes/{pid}/versions", headers=auth(pm_token), json={"bpmn_xml": xml})
    assert r.status_code == 422, r.text
    assert db.query(BPMNProcess).filter(BPMNProcess.id == pid).one().latest_version == 1


def test_guardar_una_version_dice_si_es_ejecutable(client, pm_token, db):
    pid = _proceso(client, pm_token, DECISION)
    d = client.post(f"/api/v1/bpmn-processes/{pid}/versions", headers=auth(pm_token),
                    json={"bpmn_xml": NO_EJECUTABLE}).json()["data"]
    assert d["version"] == 2 and d["validation"]["executable"] is False


def test_EL_HALLAZGO_solo_se_publica_lo_ejecutable_y_queda_una_publicada(client, pm_token, db):
    pid = _proceso(client, pm_token, DECISION)
    url = f"/api/v1/bpmn-processes/{pid}"
    client.post(f"{url}/versions", headers=auth(pm_token), json={"bpmn_xml": NO_EJECUTABLE})
    assert client.post(f"{url}/versions/2/publish", headers=auth(pm_token)).status_code == 422
    assert client.post(f"{url}/versions/1/publish", headers=auth(pm_token)).status_code == 200
    client.post(f"{url}/versions", headers=auth(pm_token), json={"bpmn_xml": DECISION})
    assert client.post(f"{url}/versions/3/publish", headers=auth(pm_token)).status_code == 200
    publicadas = [v.version for v in db.query(BPMNProcessVersion)
                  .filter(BPMNProcessVersion.process_id == pid, BPMNProcessVersion.is_published.is_(True))]
    assert publicadas == [3]
    d = client.get(url, headers=auth(pm_token)).json()["data"]
    assert d["published_version"] == 3


def test_el_listado_trae_el_xml_en_una_peticion(client, pm_token, db):
    """Antes: una petición GET /bpmn-processes/{id} por proceso (N+1)."""
    pid = _proceso(client, pm_token, DECISION)
    client.post(f"/api/v1/bpmn-processes/{pid}/versions/1/publish", headers=auth(pm_token))
    items = client.get("/api/v1/bpmn-processes", params={"include_xml": True},
                       headers=auth(pm_token)).json()["items"]
    item = next(i for i in items if i["id"] == pid)
    assert "¿Se aprueba?" in item["latest_xml"] and item["published_version"] == 1
    sin = client.get("/api/v1/bpmn-processes", headers=auth(pm_token)).json()["items"]
    assert "latest_xml" not in next(i for i in sin if i["id"] == pid)


# ── Metadatos, archivado y duplicado ────────────────────────────────────────

def test_EL_HALLAZGO_un_estado_invalido_es_422_y_no_500(client, pm_token, db):
    pid = _proceso(client, pm_token, DECISION)
    r = client.patch(f"/api/v1/bpmn-processes/{pid}", headers=auth(pm_token), json={"status": "inventado"})
    assert r.status_code == 422


def test_un_proceso_archivado_no_arranca(client, pm_token, db):
    pid = _proceso(client, pm_token, DECISION)
    assert client.patch(f"/api/v1/bpmn-processes/{pid}", headers=auth(pm_token),
                        json={"status": "archived"}).status_code == 200
    assert _arrancar(client, pm_token, pid).status_code == 409


def test_EL_HALLAZGO_el_duplicado_es_de_mi_organizacion_y_conserva_responsable(client, pm_token, db):
    pid = _proceso(client, pm_token, DECISION, owner="Compras", sla="2 días")
    origen = db.query(BPMNProcess).filter(BPMNProcess.id == pid).one()
    d = client.post(f"/api/v1/bpmn-processes/{pid}/duplicate", headers=auth(pm_token),
                    json={"new_name": "Copia de compras"}).json()["data"]
    assert d["key"] == "copia_de_compras" and (d["owner"], d["sla"]) == ("Compras", "2 días")
    copia = db.query(BPMNProcess).filter(BPMNProcess.id == d["id"]).one()
    assert copia.organization_id == origen.organization_id is not None


# ── Variables ───────────────────────────────────────────────────────────────

def test_EL_HALLAZGO_las_variables_se_validan(client, pm_token, db, monkeypatch):
    pid = _proceso(client, pm_token, DECISION)
    assert _arrancar(client, pm_token, pid, {"no vale": 1}).status_code == 422
    from app.core.config import settings
    monkeypatch.setattr(settings, "BPMN_MAX_VARIABLES_BYTES", 50)
    assert _arrancar(client, pm_token, pid, {"texto": "x" * 100}).status_code == 413
    assert db.query(BPMNInstance).filter(BPMNInstance.process_id == pid).count() == 0


# ── Permisos ────────────────────────────────────────────────────────────────

def test_EL_HALLAZGO_un_subcontratista_no_lee_los_procesos(client, pm_token, sub_token, db):
    pid = _proceso(client, pm_token, DECISION)
    assert client.get("/api/v1/bpmn-processes", headers=auth(sub_token)).status_code == 403
    assert client.get(f"/api/v1/bpmn-processes/{pid}", headers=auth(sub_token)).status_code == 403
    assert client.get(f"/api/v1/bpmn-processes/{pid}/versions/1", headers=auth(sub_token)).status_code == 403


def test_cancelar_queda_en_la_auditoria(client, pm_token, db):
    from app.models.enterprise import AuditLog
    pid = _proceso(client, pm_token, DECISION)
    inst = _arrancar(client, pm_token, pid).json()["data"]
    assert client.post(f"/api/v1/bpmn-instances/{inst['id']}/cancel", headers=auth(pm_token)).status_code == 200
    filas = db.query(AuditLog).filter(AuditLog.resource == "bpmn_instance", AuditLog.resource_id == inst["id"]).all()
    # 23-11-2026: cada acción con su nombre (antes la cancelación era un UPDATE).
    assert sorted(f.action for f in filas) == ["CANCEL", "CREATE"]
