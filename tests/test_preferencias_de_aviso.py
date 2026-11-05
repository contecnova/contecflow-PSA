"""Preferencias de aviso por tipo y canal (revisión 2026-11): antes no había
ninguna; cada aviso llegaba a todos, por la aplicación y, si tocaba, por correo."""
from __future__ import annotations

from app.models.enterprise import Notification
from tests.conftest import auth
from tests.test_approvals import add_step, create_workflow


def _apagar(client, token, tipo, **canales):
    r = client.put("/api/v1/users/me/notification-preferences", headers=auth(token),
                   json={"preferences": {tipo: canales}})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_por_defecto_todo_activado(client, pm_token):
    data = client.get("/api/v1/users/me/notification-preferences", headers=auth(pm_token)).json()["data"]
    assert all(v["app"] and v["email"] for v in data["preferences"].values())
    canales = {t["type"]: t["channels"] for t in data["types"]}
    assert canales["approval_requested"] == ["app", "email"] and canales["task_assigned"] == ["app"]


def test_EL_HALLAZGO_un_aviso_apagado_no_se_crea_por_ninguna_via(client, pm_token, db):
    from app.services.notifications import notify_user
    _apagar(client, pm_token, "task_assigned", app=False)
    db.info.pop("_preferencias_de_aviso", None)
    assert notify_user(db, "pm-test-id", "task_assigned", "x", "y") is None
    db.add(Notification(user_id="pm-test-id", type="task_assigned", title="directo", body="m"))
    db.add(Notification(user_id="pm-test-id", type="task_overdue", title="otro tipo", body="m"))
    db.commit()
    titulos = [n.title for n in db.query(Notification).filter(Notification.user_id == "pm-test-id")]
    assert titulos == ["otro tipo"]


def test_EL_HALLAZGO_sin_correo_de_aprobacion_si_se_apaga(client, admin_token, pm_token, db, monkeypatch):
    enviados = []
    monkeypatch.setattr("app.services.notification_service.send_email_notification",
                        lambda to, subject, body: enviados.append(to) or True)
    _apagar(client, admin_token, "approval_requested", app=True, email=False)
    wf = create_workflow(client, admin_token)
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")
    r = client.post("/api/v1/approvals/requests", headers=auth(pm_token), json={
        "entity_type": "expense", "entity_id": "e-1", "entity_summary": "Gasto", "context": {}})
    assert r.status_code in (200, 201), r.text
    assert "admin@contecflow.com" not in enviados
    rid = r.json()["data"]["id"]
    assert db.query(Notification).filter(Notification.resource_id == rid, Notification.user_id == "admin-test-id").count() == 1


def test_tipos_desconocidos_se_ignoran(client, pm_token):
    data = _apagar(client, pm_token, "no_existe", app=False)
    assert "no_existe" not in data["preferences"]
