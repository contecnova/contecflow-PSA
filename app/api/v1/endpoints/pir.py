"""Revisión posterior a la implantación (PIR) de cambios y proyectos (migración 206, docs/PIR.md).

La lógica está en `app/services/pir/`. Capacidades: `pir.ver` (leer y rellenar
las propias; el servicio acota), `pir.gestionar` (programar, descartar,
informes), `pir.aprobar` (aprobar, devolver, cerrar, reabrir) y
`pir.administrar` (configuración, plantillas, borrar).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.constantes import MAX_TAMANO_DE_PAGINA
from app.core.deps import get_db, requiere_capacidad
from app.core.responses import APIResponse
from app.models.user import User
from app.services.pir import informes, plantillas, servicio

router = APIRouter()


class ProgramarIn(BaseModel):
    origen_tipo: str = Field(pattern="^(change|project)$")
    origen_id: str = Field(min_length=1, max_length=36)
    milestone_id: Optional[str] = Field(None, max_length=36)
    fecha_prevista: Optional[date] = None
    responsable_id: Optional[str] = Field(None, max_length=36)
    titulo: Optional[str] = Field(None, max_length=300)


class PirIn(BaseModel):
    """Solo se aplica lo que llega (PATCH)."""
    titulo: Optional[str] = Field(None, max_length=300)
    fecha_prevista: Optional[date] = None
    responsable_id: Optional[str] = Field(None, max_length=36)
    participantes: Optional[list[str]] = None
    objetivos_cumplidos: Optional[str] = None
    resultado: Optional[str] = None
    resumen: Optional[str] = Field(None, max_length=20000)
    criterios: Optional[list[dict[str, Any]]] = None
    preguntas: Optional[list[dict[str, Any]]] = None
    kpis: Optional[list[dict[str, Any]]] = None
    incidencias: Optional[list[str]] = None
    hubo_marcha_atras: Optional[bool] = None
    marcha_atras_detalle: Optional[str] = Field(None, max_length=8000)
    beneficios: Optional[list[dict[str, Any]]] = None
    satisfaccion: Optional[list[dict[str, Any]]] = None


class ComentarioIn(BaseModel):
    comentario: Optional[str] = Field(None, max_length=4000)


class MotivoIn(BaseModel):
    motivo: str = Field(min_length=1, max_length=4000)


class AccionIn(BaseModel):
    descripcion: str = Field(min_length=3, max_length=4000)
    responsable_id: Optional[str] = Field(None, max_length=36)
    fecha_limite: Optional[date] = None
    project_id: Optional[str] = Field(None, max_length=36)


class AccionCambioIn(BaseModel):
    estado: Optional[str] = None
    responsable_id: Optional[str] = Field(None, max_length=36)
    fecha_limite: Optional[date] = None


class LeccionIn(BaseModel):
    titulo: str = Field(min_length=1, max_length=300)
    tipo: Optional[str] = None
    categoria: str = Field(min_length=1, max_length=40)
    severidad: Optional[str] = None
    que_paso: str = Field(min_length=1)
    causa: Optional[str] = None
    impacto: Optional[str] = None
    recomendacion: str = Field(min_length=1)
    etiquetas: Optional[str] = Field(None, max_length=500)
    enviar_a_revision: bool = False


class ConfigIn(BaseModel):
    dias_cambio: Optional[int] = Field(None, ge=0, le=365)
    dias_proyecto: Optional[int] = Field(None, ge=0, le=365)
    aviso_dias_antes: Optional[int] = Field(None, ge=0, le=365)
    segregacion: Optional[bool] = None
    momento_cambio: Optional[str] = None
    momento_proyecto: Optional[str] = None
    obligatorio_normal: Optional[bool] = None
    obligatorio_emergencia: Optional[bool] = None
    obligatorio_estandar: Optional[bool] = None
    obligatorio_proyecto: Optional[bool] = None
    proyecto_acciones_id: Optional[str] = Field(None, max_length=36)


class PlantillaIn(BaseModel):
    nombre: Optional[str] = Field(None, max_length=200)
    ambito: Optional[str] = Field(None, pattern="^(change|project)$")
    tipo: Optional[str] = Field(None, max_length=50)
    obligatorio: Optional[bool] = None
    dias: Optional[int] = Field(None, ge=0, le=365)
    criterios: Optional[list[dict[str, Any]]] = None
    preguntas: Optional[list[dict[str, Any]]] = None
    activo: Optional[bool] = None


# ── Listas, bandeja, CAB e informes ──────────────────────────────────────────

@router.get("", summary="PIR visibles, con filtros (estado `vencido` y `pendiente` incluidos)")
def listar(origen_tipo: Optional[str] = Query(None, pattern="^(change|project)$"),
           origen_id: Optional[str] = Query(None, max_length=36), estado: Optional[str] = Query(None, max_length=20),
           resultado: Optional[str] = Query(None, max_length=20), solo_mias: bool = False,
           solo_obligatorias: bool = False, q: Optional[str] = Query(None, max_length=200),
           page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
           db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("pir.ver"))):
    return APIResponse.ok(data=servicio.listar(db, current_user, origen_tipo=origen_tipo, origen_id=origen_id,
                                               estado=estado, resultado=resultado, solo_mias=solo_mias,
                                               solo_obligatorias=solo_obligatorias, q=q, page=page,
                                               page_size=page_size))


@router.get("/mias", summary="PIR asignadas a mí sin terminar (bandeja y Mi trabajo)")
def mias(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("pir.ver"))):
    return APIResponse.ok(data=servicio.mias_pendientes(db, current_user))


@router.get("/cab", summary="Vista del CAB: cerrados del todo y PIR de cambios pendientes")
def cab(desde: Optional[date] = None, hasta: Optional[date] = None, db: Session = Depends(get_db),
        current_user: User = Depends(requiere_capacidad("pir.ver"))):
    return APIResponse.ok(data=informes.vista_del_cab(db, current_user, desde, hasta))


@router.get("/informes/exito", summary="Tasa de éxito de cambios y proyectos (PIR revisadas)")
def informe_exito(desde: Optional[date] = None, hasta: Optional[date] = None, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("pir.gestionar"))):
    return APIResponse.ok(data=informes.tasa_de_exito(db, current_user, desde, hasta))


@router.get("/informes/cumplimiento", summary="Cumplimiento de las PIR obligatorias (vencidas)")
def informe_cumplimiento(desde: Optional[date] = None, hasta: Optional[date] = None, db: Session = Depends(get_db),
                         current_user: User = Depends(requiere_capacidad("pir.gestionar"))):
    return APIResponse.ok(data=informes.cumplimiento(db, current_user, desde, hasta))


# ── Configuración y plantillas ───────────────────────────────────────────────

@router.get("/config", summary="Configuración de PIR de la empresa")
def ver_config(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("pir.administrar"))):
    return APIResponse.ok(data=plantillas.config_dict(plantillas.config(db, plantillas.org_de(current_user))))


@router.put("/config", summary="Guardar la configuración de PIR")
def guardar_config(payload: ConfigIn, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("pir.administrar"))):
    return APIResponse.ok(data=plantillas.guardar_config(db, current_user, payload.model_dump(exclude_unset=True)))


@router.get("/plantillas", summary="Plantillas de PIR de la empresa")
def listar_plantillas(ambito: Optional[str] = Query(None, pattern="^(change|project)$"), db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("pir.administrar"))):
    return APIResponse.ok(data=plantillas.listar_plantillas(db, current_user, ambito))


@router.get("/plantillas/fabrica", summary="Cuestionario de fábrica (ITIL 4 / PMBOK) en el idioma pedido")
def de_fabrica(ambito: str = Query(..., pattern="^(change|project)$"), idioma: str = Query("es", max_length=5),
               current_user: User = Depends(requiere_capacidad("pir.administrar"))):
    return APIResponse.ok(data=plantillas.de_fabrica(ambito, idioma))


@router.post("/plantillas", summary="Crear plantilla de PIR", status_code=201)
def crear_plantilla(payload: PlantillaIn, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("pir.administrar"))):
    return APIResponse.ok(data=plantillas.guardar_plantilla(db, current_user, payload.model_dump(exclude_unset=True)))


@router.put("/plantillas/{plantilla_id}", summary="Editar plantilla de PIR")
def editar_plantilla(plantilla_id: str, payload: PlantillaIn, db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("pir.administrar"))):
    return APIResponse.ok(data=plantillas.guardar_plantilla(db, current_user, payload.model_dump(exclude_unset=True),
                                                            plantilla_id))


@router.delete("/plantillas/{plantilla_id}", summary="Borrar plantilla de PIR")
def borrar_plantilla(plantilla_id: str, db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("pir.administrar"))):
    plantillas.borrar_plantilla(db, current_user, plantilla_id)
    return APIResponse.ok(data={"ok": True})


# ── Una PIR ──────────────────────────────────────────────────────────────────

@router.post("", summary="Programar una PIR a mano (opcional u obligatoria que falte)", status_code=201)
def programar(payload: ProgramarIn, db: Session = Depends(get_db),
              current_user: User = Depends(requiere_capacidad("pir.gestionar"))):
    return APIResponse.ok(data=servicio.programar_a_mano(db, current_user, payload.model_dump()))


@router.get("/{pir_id}", summary="Detalle de una PIR con lo que puedo hacer en ella")
def detalle(pir_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("pir.ver"))):
    return APIResponse.ok(data=servicio.detalle(db, current_user, pir_id))


@router.patch("/{pir_id}", summary="Rellenar el cuestionario de la PIR")
def guardar(pir_id: str, payload: PirIn, db: Session = Depends(get_db),
            current_user: User = Depends(requiere_capacidad("pir.ver"))):
    return APIResponse.ok(data=servicio.guardar(db, current_user, pir_id, payload.model_dump(exclude_unset=True)))


@router.post("/{pir_id}/enviar", summary="Enviar la PIR a aprobación")
def enviar(pir_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("pir.ver"))):
    return APIResponse.ok(data=servicio.enviar(db, current_user, pir_id))


@router.post("/{pir_id}/aprobar", summary="Aprobar la PIR (segregación si la empresa la exige)")
def aprobar(pir_id: str, payload: ComentarioIn = ComentarioIn(), db: Session = Depends(get_db),
            current_user: User = Depends(requiere_capacidad("pir.aprobar"))):
    return APIResponse.ok(data=servicio.aprobar(db, current_user, pir_id, payload.comentario))


@router.post("/{pir_id}/devolver", summary="Devolver la PIR para completarla")
def devolver(pir_id: str, payload: ComentarioIn, db: Session = Depends(get_db),
             current_user: User = Depends(requiere_capacidad("pir.aprobar"))):
    return APIResponse.ok(data=servicio.devolver(db, current_user, pir_id, payload.comentario or ""))


@router.post("/{pir_id}/cerrar", summary="Cerrar la PIR aprobada")
def cerrar(pir_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("pir.aprobar"))):
    return APIResponse.ok(data=servicio.cerrar(db, current_user, pir_id))


@router.post("/{pir_id}/reabrir", summary="Reabrir una PIR aprobada, cerrada o descartada")
def reabrir(pir_id: str, payload: MotivoIn, db: Session = Depends(get_db),
            current_user: User = Depends(requiere_capacidad("pir.aprobar"))):
    return APIResponse.ok(data=servicio.reabrir(db, current_user, pir_id, payload.motivo))


@router.post("/{pir_id}/descartar", summary="Descartar una PIR opcional")
def descartar(pir_id: str, payload: MotivoIn, db: Session = Depends(get_db),
              current_user: User = Depends(requiere_capacidad("pir.gestionar"))):
    return APIResponse.ok(data=servicio.descartar(db, current_user, pir_id, payload.motivo))


@router.delete("/{pir_id}", summary="Borrar una PIR (bloqueo legal y auditoría)")
def borrar(pir_id: str, db: Session = Depends(get_db),
           current_user: User = Depends(requiere_capacidad("pir.administrar"))):
    servicio.borrar(db, current_user, pir_id)
    return APIResponse.ok(data={"ok": True})


@router.post("/{pir_id}/acciones", summary="Acción de mejora (nace como tarea enlazada)", status_code=201)
def crear_accion(pir_id: str, payload: AccionIn, db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("pir.ver"))):
    return APIResponse.ok(data=servicio.crear_accion(db, current_user, pir_id, payload.model_dump()))


@router.patch("/{pir_id}/acciones/{accion_id}", summary="Cambiar estado, responsable o fecha de una acción")
def editar_accion(pir_id: str, accion_id: str, payload: AccionCambioIn, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("pir.ver"))):
    return APIResponse.ok(data=servicio.editar_accion(db, current_user, pir_id, accion_id,
                                                      payload.model_dump(exclude_unset=True)))


@router.post("/{pir_id}/lecciones", summary="Crear una lección aprendida con esta PIR como origen", status_code=201)
def crear_leccion(pir_id: str, payload: LeccionIn, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("pir.ver"))):
    return APIResponse.ok(data=servicio.crear_leccion(db, current_user, pir_id, payload.model_dump()))
