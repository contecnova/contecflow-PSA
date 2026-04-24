"""
AI Data Governance: PII detection/redaction + role/tenant guardrails with audit trail.

Architecture:
- PIIDetector: regex + pattern-based detection for 10+ PII entity types
- PIIRedactor: policy-driven redaction with configurable strategies (mask/hash/remove/tokenize)
- AIGuardrailPolicy: per-org, per-role, per-module policies stored in DB
- AIGuardrailEngine: evaluates prompts/outputs against active policies
- AIGuardrailAuditLog: immutable audit record of every guardrail evaluation
- Convenience functions: check_prompt(), check_output() used as middleware in ai_chat endpoints
"""
from __future__ import annotations

import re
import uuid
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.ai_governance import AIGuardrailPolicyModel
from app.models.ai_governance import AIGuardrailAuditLog
from fastapi import HTTPException

logger = logging.getLogger("contecflow.ai.governance")

# ── PII Entity Patterns ───────────────────────────────────────────────────────

_UTC = timezone.utc

# Each pattern: (label, compiled_regex)
_PII_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("email",           re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("phone_es",        re.compile(r"\b(?:\+34|0034)?[\s\-]?[6-9]\d{8}\b")),
    ("phone_intl",      re.compile(r"\+\d{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}")),
    ("dni_nie",         re.compile(r"\b[0-9]{8}[A-Za-z]\b|\b[XYZxyz][0-9]{7}[A-Za-z]\b")),
    ("nif_nif",         re.compile(r"\b[A-HJ-NP-SUVW]\d{7}[0-9A-J]\b")),
    ("credit_card",     re.compile(r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b")),
    ("iban",            re.compile(r"\b[A-Z]{2}\d{2}[\s]?(?:\d{4}[\s]?){4,7}\d{1,4}\b")),
    ("ip_address",      re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("ssn_us",          re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("passport",        re.compile(r"\b[A-Z]{2}[0-9]{7}\b")),
    ("date_of_birth",   re.compile(r"\b(?:born|dob|fecha\s+de\s+nacimiento)[:\s]+\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}\b", re.IGNORECASE)),
    ("full_name_hint",  re.compile(r"\b(?:nombre completo|full name|señor|señora|Mr\.|Mrs\.|Dr\.)\s+[A-ZÀ-Ú][a-zà-ú]+\s+[A-ZÀ-Ú][a-zà-ú]+\b", re.IGNORECASE)),
]

# Map entity label → mask token
_DEFAULT_MASKS = {
    "email":          "[EMAIL]",
    "phone_es":       "[PHONE]",
    "phone_intl":     "[PHONE]",
    "dni_nie":        "[ID_DOC]",
    "nif_nif":        "[TAX_ID]",
    "credit_card":    "[CARD]",
    "iban":           "[IBAN]",
    "ip_address":     "[IP]",
    "ssn_us":         "[SSN]",
    "passport":       "[PASSPORT]",
    "date_of_birth":  "[DOB]",
    "full_name_hint": "[NAME]",
}

# ── PII Detector ─────────────────────────────────────────────────────────────

@dataclass
class PIIMatch:
    entity_type: str
    value: str
    start: int
    end: int


def detect_pii(text: str) -> List[PIIMatch]:
    """Return all PII matches found in text, ordered by position."""
    matches: List[PIIMatch] = []
    for label, pattern in _PII_PATTERNS:
        for m in pattern.finditer(text):
            matches.append(PIIMatch(entity_type=label, value=m.group(), start=m.start(), end=m.end()))
    matches.sort(key=lambda x: x.start)
    return matches


def has_pii(text: str) -> bool:
    return bool(detect_pii(text))


# ── PII Redactor ──────────────────────────────────────────────────────────────

def _mask_value(value: str, entity_type: str, strategy: str) -> str:
    """Apply a redaction strategy to a single PII value."""
    if strategy == "remove":
        return ""
    if strategy == "hash":
        h = hashlib.sha256(value.encode()).hexdigest()[:8]
        return f"[{entity_type.upper()}#{h}]"
    if strategy == "partial":
        # Show first 2 + last 2 chars, mask the rest
        if len(value) <= 4:
            return "*" * len(value)
        return value[:2] + "*" * (len(value) - 4) + value[-2:]
    # Default: mask token
    return _DEFAULT_MASKS.get(entity_type, f"[{entity_type.upper()}]")


def redact_pii(
    text: str,
    entity_types: Optional[List[str]] = None,  # None = all
    strategy: str = "mask",                     # mask | hash | partial | remove
) -> Tuple[str, List[PIIMatch]]:
    """
    Redact PII from text.

    Returns (redacted_text, list_of_matches_found).
    Works right-to-left so offsets remain valid after each replacement.
    """
    matches = detect_pii(text)
    if entity_types:
        matches = [m for m in matches if m.entity_type in entity_types]

    # Process right-to-left to preserve offsets
    result = text
    for match in reversed(matches):
        replacement = _mask_value(match.value, match.entity_type, strategy)
        result = result[:match.start] + replacement + result[match.end:]

    return result, matches


# ── Guardrail Policy DB Model + Engine ───────────────────────────────────────
# (imported lazily to avoid circular imports — DB is optional)

@dataclass
class GuardrailPolicy:
    """
    In-memory representation of a guardrail policy rule.
    Loaded from DB via AIGuardrailPolicyModel.
    """
    id: str
    org_id: str
    name: str
    applies_to_modules: List[str]     # ["contecflowassist", "*"] — * = all
    applies_to_roles: List[str]       # ["employee", "*"]
    scope: str                        # "prompt" | "output" | "both"
    action: str                       # "block" | "redact" | "warn" | "log"
    pii_entity_types: List[str]       # ["email", "credit_card"] or [] = all
    redact_strategy: str              # mask | hash | partial | remove
    forbidden_keywords: List[str]     # lower-case exact or substring matches
    max_prompt_tokens: int            # 0 = unlimited
    is_active: bool = True
    priority: int = 0


@dataclass
class GuardrailResult:
    allowed: bool
    redacted_text: Optional[str]      # None if no redaction needed
    pii_found: List[PIIMatch] = field(default_factory=list)
    blocked_by: Optional[str] = None  # policy name that blocked
    warnings: List[str] = field(default_factory=list)
    action_taken: str = "none"        # none | redacted | blocked | warned


class AIGuardrailEngine:
    """
    Evaluate text against active guardrail policies for a given org/role/module.
    Uses DB-loaded policies; falls back to safe defaults.
    """

    def __init__(self, db: Session, org_id: str):
        self.db     = db
        self.org_id = org_id
        self._policies_cache: Optional[List[GuardrailPolicy]] = None

    def _load_policies(self) -> List[GuardrailPolicy]:
        if self._policies_cache is not None:
            return self._policies_cache
        try:
            from app.models.ai_governance import AIGuardrailPolicyModel
            rows = self.db.query(AIGuardrailPolicyModel).filter(
                AIGuardrailPolicyModel.org_id  == self.org_id,
                AIGuardrailPolicyModel.is_active == True,
            ).order_by(AIGuardrailPolicyModel.priority.desc()).all()

            self._policies_cache = [
                GuardrailPolicy(
                    id                  = r.id,
                    org_id              = r.org_id,
                    name                = r.name,
                    applies_to_modules  = r.applies_to_modules or ["*"],
                    applies_to_roles    = r.applies_to_roles or ["*"],
                    scope               = r.scope or "both",
                    action              = r.action or "redact",
                    pii_entity_types    = r.pii_entity_types or [],
                    redact_strategy     = r.redact_strategy or "mask",
                    forbidden_keywords  = [k.lower() for k in (r.forbidden_keywords or [])],
                    max_prompt_tokens   = r.max_prompt_tokens or 0,
                    is_active           = r.is_active,
                    priority            = r.priority or 0,
                )
                for r in rows
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load guardrail policies: %s", exc)
            self._policies_cache = []
        return self._policies_cache

    def _policies_for(self, role: str, module: str) -> List[GuardrailPolicy]:
        return [
            p for p in self._load_policies()
            if ("*" in p.applies_to_roles or role in p.applies_to_roles)
            and ("*" in p.applies_to_modules or module in p.applies_to_modules)
        ]

    def evaluate(
        self,
        text: str,
        role: str,
        module: str,
        scope: str,      # "prompt" | "output"
        user_id: str,
        request_id: Optional[str] = None,
    ) -> GuardrailResult:
        """
        Evaluate text against matching policies.
        Returns GuardrailResult and persists an audit record.
        """
        policies = [p for p in self._policies_for(role, module)
                    if p.scope in ("both", scope)]

        if not policies:
            # No policy → always allow but still detect PII for audit
            pii_found = detect_pii(text)
            result = GuardrailResult(
                allowed=True, redacted_text=None,
                pii_found=pii_found, action_taken="none",
            )
            self._audit(user_id, scope, module, text, result, None, request_id)
            return result

        working_text  = text
        pii_total: List[PIIMatch] = []
        warnings:  List[str]     = []

        for policy in sorted(policies, key=lambda p: -p.priority):
            # 1. Forbidden keywords
            lower = working_text.lower()
            for kw in policy.forbidden_keywords:
                if kw in lower:
                    if policy.action == "block":
                        result = GuardrailResult(
                            allowed=False, redacted_text=None,
                            blocked_by=policy.name,
                            action_taken="blocked",
                            warnings=[f"Forbidden keyword '{kw}' matched policy '{policy.name}'"],
                        )
                        self._audit(user_id, scope, module, text, result, policy.id, request_id)
                        return result
                    elif policy.action in ("warn", "log"):
                        warnings.append(f"Keyword '{kw}' flagged by policy '{policy.name}'")

            # 2. Token limit (rough estimate: 1 token ≈ 4 chars)
            if policy.max_prompt_tokens and scope == "prompt":
                estimated_tokens = len(working_text) // 4
                if estimated_tokens > policy.max_prompt_tokens:
                    if policy.action == "block":
                        result = GuardrailResult(
                            allowed=False, redacted_text=None,
                            blocked_by=policy.name,
                            action_taken="blocked",
                            warnings=[f"Prompt exceeds {policy.max_prompt_tokens} token limit"],
                        )
                        self._audit(user_id, scope, module, text, result, policy.id, request_id)
                        return result

            # 3. PII detection + redaction
            entity_filter = policy.pii_entity_types if policy.pii_entity_types else None
            pii_matches = detect_pii(working_text)
            if entity_filter:
                pii_matches = [m for m in pii_matches if m.entity_type in entity_filter]

            if pii_matches:
                pii_total.extend(pii_matches)
                if policy.action == "block":
                    result = GuardrailResult(
                        allowed=False, redacted_text=None,
                        pii_found=pii_matches,
                        blocked_by=policy.name,
                        action_taken="blocked",
                        warnings=[f"PII detected: {', '.join(set(m.entity_type for m in pii_matches))}"],
                    )
                    self._audit(user_id, scope, module, text, result, policy.id, request_id)
                    return result
                elif policy.action in ("redact", "warn"):
                    redacted, _ = redact_pii(
                        working_text,
                        entity_types=entity_filter,
                        strategy=policy.redact_strategy,
                    )
                    working_text = redacted
                    if policy.action == "warn":
                        warnings.append(f"PII redacted by policy '{policy.name}': "
                                        f"{', '.join(set(m.entity_type for m in pii_matches))}")

        result = GuardrailResult(
            allowed     = True,
            redacted_text = working_text if working_text != text else None,
            pii_found   = pii_total,
            warnings    = warnings,
            action_taken = "redacted" if working_text != text else ("warned" if warnings else "none"),
        )
        self._audit(user_id, scope, module, text, result, None, request_id)
        return result

    def _audit(
        self,
        user_id: str,
        scope: str,
        module: str,
        original_text: str,
        result: GuardrailResult,
        policy_id: Optional[str],
        request_id: Optional[str],
    ) -> None:
        try:
            from app.models.ai_governance import AIGuardrailAuditLog
            record = AIGuardrailAuditLog(
                id             = str(uuid.uuid4()),
                org_id         = self.org_id,
                user_id        = user_id,
                module         = module,
                scope          = scope,
                policy_id      = policy_id,
                request_id     = request_id,
                action_taken   = result.action_taken,
                pii_types_found = [m.entity_type for m in result.pii_found],
                was_blocked    = not result.allowed,
                blocked_reason = result.blocked_by,
                original_length= len(original_text),
                warnings       = result.warnings,
                evaluated_at   = datetime.now(_UTC),
            )
            self.db.add(record)
            self.db.flush()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Guardrail audit write failed: %s", exc)


# ── Policy & Audit CRUD service functions ────────────────────────────────────

def create_policy(
    db: Session,
    org_id: str,
    created_by: str,
    name: str,
    description: Optional[str],
    applies_to_modules: List[str],
    applies_to_roles: List[str],
    scope: str,
    action: str,
    pii_entity_types: List[str],
    redact_strategy: str,
    forbidden_keywords: List[str],
    max_prompt_tokens: int,
    priority: int,
    is_active: bool,
):
    policy = AIGuardrailPolicyModel(
        id                  = str(uuid.uuid4()),
        org_id              = org_id,
        name                = name,
        description         = description,
        applies_to_modules  = applies_to_modules,
        applies_to_roles    = applies_to_roles,
        scope               = scope,
        action              = action,
        pii_entity_types    = pii_entity_types,
        redact_strategy     = redact_strategy,
        forbidden_keywords  = forbidden_keywords,
        max_prompt_tokens   = max_prompt_tokens,
        priority            = priority,
        is_active           = is_active,
        created_by          = created_by,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


def list_policies(db: Session, org_id: str, active_only: bool = False):
    q = db.query(AIGuardrailPolicyModel).filter(
        AIGuardrailPolicyModel.org_id == org_id
    )
    if active_only:
        q = q.filter(AIGuardrailPolicyModel.is_active == True)  # noqa
    return q.order_by(AIGuardrailPolicyModel.priority.desc(),
                      AIGuardrailPolicyModel.created_at.desc()).all()


def get_policy(db: Session, policy_id: str, org_id: str):
    return db.query(AIGuardrailPolicyModel).filter(
        AIGuardrailPolicyModel.id     == policy_id,
        AIGuardrailPolicyModel.org_id == org_id,
    ).first()


def update_policy(db: Session, policy, updates: Dict[str, Any]):
    for key, val in updates.items():
        setattr(policy, key, val)
    db.commit()
    db.refresh(policy)
    return policy


def deactivate_policy(db: Session, policy) -> None:
    policy.is_active = False
    db.commit()


def get_audit_log(
    db: Session,
    org_id: str,
    since: datetime,
    module: Optional[str] = None,
    scope: Optional[str] = None,
    action_taken: Optional[str] = None,
    was_blocked: Optional[bool] = None,
    user_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[int, list]:
    q = db.query(AIGuardrailAuditLog).filter(
        AIGuardrailAuditLog.org_id       == org_id,
        AIGuardrailAuditLog.evaluated_at >= since,
    )
    if module:       q = q.filter(AIGuardrailAuditLog.module       == module)
    if scope:        q = q.filter(AIGuardrailAuditLog.scope        == scope)
    if action_taken: q = q.filter(AIGuardrailAuditLog.action_taken == action_taken)
    if was_blocked is not None:
        q = q.filter(AIGuardrailAuditLog.was_blocked == was_blocked)
    if user_id:      q = q.filter(AIGuardrailAuditLog.user_id      == user_id)
    total = q.count()
    items = q.order_by(AIGuardrailAuditLog.evaluated_at.desc()) \
             .offset((page - 1) * page_size).limit(page_size).all()
    return total, items


def get_audit_stats(
    db: Session,
    org_id: str,
    since: datetime,
) -> Dict[str, Any]:
    base = db.query(AIGuardrailAuditLog).filter(
        AIGuardrailAuditLog.org_id       == org_id,
        AIGuardrailAuditLog.evaluated_at >= since,
    )
    total          = base.count()
    total_blocked  = base.filter(AIGuardrailAuditLog.was_blocked == True).count()  # noqa
    total_redacted = base.filter(AIGuardrailAuditLog.action_taken == "redacted").count()
    total_warned   = base.filter(AIGuardrailAuditLog.action_taken == "warned").count()

    rows = db.query(
        AIGuardrailAuditLog.module, func.count(AIGuardrailAuditLog.id)
    ).filter(
        AIGuardrailAuditLog.org_id == org_id,
        AIGuardrailAuditLog.evaluated_at >= since,
    ).group_by(AIGuardrailAuditLog.module).all()
    by_module = {module: cnt for module, cnt in rows}

    pii_counter: Dict[str, int] = {}
    all_pii = db.query(AIGuardrailAuditLog.pii_types_found).filter(
        AIGuardrailAuditLog.org_id       == org_id,
        AIGuardrailAuditLog.evaluated_at >= since,
        AIGuardrailAuditLog.pii_types_found.isnot(None),
    ).all()
    for (types_list,) in all_pii:
        if isinstance(types_list, list):
            for t in types_list:
                pii_counter[t] = pii_counter.get(t, 0) + 1

    top_pii = sorted(pii_counter.items(), key=lambda x: -x[1])[:10]
    return {
        "total":          total,
        "total_blocked":  total_blocked,
        "total_redacted": total_redacted,
        "total_warned":   total_warned,
        "by_module":      by_module,
        "top_pii":        top_pii,
    }


# ── Convenience wrappers used from ai_chat endpoints ─────────────────────────

def check_prompt(
    text: str,
    user,
    module: str,
    db: Session,
    request_id: Optional[str] = None,
) -> GuardrailResult:
    """Evaluate a user prompt before sending to AI provider."""
    if not user or not getattr(user, "organization_id", None):
        return GuardrailResult(allowed=True, redacted_text=None, action_taken="none")
    engine = AIGuardrailEngine(db=db, org_id=str(user.organization_id))
    role   = user.role.value if hasattr(user.role, "value") else str(user.role or "employee")
    return engine.evaluate(text, role=role, module=module, scope="prompt",
                           user_id=str(user.id), request_id=request_id)


def check_output(
    text: str,
    user,
    module: str,
    db: Session,
    request_id: Optional[str] = None,
) -> GuardrailResult:
    """Evaluate AI output before returning to user."""
    if not user or not getattr(user, "organization_id", None):
        return GuardrailResult(allowed=True, redacted_text=None, action_taken="none")
    engine = AIGuardrailEngine(db=db, org_id=str(user.organization_id))
    role   = user.role.value if hasattr(user.role, "value") else str(user.role or "employee")
    return engine.evaluate(text, role=role, module=module, scope="output",
                           user_id=str(user.id), request_id=request_id)


# ── Tenant helpers ─────────────────────────────────────────────────────────

def get_org_id(user) -> str:
    if not user.organization_id:
        raise HTTPException(400, "User has no organization")
    return str(user.organization_id)
