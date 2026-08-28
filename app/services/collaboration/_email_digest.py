"""Daily / weekly email digest of collaboration notifications.

Reglas:
  - Por usuario, según `collaboration_notification_rules.email_digest`:
      off    → no enviamos
      daily  → resumen diario (cada 24h)
      weekly → resumen semanal (cada 168h)
  - Por defecto (sin regla) = weekly
  - Sólo notificaciones no leídas
  - Se marca `delivered_email=True` para no repetir

Llamado por scheduler externo o manualmente vía endpoint admin
`POST /collaboration/admin/email-digest/run` (incluye dry-run).
"""
from __future__ import annotations

import logging
import os
import smtplib
from datetime import timedelta
from app.core.timeutil import utcnow
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)


def _send(to_email: str, subject: str, html: str) -> bool:
    if not settings.SMTP_HOST or not to_email:
        return False
    msg = MIMEMultipart("alternative")
    msg["From"] = settings.SMTP_FROM or settings.NOTIFICATION_EMAIL_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as s:
            s.ehlo()
            try:
                s.starttls()
            # intentional: best-effort fallback, log noise outweighs diagnostic value
            except Exception:
                logger.debug("_send: fallo best-effort ignorado", exc_info=True)
            if settings.SMTP_USER:
                s.login(settings.SMTP_USER, settings.SMTP_PASS)
            s.send_message(msg)
        return True
    except Exception as exc:
        logger.warning("digest send failed for %s: %s", to_email, exc)
        return False


def _render(notifs, user_name: str) -> str:
    lines = []
    lines.append(f"<p>Hola {user_name or ''},</p>")
    lines.append(f"<p>Tienes <b>{len(notifs)}</b> notificación(es) sin leer en Contecflow Chat:</p>")
    lines.append("<ul>")
    for n in notifs[:50]:
        title = (n.title or "Notificación").replace("<", "&lt;")
        body = (n.body or "")[:160].replace("<", "&lt;")
        lines.append(f"<li><b>{title}</b><br><span style='color:#666'>{body}</span></li>")
    lines.append("</ul>")
    base_url = os.environ.get("APP_PUBLIC_URL", "http://localhost:3000")
    lines.append(f"<p><a href='{base_url}/chat'>Abrir el chat</a></p>")
    lines.append("<p style='color:#999;font-size:12px'>Configura tu frecuencia de digest en /chat → admin → reglas.</p>")
    return "\n".join(lines)


def run(db: Session, *, dry_run: bool = False, frequency: Optional[str] = None) -> dict:
    """Ejecuta el digest. `frequency` = 'daily'|'weekly'|None (todas)."""
    from app.models.collaboration import (
        CollaborationNotification, CollaborationNotificationRule,
    )
    from app.models.user import User

    now = utcnow()
    cutoff_daily = now - timedelta(days=1)
    cutoff_weekly = now - timedelta(weeks=1)
    sent = 0
    skipped = 0
    candidates: dict[str, str] = {}

    # Determine frequencies per user via rules (global scope row)
    rules = {
        r.user_id: r.email_digest
        for r in db.query(CollaborationNotificationRule).filter(
            CollaborationNotificationRule.scope == "global"
        ).all()
    }

    # User base: any user with unread notifs
    user_ids = {
        r[0]
        for r in db.query(CollaborationNotification.user_id).filter(
            CollaborationNotification.user_id.isnot(None),
            CollaborationNotification.is_read == False,
            CollaborationNotification.delivered_email == False,
        ).distinct().all()
    }

    for uid in user_ids:
        freq = rules.get(uid, "weekly")
        if freq == "off":
            skipped += 1
            continue
        if frequency and frequency != freq:
            continue
        cutoff = cutoff_daily if freq == "daily" else cutoff_weekly
        notifs = db.query(CollaborationNotification).filter(
            CollaborationNotification.user_id == uid,
            CollaborationNotification.is_read == False,
            CollaborationNotification.delivered_email == False,
            CollaborationNotification.created_at >= cutoff,
        ).order_by(CollaborationNotification.created_at.desc()).limit(100).all()
        if not notifs:
            continue
        u = db.query(User).filter(User.id == uid).first()
        if not u or not u.email:
            continue
        html = _render(notifs, u.full_name or u.username or "")
        subject = f"Contecflow Chat — {len(notifs)} novedades ({freq})"
        candidates[u.email] = html
        if dry_run:
            sent += 1
            continue
        if _send(u.email, subject, html):
            for n in notifs:
                n.delivered_email = True
            db.commit()
            sent += 1
        else:
            skipped += 1

    return {"sent": sent, "skipped": skipped, "dry_run": dry_run, "candidates": list(candidates.keys())}
