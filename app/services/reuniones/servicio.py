"""Operaciones del asistente de reuniones. Ninguna función confirma: confirma el endpoint
(o el trabajo de fondo) cuando todo ha ido bien.
"""
from __future__ import annotations

import html
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.codigos_de_error import ErrorConCodigo, error
from app.services.reuniones import config as cfg_mod
from app.services.reuniones.analisis import TACHADO, analizar
from app.services.reuniones.consultas import bloqueo_legal, consentimiento_completo, es_gestor, puede_escuchar
from app.services.reuniones.eventos import auditar, cambiar_estado, evento

logger = logging.getLogger(__name__)

ORIGENES_MANUALES = ("recording", "transcript", "upload")
#: Dominios de reunión que acepta el bot (Teams, Zoom, Meet, Webex).
DOMINIOS_DE_REUNION = ("teams.microsoft.com", "teams.live.com", "zoom.us", "meet.google.com", "webex.com")
MAX_TROZO_MB = 25


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _fecha(v) -> Optional[datetime]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")[:32])
    except ValueError:
        raise ErrorConCodigo("fecha_reunion_no_valida")


def _cfg(db: Session, org):
    return cfg_mod.leer(db, org)


def fijar_retencion(db: Session, reunion) -> None:
    ret = _cfg(db, reunion.organization_id)["retention"]
    if reunion.transcript_expires_at is None:
        reunion.transcript_expires_at = _ahora() + timedelta(days=int(ret["transcript_days"]))


def _caducidad_audio(db: Session, org) -> datetime:
    return _ahora() + timedelta(days=int(_cfg(db, org)["retention"]["audio_days"]))


def _exigir_proyecto(db: Session, project_id: Optional[str]):
    if not project_id:
        return None
    from app.models.project import Project
    p = db.get(Project, project_id)
    if p is None:
        raise error(404, "proyecto_no_encontrado")
    return p


# ── Participantes y segmentos ─────────────────────────────────────────────────

def _usuario_por_correo(db: Session, org, correo: Optional[str]):
    if not correo:
        return None
    from app.db.session import _miembros_de
    from app.models.user import User
    q = db.query(User).filter(func.lower(User.email) == correo.strip().lower())
    if org:
        q = q.filter(_miembros_de(User, org))
    return q.first()


def añadir_participante(db: Session, reunion, *, name=None, email=None, user_id=None, role="asistente",
                        consent=None, consent_method=None, actor=None):
    from app.models.reuniones import AIMeetingParticipant
    from app.models.user import User
    email = (email or "").strip() or None
    if user_id is None and email:
        u = _usuario_por_correo(db, reunion.organization_id, email)
        user_id = u.id if u else None
    if user_id:
        u = db.get(User, user_id)
        if u is None:
            raise error(404, "persona_no_existe_en_empresa")
        name = name or u.full_name
        email = email or u.email
    for p in reunion.participantes:   # sin duplicados
        if (user_id and p.user_id == user_id) or (email and p.email and p.email.lower() == email.lower()):
            return p
    p = AIMeetingParticipant(organization_id=reunion.organization_id, user_id=user_id, name=(name or email or "")[:255],
                             email=email, role=role, consent=consent, consent_method=consent_method,
                             consent_at=_ahora() if consent is not None else None,
                             consent_by=getattr(actor, "id", None) if consent is not None else None)
    reunion.participantes.append(p)
    return p


def _participante_de_hablante(db: Session, reunion, hablante: Optional[str], correo: Optional[str] = None):
    if not hablante and not correo:
        return None
    bajo = (hablante or "").strip().lower()
    for p in reunion.participantes:
        if (correo and p.email and p.email.lower() == correo.lower()) or (bajo and (p.name or "").lower() == bajo):
            break
    else:
        p = añadir_participante(db, reunion, name=hablante, email=correo, role="hablante")
    if p.id is None:   # dado de alta sin flush (en `crear` o aquí): el segmento necesita su id
        db.flush()
    return p


def añadir_segmentos(db: Session, reunion, segmentos: list[dict], *, offset_ms: int = 0,
                     idioma: Optional[str] = None) -> int:
    from app.models.reuniones import AIMeetingSegment
    orden = max((s.orden for s in reunion.segmentos), default=-1) + 1
    n = 0
    for s in segmentos:
        texto = (s.get("text") or "").strip()
        if not texto:
            continue
        p = _participante_de_hablante(db, reunion, s.get("speaker"), s.get("email"))
        if p is not None and p.consent is False:
            texto = TACHADO
        inicio, fin = s.get("start_ms"), s.get("end_ms")
        reunion.segmentos.append(AIMeetingSegment(
            organization_id=reunion.organization_id, orden=orden, speaker=(s.get("speaker") or None),
            participant_id=getattr(p, "id", None), user_id=getattr(p, "user_id", None),
            start_ms=(inicio + offset_ms) if inicio is not None else (offset_ms if offset_ms else None),
            end_ms=(fin + offset_ms) if fin is not None else None,
            text=texto, language=s.get("language") or idioma))
        orden += 1
        n += 1
    db.flush()   # ids de participantes nuevos para los siguientes segmentos
    return n


