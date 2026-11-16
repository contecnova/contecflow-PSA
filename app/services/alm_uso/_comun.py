"""Utilidades compartidas del uso real de licencias y equipos (fase 2)."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Optional

from app.core.errores import ErrorDeDominio

#: Fiabilidades de una fuente, de más a menos. Orden para elegir la mejor evidencia.
FIABILIDADES = ("alta", "media", "baja")
RANGO_DE_FIABILIDAD = {f: i for i, f in enumerate(FIABILIDADES)}

#: Estados de uso de una asignación o licencia.
ESTADOS_DE_USO = ("en_uso", "infrautilizada", "sin_uso", "sin_datos")

TITULAR_PERSONA = "persona"
TITULAR_DISPOSITIVO = "dispositivo"


def cargar_json(v, defecto):
    if v in (None, ""):
        return defecto
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return defecto


def volcar_json(v) -> Optional[str]:
    if v is None:
        return None
    return json.dumps(v, ensure_ascii=False, default=str)


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def aware(v: Optional[datetime]) -> Optional[datetime]:
    """Las fechas de SQLite vuelven sin zona: se leen como UTC (es lo que se guardó)."""
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def a_fecha_hora(v: Any) -> Optional[datetime]:
    """Una fecha de una fuente (ISO 8601, `YYYY-MM-DD`, epoch ms) a `datetime` con zona UTC. Ilegible: None."""
    if v in (None, "", "Never", "null"):
        return None
    if isinstance(v, datetime):
        return aware(v)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(float(v) / (1000 if v > 10 ** 11 else 1), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    texto = str(v).strip()
    if not texto:
        return None
    try:
        if len(texto) == 10:
            d = date.fromisoformat(texto)
            return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        return aware(datetime.fromisoformat(texto.replace("Z", "+00:00")))
    except ValueError:
        return None


def max_fecha(*valores: Optional[datetime]) -> Optional[datetime]:
    vistos = [aware(v) for v in valores if v is not None]
    return max(vistos) if vistos else None


def normalizar(texto: Optional[str]) -> str:
    """Clave comparable de un nombre de producto: sin tildes, minúsculas, sin signos ni versión suelta."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[®™©]", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def exigir_org(org_id: Optional[str]) -> str:
    """Todo el módulo trabaja dentro de UNA empresa: sin ella no se hace nada."""
    if not org_id:
        raise ErrorDeDominio(400, {"code": "ALM_USAGE_NO_ORGANIZATION",
                                   "message": "Esta operación necesita una empresa"})
    return org_id


@dataclass(frozen=True)
class Umbrales:
    dias_sin_uso: int
    dias_infrautilizada: int
    dias_activos_minimos: int
    dias_datos_antiguos: int
    gracia_dias: int
    conservar_dias: int


def umbrales(db, org_id: Optional[str]) -> Umbrales:
    """Los umbrales de la empresa (ajustes en caliente del grupo `licencias_uso`)."""
    from app.services import settings_service as s
    sin_uso = int(s.get_runtime_int(db, "ALM_USAGE_IDLE_DAYS", org_id) or 60)
    infra = int(s.get_runtime_int(db, "ALM_USAGE_UNDERUSED_DAYS", org_id) or 30)
    return Umbrales(
        dias_sin_uso=max(1, sin_uso),
        dias_infrautilizada=max(0, min(infra, sin_uso)),
        dias_activos_minimos=max(0, int(s.get_runtime_int(db, "ALM_USAGE_MIN_ACTIVE_DAYS", org_id) or 0)),
        dias_datos_antiguos=max(1, int(s.get_runtime_int(db, "ALM_USAGE_STALE_DATA_DAYS", org_id) or 7)),
        gracia_dias=max(0, int(s.get_runtime_int(db, "ALM_RECLAIM_GRACE_DAYS", org_id) or 0)),
        conservar_dias=max(1, int(s.get_runtime_int(db, "ALM_RECLAIM_KEEP_DAYS", org_id) or 90)),
    )


def ajuste_int(db, clave: str, org_id: Optional[str], minimo: int = 0) -> int:
    from app.services import settings_service as s
    return max(minimo, int(s.get_runtime_int(db, clave, org_id) or 0))


def ajuste_bool(db, clave: str, org_id: Optional[str]) -> bool:
    from app.services import settings_service as s
    return bool(s.get_runtime_bool(db, clave, org_id))


def moneda_de_empresa(db, org_id: Optional[str]) -> str:
    from app.services.formato_regional import codigo_de_moneda
    return codigo_de_moneda(db, org_id)


def coste_unitario_anual(lic) -> Optional[float]:
    """Coste anual por puesto de una licencia: `annual_cost / total_seats` (o el total si no hay puestos)."""
    if lic is None or lic.annual_cost in (None, 0):
        return None
    puestos = lic.total_seats or 0
    return round(float(lic.annual_cost) / puestos, 2) if puestos > 0 else float(lic.annual_cost)


def moneda_de_licencia(db, lic, org_id: Optional[str]) -> str:
    contrato = getattr(lic, "contract", None)
    return ((contrato.currency if contrato is not None else None) or moneda_de_empresa(db, org_id)).upper()


def nombres_de_usuarios(db, org_id: str, ids) -> dict:
    """{user_id: nombre} de personas de la empresa (para pintar listas sin una consulta por fila)."""
    from app.db.session import _miembros_de
    from app.models.user import User
    ids = [i for i in set(ids or []) if i]
    if not ids:
        return {}
    return dict(db.query(User.id, User.full_name).filter(User.id.in_(ids), _miembros_de(User, org_id)).all())


def nombres_de_activos(db, org_id: str, ids) -> dict:
    from app.models.alm import ALMAsset
    ids = [i for i in set(ids or []) if i]
    if not ids:
        return {}
    return dict(db.query(ALMAsset.id, ALMAsset.name).filter(ALMAsset.id.in_(ids), ALMAsset.organization_id == org_id).all())


def nombres_de_licencias(db, org_id: str, ids) -> dict:
    from app.models.alm import ALMLicense
    ids = [i for i in set(ids or []) if i]
    if not ids:
        return {}
    return dict(db.query(ALMLicense.id, ALMLicense.name).filter(ALMLicense.id.in_(ids),
                                                                ALMLicense.organization_id == org_id).all())


def con_nombres(db, org_id: str, filas: list, user_key: str = "user_id", asset_key: str = "asset_id",
                license_key: str = "license_id") -> list:
    """Añade `persona`, `equipo` y `licencia` (nombres) a cada fila."""
    us = nombres_de_usuarios(db, org_id, [f.get(user_key) for f in filas])
    ac = nombres_de_activos(db, org_id, [f.get(asset_key) for f in filas])
    li = nombres_de_licencias(db, org_id, [f.get(license_key) for f in filas])
    for f in filas:
        f.setdefault("persona", us.get(f.get(user_key)))
        f.setdefault("equipo", ac.get(f.get(asset_key)))
        f.setdefault("licencia", li.get(f.get(license_key)))
    return filas
