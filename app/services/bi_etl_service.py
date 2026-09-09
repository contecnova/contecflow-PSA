"""Estado de los conectores ETL de BI, guardado en `AppSetting`.

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
from typing import Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting

logger = logging.getLogger(__name__)

#: Las claves de `AppSetting` donde se guarda el estado de cada conector.
#: Estaban como plantillas en el endpoint y se mueven verbatim.
CLAVE_DE_ESTADO = "bi.etl.connectors_state.{org}"
CLAVE_DE_DATOS_DE_SINCRONIZACION = "bi.etl.sync_data.{connector}.{org}"
CLAVE_DE_REGISTRO_DE_SINCRONIZACION = "bi.etl.sync_log.{connector}.{org}"


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
