"""Segunda auditoría 2026-11: pendientes multitenant (#7, #8, #9, #10, #11, #19)."""
import base64
import hashlib
import hmac
import importlib
import time
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from app.core.config import settings
from tests.conftest import auth

ORG_A = "org-a-test"
ORG_B = "org-b-test"


def _ajuste(db, org, clave, valor):
    from app.models.settings import AppSetting
    db.add(AppSetting(organization_id=org, key=clave, value=valor))
    db.commit()


def _desactivar(db, org_id):
    from app.models.mfa import Organization
    db.get(Organization, org_id).is_active = False
    db.commit()


# ── #7 El ticket WS lleva la organización activa ─────────────────────────────

@pytest.mark.anyio
async def test_7_el_ticket_ws_lleva_la_organizacion_activa(monkeypatch):
    from app.api.v1.endpoints import ws
    monkeypatch.setattr(ws, "_REDIS_URL", "")
    t = await ws._issue_ws_ticket("u1", "org-b")
    assert ws.separar_identidad(await ws._consume_ws_ticket(t)) == ("u1", "org-b")
    t = await ws._issue_ws_ticket("u1")
    assert ws.separar_identidad(await ws._consume_ws_ticket(t)) == ("u1", None)


def test_7_get_ticket_emite_con_la_organizacion_de_la_sesion(client, admin_token, monkeypatch):
    from app.api.v1.endpoints import ws
    visto = {}

    async def _emitir(user_id, organization_id=None):
        visto.update(user=user_id, org=organization_id)
        return "x" * 30

    monkeypatch.setattr(ws, "_issue_ws_ticket", _emitir)
    r = client.get("/api/v1/ws/ticket", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert visto["user"] == "admin-test-id" and visto["org"]


def test_7_el_socket_publica_la_activa_solo_si_sigue_perteneciendo(db, seed_multitenant):
    from app.api.v1.endpoints.ws import usuario_en_su_organizacion_activa
    from app.models.user import User, UserOrganizationMembership
    db.add(UserOrganizationMembership(user_id="outsider-test-id", organization_id=ORG_A))
    db.commit()
    outsider = db.get(User, "outsider-test-id")
    usuario_en_su_organizacion_activa(db, outsider, ORG_A)
    assert outsider.organization_id == ORG_A
    pm = db.get(User, "pm-test-id")
    usuario_en_su_organizacion_activa(db, pm, ORG_B)  # sin pertenencia: la de ficha
    assert pm.organization_id == ORG_A


# ── #8 Slack/Teams ───────────────────────────────────────────────────────────

def _post_slack(client, secreto, **campos):
    cuerpo = urlencode({"text": "ayuda", "user_name": "outsider", **campos}).encode()
    ts = str(int(time.time()))
    firma = "v0=" + hmac.new(secreto.encode(), f"v0:{ts}:{cuerpo.decode()}".encode(), hashlib.sha256).hexdigest()
    return client.post("/api/v1/integrations-hub/slack/commands", data=cuerpo.decode(), headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Slack-Request-Timestamp": ts, "X-Slack-Signature": firma})


def test_8_workspace_en_varias_organizaciones_se_rechaza(client, db, seed_multitenant, monkeypatch):
    from app.services.integrations import (
        VinculoAmbiguo, find_user_by_slack_name, find_user_by_teams_name,
        organizacion_del_workspace_de_slack)
    monkeypatch.setattr(settings, "SLACK_SIGNING_SECRET", "sec-global", raising=False)
    for org in (ORG_A, ORG_B):
        _ajuste(db, org, "SLACK_TEAM_ID", "T-DOBLE")
        _ajuste(db, org, "TEAMS_TENANT_ID", "TEN-DOBLE")
    with pytest.raises(VinculoAmbiguo):
        organizacion_del_workspace_de_slack(db, "T-DOBLE")
    # Sin caer a la búsqueda global: el usuario existe, pero no se devuelve.
    assert find_user_by_slack_name(db, "outsider", "T-DOBLE") is None
    assert find_user_by_teams_name(db, "outsider user", "TEN-DOBLE") is None
    assert find_user_by_slack_name(db, "outsider") is not None  # sin vínculo: como antes
    assert _post_slack(client, "sec-global", team_id="T-DOBLE").status_code == 403


def test_8_firma_con_el_secreto_de_la_organizacion_del_workspace(client, db, seed_multitenant, monkeypatch):
    monkeypatch.setattr(settings, "SLACK_SIGNING_SECRET", "sec-global", raising=False)
    _ajuste(db, ORG_B, "SLACK_TEAM_ID", "T-B")
    _ajuste(db, ORG_B, "SLACK_SIGNING_SECRET", "sec-b")
    assert _post_slack(client, "sec-b", team_id="T-B").status_code == 200
    assert _post_slack(client, "sec-global", team_id="T-B").status_code == 403
    # Workspace sin vínculo: el global, como antes.
    assert _post_slack(client, "sec-global", team_id="T-OTRO").status_code == 200


# ── #9 Twilio por organización ───────────────────────────────────────────────

def _firma_twilio(token, url, params):
    datos = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), datos.encode(), hashlib.sha1).digest()).decode()


