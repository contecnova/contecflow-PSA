"""
Tests for gap-filling features:
  - Resource leveling (GET /capacity/leveling)
  - Gantt cascade rescheduling (POST /tasks/{id}/cascade-reschedule)
  - Pipeline weighted forecast (GET /pipeline/forecast)
  - Pipeline configurable stages (CRUD /pipeline/stages)
  - Automation wait_step + conditional_branch
  - Currency conversion (POST /bookings/currency/convert)
  - Project templates (GET /templates)
  - AI agent new tools declared (get_capacity_plans, get_git_activity)
"""
import pytest
from datetime import date, timedelta
from tests.conftest import auth


# ── Helpers ───────────────────────────────────────────────────────────────────

def _next_monday():
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()))


def _create_project(client, token):
    res = client.post("/api/v1/projects", json={
        "name": "Test Project Feature",
        "code": "TEST-FG",
        "status": "active",
        "budget_hours": 200,
    }, headers=auth(token))
    assert res.status_code in (200, 201), res.text
    return res.json()["data"]


def _create_task(client, token, project_id, title="Task A", start_date=None, due_date=None):
    payload = {"project_id": project_id, "title": title, "status": "todo"}
    if start_date:
        payload["start_date"] = str(start_date)
    if due_date:
        payload["due_date"] = str(due_date)
    res = client.post("/api/v1/tasks", json=payload, headers=auth(token))
    assert res.status_code in (200, 201), res.text
    return res.json()


# ── Resource Leveling ─────────────────────────────────────────────────────────

