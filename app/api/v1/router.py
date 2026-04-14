from fastapi import APIRouter
from app.api.v1.endpoints import (
    integrations, auth, users, projects, tasks, imputations, dashboard,
    alerts, settings, timesheets, capacity, profitability, pipeline,
    contracts, risks, skills, absences, changes, deliverables,
    advanced_config, analytics, client_portal, service_desk, sprints,
    expenses, automations, enterprise,
    # Domain modules (formerly named vXX)
    billing_reports, bookings, cab, mfa, ai_chat, ai_modules,
    custom_fields, epics, issue_types, cmdb, activity, raci,
    # Canonical modules
    alm, clients, ai_providers, semantic_engine, rate_cards, milestones,
    resource_forecast, approvals, integrations_hub, ws, accounting_hub,
    okrs, performance, training, documents, resources, analytics_extended,
    portfolio, git_integration, esign, report_builder, nps, m365, grc,
    public_forms, developer_portal, scim, governance, abac,
    security_observability, ai_governance, abac_admin, jira,
    currency_sync, currency_rates, salesforce_sync, slack_block_kit,
    v238_features,
    v239_features,
)

api_router = APIRouter()
api_router.include_router(auth.router,             prefix="/auth",             tags=["Auth"])
api_router.include_router(users.router,            prefix="/users",            tags=["Usuarios"])
api_router.include_router(projects.router,         prefix="/projects",         tags=["Proyectos"])
api_router.include_router(tasks.router,            prefix="/tasks",            tags=["Tareas"])
api_router.include_router(imputations.router,      prefix="/imputations",      tags=["Imputaciones"])
api_router.include_router(dashboard.router,        prefix="/dashboard",        tags=["Dashboard"])
api_router.include_router(alerts.router,           prefix="/alerts",           tags=["Alertas"])
api_router.include_router(settings.router,         prefix="/settings",         tags=["Configuración"])
api_router.include_router(timesheets.router,       prefix="/timesheets",       tags=["Timesheets"])
api_router.include_router(capacity.router,         prefix="/capacity",         tags=["Capacidad"])
api_router.include_router(profitability.router,    prefix="/profitability",    tags=["Rentabilidad"])
api_router.include_router(pipeline.router,         prefix="/pipeline",         tags=["Pipeline"])
api_router.include_router(contracts.router,        prefix="/contracts",        tags=["Contratos"])
api_router.include_router(risks.router,            prefix="/risks",            tags=["Riesgos"])
api_router.include_router(skills.router,           prefix="/skills",           tags=["Skills"])
api_router.include_router(absences.router,         prefix="/absences",         tags=["Ausencias"])
api_router.include_router(changes.router,          prefix="/changes",          tags=["Control de Cambios"])
api_router.include_router(deliverables.router,     prefix="/deliverables",     tags=["Entregables"])
api_router.include_router(advanced_config.router,  prefix="/advanced-config",  tags=["Configuración Avanzada"])
api_router.include_router(analytics.router,        prefix="/analytics",        tags=["Analytics"])
api_router.include_router(client_portal.router,    prefix="/portal",           tags=["Portal Cliente"])
api_router.include_router(service_desk.router,     prefix="/sd",               tags=["Service Desk"])
api_router.include_router(sprints.router,          prefix="/sprints",          tags=["Sprints"])
api_router.include_router(expenses.router,         prefix="/expenses",         tags=["Gastos"])
api_router.include_router(automations.router,      prefix="/automations",      tags=["Automatizaciones"])
api_router.include_router(enterprise.router,       prefix="/enterprise",       tags=["Enterprise"])
# Domain modules
api_router.include_router(billing_reports.router,  tags=["Billing & Reports"])
api_router.include_router(bookings.router,         tags=["Bookings & Currency"])
api_router.include_router(cab.router,              tags=["CAB & Webhooks"])
api_router.include_router(mfa.router,              tags=["MFA & Budgets"])
api_router.include_router(ai_chat.router,          tags=["AI Assistant"])
api_router.include_router(ai_modules.router,       tags=["AI Modules"])
api_router.include_router(custom_fields.router,    tags=["Custom Fields"])
api_router.include_router(epics.router,            tags=["Epics & Wiki"])
api_router.include_router(issue_types.router,      tags=["Issue Types & FTS"])
api_router.include_router(cmdb.router,             tags=["CMDB & Kanban"])
api_router.include_router(cmdb.sd_router,          prefix="/sd",               tags=["SD Internal Comments"])
api_router.include_router(activity.router,         tags=["Activity & Mentions"])
api_router.include_router(raci.router,             tags=["RACI & UAT"])
# Canonical modules
api_router.include_router(integrations.router,     prefix="/integrations",     tags=["Integrations"])
api_router.include_router(alm.router,              prefix="/alm",              tags=["ALM"])
api_router.include_router(clients.router,          prefix="/clients",          tags=["Clients"])
api_router.include_router(ai_providers.router,     prefix="/ai-providers",     tags=["AI Providers"])
api_router.include_router(semantic_engine.router,  prefix="/semantic",         tags=["Semantic Engine"])
api_router.include_router(rate_cards.router)        # prefix="/rate-cards" defined internally
api_router.include_router(milestones.router)        # prefix="/milestones" defined internally
api_router.include_router(resource_forecast.router) # prefix="/resource-forecast" defined internally
api_router.include_router(approvals.router)          # prefix="/approvals" defined internally
api_router.include_router(integrations_hub.router)   # prefix="/integrations-hub" defined internally
api_router.include_router(ws.router)                 # prefix="/ws" defined internally
api_router.include_router(accounting_hub.router)     # prefix="/accounting" defined internally
api_router.include_router(okrs.router)               # prefix="/okrs" defined internally
api_router.include_router(performance.router)        # prefix="/performance" defined internally
api_router.include_router(training.router)           # prefix="/training" defined internally
api_router.include_router(documents.router)          # prefix="/documents" defined internally
api_router.include_router(resources.router)          # prefix="/resources" defined internally
api_router.include_router(analytics_extended.router) # prefix="/analytics" defined internally
api_router.include_router(portfolio.router,          prefix="/portfolios",       tags=["Portfolio"])
api_router.include_router(git_integration.router,    prefix="/git",              tags=["Git Integration"])
api_router.include_router(esign.router,              prefix="/esign",            tags=["E-Firma"])
api_router.include_router(report_builder.router,     prefix="/reports",          tags=["Report Builder"])
api_router.include_router(nps.router,                prefix="/nps",              tags=["NPS & Health"])
api_router.include_router(m365.router,               prefix="/m365",             tags=["Microsoft 365"])
api_router.include_router(jira.router)               # prefix="/jira" defined internally
api_router.include_router(grc.router)                # prefix="/grc" defined internally
api_router.include_router(public_forms.router)       # prefix="/forms" defined internally
api_router.include_router(developer_portal.router)   # prefix="/developer" defined internally
api_router.include_router(scim.router)
api_router.include_router(governance.router)
api_router.include_router(abac.router)
api_router.include_router(security_observability.router)
api_router.include_router(ai_governance.router)
api_router.include_router(abac_admin.router)
api_router.include_router(currency_sync.router)
api_router.include_router(currency_rates.router)
api_router.include_router(salesforce_sync.router)
api_router.include_router(slack_block_kit.router)
api_router.include_router(v238_features.router,  tags=["Legacy Features v23.8"])  # compatibility router pending full domain split
api_router.include_router(v239_features.router,  tags=["Legacy Features v23.9"])  # compatibility router pending full domain split
