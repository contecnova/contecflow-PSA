from tests.conftest import auth


def test_portal_translations_roundtrip(client, admin_token):
    from app.api.v1.endpoints import client_portal as cp

    cp._TRANSLATIONS_STORE.clear()

    payload = {
        "es": {"portal": {"hello": "Hola"}},
        "en": {"portal": {"hello": "Hello"}},
    }

    post_res = client.post(
        "/api/v1/portal/translations",
        json=payload,
        headers=auth(admin_token),
    )
    assert post_res.status_code == 200
    assert post_res.json().get("ok") is True

    get_res = client.get("/api/v1/portal/translations", headers=auth(admin_token))
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["es"]["portal"]["hello"] == "Hola"
    assert data["en"]["portal"]["hello"] == "Hello"


def test_portal_translations_require_manager_role(client, dev_token):
    res = client.get("/api/v1/portal/translations", headers=auth(dev_token))
    assert res.status_code in (401, 403)
