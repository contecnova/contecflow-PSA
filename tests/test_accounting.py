"""Tests de integración contable — sync status, validaciones."""
from tests.conftest import auth

def test_sync_status(client, admin_token, db):
    res = client.get("/api/v1/accounting/sync-status", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert "invoices" in data
    assert "active_integrations" in data

def test_push_invoice_not_found(client, admin_token, db):
    res = client.post("/api/v1/accounting/push-invoice", json={
        "invoice_id": "no-existe", "provider": "xero"
    }, headers=auth(admin_token))
    assert res.status_code in (404, 400)

def test_xero_test_no_config(client, admin_token, db):
    """Sin Xero configurado devuelve 404."""
    res = client.post("/api/v1/accounting/xero/test", json={}, headers=auth(admin_token))
    assert res.status_code in (400, 404)

def test_accounting_requires_manager(client, dev_token, db):
    res = client.get("/api/v1/accounting/sync-status", headers=auth(dev_token))
    assert res.status_code in (401, 403)

def test_push_bulk_no_config(client, admin_token, db):
    """Sin integración activa el bulk push devuelve error claro."""
    res = client.post("/api/v1/accounting/push-invoices-bulk", json={"provider": "xero"}, headers=auth(admin_token))
    assert res.status_code in (400, 404)
