"""Lecciones aprendidas (revisión 2026-11). La lógica está en `app/services/lecciones.py`."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_admin, require_internal_user
from app.core.responses import APIResponse
from app.models.user import User
from app.services import lecciones as svc
from app.core.constantes import MAX_TAMANO_DE_PAGINA

router = APIRouter()


class LeccionIn(BaseModel):
    titulo: Optional[str] = Field(None, max_length=300)
    tipo: Optional[str] = None
    categoria: Optional[str] = Field(None, max_length=40)
    severidad: Optional[str] = None
    que_paso: Optional[str] = None
    causa: Optional[str] = None
    impacto: Optional[str] = None
    recomendacion: Optional[str] = None
    etiquetas: Optional[str] = Field(None, max_length=500)
    proyecto_id: Optional[str] = None
    cliente_id: Optional[str] = None
    tipo_proyecto: Optional[str] = Field(None, max_length=30)
    servicio_id: Optional[str] = None
    ci_id: Optional[str] = None
    origen_tipo: Optional[str] = None
    origen_id: Optional[str] = Field(None, max_length=64)
    enviar_a_revision: bool = False


class EstadoIn(BaseModel):
    estado: str


class ValoracionIn(BaseModel):
    contexto_tipo: str = Field(pattern="^(project|ticket|nuevo_proyecto)$")
    contexto_id: Optional[str] = Field(None, max_length=64)
    valor: str = Field(pattern="^(util|aplicada|no_aplica)$")
    nota: Optional[str] = Field(None, max_length=500)


class NuevoProyectoIn(BaseModel):
    nombre: Optional[str] = Field(None, max_length=255)
    descripcion: Optional[str] = Field(None, max_length=4000)
    cliente_id: Optional[str] = None
    tipo_proyecto: Optional[str] = None
    etiquetas: Optional[str] = Field(None, max_length=500)


class AccionIn(BaseModel):
    descripcion: str = Field(min_length=3, max_length=4000)
    responsable_id: Optional[str] = None
    fecha_limite: Optional[date] = None


class AccionCambioIn(BaseModel):
    estado: Optional[str] = None
    resultado: Optional[str] = Field(None, max_length=4000)
    responsable_id: Optional[str] = None
    fecha_limite: Optional[date] = None


@router.get("", summary="Lecciones aprendidas, con filtros")
def listar(q: Optional[str] = Query(None, max_length=200), estado: Optional[str] = None, tipo: Optional[str] = None,
           categoria: Optional[str] = None, origen_tipo: Optional[str] = None, proyecto_id: Optional[str] = None,
           cliente_id: Optional[str] = None, etiqueta: Optional[str] = None, page: int = Query(1, ge=1),
           page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA), db: Session = Depends(get_db),
           current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=svc.listar(db, current_user, q=q, estado=estado, tipo=tipo, categoria=categoria,
                                          origen_tipo=origen_tipo, proyecto_id=proyecto_id, cliente_id=cliente_id,
                                          etiqueta=etiqueta, page=page, page_size=page_size))


@router.get("/config", summary="Categorías y si quien pregunta puede validar")
def config(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data={"categorias": svc.categorias(db, current_user.organization_id),
                                "puedo_validar": svc.puede_validar(db, current_user)})


@router.get("/pendientes", summary="Lo cerrado recientemente que aún no tiene lección")
def pendientes(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data={"items": svc.pendientes(db, current_user)})


@router.get("/indicadores", summary="Indicadores de la mejora continua")
def indicadores(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=svc.indicadores(db, current_user))


@router.get("/acciones", summary="Acciones de mejora (abiertas por defecto)")
def acciones(solo_mias: bool = False, solo_abiertas: bool = True, db: Session = Depends(get_db),
             current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data={"items": svc.acciones(db, current_user, solo_mias=solo_mias, solo_abiertas=solo_abiertas)})


@router.patch("/acciones/{accion_id}", summary="Avanzar o cerrar una acción de mejora")
def editar_accion(accion_id: str, body: AccionCambioIn, db: Session = Depends(get_db),
                  current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=svc.editar_accion(db, current_user, accion_id, body.model_dump(exclude_unset=True)))


@router.get("/borrador/{origen_tipo}/{origen_id}", summary="Hechos medidos del origen y propuesta de lección")
def borrador(origen_tipo: str, origen_id: str, db: Session = Depends(get_db),
             current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=svc.borrador(db, current_user, origen_tipo, origen_id))


@router.get("/de/{origen_tipo}/{origen_id}", summary="Lecciones que salieron de este origen")
def de_origen(origen_tipo: str, origen_id: str, db: Session = Depends(get_db),
              current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data={"items": svc.de_origen(db, current_user, origen_tipo, origen_id)})


@router.get("/recomendaciones/{contexto_tipo}/{contexto_id}", summary="Lecciones que aplican a un proyecto o ticket")
def recomendaciones(contexto_tipo: str, contexto_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=svc.recomendar(db, current_user, contexto_tipo, contexto_id))


@router.post("/recomendaciones/nuevo-proyecto", summary="Lecciones que aplican a un proyecto que se está creando")
def recomendaciones_nuevo(body: NuevoProyectoIn, db: Session = Depends(get_db),
                          current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=svc.recomendar(db, current_user, "nuevo_proyecto", campos=body.model_dump()))


@router.post("", summary="Crear una lección (a mano o desde su origen)")
def crear(body: LeccionIn, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=svc.crear(db, current_user, body.model_dump()))


@router.get("/{leccion_id}", summary="Ficha de la lección")
def detalle(leccion_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=svc.detalle(db, current_user, leccion_id))


@router.patch("/{leccion_id}", summary="Editar una lección")
def editar(leccion_id: str, body: LeccionIn, db: Session = Depends(get_db),
           current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=svc.editar(db, current_user, leccion_id, body.model_dump(exclude_unset=True)))


@router.post("/{leccion_id}/estado", summary="Enviar a revisión, validar o archivar")
def estado(leccion_id: str, body: EstadoIn, db: Session = Depends(get_db),
           current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=svc.cambiar_estado(db, current_user, leccion_id, body.estado))


@router.delete("/{leccion_id}", summary="Borrar una lección (admin; lo normal es archivarla)")
def borrar(leccion_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    svc.borrar(db, current_user, leccion_id)
    return APIResponse.ok(data={"ok": True})


@router.post("/{leccion_id}/valoracion", summary="Decir si una recomendación sirvió")
def valorar(leccion_id: str, body: ValoracionIn, db: Session = Depends(get_db),
            current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=svc.valorar(db, current_user, leccion_id, body.contexto_tipo, body.contexto_id,
                                           body.valor, body.nota))


@router.post("/{leccion_id}/acciones", summary="Añadir una acción de mejora")
def crear_accion(leccion_id: str, body: AccionIn, db: Session = Depends(get_db),
                 current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=svc.crear_accion(db, current_user, leccion_id, body.descripcion, body.responsable_id,
                                                body.fecha_limite))
