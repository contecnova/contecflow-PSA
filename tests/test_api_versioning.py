from tests.conftest import auth


def test_api_v2_compatibility_surface_available(client, admin_token, db):
    res = client.get("/api/v2/profitability/summary", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.headers.get("x-api-version") == "2"
    body = res.json()
    assert body.get("api_version") == "v2"
    assert "base_currency" in body          # honest disclosure; no longer claims full normalization
    assert body.get("currency_normalized") is None  # removed: was a false claim
    assert "portfolio" in body


def test_api_v1_is_marked_deprecated(client, admin_token, db):
    res = client.get("/api/v1/profitability/summary", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.headers.get("x-api-version") == "1"
    assert res.headers.get("x-api-deprecated") == "true"
    assert res.headers.get("deprecation") == "true"
