"""
Delivery domain — project delivery tools, resource management, documents,
reporting, and finance modules.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    billing_reports, bookings, cab, mfa, custom_fields, epics,
    # Auditoria 2026-08 (hallazgo 22): estos siete estaban dentro de `mfa`,
    # un router de 38 rutas y ocho dominios. Los paths no han cambiado.
    organizations, slack, budgets, ai_planning, scenarios, pdf_export,
    bi_tokens,
    issue_types, cmdb, activity, raci,
    alm, clients, rate_cards, milestones, resource_forecast, approvals,
    accounting_hub, okrs, performance, training, documents, resources,
    invoices, documents_collab, analytics_extended, portfolio,
    git_integration, esign, report_builder, nps, m365, m365_bi,
    backlog, export_template, events,
    gantt_suggestions, templates, revenue, predictions,
    bi_collaboration, bi_intelligence, bi_platform,
    bi_smart_alerts, bi_bookmarks, bi_report_builder_v2,
    bi_embed, bi_export, bi_data_versioning, bi_governance,
    predictive_observability,
    bi_forecasting, bi_anomaly, bi_gdpr, bi_dashboard_collab,
    bi_query_builder, bi_conditional_delivery, bi_etl, bi_o365,
)
# Auditoría 2026-08 (hallazgo 22): antes venían de `endpoints/v239/`, un
# directorio nombrado por número de versión. Las rutas no han cambiado.
from app.api.v1.endpoints import baselines, approval_builder

router = APIRouter()

# ── Domain modules ─────────────────────────────────────────────────────────────
router.include_router(billing_reports.router,  prefix="/billing-reports",  tags=["Billing & Reports"])
router.include_router(bookings.router,         prefix="/bookings",         tags=["Bookings & Currency"])
router.include_router(cab.router,                                          tags=["CAB & Webhooks"])
# Auditoria 2026-08 (hallazgo 22). Antes esto era una sola linea con
# tags=["MFA & Budgets"], y detras habia 38 rutas de ocho dominios distintos: el
# CRUD de organizaciones estaba escondido ahi, y por eso nadie noto que le faltaba
# la guarda de superadministrador — fue la causa proxima del P0 numero 1.
# Los paths son EXACTAMENTE los mismos: ABAC y GRC derivan el modulo de la ruta.
router.include_router(mfa.router,                                          tags=["MFA"])
router.include_router(organizations.router,                                tags=["Organizaciones"])
router.include_router(slack.router,                                        tags=["Slack"])
router.include_router(budgets.router,                                      tags=["Presupuestos"])
router.include_router(ai_planning.router,                                  tags=["Planificación asistida"])
router.include_router(scenarios.router,                                    tags=["Escenarios"])
router.include_router(pdf_export.router,                                   tags=["Exportación PDF"])
router.include_router(bi_tokens.router,                                    tags=["BI externo"])
router.include_router(custom_fields.router,                        tags=["Custom Fields"])
router.include_router(epics.router,            prefix="/epics",            tags=["Epics & Wiki"])
router.include_router(issue_types.router,                                  tags=["Issue Types & FTS"])
# Auditoria 2026-08: `issue_types.router` estaba registrado DOS VECES, sin
# prefijo (linea de arriba) y con prefijo "/issue-types". Consecuencias:
#
#   · cada ruta existia duplicada;
#   · las rutas del fichero ya empiezan por "/issue-types", asi que el
#     registro con prefijo producia el absurdo
#     `/api/v1/issue-types/issue-types/{project_id}`;
#   · y `/api/v1/issue-types/{project_id}` (del registro sin prefijo, que va
#     primero) TAPABA a `/api/v1/issue-types/task-dependencies` y a otras
#     cinco del registro con prefijo, que quedaban inalcanzables.
#
# Se retira el registro con prefijo: el frontend usa las rutas sin prefijo
# —comprobado— y nadie llama a las dobles.
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
router.include_router(documents_collab.router,                             tags=["Documents Collab"])
router.include_router(analytics_extended.router,                           tags=["Analytics Extended"])
router.include_router(portfolio.router,        prefix="/portfolios",       tags=["Portfolio"])
router.include_router(git_integration.router,  prefix="/git",              tags=["Git Integration"])
router.include_router(esign.router,            prefix="/esign",            tags=["E-Firma"])
router.include_router(report_builder.router,   prefix="/reports",          tags=["Report Builder"])
router.include_router(bi_collaboration.router,                              tags=["BI Collaboration"])
router.include_router(bi_intelligence.router,                               tags=["BI Intelligence"])
router.include_router(bi_platform.router,                                   tags=["BI Platform"])
router.include_router(bi_smart_alerts.router,                               tags=["BI Smart Alerts"])
router.include_router(bi_bookmarks.router,                                  tags=["BI Bookmarks"])
router.include_router(bi_report_builder_v2.router,                          tags=["BI Report Builder v2"])
router.include_router(bi_embed.router,                                      tags=["BI Embedded SDK"])
router.include_router(bi_export.router,                                     tags=["BI Export"])
router.include_router(bi_data_versioning.router,                            tags=["BI Data Versioning"])
router.include_router(bi_governance.router,                                 tags=["BI Governance"])
router.include_router(predictive_observability.router,                      tags=["Predictive Observability"])
router.include_router(nps.router,              prefix="/nps",              tags=["NPS & Health"])
router.include_router(m365.router,             prefix="/m365",             tags=["Microsoft 365"])
router.include_router(m365_bi.router,                                          tags=["M365 BI Embed"])

# ── Framework/pipeline modules ─────────────────────────────────────────────────
router.include_router(backlog.router,          tags=["Backlog"])
router.include_router(export_template.router,  tags=["Export Templates"])
router.include_router(events.router,           tags=["Events"])
# Revisión 2026-11: fuera `PATCH /documents/{id}/edit`, un stub que contestaba «ok» sin hacer nada.
router.include_router(gantt_suggestions.router, tags=["Gantt Suggestions"])
router.include_router(baselines.router,    tags=["Gantt Baselines"])
router.include_router(templates.router,         prefix="/templates",     tags=["Templates Enhanced"])
router.include_router(approval_builder.router,                      tags=["Approval Workflow Builder"])
router.include_router(revenue.router,          prefix="/revenue-recognition", tags=["Revenue Recognition"])
router.include_router(predictions.router,      prefix="/predictions",         tags=["AI Predictions"])
router.include_router(bi_forecasting.router,                                tags=["BI Forecasting"])
router.include_router(bi_anomaly.router,                                    tags=["BI Anomaly & Churn"])
router.include_router(bi_gdpr.router,                                       tags=["BI GDPR"])
router.include_router(bi_dashboard_collab.router,                           tags=["BI Dashboard Collab"])
router.include_router(bi_query_builder.router,                              tags=["BI Query Builder"])
router.include_router(bi_conditional_delivery.router,                       tags=["BI Conditional Delivery"])
router.include_router(bi_etl.router,                                        tags=["BI ETL Connectors"])
router.include_router(bi_o365.router,                                       tags=["BI Office 365"])
