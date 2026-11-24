"""Lo que se comprueba en cada petición autenticada (`deps._resolver_usuario`).

1. La sesión del token (`sid`) sigue viva, sin pasar la inactividad ni su tope.
2. La IP, el horario y el país siguen permitidos por la empresa.
3. Modo restringido: con la contraseña caducada o con cambio obligatorio, o con
   el MFA obligatorio sin configurar pasada la gracia, solo se puede llegar a las
   rutas que lo arreglan (403 `contrasena_cambio_obligatorio` /
   `mfa_configuracion_obligatoria`). La pantalla lo sabe por
   `UserPublic.account_security` y enseña el cambio o la configuración.

No aplica al superadmin (vía de recuperación) ni a «entrar como».
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.codigos_de_error import error_http

#: Rutas que siguen abiertas en modo restringido (prefijos).
RUTAS_DE_ARREGLO = (
    "/api/v1/auth/me", "/api/v1/auth/logout", "/api/v1/auth/change-password", "/api/v1/auth/password-policy",
    "/api/v1/auth/mfa", "/api/v1/auth/capacidades", "/api/v1/auth/organizations", "/api/v1/auth/sessions",
    "/api/v1/auth/roles", "/api/v1/security/me",
)


def _aware(d):
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def _ruta_de_arreglo(ruta: str) -> bool:
    return any(ruta == r or ruta.startswith(r + "/") or ruta.startswith(r + "?") for r in RUTAS_DE_ARREGLO)


def _contrasena_bloquea(user, p) -> bool:
    if not getattr(user, "hashed_password", None) or getattr(user, "sso_provider", None):
        return False
    if getattr(user, "password_must_change", False):
        return True
    if p.PASSWORD_EXPIRY_DAYS:
        base = _aware(getattr(user, "password_changed_at", None)) or _aware(getattr(user, "created_at", None))
        return bool(base and base + timedelta(days=p.PASSWORD_EXPIRY_DAYS) <= datetime.now(timezone.utc))
    return False


def _mfa_bloquea(db, user, org, p) -> bool:
    inicio = _aware(getattr(user, "mfa_grace_started_at", None))
    if inicio is None or inicio + timedelta(days=p.MFA_GRACE_DAYS) > datetime.now(timezone.utc):
        return False
    from app.services.seguridad_de_cuentas import mfa
    return bool(mfa.motivo_de_exigencia(db, user, org, p)) and not mfa.factores(db, user, p)["alguno"]


def comprobar_peticion(db, user, payload: dict, request) -> None:
    if getattr(user, "is_superadmin", False) or (db.info or {}).get("suplantado_por"):
        return
    from app.services.seguridad_de_cuentas import acceso, sesiones
    from app.services.seguridad_de_cuentas.auditoria import Origen
    from app.services.seguridad_de_cuentas.politica import leer
    org: Optional[str] = (db.info or {}).get("organization_id") or getattr(user, "organization_id", None)
    # Una sola lectura de la política por petición (antes dos: aquí y en
    # `comprobar_sesion`; sin la caché de 30 s, que en pruebas está apagada,
    # eran 3 consultas más en cada petición autenticada).
    p = leer(db, org)
    sesiones.comprobar_sesion(db, user, payload.get("sid"), org, p=p)
    acceso.comprobar(db, user, org, Origen.de(request).ip, request, p=p)
    ruta = request.url.path if request is not None else ""
    if _ruta_de_arreglo(ruta):
        return
    if _contrasena_bloquea(user, p):
        raise error_http(403, "contrasena_cambio_obligatorio")
    if _mfa_bloquea(db, user, org, p):
        raise error_http(403, "mfa_configuracion_obligatoria")


def marcas(db, user) -> dict:
    """`UserPublic.account_security`: lo que la pantalla tiene que pedir o avisar."""
    from app.services.seguridad_de_cuentas import contrasenas, mfa
    from app.services.seguridad_de_cuentas.politica import leer
    if getattr(user, "is_superadmin", False):
        return {}
    org = (db.info or {}).get("organization_id") or getattr(user, "organization_id", None)
    p = leer(db, org)
    salida = contrasenas.estado(user, p) if getattr(user, "hashed_password", None) else {}
    salida.update(mfa.estado(db, user, org, p))
    return salida
