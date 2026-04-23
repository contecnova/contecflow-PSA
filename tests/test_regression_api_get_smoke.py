from __future__ import annotations

from typing import Any

from tests.conftest import auth


_SKIP_PATH_PREFIXES = (
    "/api/v1/docs",
    "/api/v1/redoc",
    "/api/v1/openapi.json",
    "/api/v1/ws",
)

# Endpoints that can be very slow/non-deterministic in smoke mode
_SKIP_PATH_CONTAINS = (
    "/ai/",
    "/integrations/",
    "/imports/",
    "/exports/",
    "/reports/run",
    "/webhooks/",
)

_MAX_CHECKED = 80


def _query_value(schema: dict[str, Any]) -> Any:
    t = (schema or {}).get("type")
    if t == "integer":
        return 1
    if t == "number":
        return 1.0
    if t == "boolean":
        return True
    return "x"


def _build_required_query(operation: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for p in operation.get("parameters", []):
        if p.get("in") != "query" or not p.get("required"):
            continue
        name = p.get("name")
        if not name:
            continue
        schema = p.get("schema") or {}
        if "default" in schema:
            params[name] = schema["default"]
        elif "enum" in schema and schema["enum"]:
            params[name] = schema["enum"][0]
        else:
            params[name] = _query_value(schema)
    return params


def test_v1_get_endpoints_do_not_raise_5xx(client, admin_token, db):
    spec = client.get("/api/v1/openapi.json")
    assert spec.status_code == 200, spec.text
    openapi = spec.json()

    failures: list[str] = []
    checked = 0

    for path, methods in openapi.get("paths", {}).items():
        if checked >= _MAX_CHECKED:
            break
        if not path.startswith("/api/v1"):
            continue
        if "{" in path:
            continue
        if path.startswith(_SKIP_PATH_PREFIXES):
            continue
        if any(token in path for token in _SKIP_PATH_CONTAINS):
            continue

        get_op = methods.get("get")
        if not get_op:
            continue

        checked += 1
        params = _build_required_query(get_op)
        try:
            res = client.get(path, headers=auth(admin_token), params=params)
        except Exception as exc:
            failures.append(f"{path} -> exception: {exc}")
            continue

        if res.status_code >= 500:
            failures.append(f"{path} -> {res.status_code}")

    assert checked > 0
    assert not failures, "\n" + "\n".join(failures)
