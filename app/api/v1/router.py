"""
API v1 top-level router.

All endpoint modules are aggregated through five domain sub-routers defined
in app/api/v1/routers/.  Adding a new module means editing the appropriate
domain file rather than this orchestrator.

  core       — Auth, users, primary workflow modules
  delivery   — Project delivery tools, resources, documents, reporting
  ai_domain  — All AI/ML stack modules
  platform   — Integrations, security, compliance, admin tooling
  framework  — Health checks, websockets, notifications
"""
from fastapi import APIRouter

from app.api.v1.routers import core, delivery, ai_domain, platform, framework

api_router = APIRouter()

# Aliases legacy /projects/* y /sprint-plans/* retirados en 2026-05-13 (audit #107).
# Las rutas canónicas son: /tasks, /milestones, /sprints, /epics, /issue-types
# y /cmdb/sprint-plans/*. Los callers ya migraron; ver tests/test_api_versioning.py
# para la verificación de retirada.

api_router.include_router(core.router)
api_router.include_router(delivery.router)
api_router.include_router(ai_domain.router)
api_router.include_router(platform.router)
api_router.include_router(framework.router)

