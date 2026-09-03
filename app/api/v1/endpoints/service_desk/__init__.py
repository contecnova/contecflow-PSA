"""
Service Desk ITSM/ITIL API — modular aggregator.

Sub-domains:
  tickets     — ticket CRUD, comments, SLA events, watchers, merge/split, links
  kb          — knowledge base articles, KEDB
  cmdb        — configuration item inventory and relations
  sla         — SLA policies, escalation rules, holidays, priority matrix
  oncall      — on-call schedules and entries
  templates   — ticket templates, canned responses, agent workspace, inbound email
  analytics   — stats, ITIL metrics, agent performance
  misc        — catalog, groups, problems, announcements, routing, changes,
                 major incidents, assets, status page
  assets      — hardware lifecycle, license management, software audit
  smart_catalog — ML recommendations, dynamic forms, provisioning automation
  predictive  — severity prediction, resolution time, SLA breach probability
  autonomous  — bot-driven resolution, playbooks, execution audit
  multichannel — email/SMS inbound webhooks, multi-channel notifications
"""
from fastapi import APIRouter

from app.api.v1.endpoints.service_desk import (
    tickets,
    kb,
    cmdb,
    sla,
    oncall,
    templates,
    analytics,
    misc,
    workflow_designer,
    connectors_marketplace,
    governance_ops,
    ai_auto_resolution,
    assets,
    smart_catalog,
    predictive,
    autonomous,
    multichannel,
    change_impact,
    sd_reports,
    capacity_planning,
    problem_management,
    cab_workflow,
    alert_correlation,
    incident_assignment,
    change_rollout,
    cmdb_3d,
    voice_agent,
    dynamic_forms,
)

router = APIRouter()

router.include_router(tickets.router)
router.include_router(kb.router)
router.include_router(cmdb.router)
router.include_router(sla.router)
router.include_router(oncall.router)
router.include_router(templates.router)
router.include_router(analytics.router)
# Auditoria 2026-08: `change_rollout` va ANTES de `misc` a proposito.
# `misc` declara `/changes/{change_id}` y `change_rollout`
# `/changes/rollout-plans`; en FastAPI gana la primera que encaja, asi que con
# el orden anterior la peticion acababa en el detalle de un CR y respondia
# **404 «Change request no encontrado»** — endpoint inalcanzable y mensaje que
# manda a buscar un CR que falta. Es el unico caso de tapado ENTRE MODULOS, y
# por eso no se arregla reordenando dentro de un fichero sino aqui.
router.include_router(change_rollout.router)
router.include_router(misc.router)
router.include_router(workflow_designer.router)
router.include_router(connectors_marketplace.router)
router.include_router(governance_ops.router)
router.include_router(ai_auto_resolution.router)
router.include_router(assets.router)
router.include_router(smart_catalog.router)
router.include_router(predictive.router)
router.include_router(autonomous.router)
router.include_router(multichannel.router)
router.include_router(change_impact.router)
router.include_router(sd_reports.router)
router.include_router(capacity_planning.router)
router.include_router(problem_management.router)
router.include_router(cab_workflow.router)
router.include_router(alert_correlation.router)
router.include_router(incident_assignment.router)
router.include_router(cmdb_3d.router)
router.include_router(voice_agent.router)
router.include_router(dynamic_forms.router)
