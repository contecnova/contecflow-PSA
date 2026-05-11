"""Developer Portal delete regression tests."""

from tests.conftest import auth
from app.models.oauth_apps import OAuthApp


def test_delete_oauth_app_is_soft_and_hidden(client, pm_token, db):
    created = client.post(
        "/api/v1/developer/apps",
        headers=auth(pm_token),
        json={
            "name": "App QA",
            "description": "App para validar borrado",
            "homepage_url": "https://example.local/app",
            "redirect_uris": ["https://example.local/callback"],
            "scopes": ["read"],
        },
    )
    assert created.status_code in (200, 201)
    app_id = created.json()["id"]

    deleted = client.delete(f"/api/v1/developer/apps/{app_id}", headers=auth(pm_token))
    assert deleted.status_code == 200
    payload = deleted.json()
    assert payload.get("ok") is True

    listed = client.get("/api/v1/developer/apps", headers=auth(pm_token))
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()]
    assert app_id not in ids

    fetched = client.get(f"/api/v1/developer/apps/{app_id}", headers=auth(pm_token))
    assert fetched.status_code == 404

    row = db.query(OAuthApp).filter(OAuthApp.id == app_id).first()
    assert row is not None
    assert row.is_active is False