# ── Alta, edición y borrado ───────────────────────────────────────────────────

def crear(db: Session, usuario, datos: dict):
    """Alta manual: grabación propia, transcripción pegada o subida."""
    from app.models.ai_chat import AIMeeting
    org = usuario.organization_id
    cfg = _cfg(db, org)
    origen = datos.get("origin") or "transcript"
    if origen not in ORIGENES_MANUALES:
        raise ErrorConCodigo("reuniones_formato_no_valido", detail=f"origin: {', '.join(ORIGENES_MANUALES)}")
    if origen == "recording" and cfg["consent"]["notice_required"] and not datos.get("notice_confirmed"):
        raise error(422, "reuniones_sin_aviso")
    if origen != "recording" and not (datos.get("transcript") or "").strip():
        raise error(422, "reuniones_sin_transcripcion")
    _exigir_proyecto(db, datos.get("project_id"))
    reunion = AIMeeting(
        organization_id=org, title=(datos.get("title") or "").strip()[:255] or "Reunión",
        origin=origen, platform=datos.get("platform") or ("presencial" if origen == "recording" else None),
        project_id=datos.get("project_id"), client_id=datos.get("client_id"),
        meeting_date=_fecha(datos.get("meeting_date")) or _ahora(), duration_min=datos.get("duration_min"),
        created_by=usuario.id, consent_required=bool(cfg["consent"]["require_consent"]),
        status="grabando" if origen == "recording" else "procesando",
        participants=json.dumps([p.get("name") or p.get("email") for p in datos.get("participants") or []],
                                ensure_ascii=False))
    if origen == "recording":
        reunion.notice_confirmed_by, reunion.notice_confirmed_at = usuario.id, _ahora()
        reunion.audio_expires_at = _caducidad_audio(db, org)
    db.add(reunion)
    db.flush()
    # Quien graba o sube consiente por sí mismo (es quien lo pone en marcha).
    añadir_participante(db, reunion, user_id=usuario.id, role="organizador", consent=True, consent_method="self",
                        actor=usuario)
    for p in datos.get("participants") or []:
        if isinstance(p, str):
            p = {"name": p}
        añadir_participante(db, reunion, name=p.get("name"), email=p.get("email"), user_id=p.get("user_id"))
    fijar_retencion(db, reunion)
    evento(db, reunion, "created", usuario, {"origin": origen})
    if origen == "recording":
        evento(db, reunion, "notice_confirmed", usuario, {"source": datos.get("source") or "microphone"})
        auditar(db, usuario, "RECORDING_START", reunion, metadata={"notice_confirmed": True,
                                                                   "source": datos.get("source")})
        return reunion
    from app.services.reuniones.transcripcion import de_texto
    añadir_segmentos(db, reunion, de_texto(datos["transcript"]))
    reunion.transcript = datos["transcript"][:50000]
    analizar(db, reunion, usuario)
    return reunion


def actualizar(db: Session, usuario, reunion, cambios: dict):
    antes = {"title": reunion.title, "project_id": reunion.project_id, "client_id": reunion.client_id}
    if "title" in cambios and (cambios["title"] or "").strip():
        reunion.title = cambios["title"].strip()[:255]
    if "project_id" in cambios:
        _exigir_proyecto(db, cambios["project_id"])
        reunion.project_id = cambios["project_id"] or None
    if "client_id" in cambios:
        reunion.client_id = cambios["client_id"] or None
    despues = {"title": reunion.title, "project_id": reunion.project_id, "client_id": reunion.client_id}
    if antes != despues:
        evento(db, reunion, "updated", usuario, despues)
        auditar(db, usuario, "UPDATE", reunion, old_values=antes, new_values=despues)
    return reunion


def _exigir_sin_bloqueo(db: Session, reunion) -> None:
    b = bloqueo_legal(db, reunion)
    if b is not None:
        raise error(409, "bloqueo_legal_no_suprimible", casos=b.case_reference,
                    detail=f"Esta reunión está bajo bloqueo legal ({b.case_reference})")


def _borrar_medios_en_el_proveedor(db: Session, reunion) -> None:
    if not (reunion.bot_provider and reunion.bot_id):
        return
    try:
        from app.services.reuniones.bots import proveedor
        proveedor(db, reunion.organization_id, exigir_activo=False).borrar_medios(reunion.bot_id)
    except Exception:  # noqa: BLE001 - se informa; el borrado local sigue
        logger.warning("reuniones: no se pudieron borrar los medios del bot %s", reunion.bot_id, exc_info=True)


