"""Licencias y hardware — fase 4: integración (16-11-2026). Prefijo `/alm/integracion`.

- `/mio/*`: «Mis equipos y licencias», para toda persona con sesión (cada uno lo suyo).
- `/bajas`, `/devoluciones`, `/personas/{id}/previa-baja`: seguimiento de bajas.
- `/kits`, `/propuestas`: kit de alta y su confirmación con un clic.
- `/catalogo/items`, `/peticiones`: ítems del catálogo que piden licencia o equipo.
- `/proyectos/{id}/recursos`: la pestaña «Recursos técnicos» de la ficha de proyecto.
- `/recursos/{tipo}/{id}/tickets`: los tickets de un activo o licencia.

La lógica vive en `app.services.alm_integracion`; aquí solo autorización y forma.
"""
from typing import Optional

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.deps import (
    get_current_user,
    requiere_capacidad,
)
from app.core.errores import ErrorDeDominio
from app.core.periodo import SIN_HORA, Periodo, periodo
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.alm_integracion import autoservicio, bajas, catalogo, kits, proyecto

router = APIRouter()

def _exigir_gestor_de_personas(user: User) -> None:
    """Quien lleva altas y bajas: administración y RRHH (y el PM, que da equipo a su gente).

    Las escrituras de altas y bajas cuelgan de `requiere_capacidad("alm.gestionar")`
    (gestores, en la firma: los barridos de guardas la ven y la sondean) y aquí se
    exige además la capacidad `alm.personas` (admin, PM y RRHH), que deja fuera al
    jefe de equipo. Auditoría 22-11-2026 (M9): antes era una `RequireRole` hecha a
    mano con esos mismos roles; `alm.personas` no tiene módulo, así que la
    audiencia es la misma (403 `capacidad_requerida`)."""
    requiere_capacidad("alm.personas")(current_user=user, db=None)


def _ip(request: Request) -> Optional[str]:
    from app.core.network import extract_client_ip
    return extract_client_ip(request)


# ── Mis equipos y licencias ───────────────────────────────────────────────────

