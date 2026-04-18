"""Key management + automatic rotation for JWT and integration secrets.

Responsibilities:
- Maintain a JWT key ring with active kid and grace keys.
- Optionally generate key material via AWS KMS data keys (envelope mode).
- Periodically rotate integration secrets by decrypt+re-encrypt.
- Persist rotation metadata in app_settings.
"""
from __future__ import annotations

import base64
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.settings import AppSetting
from app.core.encryption import decrypt_value, encrypt_value
from app.models.ai_providers import AIProvider
from app.models.cab import IntegrationConfig
from app.models.enterprise import SSOConfig, Webhook

logger = logging.getLogger("clarive.key_management")

JWT_RING_KEY = "security.jwt_keyring"
INTEGRATION_ROTATION_KEY = "security.integration_rotation"


@dataclass
class KeyRingState:
    active_kid: str
    keys: dict[str, str]  # kid -> material_ref (plain:<key> | kms:<cipher_b64>)
    last_rotated_at: datetime


_cache: dict[str, Optional[KeyRingState]] = {"jwt": None}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dt_to_str(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _str_to_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _kms_enabled() -> bool:
    return settings.KMS_PROVIDER.lower() == "aws" and bool(settings.AWS_KMS_KEY_ID)


def _kms_client():
    import boto3

    kwargs = {}
    if settings.AWS_KMS_REGION:
        kwargs["region_name"] = settings.AWS_KMS_REGION
    return boto3.client("kms", **kwargs)


def _generate_key_material_ref() -> str:
    """Generate a new key reference (plain or KMS-wrapped)."""
    if _kms_enabled():
        try:
            client = _kms_client()
            res = client.generate_data_key(KeyId=settings.AWS_KMS_KEY_ID, KeySpec="AES_256")
            ciphertext = base64.urlsafe_b64encode(res["CiphertextBlob"]).decode()
            return f"kms:{ciphertext}"
        except Exception as exc:
            logger.error("KMS key generation failed: %s", exc, exc_info=True)
            raise

    # Non-KMS fallback key material
    return f"plain:{secrets.token_urlsafe(64)}"


def _resolve_material(ref: str) -> str:
    """Resolve material ref to plaintext key string."""
    if ref.startswith("kms:"):
        blob_b64 = ref.split(":", 1)[1]
        blob = base64.urlsafe_b64decode(blob_b64.encode())
        client = _kms_client()
        res = client.decrypt(CiphertextBlob=blob)
        plaintext = base64.urlsafe_b64encode(res["Plaintext"]).decode()
        return plaintext
    if ref.startswith("plain:"):
        return ref.split(":", 1)[1]
    raise ValueError("Invalid key material reference format")


def _get_setting(db, key: str) -> Optional[AppSetting]:
    # Key management settings are global (organization-independent).
    return db.query(AppSetting).filter(
        AppSetting.key == key, AppSetting.organization_id.is_(None)
    ).first()


def _settings_table_available(db) -> bool:
    try:
        db.query(AppSetting.id).limit(1).first()
        return True
    except (OperationalError, ProgrammingError):
        return False


def _legacy_only_state() -> KeyRingState:
    raise RuntimeError("Legacy key state is no longer supported.")


def _save_keyring(db, state: KeyRingState) -> None:
    payload = {
        "active_kid": state.active_kid,
        "keys": state.keys,
        "last_rotated_at": _dt_to_str(state.last_rotated_at),
    }
    row = _get_setting(db, JWT_RING_KEY)
    if not row:
        row = AppSetting(key=JWT_RING_KEY, value=json.dumps(payload), description="JWT signing key ring")
        db.add(row)
    else:
        row.value = json.dumps(payload)


def _load_keyring(db) -> Optional[KeyRingState]:
    row = _get_setting(db, JWT_RING_KEY)
    if not row or not row.value:
        return None
    try:
        raw = json.loads(row.value)
        return KeyRingState(
            active_kid=raw["active_kid"],
            keys=raw["keys"],
            last_rotated_at=_str_to_dt(raw["last_rotated_at"]),
        )
    except Exception as exc:
        logger.error("Invalid JWT keyring payload: %s", exc, exc_info=True)
        return None


def ensure_jwt_keyring(db) -> KeyRingState:
    if not _settings_table_available(db):
        raise RuntimeError("Settings table not available for JWT keyring initialization.")

    state = _load_keyring(db)
    if state:
        return state

    kid = f"k-{_now().strftime('%Y%m%d%H%M%S')}"
    state = KeyRingState(
        active_kid=kid,
        keys={kid: _generate_key_material_ref()},
        last_rotated_at=_now(),
    )
    _save_keyring(db, state)
    db.commit()
    logger.info("Initialized JWT keyring with kid=%s", kid)
    return state


def refresh_caches(db=None) -> None:
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True
    try:
        state = ensure_jwt_keyring(db)
        _cache["jwt"] = state
    finally:
        if own_session:
            db.close()


def get_jwt_signing_key() -> tuple[str, str]:
    """Return (kid, plaintext_key)."""
    if _cache["jwt"] is None:
        refresh_caches()
    state = _cache["jwt"]
    if state is None:
        raise RuntimeError("JWT key ring not initialised — call refresh_caches() first")
    material = state.keys.get(state.active_kid)
    if not material:
        raise RuntimeError("Active JWT kid not present in key ring")
    return state.active_kid, _resolve_material(material)


def get_jwt_verification_keys() -> dict[str, str]:
    """Return map kid -> plaintext_key (active and retained keys only)."""
    if _cache["jwt"] is None:
        refresh_caches()
    state = _cache["jwt"]
    if state is None:
        raise RuntimeError("JWT key ring not initialised — call refresh_caches() first")
    out: dict[str, str] = {}
    for kid, ref in state.keys.items():
        try:
            out[kid] = _resolve_material(ref)
        except Exception as exc:
            logger.warning("Failed resolving key for kid=%s: %s", kid, exc)
    return out


def _rotate_jwt_keyring(db) -> bool:
    state = ensure_jwt_keyring(db)
    due_at = state.last_rotated_at + timedelta(days=settings.JWT_KEY_ROTATION_DAYS)
    if _now() < due_at:
        return False

    new_kid = f"k-{_now().strftime('%Y%m%d%H%M%S')}"
    state.keys[new_kid] = _generate_key_material_ref()
    state.active_kid = new_kid
    state.last_rotated_at = _now()

    # Prune oldest keys keeping retention and always preserving legacy fallback
    ordered = [k for k in sorted(state.keys.keys()) if k != "legacy-secret-key"]
    while len(ordered) > settings.JWT_KEY_RETENTION_COUNT:
        drop = ordered.pop(0)
        state.keys.pop(drop, None)

    _save_keyring(db, state)
    db.commit()
    logger.warning("JWT keyring rotated. New active kid=%s", new_kid)
    return True


def _rotate_integration_secrets(db) -> int:
    """Re-encrypt sensitive integration secrets with current encryption policy."""

    changed = 0

    providers = db.query(AIProvider).all()
    for p in providers:
        if p.api_key:
            plain = decrypt_value(p.api_key)
            if plain:
                p.api_key = encrypt_value(plain)
                changed += 1

    integrations = db.query(IntegrationConfig).all()
    for c in integrations:
        if c.access_token:
            plain = decrypt_value(c.access_token)
            if plain:
                c.access_token = encrypt_value(plain)
                changed += 1
        if c.refresh_token:
            plain = decrypt_value(c.refresh_token)
            if plain:
                c.refresh_token = encrypt_value(plain)
                changed += 1

    sso = db.query(SSOConfig).all()
    for s in sso:
        if s.oidc_client_secret:
            plain = decrypt_value(s.oidc_client_secret)
            if plain:
                s.oidc_client_secret = encrypt_value(plain)
                changed += 1
            elif not s.oidc_client_secret.startswith("v2:"):
                # plaintext legacy
                s.oidc_client_secret = encrypt_value(s.oidc_client_secret)
                changed += 1

    hooks = db.query(Webhook).all()
    for h in hooks:
        if h.secret:
            plain = decrypt_value(h.secret)
            if plain:
                h.secret = encrypt_value(plain)
                changed += 1
            elif not h.secret.startswith("v2:"):
                h.secret = encrypt_value(h.secret)
                changed += 1

    return changed


def rotate_due_materials(db=None) -> dict:
    if not settings.KEY_ROTATION_ENABLED:
        return {"enabled": False, "jwt_rotated": False, "integration_reencrypted": 0}

    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True
    try:
        if not _settings_table_available(db):
            refresh_caches(db)
            return {"enabled": True, "jwt_rotated": False, "integration_reencrypted": 0}

        jwt_rotated = _rotate_jwt_keyring(db)

        ir_row = _get_setting(db, INTEGRATION_ROTATION_KEY)
        last_rot = None
        if ir_row and ir_row.value:
            try:
                last_rot = _str_to_dt(ir_row.value)
            except Exception:
                last_rot = None

        due = (last_rot is None) or (_now() >= last_rot + timedelta(days=settings.INTEGRATION_SECRET_ROTATION_DAYS))
        integration_reencrypted = 0
        if due:
            integration_reencrypted = _rotate_integration_secrets(db)
            if not ir_row:
                ir_row = AppSetting(key=INTEGRATION_ROTATION_KEY, description="Last integration secret re-encryption")
                db.add(ir_row)
            ir_row.value = _dt_to_str(_now())

        db.commit()
        refresh_caches(db)
        return {
            "enabled": True,
            "jwt_rotated": jwt_rotated,
            "integration_reencrypted": integration_reencrypted,
        }
    finally:
        if own_session:
            db.close()


def run_scheduled_rotation() -> None:
    """Scheduler entrypoint: rotate due keys and refresh caches."""
    try:
        result = rotate_due_materials()
        logger.info("Key rotation job result: %s", result)
    except Exception as exc:
        logger.error("Key rotation job failed: %s", exc, exc_info=True)