def borrar(db: Session, usuario, reunion) -> None:
    _exigir_sin_bloqueo(db, reunion)
    from app.services.reuniones import almacen
    _borrar_medios_en_el_proveedor(db, reunion)
    for a in reunion.audios:
        almacen.borrar(a.storage_key)
    auditar(db, usuario, "DELETE", reunion, metadata={"origin": reunion.origin, "segments": len(reunion.segmentos),
                                                     "audio_chunks": len(reunion.audios)})
    db.delete(reunion)


def borrar_audio(db: Session, usuario, reunion, motivo: str = "manual") -> int:
    _exigir_sin_bloqueo(db, reunion)
    from app.services.reuniones import almacen
    n = 0
    for a in list(reunion.audios):
        almacen.borrar(a.storage_key)
        reunion.audios.remove(a)
        n += 1
    evento(db, reunion, "audio_deleted", usuario, {"chunks": n, "reason": motivo})
    auditar(db, usuario, "DELETE", reunion, metadata={"what": "audio", "chunks": n, "reason": motivo})
    return n


# ── Audio (grabación propia) ──────────────────────────────────────────────────

def subir_audio(db: Session, usuario, reunion, datos: bytes, mime: str, seq: int, offset_ms: int) -> dict:
    from app.models.reuniones import AIMeetingAudio
    from app.services.reuniones import almacen
    if reunion.status != "grabando":
        raise error(409, "reuniones_no_grabando")
    if len(datos) > MAX_TROZO_MB * 1024 * 1024:
        raise error(413, "reuniones_audio_demasiado_grande", max=MAX_TROZO_MB)
    if not datos:
        raise error(422, "reuniones_formato_no_valido", detail="Trozo de audio vacío")
    org = reunion.organization_id
    clave = almacen.guardar(org, reunion.id, int(seq), datos, mime)
    trozo = AIMeetingAudio(organization_id=org, seq=int(seq), storage_key=clave, bytes=len(datos),
                           mime=(mime or "audio/webm")[:100], offset_ms=int(offset_ms or 0),
                           expires_at=reunion.audio_expires_at or _caducidad_audio(db, org))
    reunion.audios.append(trozo)
    db.flush()
    try:
        añadidos = _transcribir_trozo(db, reunion, trozo, datos)
    except Exception:
        almacen.borrar(clave)   # la petición se deshace: que no quede audio huérfano en disco
        raise
    evento(db, reunion, "audio_chunk", usuario, {"seq": int(seq), "bytes": len(datos), "segments": añadidos})
    return {"chunk_id": trozo.id, "seq": trozo.seq, "segments_added": añadidos}


def _transcribir_trozo(db: Session, reunion, trozo, datos: Optional[bytes] = None) -> int:
    from app.services.reuniones import almacen
    from app.services.reuniones.transcripcion import transcribir
    from app.services.stt import STTError
    datos = datos if datos is not None else almacen.leer(trozo.storage_key)
    try:
        r = transcribir(db, reunion.organization_id, datos, f"trozo-{trozo.seq}.webm", trozo.mime or "audio/webm")
    except STTError:
        logger.warning("reuniones: trozo %s sin transcribir (se reintenta al terminar)", trozo.id, exc_info=True)
        return 0
    trozo.transcribed, trozo.stt_provider = True, r.provider
    if r.language and not reunion.original_language:
        reunion.original_language = r.language[:10]
    # Sin diarización: el trozo es un segmento sin hablante (se puede renombrar luego).
    return añadir_segmentos(db, reunion, [{"speaker": None, "start_ms": 0,
                                           "end_ms": r.duration_ms, "text": r.text}],
                            offset_ms=trozo.offset_ms, idioma=(r.language or None))


def terminar(db: Session, usuario, reunion):
    if reunion.status != "grabando":
        raise error(409, "reuniones_no_grabando")
    for trozo in reunion.audios:
        if not trozo.transcribed:
            _transcribir_trozo(db, reunion, trozo)
    fin = max([s.end_ms or s.start_ms or 0 for s in reunion.segmentos] + [0])
    reunion.duration_min = max(1, round(fin / 60000)) if fin else reunion.duration_min
    reunion.ends_at = _ahora()
    evento(db, reunion, "finished", usuario, {"segments": len(reunion.segmentos)})
    analizar(db, reunion, usuario)
    return reunion


def reprocesar(db: Session, usuario, reunion):
    evento(db, reunion, "reprocessed", usuario)
    analizar(db, reunion, usuario)
    return reunion


def leer_audio(db: Session, usuario, reunion, trozo_id: str, descargar: bool) -> tuple[bytes, str, str]:
    from app.services.reuniones import almacen
    if not puede_escuchar(db, usuario, reunion):
        raise error(403, "sin_permiso", detail="Solo quien estuvo en la reunión o la gestiona puede escucharla")
    trozo = next((a for a in reunion.audios if a.id == trozo_id), None)
    if trozo is None:
        raise error(404, "no_encontrado", que="audio", detail="Audio no encontrado")
    datos = almacen.leer(trozo.storage_key)
    tipo = "download_audio" if descargar else "listen"
    evento(db, reunion, tipo, usuario, {"chunk": trozo.seq})
    auditar(db, usuario, "DOWNLOAD" if descargar else "LISTEN", reunion, metadata={"chunk": trozo.seq,
                                                                                    "bytes": trozo.bytes})
    nombre = trozo.storage_key.rsplit("/", 1)[-1]
    return datos, (trozo.mime or "audio/webm").split(";")[0], nombre


