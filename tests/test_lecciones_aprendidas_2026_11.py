"""Lecciones aprendidas: hechos medidos, recomendaciones explicadas y si sirvieron (revisión 2026-11)."""
from __future__ import annotations

import json
import uuid
from datetime import date

import pytest

from app.models.imputation import Imputation
from app.models.lecciones import Leccion
from app.models.pipeline import Risk, RiskImpact, RiskProbability, RiskStatus
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.service_desk.tickets import Ticket
from app.models.user import User
from app.services import settings_service
from tests.conftest import auth

URL = "/api/v1/lessons"


def _ajuste(db, clave, valor):
    settings_service.set_runtime_value(db, "lecciones", clave, valor, "1")
    db.commit()
    settings_service.invalidate_cache()


@pytest.fixture
def cerrado(db):
    """Proyecto cerrado con 10 días de retraso, 30 % más de horas y un riesgo materializado."""
    pm = db.query(User).filter(User.username == "pm_test").one()
    from app.models.clients import Client
    db.add(Client(id="cli-l", name="Acme Lecciones", organization_id="1"))
    p = Project(id="p-l", code="PRJ-L1", name="Migración ERP Acme", status=ProjectStatus.closed,
                project_type=ProjectType.development, organization_id="1", client_id="cli-l", tags="erp,migracion",
                budget_hours=100, budget_amount=5000, end_date_planned=date(2026, 9, 30),
                end_date_real=date(2026, 10, 10), pm_id=pm.id)
    db.add(p)
    db.add(Imputation(id=str(uuid.uuid4()), user_id=pm.id, project_id=p.id, date=date(2026, 9, 1), hours=130,
                      cost_amount=6500, organization_id="1", description="x"))
    db.add(Risk(code="RSK-1", project_id=p.id, title="Datos maestros sucios", probability=RiskProbability.high,
                impact=RiskImpact.major, status=RiskStatus.materialized, organization_id="1"))
    db.commit()
    return p


def _hecho(hechos, etiqueta):
    return next(h["valor"] for h in hechos if h["etiqueta"] == etiqueta)


def _crear(client, token, **extra):
    cuerpo = {"titulo": "Limpiar datos maestros antes de migrar", "categoria": "planificacion", "tipo": "evitar",
              "que_paso": "La carga falló por datos duplicados", "recomendacion": "Haz una limpieza de datos en la fase 0",
              **extra}
    r = client.post(URL, headers=auth(token), json=cuerpo)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_EL_HALLAZGO_los_hechos_del_proyecto_se_miden_y_se_guardan_con_la_leccion(client, db, cerrado, pm_token):
    _ajuste(db, "LESSONS_AI_DRAFT_ENABLED", False)
    b = client.get(f"{URL}/borrador/project/p-l", headers=auth(pm_token)).json()["data"]
    h = b["hechos"]
    assert _hecho(h, "Desvío de plazo (días)") == 10
    assert (_hecho(h, "Horas imputadas"), _hecho(h, "Desvío de horas (%)")) == (130.0, 30.0)
    assert (_hecho(h, "Coste imputado"), _hecho(h, "Desvío de coste (%)")) == (6500.0, 30.0)
    assert _hecho(h, "Riesgos materializados") == ["Datos maestros sucios"]
    assert b["ia"] is False and "LESSONS_AI_DRAFT_ENABLED" in b["aviso"]
    l = _crear(client, pm_token, origen_tipo="project", origen_id="p-l")
    assert l["codigo"].startswith("LEC-") and l["origen_ref"] == "PRJ-L1"
    assert (l["cliente_id"], l["tipo_proyecto"], l["etiquetas"]) == ("cli-l", "development", "erp,migracion")
    assert _hecho(l["hechos"], "Desvío de plazo (días)") == 10


def test_el_borrador_de_la_ia_se_ciñe_a_las_categorias_y_sin_ia_lo_dice(client, db, cerrado, pm_token, monkeypatch):
    respuesta = {"titulo": "Datos maestros", "tipo": "evitar", "categoria": "inventada", "severidad": "alta",
                 "que_paso": "Retraso de 10 días", "recomendacion": "Limpia los datos antes", "etiquetas": ["datos"]}
    monkeypatch.setattr("app.services.ai_provider_service.call_ai", lambda *a, **k: "```json\n" + json.dumps(respuesta) + "\n```")
    b = client.get(f"{URL}/borrador/project/p-l", headers=auth(pm_token)).json()["data"]
    assert b["ia"] is True and b["propuesta"]["severidad"] == "alta"
    assert b["propuesta"]["categoria"] == "alcance"          # la inventada no entra: queda la primera de Admin
    assert b["propuesta"]["etiquetas"] == "datos,erp,migracion"

    def falla(*a, **k):
        raise RuntimeError("presupuesto agotado")
    monkeypatch.setattr("app.services.ai_provider_service.call_ai", falla)
    b = client.get(f"{URL}/borrador/project/p-l", headers=auth(pm_token)).json()["data"]
    assert b["ia"] is False and "presupuesto agotado" in b["aviso"] and b["hechos"]


def test_el_origen_se_abre_con_su_control_de_acceso(client, db, dev_token):
    db.add(Ticket(id="t-l", number="INC-L1", ticket_type="incident", title="Caída VPN", description="x",
                  organization_id="1"))
    db.commit()
    assert client.get(f"{URL}/borrador/ticket/t-l", headers=auth(dev_token)).status_code == 404
    r = client.post(URL, headers=auth(dev_token), json={"titulo": "x", "categoria": "tecnica", "que_paso": "x",
                                                        "recomendacion": "x", "origen_tipo": "ticket", "origen_id": "t-l"})
    assert r.status_code == 404 and db.query(Leccion).count() == 0


