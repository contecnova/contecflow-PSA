"""Contraseñas: validación completa, historial, caducidad, cambio forzado y temporales.

`validar_nueva` aplica la política de la empresa (longitud mínima y máxima,
complejidad, lista LOCAL de comunes, datos personales, historial y edad mínima).
`registrar_cambio` deja el hash en el historial, poda a las N últimas y limpia
las marcas de cambio forzado y de contraseña temporal.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from app.core.codigos_de_error import error
from app.services.seguridad_de_cuentas.politica import PoliticaDeCuenta, leer


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d: Optional[datetime]) -> Optional[datetime]:
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


@lru_cache(maxsize=1)
def comunes() -> frozenset:
    ruta = Path(__file__).with_name("comunes.txt")
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    return frozenset(x.strip().lower() for x in lineas if x.strip() and not x.startswith("#"))


_SECUENCIAS = ("0123456789", "abcdefghijklmnopqrstuvwxyz", "qwertyuiop", "asdfghjkl", "zxcvbnm")


def es_comun(clave: str) -> bool:
    """Lista local + patrones triviales (un solo carácter, secuencias). Sin red."""
    baja = clave.lower()
    if baja in comunes():
        return True
    raiz = re.sub(r"[\d\W_]+$", "", baja)          # «Password2024!» -> «password»
    if raiz and len(raiz) >= 4 and raiz in comunes():
        return True
    if len(set(baja)) <= 2:
        return True
    for s in _SECUENCIAS:
        if len(baja) >= 6 and (baja in s or baja in s[::-1]):
            return True
    return False


def _contiene_datos_personales(clave: str, datos: Iterable[Optional[str]]) -> bool:
    baja = clave.lower()
    for d in datos:
        for trozo in re.split(r"[\s@._\-]+", (d or "").lower()):
            if len(trozo) >= 4 and trozo in baja:
                return True
    return False


def comprobar_reglas(clave: str, p: PoliticaDeCuenta, datos_personales: Iterable[Optional[str]] = ()) -> None:
    """Reglas sin base de datos (también para el portal). Lanza con código."""
    clave = clave or ""
    if len(clave) < p.MIN_PASSWORD_LENGTH:
        raise error(400, "contrasena_min_caracteres", n=p.MIN_PASSWORD_LENGTH)
    if len(clave) > p.PASSWORD_MAX_LENGTH:
        raise error(400, "contrasena_max_caracteres", n=p.PASSWORD_MAX_LENGTH)
    if p.PASSWORD_REQUIRE_UPPERCASE and not re.search(r"[A-Z]", clave):
        raise error(400, "contrasena_sin_mayuscula")
    if p.PASSWORD_REQUIRE_LOWERCASE and not re.search(r"[a-z]", clave):
        raise error(400, "contrasena_sin_minuscula")
    if p.PASSWORD_REQUIRE_DIGIT and not re.search(r"\d", clave):
        raise error(400, "contrasena_sin_numero")
    if p.PASSWORD_REQUIRE_SPECIAL and not re.search(r"[^A-Za-z0-9]", clave):
        raise error(400, "contrasena_sin_especial")
    if p.PASSWORD_BLOCK_COMMON and es_comun(clave):
        raise error(400, "contrasena_comun")
    if p.PASSWORD_BLOCK_PERSONAL and _contiene_datos_personales(clave, datos_personales):
        raise error(400, "contrasena_con_datos_personales")


def _historial(db, user_id: str, n: int) -> list:
    from app.db.session import sin_filtro_de_tenant
    from app.models.seguridad_de_cuentas import PasswordHistory
    if n <= 0:
        return []
    with sin_filtro_de_tenant(db):
        return (db.query(PasswordHistory).filter(PasswordHistory.user_id == user_id)
                .order_by(PasswordHistory.created_at.desc()).limit(n).all())


def validar_nueva(db, user, clave: str, *, org_id: Optional[str] = None, por_admin: bool = False) -> PoliticaDeCuenta:
    """Valida la contraseña nueva de `user` con la política de su empresa. Lanza con código."""
    from app.core.security import verify_password
    p = leer(db, org_id or getattr(user, "organization_id", None))
    comprobar_reglas(clave, p, (getattr(user, "username", None), getattr(user, "email", None),
                                getattr(user, "full_name", None)))
    # Edad mínima: solo el cambio propio (un administrador puede forzarlo).
    cambiada = _aware(getattr(user, "password_changed_at", None))
    if (not por_admin and p.PASSWORD_MIN_AGE_HOURS and cambiada and not getattr(user, "password_must_change", False)
            and _ahora() - cambiada < timedelta(hours=p.PASSWORD_MIN_AGE_HOURS)):
        raise error(400, "contrasena_cambio_demasiado_pronto", horas=p.PASSWORD_MIN_AGE_HOURS)
    anteriores = [h.password_hash for h in _historial(db, user.id, p.PASSWORD_HISTORY_COUNT)]
    if p.PASSWORD_HISTORY_COUNT and getattr(user, "hashed_password", None):
        anteriores.append(user.hashed_password)
    for h in anteriores:
        try:
            if verify_password(clave, h):
                raise error(400, "contrasena_reutilizada", n=p.PASSWORD_HISTORY_COUNT)
        except ValueError:
            continue
    return p


def registrar_cambio(db, user, nuevo_hash: str, *, temporal: bool = False, politica: Optional[PoliticaDeCuenta] = None) -> None:
    """Pone el hash, apunta el historial y las fechas. No confirma."""
    from app.db.session import sin_filtro_de_tenant
    from app.models.seguridad_de_cuentas import PasswordHistory
    p = politica or leer(db, getattr(user, "organization_id", None))
    if getattr(user, "hashed_password", None) and p.PASSWORD_HISTORY_COUNT:
        db.add(PasswordHistory(user_id=user.id, organization_id=user.organization_id,
                               password_hash=user.hashed_password))
        db.flush()
        with sin_filtro_de_tenant(db):
            sobran = (db.query(PasswordHistory).filter(PasswordHistory.user_id == user.id)
                      .order_by(PasswordHistory.created_at.desc()).offset(p.PASSWORD_HISTORY_COUNT).all())
            for fila in sobran:
                db.delete(fila)
    user.hashed_password = nuevo_hash
    user.password_changed_at = _ahora()
    user.locked_until = None
    if temporal:
        user.password_must_change = True
        user.password_temporary_until = _ahora() + timedelta(hours=p.TEMP_PASSWORD_EXPIRY_HOURS)
    else:
        user.password_must_change = False
        user.password_temporary_until = None


def caduca_el(user, p: PoliticaDeCuenta) -> Optional[datetime]:
    if not p.PASSWORD_EXPIRY_DAYS or not getattr(user, "hashed_password", None):
        return None
    base = _aware(getattr(user, "password_changed_at", None)) or _aware(getattr(user, "created_at", None))
    return base + timedelta(days=p.PASSWORD_EXPIRY_DAYS) if base else None


def estado(user, p: PoliticaDeCuenta) -> dict:
    """Marcas para la pantalla: cambio obligatorio, caducidad y aviso."""
    ahora = _ahora()
    fin = caduca_el(user, p)
    caducada = bool(fin and fin <= ahora)
    dias = (fin - ahora).days if fin and not caducada else None
    return {
        "password_change_required": bool(getattr(user, "password_must_change", False)) or caducada,
        "password_expired": caducada,
        "password_expires_at": fin.isoformat() if fin else None,
        "password_expires_in_days": dias,
        "password_expiry_warning": dias is not None and dias <= p.PASSWORD_EXPIRY_WARNING_DAYS,
        "password_temporary": bool(getattr(user, "password_temporary_until", None)),
    }


def temporal_caducada(user) -> bool:
    fin = _aware(getattr(user, "password_temporary_until", None))
    return bool(fin and fin <= _ahora())


def forzar_cambio(db, user) -> None:
    user.password_must_change = True


# ── Portal de clientes ──────────────────────────────────────────────────────
#: Códigos del portal (8 idiomas, `frontend/src/i18n/portal/*.ts`) para cada
#: regla: el portal no tiene los textos del operador.
_CODIGOS_DEL_PORTAL = {
    "contrasena_comun": "portal_contrasena_comun",
    "contrasena_con_datos_personales": "portal_contrasena_con_datos_personales",
}


def validar_del_portal(db, cliente, clave: str, minimo_del_portal: int = 0) -> None:
    """La misma política de la empresa para un usuario del portal (`ErrorConCodigo` del portal).

    Longitud (la mayor entre la de la empresa y la del portal), complejidad,
    comunes y datos personales. Sin historial: el portal no lo guarda.
    """
    from app.core.codigos_de_error import ErrorConCodigo
    from app.core.errores import ErrorDeDominio
    p = leer(db, getattr(cliente, "organization_id", None))
    minimo = max(p.MIN_PASSWORD_LENGTH, int(minimo_del_portal or 0))
    if len(clave or "") < minimo:
        raise ErrorConCodigo("contrasena_corta", n=minimo)
    try:
        comprobar_reglas(clave, p, (getattr(cliente, "email", None), getattr(cliente, "full_name", None)))
    except ErrorDeDominio as e:
        codigo = getattr(e, "code", None) or ""
        raise ErrorConCodigo(_CODIGOS_DEL_PORTAL.get(codigo, "portal_contrasena_no_cumple_politica")) from e