def exportar_transcripcion(db: Session, usuario, reunion, formato: str) -> tuple[str, str, str]:
    from app.services.reuniones.transcripcion import a_texto, a_vtt
    if not reunion.segmentos and not reunion.transcript:
        raise error(404, "reuniones_sin_transcripcion")
    if formato == "vtt":
        contenido, tipo = a_vtt(reunion.segmentos), "text/vtt"
    elif formato == "json":
        contenido = json.dumps([{"speaker": s.speaker, "start_ms": s.start_ms, "end_ms": s.end_ms, "text": s.text,
                                 "language": s.language} for s in reunion.segmentos], ensure_ascii=False, indent=1)
        tipo = "application/json"
    elif formato == "txt":
        contenido, tipo = (a_texto(reunion.segmentos) or reunion.transcript or ""), "text/plain"
    else:
        raise error(422, "reuniones_formato_no_valido", detail="txt | vtt | json")
    evento(db, reunion, "download_transcript", usuario, {"format": formato})
    auditar(db, usuario, "DOWNLOAD", reunion, metadata={"what": "transcript", "format": formato})
    return contenido, tipo, f"reunion-{reunion.id[:8]}.{formato}"


def editar_segmento(db: Session, usuario, reunion, segmento_id: str, cambios: dict):
    seg = next((s for s in reunion.segmentos if s.id == segmento_id), None)
    if seg is None:
        raise error(404, "no_encontrado", que="segmento", detail="Segmento no encontrado")
    destino = [seg]
    if cambios.get("apply_to_speaker") and seg.speaker:
        destino = [s for s in reunion.segmentos if s.speaker == seg.speaker]
    for s in destino:
        if "speaker" in cambios and (cambios["speaker"] or "").strip():
            s.speaker = cambios["speaker"].strip()[:255]
        if "user_id" in cambios:
            s.user_id = cambios["user_id"] or None
            if s.user_id:
                p = añadir_participante(db, reunion, user_id=s.user_id, role="hablante")
                db.flush()
                s.participant_id = p.id
    db.flush()
    evento(db, reunion, "updated", usuario, {"segments": len(destino)})
    return reunion


def quitar_participante(db: Session, usuario, reunion, participante_id: str):
    p = next((x for x in reunion.participantes if x.id == participante_id), None)
    if p is None:
        raise error(404, "no_encontrado", que="participante", detail="Participante no encontrado")
    reunion.participantes.remove(p)
    evento(db, reunion, "participant_removed", usuario, {"name": p.name})
    return reunion


def consentir(db: Session, usuario, reunion, participante_id: Optional[str], consiente: bool,
              metodo: Optional[str] = None):
    """El propio asistente responde por sí; el gestor apunta el de un externo (verbal o escrito)."""
    if participante_id:
        p = next((x for x in reunion.participantes if x.id == participante_id), None)
    else:
        p = next((x for x in reunion.participantes if x.user_id == usuario.id), None)
    if p is None:
        raise error(404, "no_encontrado", que="participante", detail="Participante no encontrado")
    propio = p.user_id == usuario.id
    if not propio:
        if not es_gestor(db, usuario, reunion) or p.user_id:
            # Una persona de la empresa consiente por sí misma.
            raise error(403, "sin_permiso", detail="Cada persona de la empresa responde por sí misma")
        if metodo not in ("verbal", "written"):
            raise error(422, "reuniones_formato_no_valido", detail="method: verbal | written")
    p.consent, p.consent_method = bool(consiente), ("self" if propio else metodo)
    p.consent_at, p.consent_by = _ahora(), usuario.id
    if not consiente:
        for s in reunion.segmentos:
            if s.participant_id == p.id:
                s.text = TACHADO
        for t in list(reunion.traducciones):
            reunion.traducciones.remove(t)
    evento(db, reunion, "consent", usuario, {"participant": p.id, "consents": bool(consiente),
                                              "method": p.consent_method})
    auditar(db, usuario, "CONSENT", reunion, metadata={"participant": p.id, "consents": bool(consiente),
                                                       "method": p.consent_method})
    db.flush()
    if reunion.status == "esperando_consentimiento" and consentimiento_completo(reunion):
        analizar(db, reunion, usuario)
    elif not consiente and reunion.status == "lista":
        analizar(db, reunion, usuario)   # el análisis ya no puede contar lo que dijo
    return reunion


# ── Acciones → tareas, tickets y acta ─────────────────────────────────────────

def _accion(reunion, accion_id: str):
    a = next((x for x in reunion.actions if x.id == accion_id), None)
    if a is None:
        raise error(404, "no_encontrado", que="accion", detail="Acción no encontrada")
    return a


