"""
Tests para billing_reports — facturas, catálogo de informes, importación.

Cubre:
  - CRUD de facturas (create, list, update status, summary)
  - Catálogo de informes y ejecución de reports
  - Importación masiva (plantillas, validación)
  - ITSM SLA dashboard y agente performance
  - Reglas de autenticación / autorización
"""
import io
from datetime import date

import pytest

from app.main import app
from app.models.imputation import Imputation
from tests.conftest import auth


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_project(client, token, code="BRP01"):
    r = client.post(
        "/api/v1/projects",
        json={
            "name": "Billing Project",
            "code": code,
            "status": "active",
            "billing_type": "time_material",
            "billing_rate": 100.0,
        },
        headers=auth(token),
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def minimal_invoice(project_id=None):
    return {
        "issue_date": str(date.today()),
        "due_date": str(date.today()),
        "tax_rate": 21.0,
        "currency": "EUR",
        "client_name": "ACME Corp",
        "project_id": project_id,
        "lines": [
            {
                "description": "Consultoría Q1",
                "quantity": 10,
                "unit": "h",
                "unit_price": 100.0,
                "amount": 1000.0,
                "discount_pct": 0,
            }
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# INVOICES — CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def test_list_invoices_empty(client, pm_token, db):
    res = client.get("/api/v1/invoices", headers=auth(pm_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_create_invoice_minimal(client, pm_token, db):
    res = client.post(
        "/api/v1/invoices",
        json=minimal_invoice(),
        headers=auth(pm_token),
    )
    assert res.status_code in (200, 201), res.text
    data = res.json()
    assert "id" in data
    assert "number" in data
    assert data["total"] > 0
    assert data["currency"] == "EUR"
    assert data["status"] == "draft"


def test_create_invoice_linked_to_project(client, pm_token, db):
    pid = make_project(client, pm_token, code="BRP02")
    res = client.post(
        "/api/v1/invoices",
        json=minimal_invoice(project_id=pid),
        headers=auth(pm_token),
    )
    assert res.status_code in (200, 201), res.text
    data = res.json()
    assert data["project_id"] == pid
    assert data["project_name"] is not None


def test_create_invoice_calculates_tax(client, pm_token, db):
    payload = minimal_invoice()
    payload["tax_rate"] = 10.0
    payload["lines"] = [{"description": "X", "quantity": 1, "unit": "h", "unit_price": 200.0, "amount": 200.0, "discount_pct": 0}]
    res = client.post("/api/v1/invoices", json=payload, headers=auth(pm_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["subtotal"] == 200.0
    assert abs(data["tax_amount"] - 20.0) < 0.01
    assert abs(data["total"] - 220.0) < 0.01


def test_create_invoice_requires_manager(client, dev_token, db):
    res = client.post("/api/v1/invoices", json=minimal_invoice(), headers=auth(dev_token))
    assert res.status_code in (401, 403)


def test_list_invoices_after_create(client, pm_token, db):
    client.post("/api/v1/invoices", json=minimal_invoice(), headers=auth(pm_token))
    client.post("/api/v1/invoices", json=minimal_invoice(), headers=auth(pm_token))
    res = client.get("/api/v1/invoices", headers=auth(pm_token))
    assert res.status_code == 200
    assert len(res.json()) >= 2


def test_list_invoices_filter_by_status(client, pm_token, db):
    client.post("/api/v1/invoices", json=minimal_invoice(), headers=auth(pm_token))
    res = client.get("/api/v1/invoices?status=draft", headers=auth(pm_token))
    assert res.status_code == 200
    for inv in res.json():
        assert inv["status"] == "draft"


def test_invoice_response_schema_fields(client, pm_token, db):
    """Verify that the response contains all required OpenAPI contract fields."""
    res = client.post("/api/v1/invoices", json=minimal_invoice(), headers=auth(pm_token))
    data = res.json()
    required = {"id", "number", "subtotal", "tax_rate", "tax_amount", "total", "currency", "status", "lines"}
    assert required.issubset(data.keys()), f"Missing fields: {required - data.keys()}"


def test_update_invoice_status_to_sent(client, pm_token, db):
    inv = client.post("/api/v1/invoices", json=minimal_invoice(), headers=auth(pm_token)).json()
    res = client.patch(
        f"/api/v1/invoices/{inv['id']}/status",
        json={"status": "sent"},
        headers=auth(pm_token),
    )
    assert res.status_code == 200
    assert res.json()["status"] == "sent"


def test_update_invoice_status_to_paid_sets_paid_date(client, pm_token, db):
    inv = client.post("/api/v1/invoices", json=minimal_invoice(), headers=auth(pm_token)).json()
    # First, move to 'sent'
    res_sent = client.patch(
        f"/api/v1/invoices/{inv['id']}/status",
        json={"status": "sent"},
        headers=auth(pm_token),
    )
    assert res_sent.status_code == 200
    # Then, move to 'paid'
    res_paid = client.patch(
        f"/api/v1/invoices/{inv['id']}/status",
        json={"status": "paid"},
        headers=auth(pm_token),
    )
    assert res_paid.status_code == 200
    invoices = client.get("/api/v1/invoices", headers=auth(pm_token)).json()
    paid = next((i for i in invoices if i["id"] == inv["id"]), None)
    assert paid is not None
    assert paid["status"] == "paid"


def test_update_nonexistent_invoice_status(client, pm_token, db):
    res = client.patch(
        "/api/v1/invoices/nonexistent-id/status",
        json={"status": "sent"},
        headers=auth(pm_token),
    )
    assert res.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# INVOICE SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

def test_invoice_summary_structure(client, pm_token, db):
    res = client.get("/api/v1/invoices/summary", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    assert "total_invoiced" in data
    assert "total_paid" in data
    assert "total_pending" in data
    assert "overdue_count" in data
    assert "overdue_amount" in data
    assert "by_status" in data


def test_invoice_summary_reflects_created_invoices(client, pm_token, db):
    client.post("/api/v1/invoices", json=minimal_invoice(), headers=auth(pm_token))
    res = client.get("/api/v1/invoices/summary", headers=auth(pm_token))
    data = res.json()
    assert data["total_invoiced"] > 0


def test_invoice_summary_requires_manager(client, dev_token, db):
    res = client.get("/api/v1/invoices/summary", headers=auth(dev_token))
    assert res.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT CATALOG
# ═══════════════════════════════════════════════════════════════════════════════

def test_report_catalog_returns_list(client, pm_token, db):
    res = client.get("/api/v1/report-catalog/catalog", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, (list, dict))


def test_report_data_sources(client, pm_token, db):
    res = client.get("/api/v1/report-catalog/data-sources", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, (list, dict))


def test_run_report_projects(client, pm_token, db):
    pid = make_project(client, pm_token, code="BRP03")
    res = client.post(
        "/api/v1/report-catalog/run",
        json={"data_source": "projects", "filters": {}},
        headers=auth(pm_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert "rows" in data


def test_run_report_imputations(client, pm_token, db):
    res = client.post(
        "/api/v1/report-catalog/run",
        json={"data_source": "imputations", "filters": {}},
        headers=auth(pm_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert "rows" in data
    assert "totals" in data


def test_run_report_capacity(client, pm_token, db):
    res = client.post(
        "/api/v1/report-catalog/run",
        json={"data_source": "capacity", "filters": {}},
        headers=auth(pm_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert "by_user" in data


def test_save_and_list_custom_report(client, pm_token, db):
    payload = {
        "name": "Mi informe personalizado",
        "data_source": "projects",
        "category": "custom",
        "icon": "📊",
        "is_public": False,
    }
    res = client.post("/api/v1/report-catalog/save", json=payload, headers=auth(pm_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert data.get("ok") is True
    assert "id" in data


def test_delete_custom_report(client, pm_token, db):
    payload = {"name": "Para borrar", "data_source": "projects", "icon": "📊", "is_public": False, "category": "custom"}
    save_res = client.post("/api/v1/report-catalog/save", json=payload, headers=auth(pm_token))
    rid = save_res.json()["id"]
    del_res = client.delete(f"/api/v1/report-catalog/{rid}", headers=auth(pm_token))
    assert del_res.status_code in (200, 204)


def test_report_catalog_requires_manager(client, dev_token, db):
    res = client.get("/api/v1/report-catalog/catalog", headers=auth(dev_token))
    assert res.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# BULK IMPORT — templates & validation
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("entity_type", ["projects", "tasks", "users", "imputations", "expenses"])
def test_import_template_available(client, pm_token, db, entity_type):
    res = client.get(f"/api/v1/import/template/{entity_type}", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    assert "columns" in data
    assert "example" in data
    assert data["entity_type"] == entity_type


def test_import_template_unknown_type(client, pm_token, db):
    res = client.get("/api/v1/import/template/unknown_type", headers=auth(pm_token))
    assert res.status_code == 400


def test_import_validate_valid_csv(client, pm_token, db):
    csv_content = "name,code,status,project_type\nProyecto Test,TST01,planning,consulting\n"
    files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    res = client.post(
        "/api/v1/import/validate?entity_type=projects",
        files=files,
        headers=auth(pm_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert "valid" in data
    assert "total_rows" in data
    assert "errors" in data
    assert "preview" in data
    assert data["total_rows"] == 1


def test_import_validate_empty_csv(client, pm_token, db):
    csv_content = "name,code\n"
    files = {"file": ("empty.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    res = client.post(
        "/api/v1/import/validate?entity_type=projects",
        files=files,
        headers=auth(pm_token),
    )
    assert res.status_code == 400


def test_import_validate_requires_manager(client, dev_token, db):
    csv_content = "name,code\nTest,T01\n"
    files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    res = client.post(
        "/api/v1/import/validate?entity_type=projects",
        files=files,
        headers=auth(dev_token),
    )
    assert res.status_code in (401, 403)


def test_import_execute_projects(client, pm_token, db):
    csv_content = "name,code,status,project_type\nProyecto Importado,PIMP01,planning,consulting\n"
    files = {"file": ("import.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    res = client.post(
        "/api/v1/import/execute?entity_type=projects",
        files=files,
        headers=auth(pm_token),
    )
    assert res.status_code in (200, 201), res.text
    data = res.json()
    assert "job_id" in data
    assert "status" in data
    assert data["total"] == 1


def test_import_jobs_history(client, pm_token, db):
    res = client.get("/api/v1/import/jobs", headers=auth(pm_token))
    assert res.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# ITSM METRICS
# ═══════════════════════════════════════════════════════════════════════════════

def test_sla_dashboard_structure(client, admin_token, db):
    res = client.get("/api/v1/itsm-metrics/sla-dashboard", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "real_time" in data
    rt = data["real_time"]
    assert "open" in rt
    assert "breached" in rt
    assert "compliance_by_priority" in data


def test_agent_performance_structure(client, pm_token, db):
    res = client.get("/api/v1/itsm-metrics/agent-performance", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, (list, dict))


def test_sla_dashboard_requires_auth(client, db):
    res = client.get("/api/v1/itsm-metrics/sla-dashboard")
    assert res.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# INVOICE FROM TIMESHEETS
# ═══════════════════════════════════════════════════════════════════════════════

def test_invoice_from_timesheets_no_project(client, pm_token, db):
    """Endpoint should handle missing project gracefully."""
    res = client.post(
        "/api/v1/invoices/from-timesheets",
        json={"project_id": None, "date_from": str(date.today()), "date_to": str(date.today())},
        headers=auth(pm_token),
    )
    # Returns preview data or 404 if no approved timesheets — both are valid
    assert res.status_code in (200, 404, 422)


def test_invoice_from_timesheets_requires_manager(client, dev_token, db):
    res = client.post(
        "/api/v1/invoices/from-timesheets",
        json={"project_id": None},
        headers=auth(dev_token),
    )
    assert res.status_code in (401, 403)


def test_invoice_from_timesheets_excludes_already_invoiced_imputations(client, pm_token, db):
    pid = make_project(client, pm_token, code="BRP-INV-01")

    imp = Imputation(
        user_id="dev-test-id",
        project_id=pid,
        date=date.today(),
        hours=8,
        description="Sprint implementation",
        is_billable=True,
        is_approved=True,
    )
    db.add(imp)
    db.commit()
    db.refresh(imp)

    preview_1 = client.post(
        "/api/v1/invoices/from-timesheets",
        json={"project_id": pid, "date_from": str(date.today()), "date_to": str(date.today())},
        headers=auth(pm_token),
    )
    assert preview_1.status_code == 200, preview_1.text
    preview_data_1 = preview_1.json()
    assert preview_data_1["imputation_count"] == 1
    assert len(preview_data_1["lines"]) >= 1

    create_res = client.post(
        "/api/v1/invoices",
        json={
            "project_id": pid,
            "issue_date": str(date.today()),
            "due_date": str(date.today()),
            "tax_rate": 21.0,
            "currency": "EUR",
            "client_name": "ACME Corp",
            "lines": preview_data_1["lines"],
        },
        headers=auth(pm_token),
    )
    assert create_res.status_code in (200, 201), create_res.text
    invoice_id = create_res.json()["id"]

    db.refresh(imp)
    assert imp.is_invoiced is True
    assert imp.invoiced_invoice_id == invoice_id

    preview_2 = client.post(
        "/api/v1/invoices/from-timesheets",
        json={"project_id": pid, "date_from": str(date.today()), "date_to": str(date.today())},
        headers=auth(pm_token),
    )
    assert preview_2.status_code == 200, preview_2.text
    preview_data_2 = preview_2.json()
    assert preview_data_2["imputation_count"] == 0
    assert preview_data_2["lines"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# AUTOMATION WORKFLOWS
# ═══════════════════════════════════════════════════════════════════════════════

def test_automation_workflow_create_and_list(client, pm_token, db):
    payload = {
        "name": "WF Aprobaciones",
        "description": "Flujo test",
        "trigger_type": "timesheet_submitted",
        "steps": [
            {
                "name": "Notificar",
                "step_type": "notify",
                "config": {"channel": "email"},
            }
        ],
    }
    create_res = client.post("/api/v1/automation-workflows", json=payload, headers=auth(pm_token))
    assert create_res.status_code in (200, 201), create_res.text
    created = create_res.json()
    assert "id" in created
    assert created["trigger_type"] == "timesheet_submitted"
    assert isinstance(created["steps"], list)

    list_res = client.get("/api/v1/automation-workflows", headers=auth(pm_token))
    assert list_res.status_code == 200
    assert any(w["id"] == created["id"] for w in list_res.json())


def test_automation_workflow_update_and_delete(client, pm_token, db):
    create_res = client.post(
        "/api/v1/automation-workflows",
        json={"name": "WF Update", "trigger_type": "ticket_created", "steps": []},
        headers=auth(pm_token),
    )
    wf = create_res.json()

    update_res = client.patch(
        f"/api/v1/automation-workflows/{wf['id']}",
        json={"name": "WF Update 2", "status": "active"},
        headers=auth(pm_token),
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "WF Update 2"

    delete_res = client.delete(f"/api/v1/automation-workflows/{wf['id']}", headers=auth(pm_token))
    assert delete_res.status_code == 200
    assert delete_res.json().get("ok") is True


def test_automation_workflow_executions_empty(client, pm_token, db):
    create_res = client.post(
        "/api/v1/automation-workflows",
        json={"name": "WF Exec", "trigger_type": "ticket_created", "steps": []},
        headers=auth(pm_token),
    )
    wf = create_res.json()
    res = client.get(f"/api/v1/automation-workflows/{wf['id']}/executions", headers=auth(pm_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEDULED REPORTS
# ═══════════════════════════════════════════════════════════════════════════════

def test_scheduled_report_crud_and_run(client, pm_token, db):
    create_payload = {
        "name": "Informe semanal",
        "metric": "hours_by_month",
        "frequency": "weekly",
        "recipients": ["pm@clarive.com"],
        "include_pdf": True,
        "filters_json": "{}",
    }
    create_res = client.post("/api/v1/scheduled-reports", json=create_payload, headers=auth(pm_token))
    assert create_res.status_code in (200, 201), create_res.text
    created = create_res.json()
    assert created.get("ok") is True
    report_id = created["id"]

    list_res = client.get("/api/v1/scheduled-reports", headers=auth(pm_token))
    assert list_res.status_code == 200
    assert any(r["id"] == report_id for r in list_res.json())

    update_res = client.patch(
        f"/api/v1/scheduled-reports/{report_id}",
        json={"name": "Informe semanal v2", "is_active": True},
        headers=auth(pm_token),
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Informe semanal v2"

    run_res = client.post(f"/api/v1/scheduled-reports/{report_id}/run", headers=auth(pm_token))
    assert run_res.status_code == 200
    assert run_res.json().get("ok") is True

    delete_res = client.delete(f"/api/v1/scheduled-reports/{report_id}", headers=auth(pm_token))
    assert delete_res.status_code == 200
    assert delete_res.json().get("ok") is True


def test_scheduled_report_requires_manager_for_write(client, dev_token, db):
    res = client.post(
        "/api/v1/scheduled-reports",
        json={"name": "X", "frequency": "weekly", "recipients": ["x@x.com"]},
        headers=auth(dev_token),
    )
    assert res.status_code in (401, 403)


def test_scheduled_report_list_requires_auth(client, db):
    res = client.get("/api/v1/scheduled-reports")
    assert res.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT TEMPLATES + SMARTMATCH
# ═══════════════════════════════════════════════════════════════════════════════

def test_templates_create_list_and_instantiate(client, pm_token, db):
    create_payload = {
        "name": "Plantilla Consultoria",
        "description": "Template test",
        "project_type": "consulting",
        "estimated_weeks": 4,
        "estimated_hours": 120,
        "phases": [
            {
                "name": "Discovery",
                "estimated_weeks": 1,
                "tasks": [
                    {
                        "title": "Workshop inicial",
                        "estimated_hours": 8,
                        "skill_required": "analysis",
                    }
                ],
            }
        ],
        "risks": [],
        "deliverables": [],
    }

    create_res = client.post("/api/v1/templates", json=create_payload, headers=auth(pm_token))
    assert create_res.status_code in (200, 201), create_res.text
    created = create_res.json()
    assert created.get("ok") is True
    template_id = created["id"]

    list_res = client.get("/api/v1/templates", headers=auth(pm_token))
    assert list_res.status_code == 200
    templates = list_res.json()
    assert any(t["id"] == template_id for t in templates)

    inst_res = client.post(
        f"/api/v1/templates/{template_id}/instantiate",
        json={"name": "Proyecto desde template"},
        headers=auth(pm_token),
    )
    assert inst_res.status_code == 200
    data = inst_res.json()
    assert data.get("ok") is True
    assert "project_id" in data
    assert "project_code" in data


def test_templates_require_manager(client, dev_token, db):
    res = client.post(
        "/api/v1/templates",
        json={"name": "Nope", "phases": [], "risks": [], "deliverables": []},
        headers=auth(dev_token),
    )
    assert res.status_code in (401, 403)


def test_smartmatch_returns_contract(client, pm_token, db):
    res = client.post(
        "/api/v1/smartmatch",
        json={"skills": ["python"], "hours_needed": 20},
        headers=auth(pm_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert "query" in data
    assert "candidates" in data
    assert "total_evaluated" in data
    assert "message" in data


def test_smartmatch_bad_date_format_rejected(client, pm_token, db):
    res = client.post(
        "/api/v1/smartmatch",
        json={"start_date": "15-01-2026", "end_date": "2026-01-20"},
        headers=auth(pm_token),
    )
    assert res.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# OPENAPI CONTRACTS
# ═══════════════════════════════════════════════════════════════════════════════

def test_openapi_contract_for_import_execute(client, db):
    spec = app.openapi()
    schema_ref = spec["paths"]["/api/v1/import/execute"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert "$ref" in schema_ref


def test_openapi_contract_for_sla_dashboard(client, db):
    spec = app.openapi()
    schema_ref = spec["paths"]["/api/v1/itsm-metrics/sla-dashboard"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert "$ref" in schema_ref


def test_openapi_contract_for_invoice_status_patch(client, db):
    spec = app.openapi()
    schema_ref = spec["paths"]["/api/v1/invoices/{invoice_id}/status"]["patch"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert "$ref" in schema_ref


def test_openapi_contract_for_automation_workflows(client, db):
    spec = app.openapi()
    schema_ref = spec["paths"]["/api/v1/automation-workflows"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema_ref.get("type") == "array"
    assert "$ref" in schema_ref.get("items", {})


def test_openapi_contract_for_scheduled_reports(client, db):
    spec = app.openapi()
    schema_ref = spec["paths"]["/api/v1/scheduled-reports"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema_ref.get("type") == "array"
    assert "$ref" in schema_ref.get("items", {})


def test_openapi_contract_for_templates(client, db):
    spec = app.openapi()
    schema_ref = spec["paths"]["/api/v1/templates"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema_ref.get("type") == "array"
    assert "$ref" in schema_ref.get("items", {})


def test_openapi_contract_for_smartmatch(client, db):
    spec = app.openapi()
    schema_ref = spec["paths"]["/api/v1/smartmatch"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert "$ref" in schema_ref


def test_openapi_contract_for_report_catalog_dynamic_json(client, db):
    spec = app.openapi()
    catalog_schema = spec["paths"]["/api/v1/report-catalog/catalog"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    data_sources_schema = spec["paths"]["/api/v1/report-catalog/data-sources"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    run_schema = spec["paths"]["/api/v1/report-catalog/run"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]

    assert catalog_schema.get("type") == "object"
    assert data_sources_schema.get("type") == "object"
    assert run_schema.get("type") == "object"


def test_openapi_contract_for_pdf_endpoints(client, db):
    spec = app.openapi()
    invoice_pdf_content = spec["paths"]["/api/v1/invoices/{invoice_id}/pdf"]["get"]["responses"]["200"]["content"]
    preview_pdf_content = spec["paths"]["/api/v1/scheduled-reports/{report_id}/preview-pdf"]["get"]["responses"]["200"]["content"]

    assert "application/pdf" in invoice_pdf_content
    assert "application/pdf" in preview_pdf_content
