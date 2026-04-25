"""
Auth endpoints — Modular architecture for authentication flows.
Imports sub-routers for different auth domains: core, MFA, SSO, SAML, Sessions.
"""
from fastapi import APIRouter

from app.api.v1.routers.auth_core import router as auth_core_router
from app.api.v1.routers.auth_mfa import router as auth_mfa_router
from app.api.v1.routers.auth_sso import router as auth_sso_router
from app.api.v1.routers.auth_saml import router as auth_saml_router
from app.api.v1.routers.auth_sessions import router as auth_sessions_router
from app.services.auth_service import (
	issue_password_reset_token as _issue_password_reset_token,
	resolve_sso_organization_id as _resolve_sso_organization_id,
	validate_https_discovery_url as _validate_https_discovery_url,
)

router = APIRouter()

# ── Aggregate all auth sub-routers ────────────────────────────────────────────
# Core authentication flows: login, refresh, logout, password reset
router.include_router(auth_core_router)

# Multi-factor authentication: TOTP setup and WebAuthn/passkeys
router.include_router(auth_mfa_router)

# OAuth2 / OIDC single sign-on providers
router.include_router(auth_sso_router)

# SAML 2.0 service provider metadata and health
router.include_router(auth_saml_router)

# User session management and device revocation
router.include_router(auth_sessions_router)
