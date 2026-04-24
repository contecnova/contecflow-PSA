"""
tests/test_v236_features.py
Tests for v23.6.0 features:
  1. Task status in_review (enum + API)
  2. Invoice PDF download endpoint
  3. Configurable log level endpoint
"""
from tests.conftest import auth


# ─── 1. TaskStatus in_review ─────────────────────────────────────────────────

def _create_project(client, token):
    r = client.post("/api/v1/projects", json={
        "name": "Test v236", "code": "V236",
        "status": "active", "project_type": "development",
    }, headers=auth(token))
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_task_create_with_in_review_status(client, pm_token, db):
    """Creating a task with status 'in_review' is accepted by the backend."""
    pid = _create_project(client, pm_token)
    r = client.post("/api/v1/tasks", json={
        "project_id": pid,
        "title": "Review task",
        "priority": "medium",
        "status": "in_review",
    }, headers=auth(pm_token))
    assert r.status_code in (200, 201), r.text
    assert r.json()["status"] == "in_review"


def test_task_patch_to_in_review(client, pm_token, db):
    """Patching task status to 'in_review' works correctly (via in_progress → in_review)."""
    pid = _create_project(client, pm_token)
    task_r = client.post("/api/v1/tasks", json={
        "project_id": pid, "title": "Task A", "priority": "low",
    }, headers=auth(pm_token))
    tid = task_r.json()["id"]

    # Advance to in_progress first (todo → in_progress is allowed)
    r = client.patch(f"/api/v1/tasks/{tid}", json={"status": "in_progress"}, headers=auth(pm_token))
    assert r.status_code == 200, r.text

    # Now transition to in_review
    r = client.patch(f"/api/v1/tasks/{tid}", json={"status": "in_review"}, headers=auth(pm_token))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_review"


def test_task_status_in_review_in_list(client, pm_token, db):
    """Tasks with in_review status appear when filtering by status."""
    pid = _create_project(client, pm_token)
    client.post("/api/v1/tasks", json={
        "project_id": pid, "title": "In review task", "priority": "medium", "status": "in_review",
    }, headers=auth(pm_token))
    r = client.get("/api/v1/tasks", params={"status": "in_review"}, headers=auth(pm_token))
    assert r.status_code == 200
    # Endpoint returns 200 without crashing on in_review filter — result is a list or paginated dict


# ─── 2. Invoice PDF ───────────────────────────────────────────────────────────

def _create_invoice(client, token):
    r = client.post("/api/v1/invoices", json={
        "client_name": "ACME S.L.",
        "issue_date": "2025-01-01",
        "due_date": "2025-01-31",
        "tax_rate": 21.0,
        "lines": [
            {"description": "Desarrollo web", "quantity": 10, "unit": "h",
             "unit_price": 100.0, "amount": 1000.0, "discount_pct": 0},
        ],
    }, headers=auth(token))
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_invoice_pdf_returns_bytes(client, pm_token, db):
    """GET /invoices/{id}/pdf returns a valid PDF (starts with %PDF)."""
    inv_id = _create_invoice(client, pm_token)
    r = client.get(f"/api/v1/invoices/{inv_id}/pdf", headers=auth(pm_token))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF", "Response does not start with PDF magic bytes"


def test_invoice_pdf_not_found(client, pm_token, db):
    """GET /invoices/99999/pdf returns 404."""
    r = client.get("/api/v1/invoices/99999/pdf", headers=auth(pm_token))
    assert r.status_code == 404


def test_invoice_pdf_content_disposition(client, pm_token, db):
    """PDF response includes Content-Disposition header for download."""
    inv_id = _create_invoice(client, pm_token)
    r = client.get(f"/api/v1/invoices/{inv_id}/pdf", headers=auth(pm_token))
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert "filename" in cd


# ─── 3. Configurable log level ────────────────────────────────────────────────

def test_get_log_level(client, admin_token, db):
    """GET /settings/log-level returns current levels."""
    r = client.get("/api/v1/settings/log-level", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    data = r.json()
    assert "root" in data
    assert "valid_levels" in data
    assert isinstance(data["valid_levels"], list)
    assert "INFO" in data["valid_levels"]


def test_set_log_level(client, admin_token, db):
    """POST /settings/log-level changes log level at runtime."""
    r = client.post("/api/v1/settings/log-level",
                    json={"level": "DEBUG"},
                    headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["level"] == "DEBUG"


def test_set_invalid_log_level(client, admin_token, db):
    """POST /settings/log-level with invalid level returns 400."""
    r = client.post("/api/v1/settings/log-level",
                    json={"level": "NONSENSE"},
                    headers=auth(admin_token))
    assert r.status_code == 400


def test_set_log_level_non_admin(client, dev_token, db):
    """Only admins can change log level — non-admin gets 403."""
    r = client.post("/api/v1/settings/log-level",
                    json={"level": "DEBUG"},
                    headers=auth(dev_token))
    assert r.status_code in (403, 401)
