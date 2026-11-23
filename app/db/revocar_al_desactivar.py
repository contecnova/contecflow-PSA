"""Desactivar a un usuario cierra sus sesiones y sus dispositivos de confianza.

23-11-2026 (docs/seguridad/politicas_de_cuenta.md §6). `get_current_user` ya
rechazaba al inactivo, pero sus filas de sesión seguían vivas en el panel y su
refresco solo fallaba al usarse. Un `before_flush` lo cubre venga de donde venga
la baja: la ficha, SCIM, el trabajo de externos, la recertificación o el de
cuentas inactivas. Solo depende de modelos y de `app.db`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import event, inspect, update
from sqlalchemy.orm import Session


def _desactivados(session) -> list[str]:
    from app.models.user import User
    ids = []
    for obj in session.dirty:
        if not isinstance(obj, User) or obj.is_active is not False:
            continue
        hist = inspect(obj).attrs.is_active.history
        if hist.deleted and any(v is True for v in hist.deleted):
            ids.append(obj.id)
    return ids


def revocar_al_desactivar(session, flush_context=None, instances=None) -> None:
    ids = _desactivados(session)
    if not ids:
        return
    from app.models.seguridad_de_cuentas import TrustedDevice
    from app.models.sessions import UserSession
    from app.db.session import sin_filtro_de_tenant
    ahora = datetime.now(timezone.utc)
    with sin_filtro_de_tenant(session):
        _revocar(session, ids, ahora, UserSession, TrustedDevice)


def _revocar(session, ids, ahora, UserSession, TrustedDevice) -> None:
    session.execute(update(UserSession).where(UserSession.user_id.in_(ids), UserSession.revoked_at.is_(None))
                    .values(revoked_at=ahora, revoke_reason="user_deactivated")
                    .execution_options(synchronize_session=False))
    session.execute(update(TrustedDevice).where(TrustedDevice.user_id.in_(ids), TrustedDevice.revoked_at.is_(None))
                    .values(revoked_at=ahora, revoke_reason="user_deactivated")
                    .execution_options(synchronize_session=False))


def registrar() -> None:
    if not event.contains(Session, "before_flush", revocar_al_desactivar):
        event.listen(Session, "before_flush", revocar_al_desactivar)
