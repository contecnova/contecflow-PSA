"""Ausencias gobernadas por reglas (tarea #25, revisión 167): configuración,
cuadrante, cobertura, vista previa, detalle, documentos, bandeja y ejemplos.

Montado en `/absences` junto al router de siempre (`absences.py`). La lógica
vive en `app/services/ausencias/`; aquí solo guardas y forma de la respuesta.

Guardas:
  · tipos y tipos de documento: leer, quien trabaja (también el subcontratado,
    para pedir la suya; 16-11-2026); turnos: leer, cualquier usuario interno;
    escribir, administración o RRHH;
  · acceso especial a datos de salud: solo administración (y lo ve RRHH);
  · rotaciones y cambios del cuadrante: cualquier responsable;
  · ejemplos: administración;
  · detalle y documentos de una ausencia: el servicio comprueba persona,
    responsable, quien aprueba, RRHH o administración (y la categoría especial).

Rev. 180 (horario efectivo y ausencias por horas):
  · jornadas y a quién se aplican, ficha laboral (sede, alta, contrato),
    ajustes de saldo y recalcular la bolsa de horas: administración o RRHH;
  · horario efectivo (rejilla persona×día): quien trabaja; un responsable ve a
    quien ve, un empleado a su equipo, un externo a sí mismo y a quien
    comparte proyecto con él;
  · saldos por persona: responsables (las personas que ven); los movimientos
    de un saldo: la persona, RRHH o administración.
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.deps import (
    get_current_user,
    requiere_capacidad,
)
from app.core.network import ip_del_cliente
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error as error_con_codigo
from app.core.responses import APIResponse
from app.core.uploads import UploadProfile, read_and_validate_upload_sync, safe_filename
from app.db.session import get_db
from app.models.user import User
from app.schemas.absences import (AbsenceIn, AccesoEspecialIn, AmpliarIn, AsignacionDeJornadaIn, CuadranteIn,
                                  FichaLaboralIn, JornadaIn, MovimientoDeSaldoIn, NotaIn, PatronIn, PedirDocumentoIn,
                                  RecalcularBolsaIn, TipoDeAusenciaIn, TipoDeDocumentoIn, TurnoIn)
from app.services.ausencias import (bolsa, catalogo, consultas, documentos, ejemplos, movimientos, saldos, solicitudes,
                                    turnos)
from app.services.horario import jornadas

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return ip_del_cliente(request)


# ── Tipos de ausencia ────────────────────────────────────────────────────────

@router.get("/types", summary="Tipos de ausencia")
def listar_tipos(incluir_inactivos: bool = False, db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("ausencias.trabajar"))):
    # Externos como internos (16-11-2026): el catalogo hace falta para pedir la
    # ausencia propia (POST /absences/my); no lleva datos de nadie.
    return APIResponse.ok(data=[catalogo.tipo_dict(t) for t in catalogo.tipos(db, incluir_inactivos=incluir_inactivos, usuario=current_user)])


@router.post("/types", summary="Crear tipo de ausencia")
def crear_tipo(payload: TipoDeAusenciaIn, db: Session = Depends(get_db),
               current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=catalogo.guardar_tipo(db, current_user, payload.model_dump()))


@router.put("/types/{tipo_id}", summary="Editar tipo de ausencia")
def editar_tipo(tipo_id: str, payload: TipoDeAusenciaIn, db: Session = Depends(get_db),
                current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=catalogo.guardar_tipo(db, current_user, payload.model_dump(exclude_unset=False), tipo_id))


@router.delete("/types/{tipo_id}", summary="Borrar (o desactivar si está en uso) un tipo de ausencia")
def borrar_tipo(tipo_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=catalogo.borrar_tipo(db, current_user, tipo_id))


@router.get("/document-types", summary="Tipos de documento de ausencias")
def listar_documentos(incluir_inactivos: bool = False, db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("ausencias.trabajar"))):
    # Externos como internos (16-11-2026): que documentos pide cada tipo, para la propia.
    return APIResponse.ok(data=[catalogo.documento_dict(d) for d in catalogo.documentos(db, incluir_inactivos=incluir_inactivos, usuario=current_user)])


@router.post("/document-types", summary="Crear tipo de documento")
def crear_documento(payload: TipoDeDocumentoIn, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=catalogo.guardar_documento(db, current_user, payload.model_dump()))


@router.put("/document-types/{doc_id}", summary="Editar tipo de documento")
def editar_documento(doc_id: str, payload: TipoDeDocumentoIn, db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=catalogo.guardar_documento(db, current_user, payload.model_dump(), doc_id))


@router.delete("/document-types/{doc_id}", summary="Borrar (o desactivar) un tipo de documento")
def borrar_documento(doc_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=catalogo.borrar_documento(db, current_user, doc_id))


@router.get("/special-access", summary="Quién ve documentos de categoría especial (además de la persona y RRHH)")
def listar_accesos(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=catalogo.accesos(db))


@router.post("/special-access", summary="Conceder acceso a documentos de categoría especial")
def conceder_acceso(payload: AccesoEspecialIn, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.administrar"))):
    return APIResponse.ok(data=catalogo.conceder_acceso(db, current_user, payload.user_id))


@router.delete("/special-access/{user_id}", summary="Retirar acceso a documentos de categoría especial")
def retirar_acceso(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.administrar"))):
    return APIResponse.ok(data=catalogo.retirar_acceso(db, current_user, user_id))


# ── Turnos, rotaciones y cuadrante ───────────────────────────────────────────

@router.get("/shifts", summary="Turnos")
def listar_turnos(incluir_inactivos: bool = False, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("ausencias.usar"))):
    return APIResponse.ok(data=[turnos.turno_dict(t) for t in turnos.turnos(db, incluir_inactivos=incluir_inactivos)])


@router.post("/shifts", summary="Crear turno")
def crear_turno(payload: TurnoIn, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=turnos.guardar_turno(db, current_user, payload.model_dump()))


@router.put("/shifts/{turno_id}", summary="Editar turno")
def editar_turno(turno_id: str, payload: TurnoIn, db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=turnos.guardar_turno(db, current_user, payload.model_dump(), turno_id))


@router.delete("/shifts/{turno_id}", summary="Borrar (o desactivar si está en uso) un turno")
def borrar_turno(turno_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=turnos.borrar_turno(db, current_user, turno_id))


@router.get("/rotations", summary="Rotaciones de turnos")
def listar_rotaciones(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.responsables"))):
    return APIResponse.ok(data=[turnos.patron_dict(p) for p in turnos.patrones(db)])


@router.post("/rotations", summary="Crear rotación")
def crear_rotacion(payload: PatronIn, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.responsables"))):
    return APIResponse.ok(data=turnos.guardar_patron(db, current_user, payload.model_dump()))


@router.put("/rotations/{patron_id}", summary="Editar rotación (ciclo y personas)")
def editar_rotacion(patron_id: str, payload: PatronIn, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("ausencias.responsables"))):
    return APIResponse.ok(data=turnos.guardar_patron(db, current_user, payload.model_dump(), patron_id))


@router.delete("/rotations/{patron_id}", summary="Borrar rotación")
def borrar_rotacion(patron_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.responsables"))):
    turnos.borrar_patron(db, current_user, patron_id)
    return APIResponse.ok(data={"ok": True})


def _rango(desde: Optional[date], hasta: Optional[date]) -> tuple[date, date]:
    from app.core import timeutil
    desde = desde or timeutil.today().replace(day=1)
    return desde, hasta or (desde + timedelta(days=30))


@router.get("/roster", summary="Cuadrante: turno de cada persona y día")
def ver_cuadrante(desde: Optional[date] = None, hasta: Optional[date] = None, equipo: Optional[str] = None,
                  departamento: Optional[str] = None, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("ausencias.usar"))):
    d0, d1 = _rango(desde, hasta)
    return APIResponse.ok(data=turnos.cuadrante(db, d0, d1, equipo=equipo, departamento=departamento))


@router.put("/roster", summary="Cambiar turnos del cuadrante (por persona y día)")
def cambiar_cuadrante(payload: CuadranteIn, db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("ausencias.responsables"))):
    n = turnos.asignar(db, current_user, [c.model_dump() for c in payload.cambios])
    return APIResponse.ok(data={"cambios": n})


@router.get("/coverage", summary="Cobertura por día y turno: requeridas, disponibles y ausentes")
def ver_cobertura(desde: Optional[date] = None, hasta: Optional[date] = None, equipo: Optional[str] = None,
                  departamento: Optional[str] = None, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("ausencias.usar"))):
    d0, d1 = _rango(desde, hasta)
    return APIResponse.ok(data=turnos.cobertura(db, d0, d1, equipo=equipo, departamento=departamento))


# ── Pedir: vista previa y saldos ─────────────────────────────────────────────

@router.post("/preview", summary="Vista previa de una petición (cupos, aprobaciones, documentos, saldo)")
def vista_previa(payload: AbsenceIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return APIResponse.ok(data=solicitudes.vista_previa(db, current_user, payload.model_dump()))


@router.get("/my/balances", summary="Mis saldos (vacaciones, cupos propios y bolsa), en días y horas")
def mis_saldos(year: Optional[int] = None, fecha: Optional[date] = None, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    from app.core import timeutil
    return APIResponse.ok(data=saldos.todos(db, current_user.id, fecha or year or timeutil.today()))


@router.get("/my/schedule", summary="Mi horario efectivo por día (turno o jornada, festivos, ausencias)")
def mi_horario(desde: Optional[date] = None, hasta: Optional[date] = None, db: Session = Depends(get_db),
               current_user: User = Depends(requiere_capacidad("ausencias.trabajar"))):
    d0, d1 = _rango(desde, hasta)
    return APIResponse.ok(data=jornadas.rejilla(db, current_user, d0, d1, user_ids=[current_user.id]))


# ── Rev. 180: horario efectivo, jornadas, ficha laboral ──────────────────────

@router.get("/effective-schedule", summary="Horario efectivo persona×día (turno o jornada, festivos de su sede, ausencias)")
def horario_efectivo(desde: Optional[date] = None, hasta: Optional[date] = None, equipo: Optional[str] = None,
                     departamento: Optional[str] = None, user_ids: Optional[list[str]] = Query(None),
                     db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.trabajar"))):
    d0, d1 = _rango(desde, hasta)
    ids = jornadas.personas_que_ve(db, current_user, user_ids)
    return APIResponse.ok(data=jornadas.rejilla(db, current_user, d0, d1, equipo=equipo, departamento=departamento,
                                                user_ids=ids))


@router.get("/work-schedules", summary="Jornadas laborales (normal, verano, reducida…) con sus asignaciones")
def listar_jornadas(incluir_inactivas: bool = False, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("ausencias.responsables"))):
    return APIResponse.ok(data=[jornadas.jornada_dict(j) for j in jornadas.jornadas(db, incluir_inactivas=incluir_inactivas)])


@router.post("/work-schedules", summary="Crear jornada laboral")
def crear_jornada(payload: JornadaIn, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=jornadas.guardar_jornada(db, current_user, payload.model_dump()))


@router.put("/work-schedules/{jornada_id}", summary="Editar jornada laboral")
def editar_jornada(jornada_id: str, payload: JornadaIn, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=jornadas.guardar_jornada(db, current_user, payload.model_dump(), jornada_id))


@router.delete("/work-schedules/{jornada_id}", summary="Borrar (o desactivar si está asignada) una jornada")
def borrar_jornada(jornada_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=jornadas.borrar_jornada(db, current_user, jornada_id))


@router.post("/work-schedule-assignments", summary="Aplicar una jornada (empresa, sede, departamento, equipo, grupo o persona)")
def crear_asignacion(payload: AsignacionDeJornadaIn, db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=jornadas.guardar_asignacion(db, current_user, payload.model_dump()))


@router.put("/work-schedule-assignments/{asignacion_id}", summary="Editar a quién y cuándo se aplica una jornada")
def editar_asignacion(asignacion_id: str, payload: AsignacionDeJornadaIn, db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=jornadas.guardar_asignacion(db, current_user, payload.model_dump(), asignacion_id))


@router.delete("/work-schedule-assignments/{asignacion_id}", summary="Quitar una asignación de jornada")
def borrar_asignacion(asignacion_id: str, db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    jornadas.borrar_asignacion(db, current_user, asignacion_id)
    return APIResponse.ok(data={"ok": True})


@router.get("/work-profiles", summary="Ficha laboral de cada persona (sede, fecha de alta, tipo de contrato)")
def listar_fichas(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=jornadas.fichas(db))


@router.put("/work-profiles/{user_id}", summary="Editar la ficha laboral de una persona")
def editar_ficha(user_id: str, payload: FichaLaboralIn, db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=jornadas.guardar_ficha(db, current_user, user_id, payload.model_dump(exclude_unset=True)))


# ── Rev. 180: saldos por persona, ajustes y bolsa de horas ───────────────────

@router.get("/balances", summary="Saldos por persona, en días y horas (responsables: las personas que ven)")
def saldos_por_persona(fecha: Optional[date] = None, equipo: Optional[str] = None, departamento: Optional[str] = None,
                       user_ids: Optional[list[str]] = Query(None), db: Session = Depends(get_db),
                       current_user: User = Depends(requiere_capacidad("ausencias.responsables"))):
    return APIResponse.ok(data=movimientos.saldos_de_personas(db, current_user, fecha, user_ids, equipo, departamento))


@router.get("/balances/{user_id}/movements", summary="Ajustes y horas de bolsa de un saldo")
def movimientos_de_saldo(user_id: str, saldo_clave: Optional[str] = None, db: Session = Depends(get_db),
                         current_user: User = Depends(requiere_capacidad("ausencias.trabajar"))):
    rol = str(getattr(current_user.role, "value", current_user.role))
    if user_id != current_user.id and rol not in ("admin", "hr") and not getattr(current_user, "is_superadmin", False):
        raise error_con_codigo(403, "solo_persona_rrhh_o_admin")
    return APIResponse.ok(data=movimientos.listar(db, user_id, saldo_clave))


@router.post("/balance-adjustments", summary="Ajustar un saldo (sumar o restar, con motivo y caducidad)")
def ajustar_saldo(payload: MovimientoDeSaldoIn, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    return APIResponse.ok(data=movimientos.crear(db, current_user, payload.model_dump()))


@router.delete("/balance-adjustments/{movimiento_id}", summary="Quitar un ajuste de saldo")
def quitar_ajuste(movimiento_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    movimientos.borrar(db, current_user, movimiento_id)
    return APIResponse.ok(data={"ok": True})


@router.post("/hour-bank/recalculate", summary="Recalcular la bolsa de horas desde las imputaciones")
def recalcular_bolsa(payload: RecalcularBolsaIn, db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("ausencias.config"))):
    if payload.hasta < payload.desde or (payload.hasta - payload.desde).days > 400:
        raise error_con_codigo(422, "rango_de_1_a_400_dias")
    return APIResponse.ok(data=bolsa.recalcular_y_auditar(db, current_user, payload.desde, payload.hasta,
                                                          payload.user_ids))


@router.get("/inbox", summary="Ausencias que me toca decidir, con explicación e impacto en la cobertura")
def bandeja(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.usar"))):
    return APIResponse.ok(data=consultas.bandeja(db, current_user))


@router.post("/examples", summary="Cargar el ejemplo de tres turnos con cupo y lista de espera (no se aplica solo)")
def cargar_ejemplos(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.administrar"))):
    return APIResponse.ok(data=ejemplos.cargar(db, current_user))


# ── Una ausencia ─────────────────────────────────────────────────────────────

@router.get("/{absence_id}/detail", summary="Detalle: línea de tiempo, documentos, plazas, aprobación")
def detalle(absence_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return APIResponse.ok(data=consultas.detalle(db, current_user, consultas.visible(db, current_user, absence_id)))


@router.post("/{absence_id}/documents", summary="Adjuntar un documento (o una versión nueva)")
def subir_documento(absence_id: str, request: Request, file: UploadFile = File(...), tipo_id: str = Form(...),
                    sustituye_a: Optional[str] = Form(None), nota: Optional[str] = Form(None),
                    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    a = consultas.visible(db, current_user, absence_id)
    contenido = read_and_validate_upload_sync(file, UploadProfile.DOCUMENT)
    return APIResponse.ok(data=documentos.subir(db, current_user, a, tipo_id=tipo_id, nombre=safe_filename(file.filename),
                                                content_type=file.content_type or "", contenido=contenido,
                                                sustituye_a=sustituye_a, nota=nota, ip=_ip(request)))


@router.get("/{absence_id}/documents/{doc_id}/open", summary="Enlace firmado para ver o descargar (auditado)")
def abrir_documento(absence_id: str, doc_id: str, request: Request, accion: str = Query("view"),
                    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    a = consultas.visible(db, current_user, absence_id)
    return APIResponse.ok(data=documentos.abrir(db, current_user, a, doc_id, accion, _ip(request)))


@router.post("/{absence_id}/document-requests", summary="Pedir otro documento (RRHH o responsable)")
def pedir_documento(absence_id: str, payload: PedirDocumentoIn, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("ausencias.usar"))):
    a = consultas.visible(db, current_user, absence_id)
    return APIResponse.ok(data=documentos.pedir(db, current_user, a, payload.tipo_id, payload.vence, payload.nota))


@router.post("/{absence_id}/document-requests/{requisito_id}/waive", summary="Dispensar un documento pedido")
def dispensar_documento(absence_id: str, requisito_id: str, payload: NotaIn, db: Session = Depends(get_db),
                        current_user: User = Depends(requiere_capacidad("ausencias.usar"))):
    a = consultas.visible(db, current_user, absence_id)
    return APIResponse.ok(data=documentos.dispensar(db, current_user, a, requisito_id, payload.nota))


@router.post("/{absence_id}/extend", summary="Ampliar una ausencia aprobada (RRHH, admin o responsable)")
def ampliar(absence_id: str, payload: AmpliarIn, db: Session = Depends(get_db),
            current_user: User = Depends(requiere_capacidad("ausencias.usar"))):
    a = consultas.visible(db, current_user, absence_id)
    documentos.exigir_gestion(db, current_user, a)
    a = solicitudes.ampliar(db, current_user, a, payload.end_date, payload.nota)
    return APIResponse.ok(data=consultas.detalle(db, current_user, a))


@router.post("/{absence_id}/promote", summary="Dar plaza a mano a una petición en lista de espera")
def dar_plaza(absence_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ausencias.gestionar"))):
    a = consultas.visible(db, current_user, absence_id)
    documentos.exigir_gestion(db, current_user, a)
    if a.user_id == current_user.id:
        raise error_con_codigo(403, "no_puedes_contigo", detail="No puedes darte plaza a ti")
    a = solicitudes.dar_plaza(db, current_user, a)
    return APIResponse.ok(data=consultas.detalle(db, current_user, a))
