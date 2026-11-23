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
from app.core.codigos_de_error import error
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


# ── Validación de la entrada (incidencia 9 de usuarios, 23-11-2026) ──────────
#
# Guardar un proveedor «Azure AD / Entra ID» daba 500: la columna `provider` es
# `Enum(SSOProvider)`, que guarda el NOMBRE del miembro (`azure`), y el alta le
# pasaba el texto `azure_ad` (el VALOR): SQLAlchemy no lo encontraba entre los
# nombres y lanzaba `LookupError`. Con oidc, okta y google no fallaba porque
# nombre y valor coinciden. Ahora el proveedor se convierte al miembro y el
# resto de la entrada se valida con códigos (nunca un 500).

import re as _re

_GUID = _re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_DOMINIO = _re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
_CLAIM = _re.compile(r"[A-Za-z0-9_:./-]{1,100}")
#: Hosts de Microsoft Entra ID (nube pública, administración de EE. UU. y China).
_HOSTS_DE_ENTRA = ("login.microsoftonline.com", "login.microsoftonline.us", "login.partner.microsoftonline.cn")
_MAX_GRUPOS = 200


def _proveedor(valor):
    """El miembro de `SSOProvider` (acepta el miembro, su valor `azure_ad` o su nombre `azure`)."""
    from app.models.enterprise import SSOProvider
    if isinstance(valor, SSOProvider):
        return valor
    texto = str(valor or "").strip()
    try:
        return SSOProvider(texto)
    except ValueError:
        if texto in SSOProvider.__members__:
            return SSOProvider[texto]
        raise error(422, "sso_proveedor_no_soportado", proveedor=texto[:30]) from None


def _roles_validos() -> set:
    from app.models.user import UserRole
    return {r.value for r in UserRole}


def validar_entrada_sso(data: dict, proveedor, *, actual=None) -> dict:
    """Normaliza y valida `data` (alta o edición parcial). Devuelve `data` listo para el modelo.

    - discovery: HTTPS, sin marcadores por rellenar (`{tenant-id}`) y, para
      Entra ID, en un host de Microsoft con el inquilino en la ruta;
    - client id: obligatorio para activar; en Entra ID, un GUID;
    - secreto: obligatorio para activar (se cifra al guardar, nunca vuelve);
    - dominios: lista de dominios válidos, en minúsculas y sin `@`;
    - mapeo de grupos y rol por defecto: solo roles que existen.
    """
    from urllib.parse import urlparse

    from app.models.enterprise import SSOProvider
    proveedor = _proveedor(proveedor)
    for campo in ("oidc_client_id", "oidc_discovery_url", "name", "allowed_domains", "groups_claim",
                  "oidc_scopes", "default_role"):
        if isinstance(data.get(campo), str):
            data[campo] = data[campo].strip()

    url = data.get("oidc_discovery_url")
    if url:
        partes = urlparse(url)
        if partes.scheme != "https" or not partes.hostname or "{" in url or "}" in url or " " in url:
            raise error(422, "sso_discovery_no_valida")
        if proveedor == SSOProvider.azure:
            inquilino = (partes.path.strip("/").split("/") or [""])[0]
            if partes.hostname.lower() not in _HOSTS_DE_ENTRA or not inquilino or inquilino.startswith("."):
                raise error(422, "sso_discovery_entra_no_valida")
    elif "oidc_discovery_url" in data:
        data["oidc_discovery_url"] = None

    client_id = data.get("oidc_client_id")
    if client_id and (len(client_id) > 500 or (proveedor == SSOProvider.azure and not _GUID.fullmatch(client_id))):
        raise error(422, "sso_client_id_no_valido")

    secreto = data.get("oidc_client_secret")
    if secreto is not None and len(str(secreto)) > 300:
        raise error(422, "sso_secreto_no_valido")

    if data.get("allowed_domains") is not None:
        dominios = [d.strip().lower().lstrip("@") for d in _re.split(r"[,;\s]+", data["allowed_domains"]) if d.strip()]
        for d in dominios:
            if not _DOMINIO.fullmatch(d):
                raise error(422, "sso_dominio_no_valido", dominio=d[:80])
        unidos = ",".join(dict.fromkeys(dominios))
        if len(unidos) > 500:
            raise error(422, "sso_dominio_no_valido", dominio=unidos[:80])
        data["allowed_domains"] = unidos or None

    roles = _roles_validos()
    if data.get("default_role") is not None and data["default_role"] not in roles:
        raise error(422, "sso_rol_no_valido", rol=str(data["default_role"])[:50])
    mapa = data.get("role_mapping")
    if mapa is not None:
        if not isinstance(mapa, dict) or len(mapa) > _MAX_GRUPOS:
            raise error(422, "sso_mapeo_no_valido")
        limpio = {}
        for grupo, rol in mapa.items():
            grupo, rol = str(grupo).strip(), str(rol).strip()
            if not grupo or len(grupo) > 200:
                raise error(422, "sso_mapeo_no_valido")
            if rol not in roles:
                raise error(422, "sso_rol_no_valido", rol=rol[:50])
            limpio[grupo] = rol
        data["role_mapping"] = limpio
    if data.get("groups_claim") and not _CLAIM.fullmatch(data["groups_claim"]):
        raise error(422, "sso_claim_no_valido")

    # Activo = usable en el login: tiene que tener lo mínimo.
    activo = data.get("is_active") if "is_active" in data else getattr(actual, "is_active", False)
    if activo:
        tiene_id = data.get("oidc_client_id") if "oidc_client_id" in data else getattr(actual, "oidc_client_id", None)
        tiene_secreto = data.get("oidc_client_secret") or getattr(actual, "oidc_client_secret", None)
        tiene_url = (data.get("oidc_discovery_url") if "oidc_discovery_url" in data
                     else getattr(actual, "oidc_discovery_url", None))
        if not tiene_id:
            raise error(422, "sso_falta_dato", campo="oidc_client_id")
        if not tiene_secreto:
            raise error(422, "sso_falta_dato", campo="oidc_client_secret")
        if proveedor in (SSOProvider.oidc, SSOProvider.azure) and not tiene_url:
            raise error(422, "sso_falta_dato", campo="oidc_discovery_url")
    return data


