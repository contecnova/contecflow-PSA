"""
tests/test_api_versioning.py

Contrato de rutas API: garantiza que ninguna ruta sensible devuelva 404/405 inesperado.
Cubre: versioning v1/v2, aliases legacy, branding, currency, baselines,
       approval-builder y slack block-kit.
"""
import pytest
from tests.conftest import auth


# ── v1 / v2 versioning ────────────────────────────────────────────────────────

def test_api_v2_compatibility_surface_available(client, admin_token, db):
    res = client.get("/api/v2/profitability/summary", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.headers.get("x-api-version") == "2"
    body = res.json()
    assert body.get("api_version") == "v2"
    assert "base_currency" in body
    assert body.get("currency_normalized") is None
    assert "portfolio" in body


def test_api_v1_is_marked_deprecated(client, admin_token, db):
    res = client.get("/api/v1/profitability/summary", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.headers.get("x-api-version") == "1"
    assert res.headers.get("x-api-deprecated") == "true"
    assert res.headers.get("deprecation") == "true"


# ── Legacy aliases — rutas /projects/* que deben existir ─────────────────────
# Estas rutas son aliases de compatibilidad hacia atrás. Un 404 aquí indicaría
# que el alias ha sido eliminado prematuramente. Un 401/403/422 es aceptable.

_LEGACY_GET_ROUTES = [
    "/api/v1/projects/tasks",
    "/api/v1/projects/milestones",
    "/api/v1/projects/sprints",
    "/api/v1/projects/epics",
    "/api/v1/projects/issue-types",
]


@pytest.mark.parametrize("route", _LEGACY_GET_ROUTES)
def test_legacy_alias_route_is_not_404(client, admin_token, db, route):
    res = client.get(route, headers=auth(admin_token))
    assert res.status_code != 404, (
        f"Alias legacy {route} devuelve 404 — ruta eliminada prematuramente. "
        "Ver DOCS.md sección 'Aliases legacy (deprecados)'."
    )
    assert res.status_code != 405, (
        f"Alias legacy {route} devuelve 405 — método no permitido inesperado."
    )


# ── Branding — ruta canónica activa ──────────────────────────────────────────

def test_branding_get_route_exists(client, admin_token, db):
    res = client.get("/api/v1/orgs/1/branding", headers=auth(admin_token))
    assert res.status_code not in (404, 405), (
        f"GET /api/v1/orgs/{{org_id}}/branding devolvió {res.status_code} — ruta no registrada."
    )


def test_branding_put_route_exists(client, admin_token, db):
    res = client.put(
        "/api/v1/orgs/1/branding",
        json={"app_name": "Test"},
        headers=auth(admin_token),
    )
    assert res.status_code not in (404, 405), (
        f"PUT /api/v1/orgs/{{org_id}}/branding devolvió {res.status_code} — ruta no registrada."
    )


# ── Currency sync ─────────────────────────────────────────────────────────────

def test_currency_sync_ecb_route_exists(client, admin_token, db):
    res = client.post("/api/v1/currency/sync-ecb", headers=auth(admin_token))
    # 503 (no config) or 200 are both valid; only 404/405 indicate missing route
    assert res.status_code not in (404, 405), (
        f"POST /api/v1/currency/sync-ecb devolvió {res.status_code} — ruta no registrada."
    )


def test_currency_sync_openexchangerates_route_exists(client, admin_token, db):
    res = client.post("/api/v1/currency/sync-openexchangerates", headers=auth(admin_token))
    assert res.status_code not in (404, 405), (
        f"POST /api/v1/currency/sync-openexchangerates devolvió {res.status_code} — ruta no registrada."
    )


def test_currency_sync_requires_admin(client, db):
    res = client.post("/api/v1/currency/sync-ecb")
    assert res.status_code in (401, 403), (
        "Currency sync debe requerir autenticación de admin."
    )


# ── Baselines ─────────────────────────────────────────────────────────────────

def test_baselines_route_exists_for_unknown_project(client, admin_token, db):
    res = client.get("/api/v1/projects/nonexistent-project/baselines", headers=auth(admin_token))
    # 404 from project not found is acceptable; 404 from route not found is not
    # We distinguish by checking the response body contains a meaningful message
    if res.status_code == 404:
        body = res.text.lower()
        assert "project" in body or "not found" in body, (
            "El 404 parece ser de ruta no registrada, no de proyecto inexistente. "
            "Verificar que baselines_v239.router está montado en delivery.py."
        )
    else:
        assert res.status_code != 405


def test_baselines_compare_route_exists(client, admin_token, db):
    res = client.get(
        "/api/v1/projects/nonexistent-project/baselines/nonexistent-baseline/compare",
        headers=auth(admin_token),
    )
    assert res.status_code != 405


# ── Approval workflow builder ─────────────────────────────────────────────────

def test_approval_builder_schema_route_exists(client, admin_token, db):
    res = client.get("/api/v1/approval-workflows/builder/schema", headers=auth(admin_token))
    assert res.status_code not in (404, 405), (
        f"GET /api/v1/approval-workflows/builder/schema devolvió {res.status_code}."
    )


def test_approval_builder_validate_route_exists(client, admin_token, db):
    res = client.post(
        "/api/v1/approval-workflows/builder/validate",
        json={"nodes": [], "edges": []},
        headers=auth(admin_token),
    )
    assert res.status_code not in (404, 405), (
        f"POST /api/v1/approval-workflows/builder/validate devolvió {res.status_code}."
    )


def test_approval_builder_schema_requires_auth(client, db):
    res = client.get("/api/v1/approval-workflows/builder/schema")
    assert res.status_code in (401, 403)


# ── Slack Block Kit ───────────────────────────────────────────────────────────

def test_slack_block_kit_preview_route_exists(client, admin_token, db):
    res = client.get(
        "/api/v1/notifications/slack/block-kit/preview?event_type=task_overdue",
        headers=auth(admin_token),
    )
    assert res.status_code not in (404, 405), (
        f"GET /api/v1/notifications/slack/block-kit/preview devolvió {res.status_code}."
    )


def test_slack_block_kit_send_route_exists(client, admin_token, db):
    res = client.post(
        "/api/v1/notifications/slack/block-kit",
        json={
            "event_type": "task_overdue",
            "channel": "#general",
            "context": {},
        },
        headers=auth(admin_token),
    )
    # 503 (webhook not configured) is valid; only 404/405 are not
    assert res.status_code not in (404, 405), (
        f"POST /api/v1/notifications/slack/block-kit devolvió {res.status_code}."
    )


def test_slack_block_kit_requires_auth(client, db):
    res = client.get("/api/v1/notifications/slack/block-kit/preview?event_type=task_overdue")
    assert res.status_code in (401, 403)
