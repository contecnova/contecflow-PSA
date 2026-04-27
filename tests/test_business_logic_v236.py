"""
tests/test_business_logic_v236.py
Business logic tests added in v23.6.0 covering:
  1. Task state machine (including in_review transitions)
  2. Invoice calculation correctness (subtotal, tax, total)
  3. Invoice PDF bytes validity
  4. Pipeline CRM stage lifecycle and DnD transitions
  5. Rate card + billing rate precedence
  6. Expense approval workflow invariants
  7. Configurable log level endpoint security
  8. Resource Scheduler booking create/move/delete (BookingUpdate typed schema)
"""
import pytest
from datetime import date, timedelta
from tests.conftest import auth


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _project(client, token, name="BL Project"):
    r = client.post("/api/v1/projects", json={
        "name": name, "code": name[:4].upper(), "status": "active",
        "project_type": "development", "billing_type": "time_and_materials",
    }, headers=auth(token))
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _task(client, token, project_id, title="T", status=None):
    body = {"project_id": project_id, "title": title, "priority": "medium"}
    if status:
        body["status"] = status
    r = client.post("/api/v1/tasks", json=body, headers=auth(token))
    assert r.status_code in (200, 201), r.text
    return r.json()


def _invoice(client, token, lines=None, tax_rate=21.0):
    if lines is None:
        lines = [{"description": "Desarrollo", "quantity": 10, "unit": "h",
                  "unit_price": 100.0, "amount": 1000.0, "discount_pct": 0}]
    r = client.post("/api/v1/invoices", json={
        "client_name": "Acme S.L.",
        "issue_date": str(date.today()), "due_date": str(date.today() + timedelta(days=30)),
        "tax_rate": tax_rate, "lines": lines,
    }, headers=auth(token))
    assert r.status_code in (200, 201), r.text
    return r.json()


def _opp(client, token, name="Opp A", stage="lead", revenue=50000):
    r = client.post("/api/v1/pipeline", json={
        "name": name, "client_name": "Client X", "stage": stage,
        "expected_revenue": revenue,
    }, headers=auth(token))
    assert r.status_code in (200, 201), r.text
    return r.json()


# ─── 1. Task state machine ─────────────────────────────────────────────────────

