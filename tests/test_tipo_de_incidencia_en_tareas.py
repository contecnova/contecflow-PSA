"""El tipo de incidencia del catalogo /issue-types llega a las tareas.

Auditoria 2026-11: `tasks.issue_type` existia y ningun esquema lo exponia; el
catalogo por proyecto no servia para nada al crear o editar una tarea.
"""
from tests.conftest import auth


def _proyecto(client, token):
    r = client.post("/api/v1/projects", headers=auth(token),
                    json={"name": "Tipos", "code": "ITY1", "status": "active", "billing_type": "time_material"})
    return r.json()["data"]["id"]


def test_EL_HALLAZGO_la_tarea_guarda_y_devuelve_su_tipo(client, pm_token, db):
    pid = _proyecto(client, pm_token)
    r = client.post("/api/v1/tasks", headers=auth(pm_token),
                    json={"title": "Fallo", "project_id": pid, "issue_type": "bug"})
    assert r.status_code in (200, 201), r.text
    assert r.json()["data"]["issue_type"] == "bug"
    tid = r.json()["data"]["id"]
    r = client.patch(f"/api/v1/tasks/{tid}", json={"issue_type": "story"}, headers=auth(pm_token))
    assert r.status_code == 200 and r.json()["data"]["issue_type"] == "story"


def test_un_tipo_que_no_esta_en_el_catalogo_del_proyecto_no_se_guarda(client, pm_token, db):
    pid = _proyecto(client, pm_token)
    r = client.post(f"/api/v1/issue-types/{pid}", headers=auth(pm_token),
                    json={"name": "Incidente", "value": "incidente"})
    assert r.status_code in (200, 201), r.text
    ok = client.post("/api/v1/tasks", headers=auth(pm_token),
                     json={"title": "A", "project_id": pid, "issue_type": "incidente"})
    assert ok.status_code in (200, 201), ok.text
    # Con catalogo propio, los de sistema que no estan dejan de valer.
    malo = client.post("/api/v1/tasks", headers=auth(pm_token),
                       json={"title": "B", "project_id": pid, "issue_type": "spike"})
    assert malo.status_code == 422