def editar_accion(db: Session, usuario, reunion, accion_id: str, cambios: dict):
    a = _accion(reunion, accion_id)
    if "description" in cambios and (cambios["description"] or "").strip():
        a.description = cambios["description"].strip()
    if "assignee_id" in cambios:
        a.assignee_id = cambios["assignee_id"] or None
        if a.assignee_id:
            from app.models.user import User
            u = db.get(User, a.assignee_id)
            if u is None:
                raise error(404, "persona_no_existe_en_empresa")
            a.assignee_name = u.full_name
    if "due_date" in cambios:
        a.due_date = _fecha(cambios["due_date"]) if cambios["due_date"] else None
    evento(db, reunion, "updated", usuario, {"action": a.id})
    return reunion


def accion_a_tarea(db: Session, usuario, reunion, accion_id: str, project_id: Optional[str] = None) -> dict:
    from app.models.task import Task
    from app.services.numbering import next_numbered_code
    a = _accion(reunion, accion_id)
    if a.task_id:
        return {"task_id": a.task_id}
    proyecto = project_id or reunion.project_id
    if not proyecto:
        raise error(422, "reuniones_sin_proyecto")
    _exigir_proyecto(db, proyecto)
    tarea = Task(code=next_numbered_code(db, "task", prefix="TSK", padding=5), project_id=proyecto,
                 title=a.description[:255],
                 description=f"{a.description}\n\n— Reunión: {reunion.title}",
                 status="todo", priority="medium", assignee_id=a.assignee_id,
                 due_date=a.due_date.date() if a.due_date else None,
                 created_by=usuario.id, reporter_id=usuario.id)
    db.add(tarea)
    db.flush()
    a.task_id, a.is_created = tarea.id, True
    evento(db, reunion, "task_created", usuario, {"action": a.id, "task": tarea.id})
    return {"task_id": tarea.id}


def acciones_a_tareas(db: Session, usuario, reunion, action_ids=None, project_id=None) -> dict:
    hechas = []
    for a in reunion.actions:
        if (action_ids and a.id not in action_ids) or a.is_created:
            continue
        r = accion_a_tarea(db, usuario, reunion, a.id, project_id)
        hechas.append({"action_id": a.id, "task_id": r["task_id"], "title": a.description[:255]})
    return {"ok": True, "tasks_created": len(hechas), "tasks": hechas}


def accion_a_ticket(db: Session, usuario, reunion, accion_id: str) -> dict:
    from app.models.service_desk import Ticket, TicketPriority, TicketType
    from app.services.sla_service import next_ticket_number
    a = _accion(reunion, accion_id)
    if a.ticket_id:
        t = db.get(Ticket, a.ticket_id)
        return {"ticket_id": a.ticket_id, "number": getattr(t, "number", None)}
    ticket = Ticket(organization_id=reunion.organization_id,
                    number=next_ticket_number(TicketType.service_request.value, db),
                    ticket_type=TicketType.service_request, title=a.description[:500],
                    description=f"{a.description}\n\n— Reunión: {reunion.title}",
                    status="new", priority=TicketPriority.p3_medium, source="meeting",
                    project_id=reunion.project_id, client_id=reunion.client_id,
                    requester_user_id=usuario.id, requester_name=usuario.full_name,
                    assigned_to_user_id=a.assignee_id, created_by_user_id=usuario.id)
    db.add(ticket)
    db.flush()
    a.ticket_id = ticket.id
    evento(db, reunion, "ticket_created", usuario, {"action": a.id, "ticket": ticket.id})
    return {"ticket_id": ticket.id, "number": ticket.number}


def _html_del_acta(reunion) -> str:
    from app.services.reuniones.consultas import _json
    from app.services.reuniones.transcripcion import marca
    e = html.escape
    lista = lambda xs: "".join(f"<li>{e(str(x))}</li>" for x in xs) or "<li>—</li>"  # noqa: E731
    asistentes = "".join(f"<li>{e(p.name or p.email or '')}</li>" for p in reunion.participantes)
    acciones = "".join(
        f"<tr><td>{e(a.description)}</td><td>{e(a.assignee_name or '')}</td>"
        f"<td>{e(a.due_date.date().isoformat() if a.due_date else (a.due_date_text or ''))}</td></tr>"
        for a in reunion.actions)
    fecha = reunion.meeting_date.strftime("%Y-%m-%d %H:%M") if reunion.meeting_date else ""
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{e(reunion.title or '')}</title></head><body>"
            f"<h1>{e(reunion.title or '')}</h1><p>{e(fecha)}</p>"
            f"<h2>Asistentes</h2><ul>{asistentes}</ul>"
            f"<h2>Resumen</h2><p>{e(reunion.summary or '')}</p>"
            f"<h2>Decisiones</h2><ul>{lista(_json(reunion.decisions))}</ul>"
            f"<h2>Riesgos</h2><ul>{lista(_json(reunion.risks_mentioned))}</ul>"
            f"<h2>Preguntas abiertas</h2><ul>{lista(_json(reunion.open_questions))}</ul>"
            f"<h2>Acciones</h2><table border='1'><tr><th>Acción</th><th>Responsable</th><th>Fecha</th></tr>"
            f"{acciones}</table>"
            f"<p><small>{e(str(len(reunion.segmentos)))} intervenciones · "
            f"{e(marca((reunion.duration_min or 0) * 60000))}</small></p></body></html>")


