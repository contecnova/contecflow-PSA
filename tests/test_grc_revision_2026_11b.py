"""Revisión GRC 2026-11b: lo que había quedado desfasado tras las dos auditorías de 2026-11.

Cada test nombra el hallazgo y lo comprueba contra la aplicación de hoy:

1. Exenciones de GRC: se reutilizaba la lista de ABAC, que ya exime rutas CON
   usuario (conectores, lecciones, BPMN, colaboración, MCP) y prefijos mixtos
   enteros (`/webhooks`, `/forms`). La matriz no los gobernaba.
2. Matriz: módulos escritos a mano sin ruta (`service_desk`, `hr`), un rol que
   no existe (`client`) y otro que sí y no tenía fila (`subcontractor`).
3. SoD: la autoaprobación no quedaba registrada (nombre de entidad ≠ módulo de
   la regla; y en la bandeja, `flush` sin `commit` antes del 403).
4. Auditoría: cambios de seguridad sin rastro (passkeys, SSO, secretos rotados,
   reglas SoD, policy packs).
5. Informe de cumplimiento: miembros por pertenencia y retención.
6. Supresión RGPD: reescribía `audit_logs` y rompía la cadena.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.db.session import sin_filtro_de_tenant
from app.models.billing_reports import GrcAuditLog, RolePermission, SodRule, SodViolation
from app.models.enterprise import AuditLog
from app.models.user import User
from tests.conftest import auth


@pytest.fixture(scope="module")
def fastapi_app():
    from app.main import app
    return app


def _admin(db):
    return db.query(User).filter(User.id == "admin-test-id").first()


def _auditado(db, accion, recurso=None):
    with sin_filtro_de_tenant(db):
        q = db.query(AuditLog).filter(AuditLog.action == accion)
        if recurso:
            q = q.filter(AuditLog.resource == recurso)
        return q.all()


# ── 1. Exenciones ─────────────────────────────────────────────────────────────

def test_ninguna_exencion_de_grc_esta_obsoleta(fastapi_app):
    from app.core.grc_catalog import GRC_EXEMPT_PREFIXES
    rutas = [getattr(r, "path", "") for r in fastapi_app.routes]
    muertas = [p for p in GRC_EXEMPT_PREFIXES if not any(r == p or r.startswith(p + "/") for r in rutas)]
    assert not muertas, f"exenciones GRC sin ninguna ruta: {muertas}"
    assert all(m.strip() for m in GRC_EXEMPT_PREFIXES.values())


@pytest.mark.parametrize("path, modulo", [
    ("/api/v1/conectores/estado", "conectores"),
    ("/api/v1/lessons", "lessons"),
    ("/api/v1/bpmn-instances/inbox", "bpmn-instances"),
    ("/api/v1/collaboration/teams", "collaboration"),
    ("/api/v1/mcp", "mcp"),
    ("/api/v1/webhooks/abc/rotate", "webhooks"),
    ("/api/v1/forms/abc/submissions", "forms"),
])
def test_EL_HALLAZGO_rutas_con_usuario_que_grc_no_gobernaba(path, modulo, fastapi_app):
    from app.core.grc_catalog import discover_modules, module_for_path
    assert module_for_path(path) == modulo
    assert modulo in discover_modules(fastapi_app)


@pytest.mark.parametrize("path", ["/api/v1/webhooks/fire/slug", "/api/v1/forms/public/tok/submit",
                                  "/api/v1/auth/login", "/api/v1/portal/x", "/api/v1/client-errors"])
def test_lo_publico_sigue_exento(path):
    from app.core.grc_catalog import module_for_path
    assert module_for_path(path) is None


def test_una_casilla_en_false_se_aplica_en_un_modulo_antes_exento(client, db, admin_token, dev_token):
    client.get("/api/v1/grc/permissions", headers=auth(admin_token))
    assert client.get("/api/v1/lessons", headers=auth(dev_token)).status_code != 403
    r = client.patch("/api/v1/grc/permissions/employee/lessons/ver", headers=auth(admin_token), json={"allowed": False})
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/lessons", headers=auth(dev_token)).status_code == 403


# ── 2. Matriz ─────────────────────────────────────────────────────────────────

def test_EL_HALLAZGO_la_matriz_ya_no_tiene_modulos_ni_roles_muertos(client, db, admin_token):
    with sin_filtro_de_tenant(db):   # casillas como las que dejó la semilla antigua
        for rol, mod in (("employee", "service_desk"), ("client", "projects"), ("pm", "hr")):
            db.add(RolePermission(organization_id=None, role=rol, module=mod, action="ver", allowed=False))
        db.add(RolePermission(organization_id="1", role="employee", module="hr", action="ver", allowed=False))
        db.commit()
    datos = client.get("/api/v1/grc/permissions", headers=auth(admin_token)).json()["data"]
    assert "client" not in datos["matrix"] and "client" not in datos["roles"]
    assert "subcontractor" in datos["roles"] and datos["matrix"]["subcontractor"]["projects"]["ver"] is True
    assert not {"service_desk", "hr"} & set(datos["modules"])
    assert {"sd", "absences", "collaboration", "lessons"} <= set(datos["modules"])
    assert all("hr" not in mods for mods in datos["matrix"].values())
    with sin_filtro_de_tenant(db):
        globales_muertas = db.query(RolePermission).filter(
            RolePermission.organization_id.is_(None),
            RolePermission.module.in_(["service_desk", "hr"]) | (RolePermission.role == "client")).count()
    assert globales_muertas == 0, "las casillas globales que no gobiernan nada se retiran"


def test_solo_existen_las_casillas_de_operaciones_reales(client, admin_token, fastapi_app):
    from app.core.grc_catalog import discover_module_actions
    datos = client.get("/api/v1/grc/permissions", headers=auth(admin_token)).json()["data"]
    vivas = discover_module_actions(fastapi_app)
    for mods in datos["matrix"].values():
        for modulo, acciones in mods.items():
            assert set(acciones) <= vivas[modulo], modulo


def test_una_casilla_inexistente_da_422(client, admin_token):
    for celda in ("employee/service_desk/ver", "client/projects/ver", "employee/projects/volar"):
        r = client.patch(f"/api/v1/grc/permissions/{celda}", headers=auth(admin_token), json={"allowed": False})
        assert r.status_code == 422, (celda, r.status_code)


def test_la_matriz_por_defecto_solo_opina_de_modulos_y_roles_vivos(fastapi_app):
    from app.api.v1.endpoints.grc import DEFAULT_MATRIX, DEFAULT_SOD_RULES
    from app.core.grc_catalog import discover_modules
    from app.models.user import UserRole
    vivos = set(discover_modules(fastapi_app))
    assert set(DEFAULT_MATRIX) == {r.value for r in UserRole}
    for rol, mods in DEFAULT_MATRIX.items():
        assert set(mods) <= vivos, (rol, set(mods) - vivos)
    for r in DEFAULT_SOD_RULES:
        assert {r["module_a"], r["module_b"]} <= vivos, r


# ── 3. SoD ────────────────────────────────────────────────────────────────────

def _sembrar_sod(client, admin_token):
    assert client.get("/api/v1/grc/sod-rules", headers=auth(admin_token)).status_code == 200


def test_EL_HALLAZGO_la_entidad_singular_encuentra_la_regla_por_defecto(client, db, admin_token):
    from app.services.grc_sod import record_self_approval_violation_for_request
    _sembrar_sod(client, admin_token)
    assert record_self_approval_violation_for_request(db, "expense", "gasto-1", "dev-test-id", "dev-test-id",
                                                      "employee", organization_id="1")
    db.commit()
    with sin_filtro_de_tenant(db):
        v = db.query(SodViolation).filter(SodViolation.context_id == "gasto-1").one()
        regla = db.get(SodRule, v.rule_id)
        traza = db.query(GrcAuditLog).filter(GrcAuditLog.resource_id == "gasto-1").one()
    assert regla.module_a == "expenses" and v.organization_id == "1" and traza.organization_id == "1"


def test_la_regla_de_otra_empresa_no_se_usa(db):
    from app.services.grc_sod import record_self_approval_violation_for_request
    from app.models.mfa import Organization
    db.add(Organization(id="org-sod", name="Otra", slug="org-sod"))
    db.add(SodRule(organization_id="org-sod", module_a="expenses", action_a="crear", module_b="expenses",
                   action_b="aprobar"))
    db.commit()
    assert record_self_approval_violation_for_request(db, "expense", "gasto-2", "u", "u", "pm", organization_id="1")
    db.commit()
    with sin_filtro_de_tenant(db):
        assert db.query(SodViolation).filter(SodViolation.context_id == "gasto-2").count() == 0


def test_EL_HALLAZGO_la_bandeja_confirma_la_infraccion_antes_del_403(client, db, admin_token):
    from app.services.approval_engine._base import _record_sod_violation
    _sembrar_sod(client, admin_token)
    yo = _admin(db)
    req = SimpleNamespace(id="req-sod-1", entity_type="invoice", requested_by=yo.id, organization_id="1")
    _record_sod_violation(req, yo, db)
    db.rollback()   # lo que hace el cierre de la sesión tras el 403
    with sin_filtro_de_tenant(db):
        v = db.query(SodViolation).filter(SodViolation.context_id == "req-sod-1").one()
    assert v.organization_id == "1" and v.role == "admin"


def test_EL_HALLAZGO_la_aprobacion_directa_registra_con_el_modulo_grc(client, db, admin_token):
    from app.core.errores import ErrorDeDominio
    from app.services.approval_engine._base import exigir_que_no_sea_suyo
    _sembrar_sod(client, admin_token)
    yo = _admin(db)
    with pytest.raises(ErrorDeDominio) as e:
        exigir_que_no_sea_suyo(db, yo.id, yo, "absence", "aus-1")
    assert e.value.status_code == 403
    with sin_filtro_de_tenant(db):
        v = db.query(SodViolation).filter(SodViolation.context_id == "aus-1").one()
        assert db.get(SodRule, v.rule_id).module_a == "absences"


def test_editar_y_borrar_una_regla_sod_queda_en_la_auditoria_grc(client, db, admin_token):
    _sembrar_sod(client, admin_token)
    regla = client.get("/api/v1/grc/sod-rules", headers=auth(admin_token)).json()["items"][0]
    assert client.patch(f"/api/v1/grc/sod-rules/{regla['id']}", headers=auth(admin_token),
                        json={"is_active": False}).status_code == 200
    assert client.delete(f"/api/v1/grc/sod-rules/{regla['id']}", headers=auth(admin_token)).status_code == 200
    with sin_filtro_de_tenant(db):
        tipos = {e.action_type for e in db.query(GrcAuditLog).filter(GrcAuditLog.resource_id == regla["id"])}
    assert {"sod_rule_updated", "sod_rule_deleted"} <= tipos


# ── 4. Auditoría de cambios de seguridad ──────────────────────────────────────

def test_borrar_una_passkey_se_audita(client, db, admin_token):
    from app.models.mfa import WebAuthnCredential
    cred = WebAuthnCredential(user_id="admin-test-id", organization_id="1", credential_id="cred-grc-1",
                              public_key="x", name="Llave")
    db.add(cred)
    db.commit()
    r = client.delete(f"/api/v1/auth/mfa/webauthn/credentials/{cred.id}", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    filas = _auditado(db, "PASSKEY_REMOVED")
    assert filas and json.loads(filas[0].old_values)["name"] == "Llave"


def test_cambiar_y_borrar_sso_se_audita(client, db, admin_token):
    from app.models.enterprise import SSOConfig
    c = SSOConfig(provider="oidc", organization_id="1", oidc_client_id="x")
    db.add(c)
    db.commit()
    r = client.patch(f"/api/v1/enterprise/sso/{c.id}", headers=auth(admin_token),
                     json={"name": "Entrar", "oidc_client_secret": "s3cr3t"})
    assert r.status_code == 200, r.text
    assert client.delete(f"/api/v1/enterprise/sso/{c.id}", headers=auth(admin_token)).status_code == 200
    cambios = [f for f in _auditado(db, "UPDATE", "sso_configs") if f.resource_id == c.id]
    assert cambios and "s3cr3t" not in (cambios[0].new_values or "")
    assert [f for f in _auditado(db, "DELETE", "sso_configs") if f.resource_id == c.id]


def test_rotar_el_secreto_del_webhook_de_jira_se_audita(client, db, admin_token):
    r = client.post("/api/v1/jira/webhook-secret", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    filas = _auditado(db, "SECRET_ROTATED", "jira_webhook_secret")
    assert filas and r.json()["data"]["secret"] not in json.dumps([[f.new_values, f.metadata_] for f in filas])


def test_el_policy_pack_queda_en_la_auditoria(client, db, admin_token):
    r = client.put("/api/v1/governance/policy-packs/access_baseline", headers=auth(admin_token),
                   json={"is_enabled": False})
    assert r.status_code == 200, r.text
    assert _auditado(db, "UPDATE", "tenant_policy_packs"), "se confirmaba antes de añadir la entrada"


# ── 5. Informe de cumplimiento ────────────────────────────────────────────────

def test_el_informe_cuenta_a_los_miembros_por_pertenencia_y_mide_la_retencion(db):
    from app.models.mfa import Organization
    from app.models.user import UserOrganizationMembership
    from app.services import informe_de_cumplimiento as informe
    def activos():
        c = {c["id"]: c for c in informe.generar(db, "1")["controls"]}
        return c["mfa_coverage"]["measured"]["active_users"], c

    db.add(Organization(id="org-inf", name="Otra", slug="org-inf"))
    db.flush()
    db.get(User, "sub-test-id").organization_id = "org-inf"   # su ficha, en otra empresa
    db.commit()
    sin_pertenencia, _ = activos()
    db.add(UserOrganizationMembership(user_id="sub-test-id", organization_id="1"))
    db.commit()
    con_pertenencia, controles = activos()
    assert con_pertenencia == sin_pertenencia + 1, "un miembro por pertenencia cuenta en la empresa"
    assert controles["retention"]["measured"] == {"active_policies": 0, "active_legal_holds": 0}


# ── 6. Supresión RGPD y cadena de auditoría ───────────────────────────────────

def test_EL_HALLAZGO_la_supresion_no_rompe_la_cadena_de_auditoria(db):
    from app.db import cadena_auditoria
    from app.services.audit import audit_log
    from app.services.supresion_service import suprimir_persona
    persona = db.get(User, "dev-test-id")
    audit_log(db, persona, "UPDATE", "tasks", "t-1", "Tarea")
    db.commit()
    assert cadena_auditoria.verificar(db, "1")["ok"]
    suprimir_persona(db, persona)
    db.commit()
    assert cadena_auditoria.verificar(db, "1")["ok"], "reescribir audit_logs.user_name rompía la cadena"
