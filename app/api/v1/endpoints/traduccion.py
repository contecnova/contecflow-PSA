"""Traduccion en tiempo real operador <-> cliente (16-11-2026).

- `GET  /translation/config`: si la empresa traduce, proveedor, canales, el
  idioma de quien pregunta y los idiomas admitidos.
- `POST /translation/messages`: mensajes guardados en el idioma de quien mira.
- `POST /translation/text`: un texto suelto (`/traducir` del editor, chat interno).
- `POST /translation/outbound/preview`: vista previa de una respuesta en el
  idioma del cliente.
- `/translation/glossary`: glosario de la empresa (lectura: agentes;
  cambios: administradores).
- `GET  /translation/usage`, `POST /translation/test`: pantalla de
  administracion (administradores).
- `/translation/kb/{article_id}`: versiones de un articulo en los idiomas del
  portal, con revision.

Los errores de negocio son codigos `trad_*` que la interfaz traduce.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin, require_internal_user
from app.core.errores import ErrorDeDominio
from app.core.responses import APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.traduccion import ajustes, glosario, kb, mensajes, salida, servicio
from app.services.traduccion.idiomas import IDIOMAS, IDIOMAS_DE_OPERADOR, IDIOMAS_DEL_PORTAL, normalizar

router = APIRouter()

#: Largo maximo de un texto suelto (editor, vista previa).
MAX_TEXTO = 20000
#: Canales que puede pedir `POST /translation/text` (los demas van por sus rutas).
CANALES_DE_TEXTO = ("editor", "internal_chat", "kb")


class ElementoIn(BaseModel):
    type: str = Field(..., max_length=30)
    id: str = Field(..., max_length=36)


class MensajesIn(BaseModel):
    items: list[ElementoIn] = Field(..., max_length=mensajes.MAX_POR_PETICION)
    target_language: Optional[str] = Field(None, max_length=16)


class TextoIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXTO)
    target_language: str = Field(..., max_length=16)
    source_language: Optional[str] = Field(None, max_length=16)
    channel: str = Field("editor", max_length=30)


class VistaPreviaIn(BaseModel):
    context_type: str = Field(..., pattern="^(ticket|conversation)$")
    context_id: str = Field(..., max_length=36)
    text: str = Field(..., min_length=1, max_length=MAX_TEXTO)
    target_language: Optional[str] = Field(None, max_length=16)


class TerminoIn(BaseModel):
    term: Optional[str] = Field(None, max_length=glosario.MAX_TERMINO)
    translations: Optional[dict[str, str]] = None
    case_sensitive: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None


class PruebaIn(BaseModel):
    provider: Optional[str] = Field(None, pattern="^(ai|deepl|azure)$")
    target_language: str = Field(..., max_length=16)
    text: str = Field(..., min_length=1, max_length=2000)


class GenerarIn(BaseModel):
    languages: Optional[list[str]] = Field(None, max_length=len(IDIOMAS_DEL_PORTAL))


class VersionIn(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    summary: Optional[str] = Field(None, max_length=500)
    body: Optional[str] = Field(None, max_length=200000)


class RevisionIn(BaseModel):
    publish: bool
    comment: Optional[str] = Field(None, max_length=500)


def _exigir_empresa(user: User) -> str:
    if not user.organization_id:
        raise ErrorDeDominio(422, "trad_sin_empresa")
    return user.organization_id


# ── Configuracion para la interfaz ───────────────────────────────────────────

@router.get("/config", summary="Traducción: configuración efectiva para quien pregunta")
def config(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    org = current_user.organization_id
    return APIResponse.ok(data={
        "enabled": ajustes.habilitada(db, org),
        "provider": ajustes.proveedor(db, org),
        "channels": sorted(ajustes.canales(db, org)),
        "include_original": ajustes.incluir_original(db, org),
        "outbound_auto": ajustes.salida_automatica(db, org),
        "my_language": mensajes.idioma_de_usuario(db, current_user),
        "languages": list(IDIOMAS),
        "operator_languages": list(IDIOMAS_DE_OPERADOR),
        "portal_languages": list(IDIOMAS_DEL_PORTAL),
    })


# ── Entrada: mensajes en el idioma de quien mira ─────────────────────────────

@router.post("/messages", summary="Traducción: mensajes guardados en el idioma de quien mira")
def traducir_mensajes(payload: MensajesIn, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    from app.services.politica_de_visibilidad import es_externo
    if es_externo(current_user) and any(i.type != "chat_message" for i in payload.items):
        raise ErrorDeDominio(403, "trad_sin_permiso")
    return APIResponse.ok(data=mensajes.traducir_mensajes(
        db, current_user, [i.model_dump() for i in payload.items], payload.target_language))


@router.post("/text", summary="Traducción: un texto suelto (editor, chat interno)")
def traducir_texto(payload: TextoIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    org = _exigir_empresa(current_user)
    if payload.channel not in CANALES_DE_TEXTO:
        raise ErrorDeDominio(422, "trad_canal_desconocido")
    if not normalizar(payload.target_language):
        raise ErrorDeDominio(422, "trad_idioma_no_soportado")
    r = servicio.traducir_texto(db, org, payload.text, payload.target_language, canal=payload.channel,
                                origen=payload.source_language, user_id=current_user.id)
    return APIResponse.ok(data=r.como_dict())


# ── Salida: vista previa en el idioma del cliente ────────────────────────────

@router.post("/outbound/preview", summary="Traducción: vista previa de una respuesta en el idioma del cliente")
def vista_previa(payload: VistaPreviaIn, db: Session = Depends(get_db),
                 current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=salida.vista_previa(db, current_user, payload.context_type, payload.context_id,
                                                   payload.text, payload.target_language))


# ── Glosario ─────────────────────────────────────────────────────────────────

@router.get("/glossary", summary="Traducción: glosario de la empresa")
def listar_glosario(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data={"items": glosario.listar(db, _exigir_empresa(current_user))})


@router.post("/glossary", summary="Traducción: nuevo término del glosario (admin)")
def crear_termino(payload: TerminoIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return APIResponse.ok(data=glosario.crear(db, current_user, payload.model_dump()))


@router.patch("/glossary/{termino_id}", summary="Traducción: cambiar un término del glosario (admin)")
def cambiar_termino(termino_id: str, payload: TerminoIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_admin)):
    return APIResponse.ok(data=glosario.actualizar(db, current_user, termino_id,
                                                   payload.model_dump(exclude_unset=True)))


@router.delete("/glossary/{termino_id}", summary="Traducción: borrar un término del glosario (admin)")
def borrar_termino(termino_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    glosario.borrar(db, current_user, termino_id)
    return APIResponse.ok(data={"ok": True})


# ── Administracion ───────────────────────────────────────────────────────────

@router.get("/usage", summary="Traducción: cache, mensajes traducidos y gasto de hoy (admin)")
def uso(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return APIResponse.ok(data=servicio.uso_de_la_empresa(db, _exigir_empresa(current_user)))


@router.post("/test", summary="Traducción: probar el proveedor con un texto (admin)")
def probar(payload: PruebaIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    org = _exigir_empresa(current_user)
    return APIResponse.ok(data=servicio.probar(db, org, payload.provider or ajustes.proveedor(db, org),
                                               payload.target_language, payload.text))


# ── Base de conocimiento ─────────────────────────────────────────────────────

@router.get("/kb/{article_id}", summary="Traducción: versiones de un artículo en los idiomas del portal")
def versiones_kb(article_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=kb.listar(db, current_user, article_id))


@router.post("/kb/{article_id}/generate", summary="Traducción: generar las versiones (quedan en revisión)")
def generar_kb(article_id: str, payload: GenerarIn, db: Session = Depends(get_db),
               current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=kb.generar(db, current_user, article_id, payload.languages))


@router.patch("/kb/{article_id}/{language}", summary="Traducción: corregir una versión (vuelve a revisión)")
def editar_kb(article_id: str, language: str, payload: VersionIn, db: Session = Depends(get_db),
              current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=kb.editar(db, current_user, article_id, language, payload.model_dump()))


@router.post("/kb/{article_id}/{language}/review", summary="Traducción: publicar o rechazar una versión")
def revisar_kb(article_id: str, language: str, payload: RevisionIn, db: Session = Depends(get_db),
               current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=kb.revisar(db, current_user, article_id, language, payload.publish, payload.comment))


@router.delete("/kb/{article_id}/{language}", summary="Traducción: borrar una versión")
def borrar_kb(article_id: str, language: str, db: Session = Depends(get_db),
              current_user: User = Depends(require_internal_user)):
    kb.borrar(db, current_user, article_id, language)
    return APIResponse.ok(data={"ok": True})
