from __future__ import annotations

from typing import Any

from tests.conftest import auth


_SKIP_PATH_PREFIXES = (
    "/api/v1/docs",
    "/api/v1/redoc",
    "/api/v1/openapi.json",
    "/api/v1/ws",
)

_SKIP_PATH_CONTAINS = (
    "/ai/",
    "/integrations/",
    "/imports/",
    "/exports/",
    "/reports/run",
    "/webhooks/",
    "/auth/login",
    "/webauthn/",
    "/skills/catalog",
)

_METHODS = ("post", "put", "patch", "delete")
_MAX_CHECKED = 60


def _query_value(schema: dict[str, Any]) -> Any:
    t = (schema or {}).get("type")
    if t == "integer":
        return 1
    if t == "number":
        return 1.0
    if t == "boolean":
        return True
    if t == "array":
        item = (schema or {}).get("items") or {"type": "string"}
        return [_query_value(item)]
    return "x"


def _resolve_ref(ref: str, openapi: dict[str, Any]) -> dict[str, Any]:
    if not ref.startswith("#/components/schemas/"):
        return {}
    key = ref.split("/")[-1]
    return openapi.get("components", {}).get("schemas", {}).get(key, {})


def _schema_example(schema: dict[str, Any], openapi: dict[str, Any], depth: int = 0) -> Any:
    if depth > 3:
        return "x"

    if "$ref" in schema:
        resolved = _resolve_ref(schema["$ref"], openapi)
        return _schema_example(resolved, openapi, depth + 1)

    if "example" in schema:
        return schema["example"]

    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]

    if "allOf" in schema:
        out: dict[str, Any] = {}
        for part in schema["allOf"]:
            ex = _schema_example(part, openapi, depth + 1)
            if isinstance(ex, dict):
                out.update(ex)
        return out

    if "oneOf" in schema and schema["oneOf"]:
        return _schema_example(schema["oneOf"][0], openapi, depth + 1)

    if "anyOf" in schema and schema["anyOf"]:
        return _schema_example(schema["anyOf"][0], openapi, depth + 1)

    typ = schema.get("type")
    if typ == "object" or "properties" in schema:
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        out = {}
        for name, prop_schema in props.items():
            if required and name not in required:
                continue
            out[name] = _schema_example(prop_schema, openapi, depth + 1)
        return out

    if typ == "array":
        item_schema = schema.get("items", {"type": "string"})
        return [_schema_example(item_schema, openapi, depth + 1)]

    return _query_value(schema)


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


def _build_body(operation: dict[str, Any], openapi: dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
    body = operation.get("requestBody") or {}
    required = bool(body.get("required"))
    content = body.get("content") or {}
    json_schema = (content.get("application/json") or {}).get("schema")

    if not json_schema:
        return required, None

    payload = _schema_example(json_schema, openapi)
    if isinstance(payload, (dict, list)):
        return required, payload

    return required, {"value": payload}


def test_v1_mutating_endpoints_do_not_raise_5xx(client, admin_token, db):
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

        for method in _METHODS:
            if checked >= _MAX_CHECKED:
                break
            op = methods.get(method)
            if not op:
                continue

            checked += 1
            params = _build_required_query(op)
            body_required, body = _build_body(op, openapi)

            request_args: dict[str, Any] = {
                "headers": auth(admin_token),
                "params": params,
            }
            if body is not None:
                request_args["json"] = body
            elif body_required:
                request_args["json"] = {}

            try:
                res = client.request(method.upper(), path, **request_args)
            except Exception as exc:
                failures.append(f"{method.upper()} {path} -> exception: {exc}")
                continue

            if res.status_code >= 500:
                failures.append(f"{method.upper()} {path} -> {res.status_code}")

    assert checked > 0
    assert not failures, "\n" + "\n".join(failures)
