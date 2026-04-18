"""API v2 router.

v2 is the forward-compatible contract surface.  Breaking changes that cannot be
introduced in v1 without violating backward-compatibility are added here.

Migration guide from v1
-----------------------
* All v1 endpoints remain available under /api/v1 and will continue to work
  until the v1 sunset date announced in X-API-Deprecated response headers.
* v2 introduces the following breaking changes vs v1:

  1. Multi-currency costs — profitability responses include ``project_currency``
     and ``reporting_currency`` fields; ``internal_cost`` is normalized to the
     org base currency (was: raw sum of imputation amounts, currency-unaware).

  2. SLA metrics — ticket responses include persisted ``sla_response_breached``
     and ``sla_resolution_breached`` boolean fields and minute-resolution
     ``first_response_minutes`` / ``resolution_minutes`` integers (was: computed
     on-the-fly from datetime subtraction on every GET).

  3. Financial approval audit — GET /approvals/requests/{id}/financial-audit
     endpoint available; immutable ``financial_approval_audit_logs`` table.

  4. Versioned error envelopes — HTTP 4xx/5xx bodies include ``"api_version": 2``
     alongside ``"detail"`` (was: plain FastAPI default).

Adding new v2 endpoints
-----------------------
Create a module under ``app/api/v2/endpoints/`` and include its router below,
following the same pattern as v1.
"""
from fastapi import APIRouter

from app.api.v2.endpoints import meta, profitability
 # from app.api.v1.endpoints import v238_features, v239_features  # Eliminado temporalmente por ausencia de archivo

api_v2_router = APIRouter()

# ── Core meta ─────────────────────────────────────────────────────────────────
api_v2_router.include_router(meta.router, prefix="", tags=["API v2 Meta"])

# ── Profitability v2 — multi-currency aware ───────────────────────────────────
api_v2_router.include_router(profitability.router)

# ── v23.8 feature set — now versioned under /api/v2 ──────────────────────────
# NOTE: the same endpoints are still available under /api/v1 for backward
# compatibility (see app/api/v1/router.py).  New integrations should target /v2.
   # api_v2_router.include_router(
   #     v238_features.router,
   #     prefix="/v238",
   #     tags=["v23.8 Features"],
   # )

# ── v23.9 feature set — now versioned under /api/v2 ──────────────────────────
   # api_v2_router.include_router(
   #     v239_features.router,
   #     prefix="/v239",
   #     tags=["v23.9 Features"],
   # )
