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
    ("phone_es",        re.compile(r"(?<!\d)(?:\+34|0034)?[\s\-]?[6-9]\d{8}(?!\d)")),
    # phone_intl: requiere prefijo `+`, total dígitos 8–15 (E.164), y boundaries
    # estrictos (no dígitos pegados). Antes \d{1,3} se pegaba a totales hasta 18
    # haciendo coincidir códigos de versión, IDs y números de pedido.
    ("phone_intl",      re.compile(r"(?<!\d)\+\d{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}(?!\d)")),
    ("dni_nie",         re.compile(r"\b[0-9]{8}[A-Za-z]\b|\b[XYZxyz][0-9]{7}[A-Za-z]\b")),
    ("nif_nif",         re.compile(r"\b[A-HJ-NP-SUVW]\d{7}[0-9A-J]\b")),
    ("credit_card",     re.compile(r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b")),
    ("iban",            re.compile(r"\b[A-Z]{2}\d{2}[\s]?(?:\d{4}[\s]?){4,7}\d{1,4}\b")),
    ("ip_address",      re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("ssn_us",          re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("passport",        re.compile(r"\b[A-Z]{2}[0-9]{7}\b")),
    # date_of_birth: aceptamos prefijo OR formato dd/mm/aaaa "puro" cuando el
    # año caiga en el rango plausible 1900-2099 para minimizar falsos positivos.
    ("date_of_birth",   re.compile(
        r"\b(?:born|dob|fecha\s+de\s+nacimiento|nacid[oa]\s+el|birth\s*date)[:\s]+"
        r"\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}\b"
        r"|(?<!\d)(?:0?[1-9]|[12]\d|3[01])[\/\-\.](?:0?[1-9]|1[0-2])[\/\-\.](?:19|20)\d{2}(?!\d)",
        re.IGNORECASE,
    )),
    # full_name_hint: prefijo de cortesía + 2-4 tokens (case-insensitive en
    # el prefijo, sensible en el nombre).
    ("full_name_hint",  re.compile(
        r"\b(?:nombre completo|full name|señor|señora|Sr\.|Sra\.|Mr\.|Mrs\.|Ms\.|Dr\.|Dra\.|Prof\.)\s+"
        r"[A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+){1,3}\b",
        re.IGNORECASE,
    )),
    # full_name_triple_cap: nombre + 2 apellidos (patrón ES). DEBE ser
    # case-sensitive — IGNORECASE convertiría "El proyecto avanza" en falso
    # positivo. Mínimo 3 tokens, cada uno empezando estrictamente con mayúscula
    # y resto en minúscula. Sin re.IGNORECASE deliberadamente.
    ("full_name_hint",  re.compile(
        r"\b[A-ZÀ-Ú][a-zà-ú]+\s+[A-ZÀ-Ú][a-zà-ú]+\s+[A-ZÀ-Ú][a-zà-ú]+\b"
    )),
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

# ── Token estimator (item #63) ────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    """Estimación conservadora del número de tokens en ``text``.

    Preferencia 1: ``tiktoken`` (cl100k_base) — exacto para modelos OpenAI/Claude.
    Preferencia 2: fórmula conservadora ``max(len//4, words × 1.3)``.

    El fallback ``len // 4`` infraestima con texto español/emojis. Usamos el
    máximo entre 1.3× palabras y len//4 para evitar dejar pasar prompts que
    exceden el límite real.
    """
    if not text:
        return 0
    try:
        import tiktoken  # type: ignore
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        words = text.split()
        return max(len(text) // 4, int(len(words) * 1.3))


# ── PII Detector ─────────────────────────────────────────────────────────────

@dataclass
class PIIMatch:
    entity_type: str
    value: str
    start: int
    end: int


_DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"


def _dni_checksum_valid(value: str) -> bool:
    """Valida que la letra de control de un DNI/NIE coincida con el resto.

    DNI: ``NNNNNNNN-L``  → letra = ``_DNI_LETTERS[num % 23]``
    NIE: ``[XYZ]NNNNNNN-L`` → letra calculada sustituyendo X=0, Y=1, Z=2

    Item #65: antes el regex matcheaba cualquier 8 dígitos + letra. ~96% de
    los falsos positivos vienen de IDs internos con la misma forma.
    """
    v = value.strip().upper()
    if len(v) == 9 and v[:8].isdigit():
        num = int(v[:8])
        return _DNI_LETTERS[num % 23] == v[8]
    if len(v) == 9 and v[0] in "XYZ" and v[1:8].isdigit():
        num = int({"X": "0", "Y": "1", "Z": "2"}[v[0]] + v[1:8])
        return _DNI_LETTERS[num % 23] == v[8]
    return False


def detect_pii(text: str) -> List[PIIMatch]:
    """Return all PII matches found in text, ordered by position."""
    matches: List[PIIMatch] = []
    for label, pattern in _PII_PATTERNS:
        for m in pattern.finditer(text):
            value = m.group()
            # Item #65: para DNI/NIE validamos la letra de control.
            # Esto elimina ~96% de falsos positivos (IDs internos con la
            # misma forma 8 dígitos + letra).
            if label == "dni_nie" and not _dni_checksum_valid(value):
                continue
            matches.append(PIIMatch(entity_type=label, value=value, start=m.start(), end=m.end()))
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
# NOTE (audit #110): an older comment claimed model imports were lazy to
# avoid circular imports. Verified: app.models.ai_governance only depends on
# app.db.base; nothing in app.models imports this service. The model classes
# (AIGuardrailPolicyModel, AIGuardrailAuditLog) are imported eagerly at the
# top of this module and the redundant lazy re-imports inside _load_policies()
# and _audit() have been removed.

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

    # Item #64: TTL del caché de policies. Antes ``_policies_cache`` se llenaba
    # una vez por instancia y no expiraba — si una instancia AIGuardrailEngine
    # vivía más allá del request (en worker), un PATCH a policies no se
    # reflejaba hasta reiniciar. TTL de 60s acota el drift sin matar el caché.
    _POLICY_CACHE_TTL_SECONDS = 60

    def __init__(self, db: Session, org_id: str):
        self.db     = db
        self.org_id = org_id
        self._policies_cache: Optional[List[GuardrailPolicy]] = None
        self._policies_cache_at: Optional[float] = None

    def invalidate_policies(self) -> None:
        """Fuerza recarga de policies en la próxima llamada."""
        self._policies_cache = None
        self._policies_cache_at = None

    def _load_policies(self) -> List[GuardrailPolicy]:
        import time as _time
        if (
            self._policies_cache is not None
            and self._policies_cache_at is not None
            and (_time.monotonic() - self._policies_cache_at) < self._POLICY_CACHE_TTL_SECONDS
        ):
            return self._policies_cache
        try:
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
        except Exception as exc:
            logger.warning("Could not load guardrail policies: %s", exc)
            self._policies_cache = []
        import time as _time
        self._policies_cache_at = _time.monotonic()
        return self._policies_cache

    def _policies_for(self, role: str, module: str) -> List[GuardrailPolicy]:
        """Filtra policies que aplican a ``(role, module)``.

        **Wildcard ``"*"``** (item #75): si una policy declara ``"*"`` en
        ``applies_to_roles`` o ``applies_to_modules``, aplica a TODOS los
        roles/módulos respectivamente. Es la convención para crear policies
        globales (ej. \"ningún PII en ningún prompt, sea quien sea\").

        Coincidencias exactas también funcionan: ``["admin", "pm"]`` aplica
        solo a esos roles. No hay coincidencia parcial / glob.
        """
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
            motivo, avisos = _revisar_palabras_prohibidas(policy, working_text)
            warnings.extend(avisos)
            if motivo is None:
                motivo = _revisar_limite_de_tokens(policy, working_text, scope)

            hallazgos_pii = []
            if motivo is None:
                working_text, hallazgos_pii, motivo, avisos = _revisar_pii(
                    policy, working_text)
                warnings.extend(avisos)
                pii_total.extend(hallazgos_pii)

            if motivo is not None:
                result = GuardrailResult(
                    allowed=False, redacted_text=None,
                    pii_found=hallazgos_pii or None,
                    blocked_by=policy.name,
                    action_taken="blocked",
                    warnings=[motivo],
                )
                self._audit(user_id, scope, module, text, result, policy.id, request_id)
                return result

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
        except Exception as exc:
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
        q = q.filter(AIGuardrailPolicyModel.is_active == True)
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
    total_blocked  = base.filter(AIGuardrailAuditLog.was_blocked == True).count()
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


# -- Los tres guardarrailes, uno por concepto ---------------------------------
#
# Auditoria 2026-09. `GuardrailEngine.evaluate` los llevaba dentro del bucle y
# llegaba a complejidad 15 — pero lo que de verdad pesaba no eran las ramas, era
# que el bloque «construir el resultado bloqueado, auditar y devolver» estaba
# **escrito tres veces**, una por guardarrail, con el mismo cuerpo y distinto
# mensaje. Tres copias del camino de denegacion en una funcion de seguridad es
# justo donde no se quieren tres copias.
#
# Cada revisor devuelve el **motivo** del bloqueo o `None`, y quien llama
# construye el resultado una sola vez. El orden de evaluacion se conserva
# exactamente: palabras prohibidas, limite de tokens, PII.


def _revisar_palabras_prohibidas(policy, texto):
    """Palabras vetadas. Devuelve (motivo de bloqueo o None, avisos)."""
    avisos = []
    minusculas = texto.lower()
    for palabra in policy.forbidden_keywords:
        if palabra not in minusculas:
            continue
        if policy.action == "block":
            return (
                "Forbidden keyword '%s' matched policy '%s'" % (palabra, policy.name),
                avisos,
            )
        if policy.action in ("warn", "log"):
            avisos.append(
                "Keyword '%s' flagged by policy '%s'" % (palabra, policy.name))
    return None, avisos


def _revisar_limite_de_tokens(policy, texto, scope):
    """Tope de tokens del prompt, o `None` si no aplica.

    Se conserva la cuenta de #63: `len // 4` infraestimaba con caracteres no
    ASCII —en espanol y con emojis un caracter son dos o tres bytes—, asi que si
    `tiktoken` esta disponible se usa la cuenta real y si no, la aproximacion
    `max(len//4, palabras x 1.3)`, que es la conservadora.

    Solo bloquea, nunca avisa, y eso es deliberado: un prompt que pasa del tope
    no se puede «avisar» y enviar igual, porque el modelo lo rechaza de todas
    formas. Un aviso aqui seria una promesa que no se puede cumplir.
    """
    if not (policy.max_prompt_tokens and scope == "prompt"):
        return None
    if _estimate_tokens(texto) <= policy.max_prompt_tokens:
        return None
    if policy.action == "block":
        return "Prompt exceeds %s token limit" % policy.max_prompt_tokens
    return None


def _revisar_pii(policy, texto):
    """Datos personales: detectar, y bloquear o tachar.

    Devuelve `(texto resultante, hallazgos, motivo de bloqueo, avisos)`. El
    texto vuelve tachado cuando la politica es `redact` o `warn`, y es lo que
    sigue evaluando la siguiente politica — **el orden importa**: una politica
    de menor prioridad ve el texto ya tachado por la anterior, que es el
    comportamiento que habia y el que tiene sentido.
    """
    filtro = policy.pii_entity_types if policy.pii_entity_types else None
    hallazgos = detect_pii(texto)
    if filtro:
        hallazgos = [m for m in hallazgos if m.entity_type in filtro]
    if not hallazgos:
        return texto, [], None, []

    tipos = ", ".join(sorted({m.entity_type for m in hallazgos}))
    if policy.action == "block":
        return texto, hallazgos, "PII detected: %s" % tipos, []

    if policy.action in ("redact", "warn"):
        tachado, _ = redact_pii(
            texto, entity_types=filtro, strategy=policy.redact_strategy)
        avisos = (["PII redacted by policy '%s': %s" % (policy.name, tipos)]
                  if policy.action == "warn" else [])
        return tachado, hallazgos, None, avisos

    return texto, hallazgos, None, []
