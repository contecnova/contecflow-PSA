"""Datos de seguridad de cuentas en la copia RGPD del interesado (art. 15 y 20).

Nunca salen contraseñas, hashes, secretos TOTP ni tokens. La supresión borra
`password_history` y `trusted_devices` (patrón de credenciales de
`supresion_service._CREDENCIALES`).
"""
from __future__ import annotations

import json


def _f(d):
    return d.isoformat() if d is not None else None


def copia(db, user) -> dict:
    from app.db.session import sin_filtro_de_tenant
    from app.models.seguridad_de_cuentas import AccessReviewItem, PasswordHistory, TrustedDevice
    from app.models.sessions import UserSession
    with sin_filtro_de_tenant(db):
        historial = db.query(PasswordHistory.created_at).filter(PasswordHistory.user_id == user.id).all()
        dispositivos = db.query(TrustedDevice).filter(TrustedDevice.user_id == user.id).all()
        sesiones = (db.query(UserSession).filter(UserSession.user_id == user.id)
                    .order_by(UserSession.created_at.desc()).limit(500).all())
        revisiones = db.query(AccessReviewItem).filter(AccessReviewItem.user_id == user.id).all()
    return {
        "password_changed_at": _f(user.password_changed_at),
        "password_must_change": bool(user.password_must_change),
        "password_history_entries": [_f(c) for (c,) in historial],
        "locked_until": _f(user.locked_until),
        "mfa_enabled": bool(user.mfa_enabled),
        "mfa_verified_at": _f(user.mfa_verified_at),
        "mfa_grace_started_at": _f(user.mfa_grace_started_at),
        "trusted_devices": [{"device_name": d.device_name, "ip_address": d.ip_address, "created_at": _f(d.created_at),
                             "last_used_at": _f(d.last_used_at), "expires_at": _f(d.expires_at),
                             "revoked_at": _f(d.revoked_at)} for d in dispositivos],
        "sessions": [{"ip_address": s.ip_address, "country_code": s.country_code, "device_name": s.device_name,
                      "auth_method": s.auth_method, "created_at": _f(s.created_at), "last_seen_at": _f(s.last_seen_at),
                      "revoked_at": _f(s.revoked_at), "revoke_reason": s.revoke_reason} for s in sesiones],
        "access_reviews": [{"campaign_id": r.campaign_id, "decision": r.decision, "comment": r.comment,
                            "decided_at": _f(r.decided_at), "snapshot": json.loads(r.snapshot or "{}")}
                           for r in revisiones],
    }
