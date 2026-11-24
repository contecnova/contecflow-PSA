"""Resumen diario de avisos por correo (revisión 2026-11).

Quien lo activa en *Perfil → Avisos* recibe UN correo al día con lo que no ha
leído de las últimas 24 horas, a partir de `NOTIFICATIONS_DIGEST_HOUR` en su
zona horaria. Si no hay nada pendiente, no se manda nada. La fecha del último
envío se guarda en sus preferencias: el trabajo corre cada hora y no repite.
"""
from __future__ import annotations

import html
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _ajuste(db: Session, clave: str, org) -> int:
    from app.services.settings_service import get_runtime_int
    return int(get_runtime_int(db, clave, org) or 0)


def enviar(db: Session, ahora: datetime | None = None) -> int:
    from app.core import timeutil
    from app.core.config import settings
    from app.models.enterprise import Notification
    from app.models.user import User, UserPreference
    from app.services.notification_service import send_email_notification

    ahora = ahora or datetime.now(timezone.utc)
    enviados = 0
    for pref in db.query(UserPreference).filter(UserPreference.extra.like('%notifications_digest%')):
        try:
            extra = json.loads(pref.extra or "{}")
        except ValueError:
            continue
        if not extra.get("notifications_digest"):
            continue
        usuario = db.get(User, pref.user_id)
        if not usuario or not usuario.is_active or not usuario.email:
            continue
        local = ahora.astimezone(timeutil.zone_for_user(usuario))
        if local.hour < _ajuste(db, "NOTIFICATIONS_DIGEST_HOUR", usuario.organization_id):
            continue
        hoy = local.date().isoformat()
        if extra.get("notifications_digest_last") == hoy:
            continue
        maximo = max(1, _ajuste(db, "NOTIFICATIONS_DIGEST_MAX_ITEMS", usuario.organization_id))
        pendientes = (db.query(Notification)
                      .filter(Notification.user_id == usuario.id, Notification.is_read.is_(False),
                              Notification.created_at >= ahora - timedelta(hours=24))
                      .order_by(Notification.created_at.desc()).all())
        extra["notifications_digest_last"] = hoy
        pref.extra = json.dumps(extra)
        if not pendientes:
            continue
        filas = "".join(f"<li><strong>{html.escape(n.title or '')}</strong>"
                        f"{' — ' + html.escape(n.body) if n.body else ''}</li>" for n in pendientes[:maximo])
        resto = len(pendientes) - maximo
        from app.services.textos_de_salida import texto_para

        def _t(clave, **p):
            return texto_para(db, clave, user_id=usuario.id, org_id=usuario.organization_id, **p)
        cuerpo = (f"<p>{_t('avisos.resumen.cuerpo', n=len(pendientes))}</p><ul>{filas}</ul>"
                  + (f"<p>{_t('avisos.resumen.resto', resto=resto)}</p>" if resto > 0 else "")
                  + f'<p><a href="{settings.FRONTEND_URL}/inbox">{_t("avisos.resumen.abrir")}</a></p>')
        if send_email_notification(usuario.email, _t("avisos.resumen.asunto", n=len(pendientes)), cuerpo):
            enviados += 1
    db.commit()
    return enviados


# Segunda auditoría 2026-11 (#19): `enviar_job` (sesión propia SIN contexto de
# tenant, sin llamadas) se borró; el worker llama a `enviar` por organización.
