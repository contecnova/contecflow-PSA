"""v2 meta endpoints — version information and change-log for API consumers.

EXENTO del envelope canónico a propósito (audit #67 / auditoría 2026-07): este es el
endpoint de descubrimiento de versión, es público y lo consumen clientes externos que
leen `api_version` en la raíz del body. Envolverlo en {data, meta} rompería a esos
consumidores sin ningún beneficio. No lo migres.
"""
from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()

_V2_BREAKING_CHANGES = [
    {
        "change": "multi_currency_profitability",
        "description": (
            "Profitability costs are normalized to the org base currency "
            "using the exchange rate effective on the imputation date. "
            "Response includes 'project_currency' and 'reporting_currency' fields."
        ),
        "affected_endpoints": ["/profitability/summary", "/profitability/{project_id}"],
    },
    {
        "change": "sla_persisted_metrics",
        "description": (
            "Ticket responses include persisted 'sla_response_breached', "
            "'sla_resolution_breached', 'first_response_minutes', and "
            "'resolution_minutes' fields computed at resolution time, "
            "not recalculated on every query."
        ),
        "affected_endpoints": ["/sd/tickets/{id}", "/sd/tickets"],
    },
    {
        "change": "financial_approval_audit_log",
        "description": (
            "Financial approval decisions (timesheet, expense, milestone, "
            "purchase, invoice) are written to an immutable audit log "
            "separate from the general activity log. "
            "New endpoint: GET /approvals/requests/{id}/financial-audit"
        ),
        "affected_endpoints": ["/approvals/requests/{id}/financial-audit"],
    },
    {
        "change": "versioned_error_envelopes",
        "description": (
            "HTTP 4xx/5xx error responses include 'api_version': 2 in the "
            "JSON body alongside 'detail'."
        ),
        "affected_endpoints": ["*"],
    },
]


@router.get("/version", summary="API v2 version info")
def get_version():
    """Return version metadata and the list of breaking changes vs v1."""
    return {
        "api_version": 2,
        "app_version": settings.VERSION,
        "v1_path": settings.API_V1_STR,
        "v2_path": settings.API_V2_STR,
        "v1_status": "active",
        "v1_sunset_notice": (
            "v1 endpoints remain available. Set X-API-Version: 2 or use "
            "/api/v2 prefix to opt in to v2 contract. "
            "v1 sunset date will be announced via X-API-Deprecated header."
        ),
        "breaking_changes_vs_v1": _V2_BREAKING_CHANGES,
    }
