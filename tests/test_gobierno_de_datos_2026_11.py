"""Data Governance: auditoría real, formularios que guardan y plazo RGPD de Admin (revisión 2026-11).

Medido antes:
- ningún acceso real a datos de BI quedaba auditado; sólo un botón de consola
  escribía un evento inventado en un JSON de `app_settings`;
- el linaje pedía un SQL que la pantalla no manda (422);
- el plazo de una solicitud RGPD era una constante de 30 días.
"""
from __future__ import annotations

from datetime import datetime

from app.models.enterprise import AuditLog
from app.services import bi_gdpr_service, settings_service
from tests.conftest import auth

CONSULTA = {"entity": "projects", "columns": ["code", "name"]}


def test_EL_HALLAZGO_ver_y_exportar_un_informe_queda_auditado(client, admin_token, db):
    assert client.post("/api/v1/reports/preview", headers=auth(admin_token), json=CONSULTA).status_code == 200
    assert client.post("/api/v1/reports/export", headers=auth(admin_token), json=CONSULTA).status_code == 200
    acciones = {f.action for f in db.query(AuditLog).filter(AuditLog.resource == "bi:report").all()}
    assert {"VIEW", "EXPORT"} <= acciones
    r = client.get("/api/v1/bi/governance/audit/access", headers=auth(admin_token), params={"entity_type": "report"})
    assert r.status_code == 200, r.text
    assert {i["action"] for i in r.json()["data"]["items"]} >= {"view", "export"}


def test_EL_HALLAZGO_no_se_escriben_eventos_de_auditoria_a_mano(client, admin_token):
    r = client.post("/api/v1/bi/governance/audit/access", headers=auth(admin_token),
                    json={"entity_type": "x", "entity_id": "y", "action": "view"})
    assert r.status_code in (404, 405)


def test_EL_HALLAZGO_el_linaje_se_registra_sin_sql(client, admin_token):
    r = client.post("/api/v1/bi/governance/lineage", headers=auth(admin_token),
                    json={"source_table": "imputations", "target_table": "fact_hours"})
    assert r.status_code == 200, r.text


def test_EL_HALLAZGO_el_plazo_rgpd_sale_de_admin(db):
    settings_service.set_runtime_value(db, "audit", "COMPLIANCE_GDPR_MAX_DAYS", 10, "1")
    dsr = bi_gdpr_service.create_dsr(db, org_id="1", subject_id="dev-test-id", request_type="erasure",
                                     requester_user_id="admin-test-id", notes=None)
    dias = (datetime.fromisoformat(dsr["deadline"]) - datetime.fromisoformat(dsr["created_at"])).days
    assert dias == 10