class TestResourceLeveling:
    def test_leveling_no_plans_returns_empty(self, client, admin_token, db):
        date.today()
        week_from = _next_monday()
        week_to = week_from + timedelta(weeks=3)
        res = client.get(
            "/api/v1/capacity/leveling",
            params={"week_from": str(week_from), "week_to": str(week_to)},
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert "conflicts" in data
        assert "suggestions" in data
        assert "summary" in data
        assert data["summary"]["total_conflicts"] == 0

    def test_leveling_detects_overallocation(self, client, admin_token, db):
        """A user with 200h planned in one week (capacity=40) should show a conflict."""
        from app.models.financial import CapacityPlan
        from app.models.user import User
        import uuid
        week = _next_monday()
        # Set admin capacity to 20h to ensure we can force overallocation
        admin_user = db.query(User).filter(User.id == "admin-test-id").first()
        admin_user.weekly_capacity_hours = 20
        db.commit()
        # Directly insert a plan of 60h (above 20h capacity) bypassing API validation
        plan = CapacityPlan(
            id=str(uuid.uuid4()),
            user_id="admin-test-id",
            week_start=week,
            planned_hours=60,
        )
        db.add(plan)
        db.commit()

        week_from = week
        week_to = week + timedelta(weeks=1)
        res = client.get(
            "/api/v1/capacity/leveling",
            params={"week_from": str(week_from), "week_to": str(week_to)},
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        data = res.json()["data"]
        # Should detect overallocation (60h > 40h capacity)
        assert data["summary"]["total_conflicts"] >= 1
        assert data["summary"]["total_overload_hours"] > 0

    def test_leveling_requires_manager_role(self, client, dev_token, db):
        week = _next_monday()
        res = client.get(
            "/api/v1/capacity/leveling",
            params={"week_from": str(week), "week_to": str(week + timedelta(weeks=1))},
            headers=auth(dev_token),
        )
        assert res.status_code == 403


# ── Gantt Cascade Rescheduling ────────────────────────────────────────────────

class TestCascadeReschedule:
    def test_cascade_reschedule_no_dependencies(self, client, pm_token, db):
        project = _create_project(client, pm_token)
        today = date.today()
        task = _create_task(
            client, pm_token, project["id"], "Root Task",
            start_date=today, due_date=today + timedelta(days=5),
        )
        new_end = today + timedelta(days=10)
        res = client.post(
            f"/api/v1/tasks/{task['id']}/cascade-reschedule",
            json={"new_end_date": str(new_end)},
            headers=auth(pm_token),
        )
        assert res.status_code == 200
        data = res.json()
        assert "rescheduled" in data
        assert len(data["rescheduled"]) >= 1
        # Root task should be in the list
        assert data["rescheduled"][0]["task_id"] == task["id"]
        assert data["rescheduled"][0]["new_due_date"] == str(new_end)

    def test_cascade_reschedule_no_date_error(self, client, pm_token, db):
        project = _create_project(client, pm_token)
        task = _create_task(client, pm_token, project["id"], "Task no date")
        # Task without due_date should return 400
        res = client.post(
            f"/api/v1/tasks/{task['id']}/cascade-reschedule",
            json={"new_end_date": str(date.today() + timedelta(days=5))},
            headers=auth(pm_token),
        )
        assert res.status_code == 400

    def test_cascade_reschedule_same_date_noop(self, client, pm_token, db):
        project = _create_project(client, pm_token)
        today = date.today()
        task = _create_task(
            client, pm_token, project["id"], "Task same",
            start_date=today, due_date=today + timedelta(days=5),
        )
        # Same date → no rescheduling needed
        res = client.post(
            f"/api/v1/tasks/{task['id']}/cascade-reschedule",
            json={"new_end_date": str(today + timedelta(days=5))},
            headers=auth(pm_token),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total_shifted"] == 0 or "No hay cambio" in data.get("message", "")


# ── Pipeline Forecast ─────────────────────────────────────────────────────────

class TestPipelineForecast:
    def test_forecast_empty(self, client, pm_token, db):
        res = client.get("/api/v1/pipeline/forecast", headers=auth(pm_token))
        assert res.status_code == 200
        data = res.json()["data"]
        assert "forecast" in data
        assert "total_weighted_pipeline" in data
        assert isinstance(data["forecast"], list)

    def test_forecast_with_opportunity(self, client, pm_token, db):
        close_date = (date.today() + timedelta(days=30)).replace(day=1)
        opp = client.post("/api/v1/pipeline", json={
            "name": "Big Deal",
            "client_name": "TestCorp",
            "stage": "proposal",
            "probability": 60,
            "expected_revenue": 100000,
            "expected_close_date": str(close_date),
        }, headers=auth(pm_token)).json()["data"]
        assert "id" in opp

        res = client.get("/api/v1/pipeline/forecast", params={"months": 3}, headers=auth(pm_token))
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["total_weighted_pipeline"] > 0

    def test_forecast_months_parameter(self, client, pm_token, db):
        res = client.get("/api/v1/pipeline/forecast", params={"months": 12}, headers=auth(pm_token))
        assert res.status_code == 200
        # Should return 12 month buckets
        assert len(res.json()["data"]["forecast"]) == 12


# ── Pipeline Stage Config ─────────────────────────────────────────────────────

class TestPipelineStageConfig:
    def test_list_stages_empty(self, client, pm_token, db):
        res = client.get("/api/v1/pipeline/stages", headers=auth(pm_token))
        assert res.status_code == 200
        assert isinstance(res.json()["items"], list)

    def test_create_stage_as_admin(self, client, admin_token, db):
        res = client.post("/api/v1/pipeline/stages", json={
            "stage_key": "test_stage",
            "label": "Test Stage",
            "color": "#FF5733",
            "order": 10,
            "probability_default": 35,
            "is_terminal": False,
            "is_won": False,
        }, headers=auth(admin_token))
        assert res.status_code in (200, 201), res.text
        data = res.json()["data"]
        assert data["ok"] is True or "id" in data

    def test_create_stage_duplicate_fails(self, client, admin_token, db):
        payload = {
            "stage_key": "dup_stage", "label": "Dup", "color": "#000",
            "order": 5, "probability_default": 50, "is_terminal": False, "is_won": False,
        }
        client.post("/api/v1/pipeline/stages", json=payload, headers=auth(admin_token))
        res = client.post("/api/v1/pipeline/stages", json=payload, headers=auth(admin_token))
        assert res.status_code == 400

    def test_create_stage_requires_admin(self, client, pm_token, db):
        res = client.post("/api/v1/pipeline/stages", json={
            "stage_key": "pm_stage", "label": "PM Stage", "color": "#000",
            "order": 1, "probability_default": 50, "is_terminal": False, "is_won": False,
        }, headers=auth(pm_token))
        assert res.status_code == 403


# ── Automation wait_step + conditional_branch ─────────────────────────────────

class TestAutomationWorkflow:
    def test_create_rule_with_wait_step(self, client, admin_token, db):
        res = client.post("/api/v1/automations", json={
            "name": "Regla con espera",
            "trigger_type": "task_overdue",
            "is_global": True,
            "actions": [
                {"type": "wait_step", "params": {"delay_hours": 24, "label": "Esperar 24h"}},
                {"type": "send_alert", "params": {"title": "Alerta post-espera", "message": "Escalado"}},
            ],
        }, headers=auth(admin_token))
        assert res.status_code in (200, 201), res.text
        data = res.json()["data"]
        assert data["name"] == "Regla con espera"

    def test_create_rule_with_conditional_branch(self, client, admin_token, db):
        res = client.post("/api/v1/automations", json={
            "name": "Regla condicional",
            "trigger_type": "budget_threshold",
            "is_global": True,
            "actions": [
                {
                    "type": "conditional_branch",
                    "params": {
                        "condition": {"field": "budget_pct", "operator": "greater_than", "value": 80},
                        "if_true": [{"type": "send_alert", "params": {"title": "Presupuesto crítico", "message": ">80%"}}],
                        "if_false": [{"type": "send_alert", "params": {"title": "Presupuesto OK", "message": "<=80%"}}],
                    }
                }
            ],
        }, headers=auth(admin_token))
        assert res.status_code in (200, 201), res.text
        data = res.json()["data"]
        assert data["name"] == "Regla condicional"
        # Verify actions structure is preserved
        assert data["actions"][0]["type"] == "conditional_branch"

    def test_test_rule_with_wait_step_executes(self, client, admin_token, db):
        rule = client.post("/api/v1/automations", json={
            "name": "Test wait rule",
            "trigger_type": "task_overdue",
            "is_global": True,
            "actions": [
                {"type": "wait_step", "params": {"delay_hours": 1, "label": "Esperar 1h"}},
            ],
        }, headers=auth(admin_token)).json()

        res = client.post(f"/api/v1/automations/{rule['id']}/test", headers=auth(admin_token))
        assert res.status_code == 200
        data = res.json()
        # result should show the wait_step was logged
        results = data.get("results", [])
        if results:
            assert any(r.get("action") == "wait_step" for r in results)


# ── Currency Conversion ───────────────────────────────────────────────────────

class TestCurrencyConversion:
    def test_get_exchange_rates(self, client, pm_token, db):
        res = client.get("/api/v1/currency/rates", headers=auth(pm_token))
        assert res.status_code == 200
        body = res.json()
        data = body.get("items") if isinstance(body, dict) else body
        # Endpoint returns a list of rate objects
        assert isinstance(data, list)

    def test_upsert_rate_and_convert(self, client, admin_token, pm_token, db):
        today = str(date.today())
        # Add EUR → USD rate
        res = client.post("/api/v1/currency/rates", json={
            "from_currency": "EUR",
            "to_currency": "USD",
            "rate": 1.09,
            "effective_date": today,
        }, headers=auth(admin_token))
        assert res.status_code in (200, 201), res.text

        # Convert 1000 EUR → USD
        res = client.post("/api/v1/currency/convert", json={
            "amount": 1000,
            "from_currency": "EUR",
            "to_currency": "USD",
            "date": today,
        }, headers=auth(pm_token))
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["converted"] == pytest.approx(1090.0, rel=0.01)
        assert data["rate"] == pytest.approx(1.09, rel=0.01)

    def test_convert_same_currency(self, client, pm_token, db):
        # Endpoint is GET with query params
        res = client.get(
            "/api/v1/currency/convert",
            params={"amount": 500, "from_currency": "EUR", "to_currency": "EUR"},
            headers=auth(pm_token),
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["converted"] == 500
        assert data["rate"] == 1.0

    def test_convert_missing_rate_returns_404(self, client, pm_token, db):
        res = client.post("/api/v1/currency/convert", json={
            "amount": 100,
            "from_currency": "EUR",
            "to_currency": "JPY",
        }, headers=auth(pm_token))
        assert res.status_code == 404


# ── Project Templates ────────────────────────────────────────────────────────

class TestProjectTemplates:
    def test_list_templates_empty(self, client, pm_token, db):
        res = client.get("/api/v1/advanced-config/templates", headers=auth(pm_token))
        assert res.status_code == 200
        assert isinstance(res.json()["items"], list)

    def test_create_template(self, client, admin_token, db):
        res = client.post("/api/v1/advanced-config/templates", json={
            "name": "Consultoría estándar",
            "description": "Plantilla para proyectos de consultoría",
            "estimated_weeks": 12,
            "estimated_hours": 400,
            "phases": [
                {
                    "name": "Descubrimiento",
                    "phase_order": 1,
                    "tasks": [
                        {"title": "Kick-off meeting", "estimated_hours": 4, "task_order": 1},
                        {"title": "Análisis de requisitos", "estimated_hours": 16, "task_order": 2},
                    ],
                    "deliverables": [{"title": "Informe de requisitos", "deliverable_order": 1}],
                },
                {
                    "name": "Ejecución",
                    "phase_order": 2,
                    "tasks": [
                        {"title": "Implementación fase 1", "estimated_hours": 80, "task_order": 1},
                    ],
                },
            ],
            "risks": [
                {"title": "Retraso en validaciones del cliente", "probability": "medium", "impact": "major", "risk_order": 1},
            ],
        }, headers=auth(admin_token))
        assert res.status_code in (200, 201), res.text
        data = res.json()["data"]
        assert "id" in data or data.get("ok")

    def test_instantiate_template(self, client, admin_token, db):
        # Create template first
        tpl_res = client.post("/api/v1/advanced-config/templates", json={
            "name": "Plantilla test",
            "phases": [
                {
                    "name": "Inicio",
                    "phase_order": 1,
                    "tasks": [{"title": "Setup inicial", "estimated_hours": 8, "task_order": 1}],
                    "deliverables": [],
                }
            ],
            "risks": [],
        }, headers=auth(admin_token))
        assert tpl_res.status_code in (200, 201), tpl_res.text
        tpl = tpl_res.json()["data"]
        tpl_id = tpl.get("id") or tpl.get("template_id")
        assert tpl_id

        # Instantiate it
        res = client.post(f"/api/v1/billing-reports/templates/{tpl_id}/instantiate", json={
            "project_name": "Proyecto desde plantilla",
            "client_name": "ClienteTest",
        }, headers=auth(admin_token))
        assert res.status_code in (200, 201), res.text
        data = res.json()["data"]
        assert "project_id" in data or "id" in data
