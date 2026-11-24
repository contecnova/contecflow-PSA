"""La política de cuenta de una empresa: lectura, valores recomendados y validación.

Los valores viven en el registro de ajustes en vivo (grupos `password_policy` y
`account_security`, por empresa, con respaldo en `Settings`). Se escriben solo
por `guardar()` (vía `PUT /security/policy`), que valida, aplica la separación de
funciones y audita; el editor genérico de ajustes rechaza estos grupos.
"""
from __future__ import annotations
import logging

import ipaddress
import re
from dataclasses import asdict, dataclass, fields
from typing import Any, Optional

from app.core.codigos_de_error import error

#: Grupos del registro en vivo que son de esta política.
GRUPOS = ("password_policy", "account_security")

#: Ajustes generales (`app_settings` sin grupo) que también son de esta política.
GENERALES = {"idle_timeout_enabled": "bool", "idle_timeout_minutes": "int"}

#: Capacidades sensibles: quien tenga una necesita MFA si `MFA_REQUIRED_FOR_SENSITIVE`.
CAPACIDADES_SENSIBLES = (
    "org.administrar", "seguridad.administrar", "plataforma.empresas", "personas.config",
    "costes.ver", "costes.config", "datos.plataforma", "interno.cargos", "software.config",
)

METODOS_MFA = ("totp", "webauthn")


@dataclass
class PoliticaDeCuenta:
    # Contraseñas
    MIN_PASSWORD_LENGTH: int = 8
    PASSWORD_MAX_LENGTH: int = 128
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_LOWERCASE: bool = True
    PASSWORD_REQUIRE_DIGIT: bool = True
    PASSWORD_REQUIRE_SPECIAL: bool = True
    PASSWORD_BLOCK_COMMON: bool = True
    PASSWORD_BLOCK_PERSONAL: bool = True
    PASSWORD_HISTORY_COUNT: int = 5
    PASSWORD_MIN_AGE_HOURS: int = 0
    PASSWORD_EXPIRY_DAYS: int = 0
    PASSWORD_EXPIRY_WARNING_DAYS: int = 14
    TEMP_PASSWORD_EXPIRY_HOURS: int = 72
    # Bloqueo
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_ATTEMPT_WINDOW_SECONDS: int = 900
    LOGIN_LOCKOUT_SECONDS: int = 900
    LOGIN_LOCKOUT_NOTIFY_USER: bool = True
    # MFA
    require_mfa: bool = False                      # organizations.require_mfa (toda la empresa)
    MFA_REQUIRED_ROLES: str = "admin"
    MFA_REQUIRED_FOR_SENSITIVE: bool = True
    MFA_ALLOWED_METHODS: str = "totp,webauthn"
    MFA_GRACE_DAYS: int = 7
    MFA_REMEMBER_DEVICE_DAYS: int = 0
    # Sesiones
    idle_timeout_enabled: bool = False
    idle_timeout_minutes: int = 30
    SESSION_MAX_HOURS: int = 0
    SESSION_MAX_CONCURRENT: int = 0
    # Acceso
    ACCESS_IP_ALLOWLIST: str = ""
    ACCESS_HOURS: str = ""
    ACCESS_DAYS: str = "1,2,3,4,5,6,7"
    ACCESS_HOURS_EXEMPT_ROLES: str = "admin"
    ACCESS_BLOCKED_COUNTRIES: str = ""
    # Cuentas, separación de funciones, alertas, recertificación
    ACCOUNT_INACTIVE_DISABLE_DAYS: int = 0
    SECURITY_SOD_TWO_ADMINS: bool = False
    SECURITY_ALERT_FAILED_LOGINS: int = 20
    SECURITY_ALERT_NEW_IP: bool = True
    ACCESS_REVIEW_INTERVAL_DAYS: int = 90

    # ── Lecturas derivadas ──────────────────────────────────────────────────
    def roles_con_mfa(self) -> set[str]:
        return _csv(self.MFA_REQUIRED_ROLES)

    def metodos(self) -> set[str]:
        return _csv(self.MFA_ALLOWED_METHODS) & set(METODOS_MFA) or set(METODOS_MFA)

    def redes(self) -> list:
        return [ipaddress.ip_network(x, strict=False) for x in _lista(self.ACCESS_IP_ALLOWLIST)]

    def paises_bloqueados(self) -> set[str]:
        return {p.upper() for p in _csv(self.ACCESS_BLOCKED_COUNTRIES)}

    def a_dict(self) -> dict:
        return asdict(self)