# ── SSO ───────────────────────────────────────────────────────────────────────

def list_sso_configs(db: Session) -> list:
    return [serialize_sso(c) for c in db.query(SSOConfig).filter(SSOConfig.is_deleted == False).all()]


def create_sso_config(payload, current_user, db: Session) -> dict:
    import json as _json
    data = payload.model_dump()
    # Incidencia 9 (23-11-2026): el proveedor como miembro del enum (`azure_ad` -> `azure`).
    data["provider"] = _proveedor(data.get("provider"))
    data = validar_entrada_sso(data, data["provider"])
    data["role_mapping"] = _json.dumps(data["role_mapping"]) if data.get("role_mapping") else None
    if current_user.organization_id and not data.get("organization_id"):
        data["organization_id"] = current_user.organization_id
    # Auditoria 2026-11 (critico): el alta aceptaba cualquier organization_id del
    # cuerpo (la edicion ya lo comprobaba). El admin de A creaba un SSO de B con
    # su propio IdP y entraba como cualquier usuario de B.
    if not getattr(current_user, "is_superadmin", False) and data.get("organization_id") != current_user.organization_id:
        raise error(403, "sso_otra_empresa", detail="No puedes configurar SSO para otra organización")
    # M84 (auditoría 22-11-2026): un admin sin empresa (None == None) creaba un
    # SSO GLOBAL, válido para todas. Solo un superadmin puede crear uno sin empresa.
    if not data.get("organization_id") and not getattr(current_user, "is_superadmin", False):
        raise error(403, "sso_otra_empresa", detail="Un SSO sin empresa solo lo crea la plataforma")
    if data.get("oidc_client_secret"):
        data["oidc_client_secret"] = encrypt_value(data["oidc_client_secret"])
    config = SSOConfig(created_by=current_user.id, **data)
    db.add(config)
    db.flush()  # el id existe antes de auditarlo
    # GRC: del secreto solo consta que se puso; nunca su valor.
    audit_log(db, current_user, "CREATE", "sso_configs", config.id, payload.provider,
              new_values={k: ("***" if k == "oidc_client_secret" and v else getattr(v, "value", v))
                          for k, v in data.items()})
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
    data = validar_entrada_sso(data, config.provider, actual=config)  # incidencia 9 (23-11-2026)
    if "role_mapping" in data and data["role_mapping"] is not None:
        data["role_mapping"] = _json.dumps(data["role_mapping"])
    if "oidc_client_secret" in data and data["oidc_client_secret"]:
        data["oidc_client_secret"] = encrypt_value(data["oidc_client_secret"])
    for k, v in data.items():
        setattr(config, k, v)
    # Revisión GRC 2026-11b: crear SSO se auditaba; cambiarlo (o rotar su
    # secreto) y borrarlo, no. Del secreto sólo consta que cambió.
    audit_log(db, current_user, "UPDATE", "sso_configs", config.id, config.provider,
              new_values={k: ("***" if k == "oidc_client_secret" else v) for k, v in data.items()})
    db.commit()
    return serialize_sso(config)


def delete_sso_config(config_id: str, db: Session, current_user=None) -> dict:
    config = db.query(SSOConfig).filter(SSOConfig.id == config_id, SSOConfig.is_deleted == False).first()
    if not config:
        raise ValueError("not_found")
    config.is_active = False
    config.is_deleted = True
    audit_log(db, current_user, "DELETE", "sso_configs", config.id, config.provider)
    db.commit()
    return {"ok": True, "message": "Configuracion SSO eliminada correctamente"}


def get_sso_config_for_test(config_id: str, db: Session):
    return db.query(SSOConfig).filter(SSOConfig.id == config_id, SSOConfig.is_deleted == False).first()
