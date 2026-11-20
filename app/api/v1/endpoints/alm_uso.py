"""Licencias y hardware — fase 2: uso real (16-11-2026). Prefijo `/alm/uso`.

Permisos (mínimo privilegio):
- Fuentes, credenciales, mapeos y sincronizaciones: administrador de la empresa.
- Uso, recuperación, ajuste de nivel, cumplimiento y software no controlado:
  roles de gestión (admin, pm, team_lead, hr): son datos de actividad de personas.
- `recuperaciones/mias` y «la sigo necesitando»: la propia persona titular.
Toda operación se acota a la empresa de quien llama (`organization_id`).
"""
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.api.descargas import respuesta_de_descarga
from app.core.deps import get_current_user, requiere_capacidad
from app.core.responses import APIResponse
from app.db.session import get_db
from app.models.user import UserRole
from app.services import alm_uso
from app.services.alm_uso import (
    ajuste, conexiones, cumplimiento, mapeos, no_controlado, recuperacion, sincronizacion,
)

router = APIRouter()

_GESTORES = {r.value for r in (UserRole.admin, UserRole.pm, UserRole.team_lead, UserRole.hr)}


def _org(u) -> Optional[str]:
    return u.organization_id


# ── Panel y uso ───────────────────────────────────────────────────────────────

@router.get("/panel", summary="KPIs del uso real de licencias y equipos")
def panel(db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=alm_uso.panel(db, _org(u)))


@router.get("/licencias", summary="Uso de cada licencia (resumen y asignaciones)")
def uso_licencias(con_asignaciones: bool = False, db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=alm_uso.uso_de_licencias(db, _org(u), con_asignaciones=con_asignaciones))


@router.get("/licencias/{license_id}", summary="Uso de una licencia con el detalle de cada asignación")
def uso_licencia(license_id: str, db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=alm_uso.uso_de_licencia(db, license_id, _org(u)))


@router.get("/asignaciones/{assignment_id}", summary="Uso de una asignación (evidencias por fuente)")
def uso_asignacion(assignment_id: str, db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=alm_uso.uso_de_asignacion(db, assignment_id, _org(u)))


@router.get("/equipos", summary="Último contacto y usuario de cada equipo según el inventario")
def uso_equipos(db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=alm_uso.uso_de_equipos(db, _org(u)))


# ── Fuentes (conexiones) ──────────────────────────────────────────────────────

