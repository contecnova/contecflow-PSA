from app.core.abac_registry import ABAC_ROUTE_REGISTRY
from app.main import app


CRITICAL_PREFIXES = (
    "/api/v1/projects",
    "/api/v1/tasks",
    "/api/v1/users",
    "/api/v1/sd",
    "/api/v1/billing-reports",
    "/api/v1/invoices",
    "/api/v1/imputations",
    "/api/v1/timesheets",
    "/api/v1/clients",
    "/api/v1/contracts",
    "/api/v1/expenses",
    "/api/v1/risks",
)

EXPLICIT_CRITICAL_DOMAIN_EXCLUSIONS = (
    "/api/v1/auth/",
    "/api/v1/health",
    "/api/v1/scim",
    "/api/v1/public",
)


def _has_registry_match(path: str) -> bool:
    for prefix in ABAC_ROUTE_REGISTRY:
        if path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "?"):
            return True
    return False


def test_critical_routes_have_abac_registry_prefix() -> None:
    excluded_paths = {
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/health",
        "/api/v1/health/ready",
        "/api/v1/health/live",
    }

    missing: list[str] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v1/"):
            continue
        if path in excluded_paths:
            continue
        if any(path.startswith(prefix) for prefix in CRITICAL_PREFIXES):
            if not _has_registry_match(path):
                missing.append(path)

    assert not missing, f"Rutas críticas sin ABAC registry: {missing}"


def test_critical_domain_prefixes_are_declared_or_explicitly_excluded() -> None:
    """Guardrail for new routes in critical areas.

    Any new API v1 route under a critical domain must either:
    - be covered by ABAC_ROUTE_REGISTRY, or
    - be explicitly listed as an intentional exclusion.
    """
    violations: list[str] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v1/"):
            continue
        if not any(path.startswith(prefix) for prefix in CRITICAL_PREFIXES):
            continue
        if _has_registry_match(path):
            continue
        if any(path.startswith(ex) for ex in EXPLICIT_CRITICAL_DOMAIN_EXCLUSIONS):
            continue
        violations.append(path)

    assert not violations, (
        "Rutas críticas detectadas fuera de cobertura ABAC y sin exclusión explícita: "
        f"{violations}"
    )
