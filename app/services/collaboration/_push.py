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
from app.core.timeutil import utcnow

import json
import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _vapid_claims():
    # env-driven: VAPID keys for web-push are deployment-specific secrets and an
    # optional capability; intentionally not part of Settings.
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
        from pywebpush import webpush
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
        CollaborationPushSubscription.is_active == True,
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


def purge_stale_subscriptions(db: Session, *, days: int = 30) -> int:
    """Borra suscripciones `is_active=False` creadas hace más de `days` días.
    Las recientes se mantienen por si el usuario re-aprueba en el siguiente
    login (re-activa la fila). Retorna cuántas se eliminaron."""
    from datetime import timedelta
    from app.models.collaboration import CollaborationPushSubscription
    cutoff = utcnow() - timedelta(days=days)
    n = db.query(CollaborationPushSubscription).filter(
        CollaborationPushSubscription.is_active == False,
        CollaborationPushSubscription.created_at < cutoff,
    ).delete(synchronize_session=False)
    db.commit()
    return int(n or 0)
