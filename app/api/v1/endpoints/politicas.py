"""Políticas y reglas (tarea #26). La lógica vive en `app/services/politicas/`.

Configurar (crear, editar, publicar, simular, tablas) exige administrador; la
matriz GRC (módulo `policies`) puede además quitar el permiso a un rol, y las
políticas ABAC de la empresa se aplican con `enforce_abac` (recurso `policy`).
La explicación de una entidad la ven su dueño, quien la aprueba y un admin.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.deps import get_db, require_admin, require_internal_user
from app.core.errores import ErrorDeDominio
from app.core.responses import APIResponse
from app.models.user import User
from app.services.politicas import servicio as svc
from app.services.politicas import simulador

router = APIRouter()

_MAX_IMPORTACION = 5 * 1024 * 1024


class PoliticaIn(BaseModel):
    dominio: str = Field(..., max_length=40)
    nombre: str = Field(..., max_length=200)
    descripcion: Optional[str] = Field(None, max_length=4000)
    prioridad: int = Field(100, ge=-10000, le=10000)
    activa: bool = True
    vigente_desde: Optional[str] = None
    vigente_hasta: Optional[str] = None
    ambito: dict[str, list[str]] = Field(default_factory=dict)
    nota_de_version: Optional[str] = Field(None, max_length=500)
    reglas: list[dict[str, Any]] = Field(default_factory=list)


class ReglaIn(BaseModel):
    nombre: str = Field(..., max_length=200)
    activa: bool = True
    detener: bool = False
    condicion: Optional[dict[str, Any]] = None
    resultados: list[dict[str, Any]] = Field(default_factory=list)
    exceso: Optional[dict[str, Any]] = None


class ActivacionIn(BaseModel):
    activa: bool


class SimulacionIn(BaseModel):
    politica_id: Optional[str] = None
    documento: Optional[PoliticaIn] = None
    ultimos: Optional[int] = Field(None, ge=1, le=100000)
    desde: Optional[str] = None
    hasta: Optional[str] = None


class TablaIn(BaseModel):
    nombre: str = Field(..., max_length=200)
    descripcion: Optional[str] = Field(None, max_length=4000)
    dominio: Optional[str] = Field(None, max_length=40)
    tipo_de_valor: str = Field("importe", pattern="^(importe|numero)$")
    moneda: Optional[str] = Field(None, max_length=3)


class FilasIn(BaseModel):
    filas: list[dict[str, Any]]


def _abac(db, u, accion="read", rid=None):
    enforce_abac(db, u, "policy", rid, action=accion)


# ── Catálogo y opciones ──────────────────────────────────────────────────────

@router.get("/catalog", summary="Dominios registrados, sus campos tipados, operadores y resultados")
def catalogo(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    _abac(db, current_user)
    return APIResponse.ok(data=svc.catalogo_publico())


@router.get("/options", summary="Valores para los selectores (departamentos, equipos, roles, monedas, grupos…)")
def opciones(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    _abac(db, current_user)
    return APIResponse.ok(data=svc.opciones(db, current_user))


# ── Tablas de referencia (antes que /{politica_id}) ──────────────────────────

@router.get("/tables", summary="Tablas de referencia")
def listar_tablas(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    _abac(db, current_user)
    return APIResponse.ok(data=svc.tablas(db))


@router.post("/tables", summary="Crear tabla de referencia")
def crear_tabla(body: TablaIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    _abac(db, current_user, "create")
    return APIResponse.ok(data=svc.crear_tabla(db, current_user, body.model_dump()))


@router.get("/tables/{tabla_id}", summary="Tabla de referencia con sus filas")
def ver_tabla(tabla_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    _abac(db, current_user, rid=tabla_id)
    return APIResponse.ok(data=svc.tabla(db, tabla_id))


@router.patch("/tables/{tabla_id}", summary="Editar la cabecera de una tabla")
def editar_tabla(tabla_id: str, body: TablaIn, db: Session = Depends(get_db),
                 current_user: User = Depends(require_admin)):
    _abac(db, current_user, "update", tabla_id)
    return APIResponse.ok(data=svc.editar_tabla(db, current_user, tabla_id, body.model_dump()))


@router.delete("/tables/{tabla_id}", summary="Borrar una tabla que ninguna política usa")
def borrar_tabla(tabla_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    _abac(db, current_user, "delete", tabla_id)
    svc.borrar_tabla(db, current_user, tabla_id)
    return APIResponse.ok(data={"ok": True})


@router.put("/tables/{tabla_id}/rows", summary="Guardar las filas de la rejilla (sustituye todas)")
def guardar_filas(tabla_id: str, body: FilasIn, db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin)):
    _abac(db, current_user, "update", tabla_id)
    return APIResponse.ok(data=svc.guardar_filas(db, current_user, tabla_id, body.filas))


@router.post("/tables/{tabla_id}/import", summary="Leer un CSV o XLSX para revisarlo en la rejilla (no guarda)")
async def importar(tabla_id: str, file: UploadFile = File(...), db: Session = Depends(get_db),
                   current_user: User = Depends(require_admin)):
    _abac(db, current_user, "update", tabla_id)
    contenido = await file.read(_MAX_IMPORTACION + 1)
    if len(contenido) > _MAX_IMPORTACION:
        raise ErrorDeDominio(413, "El fichero supera 5 MB")
    return APIResponse.ok(data=svc.importar(db, current_user, tabla_id, contenido, file.filename or ""))


# ── Validar, simular, explicar ───────────────────────────────────────────────

@router.post("/validate", summary="Validar una política sin guardarla")
def validar(body: PoliticaIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    _abac(db, current_user)
    errores = svc.validar(db, current_user, body.model_dump())
    return APIResponse.ok(data={"valida": not errores, "errores": errores})


@router.post("/simulate", summary="Simular una política contra entidades históricas (sin efectos)")
def simular(body: SimulacionIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    _abac(db, current_user)
    return APIResponse.ok(data=simulador.simular(
        db, current_user, politica_id=body.politica_id,
        documento=body.documento.model_dump() if body.documento else None,
        ultimos=body.ultimos, desde=body.desde, hasta=body.hasta))


@router.get("/explanations/{dominio}/{entidad_id}", summary="Por qué: evaluaciones guardadas de una entidad")
def explicar(dominio: str, entidad_id: str, db: Session = Depends(get_db),
             current_user: User = Depends(require_internal_user)):
    _abac(db, current_user, rid=entidad_id)
    return APIResponse.ok(data=svc.explicaciones(db, current_user, dominio, entidad_id))


# ── Políticas ────────────────────────────────────────────────────────────────

@router.get("", summary="Políticas (última versión de cada una), por dominio")
def listar(dominio: Optional[str] = Query(None, max_length=40), db: Session = Depends(get_db),
           current_user: User = Depends(require_admin)):
    _abac(db, current_user)
    return APIResponse.ok(data=svc.listar(db, dominio))


@router.post("", summary="Crear política (borrador v1)")
def crear(body: PoliticaIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    _abac(db, current_user, "create")
    return APIResponse.ok(data=svc.crear(db, current_user, body.model_dump()))


@router.get("/{politica_id}", summary="Detalle de una versión con sus reglas")
def ver(politica_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    _abac(db, current_user, rid=politica_id)
    return APIResponse.ok(data=svc.detalle(db, politica_id))


@router.put("/{politica_id}", summary="Guardar un borrador (cabecera y reglas)")
def guardar(politica_id: str, body: PoliticaIn, db: Session = Depends(get_db),
            current_user: User = Depends(require_admin)):
    _abac(db, current_user, "update", politica_id)
    return APIResponse.ok(data=svc.guardar(db, current_user, politica_id, body.model_dump()))


@router.delete("/{politica_id}", summary="Eliminar un borrador o retirar una versión publicada")
def borrar(politica_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    _abac(db, current_user, "delete", politica_id)
    return APIResponse.ok(data=svc.borrar(db, current_user, politica_id))


@router.post("/{politica_id}/publish", summary="Publicar un borrador (retira la versión publicada anterior)")
def publicar(politica_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    _abac(db, current_user, "update", politica_id)
    return APIResponse.ok(data=svc.publicar(db, current_user, politica_id))


@router.post("/{politica_id}/new-version", summary="Nueva versión (borrador copiado de esta)")
def nueva_version(politica_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    _abac(db, current_user, "create", politica_id)
    return APIResponse.ok(data=svc.nueva_version(db, current_user, politica_id))


@router.post("/{politica_id}/activation", summary="Activar o desactivar una versión")
def activar(politica_id: str, body: ActivacionIn, db: Session = Depends(get_db),
            current_user: User = Depends(require_admin)):
    _abac(db, current_user, "update", politica_id)
    return APIResponse.ok(data=svc.activar(db, current_user, politica_id, body.activa))


@router.get("/{politica_id}/history", summary="Todas las versiones de la política")
def historial(politica_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    _abac(db, current_user, rid=politica_id)
    return APIResponse.ok(data=svc.historial(db, politica_id))


@router.post("/{politica_id}/rules", summary="Añadir una regla a un borrador")
def crear_regla(politica_id: str, body: ReglaIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_admin)):
    _abac(db, current_user, "update", politica_id)
    return APIResponse.ok(data=svc.crear_regla(db, current_user, politica_id, body.model_dump()))


@router.patch("/{politica_id}/rules/{regla_id}", summary="Editar una regla de un borrador")
def editar_regla(politica_id: str, regla_id: str, body: dict = Body(...), db: Session = Depends(get_db),
                 current_user: User = Depends(require_admin)):
    _abac(db, current_user, "update", politica_id)
    return APIResponse.ok(data=svc.editar_regla(db, current_user, politica_id, regla_id, body))


@router.delete("/{politica_id}/rules/{regla_id}", summary="Quitar una regla de un borrador")
def borrar_regla(politica_id: str, regla_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(require_admin)):
    _abac(db, current_user, "update", politica_id)
    return APIResponse.ok(data=svc.borrar_regla(db, current_user, politica_id, regla_id))
