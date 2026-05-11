"""Pydantic schemas para endpoints de auth/MFA que antes aceptaban `payload: dict`.

Diseño deliberado de retrocompatibilidad:

  1. Todos los campos son `Optional` con default `None`. El endpoint conserva
     su check `if not X: raise HTTPException(400, "...")` original — así un
     campo ausente sigue devolviendo 400 (no 422) y los mensajes de error
     son idénticos.

  2. `extra="ignore"` (default en pydantic v2). Cualquier campo extra que
     un cliente legacy enviara se descarta silenciosamente sin lanzar 422.

El valor añadido sobre el `dict` opaco anterior:
  - Tipado en cada handler (`payload.code` en vez de `payload.get("code")`).
  - OpenAPI/Swagger ahora documenta los campos esperados.
  - Una capa más de defensa frente a payloads malformados (tipos).
"""
from __future__ import annotations
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    """Base con extra='ignore' explícito (no dependemos del default)."""
    model_config = ConfigDict(extra="ignore")


# ── auth_core ─────────────────────────────────────────────────────────────────

class ChangePasswordIn(_Base):
    current_password: Optional[str] = None
    new_password: Optional[str] = None
    mfa_challenge_token: Optional[str] = None


# ── auth_mfa ──────────────────────────────────────────────────────────────────

class MfaCodeIn(_Base):
    """Genérico para endpoints que sólo requieren un código TOTP.

    `code` es Optional para preservar el contrato: cuando el cliente lo omite
    o lo envía vacío, el endpoint responde 400 con el mensaje original (no 422).
    """
    code: Optional[str] = Field(default=None, max_length=12)


class MfaValidateIn(_Base):
    code: Optional[str] = Field(default=None, max_length=12)
    mfa_challenge_token: Optional[str] = None


class WebAuthnRegisterFinishIn(_Base):
    webauthn_challenge_token: Optional[str] = None
    # `credential` es el payload PublicKeyCredential del browser; lo dejamos
    # como dict porque su estructura la valida `webauthn` más abajo.
    credential: Optional[Dict[str, Any]] = None
    name: Optional[str] = Field(default=None, max_length=120)


class WebAuthnAuthStartIn(_Base):
    mfa_challenge_token: Optional[str] = None


class WebAuthnAuthFinishIn(_Base):
    mfa_challenge_token: Optional[str] = None
    webauthn_challenge_token: Optional[str] = None
    credential: Optional[Dict[str, Any]] = None


# ── auth_sso ──────────────────────────────────────────────────────────────────

class SSOCallbackIn(_Base):
    code: Optional[str] = None
    state: Optional[str] = None
    redirect_uri: Optional[str] = None


# ── endpoints/mfa.py (orgs, slack, budgets, estimates, pdf) ───────────────────

class AssignUserOrgIn(_Base):
    user_id: Optional[str] = None


class SlackTestIn(_Base):
    config_id: Optional[str] = None
    channel: Optional[str] = None
    message: Optional[str] = None


class SlackNotifyIn(_Base):
    channel: Optional[str] = None
    message: Optional[str] = None
    event_type: Optional[str] = None
    source_id: Optional[str] = None


class AcceptFlagIn(_Base):
    """Toggle de aceptación usado en accept_estimate / accept_triage.

    Default `True` reproduce exactamente el `payload.get("accepted", True)`
    original.
    """
    accepted: bool = True


class ExportPdfIn(_Base):
    source_id: Optional[str] = None
    export_type: Optional[str] = None
    company_name: Optional[str] = Field(default=None, max_length=200)
    primary_color: Optional[str] = Field(default=None, max_length=20)
    logo_b64: Optional[str] = None
