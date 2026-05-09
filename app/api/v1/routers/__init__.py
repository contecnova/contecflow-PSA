"""
Domain sub-routers for API v1.

Each module aggregates a cohesive set of endpoint routers under a named domain.
The main router.py simply includes these five domain routers, keeping it thin
and making the domain contract explicit and easy to review.

Domains:
  core        — Auth, users, primary workflow modules
  delivery    — Project delivery tools, documents, resources, reporting
  ai_domain   — All AI/ML stack modules
  platform    — Enterprise integrations, security, compliance, admin tooling
  framework   — Infrastructure concerns: health, websocket, notifications, etc.
"""

from . import core, delivery, ai_domain, platform, framework
