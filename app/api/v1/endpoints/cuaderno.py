"""«Mi cuaderno» (migración 202): `/notebook/*`. Diseño, permisos y GRC en docs/CUADERNO.md.

Capacidades (`app/core/capacidades.py`), literales en cada firma:
- `cuaderno.usar`: todo lo de la persona (sus cuadernos y lo compartido con ella).
- `cuaderno.config`: Configuración › Mi cuaderno (etiquetas por defecto,
  plantillas, baja, papelera, IA y voz).
- `cuaderno.acceso_excepcional`: leer los cuadernos de otra persona con un
  bloqueo legal activo o una solicitud RGPD en curso (auditado).

Privado por defecto: lo que la persona no puede ver responde 404
(`app/services/cuaderno/acceso.py`). Los servicios no confirman: confirma la ruta.
No es para el portal de clientes (que usa otra sesión y no tiene estas capacidades).
"""
from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import requiere_capacidad
from app.core.network import ip_del_cliente
from app.core.ratelimit import limiter
from app.core.responses import APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.transaccion import confirmar
from app.services.cuaderno import (acciones, adjuntos, compartir, config, exportar, ia, plantillas, reuniones,
                                   rgpd, servicio)
from app.services.cuaderno.acceso import DUENO

router = APIRouter()


def _org(u: User):
    return getattr(u, "organization_id", None)


def _ok(db: Session, data: Any = None):
    # La transacción la confirma el servicio común (`app.services.transaccion`), no la capa API.
    confirmar(db)
    return APIResponse.ok(data=data if data is not None else {"ok": True})


def _descarga(contenido: bytes, nombre: str, mime: str, en_linea: bool = False) -> Response:
    from urllib.parse import quote
    disp = "inline" if en_linea else "attachment"
    return Response(content=contenido, media_type=mime, headers={
        "Content-Disposition": f"{disp}; filename*=UTF-8''{quote(nombre)}",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox",
        "Cache-Control": "private, max-age=300",
    })


def _idioma(db: Session, u: User) -> str:
    from app.services.formato_regional import idioma_de_salida
    return idioma_de_salida(db, user_id=u.id, org_id=_org(u))


# ── Esquemas ──────────────────────────────────────────────────────────────────

