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

from app.services.settings_service.runtime import (
    get_runtime_float, get_runtime_int, get_runtime_str, invalidate_cache, monedas)
from app.core.constantes import NOMBRE_DEL_PRODUCTO
from app.services.politica_de_visibilidad import Audiencia


#: clave -> (valor de fábrica, descripción, audiencia que puede leerlo).
#:
#: La audiencia (segunda auditoría 2026-11) dice quién lo recibe por
#: `GET /settings/general` (`ajustes_generales_para`). `SESION` = también el
#: subcontratado: solo lo que la interfaz necesita para pintarse. El cierre por
#: inactividad es de seguridad pero va a `SESION` porque lo aplica el navegador:
#: ocultarlo dejaría al externo sin cierre por inactividad.
DEFAULT_SETTINGS = {
    "company_name": (NOMBRE_DEL_PRODUCTO, "Nombre de la empresa", Audiencia.SESION),
    "currency": (app_settings.DEFAULT_CURRENCY, "Moneda principal", Audiencia.SESION),
    "timezone": (app_settings.DEFAULT_TIMEZONE, "Zona horaria", Audiencia.SESION),
    "language": (app_settings.DEFAULT_LANGUAGE, "Idioma de la interfaz", Audiencia.SESION),
    "work_hours_per_day": (str(app_settings.DEFAULT_WORKING_HOURS_PER_DAY), "Horas laborales por día", Audiencia.SESION),
    "idle_timeout_enabled": ("false", "Cierre de sesión por inactividad (true/false)", Audiencia.SESION),
    "idle_timeout_minutes": ("30", "Minutos de inactividad antes de cerrar sesión", Audiencia.SESION),
}


#: 18-11-2026 (reorganización de Configuración): alias de compatibilidad.
#: La pantalla General guardaba `currency`, `timezone`, `language` y
#: `work_hours_per_day` en filas propias que no leía nadie; lo que usa la
#: aplicación son las claves de ejecución del grupo `locale` (las de
#: `GET /settings/org-defaults`). Ahora hay una sola fuente: leer o escribir el
#: alias por `/settings/general` lee o escribe la clave de ejecución. Las filas
#: viejas las migra y borra la revisión 185.
ALIAS_DE_EJECUCION = {
    "currency": "DEFAULT_CURRENCY",
    "timezone": "DEFAULT_TIMEZONE",
    "language": "DEFAULT_LANGUAGE",
    "work_hours_per_day": "DEFAULT_WORKING_HOURS_PER_DAY",
}
GRUPO_DE_LOS_ALIAS = "locale"


# ── General settings ──────────────────────────────────────────────────────────

def get_general_settings(db: Session) -> list:
    for key, (value, desc, _audiencia) in DEFAULT_SETTINGS.items():
        if key in ALIAS_DE_EJECUCION:
            continue  # 18-11-2026: no se siembran; su valor es el de la clave de ejecución
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


def audiencia_de_ajuste(key: str) -> Audiencia:
    """Quién puede leer `key`: la del catálogo; si no está, por su forma.

    Un ajuste general fuera del catálogo (nombre «limpio» que escribe algún
    servicio) es de la plantilla interna; el estado interno de los servicios
    (clave con punto, `::` o sensible), del administrador.
    """
    if key in DEFAULT_SETTINGS:
        return DEFAULT_SETTINGS[key][2]
    return Audiencia.INTERNA if es_ajuste_general(key) else Audiencia.ADMIN