def test_9_sms_se_verifica_con_el_token_de_la_organizacion_del_numero(db, seed_multitenant, monkeypatch):
    from app.models.settings import IntegrationCredential
    from app.services.service_desk.sms_service import validate_twilio_signature
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "tok-global", raising=False)
    db.add(IntegrationCredential(organization_id=ORG_B, provider="twilio", key="from_number", value="+34600000002"))
    db.commit()
    _ajuste(db, ORG_B, "TWILIO_AUTH_TOKEN", "tok-b")
    url = "https://x/api/v1/sd/inbound/sms"
    de_b = {"To": "+34600000002", "From": "+1", "Body": "hola"}
    assert validate_twilio_signature(url, de_b, _firma_twilio("tok-b", url, de_b), db)
    assert not validate_twilio_signature(url, de_b, _firma_twilio("tok-global", url, de_b), db)
    otro = {"To": "+34999", "From": "+1", "Body": "hola"}
    assert validate_twilio_signature(url, otro, _firma_twilio("tok-global", url, otro), db)


# ── #10 Organización desactivada ─────────────────────────────────────────────

def test_10_alertas_de_monitorizacion_de_una_organizacion_desactivada(client, db, seed_multitenant, monkeypatch):
    from app.services.service_desk import monitoring_ingest
    monkeypatch.setattr(monitoring_ingest, "organizacion_del_token", lambda db, token: ORG_B)
    _desactivar(db, ORG_B)
    r = client.post("/api/v1/sd/events/prometheus", json={"title": "x"}, headers={"X-Contecflow-Event-Token": "t"})
    assert r.status_code == 403


def test_10_vista_publica_del_portal_de_una_organizacion_desactivada(client, db, seed_multitenant):
    from app.services.client_portal_service.autenticacion import create_portal_share_token
    token = create_portal_share_token("project-b-test")
    assert client.get(f"/api/v1/portal/view/{token}").status_code == 200
    _desactivar(db, ORG_B)
    assert client.get(f"/api/v1/portal/view/{token}").status_code == 403


def test_10_trabajos_de_fondo_saltan_filas_de_organizaciones_desactivadas(db, seed_multitenant):
    from app.services import automation_events
    from app.services.entrada_service import organizacion_desactivada
    from app.services.service_desk import ticket_event_processor
    _desactivar(db, ORG_B)
    assert organizacion_desactivada(db, ORG_B) and not organizacion_desactivada(db, ORG_A)
    assert not organizacion_desactivada(db, None)
    ev = SimpleNamespace(organization_id=ORG_B, data="{}", ticket_id="no-existe")
    assert ticket_event_processor.procesar_evento(db, ev) == {"omitido": "organizacion desactivada"}
    ev = SimpleNamespace(id="e1", organization_id=ORG_B, status="pending", error=None,
                         processed_at=None, attempts=0)
    assert automation_events.procesar_evento(db, ev) == {"omitido": "organizacion desactivada"}
    assert ev.status == "skipped" and ev.attempts == 0


# ── #11 SSO, perfiles semánticos, OLAP ───────────────────────────────────────

def test_11_proveedores_sso_solo_del_dominio_del_correo(client, db, seed_multitenant):
    from app.models.enterprise import SSOConfig
    db.add_all([
        SSOConfig(provider="oidc", name="IdP A", is_active=True, organization_id=ORG_A, allowed_domains="a.com"),
        SSOConfig(provider="oidc", name="IdP B", is_active=True, organization_id=ORG_B, allowed_domains="b.com"),
    ])
    db.commit()
    url = "/api/v1/auth/sso/providers"
    assert client.get(url).json() == []
    assert [p["name"] for p in client.get(url, params={"email": "ana@b.com"}).json()] == ["IdP B"]
    assert [p["name"] for p in client.get(url, params={"domain": "a.com"}).json()] == ["IdP A"]


def test_11_perfil_semantico_por_usuario_y_organizacion(db, seed_multitenant):
    from app.models.semantic_engine import SemProfile, perfil_semantico
    db.add_all([SemProfile(user_id="outsider-test-id", organization_id=ORG_A, profile_text="en A"),
                SemProfile(user_id="outsider-test-id", organization_id=ORG_B, profile_text="en B")])
    db.commit()  # antes: único global de user_id → IntegrityError
    db.info["organization_id"] = ORG_A
    try:
        assert perfil_semantico(db, "outsider-test-id").profile_text == "en A"
    finally:
        db.info.pop("organization_id", None)


def test_11_recarga_olap_solo_superadmin(client, admin_token):
    assert client.post("/api/v1/analytics/olap/refresh", headers=auth(admin_token)).status_code == 403


# ── #19 Funciones sin llamadas, borradas ─────────────────────────────────────

@pytest.mark.parametrize("modulo,nombre", [
    ("app.services.alert_service", "run_alert_engine_job"),
    ("app.services.perf_reminder_service", "run_perf_reminders_job"),
    ("app.services.resumen_de_avisos", "enviar_job"),
    ("app.services.retencion", "aplicar_job"),
    ("app.services.scheduled_reports", "run_due_reports"),
])
def test_19_entradas_sin_contexto_de_tenant_borradas(modulo, nombre):
    assert not hasattr(importlib.import_module(modulo), nombre)
