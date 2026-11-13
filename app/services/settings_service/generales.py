"""Ajustes generales de la empresa: valores por defecto, enmascarado de los sensibles y actualizacion.

Parte de `app.services.settings_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import re
from typing import Optional
from sqlalchemy.orm import Session
from app.models.settings import AppSetting
from app.core.config import settings as app_settings

from app.services.settings_service.runtime import invalidate_cache
from app.core.constantes import NOMBRE_DEL_PRODUCTO


DEFAULT_SETTINGS = {
    "company_name": (NOMBRE_DEL_PRODUCTO, "Nombre de la empresa"),
    "currency": (app_settings.DEFAULT_CURRENCY, "Moneda principal"),
    "timezone": (app_settings.DEFAULT_TIMEZONE, "Zona horaria"),
    "language": (app_settings.DEFAULT_LANGUAGE, "Idioma de la interfaz"),
    "work_hours_per_day": (str(app_settings.DEFAULT_WORKING_HOURS_PER_DAY), "Horas laborales por día"),
    "idle_timeout_enabled": ("false", "Cierre de sesión por inactividad (true/false)"),
    "idle_timeout_minutes": ("30", "Minutos de inactividad antes de cerrar sesión"),
}


# ── General settings ──────────────────────────────────────────────────────────

def get_general_settings(db: Session) -> list:
    for key, (value, desc) in DEFAULT_SETTINGS.items():
        exists = db.query(AppSetting).filter(
            AppSetting.key == key, AppSetting.organization_id.is_(None)
        ).first()
        if not exists:
            db.add(AppSetting(key=key, value=value, description=desc, organization_id=None))
    db.commit()
    return db.query(AppSetting).order_by(AppSetting.key).all()


#: Claves cuyo valor no se ensena nunca por la API general (tokens y secretos
#: de e-firma, el anillo de claves JWT, el token de /metrics...).
CLAVE_SENSIBLE = re.compile(r"(token|secret|password|passwd|keyring|credential|_key$|integration_key|client_id)", re.I)
MASCARA = "••••••••"


def es_sensible(key: str) -> bool:
    return bool(CLAVE_SENSIBLE.search(key or ""))


def es_ajuste_general(key: str) -> bool:
    """Los ajustes de la pantalla General: los de fabrica y otros nombres «limpios».

    Las claves con punto o `::` son estado interno de servicios (ITSM, BI,
    seguridad, e-firma): no se leen ni se escriben por la API general salvo
    lectura de administrador.
    """
    if key in DEFAULT_SETTINGS:
        return True
    return bool(key) and "." not in key and "::" not in key and not es_sensible(key)


def ajustes_generales_para(db: Session, es_admin: bool, es_superadmin: bool = False) -> list[dict]:
    """`GET /settings/general` sin fugas.

    Auditoria 2026-11: lo usa todo usuario con sesion (el tiempo de
    inactividad) y devolvia TODAS las filas de `app_settings` en claro: los
    tokens y secretos de DocuSign/Adobe, el anillo de claves JWT y el estado
    interno de otros servicios. Ahora quien no es administrador ve solo los
    ajustes generales, y nadie ve el valor de una clave sensible.

    Revision multitenant 2026-11b: el estado interno GLOBAL (fila sin empresa,
    clave con punto o `::`) es de la plataforma y a veces lleva datos de todas
    las empresas (`predictive.retraining.last_eval` con los ids y metricas de
    cada una; `bi.bookmarks.share_tokens.<empresa>` con el id de cada una en la
    clave). El administrador de una empresa ve el de SU empresa; el global,
    solo un superadmin.
    """
    filas = get_general_settings(db)
    salida = []
    for f in filas:
        if not es_admin and not es_ajuste_general(f.key):
            continue
        if not es_superadmin and f.organization_id is None and not es_ajuste_general(f.key):
            continue
        valor = f.value
        if es_sensible(f.key) and valor:
            valor = MASCARA
        salida.append({"key": f.key, "value": valor, "description": f.description})
    return salida


def update_setting(key: str, value: str, org_id: Optional[str], db: Session) -> AppSetting:
    """Escribe en la fila de la organizacion; sin organizacion, en la global.

    Auditoria 2026-11: si la organizacion no tenia fila propia se actualizaba
    la GLOBAL, la que comparten todas las organizaciones: un administrador de
    una cambiaba el ajuste de todas. Ahora se crea la fila de su organizacion.
    """
    setting = db.query(AppSetting).filter(
        AppSetting.key == key,
        AppSetting.organization_id == org_id if org_id else AppSetting.organization_id.is_(None),
    ).first()
    if not setting:
        global_ = db.query(AppSetting).filter(
            AppSetting.key == key, AppSetting.organization_id.is_(None)).first() if org_id else None
        setting = AppSetting(key=key, value=value, organization_id=org_id,
                             description=global_.description if global_ else None)
        db.add(setting)
    else:
        setting.value = value
    db.commit()
    db.refresh(setting)
    invalidate_cache(key)
    return setting
