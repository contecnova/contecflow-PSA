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
    advanced_config, analytics, client_portal, portal_conversations, service_desk, sprints,
    expenses, automations, enterprise, bpmn_processes, user_costs, mcp,
)
from app.api.v1.endpoints import ausencias
from app.api.v1.endpoints import horas_extra
from app.api.v1.endpoints import proveedores  # rev. 190: proveedores y externalizacion
from app.api.v1.endpoints import proveedores_portal  # rev. 191: portal del proveedor
from app.api.v1.endpoints import clientes_internos  # rev. 193: clientes internos
from app.api.v1.endpoints import demanda, portal_demanda  # rev. 195: flujo de demanda
from app.api.v1.endpoints import portal_interno  # rev. 193: portal interno
from app.api.v1.endpoints import collaboration as collaboration_pkg
from app.api.v1.endpoints import collaboration_portal
from app.api.v1.endpoints import periodo as periodo_ep

router = APIRouter()

router.include_router(auth.router,            prefix="/auth",            tags=["Auth"])
router.include_router(users.router,           prefix="/users",           tags=["Usuarios"])
router.include_router(projects.router,        prefix="/projects",        tags=["Proyectos"])
router.include_router(tasks.router,           prefix="/tasks",           tags=["Tareas"])
router.include_router(imputations.router,     prefix="/imputations",     tags=["Imputaciones"])
router.include_router(dashboard.router,       prefix="/dashboard",       tags=["Dashboard"])
router.include_router(alerts.router,          prefix="/alerts",          tags=["Alertas"])
router.include_router(settings.router,        prefix="/settings",        tags=["Configuración"])
router.include_router(mcp.router,             tags=["MCP"])
router.include_router(periodo_ep.router,     prefix="/periodo",         tags=["Periodo de informes"])
router.include_router(timesheets.router,      prefix="/timesheets",      tags=["Timesheets"])
router.include_router(capacity.router,        prefix="/capacity",        tags=["Capacidad"])
router.include_router(profitability.router,   prefix="/profitability",   tags=["Rentabilidad"])
router.include_router(pipeline.router,        prefix="/pipeline",        tags=["Pipeline"])
router.include_router(contracts.router,       prefix="/contracts",       tags=["Contratos"])
router.include_router(risks.router,           prefix="/risks",           tags=["Riesgos"])
router.include_router(skills.router,          prefix="/skills",          tags=["Skills"])
router.include_router(ausencias.router,       prefix="/absences",        tags=["Ausencias"])  # tarea #25 (tipos, turnos, cupos, documentos)
router.include_router(absences.router,        prefix="/absences",        tags=["Ausencias"])
router.include_router(horas_extra.router,     prefix="/overtime",        tags=["Horas extra"])  # rev. 184 (18-11-2026)
router.include_router(changes.router,         prefix="/changes",         tags=["Control de Cambios"])
router.include_router(deliverables.router,    prefix="/deliverables",    tags=["Entregables"])
router.include_router(advanced_config.router, prefix="/advanced-config", tags=["Configuración Avanzada"])
router.include_router(analytics.router,       prefix="/analytics",       tags=["Analytics"])
router.include_router(portal_demanda.router,  prefix="/portal/demand",   tags=["Portal Cliente — demanda"])  # rev. 195
router.include_router(client_portal.router,   prefix="/portal",          tags=["Portal Cliente"])
# 23-11-2026: «¿Olvidaste tu contraseña?» y restablecimiento forzado del portal.
from app.api.v1.endpoints import client_portal_password  # noqa: E402
router.include_router(client_portal_password.router, prefix="/portal",      tags=["Portal Cliente"])
router.include_router(demanda.router,         prefix="/demand",          tags=["Flujo de demanda"])  # rev. 195
# Conversaciones gobernadas. El router ya lleva prefix="/conversations": montado
# en /portal queda /portal/conversations/... (lo que usa la pantalla).
# Auditoria 2026-11: habia un segundo montaje en /portal/conversations que
# producia /portal/conversations/conversations/... y era el unico documentado.
router.include_router(portal_conversations.router, prefix="/portal",                tags=["Portal Conversations"])
router.include_router(service_desk.router,    prefix="/sd",              tags=["Service Desk"])
router.include_router(sprints.router,         prefix="/sprints",         tags=["Sprints"])
router.include_router(expenses.router,        prefix="/expenses",        tags=["Gastos"])
router.include_router(automations.router,     prefix="/automation-workflows", tags=["Automatizaciones"])
# Compatibility alias: frontend calls /automations; tests use /automation-workflows.
router.include_router(automations.router,     prefix="/automations",          tags=["Automatizaciones"])
router.include_router(enterprise.router,      prefix="/enterprise",      tags=["Enterprise"])
router.include_router(bpmn_processes.router,  prefix="/bpmn-processes",  tags=["BPMN Processes"])
# Auditoria 2026-11: motor de procesos (instancias y bandeja).
from app.api.v1.endpoints import bpmn_instances  # noqa: E402
router.include_router(bpmn_instances.procesos, prefix="/bpmn-processes", tags=["BPMN Processes"])
router.include_router(bpmn_instances.router,   prefix="/bpmn-instances", tags=["BPMN Instances"])
router.include_router(user_costs.router,      prefix="/user-costs",      tags=["User Costs"])
router.include_router(proveedores.router,     prefix="/suppliers",       tags=["Proveedores"])
router.include_router(proveedores_portal.router, prefix="/supplier-portal", tags=["Portal del proveedor"])
router.include_router(clientes_internos.router, prefix="/internal-clients", tags=["Clientes internos"])
router.include_router(portal_interno.router, prefix="/internal-portal", tags=["Portal interno"])
router.include_router(collaboration_pkg.router, prefix="/collaboration",  tags=["Collaboration"])
router.include_router(collaboration_portal.router, prefix="/portal/collaboration", tags=["Portal Collaboration"])
# CMDB de software, composición y vulnerabilidades (rev. 190, 19-11-2026). Bajo
# /cmdb: módulo GRC `cmdb` y prefijo ABAC `/api/v1/cmdb` (abac_registry).
from app.api.v1.endpoints import cmdb_software  # noqa: E402
router.include_router(cmdb_software.router, prefix="/cmdb/software", tags=["CMDB de software y vulnerabilidades"])
# Índice de riesgo y gestión de vulnerabilidades (rev. 194, 22-11-2026).
from app.api.v1.endpoints import cmdb_riesgo  # noqa: E402
router.include_router(cmdb_riesgo.router, prefix="/cmdb/software/risk", tags=["Índice de riesgo y vulnerabilidades"])
# «Mi cuaderno»: notas personales tipo OneNote (rev. 202, 23-11-2026, docs/CUADERNO.md).
from app.api.v1.endpoints import cuaderno  # noqa: E402
router.include_router(cuaderno.router, prefix="/notebook", tags=["Mi cuaderno"])
# «Del ticket al PR»: agente de código que propone un PR (rev. 203, 23-11-2026,
# docs/integraciones/TICKET_A_PR.md). Módulo opcional por empresa, apagado por defecto.
from app.api.v1.endpoints import ticket_a_pr  # noqa: E402
router.include_router(ticket_a_pr.router, prefix="/ticket-pr", tags=["Del ticket al PR"])
