"""Segunda auditoria 2026-11: n.º 34 (Jira en una capa) y 35 (entrega de informes).

34. Jira estaba implementado tres veces (credenciales en `app_settings` con
    `httpx` en el endpoint, `JiraConfig` + `jira_sync_service`, y el worker con
    sus propios mapas). Ahora: una configuracion (`sd_jira_configs`, la de
    tareas con `usar_para_tareas`), un cliente, unos mapas y una prueba de
    conexion en `jira_service`.
35. Slack/Teams/correo/PDF de los dos sistemas de informes programados por
    `entrega_saliente` (URL validada, `cliente_httpx`, `notification_service`)
    y el PDF tabular comun de `report_pdf`.
"""
from __future__ import annotations

import importlib.util
import pathlib
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from tests.conftest import auth

RAIZ = pathlib.Path(__file__).resolve().parent.parent

JIRA = {"jira_url": "https://test.atlassian.net", "jira_email": "a@test.com",
        "jira_api_token": "tok-123", "jira_project_key": "TST"}
YO = {"accountId": "acc-1", "displayName": "Ana", "emailAddress": "a@test.com"}


def _fuente(rel: str) -> str:
    return (RAIZ / rel).read_text(encoding="utf-8")


# ── 34. Jira: una configuracion, un cliente, unos mapas, una prueba ──────────