@router.get("/mio", summary="Mis equipos y licencias")
def mio(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return APIResponse.ok(data=autoservicio.mio(db, user))


@router.get("/mio/opciones", summary="Qué puedo pedir (licencias y tipos de equipo del catálogo)")
def opciones(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return APIResponse.ok(data=autoservicio.opciones_de_peticion(db, user))


@router.post("/mio/peticiones", summary="Pedir una licencia o un equipo (va al catálogo)")
def pedir(datos: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return APIResponse.ok(data=catalogo.pedir(db, user, datos))


@router.post("/mio/asignaciones/{aid}/devolver", summary="Devolver un equipo")
def devolver(aid: str, datos: dict = Body(default={}), db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    return APIResponse.ok(data=autoservicio.devolver(db, user, aid, datos.get("motivo")))


@router.post("/mio/asignaciones/{aid}/dejar", summary="Dejar una licencia que ya no necesito")
def dejar(aid: str, datos: dict = Body(default={}), db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    return APIResponse.ok(data=autoservicio.dejar_licencia(db, user, aid, datos.get("motivo")))


@router.post("/mio/asignaciones/{aid}/averia", summary="Comunicar una avería del equipo")
def averia(aid: str, datos: dict = Body(...), db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    return APIResponse.ok(data=autoservicio.averia(db, user, aid, datos.get("descripcion") or "",
                                                   datos.get("urgencia") or "medium"))


@router.get("/mio/actas/{acta_id}", summary="Ver un acta mía")
def ver_acta(acta_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return APIResponse.ok(data=autoservicio.ver_acta(db, user, acta_id))


@router.post("/mio/actas/{acta_id}/firmar", summary="Firmar un acta de entrega o devolución")
def firmar_acta(acta_id: str, request: Request, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    return APIResponse.ok(data=autoservicio.firmar_acta(db, user, acta_id, _ip(request)))


# ── Bajas y devoluciones ──────────────────────────────────────────────────────

@router.get("/bajas", summary="Bajas y su seguimiento")
def listar_bajas(estado: Optional[str] = None, db: Session = Depends(get_db),
                 user: User = Depends(requiere_capacidad("alm.personas"))):
    enforce_abac(db, user, "alm", None, action="read")
    return APIListResponse.ok(items=bajas.listar_bajas(db, estado))


@router.get("/bajas/{baja_id}", summary="Detalle de una baja")
def detalle_baja(baja_id: str, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("alm.personas"))):
    enforce_abac(db, user, "alm", baja_id, action="read")
    return APIResponse.ok(data=bajas.detalle_baja(db, baja_id))


@router.post("/bajas/programar", summary="Programar la baja de una persona (fin de contrato)")
def programar_baja(datos: dict = Body(...), db: Session = Depends(get_db),
                   user: User = Depends(requiere_capacidad("alm.gestionar"))):
    _exigir_gestor_de_personas(user)
    enforce_abac(db, user, "alm", None, action="update")
    return APIResponse.ok(data=bajas.programar_baja(db, datos.get("user_id"), datos.get("fecha"), user,
                                                    notas=datos.get("notas")))


@router.post("/bajas/{baja_id}/anular", summary="Anular una baja programada")
def anular_baja(baja_id: str, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("alm.gestionar"))):
    _exigir_gestor_de_personas(user)
    enforce_abac(db, user, "alm", baja_id, action="update")
    return APIResponse.ok(data=bajas.anular_baja(db, baja_id, user))


@router.get("/personas/{user_id}/previa-baja", summary="Qué pasará con sus licencias y equipos si se da de baja")
def previa_baja(user_id: str, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("alm.administrar"))):
    return APIResponse.ok(data=bajas.previsualizar_persona(db, user_id))


@router.get("/devoluciones", summary="Devoluciones de equipo")
def listar_devoluciones(estado: Optional[str] = None, db: Session = Depends(get_db),
                        user: User = Depends(requiere_capacidad("alm.gestionar"))):
    return APIListResponse.ok(items=bajas.listar_devoluciones(db, estado=estado))


@router.post("/devoluciones/{dev_id}/recibir", summary="Registrar que el equipo ha vuelto (acta de devolución)")
def recibir(dev_id: str, datos: dict = Body(default={}), db: Session = Depends(get_db),
            user: User = Depends(requiere_capacidad("alm.gestionar"))):
    enforce_abac(db, user, "alm", dev_id, action="update")
    return APIResponse.ok(data=bajas.registrar_recepcion(
        db, dev_id, user, condition=datos.get("condition"), checklist=datos.get("checklist"),
        observations=datos.get("observations"), a_reparar=bool(datos.get("a_reparar"))))


@router.post("/devoluciones/{dev_id}/perdida", summary="Dar el equipo por perdido")
def perdida(dev_id: str, datos: dict = Body(...), db: Session = Depends(get_db),
            user: User = Depends(requiere_capacidad("alm.gestionar"))):
    enforce_abac(db, user, "alm", dev_id, action="update")
    return APIResponse.ok(data=bajas.marcar_perdida(db, dev_id, user, datos.get("motivo") or ""))


# ── Kits de alta ──────────────────────────────────────────────────────────────

@router.get("/kits", summary="Kits de alta de la empresa")
def listar_kits(db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("alm.personas"))):
    return APIListResponse.ok(items=kits.listar_kits(db))


@router.post("/kits", summary="Crear un kit de alta")
def crear_kit(datos: dict = Body(...), db: Session = Depends(get_db),
              user: User = Depends(requiere_capacidad("alm.configurar"))):
    enforce_abac(db, user, "alm", None, action="create")
    return APIResponse.ok(data=kits.guardar_kit(db, datos, user))


@router.put("/kits/{kit_id}", summary="Cambiar un kit de alta")
def cambiar_kit(kit_id: str, datos: dict = Body(...), db: Session = Depends(get_db),
                user: User = Depends(requiere_capacidad("alm.configurar"))):
    enforce_abac(db, user, "alm", kit_id, action="update")
    return APIResponse.ok(data=kits.guardar_kit(db, datos, user, kit_id))


@router.delete("/kits/{kit_id}", summary="Retirar un kit de alta")
def borrar_kit(kit_id: str, db: Session = Depends(get_db),
               user: User = Depends(requiere_capacidad("alm.configurar"))):
    enforce_abac(db, user, "alm", kit_id, action="delete")
    return APIResponse.ok(data=kits.borrar_kit(db, kit_id, user))


@router.get("/propuestas", summary="Propuestas de kit (las mías o, para administración y RRHH, todas)")
def listar_propuestas(estado: Optional[str] = None, db: Session = Depends(get_db),
                      user: User = Depends(requiere_capacidad("alm.gestionar"))):
    filas = kits.listar_propuestas(db, user, estado)
    return APIListResponse.ok(items=[f for f in filas if f["puedo_decidir"] or f["responsable_id"] == user.id])


@router.post("/propuestas/{pid}/confirmar", summary="Confirmar el kit con un clic")
def confirmar(pid: str, datos: dict = Body(default={}), db: Session = Depends(get_db),
              user: User = Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=kits.confirmar(db, pid, user, datos.get("claves")))


@router.post("/propuestas/{pid}/descartar", summary="Descartar la propuesta de kit")
def descartar(pid: str, datos: dict = Body(default={}), db: Session = Depends(get_db),
              user: User = Depends(requiere_capacidad("alm.gestionar"))):
    return APIResponse.ok(data=kits.descartar(db, pid, user, datos.get("motivo")))


@router.post("/personas/{user_id}/proponer-kit", summary="Proponer el kit a una persona (p. ej. tras cambiar de puesto)")
def proponer_kit(user_id: str, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("alm.gestionar"))):
    _exigir_gestor_de_personas(user)
    return APIResponse.ok(data=kits.proponer_confirmado(db, user_id, user))


# ── Catálogo ──────────────────────────────────────────────────────────────────

@router.get("/catalogo/items", summary="Ítems del catálogo que piden licencia o equipo")
def items(db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("alm.gestionar"))):
    return APIListResponse.ok(items=catalogo.listar_items(db))


@router.post("/catalogo/items", summary="Marcar un ítem del catálogo como de licencia o equipo")
def guardar_item(datos: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("alm.administrar"))):
    enforce_abac(db, user, "alm", None, action="update")
    return APIResponse.ok(data=catalogo.guardar_item(db, datos, user))


@router.post("/catalogo/items/crear", summary="Crear «Pedir licencia» y «Pedir equipo» en una categoría")
def crear_items(datos: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("alm.administrar"))):
    enforce_abac(db, user, "alm", None, action="create")
    return APIListResponse.ok(items=catalogo.crear_items(db, datos.get("category_id"), datos.get("nombres") or {}, user))