def ajustes_generales_para(db: Session, audiencia: Audiencia, es_superadmin: bool = False,
                           org_id: Optional[str] = None) -> list[dict]:
    """`GET /settings/general` sin fugas.

    Auditoria 2026-11: lo usa todo usuario con sesion (el tiempo de
    inactividad) y devolvia TODAS las filas de `app_settings` en claro: los
    tokens y secretos de DocuSign/Adobe, el anillo de claves JWT y el estado
    interno de otros servicios. Ahora quien no es administrador ve solo los
    ajustes generales, y nadie ve el valor de una clave sensible.

    Segunda auditoría 2026-11: cada fila llega solo a su `audiencia_de_ajuste`
    o más arriba; el subcontratado (`Audiencia.SESION`) recibe solo las del
    catálogo marcadas para toda sesión.

    Revision multitenant 2026-11b: el estado interno GLOBAL (fila sin empresa,
    clave con punto o `::`) es de la plataforma y a veces lleva datos de todas
    las empresas (`predictive.retraining.last_eval` con los ids y metricas de
    cada una; `bi.bookmarks.share_tokens.<empresa>` con el id de cada una en la
    clave). El administrador de una empresa ve el de SU empresa; el global,
    solo un superadmin.

    Verificación 16-11-2026: al cambiar un ajuste, `update_setting` crea la
    fila de la empresa (para no tocar la global), y aquí salían las dos: la
    pantalla General mostraba «Nombre empresa» dos veces, con el valor de
    fábrica y con el nuevo. Ahora sale el valor efectivo, uno por clave: la
    fila de la empresa sustituye a la global. Con `org_id`, las filas de otras
    empresas no salen nunca (la sesión del superadmin no filtra por empresa).
    """
    filas = get_general_settings(db)
    if org_id is not None:
        filas = [f for f in filas if f.organization_id in (None, org_id)]
    efectivas: dict[str, AppSetting] = {}
    for f in filas:
        actual = efectivas.get(f.key)
        if actual is None or (actual.organization_id is None and f.organization_id is not None):
            efectivas[f.key] = f
    salida = []
    for f in sorted(efectivas.values(), key=lambda x: x.key):
        if f.key in ALIAS_DE_EJECUCION:
            continue  # filas viejas anteriores a la revisión 185: manda la clave de ejecución
        if audiencia_de_ajuste(f.key) > audiencia:
            continue
        if not es_superadmin and f.organization_id is None and not es_ajuste_general(f.key):
            continue
        valor = f.value
        if es_sensible(f.key) and valor:
            valor = MASCARA
        salida.append({"key": f.key, "value": valor, "description": f.description})
    for alias, clave in ALIAS_DE_EJECUCION.items():
        if DEFAULT_SETTINGS[alias][2] > audiencia:
            continue
        valor = get_runtime_str(db, clave, org_id)
        salida.append({"key": alias, "value": None if valor is None else str(valor),
                       "description": DEFAULT_SETTINGS[alias][1]})
    return sorted(salida, key=lambda x: x["key"])


def update_setting(key: str, value: str, org_id: Optional[str], db: Session) -> AppSetting:
    """Escribe en la fila de la organizacion; sin organizacion, en la global.

    Auditoria 2026-11: si la organizacion no tenia fila propia se actualizaba
    la GLOBAL, la que comparten todas las organizaciones: un administrador de
    una cambiaba el ajuste de todas. Ahora se crea la fila de su organizacion.
    """
    if key in ALIAS_DE_EJECUCION:
        # 18-11-2026: una sola fuente (ver ALIAS_DE_EJECUCION). Valida el tipo y
        # deja la entrada de auditoría como la pantalla de Config. dinámica.
        from app.services.settings_service.runtime import set_runtime_value
        hecho = set_runtime_value(db, GRUPO_DE_LOS_ALIAS, ALIAS_DE_EJECUCION[key], value, org_id)
        return AppSetting(key=key, value=hecho["value"], organization_id=org_id,
                          description=DEFAULT_SETTINGS[key][1])
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


#: `GET /settings/org-defaults`: campo -> (ajuste de ejecución, tipo, audiencia).
#: Moneda, zona, idioma y jornada pintan cualquier pantalla; los días de
#: vacaciones (RR. HH.) y el IVA por defecto (facturación) no son del externo.
DEFAULTS_DE_ORGANIZACION = {
    "currency": ("DEFAULT_CURRENCY", str, Audiencia.SESION),
    "timezone": ("DEFAULT_TIMEZONE", str, Audiencia.SESION),
    "language": ("DEFAULT_LANGUAGE", str, Audiencia.SESION),
    "working_hours_per_day": ("DEFAULT_WORKING_HOURS_PER_DAY", float, Audiencia.SESION),
    "weekly_capacity_hours": ("DEFAULT_WEEKLY_CAPACITY_HOURS", float, Audiencia.SESION),
    "vacation_days_per_year": ("DEFAULT_VACATION_DAYS_PER_YEAR", int, Audiencia.INTERNA),
    "tax_rate": ("DEFAULT_TAX_RATE", float, Audiencia.INTERNA),
}


def defaults_de_organizacion(db: Session, org_id: Optional[str], audiencia: Audiencia) -> dict:
    """Los valores por defecto efectivos de la empresa que `audiencia` puede leer."""
    lectores = {str: get_runtime_str, int: get_runtime_int, float: get_runtime_float}
    datos = {campo: lectores[tipo](db, clave, org_id)
             for campo, (clave, tipo, quien) in DEFAULTS_DE_ORGANIZACION.items() if quien <= audiencia}
    datos["currencies"] = monedas(db, org_id)
    # 19-11-2026: umbrales de semáforo por métrica (`app/core/umbrales.py`); no
    # son sensibles y los pinta cualquier pantalla (useUmbrales()).
    from app.core.umbrales import umbrales_de_empresa
    datos["umbrales"] = umbrales_de_empresa(db, org_id)
    return datos
