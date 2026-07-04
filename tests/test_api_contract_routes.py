"""Frontend↔backend route contract.

Several user-facing features broke when router prefixes were refactored but the
axios client kept calling the old paths (forecasting, invoice status change,
scheduled reports, automation workflows). This test pins the client's critical
API paths to actually-registered FastAPI routes, so a future prefix change
fails here instead of silently 404-ing in production.

The path templates below mirror frontend/src/services/api/_core.ts; `{}` stands
for any path parameter.
"""
import re

import pytest

from app.main import app
from app.core.config import settings


def _norm(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


@pytest.fixture(scope="module")
def registered_routes():
    routes = set()
    for r in app.routes:
        methods = getattr(r, "methods", None)
        path = getattr(r, "path", None)
        if not methods or not path:
            continue
        norm = _norm(path)
        for m in methods:
            routes.add((m.upper(), norm))
    return routes


# (method, client-path) pairs the axios client actually issues. Without the
# API_V1 prefix — it's prepended below.
CLIENT_CONTRACT = [
    # BI forecasting (was /bi/forecasting/* — nonexistent)
    ("GET",    "/bi/forecast/metrics"),
    ("POST",   "/bi/forecast"),
    ("POST",   "/bi/forecast/multi"),
    # Invoice status change (was /invoices/{}/status)
    ("PATCH",  "/billing-reports/invoices/{}/status"),
    # Scheduled reports (was /scheduled-reports*)
    ("GET",    "/billing-reports/scheduled-reports"),
    ("POST",   "/billing-reports/scheduled-reports"),
    ("DELETE", "/billing-reports/scheduled-reports/{}"),
    ("POST",   "/billing-reports/scheduled-reports/{}/run"),
    ("PATCH",  "/billing-reports/scheduled-reports/{}"),
    # Automation workflows (was /workflows*)
    ("GET",    "/billing-reports/automation-workflows"),
    ("POST",   "/billing-reports/automation-workflows"),
    ("PATCH",  "/billing-reports/automation-workflows/{}"),
]


@pytest.mark.parametrize("method,path", CLIENT_CONTRACT)
def test_client_path_is_registered(registered_routes, method, path):
    full = _norm(f"{settings.API_V1_STR}{path}")
    assert (method, full) in registered_routes, (
        f"Client calls {method} {full} but no backend route is registered for it"
    )
