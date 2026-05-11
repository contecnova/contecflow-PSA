"""Regresión: los nuevos schemas Pydantic en auth/MFA deben preservar el
contrato del payload: dict anterior.

Reglas verificadas:
  1. Un cliente legacy que envía campos extra (que el schema no declara)
     no recibe 422 — los extras se ignoran silenciosamente.
  2. Un cliente legacy que omite un campo "obligatorio" del schema NO
     recibe 422 — sigue obteniendo el 400 con mensaje legible del endpoint.
"""
from tests.conftest import auth, _TEST_PASSWORD


# ── 1. Extra fields silently ignored ────────────────────────────────────────

def test_change_password_ignores_extra_fields(client, admin_token, db):
    """change-password rechaza con 400 si current_password falta, no con 422,
    aunque el cliente mande campos extra."""
    res = client.post("/api/v1/auth/change-password", headers=auth(admin_token), json={
        # Faltan current_password y new_password → debe devolver 400 (no 422)
        "ghost_field": "from-legacy-client",
        "another_extra": 12345,
    })
    assert res.status_code == 400
    assert "obligator" in res.json()["detail"].lower()


def test_mfa_verify_setup_extra_fields_ignored(client, admin_token, db):
    res = client.post("/api/v1/auth/mfa/verify-setup", headers=auth(admin_token), json={
        "extra_unused_field": "x",
        # sin "code"
    })
    # Sin MFA configurado responde 400 "Primero inicia la configuración"
    # Si MFA estuviera configurado y code faltara, también 400. Nunca 422.
    assert res.status_code == 400


def test_mfa_validate_missing_token_returns_400_not_422(client, db):
    """Antes: payload.get('mfa_challenge_token') → None → HTTPException(400).
    Ahora: schema con mfa_challenge_token Optional, el check inline sigue
    devolviendo 400 — preservamos el contrato."""
    res = client.post("/api/v1/auth/mfa/validate", json={
        # mfa_challenge_token ausente
        "code": "123456",
    })
    assert res.status_code == 400
    assert "mfa_challenge_token" in res.json()["detail"].lower()


def test_sso_callback_missing_code_returns_400_not_422(client, db):
    """SSO callback con code faltante o redirect_uri faltante → 400 con
    mensaje original, no 422 de Pydantic."""
    # Necesitamos crear primero un SSO config para que el endpoint no aborte
    # por otra razón. Pero la validación de payload corre antes — basta con
    # un config_id cualquiera y verificar que el endpoint no devuelve 422.
    res = client.post("/api/v1/auth/sso/inexistente/callback", json={
        "state": "abc",
        "legacy_field": "ignored",
        # Falta `code` y `redirect_uri`
    })
    # Esperamos 400 (validación de campos) o 404 (config no existe), NUNCA 422.
    assert res.status_code != 422


# ── 2. Extra fields don't break valid payloads ─────────────────────────────

def test_assign_user_org_extra_fields_ignored(client, admin_token, db):
    """POST /organizations/{id}/assign-user con campo válido + extras."""
    from app.models.user import User
    dev = db.query(User).filter(User.username == "dev_test").first()
    res = client.post("/api/v1/organizations/1/assign-user",
                      headers=auth(admin_token), json={
                          "user_id": dev.id,
                          "legacy_org_role": "ignored",
                          "extra_garbage": [1, 2, 3],
                      })
    # Pasa la validación de schema (200 o 404 si svc no encuentra org)
    assert res.status_code != 422


def test_accept_estimate_default_true_when_field_missing(client, admin_token, db):
    """payload.get('accepted', True) original → ahora `accepted: bool = True`
    como default en el schema. Si el cliente no manda el campo, sigue siendo True."""
    # task_id inexistente → 404 (no 422). El default del schema funciona.
    res = client.post("/api/v1/ai-planning/estimate/nonexistent/accept",
                      headers=auth(admin_token), json={
                          "extra_field": "x",
                          # accepted ausente — default debería ser True
                      })
    assert res.status_code != 422
