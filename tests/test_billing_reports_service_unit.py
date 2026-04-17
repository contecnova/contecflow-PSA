"""
Unit tests for billing_reports_service.py

Cubre las funciones puras y de negocio del servicio directamente,
sin pasar por la capa HTTP, usando mocks o fixtures de BD en memoria.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.services.billing_reports_service import (
    business_minutes_between,
    get_invoice_summary,
    next_invoice_number,
    run_system_report,
    serialize_workflow,
    serialize_scheduled_report,
    validate_import_csv,
)


# ─────────────────────────────────────────────────────────────────────────────
# business_minutes_between — pure function, no DB needed
# ─────────────────────────────────────────────────────────────────────────────

class TestBusinessMinutesBetween:
    """Pure-function tests for the SLA business-minutes calculator."""

    def _dt(self, day_offset: int = 0, hour: int = 9, minute: int = 0) -> datetime:
        """Return a Monday (2026-04-20) + offset at the given time, UTC."""
        base = datetime(2026, 4, 20, hour, minute, 0, tzinfo=timezone.utc)  # Monday
        return base + timedelta(days=day_offset)

    def test_same_moment_returns_zero(self):
        dt = self._dt()
        assert business_minutes_between(dt, dt) == 0

    def test_end_before_start_returns_zero(self):
        start = self._dt(hour=12)
        end = self._dt(hour=10)
        assert business_minutes_between(start, end) == 0

    def test_one_hour_same_business_day(self):
        start = self._dt(hour=9)
        end = self._dt(hour=10)
        assert business_minutes_between(start, end) == 60

    def test_two_hours_same_business_day(self):
        start = self._dt(hour=8)
        end = self._dt(hour=10)
        assert business_minutes_between(start, end) == 120

    def test_crosses_midnight_within_weekday(self):
        # Monday 23:00 → Tuesday 01:00: 120 business minutes (weekdays count fully)
        start = self._dt(day_offset=0, hour=23)
        end = self._dt(day_offset=1, hour=1)
        assert business_minutes_between(start, end) == 120

    def test_weekend_day_is_skipped(self):
        # Saturday (day_offset=5) has no business minutes
        saturday = self._dt(day_offset=5, hour=10)
        sunday = self._dt(day_offset=6, hour=10)
        assert business_minutes_between(saturday, sunday) == 0

    def test_spans_full_weekend(self):
        # Friday 09:00 → next Monday 09:00
        # Fri 09:00→midnight = 15h = 900 min (weekday)
        # Sat + Sun skipped
        # Mon 00:00→09:00 = 9h = 540 min (weekday)
        # Total = 1440 min
        friday = self._dt(day_offset=4, hour=9)   # Friday
        monday = self._dt(day_offset=7, hour=9)   # next Monday
        result = business_minutes_between(friday, monday)
        assert result == 15 * 60 + 9 * 60  # 1440

    def test_result_is_integer(self):
        start = self._dt(hour=9)
        end = self._dt(hour=9, minute=30)
        result = business_minutes_between(start, end)
        assert isinstance(result, int)
        assert result == 30


# ─────────────────────────────────────────────────────────────────────────────
# get_invoice_summary — logic tested with mock DB
# ─────────────────────────────────────────────────────────────────────────────

def _make_invoice(status: str, total: float, due_date=None):
    inv = MagicMock()
    inv.status = status
    inv.total = total
    inv.due_date = due_date or date.today() + timedelta(days=30)
    return inv


class TestGetInvoiceSummary:
    def _db_with(self, invoices):
        db = MagicMock()
        db.query.return_value.all.return_value = invoices
        return db

    def test_empty_db_returns_zero_totals(self):
        db = self._db_with([])
        result = get_invoice_summary(db)
        assert result["total_invoiced"] == 0.0
        assert result["total_paid"] == 0.0
        assert result["total_pending"] == 0.0
        assert result["overdue_count"] == 0
        assert result["overdue_amount"] == 0.0

    def test_paid_invoice_counted_in_total_and_paid(self):
        db = self._db_with([_make_invoice("paid", 1000.0)])
        result = get_invoice_summary(db)
        assert result["total_invoiced"] == 1000.0
        assert result["total_paid"] == 1000.0
        assert result["total_pending"] == 0.0

    def test_sent_invoice_counted_in_pending(self):
        db = self._db_with([_make_invoice("sent", 500.0)])
        result = get_invoice_summary(db)
        assert result["total_pending"] == 500.0
        assert result["total_paid"] == 0.0

    def test_overdue_invoice_counted(self):
        overdue_inv = _make_invoice("sent", 300.0, due_date=date.today() - timedelta(days=1))
        db = self._db_with([overdue_inv])
        result = get_invoice_summary(db)
        assert result["overdue_count"] == 1
        assert result["overdue_amount"] == 300.0

    def test_multiple_invoices_sum_correctly(self):
        invoices = [
            _make_invoice("paid", 1000.0),
            _make_invoice("sent", 500.0),
            _make_invoice("draft", 200.0),
        ]
        db = self._db_with(invoices)
        result = get_invoice_summary(db)
        assert result["total_invoiced"] == 1700.0
        assert result["total_paid"] == 1000.0
        assert result["total_pending"] == 500.0

    def test_by_status_keys_present(self):
        db = self._db_with([_make_invoice("draft", 100.0), _make_invoice("paid", 200.0)])
        result = get_invoice_summary(db)
        assert "by_status" in result
        assert "draft" in result["by_status"]
        assert "paid" in result["by_status"]

    def test_by_status_count_and_total(self):
        db = self._db_with([
            _make_invoice("draft", 100.0),
            _make_invoice("draft", 150.0),
        ])
        result = get_invoice_summary(db)
        assert result["by_status"]["draft"]["count"] == 2
        assert result["by_status"]["draft"]["total"] == 250.0

    def test_none_total_treated_as_zero(self):
        inv = _make_invoice("paid", 0.0)
        inv.total = None
        db = self._db_with([inv])
        result = get_invoice_summary(db)
        assert result["total_invoiced"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# run_system_report — routing logic
# ─────────────────────────────────────────────────────────────────────────────

class TestRunSystemReport:
    """Verify run_system_report delegates to the correct sub-runner."""

    def _db(self):
        return MagicMock()

    @patch("app.services.billing_reports_service.run_imputations_report", return_value={"rows": []})
    def test_utilization_by_person_routes_to_imputations(self, mock_fn):
        run_system_report(self._db(), "utilization_by_person", {}, None, None)
        mock_fn.assert_called_once()

    @patch("app.services.billing_reports_service.run_projects_report", return_value={"rows": []})
    def test_margin_by_project_routes_to_projects(self, mock_fn):
        run_system_report(self._db(), "margin_by_project", {}, None, None)
        mock_fn.assert_called_once()

    @patch("app.services.billing_reports_service.run_tickets_report", return_value={"rows": []})
    def test_sla_compliance_routes_to_tickets(self, mock_fn):
        run_system_report(self._db(), "sla_compliance", {}, None, None)
        mock_fn.assert_called_once()

    @patch("app.services.billing_reports_service.run_expenses_report", return_value={"rows": []})
    def test_expense_by_project_routes_to_expenses(self, mock_fn):
        run_system_report(self._db(), "expense_by_project", {}, None, None)
        mock_fn.assert_called_once()

    @patch("app.services.billing_reports_service.run_capacity_report", return_value={"by_user": []})
    def test_capacity_forecast_routes_to_capacity(self, mock_fn):
        run_system_report(self._db(), "capacity_forecast_12w", {}, None, None)
        mock_fn.assert_called_once()

    @patch("app.services.billing_reports_service.run_projects_report", return_value={"rows": []})
    def test_unknown_id_falls_back_to_projects(self, mock_fn):
        run_system_report(self._db(), "nonexistent_report", {}, None, None)
        mock_fn.assert_called_once()

    @patch("app.services.billing_reports_service.run_skills_report", return_value={})
    def test_resource_skills_matrix_routes_to_skills(self, mock_fn):
        run_system_report(self._db(), "resource_skills_matrix", {}, None, None)
        mock_fn.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# serialize_workflow — pure serialization logic
# ─────────────────────────────────────────────────────────────────────────────

class TestSerializeWorkflow:
    def _make_workflow(self, **kwargs):
        wf = MagicMock()
        wf.id = "wf-1"
        wf.name = "Test Workflow"
        wf.description = "desc"
        wf.project_id = None
        wf.project = None
        wf.is_global = True
        wf.trigger_type = "manual"
        wf.trigger_conditions = None
        wf.status = MagicMock()
        wf.status.value = "draft"
        wf.steps = []
        wf.executions = []
        wf.created_at = datetime(2026, 1, 1, 12, 0)
        for k, v in kwargs.items():
            setattr(wf, k, v)
        return wf

    def test_returns_dict(self):
        result = serialize_workflow(self._make_workflow())
        assert isinstance(result, dict)

    def test_id_and_name_present(self):
        result = serialize_workflow(self._make_workflow())
        assert result["id"] == "wf-1"
        assert result["name"] == "Test Workflow"

    def test_steps_empty_list(self):
        result = serialize_workflow(self._make_workflow())
        assert result["steps"] == []

    def test_trigger_conditions_parsed_from_json(self):
        cond = json.dumps({"event": "task_complete"})
        wf = self._make_workflow(trigger_conditions=cond)
        result = serialize_workflow(wf)
        assert result["trigger_conditions"] == {"event": "task_complete"}

    def test_trigger_conditions_none_when_null(self):
        result = serialize_workflow(self._make_workflow(trigger_conditions=None))
        assert result["trigger_conditions"] is None


# ─────────────────────────────────────────────────────────────────────────────
# validate_import_csv — pure validation logic
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateImportCsv:
    """Unit tests for CSV validation (no DB needed)."""

    def test_valid_projects_csv_passes(self):
        content = b"name,code,status,project_type\nProyecto A,PA01,planning,consulting\n"
        result = validate_import_csv("projects", content)
        assert result["valid"] is True
        assert result["total_rows"] == 1
        assert result["errors"] == []

    def test_empty_rows_returns_error(self):
        content = b"name,code,status,project_type\n"
        with pytest.raises(Exception):
            validate_import_csv("projects", content)

    def test_unknown_entity_type_raises(self):
        content = b"col1\nval1\n"
        with pytest.raises(Exception):
            validate_import_csv("unknown_type", content)

    def test_preview_contains_first_row(self):
        content = b"name,code,status,project_type\nProyecto A,PA01,planning,consulting\nProyecto B,PB01,active,consulting\n"
        result = validate_import_csv("projects", content)
        assert len(result["preview"]) >= 1
        assert result["preview"][0]["name"] == "Proyecto A"

    def test_tasks_entity_type_accepted(self):
        content = b"title,task_type,status\nTarea 1,development,todo\n"
        result = validate_import_csv("tasks", content)
        assert "total_rows" in result

    def test_users_entity_type_accepted(self):
        content = b"email,full_name,role\ntest@test.com,Test User,developer\n"
        result = validate_import_csv("users", content)
        assert "total_rows" in result

    def test_imputations_entity_type_accepted(self):
        content = b"date,hours,description\n2026-01-01,8,Trabajo\n"
        result = validate_import_csv("imputations", content)
        assert "total_rows" in result

    def test_expenses_entity_type_accepted(self):
        content = b"amount,category,description\n100,travel,Viaje\n"
        result = validate_import_csv("expenses", content)
        assert "total_rows" in result

    def test_multiple_rows_counted_correctly(self):
        rows = "\n".join(
            [f"Proyecto {i},P{i:03d},planning,consulting" for i in range(5)]
        )
        content = f"name,code,status,project_type\n{rows}\n".encode()
        result = validate_import_csv("projects", content)
        assert result["total_rows"] == 5


# ─────────────────────────────────────────────────────────────────────────────
# next_invoice_number — delegates to numbering service
# ─────────────────────────────────────────────────────────────────────────────

class TestNextInvoiceNumber:
    @patch("app.services.billing_reports_service.next_numbered_code", return_value="INV-2026-0001")
    def test_returns_formatted_code(self, mock_next):
        db = MagicMock()
        result = next_invoice_number(db)
        assert result == "INV-2026-0001"
        mock_next.assert_called_once()

    @patch("app.services.billing_reports_service.next_numbered_code", return_value="INV-2026-0001")
    def test_passes_correct_prefix(self, mock_next):
        db = MagicMock()
        next_invoice_number(db)
        call_kwargs = mock_next.call_args
        # prefix should be "INV"
        assert call_kwargs[1].get("prefix") == "INV" or "INV" in str(call_kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# serialize_scheduled_report — pure serialization
# ─────────────────────────────────────────────────────────────────────────────

class TestSerializeScheduledReport:
    def _make_report(self, **kwargs):
        r = MagicMock()
        r.id = "sr-1"
        r.name = "Weekly Report"
        r.metric = "invoices"
        r.frequency = "weekly"
        r.is_active = True
        r.include_pdf = False
        r.recipients = json.dumps(["admin@example.com"])
        r.last_run_at = None
        r.next_run_at = None
        r.created_at = datetime(2026, 1, 1, 8, 0)
        for k, v in kwargs.items():
            setattr(r, k, v)
        return r

    def test_returns_dict(self):
        result = serialize_scheduled_report(self._make_report())
        assert isinstance(result, dict)

    def test_id_and_name_present(self):
        result = serialize_scheduled_report(self._make_report())
        assert result["id"] == "sr-1"
        assert result["name"] == "Weekly Report"

    def test_recipients_parsed_from_json(self):
        result = serialize_scheduled_report(self._make_report())
        assert result["recipients"] == ["admin@example.com"]

    def test_last_run_at_none_when_not_set(self):
        result = serialize_scheduled_report(self._make_report(last_run_at=None))
        assert result["last_run_at"] is None

    def test_is_active_flag(self):
        result = serialize_scheduled_report(self._make_report(is_active=False))
        assert result["is_active"] is False
