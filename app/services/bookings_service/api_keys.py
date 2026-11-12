"""Claves de API: alta, revocacion y verificacion.

Parte de `app.services.bookings_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
import secrets
from app.models.bookings import ApiKey
from app.services.audit import audit_log as _audit
from app.core.errores import ErrorDeDominio

from app.services.bookings_service._comun import logger


# ── API key helpers ───────────────────────────────────────────────────────────

def _hash_api_key(key: str) -> str:
    import bcrypt as _bcrypt
    return _bcrypt.hashpw(key.encode(), _bcrypt.gensalt()).decode()


def _verify_api_key(key: str, hashed: str) -> bool:
    import bcrypt as _bcrypt
    try:
        return _bcrypt.checkpw(key.encode(), hashed.encode())
    except Exception:
        logger.warning("Bookings API key verification raised unexpectedly", exc_info=True)
        return False


# ── API Keys ──────────────────────────────────────────────────────────────────

def list_api_keys_records(user_id, is_superadmin: bool, db) -> list:
    q = db.query(ApiKey)
    if not is_superadmin:
        q = q.filter(ApiKey.user_id == user_id)
    return [{
        "id": k.id, "name": k.name,
        "key_prefix": k.key_prefix,
        "scopes": json.loads(k.scopes) if k.scopes else [],
        "is_active": k.is_active,
        "rate_limit_per_hour": k.rate_limit_per_hour,
        "rate_limit_per_day": k.rate_limit_per_day,
        "requests_today": k.requests_today or 0,
        "last_used_at": str(k.last_used_at)[:16] if k.last_used_at else None,
        "expires_at": str(k.expires_at)[:10] if k.expires_at else None,
        "created_at": str(k.created_at)[:10] if k.created_at else None,
    } for k in q.order_by(ApiKey.created_at.desc()).all()]


def create_api_key_record(payload, user_id, db) -> dict:
    from app.core.credenciales_delegadas import ALCANCES_VALIDOS, huella
    invalidos = sorted(set(payload.scopes) - set(ALCANCES_VALIDOS))
    if invalidos or not payload.scopes:
        raise ErrorDeDominio(422, f"Alcances no válidos: {', '.join(invalidos) or 'ninguno'}. "
                                 f"Válidos: {', '.join(ALCANCES_VALIDOS)}")
    raw_key    = f"nxpm_{secrets.token_hex(24)}"
    key_prefix = raw_key[:12]
    api_key = ApiKey(
        name=payload.name,
        key_hash=_hash_api_key(raw_key),
        key_digest=huella(raw_key),
        key_prefix=key_prefix,
        user_id=user_id,
        scopes=json.dumps(payload.scopes),
        rate_limit_per_hour=payload.rate_limit_per_hour,
        rate_limit_per_day=payload.rate_limit_per_day,
        expires_at=payload.expires_at,
    )
    db.add(api_key)
    db.flush()
    _audit(db, None, "CREATE", "api_keys", api_key.id, payload.name)
    db.commit()
    return {
        "id": api_key.id,
        "name": api_key.name,
        "key": raw_key,
        "key_prefix": key_prefix,
        "warning": "Copia esta clave ahora. No se mostrará de nuevo.",
    }


def revoke_api_key_record(key_id: str, user_id, db) -> dict:
    key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == user_id).first()
    if not key: raise ErrorDeDominio(404)
    key.is_active = False
    _audit(db, None, "REVOKE", "api_keys", key.id, key.name)
    db.commit()
    return {"ok": True}