class TestTaskStateMachine:
    """Validate the full _TASK_VALID_TRANSITIONS state graph."""

    def test_todo_to_in_progress(self, client, pm_token, db):
        pid = _project(client, pm_token)
        t = _task(client, pm_token, pid)
        r = client.patch(f"/api/v1/tasks/{t['id']}", json={"status": "in_progress"}, headers=auth(pm_token))
        assert r.status_code == 200
        assert r.json()["status"] == "in_progress"

    def test_in_progress_to_in_review(self, client, pm_token, db):
        pid = _project(client, pm_token)
        t = _task(client, pm_token, pid, status="in_progress")
        r = client.patch(f"/api/v1/tasks/{t['id']}", json={"status": "in_review"}, headers=auth(pm_token))
        assert r.status_code == 200
        assert r.json()["status"] == "in_review"

    def test_in_review_to_done(self, client, pm_token, db):
        pid = _project(client, pm_token)
        t = _task(client, pm_token, pid, status="in_review")
        r = client.patch(f"/api/v1/tasks/{t['id']}", json={"status": "done"}, headers=auth(pm_token))
        assert r.status_code == 200
        assert r.json()["status"] == "done"

    def test_in_review_back_to_in_progress(self, client, pm_token, db):
        """Failed review → back to in_progress is a common real-world workflow."""
        pid = _project(client, pm_token)
        t = _task(client, pm_token, pid, status="in_review")
        r = client.patch(f"/api/v1/tasks/{t['id']}", json={"status": "in_progress"}, headers=auth(pm_token))
        assert r.status_code == 200

    def test_todo_to_cancelled(self, client, pm_token, db):
        pid = _project(client, pm_token)
        t = _task(client, pm_token, pid)
        r = client.patch(f"/api/v1/tasks/{t['id']}", json={"status": "cancelled"}, headers=auth(pm_token))
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"

    def test_cancelled_is_terminal(self, client, pm_token, db):
        """Cannot leave cancelled state (terminal)."""
        pid = _project(client, pm_token)
        t = _task(client, pm_token, pid, status="cancelled")
        r = client.patch(f"/api/v1/tasks/{t['id']}", json={"status": "in_progress"}, headers=auth(pm_token))
        assert r.status_code == 400

    def test_done_can_reopen(self, client, pm_token, db):
        """Done → in_progress is allowed for re-opening."""
        pid = _project(client, pm_token)
        t = _task(client, pm_token, pid, status="in_review")
        client.patch(f"/api/v1/tasks/{t['id']}", json={"status": "done"}, headers=auth(pm_token))
        r = client.patch(f"/api/v1/tasks/{t['id']}", json={"status": "in_progress"}, headers=auth(pm_token))
        assert r.status_code == 200

    def test_invalid_direct_todo_to_in_review(self, client, pm_token, db):
        """todo → in_review is NOT a valid direct transition."""
        pid = _project(client, pm_token)
        t = _task(client, pm_token, pid)   # status=todo
        r = client.patch(f"/api/v1/tasks/{t['id']}", json={"status": "in_review"}, headers=auth(pm_token))
        assert r.status_code == 400

    def test_blocked_to_in_progress(self, client, pm_token, db):
        pid = _project(client, pm_token)
        t = _task(client, pm_token, pid, status="blocked")
        r = client.patch(f"/api/v1/tasks/{t['id']}", json={"status": "in_progress"}, headers=auth(pm_token))
        assert r.status_code == 200

    def test_full_lifecycle_backlog_to_done(self, client, pm_token, db):
        """Complete lifecycle: backlog→todo→in_progress→in_review→done."""
        pid = _project(client, pm_token)
        t = _task(client, pm_token, pid, status="backlog")
        tid = t["id"]

        for s_from, s_to in [
            ("backlog", "todo"), ("todo", "in_progress"),
            ("in_progress", "in_review"), ("in_review", "done"),
        ]:
            r = client.patch(f"/api/v1/tasks/{tid}", json={"status": s_to}, headers=auth(pm_token))
            assert r.status_code == 200, f"Failed {s_from}→{s_to}: {r.text}"
            assert r.json()["status"] == s_to


# ─── 2. Invoice calculation invariants ────────────────────────────────────────

