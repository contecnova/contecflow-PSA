"""AI Client — low-level Claude API wrapper.

Extracted from app/api/v1/endpoints/ai_chat.py so it can be imported by
worker.py, ai_modules.py, and other modules without pulling in the full
FastAPI router and all its dependencies.
"""
from __future__ import annotations

import logging


_logger = logging.getLogger("ai_client")










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
