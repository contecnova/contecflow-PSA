"""
Test para detectar rutas duplicadas o conflictos de prefijos en los routers de FastAPI.
"""
from collections import Counter
from fastapi import FastAPI
from app.api.v1 import router as v1_router


def _path_method_pairs(app: FastAPI):
    pairs = []
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            pairs.append((route.path, method))
    return pairs


def _assert_no_duplicate_pairs(app: FastAPI, version_label: str):
    pairs = _path_method_pairs(app)
    dupes = [pair for pair, count in Counter(pairs).items() if count > 1]
    assert not dupes, f"Rutas duplicadas detectadas en {version_label}: {dupes}"


def _assert_unique_operation_paths(app: FastAPI, version_label: str):
    spec = app.openapi()
    dupes = []
    for path, methods in spec.get("paths", {}).items():
        seen = set()
        for method, op in methods.items():
            op_id = op.get("operationId")
            if not op_id:
                continue
            key = (method.lower(), op_id)
            if key in seen:
                dupes.append((path, method, op_id))
            seen.add(key)
    assert not dupes, f"OpenAPI con operationId duplicado en {version_label}: {dupes}"


def test_no_duplicate_routes_v1():
    app = FastAPI()
    app.include_router(v1_router.api_router, prefix="/api/v1")
    _assert_no_duplicate_pairs(app, "API v1")
    _assert_unique_operation_paths(app, "API v1")