#: Valor recomendado de cada campo y su fuente (se muestra junto al campo).
RECOMENDADOS: dict[str, tuple[Any, str]] = {
    "MIN_PASSWORD_LENGTH": (15, "NIST SP 800-63B-4 §3.1.1.2 (8 si hay MFA)"),
    "PASSWORD_MAX_LENGTH": (64, "NIST SP 800-63B: admitir al menos 64"),
    "PASSWORD_REQUIRE_UPPERCASE": (False, "NIST SP 800-63B: sin reglas de composición"),
    "PASSWORD_REQUIRE_LOWERCASE": (False, "NIST SP 800-63B: sin reglas de composición"),
    "PASSWORD_REQUIRE_DIGIT": (False, "NIST SP 800-63B: sin reglas de composición"),
    "PASSWORD_REQUIRE_SPECIAL": (False, "NIST SP 800-63B: sin reglas de composición"),
    "PASSWORD_BLOCK_COMMON": (True, "NIST SP 800-63B: lista de contraseñas comprometidas"),
    "PASSWORD_BLOCK_PERSONAL": (True, "NIST SP 800-63B: palabras del contexto"),
    "PASSWORD_HISTORY_COUNT": (5, "CIS / ISO 27001 A.5.17"),
    "PASSWORD_MIN_AGE_HOURS": (0, "CIS: 24 h si hay historial"),
    "PASSWORD_EXPIRY_DAYS": (0, "NIST SP 800-63B: no caducar salvo compromiso"),
    "PASSWORD_EXPIRY_WARNING_DAYS": (14, "Práctica habitual"),
    "TEMP_PASSWORD_EXPIRY_HOURS": (72, "ISO 27001 A.5.17"),
    "LOGIN_MAX_ATTEMPTS": (5, "CIS ≤ 10; NIST ≤ 100"),
    "LOGIN_ATTEMPT_WINDOW_SECONDS": (900, "CIS"),
    "LOGIN_LOCKOUT_SECONDS": (900, "CIS ≥ 15 min"),
    "LOGIN_LOCKOUT_NOTIFY_USER": (True, "ISO 27001 A.8.5"),
    "require_mfa": (True, "ISO 27001 A.8.5, CIS 6.3"),
    "MFA_REQUIRED_ROLES": ("admin", "CIS 6.5: MFA para administradores"),
    "MFA_REQUIRED_FOR_SENSITIVE": (True, "ISO 27001 A.8.2"),
    "MFA_ALLOWED_METHODS": ("totp,webauthn", "NIST AAL2 (webauthn resiste el phishing)"),
    "MFA_GRACE_DAYS": (7, "Práctica habitual"),
    "MFA_REMEMBER_DEVICE_DAYS": (0, "NIST: reautenticar cada 24 h en AAL2"),
    "idle_timeout_enabled": (True, "NIST AAL2: 30 min de inactividad"),
    "idle_timeout_minutes": (30, "NIST AAL2"),
    "SESSION_MAX_HOURS": (24, "NIST AAL2: 24 h"),
    "SESSION_MAX_CONCURRENT": (5, "Práctica habitual"),
    "ACCESS_IP_ALLOWLIST": ("", "Según la red de la empresa"),
    "ACCESS_HOURS": ("", "Según el horario de la empresa"),
    "ACCESS_DAYS": ("1,2,3,4,5,6,7", ""),
    "ACCESS_HOURS_EXEMPT_ROLES": ("admin", "Para no dejar fuera al administrador"),
    "ACCESS_BLOCKED_COUNTRIES": ("", "Solo con país conocido"),
    "ACCOUNT_INACTIVE_DISABLE_DAYS": (90, "CIS 5.3: cuentas inactivas ≤ 45-90 días"),
    "SECURITY_SOD_TWO_ADMINS": (True, "ISO 27001 A.5.3 (con 2 o más administradores)"),
    "SECURITY_ALERT_FAILED_LOGINS": (20, "Práctica habitual"),
    "SECURITY_ALERT_NEW_IP": (True, "ISO 27001 A.8.16"),
    "ACCESS_REVIEW_INTERVAL_DAYS": (90, "ISO 27001 A.5.18 (trimestral para privilegios)"),
}

#: (mínimo, máximo) de los enteros.
RANGOS: dict[str, tuple[int, int]] = {
    "MIN_PASSWORD_LENGTH": (6, 128), "PASSWORD_MAX_LENGTH": (64, 1024), "PASSWORD_HISTORY_COUNT": (0, 24),
    "PASSWORD_MIN_AGE_HOURS": (0, 720), "PASSWORD_EXPIRY_DAYS": (0, 3650), "PASSWORD_EXPIRY_WARNING_DAYS": (0, 90),
    "TEMP_PASSWORD_EXPIRY_HOURS": (1, 720), "LOGIN_MAX_ATTEMPTS": (3, 100),
    "LOGIN_ATTEMPT_WINDOW_SECONDS": (60, 86400), "LOGIN_LOCKOUT_SECONDS": (60, 86400),
    "MFA_GRACE_DAYS": (0, 90), "MFA_REMEMBER_DEVICE_DAYS": (0, 90), "idle_timeout_minutes": (1, 1440),
    "SESSION_MAX_HOURS": (0, 720), "SESSION_MAX_CONCURRENT": (0, 100), "ACCOUNT_INACTIVE_DISABLE_DAYS": (0, 3650),
    "SECURITY_ALERT_FAILED_LOGINS": (0, 10000), "ACCESS_REVIEW_INTERVAL_DAYS": (0, 730),
}

