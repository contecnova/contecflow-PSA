"""AI Client — low-level Claude API wrapper.

Extracted from app/api/v1/endpoints/ai_chat.py so it can be imported by
worker.py, ai_modules.py, and other modules without pulling in the full
FastAPI router and all its dependencies.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from app.core.config import settings

_logger = logging.getLogger("ai_client")


def get_api_key() -> Optional[str]:
    """Return the Anthropic API key from centralized settings.

    Settings.ANTHROPIC_API_KEY is the single source of truth; a DB-managed
    provider key can override it by passing *api_key* to :func:`call_claude`.
    """
    key = settings.ANTHROPIC_API_KEY
    if not key:
        _logger.warning("ANTHROPIC_API_KEY not configured — AI features unavailable")
    return key or None


def call_claude(
    messages: list,
    system: Optional[str] = None,
    model: Optional[str] = None,
    tools: Optional[list] = None,
    max_tokens: int = 1000,
    api_key: Optional[str] = None,
) -> dict:
    """Synchronous Claude API call.  Returns the full Anthropic response dict.

    Args:
        messages:   List of ``{"role": ..., "content": ...}`` dicts.
        system:     Optional system prompt.
        model:      Model name; defaults to ``settings.NEXUS_AI_MODEL``.
        tools:      Optional tool definitions for function-calling.
        max_tokens: Maximum tokens to generate.
        api_key:    Override the default API key (e.g. from DB-managed provider).

    Returns:
        Parsed JSON response from the Anthropic Messages API.

    Raises:
        urllib.error.HTTPError: On non-2xx HTTP responses from Anthropic.
        urllib.error.URLError:  On network-level failures.
    """
    import urllib.request
    import urllib.error

    key = api_key or get_api_key()
    if not key:
        raise ValueError("No Anthropic API key available — set ANTHROPIC_API_KEY")

    headers = {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }
    body: dict = {
        "model": model or settings.NEXUS_AI_MODEL,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools

    data = json.dumps(body).encode()
    req = urllib.request.Request(settings.ANTHROPIC_API_URL, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def extract_text(response: dict) -> str:
    """Extract all text content blocks from a Claude API response."""
    texts = [
        b["text"]
        for b in response.get("content", [])
        if b.get("type") == "text"
    ]
    return "\n".join(texts)


# Prompt-injection detection patterns
_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all instructions",
    "disregard your instructions",
    "forget your instructions",
    "you are now",
    "act as if",
    "pretend you are",
    "jailbreak",
    "bypass your",
    "override your",
    "system prompt",
    "new instructions:",
    "ignore everything above",
    "ignore everything below",
    "print your system",
    "reveal your prompt",
    "what are your instructions",
]


def check_prompt_injection(message: str) -> bool:
    """Return *True* if *message* appears to be a prompt-injection attempt."""
    lower = message.lower()
    return any(p in lower for p in _INJECTION_PATTERNS)
