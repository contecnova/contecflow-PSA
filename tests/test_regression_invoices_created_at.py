from datetime import date, datetime

from app.models.billing_reports import Invoice
from tests.conftest import auth


def test_invoices_list_accepts_datetime_created_at(client, admin_token, db):
    inv = Invoice(
        id="inv-reg-created-at",
        number="INV-REG-0001",
        issue_date=date(2026, 4, 22),
        created_at=datetime(2026, 4, 22, 16, 47, 59),
    )
    db.add(inv)
    db.commit()

    res = client.get("/api/v1/invoices", headers=auth(admin_token))

    assert res.status_code == 200, res.text
    body = res.json()
    row = next((x for x in body if x.get("id") == "inv-reg-created-at"), None)
    assert row is not None
    assert row.get("created_at")
