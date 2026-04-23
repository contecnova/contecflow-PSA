"""
Core domain — authentication, users, and primary workflow modules.

This covers the day-to-day operational surface used by every role:
auth, users, projects, tasks, time, capacity, contracts, risks, etc.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth, users, projects, tasks, imputations, dashboard,
    alerts, settings, timesheets, capacity, profitability, pipeline,
    contracts, risks, skills, absences, changes, deliverables,
    advanced_config, analytics, client_portal, service_desk, sprints,
    expenses, automations, enterprise,
)

router = APIRouter()

router.include_router(auth.router,            prefix="/auth",            tags=["Auth"])
router.include_router(users.router,           prefix="/users",           tags=["Usuarios"])
router.include_router(projects.router,        prefix="/projects",        tags=["Proyectos"])
router.include_router(tasks.router,           prefix="/tasks",           tags=["Tareas"])
router.include_router(imputations.router,     prefix="/imputations",     tags=["Imputaciones"])
router.include_router(dashboard.router,       prefix="/dashboard",       tags=["Dashboard"])
router.include_router(alerts.router,          prefix="/alerts",          tags=["Alertas"])
router.include_router(settings.router,        prefix="/settings",        tags=["Configuración"])
router.include_router(timesheets.router,      prefix="/timesheets",      tags=["Timesheets"])
router.include_router(capacity.router,        prefix="/capacity",        tags=["Capacidad"])
router.include_router(profitability.router,   prefix="/profitability",   tags=["Rentabilidad"])
router.include_router(pipeline.router,        prefix="/pipeline",        tags=["Pipeline"])
router.include_router(contracts.router,       prefix="/contracts",       tags=["Contratos"])
router.include_router(risks.router,           prefix="/risks",           tags=["Riesgos"])
router.include_router(skills.router,          prefix="/skills",          tags=["Skills"])
router.include_router(absences.router,        prefix="/absences",        tags=["Ausencias"])
router.include_router(changes.router,         prefix="/changes",         tags=["Control de Cambios"])
router.include_router(deliverables.router,    prefix="/deliverables",    tags=["Entregables"])
router.include_router(advanced_config.router, prefix="/advanced-config", tags=["Configuración Avanzada"])
router.include_router(analytics.router,       prefix="/analytics",       tags=["Analytics"])
router.include_router(client_portal.router,   prefix="/portal",          tags=["Portal Cliente"])
router.include_router(service_desk.router,    prefix="/sd",              tags=["Service Desk"])
router.include_router(sprints.router,         prefix="/sprints",         tags=["Sprints"])
router.include_router(expenses.router,        prefix="/expenses",        tags=["Gastos"])
router.include_router(automations.router,     prefix="/automation-workflows", tags=["Automatizaciones"])
# Compatibility alias: frontend calls /automations; tests use /automation-workflows.
router.include_router(automations.router,     prefix="/automations",          tags=["Automatizaciones"])
router.include_router(enterprise.router,      prefix="/enterprise",      tags=["Enterprise"])
