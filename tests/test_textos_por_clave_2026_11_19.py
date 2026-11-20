"""Textos guardados por clave y planes de cambio antiguos (19-11-2026, migración 192).

- `sd_ticket_history.new_value` y `resolution_note` del agente autónomo
  guardan además clave y datos; al leer se pintan en el idioma de quien mira y
  el texto guardado queda de respaldo (filas de antes, clave desconocida).
- Los planes de cambio guardados antes de las claves (sin `_textos`) se
  traducen al leer con el servicio de traducción si está activo; si no, salen
  tal cual. En los dos casos llevan `textos_anteriores` para regenerarlos.
- El detalle del cambio trae nombre, código y tipo de cada CI afectado.
"""
from __future__ import annotations

import json

import pytest

from app.services.textos_de_salida import texto
from app.services.textos_guardados import diferido, en_idioma, pintar, por_clave


# ── Textos guardados por clave ──────────────────────────────────────────────

def test_pinta_en_el_idioma_de_quien_mira():
    clave, datos = por_clave("historial.posible_duplicado", numero="TK-12")
    assert json.loads(datos) == {"numero": "TK-12"}
    assert pintar(clave, datos, "Possible duplicate of TK-12", "es") == "Posible duplicado de TK-12"
    assert pintar(clave, datos, "x", "zh") == texto("historial.posible_duplicado", "zh", numero="TK-12")


def test_sin_clave_o_desconocida_sale_el_texto_guardado():
    assert pintar(None, None, "texto de antes", "en") == "texto de antes"
    assert pintar("no.existe", None, "texto de antes", "en") == "texto de antes"
    assert pintar("historial.posible_duplicado", "{malo", "respaldo", "en") == "respaldo"
    assert pintar("historial.posible_duplicado", "[1]", "respaldo", "en") == "respaldo"


def test_un_dato_por_clave_se_pinta_en_el_mismo_idioma():
    datos = {"confianza": "90%", "playbook": diferido("autonomo.pb.pw-reset")}
    es = en_idioma("autonomo.motivo.alta", "es", **datos)
    en = en_idioma("autonomo.motivo.alta", "en", **datos)
    assert texto("autonomo.pb.pw-reset", "es") in es
    assert texto("autonomo.pb.pw-reset", "en") in en
    assert es != en


def test_las_claves_nuevas_estan_en_los_tres_idiomas():
    from app.services.textos_de_salida import TEXTOS
    for clave in ("historial.autorresuelto_kb", "historial.posible_duplicado", "historial.aprovisionado",
                  "historial.reabierto_tras_autorresolucion"):
        assert set(TEXTOS[clave]) >= {"es", "en", "zh"}, clave


# ── Agente autónomo ─────────────────────────────────────────────────────────

def test_nombre_del_playbook_de_serie_por_clave_y_el_propio_tal_cual():
    from app.services.service_desk.autonomous_agent_service import _BUILTIN_PLAYBOOKS, nombre_diferido
    de_serie = _BUILTIN_PLAYBOOKS[0]
    assert nombre_diferido(de_serie) == diferido(f"autonomo.pb.{de_serie['id']}")
    assert nombre_diferido({"id": "propio-1", "name": "Mi playbook"}) == "Mi playbook"
    assert nombre_diferido(None) == diferido("autonomo.agente")


def test_el_registro_del_agente_se_lee_en_el_idioma_de_quien_mira(db):
    from app.models.service_desk import AutonomousPlaybookExecution, Ticket
    from app.services.service_desk.autonomous_agent_service import get_execution_log
    ticket = db.query(Ticket).filter(Ticket.organization_id == "1").first()
    if ticket is None:
        pytest.skip("el escenario de pruebas no tiene tickets en la empresa 1")
    clave, datos = por_clave("autonomo.motivo.media", confianza="70%")
    db.add(AutonomousPlaybookExecution(organization_id="1", ticket_id=ticket.id, playbook_type="x",
                                       status="skipped", resolution_note="Confianza media (70%): …",
                                       resolution_note_key=clave, resolution_note_params=datos))
    db.add(AutonomousPlaybookExecution(organization_id="1", ticket_id=ticket.id, playbook_type="y",
                                       status="skipped", resolution_note="nota de antes"))
    db.commit()
    items = get_execution_log(db, org_id="1", ticket_id=ticket.id, idioma="en")["items"]
    notas = {i["playbook_type"]: i["resolution_note"] for i in items}
    assert notas["x"] == texto("autonomo.motivo.media", "en", confianza="70%")
    assert notas["y"] == "nota de antes"


# ── Historial del ticket ────────────────────────────────────────────────────

def test_pintar_historial_traduce_y_no_saca_las_columnas_internas():
    from app.services.service_desk.ticket_read_service import pintar_historial
    clave, datos = por_clave("historial.posible_duplicado", numero="TK-9")
    payload = {"history": [
        {"field": "deduplication", "new_value": "Possible duplicate of TK-9",
         "new_value_key": clave, "new_value_params": datos},
        {"field": "status", "new_value": "resolved", "new_value_key": None, "new_value_params": None},
    ]}
    pintar_historial(payload, "es")
    assert payload["history"][0]["new_value"] == "Posible duplicado de TK-9"
    assert payload["history"][1]["new_value"] == "resolved"
    assert all("new_value_key" not in h and "new_value_params" not in h for h in payload["history"])


