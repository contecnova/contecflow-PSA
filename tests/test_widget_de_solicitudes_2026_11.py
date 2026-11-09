"""Widget de solicitudes para la web de un cliente (revisión 2026-11).

Medido antes: `/widget/ticket.js` pedía `data-client-token`, el token del portal
de un cliente puesto en una página pública; y salía con
`Cross-Origin-Resource-Policy: same-origin`. Ahora va con el token de un
formulario público. Medido en el navegador desde otro origen: el formulario se
pinta en el idioma de la empresa, se envía y crea el ticket.
"""
from __future__ import annotations

from tests.conftest import auth


def _formulario(client, token):
    r = client.post("/api/v1/forms", headers=auth(token), json={"name": "Soporte web", "form_type": "ticket"})
    assert r.status_code == 201, r.text
    return r.json()["data"]["token"]


def test_EL_HALLAZGO_el_widget_ya_no_pide_el_token_del_portal(client):
    r = client.get("/widget/ticket.js")
    assert "data-client-token" not in r.text and "data-form" in r.text
    assert r.headers["cross-origin-resource-policy"] == "cross-origin"
    assert "charset=utf-8" in r.headers["content-type"]
    assert "\\u00f3" in r.text                       # textos escapados: a salvo de la codificación de la web


def test_las_rutas_publicas_del_formulario_admiten_cualquier_origen(client, pm_token):
    tok = _formulario(client, pm_token)
    otra = {"Origin": "https://web-del-cliente.example"}
    previa = client.options(f"/api/v1/forms/public/{tok}/submit",
                            headers={**otra, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
    assert previa.status_code == 204 and previa.headers["access-control-allow-origin"] == "*"
    g = client.get(f"/api/v1/forms/public/{tok}", headers=otra)
    assert g.headers["access-control-allow-origin"] == "*" and g.json()["idioma"] in {"es", "en", "zh"}
    e = client.post(f"/api/v1/forms/public/{tok}/submit", headers=otra, json={"subject": "No puedo entrar"})
    assert e.status_code == 201 and e.headers["access-control-allow-origin"] == "*" and e.json()["ticket_id"]


def test_EL_HALLAZGO_el_resto_de_la_api_no_se_abre(client):
    previa = client.options("/api/v1/projects", headers={"Origin": "https://web-del-cliente.example",
                                                          "Access-Control-Request-Method": "POST"})
    assert previa.status_code == 400 and previa.headers.get("access-control-allow-origin") != "*"


def test_EL_HALLAZGO_el_ticket_es_de_la_empresa_del_formulario(client, db, pm_token):
    """Medido: se creaba con organization_id vacío y ninguna empresa lo veía."""
    from app.models.public_forms import PublicForm
    from app.models.service_desk import Ticket
    tok = _formulario(client, pm_token)
    tid = client.post(f"/api/v1/forms/public/{tok}/submit", json={"subject": "Hola"}).json()["ticket_id"]
    db.expire_all()
    form = db.query(PublicForm).filter(PublicForm.token == tok).one()
    assert db.get(Ticket, tid).organization_id == form.organization_id is not None


def test_un_formulario_de_tareas_crea_la_tarea_en_su_proyecto(client, db, pm_token, monkeypatch):
    from app.models.project import Project, ProjectStatus, ProjectType
    from app.models.task import Task
    from app.services import notification_service
    enviados = []
    monkeypatch.setattr(notification_service, "send_email_notification", lambda to, asunto, cuerpo: enviados.append((to, asunto)) or True)
    db.add(Project(id="p-form", code="P-FORM", name="Web", status=ProjectStatus.active,
                   project_type=ProjectType.development, organization_id="1"))
    db.commit()
    assert client.post("/api/v1/forms", headers=auth(pm_token), json={"name": "Peticiones", "form_type": "task"}).status_code == 400
    r = client.post("/api/v1/forms", headers=auth(pm_token), json={
        "name": "Peticiones", "form_type": "task", "target_project_id": "p-form", "notify_emails": ["pm@empresa.example"]})
    tok = r.json()["data"]["token"]
    res = client.post(f"/api/v1/forms/public/{tok}/submit", json={"subject": "Cambiar el logo", "submitter_name": "Ana"}).json()
    tarea = db.get(Task, res["ticket_id"])
    assert (tarea.project_id, tarea.title) == ("p-form", "Cambiar el logo") and "Ana" in tarea.description
    assert enviados == [("pm@empresa.example", "[Peticiones] Cambiar el logo")]
