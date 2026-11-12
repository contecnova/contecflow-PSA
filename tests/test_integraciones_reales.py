"""Integraciones de Enterprise: «Sync» llama al servicio de verdad, o falla.

Revisión 2026-11. Las sincronizaciones eran simulaciones: GitHub inventaba
enlaces a commits en las cinco primeras tareas, el calendario guardaba eventos
que no se enviaban, la contabilidad solo contaba facturas y Jira reescribía el
título sin traer el estado. Además, los secretos se guardan cifrados y tres
lectores los usaban sin descifrar (Slack/Teams no recibían ningún aviso).
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from app.models.cab import CalendarEvent, CommitLink, IntegrationConfig
from app.models.git_integration import GitPullRequest
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.task import Task
from tests.conftest import auth


def _resp(status=200, cuerpo=None):
    return SimpleNamespace(status_code=status, json=lambda: cuerpo, text=str(cuerpo))


def _integracion(client, token, tipo, config, access_token=None):
    r = client.post("/api/v1/oauth-integrations", headers=auth(token), json={
        "integration_type": tipo, "name": tipo, "access_token": access_token, "config": config})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _sync(client, token, iid):
    return client.post(f"/api/v1/oauth-integrations/{iid}/sync", headers=auth(token), json={})


def _proyecto(db):
    p = Project(code="INT", name="Integraciones", status=ProjectStatus.active,
                project_type=ProjectType.development, organization_id="1")
    db.add(p)
    db.commit()
    return p


def test_EL_HALLAZGO_github_trae_los_pull_requests_reales_y_no_inventa_commits(client, admin_token, db, monkeypatch):
    p = _proyecto(db)
    t = Task(code="TSK-00042", project_id=p.id, title="Login", status="in_progress", organization_id="1")
    db.add(t)
    db.commit()
    pedido = {}

    def _get(url, params=None, headers=None, timeout=None):
        pedido.update(url=url, auth=headers["Authorization"])
        return _resp(200, [
            {"number": 7, "title": "TSK-00042 login", "html_url": "https://github.com/o/r/pull/7",
             "user": {"login": "ana"}, "head": {"ref": "feature/TSK-00042"}, "base": {"ref": "main"},
             "closed_at": "2026-11-01T10:00:00Z", "merged_at": "2026-11-01T10:00:00Z"},
            {"number": 8, "title": "otra", "html_url": "u", "user": {"login": "b"},
             "head": {"ref": "x"}, "base": {"ref": "main"}, "closed_at": None, "merged_at": None},
        ])
    monkeypatch.setattr(httpx, "get", _get)
    iid = _integracion(client, admin_token, "github", {"repo": "o/r", "access_token": "ghp_secreto"})
    r = _sync(client, admin_token, iid)
    assert r.status_code == 200 and r.json()["data"]["synced"] == 2, r.text
    assert pedido == {"url": "https://api.github.com/repos/o/r/pulls", "auth": "Bearer ghp_secreto"}
    db.expire_all()
    assert db.query(GitPullRequest).count() == 2
    assert db.query(Task).filter(Task.id == t.id).one().status == "done", "PR fusionado cierra su tarea"
    assert db.query(CommitLink).count() == 0, "ya no se inventan commits"


def test_EL_HALLAZGO_google_calendar_envia_los_sprints_y_no_los_duplica(client, admin_token, db, monkeypatch):
    from app.models.sprints import Sprint
    p = _proyecto(db)
    db.add(Sprint(name="S1", number=1, project_id=p.id, start_date=date(2026, 11, 2), end_date=date(2026, 11, 13),
                  organization_id="1"))
    db.commit()
    llamadas = []
    monkeypatch.setattr(httpx, "post", lambda url, json, headers, timeout: (
        llamadas.append(("POST", url, json)) or _resp(200, {"id": "g-1"})))
    monkeypatch.setattr(httpx, "put", lambda url, json, headers, timeout: (
        llamadas.append(("PUT", url, json)) or _resp(200, {"id": "g-1"})))
    iid = _integracion(client, admin_token, "google_calendar", {"calendar_id": "equipo", "access_token": "ya29"})
    assert _sync(client, admin_token, iid).status_code == 200
    assert _sync(client, admin_token, iid).status_code == 200
    base = "https://www.googleapis.com/calendar/v3/calendars/equipo/events"
    assert [(m, u) for m, u, _ in llamadas] == [("POST", base), ("PUT", f"{base}/g-1")]
    assert llamadas[0][2]["end"] == {"date": "2026-11-14"}, "el fin de un evento de día completo es exclusivo"
    db.expire_all()
    assert [e.external_id for e in db.query(CalendarEvent).all()] == ["g-1"]


def test_EL_HALLAZGO_la_contabilidad_envia_las_facturas_con_el_token_descifrado(client, admin_token, db, monkeypatch):
    from app.models.billing_reports import Invoice
    from app.services import integrations
    db.add(Invoice(number="INV-X-1", organization_id="1", client_name="C", issue_date=date(2026, 11, 1),
                   status="sent", total=121, subtotal=100))
    db.commit()
    vistos = []
    monkeypatch.setattr(integrations, "push_invoice_to_xero", lambda cfg, inv: vistos.append(
        (cfg["access_token"], inv["number"])) or {"ok": True})
    iid = _integracion(client, admin_token, "xero", {"tenant_id": "t", "access_token": "xero-claro"})
    r = _sync(client, admin_token, iid)
    assert r.status_code == 200 and r.json()["data"]["synced"] == 1, r.text
    assert vistos == [("xero-claro", "INV-X-1")]


def test_EL_HALLAZGO_jira_trae_el_estado_a_la_tarea(client, admin_token, db, monkeypatch):
    from app.services import cab_service
    p = _proyecto(db)
    t = Task(code="TSK-J1", project_id=p.id, title="J", status="todo", jira_issue_key="PRJ-1", organization_id="1")
    db.add(t)
    db.commit()
    monkeypatch.setattr(cab_service.integraciones, "get_jira_issue", lambda cfg, key: {
        "ok": True, "data": {"fields": {"status": {"name": "In Progress"}}}})
    iid = _integracion(client, admin_token, "jira", {"base_url": "https://x", "email": "a@b.c", "api_token": "k"})
    assert _sync(client, admin_token, iid).status_code == 200
    db.expire_all()
    assert db.query(Task).filter(Task.id == t.id).one().status == "in_progress"


def test_slack_no_tiene_sincronizacion_y_lo_dice(client, admin_token, db):
    iid = _integracion(client, admin_token, "slack", {"webhook_url": "https://hooks.slack.com/x"})
    r = _sync(client, admin_token, iid)
    assert r.status_code == 400 and "Probar" in r.text


def test_un_error_del_proveedor_no_se_anuncia_como_sincronizado(client, admin_token, db, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _resp(401, {"message": "Bad credentials"}))
    iid = _integracion(client, admin_token, "github", {"repo": "o/r", "access_token": "malo"})
    r = _sync(client, admin_token, iid)
    assert r.status_code == 400 and "401" in r.text


def test_EL_HALLAZGO_los_avisos_a_slack_usan_la_url_descifrada(client, admin_token, db, monkeypatch):
    from app.services import integrations
    _integracion(client, admin_token, "slack", {"webhook_url": "https://hooks.slack.com/services/T/B/x"})
    fila = db.query(IntegrationConfig).filter(IntegrationConfig.integration_type == "slack").one()
    assert "hooks.slack.com" not in (fila.config or ""), "se guarda cifrada"
    destinos = []
    monkeypatch.setattr(integrations, "send_slack_message",
                        lambda url, *a, **k: destinos.append(url) or {"ok": True})
    integrations.notify_event(next(iter(integrations.EVENT_TEMPLATES)), _entidad(integrations), db)
    assert destinos == ["https://hooks.slack.com/services/T/B/x"]


def _entidad(integrations) -> dict:
    """Una entidad que rellena cualquier plantilla de aviso."""
    class _Todo(dict):
        def __missing__(self, k):
            return "x"
    return _Todo(id="1", title="Algo")


@pytest.mark.parametrize("tipo", ["slack", "teams"])
def test_EL_HALLAZGO_la_automatizacion_lee_el_webhook_descifrado(client, admin_token, db, tipo):
    from app.services.automations_service import _webhook_de_la_integracion
    _integracion(client, admin_token, tipo, {"webhook_url": f"https://{tipo}.example/hook"})
    assert _webhook_de_la_integracion(db, tipo, {"organization_id": "1"}) == f"https://{tipo}.example/hook"


def test_EL_HALLAZGO_contabilidad_descifra_el_token_al_enviar_en_lote(client, admin_token, db, monkeypatch):
    from app.models.billing_reports import Invoice
    from app.services import integrations
    db.add(Invoice(number="INV-Q-1", organization_id="1", client_name="C", issue_date=date(2026, 11, 1),
                   status="sent", total=121, subtotal=100))
    db.commit()
    tokens = []
    monkeypatch.setattr(integrations, "push_invoice_to_quickbooks",
                        lambda cfg, inv: tokens.append(cfg["access_token"]) or {"ok": True})
    _integracion(client, admin_token, "quickbooks", {"realm_id": "r", "access_token": "qb-claro"})
    r = client.post("/api/v1/accounting/push-invoices-bulk", headers=auth(admin_token), json={"provider": "quickbooks"})
    assert r.status_code == 200, r.text
    assert tokens == ["qb-claro"]