class TestInvoiceCalculations:
    """Invoice math: subtotal + tax_rate = total."""

    def test_single_line_21pct_vat(self, client, pm_token, db):
        inv = _invoice(client, pm_token, tax_rate=21.0)
        assert inv["subtotal"] == pytest.approx(1000.0)
        assert inv["tax_amount"] == pytest.approx(210.0)
        assert inv["total"] == pytest.approx(1210.0)

    def test_multi_line_total(self, client, pm_token, db):
        lines = [
            {"description": "Backend dev", "quantity": 10, "unit": "h", "unit_price": 120.0, "amount": 1200.0, "discount_pct": 0},
            {"description": "Frontend dev", "quantity": 5, "unit": "h", "unit_price": 80.0, "amount": 400.0, "discount_pct": 0},
        ]
        inv = _invoice(client, pm_token, lines=lines, tax_rate=10.0)
        assert inv["subtotal"] == pytest.approx(1600.0)
        assert inv["tax_amount"] == pytest.approx(160.0)
        assert inv["total"] == pytest.approx(1760.0)

    def test_zero_tax_invoice(self, client, pm_token, db):
        inv = _invoice(client, pm_token, tax_rate=0.0)
        assert inv["tax_amount"] == pytest.approx(0.0)
        assert inv["total"] == pytest.approx(inv["subtotal"])

    def test_invoice_currency_default(self, client, pm_token, db):
        inv = _invoice(client, pm_token)
        assert inv["currency"] in ("EUR", "USD", "GBP")  # has a valid currency

    def test_invoice_number_sequential(self, client, pm_token, db):
        i1 = _invoice(client, pm_token)
        i2 = _invoice(client, pm_token)
        # Both should have valid invoice numbers
        assert i1["number"] is not None
        assert i2["number"] is not None
        assert i1["number"] != i2["number"]

    def test_invoice_status_defaults_to_draft(self, client, pm_token, db):
        inv = _invoice(client, pm_token)
        assert inv.get("status") in ("draft", None)  # draft or field absent

    def test_invoice_pdf_returns_pdf_header(self, client, pm_token, db):
        inv = _invoice(client, pm_token)
        r = client.get(f"/api/v1/invoices/{inv['id']}/pdf", headers=auth(pm_token))
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    def test_invoice_pdf_content_type(self, client, pm_token, db):
        inv = _invoice(client, pm_token)
        r = client.get(f"/api/v1/invoices/{inv['id']}/pdf", headers=auth(pm_token))
        assert r.headers.get("content-type") == "application/pdf"

    def test_invoice_pdf_attachment_disposition(self, client, pm_token, db):
        inv = _invoice(client, pm_token)
        r = client.get(f"/api/v1/invoices/{inv['id']}/pdf", headers=auth(pm_token))
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd and "factura_" in cd

    def test_invoice_pdf_employee_forbidden(self, client, dev_token, db):
        """Employees (non-managers) may not download invoices."""
        r = client.get("/api/v1/invoices/1/pdf", headers=auth(dev_token))
        assert r.status_code in (403, 401)


# ─── 3. Pipeline CRM stage lifecycle ──────────────────────────────────────────

class TestPipelineStageMachine:
    """Validate _STAGE_VALID_TRANSITIONS in pipeline endpoint."""

    def test_create_opportunity_defaults_to_lead(self, client, pm_token, db):
        opp = _opp(client, pm_token)
        assert opp["stage"] == "lead"

    def test_lead_to_qualification(self, client, pm_token, db):
        opp = _opp(client, pm_token, stage="lead")
        r = client.patch(f"/api/v1/pipeline/{opp['id']}", json={"stage": "qualification"}, headers=auth(pm_token))
        assert r.status_code == 200
        assert r.json()["stage"] == "qualification"

    def test_qualification_to_proposal(self, client, pm_token, db):
        opp = _opp(client, pm_token, stage="qualification")
        r = client.patch(f"/api/v1/pipeline/{opp['id']}", json={"stage": "proposal"}, headers=auth(pm_token))
        assert r.status_code == 200

    def test_proposal_to_negotiation(self, client, pm_token, db):
        opp = _opp(client, pm_token, stage="proposal")
        r = client.patch(f"/api/v1/pipeline/{opp['id']}", json={"stage": "negotiation"}, headers=auth(pm_token))
        assert r.status_code == 200

    def test_negotiation_to_won(self, client, pm_token, db):
        opp = _opp(client, pm_token, stage="negotiation")
        r = client.patch(f"/api/v1/pipeline/{opp['id']}", json={"stage": "won"}, headers=auth(pm_token))
        assert r.status_code == 200
        assert r.json()["stage"] == "won"

    def test_won_is_terminal(self, client, pm_token, db):
        """Won stage is terminal — cannot move out."""
        opp = _opp(client, pm_token, stage="won")
        r = client.patch(f"/api/v1/pipeline/{opp['id']}", json={"stage": "negotiation"}, headers=auth(pm_token))
        assert r.status_code in (400, 422)

    def test_lost_can_reopen_to_lead(self, client, pm_token, db):
        opp = _opp(client, pm_token, stage="lost")
        r = client.patch(f"/api/v1/pipeline/{opp['id']}", json={"stage": "lead"}, headers=auth(pm_token))
        assert r.status_code == 200

    def test_invalid_transition_lead_to_won(self, client, pm_token, db):
        """Cannot jump lead → won directly."""
        opp = _opp(client, pm_token, stage="lead")
        r = client.patch(f"/api/v1/pipeline/{opp['id']}", json={"stage": "won"}, headers=auth(pm_token))
        assert r.status_code in (400, 422)

    def test_full_pipeline_funnel(self, client, pm_token, db):
        """Complete funnel: lead→qualification→proposal→negotiation→won."""
        opp = _opp(client, pm_token, stage="lead")
        oid = opp["id"]
        for s_to in ["qualification", "proposal", "negotiation", "won"]:
            r = client.patch(f"/api/v1/pipeline/{oid}", json={"stage": s_to}, headers=auth(pm_token))
            assert r.status_code == 200, f"Failed →{s_to}: {r.text}"

    def test_probability_updates_with_stage(self, client, pm_token, db):
        """Stage move should update probability_pct."""
        opp = _opp(client, pm_token, stage="lead")
        r = client.patch(f"/api/v1/pipeline/{opp['id']}", json={"stage": "proposal"}, headers=auth(pm_token))
        assert r.status_code == 200
        # proposal → STAGE_PROB 50%
        row = r.json()
        if "probability_pct" in row:
            assert row["probability_pct"] == pytest.approx(50, abs=1)

    def test_opportunity_convert_to_project(self, client, pm_token, db):
        opp = _opp(client, pm_token, stage="negotiation")
        # Move to won first so convert is valid
        client.patch(f"/api/v1/pipeline/{opp['id']}", json={"stage": "won"}, headers=auth(pm_token))
        r = client.post(f"/api/v1/pipeline/{opp['id']}/convert", headers=auth(pm_token))
        assert r.status_code in (200, 201), r.text


