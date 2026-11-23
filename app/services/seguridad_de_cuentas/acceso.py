"""Restricciones de acceso por empresa: IP/CIDR permitidas, horario y país.

El superadmin de plataforma queda fuera (no trabaja en ninguna empresa; es la vía
de recuperación). El país solo se conoce con la cabecera de un proxy de
confianza o con `GEOIP_LOOKUP_ENABLED` (apagado por defecto): sin país, el bloqueo
por país no actúa.
"""
from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from typing import Optional

from app.core.codigos_de_error import error
from app.services.seguridad_de_cuentas.politica import Politica, _csv, _lista


def ip_permitida(ip: Optional[str], p: Politica) -> bool:
    redes = p.redes()
    if not redes:
        return True
    try:
        dir_ = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return False
    return any(dir_ in r for r in redes)


def _zona(db, org_id) -> str:
    try:
        from app.services.settings_service.por_empresa import zona_de_empresa
        return zona_de_empresa(db, org_id) or "UTC"
    except Exception:
        return "UTC"


def dentro_de_horario(db, org_id, rol: str, p: Politica, ahora: Optional[datetime] = None) -> bool:
    if not p.ACCESS_HOURS or rol in _csv(p.ACCESS_HOURS_EXEMPT_ROLES):
        return True
    from zoneinfo import ZoneInfo
    try:
        local = (ahora or datetime.now(timezone.utc)).astimezone(ZoneInfo(_zona(db, org_id)))
    except Exception:
        local = (ahora or datetime.now(timezone.utc))
    if str(local.isoweekday()) not in set(_lista(p.ACCESS_DAYS)):
        return False
    ini, fin = [x.strip() for x in p.ACCESS_HOURS.split("-")]
    h = local.strftime("%H:%M")
    return ini <= h < fin if ini <= fin else (h >= ini or h < fin)


def pais_de_la_peticion(request) -> Optional[str]:
    """País por la cabecera de un proxy de confianza (sin llamar a nadie)."""
    if request is None:
        return None
    from app.core.config import settings
    if not getattr(settings, "TRUST_PROXY_HEADERS", False):
        return None
    for cabecera in ("cf-ipcountry", "x-country-code", "x-appengine-country"):
        v = (request.headers.get(cabecera) or "").strip().upper()
        if len(v) == 2 and v.isalpha():
            return v
    return None


def comprobar(db, user, org_id: Optional[str], ip: Optional[str], request=None, pais: Optional[str] = None,
              p: Optional[Politica] = None) -> None:
    """403 con código si la empresa no deja entrar desde aquí o ahora."""
    if getattr(user, "is_superadmin", False) or not org_id:
        return
    from app.services.seguridad_de_cuentas.politica import leer
    p = p or leer(db, org_id)
    if not ip_permitida(ip, p):
        raise error(403, "acceso_ip_no_permitida")
    rol = getattr(getattr(user, "role", None), "value", getattr(user, "role", "")) or ""
    if not dentro_de_horario(db, org_id, rol, p):
        raise error(403, "acceso_fuera_de_horario", horario=p.ACCESS_HOURS)
    bloqueados = p.paises_bloqueados()
    if bloqueados:
        pais = (pais or pais_de_la_peticion(request) or "").upper()
        if pais and pais in bloqueados:
            raise error(403, "acceso_pais_bloqueado", pais=pais)
