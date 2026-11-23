"""Trabajo diario `seguridad-de-cuentas-diario` (por empresa, `en_cada_organizacion`):
cuentas inactivas, avisos de caducidad de contraseña y dispositivos de confianza caducados."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _aware(d):
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def por_empresa(db, org: str) -> dict:
    from app.db.session import _miembros_de
    from app.models.seguridad_de_cuentas import TrustedDevice
    from app.models.user import User
    from app.services.seguridad_de_cuentas import alertas, contrasenas
    from app.services.seguridad_de_cuentas.auditoria import auditar
    from app.services.seguridad_de_cuentas.politica import leer

    ahora = datetime.now(timezone.utc)
    resumen = {"deactivated": 0, "expiry_warnings": 0, "devices_expired": 0}
    for d in db.query(TrustedDevice).filter(TrustedDevice.organization_id == org, TrustedDevice.revoked_at.is_(None),
                                            TrustedDevice.expires_at <= ahora).all():
        d.revoked_at, d.revoke_reason = ahora, "expired"
        resumen["devices_expired"] += 1
    p = leer(db, org)
    usuarios = db.query(User).filter(_miembros_de(User, org), User.is_active.is_(True),
                                     User.is_superadmin.isnot(True)).all()
    for u in usuarios:
        if p.ACCOUNT_INACTIVE_DISABLE_DAYS > 0:
            ultima = _aware(u.last_login) or _aware(u.created_at)
            if ultima and ultima < ahora - timedelta(days=p.ACCOUNT_INACTIVE_DISABLE_DAYS):
                u.is_active = False   # revocar_al_desactivar cierra sus sesiones
                auditar(db, None, "ACCOUNT_AUTO_DISABLED", u, org_id=org,
                        datos={"inactive_days": p.ACCOUNT_INACTIVE_DISABLE_DAYS,
                               "last_login": u.last_login.isoformat() if u.last_login else None})
                resumen["deactivated"] += 1
                continue
        if not u.hashed_password:
            continue
        e = contrasenas.estado(u, p)
        dias = e.get("password_expires_in_days")
        if e.get("password_expiry_warning") and dias in {p.PASSWORD_EXPIRY_WARNING_DAYS, 7, 3, 1, 0}:
            alertas.al_usuario(db, u.id, "seguridad.aviso.caducidad", dias=dias)
            resumen["expiry_warnings"] += 1
    db.commit()
    return resumen