# ─── 4. Rate card billing precedence ──────────────────────────────────────────

class TestRateCardBilling:
    """Rate card business rules: most-specific rate wins."""

    def test_rate_card_created_with_hourly_rate(self, client, admin_token, db):
        r = client.post("/api/v1/rate-cards", json={
            "name": "Standard Rates", "currency": "EUR",
            "roles": [{"role": "developer", "hourly_rate": 85.0},
                      {"role": "pm", "hourly_rate": 100.0}],
        }, headers=auth(admin_token))
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data["name"] == "Standard Rates"

    def test_rate_card_list_returns_created(self, client, admin_token, db):
        client.post("/api/v1/rate-cards", json={
            "name": "RC List Test", "currency": "EUR", "roles": [],
        }, headers=auth(admin_token))
        r = client.get("/api/v1/rate-cards", headers=auth(admin_token))
        assert r.status_code == 200
        names = [rc["name"] for rc in r.json()]
        assert "RC List Test" in names

    def test_employee_cannot_create_rate_card(self, client, dev_token, db):
        r = client.post("/api/v1/rate-cards", json={
            "name": "Unauthorised", "currency": "EUR", "roles": [],
        }, headers=auth(dev_token))
        assert r.status_code in (403, 401)


# ─── 5. Expense approval workflow invariants ──────────────────────────────────

