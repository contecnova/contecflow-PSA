"""Shared AI dispatch functions to avoid endpoint-to-endpoint imports."""

from app.services.ai_provider_service import call_ai, get_default_provider

__all__ = ["call_ai", "get_default_provider"]
