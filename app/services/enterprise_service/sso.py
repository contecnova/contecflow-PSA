"""Configuraciones de SSO: validacion, alta, edicion y borrado.

Parte de `app.services.enterprise_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from sqlalchemy.orm import Session
from app.core.encryption import encrypt_value
from app.models.enterprise import SSOConfig
from app.services.audit import audit_log
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.enterprise import (
        SSOConfig,
    )


def serialize_sso(s) -> dict:
    import json
    return {
        "id": s.id, "provider": s.provider, "name": s.name, "groups_claim": s.groups_claim,
        "is_active": s.is_active, "is_default": s.is_default,
        "saml_entity_id": s.saml_entity_id,
        "saml_sso_url": s.saml_sso_url,
        "saml_slo_url": s.saml_slo_url,
        "has_certificate": bool(s.saml_certificate),
        "saml_attribute_email": s.saml_attribute_email,
        "saml_attribute_name": s.saml_attribute_name,
        "saml_attribute_role": s.saml_attribute_role,
        "oidc_client_id": s.oidc_client_id,
        "has_oidc_secret": bool(s.oidc_client_secret),
        "oidc_discovery_url": s.oidc_discovery_url,
        "oidc_scopes": s.oidc_scopes,
        "role_mapping": json.loads(s.role_mapping) if s.role_mapping else {},
        "organization_id": s.organization_id,
        "auto_create_users": s.auto_create_users,
        "default_role": s.default_role,
        "allowed_domains": s.allowed_domains,
        "created_at": str(s.created_at)[:10] if s.created_at else None,
        # Auditoria 2026-11: se anunciaban URL de SAML (ACS, SLO) que no existen.
    }


def validate_sso_config(config) -> dict:
    """Validate SSO configuration fields without authenticating."""
    issues = []
    if config.provider == "saml":
        if not config.saml_entity_id: issues.append("Falta Entity ID del IdP")
        if not config.saml_sso_url:   issues.append("Falta SSO URL del IdP")
        if not config.saml_certificate: issues.append("Falta certificado X.509 del IdP")
    elif config.provider in ["oidc", "google", "azure_ad", "okta"]:
        if not config.oidc_client_id:     issues.append("Falta Client ID")
        if not config.oidc_client_secret: issues.append("Falta Client Secret")
        if config.provider == "oidc" and not config.oidc_discovery_url:
            issues.append("Falta Discovery URL (OIDC)")
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "provider": config.provider,
        # El redirect URI que hay que registrar en el IdP es el login de la app.
        "redirect_uri_hint": "<origen de la aplicación>/login",
    }


# ── SSO ───────────────────────────────────────────────────────────────────────

def list_sso_configs(db: Session) -> list:
    return [serialize_sso(c) for c in db.query(SSOConfig).filter(SSOConfig.is_deleted == False).all()]


def create_sso_config(payload, current_user, db: Session) -> dict:
    import json as _json
    data = {k: (_json.dumps(v) if k == "role_mapping" and v else v) for k, v in payload.model_dump().items()}
    if current_user.organization_id and not data.get("organization_id"):
        data["organization_id"] = current_user.organization_id
    if data.get("oidc_client_secret"):
        data["oidc_client_secret"] = encrypt_value(data["oidc_client_secret"])
    config = SSOConfig(created_by=current_user.id, **data)
    db.add(config)
    audit_log(db, current_user, "CREATE", "sso_configs", config.id, payload.provider)
    db.commit()
    return serialize_sso(config)


def update_sso_config(config_id: str, payload, current_user, db: Session) -> dict:
    import json as _json
    config = db.query(SSOConfig).filter(SSOConfig.id == config_id, SSOConfig.is_deleted == False).first()
    if not config:
        raise ValueError("not_found")
    data = payload.model_dump(exclude_unset=True)
    if current_user.organization_id and data.get("organization_id") not in (None, current_user.organization_id):
        raise ValueError("org_mismatch")
    if "role_mapping" in data and data["role_mapping"] is not None:
        data["role_mapping"] = _json.dumps(data["role_mapping"])
    if "oidc_client_secret" in data and data["oidc_client_secret"]:
        data["oidc_client_secret"] = encrypt_value(data["oidc_client_secret"])
    for k, v in data.items():
        setattr(config, k, v)
    db.commit()
    return serialize_sso(config)


def delete_sso_config(config_id: str, db: Session) -> dict:
    config = db.query(SSOConfig).filter(SSOConfig.id == config_id, SSOConfig.is_deleted == False).first()
    if not config:
        raise ValueError("not_found")
    config.is_active = False
    config.is_deleted = True
    db.commit()
    return {"ok": True, "message": "Configuracion SSO eliminada correctamente"}


def get_sso_config_for_test(config_id: str, db: Session):
    return db.query(SSOConfig).filter(SSOConfig.id == config_id, SSOConfig.is_deleted == False).first()