def test_ticket_out_lleva_la_clave_del_historial():
    """`ticket_out` pasa la clave y los datos; el detalle los pinta y los quita."""
    import inspect

    from app.services.sla_service import ticket_out
    fuente = inspect.getsource(ticket_out)
    assert '"new_value_key": getattr(h, "new_value_key", None)' in fuente
    assert '"new_value_params": getattr(h, "new_value_params", None)' in fuente


# ── Planes de cambio guardados antes de las claves ──────────────────────────

PLAN_ANTIGUO = {
    "change_id": "c", "rollback_steps": [
        {"step": 1, "action": "Detener el despliegue si está en curso", "responsible": "Gestor del cambio",
         "estimated_minutes": 5},
    ],
}


def test_un_plan_con_claves_no_es_anterior():
    from app.services.service_desk.change_impact_service.textos import con_textos, tiene_textos
    nuevo = {"rollback_steps": [con_textos({"step": 1}, "es", action=diferido("cambio.vuelta.1"))]}
    assert tiene_textos(nuevo)
    assert not tiene_textos(json.loads(json.dumps(PLAN_ANTIGUO)))


def test_plan_anterior_sin_empresa_sale_tal_cual_y_regenerable(db):
    from app.services.service_desk.change_impact_service.textos import traducir_anterior
    plan = traducir_anterior(db, json.loads(json.dumps(PLAN_ANTIGUO)), "en", None)
    assert plan["rollback_steps"][0]["action"] == "Detener el despliegue si está en curso"
    assert plan["textos_anteriores"] == {"status": "not_translated", "reason": None, "regenerable": True}


def test_plan_anterior_se_traduce_con_el_servicio_si_esta_activo(db, monkeypatch):
    from app.services.service_desk.change_impact_service import textos as mod
    from app.services.traduccion import servicio

    vistos = {}

    def falso(db_, org_id, textos, destino, *, canal, user_id=None, **_):
        vistos.update(org=org_id, canal=canal, destino=destino, textos=list(textos))
        return [servicio.Resultado(servicio.TRADUCIDO, destino, f"[{destino}] {t}") for t in textos]

    monkeypatch.setattr(servicio, "traducir", falso)
    plan = mod.traducir_anterior(db, json.loads(json.dumps(PLAN_ANTIGUO)), "en", "1", "u")
    paso = plan["rollback_steps"][0]
    assert paso["action"] == "[en] Detener el despliegue si está en curso"
    assert paso["responsible"] == "[en] Gestor del cambio"
    assert paso["estimated_minutes"] == 5  # los números y códigos no se tocan
    assert vistos["canal"] == "ticket" and vistos["org"] == "1"
    assert plan["textos_anteriores"]["status"] == "translated"


def test_plan_anterior_con_la_traduccion_desactivada(db, monkeypatch):
    from app.services.service_desk.change_impact_service import textos as mod
    from app.services.traduccion import servicio
    monkeypatch.setattr(servicio, "traducir", lambda db_, org, textos, destino, **k: [
        servicio.Resultado(servicio.DESACTIVADA, destino, motivo="disabled") for _ in textos])
    plan = mod.traducir_anterior(db, json.loads(json.dumps(PLAN_ANTIGUO)), "en", "1")
    assert plan["rollback_steps"][0]["action"] == "Detener el despliegue si está en curso"
    assert plan["textos_anteriores"]["status"] == "disabled"
    assert plan["textos_anteriores"]["reason"] == "disabled"


def test_plan_anterior_si_el_servicio_falla_sale_tal_cual(db, monkeypatch):
    from app.services.service_desk.change_impact_service import textos as mod
    from app.services.traduccion import servicio

    def roto(*a, **k):
        raise RuntimeError("caido")

    monkeypatch.setattr(servicio, "traducir", roto)
    plan = mod.traducir_anterior(db, json.loads(json.dumps(PLAN_ANTIGUO)), "en", "1")
    assert plan["rollback_steps"][0]["action"] == "Detener el despliegue si está en curso"
    assert plan["textos_anteriores"]["status"] == "unavailable"


# ── CIs afectados con nombre ────────────────────────────────────────────────

def test_el_detalle_del_cambio_trae_nombre_y_tipo_de_los_cis(db):
    from app.models.service_desk import ConfigurationItem, ITSMChangeRequest
    from app.models.service_desk._enums import CIType
    from app.services.service_desk.change_service import serialize_change
    ci = ConfigurationItem(code="CI-CIERRE", name="ERP producción", ci_type=CIType.server, organization_id="1")
    db.add(ci)
    db.flush()
    c = ITSMChangeRequest(id="chg-cis-cierre", number="CHG-CIS1", title="T", description="x",
                          status="submitted", organization_id="1",
                          affected_cis=json.dumps([ci.id, "ya-no-existe"]))
    db.add(c)
    db.commit()
    detalles = serialize_change(c, full=True)["affected_ci_details"]
    assert detalles[0] == {"id": ci.id, "name": "ERP producción", "code": "CI-CIERRE", "ci_type": "server"}
    assert detalles[1] == {"id": "ya-no-existe", "name": None, "code": None, "ci_type": None}
    assert "affected_ci_details" not in serialize_change(c)  # solo en el detalle