def test_EL_HALLAZGO_recomienda_lo_parecido_y_dice_por_que(client, db, cerrado, pm_token, admin_token):
    buena = _crear(client, pm_token, origen_tipo="project", origen_id="p-l")
    otra = _crear(client, pm_token, titulo="Reuniones semanales con el cliente", categoria="comunicacion",
                  que_paso="El cliente se enteró tarde", recomendacion="Agenda una reunión semanal")
    for l in (buena, otra):
        client.post(f"{URL}/{l['id']}/estado", headers=auth(admin_token), json={"estado": "validada"})
    r = client.post(f"{URL}/recomendaciones/nuevo-proyecto", headers=auth(pm_token), json={
        "nombre": "Migración del ERP de Acme a la nube", "cliente_id": "cli-l", "tipo_proyecto": "development",
        "etiquetas": "erp"}).json()["data"]
    assert r["items"][0]["id"] == buena["id"]
    motivos = {m["clave"] for m in r["items"][0]["motivos"]}
    assert {"mismo_cliente", "mismo_tipo_de_proyecto", "etiquetas"} <= motivos
    assert r["items"][0]["frase"].startswith("Evita: Haz una limpieza de datos en la fase 0 — porque en PRJ-L1 pasó:")
    assert otra["id"] not in [i["id"] for i in r["items"]]      # por debajo del mínimo
    # Al propio proyecto no se le recomienda su lección.
    r = client.get(f"{URL}/recomendaciones/project/p-l", headers=auth(pm_token)).json()["data"]
    assert buena["id"] not in [i["id"] for i in r["items"]]


def test_solo_se_recomiendan_las_validadas_salvo_que_admin_diga_otra_cosa(client, db, cerrado, pm_token):
    _crear(client, pm_token, origen_tipo="project", origen_id="p-l")
    cuerpo = {"cliente_id": "cli-l", "tipo_proyecto": "development", "etiquetas": "erp"}
    assert client.post(f"{URL}/recomendaciones/nuevo-proyecto", headers=auth(pm_token), json=cuerpo).json()["data"]["items"] == []
    _ajuste(db, "LESSONS_ONLY_VALIDATED", False)
    assert len(client.post(f"{URL}/recomendaciones/nuevo-proyecto", headers=auth(pm_token), json=cuerpo).json()["data"]["items"]) == 1


def test_quien_valida_y_quien_edita(client, db, pm_token, dev_token, admin_token):
    l = _crear(client, dev_token)
    assert client.post(f"{URL}/{l['id']}/estado", headers=auth(dev_token), json={"estado": "validada"}).status_code == 403
    assert client.patch(f"{URL}/{l['id']}", headers=auth(dev_token), json={"causa": "Sin limpieza"}).status_code == 200
    assert client.post(f"{URL}/{l['id']}/estado", headers=auth(pm_token), json={"estado": "validada"}).status_code == 200
    assert client.patch(f"{URL}/{l['id']}", headers=auth(dev_token), json={"causa": "otra"}).status_code == 403
    assert client.delete(f"{URL}/{l['id']}", headers=auth(pm_token)).status_code == 403
    assert client.patch(f"{URL}/{l['id']}", headers=auth(pm_token), json={"categoria": "inventada"}).status_code == 400


def test_lo_cerrado_sin_leccion_queda_pendiente_hasta_que_la_tiene(client, db, cerrado, pm_token):
    pend = client.get(f"{URL}/pendientes", headers=auth(pm_token)).json()["data"]["items"]
    assert ("project", "p-l") in {(p["origen_tipo"], p["origen_id"]) for p in pend}
    _crear(client, pm_token, origen_tipo="project", origen_id="p-l")
    pend = client.get(f"{URL}/pendientes", headers=auth(pm_token)).json()["data"]["items"]
    assert ("project", "p-l") not in {(p["origen_tipo"], p["origen_id"]) for p in pend}


def test_la_valoracion_se_cuenta_una_vez_por_persona_y_da_la_efectividad(client, db, cerrado, pm_token, admin_token):
    l = _crear(client, pm_token)
    for valor in ("no_aplica", "util"):          # cambia de opinión: cuenta la última
        client.post(f"{URL}/{l['id']}/valoracion", headers=auth(pm_token),
                    json={"contexto_tipo": "project", "contexto_id": "p-l", "valor": valor})
    client.post(f"{URL}/{l['id']}/valoracion", headers=auth(admin_token),
                json={"contexto_tipo": "project", "contexto_id": "p-l", "valor": "no_aplica"})
    i = client.get(f"{URL}/indicadores", headers=auth(pm_token)).json()["data"]
    assert i["valoraciones"] == {"util": 1, "aplicada": 0, "no_aplica": 1} and i["efectividad_pct"] == 50.0


def test_acciones_de_mejora_con_plazo(client, db, pm_token, dev_token):
    l = _crear(client, pm_token)
    dev = db.query(User).filter(User.username == "dev_test").one()
    a = client.post(f"{URL}/{l['id']}/acciones", headers=auth(pm_token),
                    json={"descripcion": "Plantilla de limpieza de datos", "responsable_id": dev.id,
                          "fecha_limite": "2020-01-01"}).json()["data"]
    assert a["vencida"] is True
    mias = client.get(f"{URL}/acciones", params={"solo_mias": True}, headers=auth(dev_token)).json()["data"]["items"]
    assert [x["id"] for x in mias] == [a["id"]]
    r = client.patch(f"{URL}/acciones/{a['id']}", headers=auth(dev_token), json={"estado": "hecha", "resultado": "Lista"})
    assert r.json()["data"]["cerrada_en"] and r.json()["data"]["vencida"] is False
