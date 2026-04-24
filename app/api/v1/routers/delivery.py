"""
Delivery domain — project delivery tools, resource management, documents,
reporting, and finance modules.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    billing_reports, bookings, cab, mfa, custom_fields, epics,
    issue_types, cmdb, activity, raci,
    alm, clients, rate_cards, milestones, resource_forecast, approvals,
    accounting_hub, okrs, performance, training, documents, resources,
    invoices, documents_collab, analytics_extended, portfolio,
    git_integration, esign, report_builder, nps, m365,
    backlog, export_template, cicd, events, documents_edit,
    gantt_suggestions, template, templates,
)
from app.api.v1.endpoints.v239 import baselines as baselines_v239, approval_builder as approval_builder_v239

router = APIRouter()

# ── Domain modules ─────────────────────────────────────────────────────────────
router.include_router(billing_reports.router,  prefix="/billing-reports",  tags=["Billing & Reports"])
router.include_router(bookings.router,         prefix="/bookings",         tags=["Bookings & Currency"])
router.include_router(cab.router,                                          tags=["CAB & Webhooks"])
router.include_router(mfa.router,                                          tags=["MFA & Budgets"])
router.include_router(custom_fields.router,    prefix="/custom-fields",    tags=["Custom Fields"])
router.include_router(epics.router,            prefix="/epics",            tags=["Epics & Wiki"])
router.include_router(issue_types.router,      prefix="/issue-types",      tags=["Issue Types & FTS"])
router.include_router(cmdb.router,             prefix="/cmdb",             tags=["CMDB & Kanban"])
router.include_router(cmdb.sd_router,          prefix="/sd",               tags=["SD Internal Comments"])
router.include_router(activity.router,         prefix="/activity",         tags=["Activity & Mentions"])
# Canonical RACI/UAT paths are defined inside the endpoint module
# (e.g. /projects/{project_id}/raci). Keep a prefixed alias for compatibility.
router.include_router(raci.router,                                         tags=["RACI & UAT"])
router.include_router(raci.router,             prefix="/raci",             tags=["RACI & UAT"])

# ── Canonical modules ──────────────────────────────────────────────────────────
router.include_router(alm.router,              prefix="/alm",              tags=["ALM"])
router.include_router(clients.router,          prefix="/clients",          tags=["Clients"])
router.include_router(rate_cards.router,       prefix="/rate-cards",       tags=["Rate Cards"])
router.include_router(milestones.router,       prefix="/milestones",       tags=["Milestones"])
router.include_router(resource_forecast.router, prefix="/resource-forecast", tags=["Resource Forecast"])
router.include_router(approvals.router,        tags=["Approvals"])
router.include_router(accounting_hub.router,   tags=["Accounting Hub"])
router.include_router(okrs.router,             prefix="/okrs",             tags=["OKRs"])
router.include_router(performance.router,      prefix="/performance",      tags=["Performance"])
router.include_router(training.router,         prefix="/training",         tags=["Training"])
router.include_router(documents.router,        tags=["Documents"])
router.include_router(resources.router,        prefix="/resources",        tags=["Resources"])
router.include_router(invoices.router,         prefix="/invoices",         tags=["Invoices"])
router.include_router(documents_collab.router, prefix="/documents-collab", tags=["Documents Collab"])
router.include_router(analytics_extended.router, prefix="/analytics-extended", tags=["Analytics Extended"])
router.include_router(portfolio.router,        prefix="/portfolios",       tags=["Portfolio"])
router.include_router(git_integration.router,  prefix="/git",              tags=["Git Integration"])
router.include_router(esign.router,            prefix="/esign",            tags=["E-Firma"])
router.include_router(report_builder.router,   prefix="/reports",          tags=["Report Builder"])
router.include_router(nps.router,              prefix="/nps",              tags=["NPS & Health"])
router.include_router(m365.router,             prefix="/m365",             tags=["Microsoft 365"])

# ── Framework/pipeline modules ─────────────────────────────────────────────────
router.include_router(backlog.router,          tags=["Backlog"])
router.include_router(export_template.router,  tags=["Export Templates"])
router.include_router(cicd.router,             tags=["CICD"])
router.include_router(events.router,           tags=["Events"])
router.include_router(documents_edit.router,   tags=["Documents"])
router.include_router(gantt_suggestions.router, tags=["Gantt Suggestions"])
router.include_router(baselines_v239.router,    tags=["Gantt Baselines"])
router.include_router(templates.router,         prefix="/templates",     tags=["Templates Enhanced"])
router.include_router(approval_builder_v239.router,                      tags=["Approval Workflow Builder"])
router.include_router(template.router,         tags=["Templates"])