@router.get("/conexiones", summary="Fuentes de uso: estado, credenciales configuradas y última sincronización")
def listar_conexiones(db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.conexiones"))):
    return APIResponse.ok(data=conexiones.listar(db, _org(u)))


@router.put("/conexiones/{clave}", summary="Configurar una fuente (activa, fiabilidad, opciones, credenciales)")
def guardar_conexion(clave: str, datos: dict = Body(...), db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.conexiones"))):
    return APIResponse.ok(data=conexiones.guardar(db, u, clave, datos))


@router.post("/conexiones/{clave}/probar", summary="Probar credenciales y permisos de una fuente")
def probar_conexion(clave: str, db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.conexiones"))):
    return APIResponse.ok(data=conexiones.probar(db, u, clave))


@router.post("/conexiones/{conexion_id}/sincronizar", summary="Sincronizar una fuente ahora")
def sincronizar(conexion_id: str, db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.conexiones"))):
    return APIResponse.ok(data=sincronizacion.sincronizar_ahora(db, u, conexion_id))


@router.get("/sincronizaciones", summary="Registro de sincronizaciones (con errores y avisos)")
def sincronizaciones(conexion_id: Optional[str] = None, limite: int = Query(50, ge=1, le=500),
                     db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.conexiones"))):
    return APIResponse.ok(data=conexiones.historial(db, _org(u), conexion_id, limite))


@router.get("/mapeos", summary="Productos de las fuentes y su licencia de ALM")
def listar_mapeos(solo_sin_licencia: bool = False, db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.conexiones"))):
    return APIResponse.ok(data=mapeos.productos(db, _org(u), solo_sin_licencia))


@router.put("/mapeos", summary="Mapear un producto de una fuente a una licencia (o ignorarlo)")
def guardar_mapeo(datos: dict = Body(...), db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.conexiones"))):
    return APIResponse.ok(data=mapeos.guardar(db, u, str(datos.get("fuente") or ""), str(datos.get("producto") or ""),
                                              datos.get("license_id") or None, bool(datos.get("ignorar"))))


# ── Recuperación ──────────────────────────────────────────────────────────────

@router.get("/recuperaciones", summary="Procesos de recuperación (abiertas, liberadas…)")
def listar_recuperaciones(estado: Optional[str] = None, db: Session = Depends(get_db),
                          u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=recuperacion.listar(db, _org(u), estado))


@router.get("/recuperaciones/simulacion", summary="Qué haría hoy la recuperación con las políticas publicadas")
def simular_recuperacion(db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=recuperacion.previsualizar(db, _org(u)))


@router.get("/recuperaciones/mias", summary="Mis licencias en recuperación")
def mis_recuperaciones(db: Session = Depends(get_db), u=Depends(get_current_user)):
    return APIResponse.ok(data=recuperacion.listar(db, _org(u), "abiertas", user_id=u.id))


@router.post("/recuperaciones/{rec_id}/conservar", summary="La sigo necesitando")
def conservar(rec_id: str, datos: dict = Body(...), db: Session = Depends(get_db), u=Depends(get_current_user)):
    es_gestor = bool(u.is_superadmin) or str(getattr(u.role, "value", u.role)) in _GESTORES
    return APIResponse.ok(data=recuperacion.conservar(db, u, rec_id, datos.get("motivo"), es_gestor))


@router.post("/recuperaciones/{rec_id}/decidir", summary="Aprobar (liberar) o rechazar una recuperación pendiente")
def decidir_recuperacion(rec_id: str, datos: dict = Body(...), db: Session = Depends(get_db),
                         u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=recuperacion.decidir(db, u, rec_id, bool(datos.get("aprobar")), datos.get("nota")))


@router.post("/recuperaciones/{rec_id}/liberar", summary="Liberar ya la licencia")
def liberar_recuperacion(rec_id: str, datos: dict = Body(default={}), db: Session = Depends(get_db),
                         u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=recuperacion.liberar_ahora(db, u, rec_id, (datos or {}).get("nota")))


@router.post("/recuperaciones/{rec_id}/cancelar", summary="Cancelar una recuperación")
def cancelar_recuperacion(rec_id: str, datos: dict = Body(default={}), db: Session = Depends(get_db),
                          u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=recuperacion.cancelar(db, u, rec_id, (datos or {}).get("motivo")))


# ── Ajuste de nivel ───────────────────────────────────────────────────────────

@router.get("/ajuste/propuestas", summary="Propuestas de bajar de nivel con su ahorro")
def propuestas(db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=ajuste.propuestas(db, _org(u)))


@router.post("/ajuste/decidir", summary="Aceptar o descartar una propuesta de ajuste")
def decidir_ajuste(datos: dict = Body(...), db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=ajuste.decidir(db, u, str(datos.get("nivel_id") or ""),
                                              str(datos.get("assignment_id") or ""), bool(datos.get("aceptar")),
                                              datos.get("motivo")))


@router.get("/ajuste/reglas", summary="Reglas de ajuste de nivel y sugerencias por nivel de licencia")
def reglas(db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data={"reglas": ajuste.reglas(db, _org(u)), "sugerencias": ajuste.sugerencias(db, _org(u))})


@router.post("/ajuste/reglas", summary="Crear una regla de ajuste de nivel")
def crear_regla(datos: dict = Body(...), db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=ajuste.guardar_regla(db, u, datos))


@router.put("/ajuste/reglas/{regla_id}", summary="Cambiar una regla de ajuste de nivel")
def editar_regla(regla_id: str, datos: dict = Body(...), db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=ajuste.guardar_regla(db, u, datos, regla_id))


@router.delete("/ajuste/reglas/{regla_id}", summary="Borrar una regla de ajuste de nivel")
def borrar_regla(regla_id: str, db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    ajuste.borrar_regla(db, u, regla_id)
    return APIResponse.ok(data={"ok": True})


# ── Cumplimiento ──────────────────────────────────────────────────────────────

@router.get("/cumplimiento", summary="Posición efectiva de licencias (derechos frente a consumo)")
def posicion(db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=cumplimiento.posicion(db, _org(u)))


@router.get("/cumplimiento/exportar", summary="Posición de licencias en CSV o XLSX para la auditoría del fabricante")
def exportar(formato: str = "csv", producto: Optional[str] = None, db: Session = Depends(get_db),
             u=Depends(requiere_capacidad("alm.gestionar"))):
    return respuesta_de_descarga(cumplimiento.exportar_con_auditoria(db, u, _org(u), formato, producto))


# ── Software no controlado ────────────────────────────────────────────────────

@router.get("/no-controlado", summary="Software detectado fuera de ALM")
def no_controlados(estado: Optional[str] = "nuevo", db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=no_controlado.listar(db, _org(u), estado or None))


@router.post("/no-controlado/detectar", summary="Volver a analizar los gastos de software")
def detectar(db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    n = no_controlado.detectar_ahora(db, _org(u))
    return APIResponse.ok(data={"candidatos": n})


@router.post("/no-controlado/{cid}/alta", summary="Dar de alta en ALM con la propuesta")
def alta(cid: str, datos: dict = Body(default={}), db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=no_controlado.dar_de_alta(db, u, cid, datos or {}))


@router.post("/no-controlado/{cid}/descartar", summary="Descartar un candidato (no volverá a proponerse)")
def descartar(cid: str, datos: dict = Body(default={}), db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=no_controlado.descartar(db, u, cid, (datos or {}).get("motivo")))


@router.post("/no-controlado/{cid}/reabrir", summary="Volver a proponer un candidato descartado")
def reabrir(cid: str, db: Session = Depends(get_db), u=Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=no_controlado.reabrir(db, u, cid))
