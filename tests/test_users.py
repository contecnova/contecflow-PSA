"""Tests de usuarios — perfil propio, preferencias, permisos."""
import pytest
from tests.conftest import auth, TEST_PASSWORD


def test_list_users_admin(client, admin_token, db):
    res = client.get("/api/v1/users", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    users = data if isinstance(data, list) else data.get("users", data.get("items", []))
    assert len(users) >= 2


def test_list_users_no_auth(client, db):
    res = client.get("/api/v1/users")
    assert res.status_code in (401, 403)


def test_get_me(client, admin_token, db):
    res = client.get("/api/v1/auth/me", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["username"] == "admin"


def test_patch_me_name(client, dev_token, db):
    res = client.patch("/api/v1/users/me",
        headers=auth(dev_token),
        json={"first_name": "Juan", "last_name": "García"})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["first_name"] == "Juan"
    assert data["last_name"] == "García"


def test_patch_me_phone(client, dev_token, db):
    res = client.patch("/api/v1/users/me",
        headers=auth(dev_token),
        json={"phone": "+34 600 000 001"})
    assert res.status_code == 200
    assert res.json()["data"]["phone"] == "+34 600 000 001"


def test_patch_me_cannot_change_role(client, dev_token, db):
    """Un employee no puede escalarse el rol."""
    res = client.patch("/api/v1/users/me",
        headers=auth(dev_token),
        json={"role": "admin"})
    # Debe ignorar el campo o devolver 403
    if res.status_code == 200:
        assert res.json()["data"].get("role") != "admin"
    else:
        assert res.status_code in (403, 422)


def test_get_user_preferences_default(client, dev_token, db):
    res = client.get("/api/v1/users/me/preferences", headers=auth(dev_token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert "accent_color" in data
    assert "theme_mode" in data
    assert "ui_density" in data


def test_save_user_preferences(client, dev_token, db):
    res = client.patch("/api/v1/users/me/preferences",
        headers=auth(dev_token),
        json={"accent_color": "#7c3aed", "theme_mode": "light", "ui_density": "compact"})
    assert res.status_code == 200
    assert res.json()["data"].get("ok") is True


def test_preferences_persist(client, dev_token, db):
    """Las preferencias guardadas se recuperan en la siguiente llamada."""
    client.patch("/api/v1/users/me/preferences",
        headers=auth(dev_token),
        json={"accent_color": "#f43f5e"})
    res = client.get("/api/v1/users/me/preferences", headers=auth(dev_token))
    assert res.status_code == 200
    assert res.json()["data"]["accent_color"] == "#f43f5e"


def test_change_password(client, dev_token, db):
    res = client.post("/api/v1/auth/change-password",
        headers=auth(dev_token),
        json={"current_password": TEST_PASSWORD, "new_password": "NewPass2024!"})
    assert res.status_code == 200
    assert res.json().get("ok") is True


def test_change_password_wrong_current(client, dev_token, db):
    res = client.post("/api/v1/auth/change-password",
        headers=auth(dev_token),
        json={"current_password": "wrong_pass", "new_password": "NewPass2024!"})
    assert res.status_code == 403


def test_change_password_too_short(client, dev_token, db):
    res = client.post("/api/v1/auth/change-password",
        headers=auth(dev_token),
        json={"current_password": TEST_PASSWORD, "new_password": "short"})
    assert res.status_code == 400


def test_admin_can_update_any_user(client, admin_token, db):
    # Obtener ID del dev
    users = client.get("/api/v1/users", headers=auth(admin_token)).json()
    if isinstance(users, dict):
        users = users.get("users", users.get("items", []))
    dev = next((u for u in users if u["username"] == "dev_test"), None)
    if not dev:
        pytest.skip("dev_test no encontrado")
    res = client.patch(f"/api/v1/users/{dev['id']}",
        headers=auth(admin_token),
        json={"job_title": "Senior Dev"})
    assert res.status_code == 200
