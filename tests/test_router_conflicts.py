"""
Test para detectar rutas duplicadas o conflictos de prefijos en los routers de FastAPI.
"""
import pytest
from fastapi import FastAPI
from app.api.v1 import router as v1_router
from app.api.v2 import router as v2_router


def get_routes(app: FastAPI):
    """Devuelve un set de (path, method) para todas las rutas registradas."""
    return set((route.path, tuple(route.methods)) for route in app.routes if hasattr(route, 'methods'))


def test_no_duplicate_routes_v1():
    app = FastAPI()
    app.include_router(v1_router.api_router, prefix="/api/v1")
    routes = get_routes(app)
    paths = [(path, method) for (path, methods) in routes for method in methods]
    assert len(paths) == len(set(paths)), "Rutas duplicadas detectadas en API v1: {}".format([
        p for p in paths if paths.count(p) > 1
    ])

def test_no_duplicate_routes_v2():
    app = FastAPI()
    app.include_router(v2_router.api_router, prefix="/api/v2")
    routes = get_routes(app)
    paths = [(path, method) for (path, methods) in routes for method in methods]
    assert len(paths) == len(set(paths)), "Rutas duplicadas detectadas en API v2: {}".format([
        p for p in paths if paths.count(p) > 1
    ])


def test_no_conflicting_prefixes():
    """
    Verifica que no existan prefijos de routers que sean subcadena exacta de otros (riesgo de shadowing).
    """
    from app.api.v1.router import api_router as v1_api_router
    prefixes = [r.prefix for r in v1_api_router.routes if hasattr(r, 'prefix')]
    for i, p1 in enumerate(prefixes):
        for j, p2 in enumerate(prefixes):
            if i != j and p1 and p2 and (p1.startswith(p2) or p2.startswith(p1)):
                assert p1 == p2, f"Conflicto de prefijos: '{p1}' y '{p2}'"
