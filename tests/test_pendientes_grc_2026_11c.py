"""Segunda auditoría 2026-11: pendientes de GRC.

SoD en presupuestos, aprobación del catálogo y planes de despliegue; reglas SoD
sembradas al crear la empresa y en la primera comprobación; matriz por defecto
del subcontratado; supresión RGPD y bloqueo legal; controles nuevos del
informe; tipos retenibles nuevos; auditoría confirmada; lecturas GRC por empresa.
"""
from __future__ import annotations

import pytest

from app.core.errores import ErrorDeDominio
from app.models.billing_reports import GrcAuditLog, SodRule, SodViolation
from app.models.user import User
from tests.conftest import auth
from tests.test_presupuestos_2026_11 import URL, _crear, _linea, proyecto  # noqa: F401  (fixture)


# ── 1 y 2. SoD ───────────────────────────────────────────────────────────────

def test_quien_crea_el_presupuesto_no_lo_decide_y_queda_la_infraccion(client, db, admin_token, proyecto):
    assert db.query(SodRule).filter(SodRule.organization_id == "1").count() == 0   # nadie abrió la pestaña SoD
    b = _crear(client, admin_token)
    _linea(client, admin_token, b["id"], tipo="otros", descripcion="x", importe=10)
    client.post(f"{URL}/{b['id']}/submit", headers=auth(admin_token))
    r = client.post(f"{URL}/{b['id']}/decision", headers=auth(admin_token), json={"aprobado": True})
    assert r.status_code == 403 and "SoD" in r.json()["detail"]
    v = db.query(SodViolation).filter(SodViolation.context_id == b["id"]).one()
    regla = db.get(SodRule, v.rule_id)
    assert (v.organization_id, regla.module_a, regla.organization_id) == ("1", "budgets", "1")


def test_quien_pide_el_servicio_no_se_lo_aprueba_ni_siendo_admin(client, db, admin_token):
    from app.models.service_desk import ServiceCategory, ServiceItem
    c = ServiceCategory(name="Accesos", organization_id="1")
    db.add(c)
    db.flush()
    s = ServiceItem(category_id=c.id, name="Acceso", requires_approval=True, approval_user_id="admin-test-id",
                    organization_id="1")
    db.add(s)
    db.commit()
    t = client.post("/api/v1/sd/tickets", headers=auth(admin_token), json={
        "title": "Acceso", "description": "d", "ticket_type": "service_request", "service_item_id": s.id,
        "urgency": "medium", "impact": "user"}).json()["data"]
    r = client.post(f"/api/v1/sd/tickets/{t['id']}/approval", headers=auth(admin_token), json={"decision": "approved"})
    assert r.status_code == 403
    assert db.query(SodViolation).filter(SodViolation.context_id == t["id"]).count() == 1


def test_la_empresa_nace_con_sus_reglas_sod(db):
    from app.services.grc_sod import DEFAULT_SOD_RULES
    from app.services.organizations_service import create_organization
    admin = db.query(User).filter(User.username == "admin").one()
    org = create_organization({"name": "Nueva SoD", "slug": "nueva-sod"}, admin, db)
    assert db.query(SodRule).filter(SodRule.organization_id == org["id"]).count() == len(DEFAULT_SOD_RULES)


# ── 3. Matriz del subcontratado ──────────────────────────────────────────────

def test_el_subcontratado_nace_sin_finanzas_ni_administracion(client, db, admin_token, sub_token):
    m = client.get("/api/v1/grc/permissions", headers=auth(admin_token)).json()["data"]["matrix"]["subcontractor"]
    for modulo in ("budgets", "invoices", "revenue-recognition", "accounting", "user-costs", "rate-cards",
                   "profitability", "organizations", "grc", "gdpr"):
        assert not any(m[modulo].values()), modulo
    assert m["settings"]["ver"] is True and m["settings"]["editar"] is False
    assert m["users"]["ver"] is True and m["users"]["crear"] is False
    assert all(m["sd"].values()) and all(m["absences"].values())
    r = client.get("/api/v1/budgets", headers=auth(sub_token))
    assert r.status_code == 403 and "budgets" in r.json()["detail"]


# ── 4. Supresión RGPD y bloqueo legal ────────────────────────────────────────

def test_la_supresion_respeta_el_bloqueo_legal(db):
    from app.models.governance import LegalHold
    from app.services.supresion_service import suprimir_persona
    dev = db.query(User).filter(User.username == "dev_test").one()
    correo = dev.email
    db.add(LegalHold(organization_id="1", case_reference="CASO-7", entity="*", field="user_id", value=dev.id))
    db.add(LegalHold(organization_id="1", case_reference="CASO-8", entity="email_logs", field="to_address",
                     value=correo))
    db.commit()
    with pytest.raises(ErrorDeDominio) as e:
        suprimir_persona(db, dev)
    assert e.value.status_code == 409 and "CASO-7" in str(e.value.detail) and "CASO-8" in str(e.value.detail)
    db.expire_all()
    assert db.get(User, dev.id).email == correo           # no se reescribió nada


# ── 5. Informe de cumplimiento ───────────────────────────────────────────────