def generar_acta(db: Session, usuario, reunion) -> dict:
    """Documento `meeting_notes` con una versión HTML, vinculado al proyecto y al cliente."""
    from app.models.documents import Document, DocumentCategory, DocumentVersion
    from app.services.s3_service import file_storage
    contenido = _html_del_acta(reunion).encode("utf-8")
    doc = None
    if reunion.minutes_document_id:
        doc = db.get(Document, reunion.minutes_document_id)
    if doc is None:
        doc = Document(title=f"Acta · {reunion.title or ''}"[:255], description=reunion.summary,
                       category=DocumentCategory.meeting_notes, project_id=reunion.project_id,
                       client_id=reunion.client_id, created_by=usuario.id)
        db.add(doc)
        db.flush()
    version = (db.query(func.max(DocumentVersion.version_num)).filter(DocumentVersion.document_id == doc.id)
               .scalar() or 0) + 1
    clave, tam = file_storage.upload_file(file_content=contenido, file_name="acta.html", document_id=doc.id,
                                          version_num=version, content_type="text/html")
    db.add(DocumentVersion(document_id=doc.id, version_num=version, file_key=clave, file_name="acta.html",
                           file_size=tam, file_mime_type="text/html", change_note="Asistente de reuniones",
                           created_by=usuario.id))
    reunion.minutes_document_id = doc.id
    evento(db, reunion, "minutes_created", usuario, {"document": doc.id, "version": version})
    return {"document_id": doc.id}


# ── Preguntar y buscar ────────────────────────────────────────────────────────

def preguntar(db: Session, usuario, reunion, pregunta: str) -> dict:
    from app.services.ai_modules._base import call_ai_unified
    from app.services.formato_regional import instruccion_de_idioma_para
    from app.services.reuniones.analisis import texto_para_analizar
    if reunion.consent_required and not consentimiento_completo(reunion):
        raise error(409, "reuniones_sin_consentimiento")
    texto = texto_para_analizar(reunion)
    if not texto.strip():
        raise error(422, "reuniones_sin_transcripcion")
    sistema = ("Respondes preguntas sobre UNA reunión usando solo su transcripción y su resumen. Si la "
               "respuesta no está, dilo. Cita la marca de tiempo [mm:ss] cuando ayude. "
               + instruccion_de_idioma_para(db, user_id=usuario.id))
    contenido = (f"Reunión: {reunion.title}\nResumen: {reunion.summary or ''}\n\nTranscripción:\n{texto[:24000]}"
                 f"\n\nPregunta: {pregunta.strip()[:2000]}")
    try:
        respuesta = call_ai_unified(db, [{"role": "user", "content": contenido}], system=sistema,
                                    module="meeting_assistant", user_id=usuario.id)
    except Exception:  # noqa: BLE001
        raise error(503, "ia_no_disponible")
    evento(db, reunion, "asked", usuario)
    return {"answer": respuesta}


def buscar(db: Session, usuario, q: str, limite: int = 30) -> list[dict]:
    from app.models.ai_chat import AIMeeting
    from app.models.reuniones import AIMeetingSegment
    from app.services.reuniones.consultas import filtro_visibles
    termino = (q or "").strip()
    if len(termino) < 2:
        return []
    patron = f"%{termino.lower()}%"
    base = db.query(AIMeeting)
    f = filtro_visibles(db, usuario)
    if f is not None:
        base = base.filter(f)
    salida: list[dict] = []
    for m in base.filter(or_(func.lower(AIMeeting.title).like(patron), func.lower(AIMeeting.summary).like(patron))) \
            .order_by(AIMeeting.created_at.desc()).limit(limite):
        trozo = (m.summary or "")
        i = trozo.lower().find(termino.lower())
        salida.append({"meeting_id": m.id, "title": m.title, "meeting_date": m.meeting_date.isoformat()
                       if m.meeting_date else None, "snippet": trozo[max(0, i - 80): i + 160] if i >= 0 else trozo[:200],
                       "segment_id": None, "start_ms": None})
    ids = base.with_entities(AIMeeting.id).subquery()
    segs = (db.query(AIMeetingSegment, AIMeeting).join(AIMeeting, AIMeeting.id == AIMeetingSegment.meeting_id)
            .filter(AIMeetingSegment.meeting_id.in_(db.query(ids.c.id)),
                    func.lower(AIMeetingSegment.text).like(patron))
            .order_by(AIMeeting.created_at.desc(), AIMeetingSegment.orden).limit(limite).all())
    for s, m in segs:
        salida.append({"meeting_id": m.id, "title": m.title,
                       "meeting_date": m.meeting_date.isoformat() if m.meeting_date else None,
                       "snippet": (f"{s.speaker}: " if s.speaker else "") + s.text[:240],
                       "segment_id": s.id, "start_ms": s.start_ms})
    return salida[:limite]