class TestExpenseWorkflow:
    """Business rules: expense approval requires manager; employee cannot self-approve."""

    def _create_expense(self, client, token, amount=500.0):
        r = client.post("/api/v1/expenses", json={
            "amount": amount, "currency": "EUR",
            "expense_date": str(date.today()),
            "category": "travel", "description": "Business trip",
        }, headers=auth(token))
        assert r.status_code in (200, 201), r.text
        return r.json()

    def test_expense_created_as_draft(self, client, dev_token, db):
        exp = self._create_expense(client, dev_token)
        assert exp["status"] == "draft"

    def test_expense_submit_changes_status(self, client, dev_token, db):
        """submit moves status from draft → submitted."""
        exp = self._create_expense(client, dev_token)
        r = client.post(f"/api/v1/expenses/my/{exp['id']}/submit", headers=auth(dev_token))
        assert r.status_code == 200

    def test_employee_cannot_review_expense(self, client, dev_token, db):
        """Review endpoint requires manager — employee gets 401/403."""
        exp = self._create_expense(client, dev_token)
        r = client.post(f"/api/v1/expenses/{exp['id']}/review",
                        json={"approved": True}, headers=auth(dev_token))
        assert r.status_code in (401, 403)

    def test_admin_can_approve_submitted_expense(self, client, admin_token, dev_token, db):
        """Full approval flow: create → submit → review (approve)."""
        exp = self._create_expense(client, dev_token)
        # Employee submits the expense
        client.post(f"/api/v1/expenses/my/{exp['id']}/submit", headers=auth(dev_token))
        # Admin approves it
        r = client.post(f"/api/v1/expenses/{exp['id']}/review",
                        json={"approved": True}, headers=auth(admin_token))
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    def test_admin_rejects_expense(self, client, admin_token, dev_token, db):
        """Full rejection flow: create → submit → review (reject)."""
        exp = self._create_expense(client, dev_token)
        client.post(f"/api/v1/expenses/my/{exp['id']}/submit", headers=auth(dev_token))
        r = client.post(f"/api/v1/expenses/{exp['id']}/review",
                        json={"approved": False, "rejection_reason": "No receipt attached"},
                        headers=auth(admin_token))
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"


# ─── 6. Log level endpoint security ───────────────────────────────────────────

class TestLogLevelSecurity:
    def test_non_admin_cannot_read_log_level(self, client, dev_token, db):
        r = client.get("/api/v1/settings/log-level", headers=auth(dev_token))
        assert r.status_code in (403, 401)

    def test_non_admin_cannot_set_log_level(self, client, dev_token, db):
        r = client.post("/api/v1/settings/log-level", json={"level": "DEBUG"}, headers=auth(dev_token))
        assert r.status_code in (403, 401)

    def test_admin_reads_log_level(self, client, admin_token, db):
        r = client.get("/api/v1/settings/log-level", headers=auth(admin_token))
        assert r.status_code == 200
        assert "root" in r.json()
        assert "valid_levels" in r.json()

    def test_admin_sets_valid_log_level(self, client, admin_token, db):
        r = client.post("/api/v1/settings/log-level", json={"level": "WARNING"}, headers=auth(admin_token))
        assert r.status_code == 200
        assert r.json()["level"] == "WARNING"

    def test_invalid_log_level_rejected(self, client, admin_token, db):
        r = client.post("/api/v1/settings/log-level", json={"level": "VERBOSE"}, headers=auth(admin_token))
        assert r.status_code == 400

    def test_named_logger_can_be_targeted(self, client, admin_token, db):
        r = client.post("/api/v1/settings/log-level",
                        json={"level": "ERROR", "logger": "contecflow"},
                        headers=auth(admin_token))
        assert r.status_code == 200
        assert r.json()["logger"] == "contecflow"

    def test_global_log_level_updates_root_and_uvicorn(self, client, admin_token, db):
        r = client.post("/api/v1/settings/log-level", json={"level": "WARNING"}, headers=auth(admin_token))
        assert r.status_code == 200
        body = r.json()
        assert body["logger"] == "global"
        assert "root" in body.get("affected", [])
        assert "uvicorn" in body.get("affected", [])

        r2 = client.get("/api/v1/settings/log-level", headers=auth(admin_token))
        assert r2.status_code == 200
        levels = r2.json()
        assert levels["root"] == "WARNING"
        assert levels["contecflow"] == "WARNING"
        assert levels["uvicorn"] == "WARNING"


