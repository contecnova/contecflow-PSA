"""Asistente de reuniones (19-11-2026): `/meeting-assistant/*` y los avisos firmados
`/webhooks/meetings/*`. Diseño y permisos en `docs/ASISTENTE_DE_REUNIONES.md`.

Capacidades (`app/core/capacidades.py`), como guarda en cada ruta con
`requiere_capacidad` (19-11-2026): `reuniones.usar` = internos (lo que era
`require_internal_user`), `reuniones.config` = admin. Lo que ve
cada uno lo decide `app.services.reuniones.consultas` (404 fuera de lo visible).
Los servicios no confirman: confirma la ruta.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.codigos_de_error import desde_valor
from app.core.deps import get_current_user, requiere_capacidad
from app.core.modulos_ia import exigir_modulo_ia
from app.core.ratelimit import limiter
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.reuniones import config as cfg_mod
from app.services.reuniones import consultas, servicio

router = APIRouter()
router_webhooks = APIRouter()

_IA = [Depends(exigir_modulo_ia("meeting_assistant"))]


def _org(u: User):
    return getattr(u, "organization_id", None)


def _detalle(db: Session, usuario: User, reunion, idioma: Optional[str] = None) -> dict:
    from app.services.formato_regional import idioma_de_salida
    from app.services.reuniones.traduccion import traducir_reunion
    destino = idioma or idioma_de_salida(db, user_id=usuario.id, org_id=_org(usuario))
    traducido = traducir_reunion(db, reunion, destino, usuario)
    return consultas.detalle(db, usuario, reunion, traducido)


def _confirmar(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def _hacer(db: Session, funcion, *args, **kw):
    """Ejecuta un servicio: `ValueError` con código → 4xx; confirma si va bien."""
    try:
        resultado = funcion(*args, **kw)
    except ValueError as exc:
        db.rollback()
        raise desde_valor(422, exc)
    _confirmar(db)
    return resultado


# ── Esquemas ──────────────────────────────────────────────────────────────────

class ParticipanteIn(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    user_id: Optional[str] = None


class ReunionIn(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    origin: str = Field("transcript", pattern=r"^(recording|transcript|upload)$")
    source: Optional[str] = Field(None, pattern=r"^(microphone|tab)$")
    transcript: Optional[str] = Field(None, max_length=2_000_000)
    platform: Optional[str] = Field(None, max_length=30)
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    meeting_date: Optional[str] = None
    duration_min: Optional[int] = Field(None, ge=0, le=24 * 60)
    participants: List[ParticipanteIn] = []
    notice_confirmed: bool = False


class ReunionPatch(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    project_id: Optional[str] = None
    client_id: Optional[str] = None


class SegmentoPatch(BaseModel):
    speaker: Optional[str] = Field(None, max_length=255)
    user_id: Optional[str] = None
    apply_to_speaker: bool = False


class ConsentimientoIn(BaseModel):
    participant_id: Optional[str] = None
    consents: bool
    method: Optional[str] = Field(None, pattern=r"^(self|verbal|written)$")


class AccionPatch(BaseModel):
    description: Optional[str] = Field(None, max_length=4000)
    assignee_id: Optional[str] = None
    due_date: Optional[str] = None


class TareaIn(BaseModel):
    project_id: Optional[str] = None


class TareasIn(BaseModel):
    action_ids: Optional[List[str]] = None
    project_id: Optional[str] = None


class PreguntaIn(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000)


class BotIn(BaseModel):
    meeting_url: str = Field(..., max_length=1000)
    title: Optional[str] = Field(None, max_length=255)
    join_at: Optional[str] = None
    project_id: Optional[str] = None


class ImportarIn(BaseModel):
    platform: str = Field(..., pattern=r"^(teams|zoom|meet)$")
    reference: str = Field(..., min_length=3, max_length=1000)


class PreferenciasIn(BaseModel):
    collect_teams: Optional[bool] = None
    collect_meet: Optional[bool] = None
    bot_for_my_calendar: Optional[bool] = None
    language: Optional[str] = Field(None, max_length=10)


class PersonaIn(BaseModel):
    email: Optional[str] = Field(None, max_length=255)
    user_id: Optional[str] = None


# ── Reuniones ─────────────────────────────────────────────────────────────────

@router.get("/meetings", summary="Reuniones visibles para mí")
def listar(status: Optional[str] = None, project_id: Optional[str] = None, q: Optional[str] = None,
           db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    from sqlalchemy import func
    from app.models.ai_chat import AIMeeting
    consulta = consultas.visibles(db, current_user)
    if status:
        consulta = consulta.filter(AIMeeting.status == status)
    if project_id:
        consulta = consulta.filter(AIMeeting.project_id == project_id)
    if q and q.strip():
        consulta = consulta.filter(func.lower(AIMeeting.title).like(f"%{q.strip().lower()}%"))
    filas = consulta.order_by(AIMeeting.created_at.desc()).limit(200).all()
    return APIListResponse.ok(items=[consultas.resumen(db, current_user, m) for m in filas])


@router.post("/meetings", summary="Alta: grabación propia, transcripción pegada o subida", dependencies=_IA)
@limiter.limit("30/minute")
def crear(request: Request, body: ReunionIn, db: Session = Depends(get_db),
          current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    datos = body.model_dump()
    datos["participants"] = [p for p in datos["participants"] if any(p.values())]
    reunion = _hacer(db, servicio.crear, db, current_user, datos)
    return APIResponse.ok(data=_detalle(db, current_user, reunion))


@router.get("/meetings/{meeting_id}", summary="Detalle (traducido al idioma pedido o al mío)")
def detalle(meeting_id: str, language: Optional[str] = Query(None, max_length=10), db: Session = Depends(get_db),
            current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener(db, current_user, meeting_id)
    datos = _detalle(db, current_user, reunion, language)
    _confirmar(db)   # caché de traducción
    return APIResponse.ok(data=datos)


@router.patch("/meetings/{meeting_id}", summary="Cambiar título, proyecto o cliente")
def actualizar(meeting_id: str, body: ReunionPatch, db: Session = Depends(get_db),
               current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener_gestionable(db, current_user, meeting_id)
    _hacer(db, servicio.actualizar, db, current_user, reunion, body.model_dump(exclude_unset=True))
    return APIResponse.ok(data=_detalle(db, current_user, reunion))


@router.delete("/meetings/{meeting_id}", summary="Borrar la reunión (409 bajo bloqueo legal)")
def borrar(meeting_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener_gestionable(db, current_user, meeting_id)
    _hacer(db, servicio.borrar, db, current_user, reunion)
    return APIResponse.ok(data={"deleted": True})


@router.post("/meetings/{meeting_id}/audio", summary="Subir un trozo de la grabación (se transcribe al llegar)")
@limiter.limit("240/minute")
def subir_audio(request: Request, meeting_id: str, file: UploadFile = File(...), seq: int = Form(0),
                offset_ms: int = Form(0), db: Session = Depends(get_db),
                current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener_gestionable(db, current_user, meeting_id)
    datos = file.file.read(servicio.MAX_TROZO_MB * 1024 * 1024 + 1)
    r = _hacer(db, servicio.subir_audio, db, current_user, reunion, datos, file.content_type or "audio/webm",
               seq, offset_ms)
    return APIResponse.ok(data=r)


@router.post("/meetings/{meeting_id}/finish", summary="Terminar la grabación y analizar", dependencies=_IA)
def terminar(meeting_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener_gestionable(db, current_user, meeting_id)
    _hacer(db, servicio.terminar, db, current_user, reunion)
    return APIResponse.ok(data=_detalle(db, current_user, reunion))


@router.post("/meetings/{meeting_id}/reprocess", summary="Volver a analizar", dependencies=_IA)
def reprocesar(meeting_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener_gestionable(db, current_user, meeting_id)
    _hacer(db, servicio.reprocesar, db, current_user, reunion)
    return APIResponse.ok(data=_detalle(db, current_user, reunion))


@router.get("/meetings/{meeting_id}/audio", summary="Trozos de audio guardados")
def listar_audio(meeting_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener(db, current_user, meeting_id)
    if not consultas.puede_escuchar(db, current_user, reunion):
        return APIListResponse.ok(items=[])
    return APIListResponse.ok(items=[{"id": a.id, "seq": a.seq, "offset_ms": a.offset_ms, "bytes": a.bytes,
                                      "mime": a.mime, "expires_at": consultas._iso(a.expires_at)}
                                     for a in reunion.audios])


@router.get("/meetings/{meeting_id}/audio/{chunk_id}", summary="Escuchar o descargar un trozo (auditado)")
def leer_audio(meeting_id: str, chunk_id: str, download: int = Query(0, ge=0, le=1), db: Session = Depends(get_db),
               current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener(db, current_user, meeting_id)
    datos, tipo, nombre = _hacer(db, servicio.leer_audio, db, current_user, reunion, chunk_id, bool(download))
    cabeceras = {"Cache-Control": "no-store"}
    if download:
        cabeceras["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return Response(content=datos, media_type=tipo, headers=cabeceras)


@router.delete("/meetings/{meeting_id}/audio", summary="Borrar el audio (auditado)")
def borrar_audio(meeting_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener_gestionable(db, current_user, meeting_id)
    n = _hacer(db, servicio.borrar_audio, db, current_user, reunion)
    return APIResponse.ok(data={"deleted_chunks": n})


@router.get("/meetings/{meeting_id}/transcript", summary="Descargar la transcripción (txt, vtt, json; auditado)")
def transcripcion(meeting_id: str, format: str = Query("txt", pattern=r"^(txt|vtt|json)$"),
                  db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener(db, current_user, meeting_id)
    contenido, tipo, nombre = _hacer(db, servicio.exportar_transcripcion, db, current_user, reunion, format)
    return Response(content=contenido.encode("utf-8"), media_type=f"{tipo}; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"', "Cache-Control": "no-store"})


@router.patch("/meetings/{meeting_id}/segments/{segment_id}", summary="Renombrar o asignar el hablante")
def editar_segmento(meeting_id: str, segment_id: str, body: SegmentoPatch, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener_gestionable(db, current_user, meeting_id)
    _hacer(db, servicio.editar_segmento, db, current_user, reunion, segment_id, body.model_dump(exclude_unset=True))
    return APIResponse.ok(data=_detalle(db, current_user, reunion))


@router.post("/meetings/{meeting_id}/participants", summary="Añadir un asistente")
def añadir_participante(meeting_id: str, body: ParticipanteIn, db: Session = Depends(get_db),
                        current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    from app.services.reuniones.eventos import evento
    reunion = consultas.obtener_gestionable(db, current_user, meeting_id)

    def _alta():
        p = servicio.añadir_participante(db, reunion, name=body.name, email=body.email, user_id=body.user_id)
        evento(db, reunion, "participant_added", current_user, {"name": p.name})
        return p
    _hacer(db, _alta)
    return APIResponse.ok(data=_detalle(db, current_user, reunion))


@router.delete("/meetings/{meeting_id}/participants/{participant_id}", summary="Quitar un asistente")
def quitar_participante(meeting_id: str, participant_id: str, db: Session = Depends(get_db),
                        current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener_gestionable(db, current_user, meeting_id)
    _hacer(db, servicio.quitar_participante, db, current_user, reunion, participant_id)
    return APIResponse.ok(data=_detalle(db, current_user, reunion))


@router.post("/meetings/{meeting_id}/consent", summary="Consentimiento (propio, o verbal/escrito de un externo)")
def consentir(meeting_id: str, body: ConsentimientoIn, db: Session = Depends(get_db),
              current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener(db, current_user, meeting_id)
    _hacer(db, servicio.consentir, db, current_user, reunion, body.participant_id, body.consents, body.method)
    return APIResponse.ok(data=_detalle(db, current_user, reunion))


@router.patch("/meetings/{meeting_id}/actions/{action_id}", summary="Editar una acción")
def editar_accion(meeting_id: str, action_id: str, body: AccionPatch, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener_gestionable(db, current_user, meeting_id)
    _hacer(db, servicio.editar_accion, db, current_user, reunion, action_id, body.model_dump(exclude_unset=True))
    return APIResponse.ok(data=_detalle(db, current_user, reunion))


@router.post("/meetings/{meeting_id}/actions/tasks", summary="Crear las tareas de las acciones")
def acciones_a_tareas(meeting_id: str, body: TareasIn = Body(default_factory=TareasIn), db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener_gestionable(db, current_user, meeting_id)
    return APIResponse.ok(data=_hacer(db, servicio.acciones_a_tareas, db, current_user, reunion,
                                      body.action_ids, body.project_id))


@router.post("/meetings/{meeting_id}/actions/{action_id}/task", summary="Acción → tarea")
def accion_a_tarea(meeting_id: str, action_id: str, body: TareaIn = Body(default_factory=TareaIn),
                   db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener_gestionable(db, current_user, meeting_id)
    return APIResponse.ok(data=_hacer(db, servicio.accion_a_tarea, db, current_user, reunion, action_id,
                                      body.project_id))


@router.post("/meetings/{meeting_id}/actions/{action_id}/ticket", summary="Acción → ticket del service desk")
def accion_a_ticket(meeting_id: str, action_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener_gestionable(db, current_user, meeting_id)
    return APIResponse.ok(data=_hacer(db, servicio.accion_a_ticket, db, current_user, reunion, action_id))


@router.post("/meetings/{meeting_id}/minutes", summary="Generar el acta (documento)")
def acta(meeting_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener_gestionable(db, current_user, meeting_id)
    return APIResponse.ok(data=_hacer(db, servicio.generar_acta, db, current_user, reunion))


@router.post("/meetings/{meeting_id}/ask", summary="Preguntar a la IA sobre la reunión", dependencies=_IA)
@limiter.limit("30/minute")
def preguntar(request: Request, meeting_id: str, body: PreguntaIn, db: Session = Depends(get_db),
              current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener(db, current_user, meeting_id)
    return APIResponse.ok(data=_hacer(db, servicio.preguntar, db, current_user, reunion, body.question))


@router.get("/search", summary="Buscar en las reuniones visibles")
def buscar(q: str = Query(..., min_length=2, max_length=200), db: Session = Depends(get_db),
           current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    return APIListResponse.ok(items=servicio.buscar(db, current_user, q))


# ── Bot y plataformas ─────────────────────────────────────────────────────────

@router.post("/bots", summary="Invitar el bot a una reunión (Teams, Zoom, Meet, Webex)", dependencies=_IA)
@limiter.limit("20/minute")
def invitar_bot(request: Request, body: BotIn, db: Session = Depends(get_db),
                current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = _hacer(db, servicio.invitar_bot, db, current_user, body.model_dump())
    return APIResponse.ok(data=_detalle(db, current_user, reunion))


@router.post("/meetings/{meeting_id}/bot/leave", summary="Sacar el bot de la llamada")
def sacar_bot(meeting_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = consultas.obtener_gestionable(db, current_user, meeting_id)
    _hacer(db, servicio.sacar_bot, db, current_user, reunion)
    return APIResponse.ok(data=_detalle(db, current_user, reunion))


@router.post("/import", summary="Traer una reunión de Teams, Zoom o Meet", dependencies=_IA)
@limiter.limit("20/minute")
def importar(request: Request, body: ImportarIn, db: Session = Depends(get_db),
             current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    reunion = _hacer(db, servicio.importar, db, current_user, body.platform, body.reference)
    reunion = consultas.obtener(db, current_user, reunion.id)
    return APIResponse.ok(data=_detalle(db, current_user, reunion))


# ── Cuarta vía: llamadas del chat interno ─────────────────────────────────────

class ActivarLlamadaIn(BaseModel):
    notice_confirmed: bool = False


@router.get("/calls/{call_id}", summary="Estado del asistente en una llamada del chat")
def estado_en_llamada(call_id: str, db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    from app.services.reuniones import llamadas
    return APIResponse.ok(data=llamadas.estado(db, current_user, call_id))


@router.post("/calls/{call_id}/activate", summary="Activar el asistente en la llamada (aviso obligatorio)",
             dependencies=_IA)
def activar_en_llamada(call_id: str, body: ActivarLlamadaIn, db: Session = Depends(get_db),
                       current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    from app.services.reuniones import llamadas
    _hacer(db, llamadas.activar, db, current_user, call_id, body.notice_confirmed)
    return APIResponse.ok(data=llamadas.estado(db, current_user, call_id))


@router.post("/calls/{call_id}/stop", summary="Parar el asistente y analizar lo grabado", dependencies=_IA)
def parar_en_llamada(call_id: str, db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    from app.services.reuniones import llamadas
    _hacer(db, llamadas.detener, db, current_user, call_id)
    return APIResponse.ok(data=llamadas.estado(db, current_user, call_id))


@router.get("/me/preferences", summary="Mis preferencias del asistente")
def mis_preferencias(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    return APIResponse.ok(data=servicio.preferencias(db, current_user))


@router.put("/me/preferences", summary="Guardar mis preferencias")
def guardar_mis_preferencias(body: PreferenciasIn, db: Session = Depends(get_db),
                             current_user: User = Depends(requiere_capacidad("reuniones.usar"))):
    return APIResponse.ok(data=_hacer(db, servicio.guardar_preferencias, db, current_user,
                                      body.model_dump(exclude_none=True)))


# ── Configuración (admin) ─────────────────────────────────────────────────────

@router.get("/config", summary="Configuración del asistente de reuniones (sin secretos)")
def leer_config(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("reuniones.config"))):
    return APIResponse.ok(data=cfg_mod.para_la_api(db, _org(current_user)))


@router.put("/config", summary="Guardar la configuración (auditada, sin secretos)")
@limiter.limit("20/minute")
def guardar_config(request: Request, body: dict = Body(...), db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user), _rol: User = Depends(requiere_capacidad("reuniones.config"))):
    from app.services.audit import audit_log
    org = _org(current_user)
    antes = cfg_mod.para_la_api(db, org)
    despues = _hacer(db, cfg_mod.guardar, db, org, body, current_user)
    secretos = sorted(f"{b}.{c}" for b, c in cfg_mod.SECRETOS
                      if isinstance(body.get(b), dict) and (body[b].get(c) or "").strip())
    audit_log(db, current_user, "UPDATE", "meeting_assistant_config", org, "reuniones.config",
              old_values=antes, new_values=despues, metadata={"secretos_cambiados": secretos})
    _confirmar(db)
    return APIResponse.ok(data=despues)


@router.post("/config/test/{conector}", summary="Probar una conexión")
@limiter.limit("10/minute")
def probar_conector(request: Request, conector: str, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("reuniones.config"))):
    from app.core.codigos_de_error import error
    from app.services.reuniones.conectores import meet, teams, zoom
    org = _org(current_user)
    try:
        if conector == "teams":
            r = teams.probar(db, org)
        elif conector == "zoom":
            r = zoom.probar(db, org)
        elif conector == "meet":
            r = meet.probar(db, org, current_user.email)
        elif conector == "bots":
            from app.services.reuniones.bots import proveedor
            proveedor(db, org)
            r = {"ok": True, "detail": "proveedor activo y con contrato"}
        else:
            raise error(404, "no_encontrado", que="conector", detail="Conector desconocido")
    except ValueError as exc:
        from app.core.codigos_de_error import ErrorConCodigo
        r = {"ok": False, "detail": str(exc), "code": exc.codigo if isinstance(exc, ErrorConCodigo) else None}
    return APIResponse.ok(data=r)


@router.post("/config/teams/subscription", summary="Crear o renovar la suscripción de Graph")
def suscripcion_de_teams(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("reuniones.config"))):
    from app.services.reuniones.conectores import teams
    return APIResponse.ok(data=_hacer(db, teams.suscribir, db, _org(current_user)))


@router.get("/gdpr/person", summary="Copia de los datos de una persona en las reuniones (auditada)")
def rgpd_copia(email: Optional[str] = None, user_id: Optional[str] = None, db: Session = Depends(get_db),
               current_user: User = Depends(requiere_capacidad("reuniones.config"))):
    from app.core.codigos_de_error import error
    from app.services.audit import audit_log
    from app.services.reuniones import rgpd
    if not (email or user_id):
        raise error(422, "campo_obligatorio", campo="email", detail="Indica el correo o el usuario")
    datos = rgpd.copia(db, _org(current_user), user_id=user_id, email=email)
    audit_log(db, current_user, "GDPR_EXPORT", "ai_meeting", user_id or None, email or "",
              metadata={"meetings": datos["meetings_count"]})
    _confirmar(db)
    return APIResponse.ok(data=datos)


@router.post("/gdpr/person/erase", summary="Suprimir a una persona de las reuniones (auditada)")
def rgpd_suprimir(body: PersonaIn, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("reuniones.config"))):
    from app.core.codigos_de_error import error
    from app.services.audit import audit_log
    from app.services.reuniones import rgpd
    if not (body.email or body.user_id):
        raise error(422, "campo_obligatorio", campo="email", detail="Indica el correo o el usuario")
    informe = _hacer(db, rgpd.suprimir, db, _org(current_user), user_id=body.user_id, email=body.email)
    audit_log(db, current_user, "GDPR_ERASE", "ai_meeting", body.user_id or None, "",
              metadata={k: v for k, v in informe.items()})
    _confirmar(db)
    return APIResponse.ok(data=informe)


# ── Avisos firmados (sin sesión) ──────────────────────────────────────────────

@router_webhooks.post("/recall/{org_id}", summary="Avisos del proveedor de bots (firma Svix)")
@limiter.limit("600/minute")
async def aviso_recall(request: Request, org_id: str, db: Session = Depends(get_db)):
    from app.core.async_db import run_db
    from app.services.reuniones import webhooks
    cuerpo = await request.body()
    return await run_db(webhooks.recall, db, org_id, dict(request.headers), cuerpo)


@router_webhooks.post("/zoom/{org_id}", summary="Avisos de Zoom (x-zm-signature)")
@limiter.limit("600/minute")
async def aviso_zoom(request: Request, org_id: str, db: Session = Depends(get_db)):
    from app.core.async_db import run_db
    from app.services.reuniones import webhooks
    cuerpo = await request.body()
    return await run_db(webhooks.zoom, db, org_id, dict(request.headers), cuerpo)


@router_webhooks.post("/teams/{org_id}", summary="Avisos de Microsoft Graph (clientState)")
@limiter.limit("600/minute")
async def aviso_teams(request: Request, org_id: str, validationToken: Optional[str] = Query(None),  # noqa: N803
                      db: Session = Depends(get_db)):
    from app.core.async_db import run_db
    from app.services.reuniones import webhooks
    cuerpo = b"" if validationToken else await request.body()
    r = await run_db(webhooks.teams, db, org_id, validationToken, cuerpo)
    if isinstance(r, str):
        return PlainTextResponse(r)
    return r