# ── Bot invitado ──────────────────────────────────────────────────────────────

def _url_valida(url: str) -> str:
    url = (url or "").strip()
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if p.scheme != "https" or not any(host == d or host.endswith("." + d) for d in DOMINIOS_DE_REUNION):
        raise error(422, "reuniones_url_no_valida")
    return url


def _plataforma_de(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for clave, nombre in (("teams", "teams"), ("zoom", "zoom"), ("meet.google", "meet"), ("webex", "webex")):
        if clave in host:
            return nombre
    return "otro"


def invitar_bot(db: Session, usuario, datos: dict, *, calendar_event_id: Optional[str] = None):
    from app.models.ai_chat import AIMeeting
    from app.services.reuniones.bots import ErrorDeBot, proveedor
    org = usuario.organization_id
    url = _url_valida(datos.get("meeting_url"))
    bots = proveedor(db, org)        # 403/422 si no está activo o sin contrato
    cfg = _cfg(db, org)
    _exigir_proyecto(db, datos.get("project_id"))
    reunion = AIMeeting(organization_id=org, title=(datos.get("title") or "").strip()[:255] or "Reunión",
                        origin="bot", platform=_plataforma_de(url), join_url=url, project_id=datos.get("project_id"),
                        meeting_date=_fecha(datos.get("join_at")) or _ahora(), created_by=usuario.id,
                        calendar_event_id=calendar_event_id, status="programada",
                        consent_required=bool(cfg["consent"]["require_consent"]),
                        bot_provider=bots.nombre, notice_confirmed_by=usuario.id, notice_confirmed_at=_ahora())
    db.add(reunion)
    db.flush()
    añadir_participante(db, reunion, user_id=usuario.id, role="organizador", consent=True, consent_method="self",
                        actor=usuario)
    try:
        creado = bots.crear_bot(url, nombre_bot=cfg["bots"].get("bot_name") or "Asistente de reuniones",
                                mensaje_al_entrar=cfg_mod.mensaje_del_bot(cfg),
                                unirse_en=datos.get("join_at"), metadatos={"meeting_id": reunion.id})
    except ErrorDeBot as exc:
        raise error(502, exc.codigo if exc.codigo.startswith(("conector_", "credencial_", "reuniones_"))
                    else "conector_rechazado", plataforma=bots.nombre)
    reunion.bot_id, reunion.bot_status = creado.get("id"), creado.get("estado")
    fijar_retencion(db, reunion)
    evento(db, reunion, "bot_invited", usuario, {"provider": bots.nombre, "bot": reunion.bot_id})
    auditar(db, usuario, "BOT_INVITE", reunion, metadata={"provider": bots.nombre, "platform": reunion.platform,
                                                          "contract": cfg["bots"].get("contract_reference")})
    return reunion


def sacar_bot(db: Session, usuario, reunion):
    from app.services.reuniones.bots import proveedor
    if not reunion.bot_id:
        raise error(409, "reuniones_bots_desactivados")
    proveedor(db, reunion.organization_id, exigir_activo=False).salir(reunion.bot_id)
    evento(db, reunion, "bot_left", usuario)
    return reunion


def procesar_evento_de_bot(db: Session, org: str, ev) -> Optional[object]:
    """Aviso del proveedor ya verificado: estado del bot y, al terminar, transcripción y análisis."""
    from app.models.ai_chat import AIMeeting
    from app.services.reuniones.bots import proveedor
    reunion = db.query(AIMeeting).filter(AIMeeting.bot_id == ev.bot_id, AIMeeting.organization_id == org).first()
    if reunion is None:
        return None
    reunion.bot_status = ev.estado_crudo or ev.estado
    evento(db, reunion, "bot_status", None, {"status": ev.estado_crudo, **(ev.datos or {})})
    if ev.estado in ("programada", "bot_unido", "grabando"):
        if reunion.status in ("programada", "bot_unido", "grabando"):
            cambiar_estado(db, reunion, ev.estado)
    elif ev.estado == "error":
        cambiar_estado(db, reunion, "error", error_code="conector_rechazado")
    elif ev.estado == "terminada" and reunion.status not in ("lista", "esperando_consentimiento"):
        cambiar_estado(db, reunion, "procesando")
        try:
            segmentos = proveedor(db, org, exigir_activo=False).transcripcion(reunion.bot_id)
        except Exception:  # noqa: BLE001 - puede no estar lista aún; el siguiente aviso lo reintenta
            logger.warning("reuniones: transcripción del bot %s aún no disponible", reunion.bot_id, exc_info=True)
            return reunion
        if not reunion.segmentos:
            añadir_segmentos(db, reunion, segmentos)
        fin = max([s.end_ms or 0 for s in reunion.segmentos] + [0])
        reunion.duration_min = max(1, round(fin / 60000)) if fin else None
        reunion.ends_at = _ahora()
        analizar(db, reunion, None)
    return reunion


# ── Importadas de Teams, Zoom y Meet ──────────────────────────────────────────

def guardar_importada(db: Session, org: str, imp, creador=None):
    """Una `Importable` a reunión. Idempotente por (empresa, origen, external_id)."""
    from app.models.ai_chat import AIMeeting
    ya = db.query(AIMeeting).filter(AIMeeting.organization_id == org, AIMeeting.origin == imp.origin,
                                    AIMeeting.external_id == imp.external_id).first()
    if ya is not None:
        return ya
    if creador is None and imp.organizer_email:
        creador = _usuario_por_correo(db, org, imp.organizer_email)
    cfg = _cfg(db, org)
    reunion = AIMeeting(organization_id=org, title=(imp.title or "")[:255] or f"Reunión de {imp.origin}",
                        origin=imp.origin, platform=imp.origin, external_id=imp.external_id, join_url=imp.join_url,
                        meeting_date=_fecha(imp.meeting_date) or _ahora(), ends_at=_fecha(imp.ends_at),
                        created_by=getattr(creador, "id", None), original_language=imp.language,
                        consent_required=bool(cfg["consent"]["require_consent"]), status="procesando")
    db.add(reunion)
    db.flush()
    for p in imp.participants:
        añadir_participante(db, reunion, name=p.get("name"), email=p.get("email"), role=p.get("role") or "asistente",
                            consent=True if creador and p.get("email") == getattr(creador, "email", None) else None,
                            consent_method="platform" if creador and p.get("email") == getattr(creador, "email", None)
                            else None)
    añadir_segmentos(db, reunion, imp.segments, idioma=imp.language)
    if reunion.meeting_date and reunion.ends_at:
        reunion.duration_min = max(1, int((reunion.ends_at - reunion.meeting_date).total_seconds() // 60))
    fijar_retencion(db, reunion)
    evento(db, reunion, "imported", creador, {"origin": imp.origin, "segments": len(reunion.segmentos)})
    analizar(db, reunion, creador)
    return reunion


def importar(db: Session, usuario, plataforma: str, referencia: str):
    from app.services.reuniones.conectores import meet, teams, zoom
    org = usuario.organization_id
    if not (referencia or "").strip():
        raise error(422, "reuniones_formato_no_valido", detail="reference")
    if plataforma == "teams":
        imp = teams.por_referencia(db, org, usuario.email, referencia)
    elif plataforma == "zoom":
        imp = zoom.por_referencia(db, org, referencia)
    elif plataforma == "meet":
        imp = meet.por_referencia(db, org, usuario.email, referencia)
    else:
        raise error(422, "reuniones_formato_no_valido", detail="platform: teams | zoom | meet")
    reunion = guardar_importada(db, org, imp, usuario)
    if reunion.created_by is None:
        reunion.created_by = usuario.id
    return reunion


# ── Preferencias ──────────────────────────────────────────────────────────────

def preferencias(db: Session, usuario) -> dict:
    from app.models.reuniones import AIMeetingUserPrefs
    p = db.query(AIMeetingUserPrefs).filter(AIMeetingUserPrefs.user_id == usuario.id).first()
    cfg = _cfg(db, usuario.organization_id)
    return {"collect_teams": bool(p and p.collect_teams), "collect_meet": bool(p and p.collect_meet),
            "bot_for_my_calendar": True if p is None else bool(p.bot_for_my_calendar), "language": getattr(p, "language", None),
            "available": {"teams": cfg["teams"]["enabled"], "zoom": cfg["zoom"]["enabled"],
                          "meet": cfg["meet"]["enabled"],
                          "bots": bool(cfg["bots"]["enabled"] and cfg["bots"].get("contract_reference")
                                       and cfg_mod.secreto(db, usuario.organization_id, "bots", "api_key"))}}


def guardar_preferencias(db: Session, usuario, datos: dict) -> dict:
    from app.models.reuniones import AIMeetingUserPrefs
    p = db.query(AIMeetingUserPrefs).filter(AIMeetingUserPrefs.user_id == usuario.id).first()
    if p is None:
        p = AIMeetingUserPrefs(user_id=usuario.id, organization_id=usuario.organization_id)
        db.add(p)
    for campo in ("collect_teams", "collect_meet", "bot_for_my_calendar"):
        if campo in datos:
            setattr(p, campo, bool(datos[campo]))
    if "language" in datos:
        from app.services.traduccion.idiomas import normalizar
        p.language = normalizar(datos["language"]) if datos["language"] else None
    db.flush()
    return preferencias(db, usuario)
