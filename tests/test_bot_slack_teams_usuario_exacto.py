"""Comandos de Slack y Teams: usuario exacto y en su organizacion.

Auditoria 2026-11: el usuario se buscaba por coincidencia parcial en cualquier
organizacion («ana» casaba con juana@…), sin usuario se creaban tareas y
tickets anonimos, y los codigos de proyecto se buscaban en todas las
organizaciones.
"""
import time

from app.core.config import settings
from app.models.task import Task
from app.services.integrations import find_user_by_slack_name, find_user_by_teams_name
from tests.test_integrations_inbound_security import _slack_signature

RUTA = "/api/v1/integrations-hub/slack/commands"


def _slack(client, monkeypatch, texto, usuario):
    monkeypatch.setattr(settings, "SLACK_SIGNING_SECRET", "sec-test", raising=False)
    from urllib.parse import urlencode
    cuerpo = urlencode({"text": texto, "user_name": usuario}).encode()
    ts = str(int(time.time()))
    return client.post(RUTA, data=cuerpo.decode(), headers={
        "Content-Type": "application/x-www-form-urlencoded", "X-Slack-Request-Timestamp": ts,
        "X-Slack-Signature": _slack_signature("sec-test", cuerpo, ts)})


def test_la_coincidencia_parcial_ya_no_vale(db, seed_multitenant):
    # outsider@example.com es de otra organizacion; «out» y «side» no son nadie.
    assert find_user_by_slack_name(db, "out") is None
    assert find_user_by_slack_name(db, "outsider").id == "outsider-test-id"
    assert find_user_by_teams_name(db, "Outsider") is None
    assert find_user_by_teams_name(db, "outsider  user").id == "outsider-test-id"


def test_sin_usuario_no_se_crea_nada(client, monkeypatch, db):
    r = _slack(client, monkeypatch, "tarea Algo anonimo", "nadie-conocido")
    assert r.status_code == 200 and "No encuentro" in r.json()["text"]
    assert db.query(Task).filter(Task.title.like("%anonimo%")).count() == 0


def test_el_comando_corre_en_la_organizacion_del_usuario(client, monkeypatch, db, seed_multitenant):
    from app.models.project import Project
    codigo_a = db.query(Project).filter(Project.id == "project-a-test").one().code
    codigo_b = db.query(Project).filter(Project.id == "project-b-test").one().code
    # El admin es de la organizacion A: ve su proyecto y no el de la B.
    assert "No encontré" not in _slack(client, monkeypatch, f"estado {codigo_a}", "admin").json()["text"]
    assert "No encontré" in _slack(client, monkeypatch, f"estado {codigo_b}", "admin").json()["text"]
