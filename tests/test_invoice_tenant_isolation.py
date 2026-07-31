from datetime import date, timedelta

from tests.conftest import auth
from tests.conftest import TEST_PASSWORD


BASE_PAYLOAD = {
    "contract_id": None,
    "client_name": "Client Test",
    "client_address": "Addr",
    "client_vat": "ES123",
    "client_email": "c@test.com",
    "issue_date": str(date.today()),
    "due_date": str(date.today() + timedelta(days=15)),
    "tax_rate": 21,
    "currency": "EUR",
    "notes": "n",
    "po_reference": "PO-1",
    "period_from": str(date.today() - timedelta(days=7)),
    "period_to": str(date.today()),
    "lines": [
        {
            "description": "Consulting",
            "quantity": 2,
            "unit": "h",
            "unit_price": 100,
            "discount_pct": 0,
            "amount": 200,
        }
    ],
}


def test_invoice_create_blocks_cross_tenant_project(client, pm_token, seed_multitenant):
    payload = {**BASE_PAYLOAD, "project_id": "project-b-test"}
    res = client.post("/api/v1/invoices", json=payload, headers=auth(pm_token))
    assert res.status_code == 404, res.text


def test_invoice_create_allows_same_tenant_project_and_sets_org(client, pm_token, seed_multitenant, db):
    payload = {**BASE_PAYLOAD, "project_id": "project-a-test"}
    res = client.post("/api/v1/invoices", json=payload, headers=auth(pm_token))
    assert res.status_code == 201, res.text

    body = res.json()["data"]
    assert body["project_id"] == "project-a-test"

    from app.models.billing_reports import Invoice

    inv = db.query(Invoice).filter(Invoice.id == body["id"]).first()
    assert inv is not None
    assert inv.organization_id == "org-a-test"


def _outsider_token(client):
    res = client.post("/api/v1/auth/login", json={"username": "outsider", "password": TEST_PASSWORD})
    assert res.status_code == 200, res.text
    token = res.cookies.get("access_token")
    assert token
    return token


def test_invoice_list_hides_other_tenant_invoices(client, pm_token, seed_multitenant):
    payload = {**BASE_PAYLOAD, "project_id": "project-a-test"}
    create_res = client.post("/api/v1/invoices", json=payload, headers=auth(pm_token))
    assert create_res.status_code == 201, create_res.text
    invoice_id = create_res.json()["data"]["id"]

    outsider = _outsider_token(client)
    list_res = client.get("/api/v1/invoices", headers=auth(outsider))
    assert list_res.status_code == 200, list_res.text
    items = list_res.json().get("items") or []
    assert all(item.get("id") != invoice_id for item in items)


def test_invoice_status_update_blocks_cross_tenant(client, pm_token, seed_multitenant):
    payload = {**BASE_PAYLOAD, "project_id": "project-a-test"}
    create_res = client.post("/api/v1/invoices", json=payload, headers=auth(pm_token))
    assert create_res.status_code == 201, create_res.text
    invoice_id = create_res.json()["data"]["id"]

    outsider = _outsider_token(client)
    patch_res = client.patch(
        f"/api/v1/billing-reports/invoices/{invoice_id}/status",
        json={"status": "sent"},
        headers=auth(outsider),
    )
    # ABAC denies role before row lookup.
    assert patch_res.status_code == 403, patch_res.text
