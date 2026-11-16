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
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.deps import (get_current_user, require_admin, require_admin_or_hr, require_any_manager,
                           require_internal_user, require_worker)
from app.core.errores import ErrorDeDominio
from app.core.responses import APIResponse
from app.db.session import get_db
from app.models.user import User
from app.schemas.absences import (AbsenceIn, AccesoEspecialIn, AmpliarIn, CuadranteIn, NotaIn, PatronIn,
                                  PedirDocumentoIn, TipoDeAusenciaIn, TipoDeDocumentoIn, TurnoIn)
from app.services.ausencias import catalogo, consultas, documentos, ejemplos, saldos, solicitudes, turnos

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


# ── Tipos de ausencia ────────────────────────────────────────────────────────

@router.get("/types", summary="Tipos de ausencia")
def listar_tipos(incluir_inactivos: bool = False, db: Session = Depends(get_db),
                 current_user: User = Depends(require_worker)):
    # Externos como internos (16-11-2026): el catalogo hace falta para pedir la
    # ausencia propia (POST /absences/my); no lleva datos de nadie.
    return APIResponse.ok(data=[catalogo.tipo_dict(t) for t in catalogo.tipos(db, incluir_inactivos=incluir_inactivos)])


@router.post("/types", summary="Crear tipo de ausencia")
def crear_tipo(payload: TipoDeAusenciaIn, db: Session = Depends(get_db),
               current_user: User = Depends(require_admin_or_hr)):
    return APIResponse.ok(data=catalogo.guardar_tipo(db, current_user, payload.model_dump()))


@router.put("/types/{tipo_id}", summary="Editar tipo de ausencia")
def editar_tipo(tipo_id: str, payload: TipoDeAusenciaIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_admin_or_hr)):
    return APIResponse.ok(data=catalogo.guardar_tipo(db, current_user, payload.model_dump(exclude_unset=False), tipo_id))


@router.delete("/types/{tipo_id}", summary="Borrar (o desactivar si está en uso) un tipo de ausencia")
def borrar_tipo(tipo_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_hr)):
    return APIResponse.ok(data=catalogo.borrar_tipo(db, current_user, tipo_id))


@router.get("/document-types", summary="Tipos de documento de ausencias")
def listar_documentos(incluir_inactivos: bool = False, db: Session = Depends(get_db),
                      current_user: User = Depends(require_worker)):
    # Externos como internos (16-11-2026): que documentos pide cada tipo, para la propia.
    return APIResponse.ok(data=[catalogo.documento_dict(d) for d in catalogo.documentos(db, incluir_inactivos=incluir_inactivos)])


@router.post("/document-types", summary="Crear tipo de documento")
def crear_documento(payload: TipoDeDocumentoIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_admin_or_hr)):
    return APIResponse.ok(data=catalogo.guardar_documento(db, current_user, payload.model_dump()))


@router.put("/document-types/{doc_id}", summary="Editar tipo de documento")
def editar_documento(doc_id: str, payload: TipoDeDocumentoIn, db: Session = Depends(get_db),
                     current_user: User = Depends(require_admin_or_hr)):
    return APIResponse.ok(data=catalogo.guardar_documento(db, current_user, payload.model_dump(), doc_id))


@router.delete("/document-types/{doc_id}", summary="Borrar (o desactivar) un tipo de documento")
def borrar_documento(doc_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_hr)):
    return APIResponse.ok(data=catalogo.borrar_documento(db, current_user, doc_id))


@router.get("/special-access", summary="Quién ve documentos de categoría especial (además de la persona y RRHH)")
def listar_accesos(db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_hr)):
    return APIResponse.ok(data=catalogo.accesos(db))


@router.post("/special-access", summary="Conceder acceso a documentos de categoría especial")
def conceder_acceso(payload: AccesoEspecialIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return APIResponse.ok(data=catalogo.conceder_acceso(db, current_user, payload.user_id))


@router.delete("/special-access/{user_id}", summary="Retirar acceso a documentos de categoría especial")
def retirar_acceso(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return APIResponse.ok(data=catalogo.retirar_acceso(db, current_user, user_id))


# ── Turnos, rotaciones y cuadrante ───────────────────────────────────────────

@router.get("/shifts", summary="Turnos")
def listar_turnos(incluir_inactivos: bool = False, db: Session = Depends(get_db),
                  current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=[turnos.turno_dict(t) for t in turnos.turnos(db, incluir_inactivos=incluir_inactivos)])


@router.post("/shifts", summary="Crear turno")
def crear_turno(payload: TurnoIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_hr)):
    return APIResponse.ok(data=turnos.guardar_turno(db, current_user, payload.model_dump()))


@router.put("/shifts/{turno_id}", summary="Editar turno")
def editar_turno(turno_id: str, payload: TurnoIn, db: Session = Depends(get_db),
                 current_user: User = Depends(require_admin_or_hr)):
    return APIResponse.ok(data=turnos.guardar_turno(db, current_user, payload.model_dump(), turno_id))


@router.delete("/shifts/{turno_id}", summary="Borrar (o desactivar si está en uso) un turno")
def borrar_turno(turno_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_hr)):
    return APIResponse.ok(data=turnos.borrar_turno(db, current_user, turno_id))


@router.get("/rotations", summary="Rotaciones de turnos")
def listar_rotaciones(db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=[turnos.patron_dict(p) for p in turnos.patrones(db)])


@router.post("/rotations", summary="Crear rotación")
def crear_rotacion(payload: PatronIn, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=turnos.guardar_patron(db, current_user, payload.model_dump()))


