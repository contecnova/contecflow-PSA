"""Segunda auditoria 2026-11: n.º 1-9 (seguridad multi-empresa, ajustes muertos, umbrales)."""
from types import SimpleNamespace

import pytest

from app.core.errores import ErrorDeDominio
from tests.conftest import auth


def test_1_no_se_crea_sso_para_otra_organizacion(client, admin_token):
    r = client.post("/api/v1/enterprise/sso", headers=auth(admin_token), json={
        "provider": "oidc", "name": "Ajeno", "oidc_client_id": "x", "oidc_client_secret": "s",
        "oidc_discovery_url": "https://idp.example.com/.well-known/openid-configuration",
        "organization_id": "otra-organizacion", "is_active": True})
    assert r.status_code == 403, r.text


def test_2_y_13_sso_no_entra_como_superadmin_ni_con_otro_sub(db, monkeypatch):
    from app.services.auth_service import sso
    monkeypatch.setattr(sso, "_dominio_permitido", lambda c, e: True)
    monkeypatch.setattr(sso, "rol_desde_grupos", lambda c, cl: None)
    super_ = SimpleNamespace(organization_id="o1", is_active=True, is_superadmin=True, sso_subject=None)
    ligado = SimpleNamespace(organization_id="o1", is_active=True, is_superadmin=False, sso_subject="sub-bueno")

    class _Q:
        def __init__(self, u): self.u = u
        def filter(self, *a, **k): return self
        def first(self): return self.u

    config = SimpleNamespace(organization_id="o1", auto_create_users=False)
    for usuario, claims in ((super_, {"sub": "x"}), (ligado, {"sub": "sub-malo"})):
        falso = SimpleNamespace(query=lambda *a, u=usuario: _Q(u))
        with pytest.raises(ErrorDeDominio) as e:
            sso.create_or_update_sso_user(falso, config, "a@b.com", "A", claims)
        assert e.value.status_code == 403


def test_3_correlacion_sin_organizacion_va_empresa_a_empresa(monkeypatch, db):
    from app.services.service_desk import alert_correlation_service as svc
    vistas = []
    monkeypatch.setattr(svc, "cluster_open_alerts", lambda db, organization_id, window_hours: vistas.append(organization_id) or [])
    svc.run_correlation_scan_job(db)
    assert None not in vistas


def test_4_webhooks_sin_organizacion_no_se_entregan(db):
    from app.services.webhooks import fire_webhook
    assert fire_webhook(db, "task.created", {"x": 1}) == 0


def test_5_valor_global_del_catalogo_no_se_edita_desde_una_empresa(client, pm_token):
    filas = client.get("/api/v1/settings/task-statuses", headers=auth(pm_token)).json()
    filas = (filas.get("items") or filas.get("data") or []) if isinstance(filas, dict) else filas
    globales = [f for f in filas if not f.get("organization_id")]
    if not globales:
        pytest.skip("sin filas globales en la base de test")
    r = client.patch(f"/api/v1/settings/task-statuses/{globales[0]['id']}", headers=auth(pm_token),
                     json={"value": globales[0]["value"], "label": "pirateado", "color": "#000000"})
    assert r.status_code == 403, r.text


def test_6_http_call_a_red_interna_toma_la_rama_de_fallo():
    from app.services.service_desk.workflow_engine import _nodo_llamada_http
    nodo = SimpleNamespace(config={"url": "http://169.254.169.254/latest/meta-data/", "method": "GET"})
    rama, salida, _ = _nodo_llamada_http(nodo)
    assert rama == "failure" and "response" not in salida


def test_7_politica_de_bloqueo_sale_del_ajuste_en_caliente(monkeypatch):
    from app.services.auth_service import estado_efimero as ee
    from app.services import settings_service
    monkeypatch.setattr(settings_service, "get_runtime_int",
                        lambda db, k, org_id=None, default=None: {"LOGIN_MAX_ATTEMPTS": 2}.get(k, default))
    ee._POLITICA_CACHE.update(hasta=0, valor=None)
    assert ee._politica_de_bloqueo()[0] == 2
    ee._POLITICA_CACHE.update(hasta=0, valor=None)


def test_7_tipos_de_cambio_respetan_el_interruptor(monkeypatch):
    from app import worker
    from app.services import settings_service
    monkeypatch.setattr(settings_service, "get_runtime_bool", lambda *a, **k: False)
    assert "skipped" in worker.actualizar_tipos_de_cambio()


def test_9_el_endpoint_de_errores_del_frontend_existe(client):
    r = client.post("/api/v1/client-errors", json={"section": "test", "message": "boom"})
    assert r.status_code == 204, r.text
