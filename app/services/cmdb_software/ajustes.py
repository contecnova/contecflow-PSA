"""Configuración del módulo por empresa (`sw_config`, una fila).

Sin fila, los valores por defecto (todas las fuentes apagadas: el módulo
funciona sin red con importación de ficheros). Las credenciales (clave de NVD,
token de GitHub) se guardan cifradas (`app.core.encryption`) y nunca se
devuelven: la lectura dice solo si están puestas (`nvd_api_key_set`).

Lo edita *Configuración → Service desk → Software y vulnerabilidades*
(`/settings/cmdb-software`, capacidad `software.config`). Cada cambio queda en
la auditoría con antes y después, sin secretos (`metadata.secretos_cambiados`).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.cmdb_software import SoftwareConfig

URLS_POR_DEFECTO = {
    "osv_url": "https://api.osv.dev",
    "nvd_url": "https://services.nvd.nist.gov/rest/json/cves/2.0",
    "ghsa_url": "https://api.github.com",
    "epss_url": "https://api.first.org/data/v1/epss",
    "kev_url": "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
    "eol_url": "https://endoflife.date/api",
}
SECRETOS = ("nvd_api_key", "ghsa_token")
SEVERIDADES = ("critical", "high", "medium", "low")

_BOOLEANOS = ("osv_enabled", "nvd_enabled", "ghsa_enabled", "epss_enabled", "kev_enabled", "eol_enabled", "auto_sync")
_ENTEROS = {"max_queries": (1, 5000), "timeout_seconds": (3, 120), "sla_days_critical": (1, 3650),
            "sla_days_high": (1, 3650), "sla_days_medium": (1, 3650), "sla_days_low": (1, 3650),
            "sla_days_kev": (1, 3650), "exception_max_days": (1, 1825), "eol_warning_days": (0, 3650)}
_TEXTOS = ("osv_url", "nvd_url", "ghsa_url", "epss_url", "kev_url", "eol_url", "licenses_allowed", "licenses_denied")


def fila(db: Session, org: Optional[str], crear: bool = False) -> Optional[SoftwareConfig]:
    q = db.query(SoftwareConfig)
    q = q.filter(SoftwareConfig.organization_id == org) if org else q.filter(SoftwareConfig.organization_id.is_(None))
    c = q.first()
    if c is None and crear:
        c = SoftwareConfig(organization_id=org)
        db.add(c)
        db.flush()
    return c


def _defecto(campo: str):
    col = SoftwareConfig.__table__.c[campo]
    d = col.default.arg if col.default is not None else None
    return d


def leer(db: Session, org: Optional[str]) -> dict:
    """La configuración efectiva, sin secretos."""
    c = fila(db, org)
    salida: dict = {}
    for campo in _BOOLEANOS + tuple(_ENTEROS) + _TEXTOS + ("auto_ticket_min_severity",):
        v = getattr(c, campo) if c is not None else _defecto(campo)
        salida[campo] = v
    for campo, url in URLS_POR_DEFECTO.items():
        salida[f"{campo}_effective"] = salida.get(campo) or url
    for s in SECRETOS:
        salida[f"{s}_set"] = bool(c is not None and getattr(c, s))
    salida["last_sync_at"] = c.last_sync_at.isoformat() if c is not None and c.last_sync_at else None
    salida["last_sync_status"] = c.last_sync_status if c is not None else None
    return salida


def secreto(db: Session, org: Optional[str], campo: str) -> Optional[str]:
    c = fila(db, org)
    if c is None or not getattr(c, campo):
        return None
    from app.core.encryption import decrypt_value
    return decrypt_value(getattr(c, campo))


def sla_dias(conf: dict, severidad: str, kev: bool = False) -> int:
    if kev:
        return int(conf.get("sla_days_kev") or 7)
    clave = f"sla_days_{severidad}" if severidad in SEVERIDADES else "sla_days_low"
    return int(conf.get(clave) or 180)


def guardar(db: Session, org: Optional[str], datos: dict, usuario=None) -> dict:
    """Valida y guarda; audita sin secretos. No confirma (lo hace el endpoint)."""
    from app.core.codigos_de_error import error
    from app.services.audit import audit_log
    antes = leer(db, org)
    c = fila(db, org, crear=True)
    for campo in _BOOLEANOS:
        if campo in datos and datos[campo] is not None:
            setattr(c, campo, bool(datos[campo]))
    for campo, (minimo, maximo) in _ENTEROS.items():
        if campo in datos and datos[campo] is not None:
            try:
                v = int(datos[campo])
            except (TypeError, ValueError):
                raise error(422, "sw_ajuste_no_valido", campo=campo)
            if not minimo <= v <= maximo:
                raise error(422, "sw_ajuste_fuera_de_rango", campo=campo, minimo=minimo, maximo=maximo)
            setattr(c, campo, v)
    for campo in _TEXTOS:
        if campo in datos:
            v = (str(datos[campo]).strip() or None) if datos[campo] is not None else None
            if v and campo.endswith("_url") and not v.lower().startswith(("https://", "http://")):
                raise error(422, "sw_ajuste_no_valido", campo=campo)
            setattr(c, campo, v)
    if "auto_ticket_min_severity" in datos:
        v = datos["auto_ticket_min_severity"] or None
        if v is not None and v not in SEVERIDADES:
            raise error(422, "sw_ajuste_no_valido", campo="auto_ticket_min_severity")
        c.auto_ticket_min_severity = v
    cambiados = []
    from app.core.encryption import encrypt_value
    for s in SECRETOS:
        if s in datos:
            v = datos[s]
            if v is None or v == "":
                continue           # vacío: no cambia
            if v == "__borrar__":
                setattr(c, s, None)
            else:
                setattr(c, s, encrypt_value(str(v)))
            cambiados.append(s)
    if usuario is not None:
        c.updated_by = usuario.id
    db.flush()
    despues = leer(db, org)
    audit_log(db, usuario, "UPDATE", "sw_config", c.id, "CMDB de software",
              old_values=antes, new_values=despues, metadata={"secretos_cambiados": cambiados})
    return despues
