"""Flujo de demanda — API del operador y de los solicitantes internos (migración 195).

Ver docs/FLUJO_DE_DEMANDA.md (§4). Capacidades: `demanda.config` (tipos,
flujos, plantillas), `demanda.ver` (lista, expediente, decidir donde se es
responsable), `demanda.gestionar` (comité, ejecución, crear en nombre de otro).
`/demand/mine/...` lo usa cualquier usuario con sesión (empleado, cliente
interno, proveedor) para sus propias solicitudes, por su canal.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, requiere_capacidad
from app.core.network import ip_del_cliente
from app.core.responses import APIResponse
from app.core.uploads import UploadProfile, read_and_validate_upload_sync, safe_filename
from app.models.user import User
from app.services.demanda import (biblioteca, config, consultas, documentos, ejecucion, entrada, expediente,
                                  resumen_ejecutivo, serializacion)
from app.services.demanda import definicion as D
from app.services.demanda.acceso import de_usuario, puede_gestionar
from app.services.demanda.motor import decidir as decidir_paso
from app.core.codigos_de_error import error
from app.services.formato_regional import IDIOMA_DE_RESPALDO

router = APIRouter()

# Cada ruta cita en literal su capacidad `demanda.*` en la firma: los barridos
# de guardas y capacidades leen el literal de la firma.


def idioma_de(request: Request) -> str:
    """Idioma de la petición (Accept-Language), «es» por defecto."""
    cab = (request.headers.get("accept-language") or IDIOMA_DE_RESPALDO).split(",")[0].strip().lower()
    return (cab[:2] or IDIOMA_DE_RESPALDO) if cab else IDIOMA_DE_RESPALDO


def _ip(request: Request) -> Optional[str]:
    return ip_del_cliente(request)


def _descarga(contenido: bytes, nombre: str, mime: str) -> Response:
    from urllib.parse import quote
    return Response(content=contenido, media_type=mime,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre)}"})


# ── Esquemas ─────────────────────────────────────────────────────────────────

class TipoIn(BaseModel):
    key: Optional[str] = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,59}$")
    name: Optional[str] = Field(default=None, max_length=200)
    name_i18n: Optional[dict[str, str]] = None
    description: Optional[str] = Field(default=None, max_length=2000)
    channels: Optional[list[str]] = None
    scopes: Optional[list[str]] = None
    requires_project: Optional[bool] = None
    allows_standalone: Optional[bool] = None
    flow_id: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class FlujoIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=4000)
    definition: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None


class DefinicionIn(BaseModel):
    definition: dict[str, Any]


class SimularIn(BaseModel):
    definition: dict[str, Any]
    data: dict[str, Any] = Field(default_factory=dict)
    decisions: dict[str, str] = Field(default_factory=dict)


class ExpedienteIn(BaseModel):
    type_key: str = Field(..., max_length=60)
    title: str = Field(..., min_length=3, max_length=255)
    project_id: Optional[str] = None
    scope_kind: Optional[str] = Field(default=None, pattern="^(project|service|asset|none)$")
    scope_ref_id: Optional[str] = None
    client_id: Optional[str] = None
    requester_user_id: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
    submit: bool = False


class CamposIn(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    data: dict[str, Any] = Field(default_factory=dict)
    note: Optional[str] = Field(default=None, max_length=2000)


class DecisionIn(BaseModel):
    step_key: str = Field(..., max_length=60)
    decision: str = Field(..., max_length=30)
    target_phase: Optional[str] = Field(default=None, max_length=60)
    justification: Optional[str] = Field(default=None, max_length=5000)


class ComentarioIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=10000)
    internal: bool = False


class EnviarIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=5000)


class RetirarIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=2000)


class ComiteIn(BaseModel):
    date: datetime


class EjecutarIn(BaseModel):
    mode: str = Field(..., pattern="^(backlog|new_project|portfolio)$")
    name: Optional[str] = Field(default=None, max_length=255)
    pm_id: Optional[str] = None


# ── Configuración ────────────────────────────────────────────────────────────

@router.get("/catalog", summary="Opciones del configurador de flujos de demanda")
def catalogo(request: Request, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("demanda.config"))):
    return APIResponse.ok(data=config.catalogo(db, user, idioma_de(request)))


@router.get("/types", summary="Tipos de solicitud")
def tipos(request: Request, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("demanda.ver"))):
    return APIResponse.ok(data=config.tipos(db, user, idioma_de(request)))


@router.post("/types", summary="Crear tipo de solicitud")
def crear_tipo(payload: TipoIn, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("demanda.config"))):
    return APIResponse.ok(data=config.guardar_tipo(db, user, payload.model_dump(exclude_unset=True)))


@router.patch("/types/{tipo_id}", summary="Editar tipo de solicitud")
def editar_tipo(tipo_id: str, payload: TipoIn, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("demanda.config"))):
    return APIResponse.ok(data=config.guardar_tipo(db, user, payload.model_dump(exclude_unset=True), tipo_id))


@router.get("/flows", summary="Flujos de demanda")
def flujos(db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("demanda.config"))):
    return APIResponse.ok(data=config.flujos(db, user))


@router.post("/flows", summary="Crear flujo")
def crear_flujo(payload: FlujoIn, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("demanda.config"))):
    return APIResponse.ok(data=config.guardar_flujo(db, user, payload.model_dump(exclude_unset=True)))


@router.get("/flows/{flujo_id}", summary="Flujo con su definición")
def flujo(flujo_id: str, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("demanda.config"))):
    return APIResponse.ok(data=config.flujo_dict(config.flujo(db, user, flujo_id), True))


@router.patch("/flows/{flujo_id}", summary="Editar flujo (otra definición sube la versión)")
def editar_flujo(flujo_id: str, payload: FlujoIn, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("demanda.config"))):
    return APIResponse.ok(data=config.guardar_flujo(db, user, payload.model_dump(exclude_unset=True), flujo_id))


@router.post("/flows/validate", summary="Validar una definición")
def validar(payload: DefinicionIn, user: User = Depends(requiere_capacidad("demanda.config"))):
    return APIResponse.ok(data={"errors": D.validar(payload.definition)})


@router.post("/flows/simulate", summary="Simular el recorrido de una definición con unos datos")
def simular(payload: SimularIn, user: User = Depends(requiere_capacidad("demanda.config"))):
    errores = D.validar(payload.definition)
    if errores:
        return APIResponse.ok(data={"errors": errores, "path": [], "end": None, "warnings": []})
    return APIResponse.ok(data={"errors": [], **D.simular(payload.definition, payload.data, payload.decisions)})


@router.post("/flows/diagram", summary="Nodos y aristas de una definición (diseñador visual)")
def diagrama(payload: DefinicionIn, user: User = Depends(requiere_capacidad("demanda.config"))):
    return APIResponse.ok(data=D.diagrama(payload.definition))


@router.get("/flows/{flujo_id}/export", summary="Exportar flujo y sus tipos (JSON)")
def exportar(flujo_id: str, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("demanda.config"))):
    f = config.flujo(db, user, flujo_id)
    tipos_ = config.tipos_de_flujo(db, f)
    return APIResponse.ok(data=biblioteca.exportar(db, f, tipos_))


@router.post("/flows/import", summary="Importar un flujo exportado")
def importar(payload: dict[str, Any], db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("demanda.config"))):
    return APIResponse.ok(data=biblioteca.importar(db, user, payload))


@router.get("/templates", summary="Biblioteca de plantillas")
def plantillas(request: Request, user: User = Depends(requiere_capacidad("demanda.config"))):
    return APIResponse.ok(data=biblioteca.listar(idioma_de(request)))


@router.post("/templates/{clave}/install", summary="Instalar una plantilla en la empresa")
def instalar(clave: str, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("demanda.config"))):
    return APIResponse.ok(data=biblioteca.instalar(db, user, clave))


@router.post("/flows/pilot-template", summary="Instalar la plantilla piloto (CAB y comité)")
def piloto(db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("demanda.config"))):
    return APIResponse.ok(data=biblioteca.instalar(db, user, "nueva_funcionalidad"))


# ── Mis solicitudes (cualquier usuario con sesión: empleado, cliente interno, proveedor) ──

def _canal_de(user: User, canal: Optional[str]) -> str:
    rol = getattr(user.role, "value", user.role)
    if rol == "subcontractor":
        return "supplier_portal"
    return canal if canal in ("internal_portal", "operator") else "operator"


@router.get("/mine/types", summary="Tipos que puedo pedir por mi canal")
def mis_tipos(request: Request, channel: Optional[str] = Query(None), db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    # Misma forma que /portal/demand/types: {types, projects}.
    proyectos = config.proyectos_de_la_organizacion(db, user.organization_id)
    return APIResponse.ok(data={"types": entrada.tipos_del_canal(db, _canal_de(user, channel), user.organization_id,
                                                                 idioma_de(request)), "projects": proyectos})


@router.get("/mine/scope-options", summary="Opciones del alcance: servicios del catálogo o activos (CMDB)")
def opciones_de_alcance(kind: str = Query(..., pattern="^(service|asset)$"), q: Optional[str] = Query(None, max_length=100),
                        db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return APIResponse.ok(data=entrada.opciones_de_alcance(db, user.organization_id, kind, q))


@router.get("/mine", summary="Mis solicitudes")
def mias(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return APIResponse.ok(data=entrada.listar_propios(db, de_usuario(user), idioma_de(request)))


@router.post("/mine", summary="Nueva solicitud propia")
def crear_mia(payload: ExpedienteIn, request: Request, channel: Optional[str] = Query(None),
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    datos = payload.model_dump()
    datos.pop("requester_user_id", None)
    req = entrada.crear_expediente(db, de_usuario(user), _canal_de(user, channel), datos, org_id=user.organization_id)
    return APIResponse.ok(data=entrada.detalle(db, de_usuario(user), req.id, idioma_de(request)))


# ── Expedientes ──────────────────────────────────────────────────────────────

@router.get("/requests", summary="Expedientes de demanda")
def listar(request: Request, status: Optional[str] = Query(None, max_length=20),
           phase: Optional[str] = Query(None, max_length=60), type: Optional[str] = Query(None, max_length=60),
           pending_for_me: bool = Query(False), q: Optional[str] = Query(None, max_length=200),
           db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("demanda.ver"))):
    return APIResponse.ok(data=consultas.listar(db, de_usuario(user), user.organization_id, estado=status, fase=phase,
                                                tipo=type, para_mi=pending_for_me, q=q, idioma=idioma_de(request)))


@router.get("/metrics", summary="Métricas del flujo de demanda")
def metricas(request: Request, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("demanda.ver"))):
    return APIResponse.ok(data=consultas.metricas(db, de_usuario(user), user.organization_id, idioma_de(request)))


@router.post("/requests", summary="Nueva solicitud (operador)")
def crear(payload: ExpedienteIn, request: Request, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("demanda.ver"))):
    req = expediente.crear(db, de_usuario(user), "operator", payload.model_dump(), org_id=user.organization_id)
    return APIResponse.ok(data=serializacion.detalle(db, req, de_usuario(user), idioma_de(request)))


def _req(db: Session, user: User, req_id: str):
    return expediente.obtener(db, user.organization_id, req_id)


@router.get("/requests/{req_id}", summary="Expediente completo")
def detalle(req_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    req = _visible(db, user, req_id)
    return APIResponse.ok(data=serializacion.detalle(db, req, de_usuario(user), idioma_de(request)))


def _visible(db: Session, user: User, req_id: str):
    """El expediente si el usuario lo ve (capacidad `demanda.ver` o es su solicitante)."""
    from app.core.capacidades import CAPACIDADES
    req = _req(db, user, req_id)
    rol = getattr(user.role, "value", user.role)
    if not (expediente.es_solicitante(de_usuario(user), req) or user.is_superadmin
            or rol in CAPACIDADES["demanda.ver"].roles):
        raise error(404, "dem_expediente_no_encontrado")
    return req


@router.patch("/requests/{req_id}/fields", summary="Editar la ficha (campos críticos versionados)")
def editar(req_id: str, payload: CamposIn, request: Request, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    req = _visible(db, user, req_id)
    expediente.editar(db, de_usuario(user), req, payload.title, payload.data, payload.note)
    return APIResponse.ok(data=serializacion.detalle(db, req, de_usuario(user), idioma_de(request)))


@router.post("/requests/{req_id}/submit", summary="Enviar o devolver la información pedida")
def enviar(req_id: str, request: Request, payload: Optional[EnviarIn] = None, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    req = _visible(db, user, req_id)
    expediente.enviar(db, de_usuario(user), req, payload.note if payload else None)
    return APIResponse.ok(data=serializacion.detalle(db, req, de_usuario(user), idioma_de(request)))


@router.post("/requests/{req_id}/decide", summary="Decidir un paso de la fase actual")
def decidir(req_id: str, payload: DecisionIn, request: Request, db: Session = Depends(get_db),
            user: User = Depends(requiere_capacidad("demanda.ver"))):
    req = _req(db, user, req_id)
    decidir_paso(db, req, de_usuario(user), payload.step_key, payload.decision, destino=payload.target_phase,
                 justificacion=payload.justification)
    db.refresh(req)
    return APIResponse.ok(data=serializacion.detalle(db, req, de_usuario(user), idioma_de(request)))


@router.post("/requests/{req_id}/withdraw", summary="Retirar mi solicitud")
def retirar(req_id: str, payload: RetirarIn, request: Request, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    req = _visible(db, user, req_id)
    expediente.retirar(db, de_usuario(user), req, payload.reason)
    return APIResponse.ok(data=serializacion.detalle(db, req, de_usuario(user), idioma_de(request)))


@router.post("/requests/{req_id}/comments", summary="Comentar")
def comentar(req_id: str, payload: ComentarioIn, request: Request, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    req = _visible(db, user, req_id)
    interno = payload.internal and not expediente.es_solicitante(de_usuario(user), req)
    expediente.comentar(db, de_usuario(user), req, payload.body, interno)
    return APIResponse.ok(data=serializacion.detalle(db, req, de_usuario(user), idioma_de(request)))


@router.post("/requests/{req_id}/documents", summary="Adjuntar un documento al expediente")
def subir(req_id: str, request: Request, file: UploadFile = File(...), tag: Optional[str] = Form(None),
          personal_data: bool = Form(False), internal: Optional[bool] = Form(None),
          db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    req = _visible(db, user, req_id)
    actor = de_usuario(user)
    if expediente.es_solicitante(actor, req):
        internal = False
    contenido = read_and_validate_upload_sync(file, UploadProfile.DOCUMENT)
    documentos.subir(db, actor, req, nombre=safe_filename(file.filename), content_type=file.content_type or "",
                     contenido=contenido, etiqueta=tag, datos_personales=personal_data, interno=internal,
                     ip=_ip(request))
    return APIResponse.ok(data=serializacion.detalle(db, req, actor, idioma_de(request)))


@router.get("/requests/{req_id}/documents/{doc_id}/download", summary="Descargar un documento (auditado)")
def bajar(req_id: str, doc_id: str, request: Request, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    req = _visible(db, user, req_id)
    return _descarga(*documentos.descargar(db, de_usuario(user), req, doc_id, _ip(request)))


@router.post("/requests/{req_id}/committee", summary="Agendar el comité (genera el Executive Summary)")
def comite(req_id: str, payload: ComiteIn, request: Request, db: Session = Depends(get_db),
           user: User = Depends(requiere_capacidad("demanda.gestionar"))):
    req = _req(db, user, req_id)
    resumen_ejecutivo.agendar_comite(db, req, de_usuario(user), payload.date, idioma_de(request))
    return APIResponse.ok(data=serializacion.detalle(db, req, de_usuario(user), idioma_de(request)))


@router.post("/requests/{req_id}/executive-summary", summary="Generar el Executive Summary (PDF y PPTX)")
def resumen(req_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("demanda.gestionar"))):
    req = _req(db, user, req_id)
    if req.status == "draft":
        raise error(409, "dem_estado_no_permite", estado=req.status)
    resumen_ejecutivo.generar_y_confirmar(db, req, de_usuario(user), idioma_de(request))
    return APIResponse.ok(data=serializacion.detalle(db, req, de_usuario(user), idioma_de(request)))


@router.post("/requests/{req_id}/execute", summary="Ejecutar un expediente aprobado")
def ejecutar(req_id: str, payload: EjecutarIn, request: Request, db: Session = Depends(get_db),
             user: User = Depends(requiere_capacidad("demanda.gestionar"))):
    req = _req(db, user, req_id)
    ejecucion.ejecutar(db, de_usuario(user), req, payload.mode, {"name": payload.name, "pm_id": payload.pm_id})
    return APIResponse.ok(data=serializacion.detalle(db, req, de_usuario(user), idioma_de(request)))


@router.get("/requests/{req_id}/verify", summary="Comprobar la cadena del log inmutable")
def verificar(req_id: str, db: Session = Depends(get_db), user: User = Depends(requiere_capacidad("demanda.ver"))):
    from app.services.demanda.motor import verificar_cadena
    return APIResponse.ok(data={"ok": verificar_cadena(db, _req(db, user, req_id))})


__all__ = ["router", "idioma_de", "puede_gestionar"]
