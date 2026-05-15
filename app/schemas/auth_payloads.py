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
    current_password: Optional[str] = Field(None, description="Contraseña actual del usuario")
    new_password: Optional[str] = Field(None, description="Nueva contraseña a establecer")
    mfa_challenge_token: Optional[str] = Field(None, description="Token de reto MFA si el flujo lo requiere")


# ── auth_mfa ──────────────────────────────────────────────────────────────────

class MfaCodeIn(_Base):
    """Genérico para endpoints que sólo requieren un código TOTP.

    `code` es Optional para preservar el contrato: cuando el cliente lo omite
    o lo envía vacío, el endpoint responde 400 con el mensaje original (no 422).
    """
    code: Optional[str] = Field(default=None, max_length=12, description="Código TOTP de un solo uso")


class MfaValidateIn(_Base):
    code: Optional[str] = Field(default=None, max_length=12, description="Código TOTP a validar")
    mfa_challenge_token: Optional[str] = Field(None, description="Token de reto MFA emitido en el login")


class WebAuthnRegisterFinishIn(_Base):
    webauthn_challenge_token: Optional[str] = Field(None, description="Token de reto WebAuthn emitido al iniciar el registro")
    # `credential` es el payload PublicKeyCredential del browser; lo dejamos
    # como dict porque su estructura la valida `webauthn` más abajo.
    credential: Optional[Dict[str, Any]] = Field(None, description="PublicKeyCredential serializado por el navegador")
    name: Optional[str] = Field(default=None, max_length=120, description="Nombre amigable para la credencial")


class WebAuthnAuthStartIn(_Base):
    mfa_challenge_token: Optional[str] = Field(None, description="Token de reto MFA emitido en el login")


class WebAuthnAuthFinishIn(_Base):
    mfa_challenge_token: Optional[str] = Field(None, description="Token de reto MFA emitido en el login")
    webauthn_challenge_token: Optional[str] = Field(None, description="Token de reto WebAuthn emitido al iniciar la autenticación")
    credential: Optional[Dict[str, Any]] = Field(None, description="PublicKeyCredential de respuesta del autenticador")


# ── auth_sso ──────────────────────────────────────────────────────────────────

class SSOCallbackIn(_Base):
    code: Optional[str] = Field(None, description="Authorization code devuelto por el IdP")
    state: Optional[str] = Field(None, description="Parámetro state para prevenir CSRF")
    redirect_uri: Optional[str] = Field(None, description="URI de redirección registrada en el IdP")


# ── endpoints/mfa.py (orgs, slack, budgets, estimates, pdf) ───────────────────

class AssignUserOrgIn(_Base):
    user_id: Optional[str] = Field(None, description="ID del usuario a asignar a la organización")


class SlackTestIn(_Base):
    config_id: Optional[str] = Field(None, description="ID de la configuración de Slack a probar")
    channel: Optional[str] = Field(None, description="Canal de Slack destino para el test")
    message: Optional[str] = Field(None, description="Mensaje de prueba a enviar")


class SlackNotifyIn(_Base):
    channel: Optional[str] = Field(None, description="Canal de Slack destino")
    message: Optional[str] = Field(None, description="Mensaje a notificar")
    event_type: Optional[str] = Field(None, description="Tipo de evento que origina la notificación")
    source_id: Optional[str] = Field(None, description="ID de la entidad origen del evento")


class AcceptFlagIn(_Base):
    """Toggle de aceptación usado en accept_estimate / accept_triage.

    Default `True` reproduce exactamente el `payload.get("accepted", True)`
    original.
    """
    accepted: bool = Field(True, description="Indica si se acepta o rechaza la propuesta")


class ExportPdfIn(_Base):
    source_id: Optional[str] = Field(None, description="ID del recurso a exportar a PDF")
    export_type: Optional[str] = Field(None, description="Tipo de exportación PDF solicitada")
    company_name: Optional[str] = Field(default=None, max_length=200, description="Nombre de la empresa para la cabecera del PDF")
    primary_color: Optional[str] = Field(default=None, max_length=20, description="Color primario en formato hex para el PDF")
    logo_b64: Optional[str] = Field(None, description="Logotipo de la empresa codificado en base64")
