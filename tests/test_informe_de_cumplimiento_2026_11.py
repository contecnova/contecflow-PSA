"""Informe de cumplimiento medido (revisión 2026-11).

Cada prueba cambia el dato que mide un control y comprueba que el control
cambia: un informe que no mira daría siempre lo mismo.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.models.bookings import ApiKey
from app.models.cab import GDPRRequest, GDPRRequestType
from app.models.enterprise import AuditLog
from app.models.mfa import Organization, WebAuthnCredential
from app.models.user import User
from app.db import cadena_auditoria
from app.services import informe_de_cumplimiento as informe
from app.services import settings_service
from tests.conftest import auth


def _c(db, id_, org="1"):
    return next(c for c in informe.generar(db, org)["controls"] if c["id"] == id_)


def _activos(db):
    return db.query(User).filter(User.organization_id == "1", User.is_active.is_(True)).all()


def test_todos_los_controles_dicen_de_donde_salen_y_el_resumen_cuadra(db):
    r = informe.generar(db, "1")
    assert {c["id"] for c in r["controls"]} >= {"mfa_required", "mfa_coverage", "password_policy", "idle_logout",
                                                "stale_accounts", "api_keys", "sod_open", "audit_chain",
                                                "db_isolation", "secrets_encryption", "gdpr_requests", "backups"}
    assert all(c["source"] for c in r["controls"])
    assert sum(r["summary"].values()) == len(r["controls"])
    assert _c(db, "backups")["status"] == "not_measurable"      # no se inventa


def test_EL_HALLAZGO_la_mfa_obligatoria_se_mide_y_la_linea_base_ya_no_dice_true_a_mano(client, db, admin_token):
    assert _c(db, "mfa_required")["status"] == "attention"
    base = client.get("/api/v1/governance/compliance/controls/status", headers=auth(admin_token)).json()["data"]
    assert base["platform_security_baseline"]["mfa_enforced"] is False
    db.get(Organization, "1").require_mfa = True
    db.commit()
    assert _c(db, "mfa_required")["status"] == "pass"
    base = client.get("/api/v1/governance/compliance/controls/status", headers=auth(admin_token)).json()["data"]
    assert base["platform_security_baseline"]["mfa_enforced"] is True


def test_cobertura_de_mfa(db):
    activos = _activos(db)
    antes = _c(db, "mfa_coverage")["measured"]
    assert antes["active_users"] == len(activos) and antes["with_second_factor"] == 0
    # Lo que exige el login: TOTP verificado (mfa_enabled + mfa_secret) o passkey activa.
    activos[0].mfa_enabled, activos[0].mfa_secret = True, "x"
    activos[1].mfa_enabled, activos[1].mfa_secret = False, "y"      # alta sin verificar: no cuenta
    db.add(WebAuthnCredential(user_id=activos[1].id, credential_id="c-baja", public_key="k",
                              is_active=False, organization_id="1"))  # passkey borrada: no cuenta
    db.commit()
    medido = _c(db, "mfa_coverage")["measured"]
    assert (medido["with_second_factor"], medido["totp"], medido["passkey"]) == (1, 1, 0)
    settings_service.set_runtime_value(db, "audit", "COMPLIANCE_MFA_MIN_COVERAGE_PCT", 1.0, "1")
    db.commit()
    settings_service.invalidate_cache()
    assert _c(db, "mfa_coverage")["status"] == "pass"


def test_cuentas_sin_entrar(db):
    ahora = datetime.now(timezone.utc)
    for u in _activos(db):
        u.last_login = ahora
    db.commit()
    assert _c(db, "stale_accounts")["status"] == "pass"
    _activos(db)[0].last_login = ahora - timedelta(days=120)
    db.commit()
    c = _c(db, "stale_accounts")
    assert c["status"] == "attention" and c["measured"]["active_without_login_in_days"] == 1


def test_claves_de_api_sin_caducidad_y_rgpd_vencidas(db):
    u = _activos(db)[0]
    db.add(ApiKey(name="k", key_hash="h1", key_prefix="nxpm_a", user_id=u.id, organization_id="1"))
    db.add(GDPRRequest(request_type=GDPRRequestType.access, subject_user_id=u.id, organization_id="1",
                       created_at=datetime.now(timezone.utc) - timedelta(days=45)))
    db.commit()
    assert _c(db, "api_keys")["measured"] == {"active": 1, "without_expiry": 1}
    g = _c(db, "gdpr_requests")
    assert g["status"] == "attention" and g["measured"]["older_than_days"] == 1


def test_la_cadena_de_auditoria_rota_se_ve_en_el_informe(db):
    db.add(AuditLog(action="UPDATE", resource="x", organization_id="1"))
    db.commit()
    assert _c(db, "audit_chain")["status"] == "pass"
    db.execute(text("UPDATE audit_logs SET action = 'Y' WHERE organization_id = '1'"))
    db.commit()
    db.expire_all()
    c = _c(db, "audit_chain")
    assert c["status"] == "attention" and c["measured"]["breaks_total"] >= 1


def test_cada_empresa_lo_suyo(db):
    db.add(Organization(id="org-inf", name="Otra", slug="org-inf"))
    db.add(User(id="u-inf", username="inf", email="inf@x.com", full_name="Inf", hashed_password="x",
                organization_id="org-inf"))
    db.commit()
    assert _c(db, "mfa_coverage", "org-inf")["measured"]["active_users"] == 1


def test_el_informe_firmado_y_solo_admin(client, db, admin_token, pm_token):
    r = client.get("/api/v1/grc/compliance-report", params={"signed": True}, headers=auth(admin_token))
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    doc = r.json()
    assert cadena_auditoria.comprobar_firma(doc)
    doc["summary"]["pass"] += 1
    assert not cadena_auditoria.comprobar_firma(doc)
    assert client.get("/api/v1/grc/compliance-report", headers=auth(pm_token)).status_code == 403
    assert client.get("/api/v1/grc/compliance-report", headers=auth(admin_token)).json()["data"]["controls"]
