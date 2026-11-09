"""BPM: el responsable y el SLA de «Nuevo proceso» se guardan (revisión 2026-11).

Medido antes: el formulario los pedía y no se enviaban; `bpmn_processes` no tenía
columnas para ellos y se perdían al recargar.
"""
from tests.conftest import auth


def test_EL_HALLAZGO_responsable_y_sla_vuelven_al_recargar(client, admin_token):
    r = client.post("/api/v1/bpmn-processes", headers=auth(admin_token),
                    json={"name": "Alta de proveedor", "category": "finanzas", "owner": "Compras", "sla": "3 días hábiles"})
    assert r.status_code == 200, r.text
    pid = r.json()["data"]["id"]
    d = client.get(f"/api/v1/bpmn-processes/{pid}", headers=auth(admin_token)).json()["data"]
    assert (d["owner"], d["sla"]) == ("Compras", "3 días hábiles")
    d = client.patch(f"/api/v1/bpmn-processes/{pid}", headers=auth(admin_token), json={"sla": "2 días"}).json()["data"]
    assert (d["owner"], d["sla"]) == ("Compras", "2 días")