_HORARIO = re.compile(r"^\s*([01]\d|2[0-3]):([0-5]\d)\s*-\s*([01]\d|2[0-3]):([0-5]\d)\s*$")


def _lista(valor: Optional[str]) -> list[str]:
    return [x.strip() for x in str(valor or "").replace(";", ",").replace("\n", ",").split(",") if x.strip()]


def _csv(valor: Optional[str]) -> set[str]:
    return {x.lower() for x in _lista(valor)}


def _grupo_de(clave: str) -> Optional[str]:
    from app.services.settings_service import RUNTIME_FLAG_GROUPS
    for g in GRUPOS:
        if any(k == clave for k, _, _ in RUNTIME_FLAG_GROUPS.get(g, [])):
            return g
    return None


#: Caché por proceso de la política de cada empresa (se lee en cada petición).
_CACHE: dict = {}
_CACHE_S = 30.0


def olvidar_cache() -> None:
    _CACHE.clear()


def leer(db, org_id: Optional[str]) -> PoliticaDeCuenta:
    """La política efectiva de la empresa (empresa → global → entorno). Caché de 30 s."""
    import time
    from app.core.entorno import en_pruebas
    ahora = time.time()
    en_cache = _CACHE.get(org_id)
    if en_cache and en_cache[0] > ahora and not en_pruebas():
        return en_cache[1]
    p = _leer(db, org_id)
    _CACHE[org_id] = (ahora + _CACHE_S, p)
    return p


def _leer(db, org_id: Optional[str]) -> PoliticaDeCuenta:
    from app.services.settings_service import get_runtime_bool, get_runtime_int, get_runtime_str
    p = PoliticaDeCuenta()
    for f in fields(PoliticaDeCuenta):
        if f.name == "require_mfa" or f.name in GENERALES:
            continue
        lector = {bool: get_runtime_bool, int: get_runtime_int}.get(type(getattr(p, f.name)), get_runtime_str)
        try:
            valor = lector(db, f.name, org_id)
        except Exception:
            logging.getLogger(__name__).debug("_leer: excepcion ignorada", exc_info=True)
            valor = None
        if valor is not None:
            setattr(p, f.name, valor)
    if org_id:
        from app.models.mfa import Organization
        from app.db.session import sin_filtro_de_tenant
        with sin_filtro_de_tenant(db):
            org = db.get(Organization, org_id)
        p.require_mfa = bool(getattr(org, "require_mfa", False))
    try:
        # Los dos ajustes generales en UNA consulta (la de la empresa manda sobre
        # la global), igual que `informe_de_cumplimiento._ajuste_general`.
        from app.models.settings import AppSetting
        claves = ("idle_timeout_enabled", "idle_timeout_minutes")
        filas = db.query(AppSetting).filter(
            AppSetting.key.in_(claves),
            (AppSetting.organization_id == org_id) | AppSetting.organization_id.is_(None)).all()
        valor = {}
        for f in sorted(filas, key=lambda f: f.organization_id == org_id):
            valor[f.key] = f.value
        p.idle_timeout_enabled = str(valor.get("idle_timeout_enabled") or "false").lower() == "true"
        p.idle_timeout_minutes = int(valor.get("idle_timeout_minutes") or 30)
    except Exception:
        logging.getLogger(__name__).warning("_leer: excepcion ignorada", exc_info=True)
    return p


def describir(db, org_id: Optional[str]) -> dict:
    """La política con el valor recomendado de cada campo, para la pantalla."""
    p = leer(db, org_id)
    return {
        "values": p.a_dict(),
        "recommended": {k: {"value": v, "source": s} for k, (v, s) in RECOMENDADOS.items()},
        "ranges": {k: list(v) for k, v in RANGOS.items()},
        "sensitive_capabilities": list(CAPACIDADES_SENSIBLES),
        "mfa_methods": list(METODOS_MFA),
    }