@router.delete("/catalogo/items/{mapeo_id}", summary="Quitar la marca de ALM a un ítem del catálogo")
def borrar_item(mapeo_id: str, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("alm.administrar"))):
    enforce_abac(db, user, "alm", mapeo_id, action="delete")
    return APIResponse.ok(data=catalogo.borrar_item(db, mapeo_id, user))


@router.get("/peticiones", summary="Peticiones de licencia o equipo")
def peticiones(estado: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("alm.gestionar"))):
    return APIListResponse.ok(items=catalogo.listar(db, estado=estado))


@router.post("/peticiones/{pid}/reintentar", summary="Volver a intentar el alta (tras la compra)")
def reintentar(pid: str, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("alm.gestionar"))):
    enforce_abac(db, user, "alm", pid, action="update")
    return APIResponse.ok(data=catalogo.reintentar(db, pid, user))


# ── Ficha de proyecto ─────────────────────────────────────────────────────────

@router.get("/proyectos/{project_id}/recursos", summary="Recursos técnicos del proyecto")
def recursos(project_id: str,
             p: Periodo = Depends(periodo(dias_por_defecto=30, granularidades=SIN_HORA, serie=False)),
             db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Periodo libre (16-11-2026): el coste es por día de calendario (sin hora).
    # `hasta` es ahora exclusivo (contrato común); el último día es `p.fecha_hasta`.
    enforce_abac(db, user, "project", project_id, action="read")
    datos = proyecto.recursos(db, user, project_id, p.fecha_desde, p.fecha_hasta)
    datos["periodo"] = p.a_dict()
    return APIResponse.ok(data=datos)


@router.post("/proyectos/{project_id}/asignar", summary="Asignar una licencia o un equipo al proyecto o a su equipo")
def asignar(project_id: str, datos: dict = Body(...), db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    enforce_abac(db, user, "project", project_id, action="update")
    return APIResponse.ok(data=proyecto.asignar(db, user, project_id, datos))


@router.post("/proyectos/{project_id}/asignaciones/{aid}/liberar", summary="Liberar una asignación del proyecto")
def liberar(project_id: str, aid: str, datos: dict = Body(default={}), db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    enforce_abac(db, user, "project", project_id, action="update")
    return APIResponse.ok(data=proyecto.liberar(db, user, project_id, aid, datos.get("motivo")))


# ── Ticket ↔ recurso ──────────────────────────────────────────────────────────

@router.get("/recursos/{tipo}/{recurso_id}/tickets", summary="Tickets de un activo o una licencia")
def tickets(tipo: str, recurso_id: str, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("alm.gestionar"))):
    from app.services.alm_integracion import _comun
    if tipo not in (_comun.ENLACE_ACTIVO, _comun.ENLACE_LICENCIA):
        raise ErrorDeDominio(422, "almint_tipo_invalido")
    return APIListResponse.ok(items=_comun.tickets_del_recurso(db, tipo, recurso_id))


@router.get("/tickets/{ticket_id}/recurso", summary="El activo o la licencia enlazados a un ticket")
def recurso_del_ticket(ticket_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.alm_integracion import _comun
    from app.services.service_desk.scoping import get_scoped_ticket_or_404
    ticket = get_scoped_ticket_or_404(db, user, ticket_id)
    return APIResponse.ok(data=_comun.recurso_del_ticket(db, ticket))
