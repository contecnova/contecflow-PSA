"""Shared AI dispatch functions to avoid endpoint-to-endpoint imports."""

from app.api.v1.endpoints.ai_providers import call_ai, get_default_provider

__all__ = ["call_ai", "get_default_provider"]
