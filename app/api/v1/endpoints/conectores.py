"""Conectores con contecmind (gestor documental) y contecintelligence (analítica conversacional).

Revisión 2026-11. La lógica vive en `app/services/conectores/`; aquí sólo se
traduce cada fallo con nombre a su código HTTP y a un mensaje que la pantalla
puede enseñar tal cual. El código del fallo viaja en la cabecera
`X-Conector-Codigo` (no_configurado, no_alta, sin_permiso, no_encontrado,
rechazado, no_responde).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_admin, require_internal_user
from app.core.responses import APIResponse
from app.models.user import User
from app.services.conectores import anfitrion, contecintelligence as ci, contecmind as cm
from app.services.conectores.anfitrion import ErrorDeConector

router = APIRouter()

_HTTP = {"no_configurado": 409, "no_alta": 403, "sin_permiso": 403, "no_encontrado": 404,
         "rechazado": 502, "no_responde": 503, "no_listo": 503}


@contextmanager
def _traducir():
    try:
        yield
    except ErrorDeConector as e:
        raise HTTPException(_HTTP.get(e.codigo, 502), e.detalle, headers={"X-Conector-Codigo": e.codigo}) from e


def _producto(clave: str) -> anfitrion.Producto:
    if clave not in anfitrion.PRODUCTOS:
        raise HTTPException(404, f"Conector desconocido: {clave}")
    return anfitrion.PRODUCTOS[clave]


# ── Administración ────────────────────────────────────────────────────────────

@router.get("/estado", summary="Estado de los conectores: llamadas, fallos y latencias de la ventana")
def estado(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.services.conectores.estado import estado as calcular
    return APIResponse.ok(data=calcular(db, current_user.organization_id))


@router.post("/{producto}/probar", summary="Probar la credencial de la aplicación y el alta de la empresa")
def probar(producto: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    p = _producto(producto)
    aplicacion = anfitrion.probar(db, p, current_user.organization_id)
    empresa = anfitrion.probar_con_usuario(db, p, current_user) if aplicacion["ok"] else None
    return APIResponse.ok(data={"aplicacion": aplicacion, "empresa": empresa,
                                "ok": bool(aplicacion["ok"] and empresa and empresa["ok"])})


# ── contecmind ────────────────────────────────────────────────────────────────

class EnlaceIn(BaseModel):
    document_id: str = Field(min_length=1, max_length=64)
    nota: Optional[str] = Field(None, max_length=500)


class PreguntaCarpetaIn(BaseModel):
    pregunta: str = Field(min_length=2, max_length=2000)


@router.get("/contecmind/disponible", summary="Si contecmind está configurado y si este usuario puede subir")
def cm_disponible(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    p = anfitrion.CONTECMIND
    ok = anfitrion.configurado(db, p, current_user.organization_id)
    return APIResponse.ok(data={"configurado": ok, "puede_escribir": ok and anfitrion.puede_escribir(db, p, current_user)})


@router.get("/contecmind/buscar", summary="Buscar documentos en contecmind con los permisos del usuario")
def cm_buscar(q: str = Query(..., min_length=2, max_length=500), limit: Optional[int] = Query(None, ge=1, le=50),
              db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    with _traducir():
        return APIResponse.ok(data={"items": cm.buscar(db, current_user, q, limite=limit)})


@router.get("/contecmind/documentos/{document_id}", summary="Ficha de un documento de contecmind")
def cm_documento(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    with _traducir():
        return APIResponse.ok(data=cm.documento(db, current_user, document_id))


@router.get("/contecmind/documentos/{document_id}/original", summary="Descargar el fichero original")
def cm_original(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    with _traducir():
        contenido, tipo, nombre = cm.original(db, current_user, document_id)
    nombre = (nombre or f"documento-{document_id}").replace('"', "")
    return Response(content=contenido, media_type=tipo,
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/contecmind/documentos/{document_id}/aprobacion", summary="Versiones y aprobación del documento")
def cm_aprobacion(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    with _traducir():
        return APIResponse.ok(data=cm.aprobacion(db, current_user, document_id))


@router.post("/contecmind/documentos/{document_id}/aprobacion", summary="Pedir la aprobación de una versión")
def cm_pedir_aprobacion(document_id: str, version_no: Optional[int] = Query(None, ge=1),
                        db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    with _traducir():
        return APIResponse.ok(data=cm.pedir_aprobacion(db, current_user, document_id, version_no))


@router.get("/contecmind/fichas/{entidad}/{entidad_id}/documentos", summary="Documentos enlazados a una ficha")
def cm_enlaces(entidad: str, entidad_id: str, db: Session = Depends(get_db),
               current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data={"items": cm.enlaces(db, current_user, entidad, entidad_id)})


@router.get("/contecmind/fichas/{entidad}/{entidad_id}/sugerencias",
            summary="Documentos de contecmind que pueden servir para esta ficha")
def cm_sugerencias(entidad: str, entidad_id: str, db: Session = Depends(get_db),
                   current_user: User = Depends(require_internal_user)):
    with _traducir():
        return APIResponse.ok(data={"items": cm.sugerencias(db, current_user, entidad, entidad_id)})


@router.post("/contecmind/fichas/{entidad}/{entidad_id}/documentos", summary="Enlazar un documento de contecmind")
def cm_enlazar(entidad: str, entidad_id: str, body: EnlaceIn, db: Session = Depends(get_db),
               current_user: User = Depends(require_internal_user)):
    with _traducir():
        return APIResponse.ok(data=cm.enlazar(db, current_user, entidad, entidad_id, body.document_id, body.nota))


@router.post("/contecmind/fichas/{entidad}/{entidad_id}/subir",
             summary="Subir un fichero a la carpeta de la ficha en contecmind y enlazarlo")
async def cm_subir(entidad: str, entidad_id: str, file: UploadFile = File(...),
                   titulo: Optional[str] = Form(None, max_length=500), nota: Optional[str] = Form(None, max_length=500),
                   db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    contenido = await file.read()
    from app.core.async_db import run_db
    with _traducir():
        return APIResponse.ok(data=await run_db(cm.subir, db, current_user, entidad, entidad_id, contenido,
                                                file.filename or "documento", file.content_type, titulo, nota))


@router.delete("/contecmind/fichas/{entidad}/{entidad_id}/documentos/{enlace_id}",
               summary="Quitar un enlace (el documento sigue en contecmind)")
def cm_desenlazar(entidad: str, entidad_id: str, enlace_id: str, db: Session = Depends(get_db),
                  current_user: User = Depends(require_internal_user)):
    cm.desenlazar(db, current_user, entidad, entidad_id, enlace_id)
    return APIResponse.ok(data={"ok": True})


@router.get("/contecmind/fichas/{entidad}/{entidad_id}/carpeta",
            summary="La carpeta de la ficha en contecmind y lo que contiene (sin crearla)")
def cm_carpeta(entidad: str, entidad_id: str, db: Session = Depends(get_db),
               current_user: User = Depends(require_internal_user)):
    carpeta = cm.carpeta_de(db, current_user, entidad, entidad_id, crear=False)
    if carpeta is None:
        return APIResponse.ok(data={"carpeta": None, "items": []})
    with _traducir():
        return APIResponse.ok(data={"carpeta": carpeta,
                                    "items": cm.documentos_de_carpeta(db, current_user, carpeta["folder_id"])})


@router.post("/contecmind/fichas/{entidad}/{entidad_id}/preguntar",
             summary="Preguntar a los documentos de la carpeta de la ficha (respuesta con citas)")
def cm_preguntar(entidad: str, entidad_id: str, body: PreguntaCarpetaIn, db: Session = Depends(get_db),
                 current_user: User = Depends(require_internal_user)):
    carpeta = cm.carpeta_de(db, current_user, entidad, entidad_id, crear=False)
    if carpeta is None:
        raise HTTPException(409, "Esta ficha todavía no tiene documentos en contecmind")
    with _traducir():
        return APIResponse.ok(data=cm.preguntar_carpeta(db, current_user, carpeta["folder_id"], body.pregunta))


# ── contecintelligence ────────────────────────────────────────────────────────

class PreguntaIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    source_id: Optional[str] = Field(None, max_length=120)
    conversation_id: Optional[str] = Field(None, max_length=120)


class ConsultaMetricaIn(BaseModel):
    source_id: str = Field(min_length=1, max_length=120)
    query: dict[str, Any]


class VentanaIn(BaseModel):
    column: str = Field(min_length=1, max_length=120)
    start: str = Field(min_length=1, max_length=40)
    end: str = Field(min_length=1, max_length=40)


class ExplicarIn(BaseModel):
    source_id: str = Field(min_length=1, max_length=120)
    metric: str = Field(min_length=1, max_length=120)
    actual: VentanaIn
    anterior: VentanaIn
    dimensions: Optional[list[str]] = None


class AnomaliasIn(BaseModel):
    source_id: str = Field(min_length=1, max_length=120)
    metric: str = Field(min_length=1, max_length=120)
    time_column: str = Field(min_length=1, max_length=120)
    start: str = Field(min_length=1, max_length=40)
    end: str = Field(min_length=1, max_length=40)
    granularity: str = Field("day", pattern="^(hour|day|week|month)$")


class TokenIn(BaseModel):
    source_id: Optional[str] = Field(None, max_length=120)


@router.get("/contecintelligence/disponible", summary="Si contecintelligence está configurado para la empresa")
def ci_disponible(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    from app.services import settings_service
    p = anfitrion.CONTECINTELLIGENCE
    ok = anfitrion.configurado(db, p, current_user.organization_id)
    return APIResponse.ok(data={
        "configurado": ok,
        "analista": ok and anfitrion.puede_escribir(db, p, current_user),
        "fuente_por_defecto": ci.fuente_por_defecto(db, current_user) if ok else None,
        "pasar_preguntas": bool(settings_service.get_runtime_bool(
            db, "CONTECINTELLIGENCE_HANDOFF_ENABLED", current_user.organization_id)),
    })


@router.get("/contecintelligence/fuentes", summary="Fuentes de datos a las que este usuario puede preguntar")
def ci_fuentes(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    with _traducir():
        return APIResponse.ok(data={"items": ci.fuentes(db, current_user)})


@router.post("/contecintelligence/preguntar", summary="Preguntar en lenguaje natural (respuesta con recibo)")
def ci_preguntar(body: PreguntaIn, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    with _traducir():
        return APIResponse.ok(data=ci.preguntar(db, current_user, body.question, body.source_id, body.conversation_id))


@router.post("/contecintelligence/preguntar/directo", summary="Preguntar con el progreso en vivo (SSE)")
def ci_preguntar_directo(body: PreguntaIn, db: Session = Depends(get_db),
                         current_user: User = Depends(require_internal_user)):
    with _traducir():
        eventos = ci.preguntar_en_directo(db, current_user, body.question, body.source_id, body.conversation_id)
    return StreamingResponse(eventos, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/contecintelligence/metricas", summary="Métricas certificadas del catálogo")
def ci_metricas(source_id: Optional[str] = Query(None, max_length=120), db: Session = Depends(get_db),
                current_user: User = Depends(require_internal_user)):
    with _traducir():
        return APIResponse.ok(data={"items": ci.metricas(db, current_user, source_id)})


@router.post("/contecintelligence/metricas/consultar", summary="Consultar una métrica certificada")
def ci_consultar(body: ConsultaMetricaIn, db: Session = Depends(get_db),
                 current_user: User = Depends(require_internal_user)):
    with _traducir():
        return APIResponse.ok(data=ci.consultar_metrica(db, current_user, body.source_id, body.query))


@router.post("/contecintelligence/metricas/explicar", summary="Explicar el cambio de una métrica entre dos periodos")
def ci_explicar(body: ExplicarIn, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    with _traducir():
        return APIResponse.ok(data=ci.explicar_cambio(db, current_user, body.source_id, body.metric,
                                                      body.actual.model_dump(), body.anterior.model_dump(),
                                                      body.dimensions))


@router.post("/contecintelligence/metricas/anomalias", summary="Anomalías de una métrica en un periodo")
def ci_anomalias(body: AnomaliasIn, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    with _traducir():
        return APIResponse.ok(data=ci.anomalias(db, current_user, body.source_id, body.metric, body.time_column,
                                                body.start, body.end, body.granularity))


@router.get("/contecintelligence/recibos/{receipt_id}", summary="El recibo firmado de una respuesta")
def ci_recibo(receipt_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    with _traducir():
        return APIResponse.ok(data=ci.recibo(db, current_user, receipt_id))


@router.get("/contecintelligence/recibos/{receipt_id}/verificar", summary="Verificar la firma de un recibo")
def ci_verificar(receipt_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    with _traducir():
        return APIResponse.ok(data=ci.verificar_recibo(db, current_user, receipt_id))


@router.post("/contecintelligence/token", summary="Token acotado para los componentes incrustables")
def ci_token(body: TokenIn, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    with _traducir():
        return APIResponse.ok(data=ci.token_para_componentes(db, current_user, body.source_id))