def _normalizar(clave: str, valor: Any, tipo: type) -> Any:
    if tipo is bool:
        if isinstance(valor, bool):
            return valor
        return str(valor).strip().lower() in {"1", "true", "yes", "on", "si", "sí"}
    if tipo is int:
        try:
            n = int(valor)
        except (TypeError, ValueError):
            raise error(422, "politica_valor_no_valido", clave=clave)
        lo, hi = RANGOS.get(clave, (0, 10 ** 9))
        if not lo <= n <= hi:
            raise error(422, "politica_fuera_de_rango", clave=clave, min=lo, max=hi)
        return n
    return str(valor or "").strip()


def validar(cambios: dict, actual: PoliticaDeCuenta) -> dict:
    """Normaliza y valida `cambios` (solo claves conocidas). Devuelve lo que cambia."""
    conocidos = {f.name: type(getattr(actual, f.name)) for f in fields(PoliticaDeCuenta)}
    limpio: dict = {}
    for clave, valor in (cambios or {}).items():
        if clave not in conocidos:
            raise error(422, "politica_clave_desconocida", clave=clave)
        nuevo = _normalizar(clave, valor, conocidos[clave])
        if nuevo != getattr(actual, clave):
            limpio[clave] = nuevo
    futura = PoliticaDeCuenta(**{**actual.a_dict(), **limpio})
    if futura.PASSWORD_MAX_LENGTH < futura.MIN_PASSWORD_LENGTH:
        raise error(422, "politica_longitudes_incoherentes")
    if futura.PASSWORD_EXPIRY_DAYS and futura.PASSWORD_EXPIRY_WARNING_DAYS >= futura.PASSWORD_EXPIRY_DAYS:
        raise error(422, "politica_aviso_mayor_que_caducidad")
    for x in _lista(futura.ACCESS_IP_ALLOWLIST):
        try:
            ipaddress.ip_network(x, strict=False)
        except ValueError:
            raise error(422, "politica_ip_no_valida", valor=x)
    if futura.ACCESS_HOURS and not _HORARIO.match(futura.ACCESS_HOURS):
        raise error(422, "politica_horario_no_valido", valor=futura.ACCESS_HOURS)
    dias = _lista(futura.ACCESS_DAYS)
    if not dias or any(d not in {"1", "2", "3", "4", "5", "6", "7"} for d in dias):
        raise error(422, "politica_dias_no_validos", valor=futura.ACCESS_DAYS)
    for pais in _lista(futura.ACCESS_BLOCKED_COUNTRIES):
        if not re.fullmatch(r"[A-Za-z]{2}", pais):
            raise error(422, "politica_pais_no_valido", valor=pais)
    metodos = _csv(futura.MFA_ALLOWED_METHODS)
    if not metodos or metodos - set(METODOS_MFA):
        raise error(422, "politica_metodos_mfa_no_validos", valor=futura.MFA_ALLOWED_METHODS)
    from app.core.capacidades import ROLES
    for rol in _csv(futura.MFA_REQUIRED_ROLES) | _csv(futura.ACCESS_HOURS_EXEMPT_ROLES):
        if rol not in ROLES:
            raise error(422, "politica_rol_desconocido", valor=rol)
    return limpio


def escribir(db, org_id: str, cambios: dict, actor=None, ip: Optional[str] = None) -> None:
    """Aplica `cambios` ya validados en la empresa. No audita (lo hace quien llama)."""
    from app.services.settings_service import set_runtime_value
    from app.services.settings_service.runtime import invalidate_cache
    for clave, valor in cambios.items():
        if clave == "require_mfa":
            from app.models.mfa import Organization
            from app.db.session import sin_filtro_de_tenant
            with sin_filtro_de_tenant(db):
                org = db.get(Organization, org_id)
                if org is not None:
                    org.require_mfa = bool(valor)
            continue
        if clave in GENERALES:
            _escribir_general(db, org_id, clave, valor)
            continue
        grupo = _grupo_de(clave)
        if grupo is None:
            raise error(422, "politica_clave_desconocida", clave=clave)
        set_runtime_value(db, grupo, clave, valor, org_id, actor_id=getattr(actor, "id", None), actor_ip=ip)
    invalidate_cache(None)
    olvidar_cache()
    # La política de bloqueo tiene su propia caché de 60 s.
    from app.services.auth_service import estado_efimero
    estado_efimero._POLITICA_CACHE.update(hasta=0.0, valor=None)
    estado_efimero._POLITICA_POR_EMPRESA.clear()
    db.flush()


def _escribir_general(db, org_id: str, clave: str, valor) -> None:
    """Ajuste general de la empresa (la misma fila que leen el navegador y el informe)."""
    from app.services.settings_service.generales import update_setting
    texto = ("true" if valor else "false") if isinstance(valor, bool) else str(valor)
    update_setting(clave, texto, org_id, db)
