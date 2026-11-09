"""Conectores ETL de BI: la única fuente de su estado, su configuración y su registro.

Revisión 2026-11. Medido antes: había tres listas de conectores en la misma
pantalla —«Conectores ETL» (`/bi/etl`), «Conectores de datos activos»
(`/bi/intelligence/connectors`) y el «Catálogo» de Plataforma BI— y ninguna
coincidía con las otras. El «Sync» de la segunda inventaba el número de
registros; el «Sincronizar» de la primera mandaba la tarea a una cola que
ningún worker escucha; el catálogo era un interruptor que no conectaba nada; y
los «conectores personalizados» guardaban una URL de la que nadie extraía.
Quedan esta lista —los conectores del registro y las fuentes REST que da de
alta cada organización— y un panel.

Los secretos se guardan cifrados y se descifran al usarlos (antes se pasaban
cifrados a la API del proveedor). Nunca vuelven a la pantalla: ésta sólo sabe
si están puestos.

Auditoria 2026-08 (hallazgo 22). Estas dos funciones vivian en
`endpoints/bi_etl.py`, que era el ultimo fichero de la capa API con acceso
directo a base de datos.

El filtro por organizacion **ya estaba y era el correcto**, asi que aqui no hay
guarda nueva: es un movimiento. Y merece decirse por que es correcto, porque no
es el patron habitual del repositorio:

    if organization_id:
        q = q.filter(AppSetting.organization_id == organization_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))

Esto **no** es el condicional defectuoso que aparecio cuatro veces en esta
auditoria —`if org_id: q = q.filter(...)`, que sin organizacion devuelve las
filas de todos—. Aqui la rama `else` filtra por `IS NULL`, que es «el valor
global del despliegue»: los dos caminos acotan, y ninguno deja pasar todo.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.integrations import bi_etl_connectors as etl
from app.models.settings import AppSetting

logger = logging.getLogger(__name__)

#: Estado (activo, última sincronización) y configuración, por organización.
#: Son las claves que ya existían, para no perder lo guardado.
CLAVE_ESTADO = "bi.phase2.connectors"
CLAVE_CONFIG = "bi.phase2.connector_configs"
CLAVE_DE_DATOS_DE_SINCRONIZACION = "bi.etl.sync_data.{connector}.{org}"
CLAVE_DE_REGISTRO_DE_SINCRONIZACION = "bi.etl.sync_log.{connector}.{org}"
PREFIJO_FUENTE = "rest."


class NoEncontrado(LookupError):
    pass


def _guardar(db: Session, clave: str, org: Optional[str], valor: Any, descripcion: str) -> None:
    consulta = db.query(AppSetting).filter(AppSetting.key == clave)
    consulta = consulta.filter(AppSetting.organization_id == org) if org else consulta.filter(AppSetting.organization_id.is_(None))
    fila = consulta.first()
    texto = json.dumps(valor, ensure_ascii=False, separators=(",", ":"))
    if fila:
        fila.value = texto
    else:
        db.add(AppSetting(key=clave, organization_id=org, value=texto, description=descripcion))
    db.commit()


def _estado(db, org):
    return leer_json(db, CLAVE_ESTADO, org, default={}) or {}


def _configs(db, org):
    return leer_json(db, CLAVE_CONFIG, org, default={}) or {}


def _tipo(cid: str, cfg: dict) -> str:
    if cid.startswith(PREFIJO_FUENTE):
        return etl.TIPO_GENERICO
    if cid in etl.SUPPORTED_CONNECTORS:
        return cid
    raise NoEncontrado(cid)


def _secretos(tipo: str) -> set[str]:
    return {c["clave"] for c in etl.ficha(tipo)["campos"] if c["secreto"]}


def _fila(cid: str, tipo: str, estado: dict, cfg: dict) -> dict:
    secretos = _secretos(tipo)
    campos = {c["clave"] for c in etl.ficha(tipo)["campos"]}
    return {
        "connector_id": cid,
        "tipo": tipo,
        "nombre": cfg.get("nombre") or etl.ficha(tipo)["etiqueta"] or cid,
        "personalizado": tipo == etl.TIPO_GENERICO,
        "enabled": bool(estado.get("enabled")),
        "status": estado.get("status") or "disconnected",
        "last_sync_at": estado.get("last_sync_at"),
        "last_records": estado.get("last_records", 0),
        "last_error": estado.get("last_error"),
        "entity": cfg.get("entity") or etl.ficha(tipo)["entidades"][0],
        "config": {k: v for k, v in cfg.items() if k in campos and k not in secretos},
        "secretos_puestos": sorted(k for k in secretos if cfg.get(k)),
        **etl.ficha(tipo),
    }


def listar(db: Session, org: Optional[str]) -> list[dict]:
    estado, configs = _estado(db, org), _configs(db, org)
    ids = list(etl.SUPPORTED_CONNECTORS) + sorted(k for k in configs if k.startswith(PREFIJO_FUENTE))
    return [_fila(cid, _tipo(cid, configs.get(cid, {})), estado.get(cid, {}), configs.get(cid, {})) for cid in ids]


def uno(db: Session, org: Optional[str], cid: str) -> dict:
    configs = _configs(db, org)
    if cid.startswith(PREFIJO_FUENTE) and cid not in configs:
        raise NoEncontrado(cid)
    return _fila(cid, _tipo(cid, configs.get(cid, {})), _estado(db, org).get(cid, {}), configs.get(cid, {}))


def _cifrar(valor: str) -> str:
    from app.core.encryption import encrypt_value
    return encrypt_value(valor)  # si no se puede cifrar, falla: un secreto no se guarda en claro


def _descifrar(cfg: dict, tipo: str) -> dict:
    from app.core.encryption import decrypt_value
    claro = dict(cfg)
    for k in _secretos(tipo):
        if claro.get(k):
            valor = decrypt_value(claro[k])
            if valor is None:
                raise ValueError(f"No se pudo descifrar «{k}»: vuelve a introducirlo")
            claro[k] = valor
    return claro


def configurar(db: Session, org: Optional[str], cid: str, *, enabled: Optional[bool] = None,
               entity: Optional[str] = None, config: Optional[dict] = None) -> dict:
    configs = _configs(db, org)
    if cid.startswith(PREFIJO_FUENTE) and cid not in configs:
        raise NoEncontrado(cid)
    tipo = _tipo(cid, configs.get(cid, {}))
    ficha = etl.ficha(tipo)
    cfg = dict(configs.get(cid, {}))
    if config is not None:
        validas = {c["clave"] for c in ficha["campos"]}
        sobran = set(config) - validas
        if sobran:
            raise ValueError(f"Campos que {tipo} no usa: {', '.join(sorted(sobran))}")
        for k, v in config.items():
            v = "" if v is None else str(v).strip()
            if k in _secretos(tipo):
                if v:                       # vacío = dejar el que hay
                    cfg[k] = _cifrar(v)
            else:
                cfg[k] = v
    if entity is not None:
        if entity not in ficha["entidades"]:
            raise ValueError(f"Entidad «{entity}» no soportada: {', '.join(ficha['entidades'])}")
        cfg["entity"] = entity
    configs[cid] = cfg
    _guardar(db, CLAVE_CONFIG, org, configs, "Conectores ETL de BI — configuración (secretos cifrados)")
    if enabled and etl.ficha(tipo)["falta"]:
        raise ValueError(f"No está instalado: {etl.ficha(tipo)['falta']}")
    if enabled is not None:
        estado = _estado(db, org)
        fila = dict(estado.get(cid, {}))
        fila["enabled"] = bool(enabled)
        if not enabled:
            fila["status"] = "disconnected"
        estado[cid] = fila
        _guardar(db, CLAVE_ESTADO, org, estado, "Conectores ETL de BI — estado")
    return uno(db, org, cid)


def crear_fuente(db: Session, org: Optional[str], nombre: str, config: dict) -> dict:
    nombre = (nombre or "").strip()
    slug = re.sub(r"[^a-z0-9]+", "-", nombre.lower()).strip("-")
    if not slug:
        raise ValueError("Pon un nombre a la fuente")
    cid = PREFIJO_FUENTE + slug
    configs = _configs(db, org)
    if cid in configs:
        raise ValueError(f"Ya hay una fuente «{nombre}»")
    if not (config or {}).get("endpoint_url"):
        raise ValueError("Falta endpoint_url")
    configs[cid] = {"nombre": nombre}
    _guardar(db, CLAVE_CONFIG, org, configs, "Conectores ETL de BI — configuración (secretos cifrados)")
    return configurar(db, org, cid, config=config)


def borrar_fuente(db: Session, org: Optional[str], cid: str) -> None:
    configs = _configs(db, org)
    if not cid.startswith(PREFIJO_FUENTE) or cid not in configs:
        raise NoEncontrado(cid)
    del configs[cid]
    _guardar(db, CLAVE_CONFIG, org, configs, "Conectores ETL de BI — configuración (secretos cifrados)")
    estado = _estado(db, org)
    if estado.pop(cid, None) is not None:
        _guardar(db, CLAVE_ESTADO, org, estado, "Conectores ETL de BI — estado")


def _ajustes(db: Session, org: Optional[str]) -> dict:
    from app.services import settings_service as s
    return {
        "BI_ETL_PAGE_SIZE": s.get_runtime_int(db, "BI_ETL_PAGE_SIZE", org),
        "BI_ETL_HTTP_TIMEOUT_S": s.get_runtime_float(db, "BI_ETL_HTTP_TIMEOUT_S", org),
        "BI_ETL_LOG_MAX_ENTRIES": s.get_runtime_int(db, "BI_ETL_LOG_MAX_ENTRIES", org),
    }


def _preparar(db: Session, org: Optional[str], cid: str):
    configs = _configs(db, org)
    if cid.startswith(PREFIJO_FUENTE) and cid not in configs:
        raise NoEncontrado(cid)
    tipo = _tipo(cid, configs.get(cid, {}))
    return etl.instancia(tipo, cid), configs.get(cid, {}), tipo


def probar(db: Session, org: Optional[str], cid: str) -> dict:
    """Conecta y extrae sin guardar nada. El error vuelve tal cual."""
    conector, cfg, tipo = _preparar(db, org, cid)
    try:
        with etl.ajustes(**_ajustes(db, org)):
            n = conector.probar(_descifrar(cfg, tipo))
        return {"ok": True, "records": n}
    except Exception as exc:  # el motivo es lo que el administrador necesita ver
        return {"ok": False, "error": str(exc)[:500]}


def sincronizar(db: Session, org: Optional[str], cid: str) -> dict:
    """Extrae, guarda y deja constancia; el estado refleja el resultado real."""
    conector, cfg, tipo = _preparar(db, org, cid)
    if conector.falta():
        raise ValueError(f"No está instalado: {conector.falta()}")
    estado = _estado(db, org)
    if not estado.get(cid, {}).get("enabled"):
        raise ValueError("El conector está desactivado")
    try:
        claro = _descifrar(cfg, tipo)
    except ValueError as exc:
        claro, fallo = None, str(exc)
    with etl.ajustes(**_ajustes(db, org)):
        if claro is None:
            resultado = {"ok": False, "records_ingested": 0, "error": fallo}
        else:
            resultado = conector.run_sync(config=claro, organization_id=org, db=db)
    fila = dict(estado.get(cid, {}))
    fila.update(status="connected" if resultado.get("ok") else "error",
                last_sync_at=resultado.get("finished_at"),
                last_records=resultado.get("records_ingested", 0),
                last_error=resultado.get("error"))
    estado = _estado(db, org)       # run_sync confirmó: se relee para no pisar otro cambio
    estado[cid] = fila
    _guardar(db, CLAVE_ESTADO, org, estado, "Conectores ETL de BI — estado")
    return {"connector_id": cid, **resultado}


def registro(db: Session, org: Optional[str], cid: str, limite: int) -> list[dict]:
    uno(db, org, cid)
    clave = CLAVE_DE_REGISTRO_DE_SINCRONIZACION.format(connector=cid, org=org or "global")
    return list(reversed((leer_json(db, clave, org, default=[]) or [])[-limite:]))


def datos(db: Session, org: Optional[str], cid: str) -> dict:
    uno(db, org, cid)
    clave = CLAVE_DE_DATOS_DE_SINCRONIZACION.format(connector=cid, org=org or "global")
    return leer_json(db, clave, org, default={}) or {}


def activos(db: Session) -> list[tuple[Optional[str], str]]:
    """(organización, conector) de todo lo activo, para la sincronización periódica."""
    filas = db.query(AppSetting.organization_id, AppSetting.value).filter(AppSetting.key == CLAVE_ESTADO).all()
    salida = []
    for org, valor in filas:
        try:
            estado = json.loads(valor or "{}")
        except ValueError:
            continue
        salida += [(org, cid) for cid, e in estado.items() if (e or {}).get("enabled")]
    return salida


def leer_json(
    db: Session,
    clave: str,
    organization_id: Optional[str],
    *,
    default=None,
):
    """El valor JSON de un ajuste, o `default` si no hay o no se puede leer.

    Un JSON ilegible se trata como «no hay valor» y no como un error: es el
    comportamiento que ya tenia, y es el correcto para un estado de
    sincronizacion que no debe tumbar el panel. Se anade un aviso al registro,
    que antes no habia: un valor corrupto en la base era invisible.
    """
    consulta = db.query(AppSetting).filter(AppSetting.key == clave)
    if organization_id:
        consulta = consulta.filter(
            AppSetting.organization_id == organization_id)
    else:
        consulta = consulta.filter(AppSetting.organization_id.is_(None))

    fila = consulta.first()
    if not fila or not fila.value:
        return default
    try:
        return json.loads(fila.value)
    except Exception:
        logger.warning(
            "bi_etl: el ajuste %s no contiene JSON valido; se usa el valor por "
            "defecto", clave, exc_info=True)
        return default