@router.put("/rotations/{patron_id}", summary="Editar rotación (ciclo y personas)")
def editar_rotacion(patron_id: str, payload: PatronIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=turnos.guardar_patron(db, current_user, payload.model_dump(), patron_id))


@router.delete("/rotations/{patron_id}", summary="Borrar rotación")
def borrar_rotacion(patron_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    turnos.borrar_patron(db, current_user, patron_id)
    return APIResponse.ok(data={"ok": True})


def _rango(desde: Optional[date], hasta: Optional[date]) -> tuple[date, date]:
    from app.core import timeutil
    desde = desde or timeutil.today().replace(day=1)
    return desde, hasta or (desde + timedelta(days=30))


@router.get("/roster", summary="Cuadrante: turno de cada persona y día")
def ver_cuadrante(desde: Optional[date] = None, hasta: Optional[date] = None, equipo: Optional[str] = None,
                  departamento: Optional[str] = None, db: Session = Depends(get_db),
                  current_user: User = Depends(require_internal_user)):
    d0, d1 = _rango(desde, hasta)
    return APIResponse.ok(data=turnos.cuadrante(db, d0, d1, equipo=equipo, departamento=departamento))


@router.put("/roster", summary="Cambiar turnos del cuadrante (por persona y día)")
def cambiar_cuadrante(payload: CuadranteIn, db: Session = Depends(get_db),
                      current_user: User = Depends(require_any_manager)):
    n = turnos.asignar(db, current_user, [c.model_dump() for c in payload.cambios])
    return APIResponse.ok(data={"cambios": n})


@router.get("/coverage", summary="Cobertura por día y turno: requeridas, disponibles y ausentes")
def ver_cobertura(desde: Optional[date] = None, hasta: Optional[date] = None, equipo: Optional[str] = None,
                  departamento: Optional[str] = None, db: Session = Depends(get_db),
                  current_user: User = Depends(require_internal_user)):
    d0, d1 = _rango(desde, hasta)
    return APIResponse.ok(data=turnos.cobertura(db, d0, d1, equipo=equipo, departamento=departamento))


# ── Pedir: vista previa y saldos ─────────────────────────────────────────────

@router.post("/preview", summary="Vista previa de una petición (cupos, aprobaciones, documentos, saldo)")
def vista_previa(payload: AbsenceIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return APIResponse.ok(data=solicitudes.vista_previa(db, current_user, payload.model_dump()))


@router.get("/my/balances", summary="Mis saldos (vacaciones y cupos propios)")
def mis_saldos(year: Optional[int] = None, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    from app.core import timeutil
    return APIResponse.ok(data=saldos.todos(db, current_user.id, year or timeutil.today().year))


@router.get("/inbox", summary="Ausencias que me toca decidir, con explicación e impacto en la cobertura")
def bandeja(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=consultas.bandeja(db, current_user))


@router.post("/examples", summary="Cargar el ejemplo de tres turnos con cupo y lista de espera (no se aplica solo)")
def cargar_ejemplos(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
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
    contenido = file.file.read()
    return APIResponse.ok(data=documentos.subir(db, current_user, a, tipo_id=tipo_id, nombre=file.filename or "",
                                                content_type=file.content_type or "", contenido=contenido,
                                                sustituye_a=sustituye_a, nota=nota, ip=_ip(request)))


@router.get("/{absence_id}/documents/{doc_id}/open", summary="Enlace firmado para ver o descargar (auditado)")
def abrir_documento(absence_id: str, doc_id: str, request: Request, accion: str = Query("view"),
                    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    a = consultas.visible(db, current_user, absence_id)
    return APIResponse.ok(data=documentos.abrir(db, current_user, a, doc_id, accion, _ip(request)))


@router.post("/{absence_id}/document-requests", summary="Pedir otro documento (RRHH o responsable)")
def pedir_documento(absence_id: str, payload: PedirDocumentoIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_internal_user)):
    a = consultas.visible(db, current_user, absence_id)
    return APIResponse.ok(data=documentos.pedir(db, current_user, a, payload.tipo_id, payload.vence, payload.nota))


@router.post("/{absence_id}/document-requests/{requisito_id}/waive", summary="Dispensar un documento pedido")
def dispensar_documento(absence_id: str, requisito_id: str, payload: NotaIn, db: Session = Depends(get_db),
                        current_user: User = Depends(require_internal_user)):
    a = consultas.visible(db, current_user, absence_id)
    return APIResponse.ok(data=documentos.dispensar(db, current_user, a, requisito_id, payload.nota))


@router.post("/{absence_id}/extend", summary="Ampliar una ausencia aprobada (RRHH, admin o responsable)")
def ampliar(absence_id: str, payload: AmpliarIn, db: Session = Depends(get_db),
            current_user: User = Depends(require_internal_user)):
    a = consultas.visible(db, current_user, absence_id)
    documentos.exigir_gestion(db, current_user, a)
    a = solicitudes.ampliar(db, current_user, a, payload.end_date, payload.nota)
    return APIResponse.ok(data=consultas.detalle(db, current_user, a))


@router.post("/{absence_id}/promote", summary="Dar plaza a mano a una petición en lista de espera")
def dar_plaza(absence_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    a = consultas.visible(db, current_user, absence_id)
    documentos.exigir_gestion(db, current_user, a)
    if a.user_id == current_user.id:
        raise ErrorDeDominio(403, "No puedes darte plaza a ti")
    a = solicitudes.dar_plaza(db, current_user, a)
    return APIResponse.ok(data=consultas.detalle(db, current_user, a))