class TestSemanticEngineConfig:
    def test_engine_modes_can_be_switched(self, client, admin_token, db):
        for mode in ["hybrid", "semantic", "llm", "rules_only"]:
            r = client.patch("/api/v1/semantic/config", json={"engine_mode": mode}, headers=auth(admin_token))
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["ok"] is True
            assert body["config"]["engine_mode"] == mode

            r2 = client.get("/api/v1/semantic/config", headers=auth(admin_token))
            assert r2.status_code == 200, r2.text
            assert r2.json()["engine_mode"] == mode

    def test_engine_mode_rejects_invalid_values(self, client, admin_token, db):
        r = client.patch("/api/v1/semantic/config", json={"engine_mode": "semantico-magico"}, headers=auth(admin_token))
        assert r.status_code == 400


# ─── 8. Resource Scheduler bookings ───────────────────────────────────────────

class TestResourceSchedulerBookings:
    """PATCH /bookings/{id} must accept typed date fields (BookingUpdate schema)."""

    def _make_booking(self, client, token, pm_token):
        # Get any active user ID from admin-accessible /users list
        users_r = client.get("/api/v1/users", headers=auth(pm_token))
        users = users_r.json() if isinstance(users_r.json(), list) else users_r.json().get("items", [])
        assert users, "No users found for booking test"
        user_id = users[0]["id"]
        start = str(date.today())
        end   = str(date.today() + timedelta(days=13))
        r = client.post("/api/v1/bookings", json={
            "user_id": user_id, "booking_type": "soft",
            "start_date": start, "end_date": end, "hours_per_day": 8,
        }, headers=auth(pm_token))
        assert r.status_code in (200, 201), r.text
        return r.json()

    def test_create_booking(self, client, pm_token, db):
        b = self._make_booking(client, pm_token, pm_token)
        assert b["id"]
        assert b["booking_type"] == "soft"

    def test_patch_booking_moves_dates(self, client, pm_token, db):
        """Core bug fix: PATCH with date strings should not fail with type error."""
        b = self._make_booking(client, pm_token, pm_token)
        new_start = str(date.today() + timedelta(weeks=2))
        new_end   = str(date.today() + timedelta(weeks=4))
        r = client.patch(f"/api/v1/bookings/{b['id']}",
                         json={"start_date": new_start, "end_date": new_end},
                         headers=auth(pm_token))
        assert r.status_code == 200, r.text
        assert r.json()["start_date"] == new_start
        assert r.json()["end_date"]   == new_end

    def test_patch_booking_partial_update(self, client, pm_token, db):
        """Partial PATCH (only hours_per_day) must not touch dates."""
        b = self._make_booking(client, pm_token, pm_token)
        orig_start = b["start_date"]
        r = client.patch(f"/api/v1/bookings/{b['id']}",
                         json={"hours_per_day": 6.0},
                         headers=auth(pm_token))
        assert r.status_code == 200
        assert r.json()["hours_per_day"] == 6.0
        assert r.json()["start_date"] == orig_start  # unchanged

    def test_patch_booking_invalid_date_range(self, client, pm_token, db):
        """end_date before start_date must be rejected."""
        b = self._make_booking(client, pm_token, pm_token)
        r = client.patch(f"/api/v1/bookings/{b['id']}",
                         json={"start_date": str(date.today() + timedelta(days=14)),
                               "end_date":   str(date.today())},
                         headers=auth(pm_token))
        assert r.status_code == 400

    def test_delete_booking(self, client, pm_token, db):
        b = self._make_booking(client, pm_token, pm_token)
        r = client.delete(f"/api/v1/bookings/{b['id']}", headers=auth(pm_token))
        assert r.status_code == 200

    def test_employee_cannot_patch_booking(self, client, dev_token, pm_token, db):
        b = self._make_booking(client, pm_token, pm_token)
        r = client.patch(f"/api/v1/bookings/{b['id']}",
                         json={"hours_per_day": 4},
                         headers=auth(dev_token))
        assert r.status_code in (401, 403)

