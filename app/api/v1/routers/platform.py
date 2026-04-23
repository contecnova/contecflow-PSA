"""
Platform domain — enterprise integrations, security, compliance, and admin tooling.

Covers: external system connectors (Jira, Salesforce, Slack, M365 sync),
identity/access management (SCIM, ABAC, governance), GRC, public-facing
surfaces (public forms, developer portal), and branding/customisation.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    integrations, integrations_hub,
    jira, grc, salesforce_sync, slack_block_kit,
    currency_sync, currency_rates,
    scim, governance, abac, abac_admin, security_observability,
    public_forms, developer_portal,
    branding, marketplace, collaborative, labels, translations, ui,
    resource_demand,
)

router = APIRouter()

# ── External integrations ──────────────────────────────────────────────────────
router.include_router(integrations.router,         prefix="/integrations",          tags=["Integrations"])
router.include_router(integrations_hub.router,     prefix="/integrations-hub",      tags=["Integrations Hub"])
router.include_router(jira.router,                 prefix="/jira",                  tags=["Jira"])
router.include_router(grc.router,                  prefix="/grc",                   tags=["GRC"])
router.include_router(salesforce_sync.router,      prefix="/salesforce-sync",       tags=["Salesforce Sync"])
router.include_router(slack_block_kit.router,      prefix="/slack-block-kit",       tags=["Slack Block Kit"])
router.include_router(currency_sync.router,        prefix="/currency-sync",         tags=["Currency Sync"])
router.include_router(currency_rates.router,       prefix="/currency-rates",        tags=["Currency Rates"])

# ── Identity, access & compliance ─────────────────────────────────────────────
router.include_router(scim.router,                 tags=["SCIM"])
router.include_router(governance.router,           tags=["Governance"])
router.include_router(abac.router,                 prefix="/abac",                  tags=["ABAC"])
router.include_router(abac_admin.router,           prefix="/abac-admin",            tags=["ABAC Admin"])
router.include_router(security_observability.router, prefix="/security-observability", tags=["Security Observability"])

# ── Public-facing & developer surfaces ────────────────────────────────────────
router.include_router(public_forms.router,                                          tags=["Public Forms"])
router.include_router(developer_portal.router,                                          tags=["Developer Portal"])

# ── Customisation & platform tooling ──────────────────────────────────────────
router.include_router(branding.router,             prefix="/branding",              tags=["Branding"])
router.include_router(marketplace.router,          prefix="/marketplace",           tags=["Marketplace"])
router.include_router(collaborative.router,        prefix="/collaborative",         tags=["Collaborative"])
router.include_router(labels.router,               prefix="/labels",                tags=["Labels"])
router.include_router(translations.router,         prefix="/translations",          tags=["Translations"])
router.include_router(ui.router,                   prefix="/ui",                    tags=["UI"])
router.include_router(resource_demand.router,      prefix="/resource-demand",       tags=["Resource Demand"])