class CuadernoIn(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    color: Optional[str] = Field(None, max_length=20)
    section_title: Optional[str] = Field(None, max_length=200)


class SeccionIn(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    color: Optional[str] = Field(None, max_length=20)
    notebook_id: Optional[str] = Field(None, max_length=36)


class PaginaIn(BaseModel):
    title: Optional[str] = Field(None, max_length=300)
    parent_id: Optional[str] = Field(None, max_length=36)
    template_key: Optional[str] = Field(None, max_length=60)
    content: Optional[Any] = None


class ContenidoIn(BaseModel):
    content: Optional[Any] = None
    title: Optional[str] = Field(None, max_length=300)
    base_version: Optional[int] = None
    collab: bool = False
    yjs_state: Optional[str] = Field(None, max_length=8 * 1024 * 1024)


class MoverIn(BaseModel):
    title: Optional[str] = Field(None, max_length=300)
    section_id: Optional[str] = Field(None, max_length=36)
    parent_id: Optional[str] = Field(None, max_length=36)
    sort_order: Optional[int] = None
    detach: bool = False


class OrdenIn(BaseModel):
    kind: str = Field(..., pattern=r"^(notebook|section|page)$")
    ids: List[str] = Field(..., max_length=2000)


class CompartirIn(BaseModel):
    # `agents` (23-11-2026): los agentes de código del propio dueño por MCP (solo lectura).
    target_type: str = Field(..., pattern=r"^(user|team|department|agents)$")
    target_id: str = Field(..., min_length=1, max_length=200)
    permission: str = Field("read", pattern=r"^(read|edit)$")
    section_id: Optional[str] = Field(None, max_length=36)


class PermisoIn(BaseModel):
    permission: str = Field(..., pattern=r"^(read|edit)$")


class CasillaIn(BaseModel):
    checked: bool


class EtiquetaIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=80)
    color: Optional[str] = Field(None, max_length=20)
    icon: Optional[str] = Field(None, max_length=30)


class RefsIn(BaseModel):
    refs: List[dict] = Field(default_factory=list, max_length=200)


class AccionIn(BaseModel):
    kind: str = Field(..., pattern=r"^(task|ticket|demand|proposal|event)$")
    text: Optional[str] = Field(None, max_length=10000)
    title: Optional[str] = Field(None, max_length=255)
    project_id: Optional[str] = Field(None, max_length=36)
    due_date: Optional[str] = Field(None, max_length=10)
    start: Optional[str] = Field(None, max_length=40)
    end: Optional[str] = Field(None, max_length=40)
    duration_min: Optional[int] = Field(None, ge=5, le=24 * 60)
    type_key: Optional[str] = Field(None, max_length=60)
    block_id: Optional[str] = Field(None, max_length=40)


class DibujoIn(BaseModel):
    width: float = 800
    height: float = 500
    strokes: List[dict] = Field(default_factory=list, max_length=2000)


class IaIn(BaseModel):
    action: str = Field(..., pattern=r"^(summarize|extract_tasks|organize)$")


class VolcadoIn(BaseModel):
    section_id: Optional[str] = Field(None, max_length=36)


class RapidaIn(BaseModel):
    title: Optional[str] = Field(None, max_length=300)
    text: Optional[str] = Field(None, max_length=20000)


class PlantillaIn(BaseModel):
    key: str = Field(..., pattern=r"^[a-z][a-z0-9_]{0,59}$")
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    content: Optional[Any] = None
    is_active: bool = True
    sort_order: int = 0


class AccesoExcepcionalIn(BaseModel):
    legal_hold_id: Optional[str] = Field(None, max_length=36)
    gdpr_request_id: Optional[str] = Field(None, max_length=36)
    justification: str = Field(..., min_length=10, max_length=2000)
    format: str = Field("md", pattern=r"^(md|pdf)$")


# ── Árbol, cuadernos y secciones ─────────────────────────────────────────────

@router.get("/tree", summary="Mis cuadernos y lo compartido conmigo")
def arbol(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    datos = servicio.arbol(db, current_user)
    datos["tags"] = servicio.etiquetas(db, current_user)
    cfg = config.leer(db, _org(current_user))
    datos["features"] = {"ai": bool(cfg.get("ai_enabled")), "voice": bool(cfg.get("voice_enabled")),
                         "sharing": cfg.get("sharing")}
    return _ok(db, datos)


@router.post("/notebooks", summary="Crear un cuaderno")
def crear_cuaderno(body: CuadernoIn, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    nb = servicio.crear_cuaderno(db, current_user, body.model_dump(exclude_none=True))
    return _ok(db, {"id": nb.id, "title": nb.title})


@router.patch("/notebooks/{nb_id}", summary="Renombrar o cambiar el color de un cuaderno")
def editar_cuaderno(nb_id: str, body: CuadernoIn, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    nb = servicio.editar_cuaderno(db, current_user, nb_id, body.model_dump(exclude_none=True))
    return _ok(db, {"id": nb.id, "title": nb.title, "color": nb.color})


@router.delete("/notebooks/{nb_id}", summary="Mandar un cuaderno a la papelera")
def borrar_cuaderno(nb_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    servicio.borrar_cuaderno(db, current_user, nb_id)
    return _ok(db)


@router.post("/notebooks/{nb_id}/sections", summary="Crear una sección")
def crear_seccion(nb_id: str, body: SeccionIn, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    s = servicio.crear_seccion(db, current_user, nb_id, body.model_dump(exclude_none=True))
    return _ok(db, {"id": s.id, "title": s.title, "color": s.color})


@router.patch("/sections/{sec_id}", summary="Renombrar, colorear o mover una sección")
def editar_seccion(sec_id: str, body: SeccionIn, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    s = servicio.editar_seccion(db, current_user, sec_id, body.model_dump(exclude_none=True))
    return _ok(db, {"id": s.id, "title": s.title, "color": s.color, "notebook_id": s.notebook_id})


@router.delete("/sections/{sec_id}", summary="Mandar una sección a la papelera")
def borrar_seccion(sec_id: str, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    servicio.borrar_seccion(db, current_user, sec_id)
    return _ok(db)


@router.post("/reorder", summary="Orden libre de cuadernos, secciones o páginas")
def reordenar(body: OrdenIn, db: Session = Depends(get_db),
              current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    servicio.reordenar(db, current_user, body.kind, body.ids)
    return _ok(db)


# ── Compartir ────────────────────────────────────────────────────────────────

@router.get("/notebooks/{nb_id}/shares", summary="Con quién está compartido el cuaderno")
def listar_comparticiones(nb_id: str, db: Session = Depends(get_db),
                          current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return APIResponse.ok(data=compartir.listar(db, current_user, nb_id))


@router.post("/notebooks/{nb_id}/shares", summary="Compartir el cuaderno o una sección (auditado)")
def compartir_cuaderno(nb_id: str, body: CompartirIn, db: Session = Depends(get_db),
                       current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return _ok(db, compartir.compartir(db, current_user, nb_id, body.model_dump()))


@router.patch("/shares/{share_id}", summary="Cambiar el permiso compartido (auditado)")
def cambiar_permiso(share_id: str, body: PermisoIn, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return _ok(db, compartir.cambiar(db, current_user, share_id, body.permission))


@router.delete("/shares/{share_id}", summary="Dejar de compartir (auditado)")
def quitar_comparticion(share_id: str, db: Session = Depends(get_db),
                        current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    compartir.quitar(db, current_user, share_id)
    return _ok(db)


@router.get("/share-targets", summary="Equipos y departamentos con los que se puede compartir")
def destinos(q: str = Query("", max_length=100), db: Session = Depends(get_db),
             current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return APIResponse.ok(data=compartir.destinos(db, current_user, q))


# ── Páginas ──────────────────────────────────────────────────────────────────

@router.post("/sections/{sec_id}/pages", summary="Crear una página o subpágina (opcional: desde plantilla)")
def crear_pagina(sec_id: str, body: PaginaIn, db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    p = servicio.crear_pagina(db, current_user, sec_id, body.model_dump(exclude_none=True))
    confirmar(db)
    return APIResponse.ok(data=servicio.detalle(db, current_user, p.id))


@router.get("/pages/{page_id}", summary="Una página con su contenido")
def pagina(page_id: str, db: Session = Depends(get_db),
           current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    datos = servicio.detalle(db, current_user, page_id)
    if datos["permission"] != DUENO:
        acciones.redactar(db, current_user, datos["content"])
    return APIResponse.ok(data=datos)


@router.put("/pages/{page_id}/content", summary="Guardado automático del contenido")
@limiter.limit("240/minute")
def guardar_contenido(request: Request, page_id: str, body: ContenidoIn, db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return _ok(db, servicio.guardar_contenido(db, current_user, page_id, body.model_dump(exclude_unset=True)))


@router.get("/pages/{page_id}/collab", summary="Estado de colaboración (Yjs) de la página")
def estado_colaborativo(page_id: str, db: Session = Depends(get_db),
                        current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    from app.services.cuaderno import acceso, colaboracion
    acceso.pagina(db, current_user, page_id)
    return APIResponse.ok(data={"state": colaboracion.cargar(db, page_id)})


@router.patch("/pages/{page_id}", summary="Renombrar, mover o cambiar de padre una página")
def mover_pagina(page_id: str, body: MoverIn, db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    datos = body.model_dump(exclude_unset=True)
    if datos.pop("detach", False):
        datos["parent_id"] = None
    titulo = datos.pop("title", None)
    if titulo is not None:
        servicio.guardar_contenido(db, current_user, page_id, {"title": titulo})
    if datos:
        servicio.mover_pagina(db, current_user, page_id, datos)
    confirmar(db)
    return APIResponse.ok(data={"id": page_id})


@router.delete("/pages/{page_id}", summary="Mandar una página (y sus subpáginas) a la papelera")
def borrar_pagina(page_id: str, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    servicio.borrar_pagina(db, current_user, page_id)
    return _ok(db)


# ── Notas rápidas (panel lateral) ────────────────────────────────────────────

@router.get("/quick", summary="Notas rápidas y páginas recientes (panel lateral)")
def rapidas(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return APIResponse.ok(data=servicio.panel_rapido(db, current_user))


@router.post("/quick", summary="Nueva nota rápida")
def nueva_rapida(body: RapidaIn, db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    _, sec = servicio.cuaderno_rapido(db, current_user)
    datos: dict = {"title": body.title or ""}
    if body.text:
        datos["content"] = {"type": "doc", "content": [{"type": "paragraph", "content": [
            {"type": "text", "text": linea}]} if linea else {"type": "paragraph"} for linea in body.text.split("\n")]}
    p = servicio.crear_pagina(db, current_user, sec.id, datos)
    confirmar(db)
    return APIResponse.ok(data=servicio.detalle(db, current_user, p.id))


# ── Papelera ─────────────────────────────────────────────────────────────────

@router.get("/trash", summary="Mi papelera")
def papelera(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return APIResponse.ok(data=servicio.papelera(db, current_user))


@router.post("/trash/{kind}/{oid}/restore", summary="Restaurar de la papelera")
def restaurar(kind: str, oid: str, db: Session = Depends(get_db),
              current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    servicio.restaurar(db, current_user, kind, oid)
    return _ok(db)


@router.delete("/trash/{kind}/{oid}", summary="Borrar definitivamente (respeta el bloqueo legal)")
def purgar(kind: str, oid: str, db: Session = Depends(get_db),
           current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    servicio.purgar(db, current_user, kind, oid)
    return _ok(db)


@router.delete("/trash", summary="Vaciar la papelera")
def vaciar(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return _ok(db, {"deleted": servicio.vaciar_papelera(db, current_user)})


# ── Búsqueda, tareas y etiquetas ─────────────────────────────────────────────

@router.get("/search", summary="Buscar en mis cuadernos (y lo compartido conmigo)")
def buscar(q: str = Query(..., min_length=2, max_length=200), notebook_id: Optional[str] = None,
           db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return APIResponse.ok(data=servicio.buscar(db, current_user, q, notebook_id))


@router.get("/items", summary="Todas mis tareas y etiquetas")
def elementos(kind: Optional[str] = Query(None, pattern=r"^(todo|tag)$"),
              status: str = Query("open", pattern=r"^(open|done|all)$"), tag: Optional[str] = Query(None, max_length=40),
              db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return APIResponse.ok(data=servicio.elementos(db, current_user, kind, status, tag))


@router.patch("/items/{item_id}", summary="Marcar o desmarcar una casilla desde la vista agregada")
def marcar(item_id: str, body: CasillaIn, db: Session = Depends(get_db),
           current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return _ok(db, servicio.marcar_casilla(db, current_user, item_id, body.checked))


@router.get("/tags", summary="Etiquetas (las de la empresa y las mías)")
def etiquetas(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return APIResponse.ok(data=servicio.etiquetas(db, current_user))


@router.post("/tags", summary="Crear una etiqueta propia")
def crear_etiqueta(body: EtiquetaIn, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return _ok(db, servicio.crear_etiqueta(db, current_user, body.model_dump(exclude_none=True)))


@router.delete("/tags/{tag_id}", summary="Borrar una etiqueta propia")
def borrar_etiqueta(tag_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    servicio.borrar_etiqueta(db, current_user, tag_id)
    return _ok(db)


@router.get("/templates", summary="Plantillas disponibles")
def plantillas_activas(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    lista = plantillas.listar(db, _org(current_user), _idioma(db, current_user), solo_activas=True)
    return APIResponse.ok(data=[{k: v for k, v in p.items() if k != "content"} for p in lista])


# ── Enlaces vivos y de nota a acción ─────────────────────────────────────────

@router.get("/refs", summary="Buscar para un chip: # (tareas, tickets, proyectos, clientes) o @ (personas)")
@limiter.limit("120/minute")
def referencias(request: Request, q: str = Query("", max_length=100), types: Optional[str] = Query(None, max_length=60),
                db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    tipos = [t for t in (types or "").split(",") if t] or None
    return APIResponse.ok(data=acciones.buscar(db, current_user, q, tipos))


@router.post("/chips/resolve", summary="Estado actual de los chips (solo lo que el lector puede ver)")
@limiter.limit("240/minute")
def resolver_chips(request: Request, body: RefsIn, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return APIResponse.ok(data=acciones.resolver(db, current_user, body.refs))


@router.post("/pages/{page_id}/actions", summary="De nota a acción: tarea, ticket, demanda, idea o recordatorio")
@limiter.limit("60/minute")
def convertir(request: Request, page_id: str, body: AccionIn, db: Session = Depends(get_db),
              current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return _ok(db, acciones.convertir(db, current_user, page_id, body.model_dump(exclude_none=True)))


@router.get("/backlinks", summary="Notas que enlazan un objeto (enlace de vuelta)")
def vinculos(type: str = Query(..., pattern=r"^(task|ticket|project|client|demand|proposal|event|user)$"),
             id: str = Query(..., max_length=36), db: Session = Depends(get_db),
             current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return APIResponse.ok(data=acciones.vinculos_de(db, current_user, type, id))


# ── Adjuntos, dibujos y voz ──────────────────────────────────────────────────

@router.post("/pages/{page_id}/attachments", summary="Adjuntar un fichero o una imagen (validador de subidas)")
@limiter.limit("60/minute")
def subir(request: Request, page_id: str, file: UploadFile = File(...), db: Session = Depends(get_db),
          current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return _ok(db, adjuntos.subir(db, current_user, page_id, file))


@router.get("/attachments/{att_id}/file", summary="Descargar o ver un adjunto")
def fichero(att_id: str, download: bool = False, db: Session = Depends(get_db),
            current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    datos, mime, nombre, en_linea = adjuntos.leer(db, current_user, att_id)
    return _descarga(datos, nombre, mime, en_linea and not download)


@router.delete("/attachments/{att_id}", summary="Borrar un adjunto")
def borrar_adjunto(att_id: str, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    adjuntos.borrar(db, current_user, att_id)
    return _ok(db)


@router.post("/pages/{page_id}/drawings", summary="Guardar un dibujo nuevo (SVG generado en el servidor)")
@limiter.limit("60/minute")
def nuevo_dibujo(request: Request, page_id: str, body: DibujoIn, db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return _ok(db, adjuntos.dibujo(db, current_user, page_id, body.model_dump()))


@router.get("/drawings/{att_id}", summary="Trazos de un dibujo (para editarlo)")
def leer_dibujo(att_id: str, db: Session = Depends(get_db),
                current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return APIResponse.ok(data=adjuntos.trazos(db, current_user, att_id))


@router.put("/drawings/{att_id}", summary="Cambiar un dibujo")
@limiter.limit("60/minute")
def cambiar_dibujo(request: Request, att_id: str, body: DibujoIn, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    pagina = adjuntos.pagina_del_dibujo(db, att_id)
    return _ok(db, adjuntos.dibujo(db, current_user, pagina, body.model_dump(), att_id))


@router.post("/pages/{page_id}/transcribe", summary="Grabar y transcribir una nota de voz")
@limiter.limit("20/minute")
def transcribir(request: Request, page_id: str, file: UploadFile = File(...),
                language: Optional[str] = Form(None), keep_audio: bool = Form(False), db: Session = Depends(get_db),
                current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return _ok(db, adjuntos.transcribir(db, current_user, page_id, file, language, keep_audio))


@router.post("/pages/{page_id}/ai", summary="IA: resumir, extraer tareas u ordenar ideas")
@limiter.limit("20/minute")
def inteligencia(request: Request, page_id: str, body: IaIn, db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return _ok(db, ia.ejecutar(db, current_user, page_id, body.action))


# ── Exportar y volcar reuniones ──────────────────────────────────────────────

@router.get("/export/{kind}/{oid}", summary="Exportar página, sección o cuaderno a Markdown o PDF (auditado)")
@limiter.limit("30/minute")
def exportar_(request: Request, kind: str, oid: str, format: str = Query("md", pattern=r"^(md|pdf)$"),
              db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    datos, nombre, mime = exportar.exportar(db, current_user, kind, oid, format)
    confirmar(db)
    return _descarga(datos, nombre, mime)


@router.post("/from-meeting/{meeting_id}", summary="Volcar el resumen y las acciones de una reunión a un cuaderno")
def desde_reunion(meeting_id: str, body: Optional[VolcadoIn] = None, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("cuaderno.usar"))):
    return _ok(db, reuniones.volcar(db, current_user, meeting_id, body.section_id if body else None))


# ── Configuración (Configuración › Mi cuaderno) ──────────────────────────────

@router.get("/config", summary="Configuración de Mi cuaderno")
def leer_config(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("cuaderno.config"))):
    return APIResponse.ok(data=config.leer(db, _org(current_user)))


@router.put("/config", summary="Guardar la configuración (auditada)")
@limiter.limit("20/minute")
def guardar_config(request: Request, body: dict = Body(...), db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("cuaderno.config"))):
    return _ok(db, config.guardar(db, _org(current_user), current_user, body))


@router.get("/config/templates", summary="Plantillas (todas, para gestionarlas)")
def todas_las_plantillas(db: Session = Depends(get_db),
                         current_user: User = Depends(requiere_capacidad("cuaderno.config"))):
    return APIResponse.ok(data=plantillas.listar(db, _org(current_user), _idioma(db, current_user)))


@router.put("/config/templates", summary="Crear o cambiar una plantilla (auditado)")
def guardar_plantilla(body: PlantillaIn, db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("cuaderno.config"))):
    return _ok(db, plantillas.guardar(db, _org(current_user), current_user, body.model_dump()))


@router.delete("/config/templates/{key}", summary="Borrar una plantilla propia (la de fábrica vuelve)")
def borrar_plantilla(key: str, db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("cuaderno.config"))):
    plantillas.borrar(db, _org(current_user), current_user, key)
    return _ok(db)


# ── Acceso excepcional (bloqueo legal o solicitud RGPD) ──────────────────────

@router.post("/admin/exceptional-access/{user_id}",
             summary="Leer los cuadernos de una persona con bloqueo legal o solicitud RGPD (auditado)")
@limiter.limit("10/minute")
def acceso_excepcional(request: Request, user_id: str, body: AccesoExcepcionalIn, db: Session = Depends(get_db),
                       current_user: User = Depends(requiere_capacidad("cuaderno.acceso_excepcional"))):
    datos, nombre, mime = rgpd.acceso_excepcional(db, current_user, user_id, body.model_dump(),
                                                  ip=ip_del_cliente(request))
    confirmar(db)
    return _descarga(datos, nombre, mime)