def test_34_la_configuracion_de_tareas_vive_en_sd_jira_configs(client, admin_token, db):
    from app.models.jira_integration import JiraConfig
    from app.models.settings import AppSetting

    r = client.post("/api/v1/jira/config", json=JIRA, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    # Guardar dos veces actualiza la misma fila.
    client.post("/api/v1/jira/config", json={**JIRA, "jira_project_key": "OTR"}, headers=auth(admin_token))

    filas = db.query(JiraConfig).filter(JiraConfig.usar_para_tareas.is_(True)).all()
    assert len(filas) == 1 and filas[0].jira_project_key == "OTR"
    assert filas[0].jira_api_token_enc != "tok-123"            # cifrado
    assert db.query(AppSetting).filter(AppSetting.key.in_(
        ("jira_url", "jira_email", "jira_api_token", "jira_project_key"))).count() == 0

    lista = client.get("/api/v1/integrations/jira/configs", headers=auth(admin_token)).json()["items"]
    assert [c["usar_para_tareas"] for c in lista] == [True]
    cfg = client.get("/api/v1/jira/config", headers=auth(admin_token)).json()["data"]
    assert cfg["configured"] is True and cfg["jira_project_key"] == "OTR" and "jira_api_token" not in cfg


def test_34_las_dos_rutas_de_prueba_usan_la_misma_funcion(client, admin_token, db):
    client.post("/api/v1/jira/config", json=JIRA, headers=auth(admin_token))
    cid = client.get("/api/v1/integrations/jira/configs", headers=auth(admin_token)).json()["items"][0]["id"]
    with patch("app.services.jira_service.llamar_a_jira_crudo", return_value=YO) as llamada:
        a = client.get("/api/v1/jira/test", headers=auth(admin_token)).json()["data"]
        b = client.post(f"/api/v1/integrations/jira/configs/{cid}/test", headers=auth(admin_token)).json()["data"]
    assert a["ok"] and a["display_name"] == "Ana" and a["account_id"] == "acc-1"
    assert b == {"ok": True, "jira_account_id": "acc-1", "display_name": "Ana"}
    assert [c.args[2] for c in llamada.call_args_list] == ["/rest/api/3/myself"] * 2


def test_34_la_prueba_de_una_configuracion_no_repite_la_respuesta_remota(client, admin_token, db):
    import httpx

    client.post("/api/v1/jira/config", json=JIRA, headers=auth(admin_token))
    cid = client.get("/api/v1/integrations/jira/configs", headers=auth(admin_token)).json()["items"][0]["id"]
    req = httpx.Request("GET", "https://test.atlassian.net/rest/api/3/myself")
    err = httpx.HTTPStatusError("x", request=req, response=httpx.Response(401, text="secreto-remoto", request=req))
    with patch("app.services.jira_service.llamar_a_jira_crudo", side_effect=err):
        d = client.post(f"/api/v1/integrations/jira/configs/{cid}/test", headers=auth(admin_token)).json()["data"]
    assert d["ok"] is False and "401" in d["error"] and "secreto" not in d["error"]


def test_34_una_sola_conexion_de_tareas_por_organizacion(db):
    from types import SimpleNamespace

    from app.models.jira_integration import JiraConfig
    from app.services.service_desk.jira_sync_service import aplicar_cambios_de_configuracion, crear_configuracion

    user = SimpleNamespace(id="admin-test-id", organization_id="1")
    base = {"jira_base_url": "https://x.atlassian.net", "jira_email": "a@b.c",
            "jira_api_token_enc": "t", "jira_project_key": "K"}
    a = crear_configuracion(db, user, {"name": "a", **base, "usar_para_tareas": True})
    b = crear_configuracion(db, user, {"name": "b", **base})
    aplicar_cambios_de_configuracion(db, b, {"usar_para_tareas": True})
    db.expire_all()
    assert (db.get(JiraConfig, a.id).usar_para_tareas, db.get(JiraConfig, b.id).usar_para_tareas) == (False, True)


def test_34_un_solo_cliente_http_de_jira():
    """Solo `jira_service` arma la autenticacion Basic y abre conexiones a Jira."""
    for rel in ("app/api/v1/endpoints/jira.py", "app/api/v1/endpoints/jira_integration.py",
                "app/services/service_desk/jira_sync_service.py", "app/services/integrations.py"):
        src = _fuente(rel)
        assert 'f"Basic ' not in src and "b64encode(" not in src, rel
    src = _fuente("app/api/v1/endpoints/jira_integration.py")
    assert "cliente_httpx" not in src and "import httpx" not in src


def test_34_un_solo_juego_de_mapas():
    from app.services import jira_service as js
    from app.services.cab_service import integraciones
    from app.services.service_desk import jira_sync_service as sd

    assert "_PERIODICA" not in _fuente("app/services/jira_service.py")
    assert "NEXUS_PRIORITY_TO_JIRA" not in _fuente("app/api/v1/endpoints/jira.py")
    assert sd._DEFAULT_PRIORITY_MAP is js.TICKET_A_JIRA_PRIORIDAD
    assert sd._DEFAULT_STATUS_MAP is js.TICKET_A_JIRA_ESTADO
    assert sd._JIRA_TO_TICKET_STATUS is js.JIRA_A_TICKET_ESTADO
    assert integraciones._ESTADO_DESDE_JIRA is js.JIRA_STATUS_MAP
    assert js.estado_de_tarea(" Blocked ") == "blocked" and js.estado_de_tarea("Raro") is None
    assert js.prioridad_de_tarea("HIGHEST") == "critical"


def test_34_la_sincronizacion_periodica_no_pisa_con_un_estado_desconocido(db, seed_multitenant):
    from app.models.task import Task
    from app.services import jira_service

    jira_service.save_jira_config(db, "org-a-test", **{k: v for k, v in zip(
        ("jira_url", "jira_email", "jira_api_token", "jira_project_key"),
        ("https://t.atlassian.net", "u@t.com", "s", "ABC"))})
    t = db.get(Task, "task-a-test")
    t.jira_issue_key, t.status = "ABC-1", "in_review"
    db.commit()
    assert jira_service.organizaciones_con_jira(db) == ["org-a-test"]
    datos = {"issues": [{"key": "ABC-1", "fields": {"summary": "S", "status": {"name": "Estado propio"},
                                                     "priority": {"name": "Lowest"}}}]}
    with patch("app.services.jira_service.llamar_a_jira_crudo", return_value=datos):
        r = jira_service.sincronizar_organizacion(db, "org-a-test")
    db.commit()
    db.expire_all()
    t = db.get(Task, "task-a-test")
    assert r["synced"] == 1 and str(getattr(t.status, "value", t.status)) == "in_review"
    assert str(getattr(t.priority, "value", t.priority)) == "low"


# ── 34. Migracion 159 ────────────────────────────────────────────────────────

def _migracion_159():
    ruta = RAIZ / "alembic" / "versions" / "159_jira_una_sola_configuracion.py"
    spec = importlib.util.spec_from_file_location("m159", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _aplicar(con, fn):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with Operations.context(MigrationContext.configure(con)):
        fn()


@pytest.fixture()
def base_antigua():
    eng = sa.create_engine("sqlite://")
    with eng.begin() as con:
        con.execute(sa.text("CREATE TABLE organizations (id VARCHAR(36) PRIMARY KEY)"))
        con.execute(sa.text("CREATE TABLE app_settings (id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36), "
                            "key VARCHAR(100) NOT NULL, value TEXT, description VARCHAR(255))"))
        con.execute(sa.text(
            "CREATE TABLE sd_jira_configs (id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36), "
            "name VARCHAR(100) NOT NULL, jira_base_url VARCHAR(500) NOT NULL, jira_email VARCHAR(255) NOT NULL, "
            "jira_api_token_enc TEXT NOT NULL, jira_project_key VARCHAR(50) NOT NULL, "
            "jira_issue_type_incident VARCHAR(100), jira_issue_type_service_request VARCHAR(100), "
            "jira_issue_type_change VARCHAR(100), jira_issue_type_problem VARCHAR(100), sync_direction VARCHAR(30), "
            "sync_comments BOOLEAN, sync_status_changes BOOLEAN, sync_priority_changes BOOLEAN, "
            "sync_assignments BOOLEAN, sync_interval_minutes INTEGER, status_map_json TEXT, priority_map_json TEXT, "
            "is_active BOOLEAN, last_full_sync_at DATETIME, created_at DATETIME, updated_at DATETIME, "
            "created_by_user_id VARCHAR(36))"))
        con.execute(sa.text("CREATE TABLE sd_jira_sync_map (id VARCHAR(36) PRIMARY KEY, config_id VARCHAR(36))"))
        con.execute(sa.text("INSERT INTO organizations VALUES ('o1'), ('o2')"))
        for i, (org, k, v) in enumerate([("o1", "jira_url", "https://a.atlassian.net/"), ("o1", "jira_email", "a@a"),
                                         ("o1", "jira_api_token", "v2:cifrado"), ("o1", "jira_project_key", "A"),
                                         ("o1", "jira_webhook_secret", "s"), ("o2", "jira_url", "https://b")]):
            con.execute(sa.text("INSERT INTO app_settings (id, organization_id, key, value) VALUES (:i, :o, :k, :v)"),
                        {"i": str(i), "o": org, "k": k, "v": v})
    return eng


def test_34_migracion_159_trae_la_configuracion_y_es_idempotente(base_antigua):
    m = _migracion_159()
    for _ in range(2):
        with base_antigua.begin() as con:
            _aplicar(con, m.upgrade)
    with base_antigua.connect() as con:
        filas = con.execute(sa.text("SELECT organization_id, jira_base_url, jira_api_token_enc, jira_project_key, "
                                    "usar_para_tareas FROM sd_jira_configs")).fetchall()
        claves = {tuple(r) for r in con.execute(sa.text("SELECT organization_id, key FROM app_settings"))}
    assert [tuple(f) for f in filas] == [("o1", "https://a.atlassian.net", "v2:cifrado", "A", 1)]
    # o2 sin token no se migra (y su fila queda, sin lector); el secreto del webhook se queda.
    assert claves == {("o1", "jira_webhook_secret"), ("o2", "jira_url")}

    with base_antigua.begin() as con:
        _aplicar(con, m.downgrade)
    with base_antigua.connect() as con:
        assert con.execute(sa.text("SELECT COUNT(*) FROM sd_jira_configs")).scalar() == 0
        assert con.execute(sa.text("SELECT value FROM app_settings WHERE organization_id='o1' "
                                   "AND key='jira_api_token'")).scalar() == "v2:cifrado"


def test_34_la_migracion_159_encadena_con_la_158():
    m = _migracion_159()
    assert m.down_revision == "158_obligaciones_asc606_precio_y_metodo"


# ── 35. Entrega comun: Slack/Teams, correo, PDF ──────────────────────────────

@pytest.mark.parametrize("url", ["http://127.0.0.1:8080/x", "http://169.254.169.254/latest", "file:///etc/passwd"])
def test_35_el_emisor_comun_no_sale_a_redes_internas(url, monkeypatch):
    import httpx

    from app.services import entrega_saliente

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: pytest.fail("no debe conectar"))
    r = entrega_saliente.enviar_a_webhook(url, {"text": "x"})
    assert r.ok is False and "no permitido" in r.error


def test_35_slack_y_teams_de_informes_y_de_integraciones_validan_la_url():
    from app.services import bi_report_delivery_service as bi
    from app.services import integrations

    interna = "http://10.0.0.5/hook"
    assert bi._send_slack(interna, "t", "s") is False
    assert bi._send_teams(interna, "t", "s") is False
    assert integrations.send_slack_message(interna, "x")["ok"] is False
    assert integrations.send_teams_message(interna, "t", "x")["ok"] is False


def test_35_bi_rechaza_un_webhook_interno_al_guardar(db):
    from app.core.errores import ErrorDeDominio
    from app.services import bi_report_delivery_service as bi

    with pytest.raises(ErrorDeDominio):
        bi.create_schedule(db, organization_id="1", name="x", report_preset_id="p", channels=["slack"],
                           recipients=[], frequency="daily", slack_webhook_url="http://127.0.0.1/h")


def test_35_block_kit_rechaza_la_url_interna_del_cuerpo(client, admin_token):
    r = client.post("/api/v1/notifications/slack/block-kit", headers=auth(admin_token), json={
        "event_type": "custom", "data": {}, "webhook_url": "http://169.254.169.254/latest/meta-data"})
    assert r.status_code == 400


def test_35_nadie_llama_a_httpx_o_urllib_directamente_para_avisar():
    for rel in ("app/services/bi_report_delivery_service.py", "app/services/scheduled_reports.py",
                "app/services/slack_service.py", "app/api/v1/endpoints/slack_block_kit.py"):
        src = _fuente(rel)
        for prohibido in ("httpx.post(", "httpx.Client(", "abrir(", "urllib.request.Request("):
            assert prohibido not in src, f"{rel}: {prohibido}"


def test_35_el_informe_programado_va_un_mensaje_por_destinatario(monkeypatch):
    from app.services import notification_service as ns
    from app.services import scheduled_reports as sr

    vistos = []
    monkeypatch.setattr(ns.settings, "SMTP_HOST", "smtp.env")
    monkeypatch.setattr(ns, "enviar_correo", lambda para, asunto, html, **k: (
        vistos.append((para, k["adjuntos"][0][0])), ns.ResultadoEnvio(True))[1])
    sr._send_email(["a@x.com", "b@x.com", "a@x.com"], "s", "<p>x</p>", b"%PDF", "i.pdf")
    assert vistos == [("a@x.com", "i.pdf"), ("b@x.com", "i.pdf")]

    monkeypatch.setattr(ns, "enviar_correo", lambda *a, **k: ns.ResultadoEnvio(False, error="x"))
    with pytest.raises(RuntimeError):
        sr._send_email(["a@x.com"], "s", "<p>x</p>", b"", "i.pdf")


def test_35_el_pdf_bi_es_el_generador_tabular_comun(monkeypatch):
    from app.services import bi_report_delivery_service as bi
    from app.services import report_pdf

    llamadas = []
    original = report_pdf.generate_report_pdf
    monkeypatch.setattr(report_pdf, "generate_report_pdf",
                        lambda **k: (llamadas.append(k), original(**k))[1])
    pdf = bi._export_to_pdf("Ventas", ["a", "b"], [{"a": 1, "b": 2, "c": "fuera"}])
    assert pdf[:4] == b"%PDF"
    assert llamadas[0]["data"] == [{"a": 1, "b": 2}] and llamadas[0]["summary"] == {"Filas": 1}
