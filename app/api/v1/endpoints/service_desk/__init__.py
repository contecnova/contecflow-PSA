"""
Service Desk ITSM/ITIL API — modular aggregator.

Sub-domains:
  tickets   — ticket CRUD, comments, SLA events, watchers, merge/split, links
  kb        — knowledge base articles, KEDB
  cmdb      — configuration item inventory and relations
  sla       — SLA policies, escalation rules, holidays, priority matrix
  oncall    — on-call schedules and entries
  templates — ticket templates, canned responses, agent workspace, inbound email
  analytics — stats, ITIL metrics, agent performance
  misc      — catalog, groups, problems, announcements, routing, changes,
               major incidents, assets, status page
"""
from fastapi import APIRouter

from app.api.v1.endpoints.service_desk import (
    tickets, kb, cmdb, sla, oncall, templates, analytics, misc,
)

router = APIRouter()

router.include_router(tickets.router)
router.include_router(kb.router)
router.include_router(cmdb.router)
router.include_router(sla.router)
router.include_router(oncall.router)
router.include_router(templates.router)
router.include_router(analytics.router)
router.include_router(misc.router)