def test_el_informe_mide_revocacion_de_sesiones_y_politica_sso(db):
    from app.db import cadena_auditoria
    from app.models.enterprise import SSOConfig, SSOProvider
    from app.services import informe_de_cumplimiento as informe

    def control(id_):
        return next(c for c in informe.generar(db, "1")["controls"] if c["id"] == id_)

    rev = control("session_revocation")
    assert rev["status"] == "pass" and rev["measured"]["on_password_change"] and rev["measured"]["on_password_reset"]
    assert control("sso_policy")["status"] == "info"                       # sin SSO
    sso = SSOConfig(provider=SSOProvider.oidc, is_active=True, organization_id="1", auto_create_users=True, name="IdP")
    db.add(sso)
    db.commit()
    c = control("sso_policy")
    assert c["status"] == "attention" and c["measured"]["providers_auto_create_without_domains"] == ["IdP"]
    sso.allowed_domains = "Empresa.com, otra.es"
    db.commit()
    c = control("sso_policy")
    assert c["status"] == "pass" and c["measured"]["allowed_domains"] == ["empresa.com", "otra.es"]
    assert cadena_auditoria.comprobar_firma(informe.firmar(informe.generar(db, "1")))


# ── 6. Tipos retenibles nuevos ───────────────────────────────────────────────

@pytest.mark.parametrize("clave,campo", [("connector_calls", "user_id"), ("webhook_deliveries", "webhook_id"),
                                         ("email_logs", "to_address"), ("activity_events", "actor_id")])
def test_los_registros_tecnicos_se_retienen_y_se_bloquean(db, clave, campo):
    from app.services import retencion
    retencion.validar_bloqueo(clave, campo)
    assert retencion.vista_previa(db, "1", clave, 30)["expired"] == 0
    assert clave in {p["entity"] for p in retencion.politicas(db, "1")}


# ── 20. La auditoría que se escribe tras el commit del servicio se confirma ──

def test_asignar_a_otra_empresa_deja_la_auditoria_confirmada(db):
    from app.models.enterprise import AuditLog
    from app.models.mfa import Organization
    from app.services.organizations_service import assign_user_to_org
    db.add(Organization(id="org-asig", name="Asig", slug="org-asig", max_users=10))
    db.commit()
    dev = db.query(User).filter(User.username == "dev_test").one()
    assign_user_to_org("org-asig", dev.id, db)
    db.rollback()                                      # lo que no se confirmó se pierde
    assert db.query(AuditLog).filter(AuditLog.action == "ORG_ASSIGN", AuditLog.resource_id == "org-asig").count() == 1


# ── 21. Lecturas GRC por empresa explícita ───────────────────────────────────

def test_infracciones_reglas_y_auditoria_grc_por_empresa(db):
    from app.services import grc_service as g
    from app.models.mfa import Organization
    db.add(Organization(id="org-grc-b", name="B", slug="org-grc-b"))
    db.flush()
    propia = SodRule(module_a="x", action_a="crear", module_b="x", action_b="aprobar", risk="high", organization_id="1")
    ajena = SodRule(module_a="x", action_a="crear", module_b="x", action_b="aprobar", risk="high",
                    organization_id="org-grc-b")
    db.add_all([propia, ajena])
    db.flush()
    db.add_all([SodViolation(rule_id=propia.id, organization_id="1"),
                SodViolation(rule_id=ajena.id, organization_id="org-grc-b"),
                GrcAuditLog(action_type="a", organization_id="1"),
                GrcAuditLog(action_type="a", organization_id="org-grc-b")])
    db.commit()
    # La sesión de los tests es de superadmin: sin el filtro explícito vería las dos.
    assert {v.organization_id for v in g.list_violations_db(db, None, 50, "1")} == {"1"}
    assert {e.organization_id for e in g.list_audit_log_db(db, None, None, 50, "1")} == {"1"}
    assert g.get_sod_rule_or_404(db, propia.id, "1") is not None
    with pytest.raises(ErrorDeDominio):
        g.get_sod_rule_or_404(db, ajena.id, "1")
    v_ajena = db.query(SodViolation).filter(SodViolation.organization_id == "org-grc-b").one()
    with pytest.raises(ErrorDeDominio):
        g.get_violation_or_404(db, v_ajena.id, "1")


def test_una_empresa_con_reglas_antiguas_recibe_las_nuevas_una_vez(db):
    import uuid as _uuid
    from app.models.billing_reports import SodRule
    from app.services.grc_service import ensure_sod_seeded
    from app.services.grc_sod import DEFAULT_SOD_RULES
    org = "org-reglas-antiguas"
    db.add(SodRule(id=str(_uuid.uuid4()), organization_id=org, module_a="x", action_a="crear",
                   module_b="x", action_b="aprobar", risk="low", description="antigua", roles_conflict="[]"))
    db.commit()
    ensure_sod_seeded(db, DEFAULT_SOD_RULES, org)
    claves = {(r.module_a, r.module_b) for r in db.query(SodRule).filter(SodRule.organization_id == org)}
    assert ("budgets", "budgets") in claves and ("sd", "sd") in claves
    db.query(SodRule).filter(SodRule.organization_id == org, SodRule.module_a == "sd").delete()
    db.commit()
    ensure_sod_seeded(db, DEFAULT_SOD_RULES, org)  # borrada a proposito: no vuelve
    assert not db.query(SodRule).filter(SodRule.organization_id == org, SodRule.module_a == "sd").count()
