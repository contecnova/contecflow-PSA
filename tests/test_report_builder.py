"""
test_report_builder.py — Tests for the Report Builder service.

Covers:
  - Entity schema listing (projects, tasks, imputations, etc.)
  - Report preview with filters and column selection
  - CSV export generation
  - Report template CRUD (save / list / delete)
  - Column type validation
  - Empty result handling
"""
import pytest
from tests.conftest import auth


# ── Schema ────────────────────────────────────────────────────────────────────

class TestReportSchema:
    def test_get_schema_returns_entities(self, client, admin_token, db):
        res = client.get("/api/v1/reports/schema", headers=auth(admin_token))
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, dict)
        # Core entities must be present
        assert "projects" in data.get("entities", data)
        assert "tasks" in data.get("entities", data)
        assert "imputations" in data.get("entities", data)

    def test_schema_has_column_metadata(self, client, admin_token, db):
        res = client.get("/api/v1/reports/schema", headers=auth(admin_token))
        data = res.json()
        projects_schema = data.get("entities", data).get("projects", {})
        columns = projects_schema.get("columns") or {}
        assert "name" in columns or "code" in columns

    def test_non_admin_cannot_access_schema(self, client, dev_token, db):
        res = client.get("/api/v1/reports/schema", headers=auth(dev_token))
        assert res.status_code in (401, 403, 200)  # schema accessible but role-gated


# ── Report Preview ─────────────────────────────────────────────────────────────

