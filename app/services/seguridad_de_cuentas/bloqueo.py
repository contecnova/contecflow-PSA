"""Bloqueo de cuenta por intentos: persistente, con aviso y desbloqueo por el administrador.

Se integra con las cubetas de login que ya había (`auth_service/estado_efimero`):
cuando la cubeta de la CUENTA se bloquea, el bloqueo también se guarda en
`users.locked_until` (vale para todos los procesos aunque Redis no esté), se
avisa al usuario y se alerta al administrador.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d):
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def segundos_bloqueado(user) -> int:
    fin = _aware(getattr(user, "locked_until", None))
    if not fin:
        return 0
    return max(0, int((fin - _ahora()).total_seconds()))


def al_bloquearse(db, user, segundos: int) -> None:
    """La cuenta acaba de bloquearse: persiste, avisa y alerta. Confirma; nunca propaga."""
    if user is None or segundos <= 0:
        return
    try:
        from app.services.seguridad_de_cuentas import alertas
        from app.services.seguridad_de_cuentas.auditoria import auditar
        from app.services.seguridad_de_cuentas.politica import leer
        user.locked_until = _ahora() + timedelta(seconds=segundos)
        p = leer(db, user.organization_id)
        auditar(db, None, "ACCOUNT_LOCKED", user, datos={"seconds": segundos})
        if p.LOGIN_LOCKOUT_NOTIFY_USER:
            alertas.al_usuario(db, user.id, "seguridad.aviso.bloqueo", min=max(1, segundos // 60))
        alertas.a_los_admins(db, user.organization_id, "seguridad.alerta.bloqueo",
                             usuario=user.email or user.username)
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("al_bloquearse: no se pudo registrar el bloqueo de %s", getattr(user, "id", None), exc_info=True)


def desbloquear(db, user) -> None:
    """Quita el bloqueo persistente y las cubetas del usuario (todas las IPs). No confirma."""
    from app.services.auth_service import estado_efimero as ee
    user.locked_until = None
    nombres = {n.strip().lower() for n in (user.username, user.email) if n}
    for n in nombres:
        ee.clear_login_failure(ee.login_account_bucket(n))
        r = ee.get_sso_redis()
        if r is not None:
            try:
                for clave in list(r.scan_iter(f"{ee.LOGIN_FAIL_PREFIX}{n}|*")) + list(r.scan_iter(f"{ee.LOGIN_LOCK_PREFIX}{n}|*")):
                    r.delete(clave)
            except Exception:
                logger.debug("desbloquear: Redis no disponible", exc_info=True)
        with ee._sso_states_lock:
            for clave in [k for k in ee._login_fail_fallback if k.startswith(f"{n}|")]:
                ee._login_fail_fallback.pop(clave, None)


def bloqueado(user) -> Optional[int]:
    s = segundos_bloqueado(user)
    return s or None
