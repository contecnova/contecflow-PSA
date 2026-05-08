"""Web Push para notificaciones en navegador (VAPID).

Variables de entorno:
  VAPID_PUBLIC_KEY   — base64url, expuesta al frontend (clave pública)
  VAPID_PRIVATE_KEY  — base64url, sólo backend
  VAPID_CONTACT      — mailto:owner@example.com

Genera con (una vez):
  python -c "from py_vapid import Vapid; v = Vapid(); v.generate_keys(); print(v.public_key, v.private_key)"

Si no hay claves configuradas, las funciones registran/borran subs pero no envían.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _vapid_claims():
    contact = os.environ.get("VAPID_CONTACT", "mailto:noreply@contecflow.local")
    return {"sub": contact}


def public_key() -> Optional[str]:
    return os.environ.get("VAPID_PUBLIC_KEY") or None


def is_configured() -> bool:
    return bool(os.environ.get("VAPID_PRIVATE_KEY")) and bool(public_key())


def send(subscription: dict, payload: dict) -> bool:
    """Envía una notificación. `subscription` = {endpoint, keys: {p256dh, auth}}"""
    if not is_configured():
        return False
    try:
        from pywebpush import WebPushException, webpush
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload),
            vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
            vapid_claims=_vapid_claims(),
        )
        return True
    except Exception as exc:
        # 404 / 410 → endpoint expired
        logger.warning("web-push delivery failed: %s", exc)
        return False


def push_to_user(db: Session, user_id: str, payload: dict) -> int:
    from app.models.collaboration import CollaborationPushSubscription
    if not is_configured():
        return 0
    subs = db.query(CollaborationPushSubscription).filter(
        CollaborationPushSubscription.user_id == user_id,
        CollaborationPushSubscription.is_active == True,  # noqa: E712
    ).all()
    delivered = 0
    for s in subs:
        sub = {"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh_key, "auth": s.auth_key}}
        if send(sub, payload):
            delivered += 1
        else:
            s.is_active = False
    db.commit()
    return delivered
