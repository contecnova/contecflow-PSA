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


# ── Resumen diario (revisión 2026-11) ───────────────────────────────────────

import pytest as _pytest  # noqa: E402


@_pytest.fixture
def correos_resumen(monkeypatch):
    enviados = []
    monkeypatch.setattr("app.services.notification_service.send_email_notification",
                        lambda to, subject, body: enviados.append((to, subject, body)) or True)
    return enviados


def _activar_resumen(client, token):
    r = client.put("/api/v1/users/me/notification-preferences", headers=auth(token),
                   json={"preferences": {}, "digest": True})
    assert r.status_code == 200 and r.json()["data"]["digest"] is True, r.text


def _a_las(hora):
    from datetime import datetime, timezone
    return datetime(2026, 11, 5, hora, 30, tzinfo=timezone.utc)


def test_EL_HALLAZGO_el_resumen_diario_llega_una_vez_con_lo_no_leido(client, pm_token, db, correos_resumen):
    from datetime import timedelta
    from app.services.resumen_de_avisos import enviar
    _activar_resumen(client, pm_token)
    ahora = _a_las(10)
    db.add(Notification(user_id="pm-test-id", type="task_assigned", title="Tarea A", body="b", created_at=ahora - timedelta(hours=2)))
    db.add(Notification(user_id="pm-test-id", type="task_overdue", title="Leída", body="b", is_read=True, created_at=ahora - timedelta(hours=2)))
    db.add(Notification(user_id="pm-test-id", type="task_overdue", title="Vieja", body="b", created_at=ahora - timedelta(days=3)))
    db.commit()
    assert enviar(db, _a_las(3)) == 0, "antes de la hora no se manda"
    assert enviar(db, ahora) == 1
    to, asunto, cuerpo = correos_resumen[-1]
    assert to == "pm@contecflow.com" and "Tarea A" in cuerpo and "Leída" not in cuerpo and "Vieja" not in cuerpo
    assert enviar(db, ahora + timedelta(hours=3)) == 0, "una vez al día"


def test_sin_pendientes_o_sin_activar_no_hay_resumen(client, pm_token, dev_token, db, correos_resumen):
    from app.services.resumen_de_avisos import enviar
    _activar_resumen(client, pm_token)
    db.add(Notification(user_id="dev-test-id", type="task_assigned", title="Para dev", body="b", created_at=_a_las(9)))
    db.commit()
    assert enviar(db, _a_las(10)) == 0 and correos_resumen == []
