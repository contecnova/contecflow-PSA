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
    labels, translations,
    resource_demand, jira_integration,
)
# Auditoría 2026-08 (hallazgo 22): antes venía de `endpoints/v239/`.
from app.api.v1.endpoints import branding
from app.api.v1.endpoints import conectores
from app.api.v1.endpoints import lecciones
from app.api.v1.endpoints import politicas
from app.api.v1.endpoints import errores_del_frontend
from app.api.v1.endpoints import seguridad_de_cuentas

router = APIRouter()

# ── External integrations ──────────────────────────────────────────────────────
router.include_router(integrations.router,         prefix="/integrations",          tags=["Integrations"])
router.include_router(integrations_hub.router,     prefix="/integrations-hub",      tags=["Integrations Hub"])
router.include_router(jira.router,                 prefix="/jira",                  tags=["Jira"])
router.include_router(jira_integration.router,                                     tags=["Jira Integration"])
router.include_router(grc.router,                  prefix="/grc",                   tags=["GRC"])
router.include_router(salesforce_sync.router,      prefix="/salesforce-sync",       tags=["Salesforce Sync"])
router.include_router(slack_block_kit.router,                                   tags=["Slack Block Kit"])
router.include_router(currency_sync.router,                                      tags=["Currency Sync"])
router.include_router(currency_rates.router,                                     tags=["Currency Rates"])

# ── Identity, access & compliance ─────────────────────────────────────────────
router.include_router(scim.router,                 tags=["SCIM"])
router.include_router(governance.router,           tags=["Governance"])
router.include_router(abac.router,                 prefix="/abac",                  tags=["ABAC"])
router.include_router(abac_admin.router,                                        tags=["ABAC Admin"])
router.include_router(security_observability.router, prefix="/security-observability", tags=["Security Observability"])
# 23-11-2026: políticas de cuenta (docs/seguridad/politicas_de_cuenta.md).
router.include_router(seguridad_de_cuentas.router, prefix="/security",          tags=["Seguridad de cuentas"])

# ── Public-facing & developer surfaces ────────────────────────────────────────
router.include_router(public_forms.router,                                          tags=["Public Forms"])
router.include_router(developer_portal.router,                                          tags=["Developer Portal"])

# ── Customisation & platform tooling ──────────────────────────────────────────
router.include_router(branding.router,                                      tags=["Branding"])
router.include_router(labels.router,               prefix="/labels",                tags=["Labels"])
router.include_router(translations.router,         prefix="/translations",          tags=["Translations"])
# 18-11-2026: `/ui` (accessibility, keyboard-nav, labels) era un endpoint de
# relleno con textos fijos que no usaba nadie (ni el frontend ni otro servicio):
# retirado. Las etiquetas de la interfaz viven en `frontend/src/i18n`.
router.include_router(resource_demand.router,      prefix="/resource-demand",       tags=["Resource Demand"])
router.include_router(conectores.router,           prefix="/conectores",            tags=["Conectores contecmind y contecintelligence"])
router.include_router(lecciones.router,            prefix="/lessons",               tags=["Lecciones aprendidas"])
router.include_router(politicas.router,            prefix="/policies",              tags=["Políticas y reglas"])
router.include_router(errores_del_frontend.router, prefix="/client-errors",         tags=["Errores del frontend"])
# Revisión posterior a la implantación (PIR) de cambios y proyectos (migración 206, docs/PIR.md)
from app.api.v1.endpoints import pir  # noqa: E402
router.include_router(pir.router,                  prefix="/pir",                   tags=["PIR"])
