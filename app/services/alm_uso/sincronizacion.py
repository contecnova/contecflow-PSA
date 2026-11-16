"""Sincronización de las fuentes de uso: programada (worker) y manual (pantalla).

Cada lectura deja un `ALMUsoSincronizacion` con lo leído, los avisos (lo que no
se pudo leer sin impedir el resto) y los errores. Una conexión que falla no
para a las demás. Al terminar se registra el pico de las licencias
concurrentes (`alm_asignaciones.registrar_pico`).

Flujo de una lectura:
  proveedor.leer(ctx)  →  conciliacion.conciliar(...)  →  registro y estado.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.alm_uso import ALMUsoConexion, ALMUsoEvidencia, ALMUsoSincronizacion
from app.services.alm_uso import conexiones as cx
from app.services.alm_uso._comun import (
    ahora, ajuste_bool, ajuste_int, aware, cargar_json, exigir_org, volcar_json,
)
from app.services.alm_uso.proveedores import proveedor
from app.services.alm_uso.proveedores.base import ErrorDeConector

logger = logging.getLogger(__name__)


#: Vive en `conexiones` (lo usa también `conexiones.probar`); se re-exporta aquí
#: para no cerrar un ciclo con un import dentro de una función.
contexto_de_lectura = cx.contexto_de_lectura


def iniciar(db: Session, conexion: ALMUsoConexion, origen: str, usuario_id: Optional[str] = None
            ) -> ALMUsoSincronizacion:
    s = ALMUsoSincronizacion(organization_id=conexion.organization_id, conexion_id=conexion.id,
                             proveedor=conexion.proveedor, origen=origen, estado="en_curso", iniciada_at=ahora(),
                             iniciada_por=usuario_id)
    db.add(s)
    conexion.ultimo_estado = "en_curso"
    db.flush()
    return s


def ejecutar(db: Session, sincronizacion_id: str, http=None) -> dict:
    """Lee la fuente y concilia. Siempre deja la sincronización cerrada (ok, parcial o error)."""
    s = db.query(ALMUsoSincronizacion).filter(ALMUsoSincronizacion.id == sincronizacion_id).first()
    if s is None:
        raise ErrorDeDominio(404, {"code": "ALM_USAGE_SYNC_NOT_FOUND", "message": "Sincronización no encontrada"})
    org = exigir_org(s.organization_id)
    c = db.query(ALMUsoConexion).filter(ALMUsoConexion.id == s.conexion_id,
                                        ALMUsoConexion.organization_id == org).one()
    p = proveedor(c.proveedor)
    errores: list = []
    avisos: list = []
    contador: dict = {}
    try:
        ctx = contexto_de_lectura(db, org, p, c, http=http)
        faltan = [k for k in p.obligatorias if not (ctx.credenciales.get(k) or "").strip()] if p.credencial else []
        if faltan:
            raise _FaltanCredenciales(faltan)
        r = p.leer(ctx)
        avisos = list(r.avisos)
        from app.services.alm_uso.conciliacion import conciliar
        contador = conciliar(db, org, p.clave, c, c.fiabilidad or p.fiabilidad, r, ctx.ahora,
                             ajuste_bool(db, "ALM_USAGE_CREATE_ASSETS", org))
        estado = "parcial" if any(a.get("codigo") != "PUSH_SOURCE" for a in avisos) else "ok"
    except ErrorDeConector as e:
        db.rollback()
        errores.append({"codigo": e.codigo, "mensaje": e.mensaje})
        estado = "error"
    except ErrorDeDominio as e:     # p. ej. la URL de la fuente no pasa la protección de salidas
        db.rollback()
        errores.append({"codigo": "URL_NOT_ALLOWED", "mensaje": str(e.detail)[:500]})
        estado = "error"
    except Exception as e:  # el registro tiene que quedar aunque falle algo inesperado
        db.rollback()
        logger.exception("sincronización de uso %s (%s) fallida", c.proveedor, org)
        errores.append({"codigo": "UNEXPECTED", "mensaje": type(e).__name__})
        estado = "error"
    # Tras un rollback los objetos se recargan: se vuelven a leer por id.
    s = db.query(ALMUsoSincronizacion).filter(ALMUsoSincronizacion.id == sincronizacion_id).one()
    c = db.query(ALMUsoConexion).filter(ALMUsoConexion.id == s.conexion_id).one()
    for k in ("leidos", "nuevas", "actualizadas", "sin_titular", "sin_licencia", "dispositivos"):
        setattr(s, k, int(contador.get(k) or 0))
    s.estado = estado
    s.terminada_at = ahora()
    s.errores = volcar_json(errores) if errores else None
    s.avisos = volcar_json(avisos) if avisos else None
    c.ultimo_estado = estado
    c.ultima_sincronizacion_at = s.terminada_at
    c.ultimo_error = "; ".join(f"{e['codigo']}: {e['mensaje']}" for e in errores)[:2000] or None
    if estado != "error":
        registrar_picos(db, org)
    db.commit()
    return cx.sincronizacion_dict(s)


class _FaltanCredenciales(ErrorDeConector):
    def __init__(self, faltan):
        super().__init__("MISSING_CREDENTIALS", f"Faltan credenciales: {', '.join(faltan)}")


def sincronizar_ahora(db: Session, usuario, conexion_id: str) -> dict:
    """Sincronización manual desde la pantalla: se registra ya y se ejecuta en segundo plano."""
    from app.core.segundo_plano import encolar
    from app.services.audit import audit_log
    org = exigir_org(getattr(usuario, "organization_id", None))
    c = cx.conexion_o_404(db, org, conexion_id)
    if c.proveedor == "agente_cmdb":
        raise ErrorDeDominio(409, {"code": "ALM_USAGE_PUSH_SOURCE",
                                   "message": "El agente envía su inventario solo; no se sincroniza a mano"})
    if not c.activa:
        raise ErrorDeDominio(409, {"code": "ALM_USAGE_CONNECTION_INACTIVE", "message": "Activa la conexión primero"})
    if _en_curso(db, c):
        raise ErrorDeDominio(409, {"code": "ALM_USAGE_SYNC_RUNNING", "message": "Ya hay una sincronización en curso"})
    s = iniciar(db, c, "manual", usuario.id)
    audit_log(db, usuario, "SYNC", "alm_uso_conexion", c.id, c.proveedor, new_values={"sincronizacion": s.id})
    db.commit()
    encolar(ejecutar, sincronizacion_id=s.id, _organizacion=org)
    db.expire_all()
    s = db.query(ALMUsoSincronizacion).filter(ALMUsoSincronizacion.id == s.id).one()
    return cx.sincronizacion_dict(s)


def _en_curso(db: Session, c: ALMUsoConexion) -> bool:
    """Una sincronización en curso que empezó dentro del intervalo programado (más antigua: se dio por perdida)."""
    horas = ajuste_int(db, "ALM_USAGE_SYNC_INTERVAL_HOURS", c.organization_id, minimo=1)
    s = db.query(ALMUsoSincronizacion).filter(ALMUsoSincronizacion.conexion_id == c.id,
                                              ALMUsoSincronizacion.estado == "en_curso").order_by(
        ALMUsoSincronizacion.iniciada_at.desc()).first()
    return bool(s and aware(s.iniciada_at) and aware(s.iniciada_at) > ahora() - timedelta(hours=horas))


def sincronizar_pendientes(db: Session, org: str, http=None) -> dict:
    """La pasada del worker en una empresa: cada conexión activa cuya última lectura es más vieja que el intervalo."""
    exigir_org(org)
    horas = ajuste_int(db, "ALM_USAGE_SYNC_INTERVAL_HOURS", org, minimo=1)
    limite = ahora() - timedelta(hours=horas)
    hechas = []
    for c in db.query(ALMUsoConexion).filter(ALMUsoConexion.organization_id == org,
                                             ALMUsoConexion.activa.is_(True)).all():
        if c.proveedor == "agente_cmdb" or _en_curso(db, c):
            continue
        if c.ultima_sincronizacion_at and aware(c.ultima_sincronizacion_at) > limite:
            continue
        s = iniciar(db, c, "programada")
        db.commit()
        hechas.append(ejecutar(db, s.id, http=http))
    purgar_registro(db, org)
    db.commit()
    return {"sincronizadas": len(hechas), "errores": sum(1 for h in hechas if h["estado"] == "error")}


def purgar_registro(db: Session, org: str) -> int:
    dias = ajuste_int(db, "ALM_USAGE_SYNC_LOG_RETENTION_DAYS", org, minimo=1)
    return db.query(ALMUsoSincronizacion).filter(
        ALMUsoSincronizacion.organization_id == org,
        ALMUsoSincronizacion.iniciada_at < ahora() - timedelta(days=dias)).delete(synchronize_session=False)


def registrar_picos(db: Session, org: str) -> int:
    """Pico de cada licencia concurrente: titulares distintos con uso en las últimas 24 h, de todas las fuentes.

    Es un pico diario (personas distintas en un día), no de sesiones simultáneas:
    ninguna de las fuentes integradas da sesiones abiertas a la vez. Se anota con
    `alm_asignaciones.registrar_pico`, que deja en la licencia el máximo de su ventana.
    """
    from app.models.alm import ALMLicense
    from app.services import alm_asignaciones
    desde = ahora() - timedelta(days=1)
    n = 0
    for lic in db.query(ALMLicense).filter(ALMLicense.organization_id == org, ALMLicense.is_active.is_(True),
                                           ALMLicense.metric == "concurrent").all():
        titulares = {(e.titular_tipo, e.user_id or e.titular_externo) for e in db.query(ALMUsoEvidencia).filter(
            ALMUsoEvidencia.organization_id == org, ALMUsoEvidencia.license_id == lic.id,
            ALMUsoEvidencia.ultimo_uso_at >= desde)}
        hay_datos = db.query(ALMUsoEvidencia.id).filter(ALMUsoEvidencia.organization_id == org,
                                                        ALMUsoEvidencia.license_id == lic.id).first() is not None
        if not hay_datos:
            continue
        alm_asignaciones.registrar_pico(db, lic.id, len(titulares), fuente="usage", commit=False)
        n += 1
    return n
