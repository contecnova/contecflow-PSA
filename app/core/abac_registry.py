"""
ABAC route registry.

Maps URL path prefixes to (resource_type, action) tuples that the
ABACMiddleware will enforce automatically.  The middleware performs an
opt-in check: only routes whose prefix appears in this dict are verified.
Routes NOT listed here are left to endpoint-level guards or RBAC.

Key format: path prefix (without trailing slash).
Value format: (resource_type, action)
"""

ABAC_ROUTE_REGISTRY: dict[str, tuple[str, str]] = {
    "/api/v1/projects":     ("project",     "read"),
    "/api/v1/tasks":        ("task",        "read"),
    "/api/v1/imputations":  ("imputation",  "read"),
    "/api/v1/timesheets":   ("timesheet",   "read"),
    "/api/v1/clients":      ("client",      "read"),
    "/api/v1/contracts":    ("contract",    "read"),
    "/api/v1/invoices":     ("invoice",     "read"),
    "/api/v1/expenses":     ("expense",     "read"),
    "/api/v1/risks":        ("risk",        "read"),
}
