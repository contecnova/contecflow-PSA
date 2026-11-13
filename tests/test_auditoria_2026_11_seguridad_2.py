"""Segunda auditoria 2026-11: hallazgos 14, 15, 21-29, 32 y 45 (parte de login).

Cada bloque prueba el comportamiento que el hallazgo describia como roto.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tests.conftest import TEST_PASSWORD, auth

ORG_A, ORG_B = "org-a-test", "org-b-test"


# ── 14. Webhook de Jira: secreto por organizacion y claves acotadas ──────────

def _issue(key, estado="Done"):
    return {"webhookEvent": "jira:issue_updated",
            "issue": {"key": key, "fields": {"status": {"name": estado}, "priority": {"name": "Low"}}}}


def test_14_el_secreto_global_de_jira_ya_no_autentica(client, db, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "JIRA_WEBHOOK_SECRET", "global-compartido")
    for ruta in ("/api/v1/jira/webhook", "/api/v1/integrations/jira/webhook"):
        r = client.post(ruta, json=_issue("X-1"), headers={"X-Atlassian-Webhook-Token": "global-compartido"})
        assert r.status_code == 403, ruta


def test_14_el_webhook_de_una_organizacion_no_toca_tareas_de_otra(client, db, seed_multitenant):
    from app.models.task import Task
    from app.services import jira_service

    for tid in ("task-a-test", "task-b-test"):
        db.get(Task, tid).jira_issue_key = "SHR-1"
    db.commit()
    secreto_a = jira_service.generar_secreto_de_webhook(db, ORG_A)
    jira_service.generar_secreto_de_webhook(db, ORG_B)

    r = client.post("/api/v1/jira/webhook", json=_issue("SHR-1"),
                    headers={"X-Atlassian-Webhook-Token": secreto_a})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert getattr(db.get(Task, "task-a-test").status, "value", None) == "done"
    assert getattr(db.get(Task, "task-b-test").status, "value", None) == "todo", "tarea de otra organizacion"
    # `?org=` solo acota: con el secreto de A y la organizacion de B, 403.
    r = client.post(f"/api/v1/jira/webhook?org={ORG_B}", json=_issue("SHR-1"),
                    headers={"X-Atlassian-Webhook-Token": secreto_a})
    assert r.status_code == 403


def test_14_el_webhook_de_tickets_solo_aplica_los_enlaces_de_su_organizacion(db):
    from app.models.jira_integration import JiraConfig, JiraSyncMap
    from app.models.mfa import Organization
    from app.models.service_desk import Ticket
    from app.services.service_desk.jira_sync_service import procesar_webhook

    db.add(Organization(id="org-jira-b", name="B", slug="org-jira-b", is_active=True))
    tickets = {}
    for org, n in (("1", 1), ("org-jira-b", 2)):
        t = Ticket(number=f"INC-900{n}", ticket_type="incident", title="t", description="d", organization_id=org)
        c = JiraConfig(name="j", jira_base_url="https://x.atlassian.net", jira_email="a@b.c",
                       jira_api_token_enc="x", jira_project_key="SUP", organization_id=org)
        db.add_all([t, c])
        db.flush()
        db.add(JiraSyncMap(config_id=c.id, ticket_id=t.id, jira_issue_key="SUP-12", organization_id=org))
        tickets[org] = t.id
    db.commit()

    r = procesar_webhook(db, {"fields": {"status": {"name": "In Progress"}}}, "SUP-12", "1")
    assert r["processed"] == 1
    db.expire_all()
    assert db.get(Ticket, tickets["1"]).status.value == "in_progress"
    assert db.get(Ticket, tickets["org-jira-b"]).status.value == "new"
    assert procesar_webhook(db, {"fields": {}}, "SUP-12", None)["skipped"] == "no organization"


def test_14_el_secreto_se_rota_solo_por_un_administrador(client, admin_token, pm_token, db):
    assert client.post("/api/v1/jira/webhook-secret", headers=auth(pm_token)).status_code == 403
    r = client.post("/api/v1/jira/webhook-secret", headers=auth(admin_token))
    assert r.status_code == 200 and len(r.json()["data"]["secret"]) >= 32


# ── 15. Microsoft Graph: solo buzones de la organizacion ─────────────────────

@pytest.fixture()
def graph_falso(monkeypatch):
    from app.api.v1.endpoints import m365
    from app.services import m365_service

    pedidas = []

    async def _get(path):
        pedidas.append(path)
        return {"value": [], "id": path}

    async def _post(path, payload):
        pedidas.append((path, payload))
        return {"value": []}

    monkeypatch.setattr(m365_service, "m365_configured", lambda: True)
    monkeypatch.setattr(m365, "_graph_get", _get)
    monkeypatch.setattr(m365, "_graph_post", _post)
    return pedidas


def test_15_el_calendario_de_alguien_de_otra_organizacion_es_403(client, admin_token, db, seed_multitenant, graph_falso):
    r = client.post("/api/v1/m365/calendar/sync?user_upn=outsider@example.com", headers=auth(admin_token))
    assert r.status_code == 403 and graph_falso == []
    r = client.post("/api/v1/m365/calendar/sync?user_upn=pm@contecflow.com", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert graph_falso and graph_falso[0].startswith("/users/pm@contecflow.com/")


def test_15_la_presencia_omite_a_los_de_otra_organizacion(client, dev_token, db, seed_multitenant, graph_falso):
    r = client.get("/api/v1/m365/users/presence?upns=outsider@example.com,pm@contecflow.com",
                   headers=auth(dev_token))
    assert r.status_code == 200, r.text
    consultados = [p for p in graph_falso if isinstance(p, str)]
    assert consultados == ["/users/pm@contecflow.com?$select=id,displayName"]


def test_25_teams_notify_no_acepta_urls_internas(client, admin_token, db):
    r = client.post("/api/v1/m365/teams/notify", headers=auth(admin_token),
                    json={"title": "t", "text": "x", "webhook_url": "https://169.254.169.254/latest"})
    assert r.status_code == 400


def test_25_jira_no_repite_la_respuesta_remota(monkeypatch):
    import httpx
    from app.core.errores import ErrorDeDominio
    from app.services import jira_service

    respuesta = httpx.Response(500, text="SECRETO-INTERNO", request=httpx.Request("GET", "https://j.example.com"))

    def _crudo(*a, **k):
        raise httpx.HTTPStatusError("x", request=respuesta.request, response=respuesta)
    monkeypatch.setattr(jira_service, "llamar_a_jira_crudo", _crudo)
    with pytest.raises(ErrorDeDominio) as e:
        jira_service.llamar_a_jira({"jira_url": "https://j.example.com"}, "GET", "/x")
    assert e.value.status_code == 502 and "SECRETO" not in str(e.value.detail)
    with pytest.raises(ErrorDeDominio) as e:   # la URL se valida al guardar
        jira_service.save_jira_config(None, "1", "http://127.0.0.1:8080", "a@b.c", "t", "K")
    assert e.value.status_code == 400


# ── 21. Cambiar el segundo factor pide reautenticacion ───────────────────────

def test_21_reconfigurar_el_2fa_activo_pide_contrasena(client, admin_token, db):
    import pyotp

    secreto = client.post("/api/v1/auth/mfa/setup", headers=auth(admin_token)).json()["secret"]
    assert client.post("/api/v1/auth/mfa/verify-setup", headers=auth(admin_token),
                       json={"code": pyotp.TOTP(secreto).now()}).status_code == 200
    assert client.post("/api/v1/auth/mfa/setup", headers=auth(admin_token)).status_code == 401
    assert client.post("/api/v1/auth/mfa/setup", headers=auth(admin_token),
                       json={"password": "mala"}).status_code == 401
    from app.models.user import User
    db.expire_all()
    assert db.get(User, "admin-test-id").mfa_enabled is True, "un intento fallido no apaga el 2FA"
    r = client.post("/api/v1/auth/mfa/setup", headers=auth(admin_token), json={"password": TEST_PASSWORD})
    assert r.status_code == 200, r.text


def test_21_registrar_una_passkey_pide_contrasena(client, pm_token, db):
    ruta = "/api/v1/auth/mfa/webauthn/register/start"
    assert client.post(ruta, headers=auth(pm_token)).status_code == 401
    assert client.post(ruta, headers=auth(pm_token), json={"password": TEST_PASSWORD}).status_code == 200


# ── 22. Cambio/restablecimiento de contrasena y logout revocan sesiones ──────

def _sesiones(db, user_id="admin-test-id"):
    from app.models.sessions import UserSession
    db.expire_all()
    return db.query(UserSession).filter(UserSession.user_id == user_id).all()


def _login(client, usuario="admin"):
    r = client.post("/api/v1/auth/login", json={"username": usuario, "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return r


def test_22_la_cookie_de_refresco_llega_a_logout_y_logout_la_revoca(client, db):
    r = _login(client)
    cabeceras = r.headers.get_list("set-cookie")
    assert any(c.startswith("refresh_token=") and "Path=/api/v1/auth;" in c for c in cabeceras), cabeceras
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert all(s.revoked_at is not None for s in _sesiones(db))
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_22_cambiar_la_contrasena_cierra_las_demas_sesiones(client, db):
    from app.models.sessions import UserSession
    from datetime import datetime, timedelta, timezone

    db.add(UserSession(user_id="admin-test-id", refresh_token_jti="otra-sesion", auth_method="password",
                       expires_at=datetime.now(timezone.utc) + timedelta(days=1), organization_id="1"))
    db.commit()
    _login(client)
    r = client.post("/api/v1/auth/change-password",
                    json={"current_password": TEST_PASSWORD, "new_password": "Nueva-Clave#2026-xyz!"})
    assert r.status_code == 200, r.text
    estado = {s.refresh_token_jti: s.revoked_at for s in _sesiones(db)}
    assert estado.pop("otra-sesion") is not None
    assert len(estado) == 1 and all(v is None for v in estado.values()), "la sesion actual sigue"


def test_22_restablecer_la_contrasena_cierra_todas(client, db):
    from app.services.auth_service import issue_password_reset_token
    from app.models.user import User

    _login(client)
    token = issue_password_reset_token(db.get(User, "admin-test-id"))
    r = client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": "Nueva-Clave#2026-xyz!"})
    assert r.status_code == 200, r.text
    assert _sesiones(db) and all(s.revoked_at is not None for s in _sesiones(db))


# ── 23. Token del portal: contacto desactivado y logout ──────────────────────

@pytest.fixture()
def contacto_portal(db):
    from app.models.client_portal import ClientUser
    from app.services.client_portal_service import hash_password
    c = ClientUser(full_name="Ana", email="ana@portal.com", organization_id="1", is_active=True,
                   hashed_password=hash_password("Clave-del-portal-1"))
    db.add(c)
    db.commit()
    return c


def test_23_un_contacto_desactivado_no_entra_con_su_token(db, contacto_portal):
    from app.core.security import verify_client_token
    from app.services.client_portal_service import create_client_token

    token = create_client_token(contacto_portal.id)
    assert verify_client_token(token, db).id == contacto_portal.id
    contacto_portal.is_active = False
    db.commit()
    assert verify_client_token(token, db) is None


def test_23_el_logout_del_portal_revoca_el_token(client, db, contacto_portal):
    r = client.post("/api/v1/portal/auth/login", json={"email": "ana@portal.com", "password": "Clave-del-portal-1"})
    assert r.status_code == 200, r.text
    token = r.cookies.get("portal_access_token")
    cab = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/portal/auth/me", headers=cab).status_code == 200
    assert client.post("/api/v1/portal/auth/logout", headers=cab).status_code == 200
    assert client.get("/api/v1/portal/auth/me", headers=cab).status_code == 401
    from app.core.security import verify_client_token
    assert verify_client_token(token, db) is None


# ── 24. Secretos de webhooks de colaboracion ─────────────────────────────────

def test_24_solo_un_administrador_ve_el_secreto_del_webhook(client, admin_token, dev_token, db):
    r = client.post("/api/v1/collaboration/webhooks", headers=auth(admin_token),
                    json={"direction": "incoming", "name": "ci", "events": []})
    assert r.status_code == 200, r.text
    secreto = r.json()["data"]["secret_token"]
    assert len(secreto) > 20
    del_dev = client.get("/api/v1/collaboration/webhooks", headers=auth(dev_token)).json()["items"]
    assert del_dev and del_dev[0]["secret_token"].startswith("••••") and secreto not in json.dumps(del_dev)
    del_admin = client.get("/api/v1/collaboration/webhooks", headers=auth(admin_token)).json()["items"]
    assert del_admin[0]["secret_token"] == secreto


# ── 26. OAuth con `state` firmado, de un uso y ligado ────────────────────────

def test_26_state_firmado_de_un_uso_y_del_mismo_usuario():
    from app.core.errores import ErrorDeDominio
    from app.services import oauth_state

    s = oauth_state.emitir("prueba", user_id="u1", org_id="o1", x=1)
    with pytest.raises(ErrorDeDominio):
        oauth_state.consumir("otro-proposito", s)
    with pytest.raises(ErrorDeDominio):
        oauth_state.consumir("prueba", s.split(".")[0] + ".firma-falsa")
    s2 = oauth_state.emitir("prueba", user_id="u1", org_id="o1")
    with pytest.raises(ErrorDeDominio):
        oauth_state.consumir("prueba", s2, user_id="u2")
    assert oauth_state.consumir("prueba", s, user_id="u1", org_id="o1")["x"] == 1
    with pytest.raises(ErrorDeDominio):
        oauth_state.consumir("prueba", s, user_id="u1")   # segundo uso


def test_26_el_callback_de_docusign_exige_el_state_emitido(client, admin_token, db, monkeypatch):
    from app.core.config import settings
    from app.services import esign_providers

    monkeypatch.setattr(settings, "DOCUSIGN_INTEGRATION_KEY", "ik")
    monkeypatch.setattr(settings, "DOCUSIGN_SECRET_KEY", "sk")
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://app.example.com")
    monkeypatch.setattr(esign_providers, "docusign_exchange_code",
                        lambda *a, **k: {"ok": True, "access_token": "at"})
    cb = "/api/v1/esign/auth/docusign/callback?code=c"
    assert client.get(cb, headers=auth(admin_token)).status_code == 400
    url = client.get("/api/v1/esign/auth/docusign/authorize", headers=auth(admin_token)).json()["data"]["authorization_url"]
    from urllib.parse import parse_qs, urlparse
    state = parse_qs(urlparse(url).query)["state"][0]
    assert client.get(f"{cb}&state={state}", headers=auth(admin_token)).status_code == 200
    assert client.get(f"{cb}&state={state}", headers=auth(admin_token)).status_code == 400, "un solo uso"


def test_26_oauth_de_colaboracion_ligado_al_navegador_y_a_la_organizacion(db, monkeypatch):
    from urllib.parse import parse_qs, urlparse
    from app.services.collaboration import _integrations as integ
    from app.services.collaboration.admin import guardar_tokens_de_oauth

    from app.core.config import settings
    monkeypatch.setenv("GITHUB_CLIENT_ID", "cid")
    monkeypatch.setattr(settings, "GITHUB_CLIENT_ID", "cid", raising=False)
    url = integ.auth_url_for("github", "integ-1", user_id="u1", org_id="1", vinculo="navegador-1")
    state = parse_qs(urlparse(url).query)["state"][0]
    pend, error = integ.consumir_estado(state, "otro-navegador")
    assert pend is None and "navegador" in error
    url = integ.auth_url_for("github", "integ-1", user_id="u1", org_id="1", vinculo="navegador-1")
    state = parse_qs(urlparse(url).query)["state"][0]
    pend, _ = integ.consumir_estado(state, "navegador-1")
    assert pend["integration_id"] == "integ-1" and pend["org_id"] == "1"
    assert integ.consumir_estado(state, "navegador-1")[0] is None, "un solo uso"
    assert guardar_tokens_de_oauth(db, "integ-1", {"access_token": "x"}, None) is None


# ── 27. El constructor de informes respeta la visibilidad de tarifas ─────────

def _informe(client, token, entidad, columnas, filtros=()):
    return client.post("/api/v1/reports/preview", headers=auth(token),
                       json={"entity": entidad, "columns": columnas, "filters": list(filtros)})


def test_27_un_pm_no_ve_ni_filtra_tarifas_en_el_constructor(client, pm_token, admin_token, db):
    filas = _informe(client, pm_token, "users", ["email", "hourly_rate"]).json()["data"]["rows"]
    assert filas and all(f["hourly_rate"] is None for f in filas)
    filas = _informe(client, admin_token, "users", ["email", "hourly_rate"]).json()["data"]["rows"]
    assert any(f["hourly_rate"] == 50.0 for f in filas)
    r = _informe(client, pm_token, "users", ["email"], [{"column": "hourly_rate", "operator": "gt", "value": 40}])
    assert r.status_code == 403
    r = _informe(client, pm_token, "imputations", ["hours"],
                 [{"column": "hourly_rate_snapshot", "operator": "gt", "value": 1}])
    assert r.status_code == 403


# ── 28. PDF: el texto del usuario no es marcado de ReportLab ─────────────────

def test_28_el_pdf_escapa_el_texto_del_usuario(db):
    from app.services.pdf_export_service import _texto, generate_pdf

    assert _texto("<img src='/etc/passwd'/> & <a href='javascript:x'>") == \
        "&lt;img src='/etc/passwd'/&gt; &amp; &lt;a href='javascript:x'&gt;"
    pdf = generate_pdf("generic<b>", None, {"company_name": "<img src='/etc/passwd'/><unclosed & co",
                                            "primary_color": "javascript:red"}, db)
    assert pdf.startswith(b"%PDF")


# ── 29. Avisos de aprobacion solo al canal de su organizacion ────────────────

def test_29_el_aviso_va_solo_al_slack_de_la_organizacion(db, monkeypatch):
    from app.models.cab import IntegrationConfig
    from app.services import integrations

    enviados = []
    monkeypatch.setattr(integrations, "send_slack_message",
                        lambda url, title, blocks=None: enviados.append(url) or {"ok": True})
    for org in ("1", "org-ajena"):
        db.add(IntegrationConfig(integration_type="slack", name=f"s-{org}", is_active=True, organization_id=org,
                                 config=json.dumps({"webhook_url": f"https://hooks.slack.com/{org}"})))
    db.commit()
    entidad = {"id": "a1", "title": "Gasto", "entity_type": "expense", "step": "1", "requester": "x"}
    monkeypatch.delitem(db.info, "organization_id")   # como un job: sesion sin organizacion
    assert integrations.notify_event("approval.required", entidad, db) == [], "sin organizacion no se envia"
    assert enviados == []
    integrations.notify_event("approval.required", entidad, db, organization_id="1")
    assert enviados == ["https://hooks.slack.com/1"]


def test_29_los_aprobadores_por_rol_son_de_la_organizacion_de_la_solicitud(db, seed_multitenant):
    from app.models.user import User, UserRole, UserStatus
    from app.services.approval_engine._base import aprobadores_del_paso

    db.add(User(id="admin-b", username="admin_b", email="admin@b.com", full_name="Admin B", role=UserRole.admin,
                status=UserStatus.active, is_active=True, organization_id=ORG_B, hashed_password="x"))
    db.commit()
    paso = SimpleNamespace(approver_type="role", approver_role="admin", approver_user_id=None,
                           approver_department=None, approver_group_id=None)
    ids = aprobadores_del_paso(SimpleNamespace(organization_id=ORG_A, requested_by="pm-test-id"), paso, db)
    assert "admin-test-id" in ids and "admin-b" not in ids


# ── 32. Correo entrante: remitente y organizacion ────────────────────────────

def _correo(remitente, asunto, autenticacion=None, mid="<m@x>"):
    from app.services.service_desk.inbound_mail import CorreoEntrante
    return CorreoEntrante(remitente=remitente, nombre="N", asunto=asunto, texto="hola", message_id=mid,
                          autenticacion=autenticacion)


@pytest.mark.parametrize("cabecera,esperado", [
    (None, None),
    ("mx.empresa.com; spf=pass smtp.mailfrom=a@cliente.com; dkim=none", True),
    ("mx.empresa.com; dkim=pass header.d=cliente.com; spf=fail", True),
    ("mx.empresa.com; dmarc=pass header.from=cliente.com", True),
    ("mx.empresa.com; spf=fail smtp.mailfrom=a@cliente.com; dkim=fail; dmarc=fail", False),
    ("mx.empresa.com; dkim=pass header.d=atacante.com", False),
])
def test_32_lectura_de_authentication_results(cabecera, esperado):
    from app.services.service_desk.inbound_mail import autenticacion_del_remitente
    assert autenticacion_del_remitente(_correo("a@cliente.com", "x", cabecera)) is esperado


def test_32_desde_mime_lee_solo_la_cabecera_de_arriba():
    from email.message import EmailMessage
    from app.services.service_desk.inbound_mail import desde_mime

    m = EmailMessage()
    m["Authentication-Results"] = "mx.empresa.com; dmarc=fail"
    m["Authentication-Results"] = "falsa; dmarc=pass"
    m["From"], m["Subject"] = "a@cliente.com", "x"
    m.set_content("t")
    assert desde_mime(m.as_bytes()).autenticacion == "mx.empresa.com; dmarc=fail"


def test_32_sin_organizacion_no_se_busca_el_ticket_en_otras(db):
    from app.models.service_desk import Ticket
    from app.services.service_desk.inbound_mail import procesar

    db.add(Ticket(number="INC-0042", ticket_type="incident", title="t", description="d",
                  organization_id="1", requester_email="ana@cliente.com"))
    db.commit()
    r = procesar(db, None, _correo("ana@cliente.com", "RE: [INC-0042] hola"))
    db.commit()
    assert r.accion == "created" and r.ticket_id is not None


def test_32_un_from_que_no_se_autentica_comenta_como_externo_sin_cambiar_estado(db):
    from app.models.service_desk import Ticket, TicketComment
    from app.services.service_desk.inbound_mail import procesar

    t = Ticket(number="INC-0042", ticket_type="incident", title="t", description="d", organization_id="1",
               requester_email="ana@cliente.com", status="pending_client")
    db.add(t)
    db.commit()
    r = procesar(db, "1", _correo("ana@cliente.com", "RE: [INC-0042] hola", "mx.empresa.com; dmarc=fail"))
    db.commit()
    db.refresh(t)
    assert r.accion == "commented" and t.status.value == "pending_client"
    c = db.query(TicketComment).filter(TicketComment.ticket_id == t.id).one()
    assert c.author_user_id is None and c.author_client_id is None
    # Un `From` de un agente que no se autentica no comenta como el agente.
    r = procesar(db, "1", _correo("pm@contecflow.com", "RE: [INC-0042] cerrado", "mx; spf=fail; dkim=fail",
                                  mid="<m2@x>"))
    db.commit()
    assert r.accion == "created", "no es del ticket: un externo no comenta un ticket ajeno"
    # Autenticado: si reanuda el ticket.
    procesar(db, "1", _correo("ana@cliente.com", "RE: [INC-0042] ok", "mx; dmarc=pass", mid="<m3@x>"))
    db.commit()
    db.refresh(t)
    assert t.status.value == "in_progress"


# ── 45. Login: tiempo constante, bloqueo por cuenta y MFA en SSO ─────────────

def test_45_un_usuario_inexistente_tambien_paga_un_bcrypt(client, db, monkeypatch):
    from app.api.v1.routers import auth_core

    llamadas = []
    real = auth_core.verify_password
    monkeypatch.setattr(auth_core, "verify_password", lambda p, h: llamadas.append(h) or real(p, h))
    r = client.post("/api/v1/auth/login", json={"username": "no-existe-nadie", "password": "x"})
    assert r.status_code == 401 and len(llamadas) == 1


def test_45_el_bloqueo_por_cuenta_no_depende_de_la_ip(db, monkeypatch):
    from app.services.auth_service import estado_efimero as ee

    monkeypatch.setattr(ee, "_politica_de_bloqueo", lambda: (2, 60, 30))
    monkeypatch.setattr(ee, "get_sso_redis", lambda: None)
    cuenta = ee.login_account_bucket("Victima@x.com ")
    ee.clear_login_failure(cuenta)
    resultados = [ee.register_login_failure(cuenta, ee.LOGIN_ACCOUNT_MULTIPLIER) for _ in range(6)]
    assert resultados[:5] == [0] * 5 and resultados[5] == 30, "3x el umbral por IP"
    assert ee.login_lock_ttl(cuenta) > 0
    ee.clear_login_failure(cuenta)


def test_45_la_organizacion_que_exige_mfa_lo_exige_por_sso(db):
    from app.models.mfa import Organization
    from app.services.auth_service import organizacion_exige_mfa

    db.add(Organization(id="org-mfa", name="M", slug="org-mfa", is_active=True, require_mfa=True))
    db.commit()
    usuario = SimpleNamespace(organization_id="1")
    assert organizacion_exige_mfa(db, usuario) is False
    assert organizacion_exige_mfa(db, usuario, "org-mfa") is True, "la empresa del proveedor SSO manda"
