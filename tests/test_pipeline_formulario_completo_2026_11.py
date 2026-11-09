"""Pipeline: la oportunidad lleva cliente, tarifa y tipo de contrato (revisión 2026-11).

Medido antes: ni el formulario ni la API los aceptaban (OpportunityIn no tenía
client_id, hourly_rate ni contract_type), así que un proyecto convertido salía
sin cliente ni tarifa, y sólo se podía cambiar la etapa.
"""
from __future__ import annotations

from app.models.clients import Client
from app.models.project import Project
from tests.conftest import auth

URL = "/api/v1/pipeline"


def test_EL_HALLAZGO_cliente_tarifa_y_contrato_llegan_al_proyecto(client, db, admin_token):
    db.add(Client(id="cli-pipe", name="Acme Industrial", organization_id="1"))
    db.commit()
    r = client.post(URL, headers=auth(admin_token), json={
        "name": "ERP", "client_name": "lo que sea", "client_id": "cli-pipe", "hourly_rate": 85,
        "contract_type": "time_material", "expected_start_date": "2026-12-01", "expected_duration_weeks": 12})
    assert r.status_code == 200, r.text
    o = r.json()["data"]
    assert (o["client_name"], o["hourly_rate"], o["contract_type"]) == ("Acme Industrial", 85, "time_material")
    assert client.post(URL, headers=auth(admin_token), json={"name": "X", "client_name": "Y",
                                                               "client_id": "no-existe"}).status_code == 400
    assert client.post(URL, headers=auth(admin_token), json={"name": "X", "client_name": "Y",
                                                               "contract_type": "inventado"}).status_code == 422
    d = client.patch(f"{URL}/{o['id']}", headers=auth(admin_token), json={"hourly_rate": 90, "name": "ERP fase 1"}).json()["data"]
    assert (d["hourly_rate"], d["name"], d["client_id"]) == (90, "ERP fase 1", "cli-pipe")
    r = client.post(f"{URL}/{o['id']}/convert", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    db.expire_all()
    p = db.query(Project).filter(Project.id == db.get(__import__("app.models.pipeline", fromlist=["Opportunity"]).Opportunity, o["id"]).project_id).one()
    assert (p.client_id, p.billing_rate) == ("cli-pipe", 90)