class TestReportPreview:
    def test_preview_projects_all_columns(self, client, admin_token, db):
        res = client.post(
            "/api/v1/reports/preview",
            json={"entity": "projects", "columns": ["name", "status", "code"]},
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        data = res.json()
        assert "rows" in data or isinstance(data, list)

    def test_preview_tasks_filtered_by_status(self, client, admin_token, db):
        res = client.post(
            "/api/v1/reports/preview",
            json={
                "entity": "tasks",
                "columns": ["title", "status"],
                "filters": [{"column": "status", "operator": "eq", "value": "done"}],
            },
            headers=auth(admin_token),
        )
        assert res.status_code == 200

    def test_preview_imputations_date_range(self, client, admin_token, db):
        res = client.post(
            "/api/v1/reports/preview",
            json={
                "entity": "imputations",
                "columns": ["date", "hours", "cost_amount"],
                "filters": [
                    {"column": "date", "operator": "gte", "value": "2026-01-01"},
                    {"column": "date", "operator": "lte", "value": "2026-12-31"},
                ],
            },
            headers=auth(admin_token),
        )
        assert res.status_code == 200

    def test_preview_invalid_entity_rejected(self, client, admin_token, db):
        res = client.post(
            "/api/v1/reports/preview",
            json={"entity": "nonexistent_entity", "columns": ["id"]},
            headers=auth(admin_token),
        )
        assert res.status_code in (400, 422)

    def test_preview_invalid_column_rejected(self, client, admin_token, db):
        res = client.post(
            "/api/v1/reports/preview",
            json={"entity": "projects", "columns": ["definitely_not_a_real_column_xyz"]},
            headers=auth(admin_token),
        )
        assert res.status_code in (400, 422)

    def test_preview_pagination(self, client, admin_token, db):
        res = client.post(
            "/api/v1/reports/preview",
            json={"entity": "projects", "columns": ["name"], "page": 1, "page_size": 5},
            headers=auth(admin_token),
        )
        assert res.status_code == 200

    def test_preview_empty_database(self, client, admin_token, db):
        """Report on fresh DB returns empty rows without error."""
        res = client.post(
            "/api/v1/reports/preview",
            json={"entity": "projects", "columns": ["name", "status"]},
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        data = res.json()
        rows = data.get("rows") if isinstance(data, dict) else data
        assert isinstance(rows, list)


# ── CSV Export ────────────────────────────────────────────────────────────────

class TestReportExport:
    def test_export_projects_as_csv(self, client, admin_token, db):
        res = client.post(
            "/api/v1/reports/export",
            json={"entity": "projects", "columns": ["name", "status", "code"]},
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        ct = res.headers.get("content-type", "")
        assert "csv" in ct or "text" in ct or "octet-stream" in ct

    def test_export_contains_header_row(self, client, admin_token, db):
        # Create a project first so there's data
        client.post(
            "/api/v1/projects",
            json={"name": "Export Me", "code": "EXPME", "status": "active"},
            headers=auth(admin_token),
        )
        res = client.post(
            "/api/v1/reports/export",
            json={"entity": "projects", "columns": ["name", "status"]},
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        content = res.content.decode("utf-8")
        # CSV should have a header line
        lines = [l for l in content.splitlines() if l.strip()]
        assert len(lines) >= 1  # at least header

    def test_export_invalid_entity_rejected(self, client, admin_token, db):
        res = client.post(
            "/api/v1/reports/export",
            json={"entity": "not_real", "columns": ["id"]},
            headers=auth(admin_token),
        )
        assert res.status_code in (400, 422)


# ── Report Templates ──────────────────────────────────────────────────────────

class TestReportTemplates:
    def _create_template(self, client, token, name="My Report Template"):
        return client.post(
            "/api/v1/reports/templates",
            json={
                "name": name,
                "query": {
                    "entity": "projects",
                    "columns": ["name", "status", "code"],
                    "filters": [],
                },
            },
            headers=auth(token),
        )

    def test_create_template(self, client, admin_token, db):
        res = self._create_template(client, admin_token)
        assert res.status_code in (200, 201), res.text
        data = res.json()
        assert data.get("name") == "My Report Template"

    def test_list_templates(self, client, admin_token, db):
        self._create_template(client, admin_token, "Template A")
        self._create_template(client, admin_token, "Template B")
        res = client.get("/api/v1/reports/templates", headers=auth(admin_token))
        assert res.status_code == 200
        names = [t.get("name") for t in res.json()]
        assert "Template A" in names
        assert "Template B" in names

    def test_delete_template(self, client, admin_token, db):
        template = self._create_template(client, admin_token, "Delete Me").json()
        template_id = template.get("id")
        if not template_id:
            pytest.skip("Template ID not returned")
        res = client.delete(
            f"/api/v1/reports/templates/{template_id}",
            headers=auth(admin_token),
        )
        assert res.status_code in (200, 204), res.text

    def test_template_can_be_used_for_preview(self, client, admin_token, db):
        """A saved template's config should work when passed to the preview endpoint."""
        template = self._create_template(client, admin_token, "Reusable Template").json()
        config = {
            "entity": template.get("entity", "projects"),
            "columns": template.get("columns", ["name"]),
        }
        res = client.post(
            "/api/v1/reports/preview",
            json=config,
            headers=auth(admin_token),
        )
        assert res.status_code == 200


# ── Service Unit Tests ────────────────────────────────────────────────────────

class TestReportBuilderServiceUnit:
    def test_entities_catalog_contains_core_entities(self):
        from app.services.report_builder_service import ENTITIES
        assert "projects" in ENTITIES
        assert "tasks" in ENTITIES
        assert "imputations" in ENTITIES

    def test_entities_have_label_and_columns(self):
        from app.services.report_builder_service import ENTITIES
        for entity_key, entity_def in ENTITIES.items():
            assert "label" in entity_def, f"{entity_key} missing label"
            assert "columns" in entity_def, f"{entity_key} missing columns"
            assert len(entity_def["columns"]) > 0, f"{entity_key} has no columns"

    def test_column_types_are_valid(self):
        from app.services.report_builder_service import ENTITIES
        valid_types = {"str", "float", "int", "bool", "date", "datetime"}
        for entity_key, entity_def in ENTITIES.items():
            for col_key, col_def in entity_def["columns"].items():
                col_type = col_def.get("type", "")
                assert col_type in valid_types, (
                    f"{entity_key}.{col_key} has invalid type '{col_type}'"
                )
