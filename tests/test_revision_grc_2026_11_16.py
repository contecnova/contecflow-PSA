"""Revisión GRC 16-11-2026: lo que se arregló, probado por la API.

Cada prueba reproduce el hallazgo (lo que antes pasaba) y comprueba el arreglo:

- reglas SoD: texto libre en módulos, acciones, roles y riesgo; el PATCH era un
  `dict` que ignoraba módulos y acciones; el flujo de mitigación podía ser de
  otra empresa; `/sod-check` callaba las reglas que no puede evaluar; resolver
  dos veces pisaba la resolución;
- evidencias: control sin comprobar, «hash» de la URI, ISO 27001:2013 mezclada
  con 2022 y un «pass» por tener una evidencia aunque el sistema midiera rojo;
- RGPD: tipo libre, persona de otra empresa, plazo fijo de 30 días, «acceso»
  sin copia, sin rechazo, y el informe sin las solicitudes registradas en BI;
- permisos por proyecto: el motivo era una frase en castellano usada como
  clave de traducción.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.session import sin_filtro_de_tenant
from app.models.billing_reports import ApprovalWorkflow, SodRule, SodViolation
from app.models.cab import GDPRRequest, GDPRRequestStatus
from app.models.mfa import Organization
from app.models.user import User, UserRole
from tests.conftest import HASH_DE_PRUEBA, auth

_SOD = "/api/v1/grc/sod-rules"


def _regla(**cambios):
    base = {"module_a": "invoices", "action_a": "crear", "module_b": "invoices", "action_b": "aprobar",
            "risk": "high", "description": "x", "roles_conflict": ["pm"]}
    return {**base, **cambios}


def _otra_empresa(db, org="org-grc-16"):
    with sin_filtro_de_tenant(db):
        if db.get(Organization, org) is None:
            db.add(Organization(id=org, name="Otra", slug=org))
            db.flush()
    return org


# ── Reglas SoD ────────────────────────────────────────────────────────────────

def test_regla_sod_valida_modulo_accion_rol_y_riesgo(client, admin_token):
    h = auth(admin_token)
    assert client.post(_SOD, headers=h, json=_regla(module_a="no-existe")).status_code == 422
    assert client.post(_SOD, headers=h, json=_regla(action_b="firmar")).status_code == 422
    assert client.post(_SOD, headers=h, json=_regla(roles_conflict=["jefazo"])).status_code == 422
    assert client.post(_SOD, headers=h, json=_regla(risk="enorme")).status_code == 422
    assert client.post(_SOD, headers=h, json=_regla(action_b="crear")).status_code == 422, "dos veces la misma operación"
    r = client.post(_SOD, headers=h, json=_regla())
    assert r.status_code == 200, r.text


def test_regla_sod_nace_en_la_empresa_del_admin(client, db, admin_token):
    r = client.post(_SOD, headers=auth(admin_token), json=_regla())
    with sin_filtro_de_tenant(db):
        assert db.get(SodRule, r.json()["data"]["id"]).organization_id == "1"


def test_el_flujo_de_mitigacion_de_otra_empresa_no_se_acepta(client, db, admin_token):
    org = _otra_empresa(db)
    db.add(ApprovalWorkflow(id="wf-ajeno-16", organization_id=org, name="Ajeno", entity_type="expense"))
    db.commit()
    r = client.post(_SOD, headers=auth(admin_token), json=_regla(mitigated_by_workflow_id="wf-ajeno-16"))
    assert r.status_code == 404, r.text


def test_EL_HALLAZGO_editar_los_modulos_de_una_regla_se_guarda(client, admin_token):
    h = auth(admin_token)
    rid = client.post(_SOD, headers=h, json=_regla()).json()["data"]["id"]
    r = client.patch(f"{_SOD}/{rid}", headers=h, json={"module_a": "expenses", "module_b": "expenses"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["module_a"] == "expenses", "antes el PATCH ignoraba módulos y acciones"
    assert client.patch(f"{_SOD}/{rid}", headers=h, json={"risk": "enorme"}).status_code == 422
    assert client.patch(f"{_SOD}/{rid}", headers=h, json={"is_active": "quizá"}).status_code == 422


def test_desactivar_una_regla_antigua_no_exige_revalidarla(client, db, admin_token):
    db.add(SodRule(id="regla-vieja-16", organization_id="1", module_a="modulo_borrado", action_a="crear",
                   module_b="modulo_borrado", action_b="aprobar", risk="high"))
    db.commit()
    r = client.patch(f"{_SOD}/regla-vieja-16", headers=auth(admin_token), json={"is_active": False})
    assert r.status_code == 200, r.text


def test_sod_check_dice_que_reglas_no_puede_evaluar(client, db, admin_token):
    h = auth(admin_token)
    client.get(_SOD, headers=h)   # siembra las reglas por defecto
    with sin_filtro_de_tenant(db):
        facturas = db.query(SodRule).filter(SodRule.organization_id == "1", SodRule.module_a == "invoices",
                                            SodRule.action_b == "aprobar").first()
    data = client.get("/api/v1/grc/sod-check", headers=h).json()["data"]
    assert facturas is not None
    # «aprobar» facturas no es una casilla de la matriz: antes no salía nada y parecía «sin conflictos».
    assert facturas.id in data["not_evaluable_rule_ids"]


def test_resolver_dos_veces_una_violacion_da_409(client, db, admin_token):
    db.add(SodRule(id="regla-v-16", organization_id="1", module_a="expenses", action_a="crear",
                   module_b="expenses", action_b="aprobar"))
    db.add(SodViolation(id="viol-16", organization_id="1", rule_id="regla-v-16", user_id="pm-test-id"))
    db.commit()
    h = auth(admin_token)
    url = "/api/v1/grc/violations/viol-16/resolve"
    assert client.patch(url, headers=h, json={"resolution_note": "primera"}).status_code == 200
    assert client.patch(url, headers=h, json={"resolution_note": "segunda"}).status_code == 409
    with sin_filtro_de_tenant(db):
        db.expire_all()
        assert db.get(SodViolation, "viol-16").resolution_note == "primera"


def test_audit_log_rechaza_una_severidad_desconocida(client, admin_token):
    assert client.get("/api/v1/grc/audit-log", headers=auth(admin_token),
                      params={"severity": "gravisimo"}).status_code == 422


def test_la_matriz_publica_su_vocabulario_de_acciones(client, admin_token):
    from app.core.grc_catalog import GRC_ACTIONS
    data = client.get("/api/v1/grc/permissions", headers=auth(admin_token)).json()["data"]
    assert data["actions"] == list(GRC_ACTIONS)


# ── Marcos y evidencias ───────────────────────────────────────────────────────

_EV = "/api/v1/governance/compliance/evidence"


def test_evidencia_de_un_control_inexistente_da_422(client, admin_token):
    r = client.post(_EV, headers=auth(admin_token), json={
        "framework": "SOC2", "control_id": "SOC2-CC99.9", "evidence_type": "policy", "title": "x"})
    assert r.status_code == 422
    r = client.post(_EV, headers=auth(admin_token), json={
        "framework": "SOC2", "control_id": "SOC2-CC6.1", "evidence_type": "inventado", "title": "x"})
    assert r.status_code == 422


def test_EL_HALLAZGO_el_hash_ya_no_es_el_de_la_uri(client, admin_token):
    h = auth(admin_token)
    r = client.post(_EV, headers=h, json={"framework": "SOC2", "control_id": "SOC2-CC6.1", "evidence_type": "policy",
                                          "title": "x", "artifact_uri": "s3://b/p.pdf"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["artifact_hash"] is None, "antes: sha256 del texto de la URI"
    sha = "AB" * 32
    r = client.post(_EV, headers=h, json={"framework": "SOC2", "control_id": "SOC2-CC6.1", "evidence_type": "policy",
                                          "title": "x", "artifact_sha256": sha})
    assert r.json()["data"]["artifact_hash"] == sha.lower()
    assert client.post(_EV, headers=h, json={"framework": "SOC2", "control_id": "SOC2-CC6.1",
                                             "evidence_type": "policy", "title": "x",
                                             "artifact_sha256": "no-es-un-hash"}).status_code == 422


def test_el_control_iso_2013_cuenta_como_el_de_2022(client, db, admin_token):
    from app.models.governance import ComplianceEvidence
    db.add(ComplianceEvidence(organization_id="1", framework="ISO27001", control_id="ISO27001-A.9.2",
                              evidence_type="policy", title="antigua"))
    db.commit()
    data = client.get("/api/v1/governance/compliance/controls/status", headers=auth(admin_token),
                      params={"framework": "ISO27001"}).json()["data"]
    fila = next(c for c in data["controls"] if c["control_id"] == "ISO27001-A.5.18")
    assert fila["evidence_count"] == 1
    assert all(c["control_id"] != "ISO27001-A.9.2" for c in data["controls"])


def test_EL_HALLAZGO_una_evidencia_no_tapa_un_control_medido_en_rojo(client, db, admin_token):
    db.get(Organization, "1").require_mfa = False
    db.commit()
    h = auth(admin_token)
    client.post(_EV, headers=h, json={"framework": "SOC2", "control_id": "SOC2-CC6.1", "evidence_type": "policy",
                                      "title": "política de MFA"})
    data = client.get("/api/v1/governance/compliance/controls/status", headers=h,
                      params={"framework": "SOC2"}).json()["data"]
    fila = next(c for c in data["controls"] if c["control_id"] == "SOC2-CC6.1")
    assert fila["evidence_count"] >= 1
    assert {"id": "mfa_required", "status": "attention"} in fila["measured"]
    assert fila["status"] == "attention"


def test_marcos_publica_controles_y_tipos(client, admin_token):
    from app.core import marcos_de_cumplimiento as m
    data = client.get("/api/v1/governance/compliance/frameworks", headers=auth(admin_token)).json()["data"]
    assert data["frameworks"] == {k: list(v) for k, v in m.CONTROLES.items()}
    assert data["evidence_types"] == list(m.TIPOS_DE_EVIDENCIA)


def test_los_paquetes_solo_citan_controles_del_catalogo():
    from app.core import marcos_de_cumplimiento as m
    todos = {c for ids in m.CONTROLES.values() for c in ids}
    for clave, paquete in m.PAQUETES.items():
        assert set(paquete["controls"]) <= todos, clave


def test_modulo_de_ia_exige_un_booleano(client, admin_token):
    r = client.patch("/api/v1/governance/config/voice", headers=auth(admin_token), json={"is_enabled": "quizá"})
    assert r.status_code == 422


# ── RGPD ──────────────────────────────────────────────────────────────────────

_RGPD = "/api/v1/gdpr/requests"


def _persona_de_otra(db):
    org = _otra_empresa(db)
    db.add(User(id="ajeno-16", username="ajeno16", email="ajeno16@otra.com", full_name="Ajeno",
                role=UserRole.employee, is_active=True, organization_id=org, hashed_password=HASH_DE_PRUEBA))
    db.commit()


def test_rgpd_valida_tipo_y_persona(client, db, admin_token):
    h = auth(admin_token)
    assert client.post(_RGPD, headers=h, json={"request_type": "olvidame", "subject_email": "a@b.c"}).status_code == 422
    assert client.post(_RGPD, headers=h, json={"request_type": "access"}).status_code == 422, "sin persona ni correo"
    _persona_de_otra(db)
    r = client.post(_RGPD, headers=h, json={"request_type": "erasure", "subject_user_id": "ajeno-16"})
    assert r.status_code == 404, "antes se aceptaba una persona de otra empresa"


def test_rgpd_plazo_sale_del_ajuste(client, db, admin_token):
    from app.services import settings_service
    settings_service.set_runtime_value(db, "audit", "COMPLIANCE_GDPR_MAX_DAYS", 10, "1")
    db.commit()
    settings_service.invalidate_cache()
    r = client.post(_RGPD, headers=auth(admin_token), json={"request_type": "access", "subject_user_id": "dev-test-id"})
    assert r.status_code == 200, r.text
    from app.core import timeutil
    assert r.json()["data"]["deadline"] == str(timeutil.today() + timedelta(days=10))


def test_EL_HALLAZGO_acceso_entrega_una_copia_descargable(client, admin_token):
    h = auth(admin_token)
    rid = client.post(_RGPD, headers=h, json={"request_type": "access", "subject_user_id": "dev-test-id"}).json()["data"]["id"]
    r = client.post(f"{_RGPD}/{rid}/process", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["data"]["user"]["full_name"], "antes «acceso» se completaba sin entregar nada"
    fila = next(x for x in client.get(_RGPD, headers=h).json()["items"] if x["id"] == rid)
    assert fila["status"] == "completed" and fila["has_export"] is True
    d = client.get(f"{_RGPD}/{rid}/export", headers=h)
    assert d.status_code == 200 and "attachment" in d.headers["content-disposition"]
    assert "imputations" in d.json()
    assert client.post(f"{_RGPD}/{rid}/process", headers=h).status_code == 409


def test_rgpd_se_puede_rechazar_con_motivo(client, admin_token):
    h = auth(admin_token)
    rid = client.post(_RGPD, headers=h, json={"request_type": "rectification", "subject_email": "x@y.z"}).json()["data"]["id"]
    assert client.post(f"{_RGPD}/{rid}/reject", headers=h, json={"reason": ""}).status_code == 422
    r = client.post(f"{_RGPD}/{rid}/reject", headers=h, json={"reason": "Identidad no acreditada"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "rejected"
    assert client.post(f"{_RGPD}/{rid}/process", headers=h).status_code == 409
    assert client.get(f"{_RGPD}/{rid}/export", headers=h).status_code == 404


def test_rgpd_de_otra_empresa_no_se_ve_ni_se_procesa(client, db, admin_token):
    org = _otra_empresa(db)
    db.add(GDPRRequest(id="rgpd-ajena-16", organization_id=org, request_type="access",
                       subject_email="z@z.z", status=GDPRRequestStatus.pending))
    db.commit()
    h = auth(admin_token)
    assert all(x["id"] != "rgpd-ajena-16" for x in client.get(_RGPD, headers=h).json()["items"])
    assert client.post(f"{_RGPD}/rgpd-ajena-16/process", headers=h).status_code == 404


def test_EL_HALLAZGO_el_informe_cuenta_las_solicitudes_vencidas_de_bi(db):
    from app.services import bi_gdpr_service as g
    from app.services import informe_de_cumplimiento as informe
    dsr = g.create_dsr(db, subject_id="sujeto-16", request_type="access", org_id="1", requester_user_id="admin")
    todas = g._get_setting(db, g._KEY_DSR, "1", {})
    todas[dsr["id"]]["deadline"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    g._set_setting(db, g._KEY_DSR, "1", todas)
    db.commit()
    c = next(x for x in informe.generar(db, "1")["controls"] if x["id"] == "gdpr_requests")
    assert c["measured"]["bi_overdue"] == 1
    assert c["status"] == "attention", "antes sólo contaban las de gdpr_requests"


# ── Permisos por proyecto ─────────────────────────────────────────────────────

def test_el_motivo_de_proyecto_es_un_codigo_con_mensaje():
    from app.core import permisos_de_proyecto as pp
    assert set(pp.MOTIVOS) == {"project_level_none", "project_viewer_read_only", "project_no_financials",
                               "project_no_export"}
    assert all(" " not in k and " " in v for k, v in pp.MOTIVOS.items())
