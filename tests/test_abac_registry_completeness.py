from app.core.abac_registry import ABAC_EXEMPT_PREFIXES, ABAC_ROUTE_REGISTRY
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


# ══════════════════════════════════════════════════════════════════════════════
# Cobertura TOTAL del registro (auditoría 2026-07, docs/AUDIT_2026_07_FULL.md §1.5)
#
# Los dos tests de arriba solo vigilaban 12 prefijos críticos de los 127 que expone
# la API, así que un dominio nuevo entero podía nacer sin ninguna decisión sobre
# ABAC. Estos tests exigen que CADA prefijo de primer nivel esté clasificado:
# o en ABAC_ROUTE_REGISTRY, o en ABAC_EXEMPT_PREFIXES con su motivo.
# ══════════════════════════════════════════════════════════════════════════════

def _api_prefixes() -> set[str]:
    """Prefijos de primer nivel: /api/v1/<segmento> y /api/v2/<segmento>."""
    prefixes: set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v"):
            continue
        parts = path.split("/")
        if len(parts) < 4 or not parts[3]:
            continue
        prefixes.add("/".join(parts[:4]))
    return prefixes


def test_every_api_prefix_is_registered_or_exempt() -> None:
    undecided = sorted(
        p for p in _api_prefixes()
        if p not in ABAC_ROUTE_REGISTRY and p not in ABAC_EXEMPT_PREFIXES
    )
    assert not undecided, (
        "Prefijos de API sin decisión sobre ABAC. Añade cada uno a "
        "ABAC_ROUTE_REGISTRY (con su resource_type) o a ABAC_EXEMPT_PREFIXES "
        "(con el motivo):\n  - " + "\n  - ".join(undecided)
    )


def test_no_prefix_is_both_registered_and_exempt() -> None:
    overlap = sorted(set(ABAC_ROUTE_REGISTRY) & set(ABAC_EXEMPT_PREFIXES))
    assert not overlap, f"Prefijos declarados a la vez en registro y exentos: {overlap}"


def test_registry_and_exemptions_have_no_stale_prefixes() -> None:
    """Evita que ambas listas acumulen prefijos de rutas que ya no existen."""
    live = _api_prefixes()
    # El registro admite prefijos más específicos que el primer nivel (p.ej. si en
    # el futuro se acota /api/v1/bi/embed), así que solo exigimos que el primer
    # nivel del prefijo declarado siga existiendo.
    stale_registry = sorted(
        p for p in ABAC_ROUTE_REGISTRY
        if "/".join(p.split("/")[:4]) not in live
    )
    stale_exempt = sorted(p for p in ABAC_EXEMPT_PREFIXES if p not in live)
    assert not stale_registry, f"Prefijos del registro que ya no existen: {stale_registry}"
    assert not stale_exempt, f"Prefijos exentos que ya no existen: {stale_exempt}"


def test_exemptions_document_a_reason() -> None:
    empty = sorted(p for p, reason in ABAC_EXEMPT_PREFIXES.items() if not (reason or "").strip())
    assert not empty, f"Exenciones sin motivo escrito: {empty}"
