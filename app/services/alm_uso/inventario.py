"""El inventario que envía el agente on-premise de la CMDB en cada check-in.

`POST /service-desk/cmdb/agents/checkin` (autenticado con el token del agente)
admite, además de lo de siempre, `serial_number`, `manufacturer`, `model`,
`primary_user` (correo de quien usa el equipo) y `software`
(`[{name, version, publisher, last_used_at}]`; `software_complete` = la lista
es todo lo instalado, por defecto sí si se envía `software`). Aquí se convierte
en un `Dispositivo` y se concilia como cualquier fuente de inventario (fuente
`agente_cmdb`): activo de ALM por nº de serie o nombre, evidencias de equipo y
de software, instalaciones (`ALMSoftwareInstall`) de lo que tiene licencia.

Solo si la empresa del agente no desactivó la fuente «Agente de inventario».
Cada check-in no deja una fila de sincronización (serían miles al día): la
conexión guarda la fecha y el estado del último envío.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.services.alm_uso._comun import a_fecha_hora, ahora, ajuste_bool
from app.services.alm_uso.proveedores.base import AppInstalada, Dispositivo, ResultadoDeLectura

logger = logging.getLogger(__name__)

#: Software que se acepta como mucho en un check-in (un agente mal configurado no llena la base).
MAX_APPS_POR_CHECKIN = 5000


def dispositivo_de_checkin(payload: dict, externo_id: str) -> Optional[Dispositivo]:
    serie = (payload.get("serial_number") or "").strip() or None
    nombre = (payload.get("hostname") or payload.get("fqdn") or "").strip() or None
    if not serie and not nombre:
        return None
    software = payload.get("software")
    apps = []
    for s in (software or [])[:MAX_APPS_POR_CHECKIN]:
        if isinstance(s, dict) and (s.get("name") or "").strip():
            apps.append(AppInstalada(nombre=str(s["name"]).strip()[:255], version=(s.get("version") or None),
                                     editor=(s.get("publisher") or None),
                                     ultimo_uso=a_fecha_hora(s.get("last_used_at"))))
    completa = payload.get("software_complete")
    return Dispositivo(
        externo_id=externo_id, nombre=nombre, serie=serie, sistema=payload.get("os_type"),
        version_sistema=payload.get("os_version"), fabricante=payload.get("manufacturer"),
        modelo=payload.get("model"), usuario=((payload.get("primary_user") or "").strip().lower() or None),
        ultimo_contacto=ahora(), ip=payload.get("ip_address"), apps=apps,
        apps_leidas=bool(software is not None and (completa is None or completa)
                         and len(software or []) <= MAX_APPS_POR_CHECKIN),
        detalle={"agente": externo_id})


def procesar_checkin(db: Session, organization_id: Optional[str], agente_id: str, payload: dict) -> dict:
    """Concilia el inventario de un check-in. No hace commit (lo hace el endpoint del check-in)."""
    if not organization_id:
        return {"inventario": "sin_empresa"}
    from app.services.alm_uso import conexiones as cx
    from app.services.alm_uso.conciliacion import conciliar
    from app.services.alm_uso.proveedores import proveedor
    d = dispositivo_de_checkin(payload, agente_id)
    if d is None:
        return {"inventario": "sin_identificador"}
    c = cx.conexion_del_agente(db, organization_id)
    if not c.activa:
        return {"inventario": "fuente_desactivada"}
    p = proveedor("agente_cmdb")
    r = ResultadoDeLectura(dispositivos=[d])
    try:
        with db.begin_nested():
            cont = conciliar(db, organization_id, p.clave, c, c.fiabilidad or p.fiabilidad, r, ahora(),
                             ajuste_bool(db, "ALM_USAGE_CREATE_ASSETS", organization_id))
        c.ultimo_estado, c.ultimo_error = "ok", None
    except Exception as exc:
        # El inventario de ALM no puede tumbar el check-in de la CMDB.
        logger.exception("inventario del agente %s no conciliado", agente_id)
        c.ultimo_estado, c.ultimo_error = "error", type(exc).__name__
        cont = {}
    c.ultima_sincronizacion_at = ahora()
    return {"inventario": c.ultimo_estado, "apps": len(d.apps), **{k: cont.get(k) for k in ("nuevas", "actualizadas")}}

