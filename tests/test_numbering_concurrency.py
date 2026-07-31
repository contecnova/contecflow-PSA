"""
Numbering uniqueness tests.

NOTE: The test suite uses SQLite with StaticPool (single shared connection).
SQLite does not support savepoints across concurrent threads, so the actual
FOR UPDATE locking behaviour of `next_numbered_code` cannot be exercised here.
Sequential calls are used instead; they still prove that the sequencing
logic produces unique, monotonically increasing numbers.
Real concurrent safety is guaranteed in production (PostgreSQL) by the
SELECT … FOR UPDATE lock inside `next_numbered_code`.
"""

from app.models.billing_reports import Invoice
from tests.conftest import auth


def _create_invoice(client, pm_token, idx):
    payload = {
        "project_id": None,
        "contract_id": None,
        "client_name": f"Cliente {idx}",
        "client_address": None,
        "client_vat": None,
        "client_email": f"cliente{idx}@example.com",
        "issue_date": "2026-04-14",
        "due_date": "2026-05-14",
        "tax_rate": 21,
        "currency": "EUR",
        "notes": "test numeración",
        "po_reference": None,
        "period_from": "2026-04-01",
        "period_to": "2026-04-30",
        "lines": [
            {
                "description": "Servicio",
                "quantity": 1,
                "unit": "h",
                "unit_price": 100,
                "discount_pct": 0,
                "amount": 100,
                "source_type": "manual",
                "source_ids": [],
            }
        ],
    }
    res = client.post("/api/v1/invoices", json=payload, headers=auth(pm_token))
    assert res.status_code in (200, 201), res.text
    return res.json()["data"]["number"]


def test_invoice_numbering_sequential_uniqueness(client, pm_token, db):
    """Sequential uniqueness: each call must produce a distinct, incrementing number."""
    count = 8
    numbers = [_create_invoice(client, pm_token, i) for i in range(count)]

    assert len(numbers) == count, "Not all invoices were created"
    assert len(set(numbers)) == count, f"Duplicate invoice numbers: {numbers}"

    # Confirm every DB row also has a unique number
    created_numbers = [row.number for row in db.query(Invoice).all()]
    assert len(created_numbers) == len(set(created_numbers)), (
        f"Duplicate numbers in DB: {created_numbers}"
    )

    # Numbers must be strictly increasing (format INV-YYYY-####)
    for a, b in zip(numbers, numbers[1:]):
        assert a < b, f"Numbers not monotonically increasing: {a} >= {b}"
