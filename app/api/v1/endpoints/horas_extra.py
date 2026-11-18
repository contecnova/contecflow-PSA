"""Horas extra y trabajo fuera de horario (`/overtime`, 18-11-2026, rev. 184).

La lógica vive en `app/services/horas_extra/`; aquí solo guardas y forma.

Guardas:
  · configuración: leer, cualquiera que trabaja (la pantalla la necesita para
    pedir); escribir, administración o RRHH;
  · presupuestos: leer, responsables; escribir, administración o RRHH;
  · pedir, vista previa, las mías, cancelar y editar las suyas: quien trabaja
    (también el subcontratado); pedir para otro, su responsable (o RRHH/admin);
  · lista de gestión, resumen y sin autorizar: responsables, acotado a lo que
    ven (`consultas.acotar`); detalle: quien lo ve o lo tiene que aprobar;
  · revisar: quien aprueba (nunca sobre lo suyo ni lo que pidió para otro);
  · liquidar, nómina y regularizar un periodo: administración o RRHH.
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.codigos_de_error import error as error_con_codigo
from app.core.deps import require_admin_or_hr, require_any_manager, require_worker
from app.core.responses import APIResponse
from app.db.session import get_db
from app.models.user import User
from app.schemas.horas_extra import (ConfigIn, LiquidarIn, NotaIn, PeticionDeHorasExtraIn, PresupuestoIn,
                                     RegularizarIn, RevisarIn, VistaPreviaIn)
from app.services.horas_extra import calculo, config, consultas, control, solicitudes

router = APIRouter()


def _rango(desde: Optional[date], hasta: Optional[date]) -> tuple[date, date]:
    hoy = timeutil.today()
    hasta = hasta or hoy
    desde = desde or hasta.replace(day=1)
    if hasta < desde or (hasta - desde).days > 400:
        raise error_con_codigo(422, "rango_de_1_a_400_dias")
    return desde, hasta


def _ficha(db, usuario, p) -> dict:
    return consultas.serializar(db, usuario, [p], consultas._reales(db, [p]))[0]


# ── Configuración y presupuestos ─────────────────────────────────────────────

@router.get("/config", summary="Configuración de horas extra de la empresa")
def leer_config(db: Session = Depends(get_db), current_user: User = Depends(require_worker)):
    return APIResponse.ok(data=config.para_pantalla(db, current_user))


@router.put("/config", summary="Guardar la configuración de horas extra")
def guardar_config(body: ConfigIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_hr)):
    return APIResponse.ok(data=config.guardar(db, current_user, body.model_dump()))


@router.get("/budgets", summary="Presupuestos de horas extra con su consumo")
def listar_presupuestos(fecha: Optional[date] = None, db: Session = Depends(get_db),
                        current_user: User = Depends(require_any_manager)):
    f = fecha or timeutil.today()
    from app.models.project import Project
    nombres = dict(db.query(Project.id, Project.name).all())
    return APIResponse.ok(data=[config.presupuesto_dict(p, calculo.consumo_de(db, p, f),
                                                        nombres.get(p.valor) if p.ambito == "proyecto" else None)
                                for p in config.presupuestos(db)])


@router.post("/budgets", summary="Crear un presupuesto de horas extra")
def crear_presupuesto(body: PresupuestoIn, db: Session = Depends(get_db),
                      current_user: User = Depends(require_admin_or_hr)):
    return APIResponse.ok(data=config.presupuesto_dict(config.guardar_presupuesto(db, current_user, body.model_dump())))


@router.put("/budgets/{presupuesto_id}", summary="Cambiar un presupuesto de horas extra")
def cambiar_presupuesto(presupuesto_id: str, body: PresupuestoIn, db: Session = Depends(get_db),
                        current_user: User = Depends(require_admin_or_hr)):
    p = config.guardar_presupuesto(db, current_user, body.model_dump(), presupuesto_id)
    return APIResponse.ok(data=config.presupuesto_dict(p))


@router.delete("/budgets/{presupuesto_id}", summary="Borrar un presupuesto de horas extra")
def borrar_presupuesto(presupuesto_id: str, db: Session = Depends(get_db),
                       current_user: User = Depends(require_admin_or_hr)):
    config.borrar_presupuesto(db, current_user, presupuesto_id)
    return APIResponse.ok(data={"id": presupuesto_id})


# ── Pedir ────────────────────────────────────────────────────────────────────

@router.post("/preview", summary="Vista previa de una petición de horas extra (no guarda)")
def vista_previa(body: VistaPreviaIn, db: Session = Depends(get_db), current_user: User = Depends(require_worker)):
    return APIResponse.ok(data=solicitudes.vista_previa(db, current_user, body.model_dump()))


@router.post("", summary="Pedir horas extra (autorización previa)")
def pedir(body: PeticionDeHorasExtraIn, db: Session = Depends(get_db), current_user: User = Depends(require_worker)):
    p = solicitudes.solicitar(db, current_user, body.model_dump())
    return APIResponse.ok(data=_ficha(db, current_user, p))


@router.get("/mine", summary="Mis horas extra (y las que pedí para otros)")
def mias(desde: Optional[date] = None, hasta: Optional[date] = None, estado: Optional[str] = None,
         db: Session = Depends(get_db), current_user: User = Depends(require_worker)):
    return APIResponse.ok(data=consultas.mias(db, current_user, {"desde": desde, "hasta": hasta, "estado": estado}))


@router.get("/inbox", summary="Horas extra que me toca decidir")
def bandeja(db: Session = Depends(get_db), current_user: User = Depends(require_worker)):
    return APIResponse.ok(data=consultas.bandeja(db, current_user))


@router.get("/check", summary="Qué pasaría al imputar esas horas ese día (control de horas extra)")
def comprobar(fecha: date, horas: float = Query(0, ge=0, le=24), imputation_id: Optional[str] = None,
              db: Session = Depends(get_db), current_user: User = Depends(require_worker)):
    return APIResponse.ok(data=control.comprobar(db, current_user.id, fecha, horas, imputation_id))


@router.get("/summary", summary="Resumen por persona, equipo, departamento o proyecto frente a los límites")
def resumen(desde: Optional[date] = None, hasta: Optional[date] = None, agrupar: str = "persona",
            db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    d, h = _rango(desde, hasta)
    return APIResponse.ok(data=consultas.resumen(db, current_user, d, h, agrupar))


@router.get("/unauthorized", summary="Días con horas imputadas fuera de horario sin autorizar")
def sin_autorizar(desde: Optional[date] = None, hasta: Optional[date] = None, user_id: Optional[str] = None,
                  db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    d, h = _rango(desde, hasta)
    return APIResponse.ok(data=consultas.sin_autorizar(db, current_user, d, h, user_id))


@router.get("/payroll", summary="Horas extra aprobadas que se pagan (para nómina)")
def nomina(desde: Optional[date] = None, hasta: Optional[date] = None, liquidadas: Optional[bool] = None,
           db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_hr)):
    d, h = _rango(desde, hasta)
    return APIResponse.ok(data=consultas.nomina(db, d, h, liquidadas))


@router.post("/regularize", summary="Crear las declaraciones posteriores de un periodo")
def regularizar(body: RegularizarIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_hr)):
    return APIResponse.ok(data=control.regularizar_periodo(db, current_user, body.desde, body.hasta))


@router.get("", summary="Horas extra (gestión, acotado a lo que ve)")
def listar(desde: Optional[date] = None, hasta: Optional[date] = None, estado: Optional[str] = None,
           origen: Optional[str] = None, tipo: Optional[str] = None, compensacion: Optional[str] = None,
           user_id: Optional[str] = None, project_id: Optional[str] = None, equipo: Optional[str] = None,
           departamento: Optional[str] = None, db: Session = Depends(get_db),
           current_user: User = Depends(require_any_manager)):
    d, h = _rango(desde, hasta or (desde + timedelta(days=30) if desde else None))
    return APIResponse.ok(data=consultas.listar(db, current_user, {
        "desde": d, "hasta": h, "estado": estado, "origen": origen, "tipo": tipo, "compensacion": compensacion,
        "user_id": user_id, "project_id": project_id, "equipo": equipo, "departamento": departamento}))


# ── Una petición ─────────────────────────────────────────────────────────────

@router.get("/{peticion_id}", summary="Ciclo completo de una petición de horas extra")
def detalle(peticion_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_worker)):
    p = consultas.visible(db, current_user, peticion_id)
    return APIResponse.ok(data=consultas.detalle(db, current_user, p))


def _propia(db, usuario, peticion_id):
    p = consultas.visible(db, usuario, peticion_id)
    if usuario.id not in (p.user_id, p.solicitante_id):
        raise error_con_codigo(404, "horas_extra_no_encontrada")
    return p


@router.put("/{peticion_id}", summary="Editar una petición pendiente (se vuelve a pedir)")
def editar(peticion_id: str, body: PeticionDeHorasExtraIn, db: Session = Depends(get_db),
           current_user: User = Depends(require_worker)):
    p = solicitudes.editar(db, current_user, _propia(db, current_user, peticion_id), body.model_dump())
    return APIResponse.ok(data=_ficha(db, current_user, p))


@router.post("/{peticion_id}/cancel", summary="Cancelar una petición de horas extra")
def cancelar(peticion_id: str, body: NotaIn, db: Session = Depends(get_db),
             current_user: User = Depends(require_worker)):
    p = solicitudes.cancelar(db, current_user, _propia(db, current_user, peticion_id), body.nota)
    return APIResponse.ok(data=_ficha(db, current_user, p))


@router.post("/{peticion_id}/review", summary="Aprobar o rechazar horas extra")
def revisar(peticion_id: str, body: RevisarIn, db: Session = Depends(get_db),
            current_user: User = Depends(require_worker)):
    p = consultas.visible(db, current_user, peticion_id)
    p = solicitudes.revisar(db, current_user, p, body.aprobado, body.nota, body.horas_autorizadas)
    return APIResponse.ok(data=_ficha(db, current_user, p))


@router.post("/{peticion_id}/settle", summary="Liquidar (pagar) horas extra aprobadas")
def liquidar(peticion_id: str, body: LiquidarIn, db: Session = Depends(get_db),
             current_user: User = Depends(require_admin_or_hr)):
    p = solicitudes.liquidar(db, current_user, consultas.visible(db, current_user, peticion_id), body.referencia)
    return APIResponse.ok(data=_ficha(db, current_user, p))
