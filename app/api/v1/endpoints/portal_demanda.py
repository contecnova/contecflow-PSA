"""Flujo de demanda en el portal de clientes (migración 195).

El cliente pide un cambio en uno de sus proyectos o una nueva funcionalidad
fuera de todo proyecto (iniciativa independiente), según los tipos que la
empresa ofrezca en el canal `client_portal`. Todo pasa por
`app/services/demanda/entrada.py` (el mismo punto de entrada que el portal
interno). El cliente no ve comentarios, documentos ni campos internos, y desde
que la ficha se bloquea solo añade comentarios y anexos registrados.

Necesita `can_request_changes` en el usuario del portal.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.endpoints.client_portal import get_current_client
from app.api.v1.endpoints.demanda import _descarga, _ip, idioma_de
from app.core.codigos_de_error import error
from app.core.responses import APIResponse
from app.db.session import get_db
from app.models.client_portal import ClientUser
from app.services.demanda import entrada
from app.services.demanda.acceso import de_cliente

router = APIRouter()
CANAL = "client_portal"


class NuevaIn(BaseModel):
    type_key: str = Field(..., max_length=60)
    title: str = Field(..., min_length=3, max_length=255)
    project_id: Optional[str] = None
    scope_kind: Optional[str] = Field(default=None, pattern="^(project|service|asset|none)$")
    data: dict[str, Any] = Field(default_factory=dict)
    submit: bool = False


class EditarIn(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    data: dict[str, Any] = Field(default_factory=dict)


class NotaIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=5000)


class ComentarioIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=10000)


class DecisionIn(BaseModel):
    step_key: str = Field(..., max_length=60)
    decision: str = Field(..., max_length=30)
    justification: Optional[str] = Field(default=None, max_length=5000)


class RetirarIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=2000)


def _idioma(request: Request, cliente: ClientUser) -> str:
    return (getattr(cliente, "language", None) or idioma_de(request))[:2]


def _puede_pedir(cliente: ClientUser) -> None:
    if not cliente.can_request_changes:
        raise error(403, "sin_permiso_cambios")


@router.get("/types", summary="Tipos de solicitud que puedo pedir y mis proyectos")
def tipos(request: Request, db: Session = Depends(get_db), cliente: ClientUser = Depends(get_current_client)):
    proyectos = [{"id": p.id, "name": p.name} for p in (cliente.projects or [])]
    if cliente.project_id and all(p["id"] != cliente.project_id for p in proyectos):
        from app.models.project import Project
        p = db.query(Project).filter(Project.id == cliente.project_id).first()
        if p:
            proyectos.insert(0, {"id": p.id, "name": p.name})
    lista = entrada.tipos_del_canal(db, CANAL, cliente.organization_id, _idioma(request, cliente)) \
        if cliente.can_request_changes else []
    return APIResponse.ok(data={"types": lista, "projects": proyectos})


@router.get("/scope-options", summary="Opciones del alcance: servicios del catálogo o activos (CMDB)")
def opciones_de_alcance(kind: str, q: Optional[str] = None, db: Session = Depends(get_db),
                        cliente: ClientUser = Depends(get_current_client)):
    if kind not in ("service", "asset"):
        raise error(422, "dem_alcance_no_permitido", alcance=kind)
    return APIResponse.ok(data=entrada.opciones_de_alcance(db, cliente.organization_id, kind, (q or "")[:100]))


@router.get("/requests", summary="Mis solicitudes")
def listar(request: Request, db: Session = Depends(get_db), cliente: ClientUser = Depends(get_current_client)):
    return APIResponse.ok(data=entrada.listar_propios(db, de_cliente(cliente), _idioma(request, cliente)))


@router.post("/requests", summary="Nueva solicitud (borrador o enviada)")
def crear(payload: NuevaIn, request: Request, db: Session = Depends(get_db),
          cliente: ClientUser = Depends(get_current_client)):
    _puede_pedir(cliente)
    actor = de_cliente(cliente)
    req = entrada.crear_expediente(db, actor, CANAL, payload.model_dump(), org_id=cliente.organization_id,
                        proyectos_permitidos=cliente.get_project_ids())
    return APIResponse.ok(data=entrada.detalle(db, actor, req.id, _idioma(request, cliente)))


@router.get("/requests/{req_id}", summary="Mi solicitud")
def detalle(req_id: str, request: Request, db: Session = Depends(get_db),
            cliente: ClientUser = Depends(get_current_client)):
    return APIResponse.ok(data=entrada.detalle(db, de_cliente(cliente), req_id, _idioma(request, cliente)))


@router.patch("/requests/{req_id}", summary="Editar mi solicitud (si la fase lo permite)")
def editar(req_id: str, payload: EditarIn, request: Request, db: Session = Depends(get_db),
           cliente: ClientUser = Depends(get_current_client)):
    actor = de_cliente(cliente)
    entrada.editar(db, actor, req_id, payload.title, payload.data)
    return APIResponse.ok(data=entrada.detalle(db, actor, req_id, _idioma(request, cliente)))


@router.post("/requests/{req_id}/submit", summary="Enviar o devolver la información pedida")
def enviar(req_id: str, request: Request, payload: Optional[NotaIn] = None, db: Session = Depends(get_db),
           cliente: ClientUser = Depends(get_current_client)):
    actor = de_cliente(cliente)
    entrada.enviar(db, actor, req_id, payload.note if payload else None)
    return APIResponse.ok(data=entrada.detalle(db, actor, req_id, _idioma(request, cliente)))


@router.post("/requests/{req_id}/comments", summary="Comentar")
def comentar(req_id: str, payload: ComentarioIn, request: Request, db: Session = Depends(get_db),
             cliente: ClientUser = Depends(get_current_client)):
    actor = de_cliente(cliente)
    entrada.comentar(db, actor, req_id, payload.body)
    return APIResponse.ok(data=entrada.detalle(db, actor, req_id, _idioma(request, cliente)))


@router.post("/requests/{req_id}/documents", summary="Adjuntar (anexo registrado si la ficha está bloqueada)")
def subir(req_id: str, request: Request, file: UploadFile = File(...), tag: Optional[str] = Form(None),
          personal_data: bool = Form(False), db: Session = Depends(get_db),
          cliente: ClientUser = Depends(get_current_client)):
    actor = de_cliente(cliente)
    entrada.adjuntar(db, actor, req_id, nombre=file.filename or "", content_type=file.content_type or "",
                     contenido=file.file.read(), etiqueta=tag, datos_personales=personal_data, ip=_ip(request))
    return APIResponse.ok(data=entrada.detalle(db, actor, req_id, _idioma(request, cliente)))


@router.get("/requests/{req_id}/documents/{doc_id}/download", summary="Descargar un documento")
def bajar(req_id: str, doc_id: str, request: Request, db: Session = Depends(get_db),
          cliente: ClientUser = Depends(get_current_client)):
    return _descarga(*entrada.descargar(db, de_cliente(cliente), req_id, doc_id, _ip(request)))


@router.post("/requests/{req_id}/withdraw", summary="Retirar mi solicitud")
def retirar(req_id: str, payload: RetirarIn, request: Request, db: Session = Depends(get_db),
            cliente: ClientUser = Depends(get_current_client)):
    actor = de_cliente(cliente)
    entrada.retirar(db, actor, req_id, payload.reason)
    return APIResponse.ok(data=entrada.detalle(db, actor, req_id, _idioma(request, cliente)))


@router.post("/requests/{req_id}/decide", summary="Decidir un paso que me toca a mí (solicitante)")
def decidir(req_id: str, payload: DecisionIn, request: Request, db: Session = Depends(get_db),
            cliente: ClientUser = Depends(get_current_client)):
    actor = de_cliente(cliente)
    entrada.decidir(db, actor, req_id, payload.step_key, payload.decision, payload.justification)
    return APIResponse.ok(data=entrada.detalle(db, actor, req_id, _idioma(request, cliente)))
