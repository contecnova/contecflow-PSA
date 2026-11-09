"""
ai_modules — thin router delegating to app.services.ai_modules_service
"""
import os
from app.core.config import settings
from app.core.modulos_ia import comprobar_modulo, exigir_modulo_ia
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Body
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_internal_user
from app.core.ratelimit import limiter
from app.core.uploads import UploadProfile, read_and_validate_upload_sync
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.services.service_desk.portal_auth_service import get_current_portal_client
import app.services.ai_modules_service as _svc

router = APIRouter()

# Local aliases for backward compatibility with tests
def _api_key():
    return _svc.api_key()

def _call_ai_unified(db, messages, system=None, module="v16", user_id=None, max_tokens=1000):
    return _svc.call_ai_unified(db, messages, system=system, module=module,
                                user_id=user_id, max_tokens=max_tokens)



def _compute_kb_embedding(db, article_id: str, text: str):
    return _svc.compute_kb_embedding(db, article_id, text)

def _log_action(db, user_id, module, action_type, input_s=None, output_s=None,
                entities=None, tokens=0, latency=0, status="success"):
    return _svc.log_action(db, user_id, module, action_type, input_s=input_s,
                           output_s=output_s, entities=entities, tokens=tokens,
                           latency=latency, status=status)

def _burnout_score(weekly_hours: list) -> float:
    return _svc.burnout_score(weekly_hours)

def _chunk_text(text: str, chunk_size: int = 6000, overlap: int = 500) -> list:
    return _svc.chunk_text(text, chunk_size=chunk_size, overlap=overlap)

def _map_reduce_analysis(text, map_system, map_user_prefix, reduce_system, reduce_user_suffix,
                         db, module, user_id, map_tokens=1500, reduce_tokens=3000):
    return _svc.map_reduce_analysis(text, map_system, map_user_prefix, reduce_system,
                                    reduce_user_suffix, db, module, user_id,
                                    map_tokens=map_tokens, reduce_tokens=reduce_tokens)

def _kb_vector_search(db, query_text: str, limit: int = 5, only_published: bool = True) -> list:
    return _svc.kb_vector_search(db, query_text, limit=limit, only_published=only_published)

def _openai_key_from_db(db) -> Optional[str]:
    return _svc.openai_key_from_db(db)

def _process_voice_core(transcript: str, db, current_user, confirm: bool = False):
    # Auditoria 2026-11: el envoltorio no aceptaba `confirm` y las dos rutas de
    # voz (/voice/command y /voice/transcribe) daban 500 siempre.
    return _svc.process_voice_core(transcript, db, current_user, confirm=confirm)

def _get_client_project_data(client_user, db: Session) -> dict:
    return _svc.get_client_project_data(client_user, db)

def _client_demo_response(message: str, project_data: dict) -> str:
    return _svc.client_demo_response(message, project_data)

def _predict_overrun_ml(cpi, spi, budget_used_pct, elapsed_pct,
                        task_completion_pct, overdue_task_ratio, team_load_pct):
    return _svc.predict_overrun_ml(cpi, spi, budget_used_pct, elapsed_pct,
                                   task_completion_pct, overdue_task_ratio, team_load_pct)


# ═══════════════════════════════════════════════════════════════════════════════
# NEXUSORACLE — Predictive Intelligence
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/oracle/predictions", summary="NexusOracle — listar predicciones activas")
def list_predictions(
    severity: Optional[str] = None,
    prediction_type: Optional[str] = None,
    only_unacked: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIListResponse.ok(items=_svc.list_predictions(db, severity=severity, prediction_type=prediction_type, only_unacked=only_unacked))


@router.post("/oracle/run", summary="Alertas Inteligentes — ejecutar análisis de alertas", dependencies=[Depends(exigir_modulo_ia("nexusoracle"))])
def run_oracle(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.run_oracle_analysis(db, current_user))


@router.post("/oracle/predictions/{pred_id}/acknowledge", summary="Reconocer predicción")
def acknowledge_prediction(
    pred_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    try:
        return APIResponse.ok(data=_svc.acknowledge_prediction(db, pred_id, current_user.id))
    except ValueError:
        raise HTTPException(404)


# ═══════════════════════════════════════════════════════════════════════════════
# SMART MEETING ASSISTANT
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/meetings", summary="Listar reuniones procesadas")
def list_meetings(
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIListResponse.ok(items=_svc.list_meetings(db, project_id=project_id))


from app.schemas.ai_modules import MeetingProcessPayload


@router.post("/meetings/process", summary="Procesar transcripción de reunión con IA", dependencies=[Depends(exigir_modulo_ia("meeting_assistant"))])
def process_meeting(
    payload: MeetingProcessPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    try:
        return APIResponse.ok(data=_svc.process_meeting(db, payload, current_user))
    except ValueError as e:
        if "invalid_meeting_date" in str(e):
            raise HTTPException(400, "Formato de meeting_date inválido, se espera YYYY-MM-DD[T]HH:MM:SS")
        raise HTTPException(400, str(e))


@router.post("/meetings/{meeting_id}/create-tasks", summary="Crear tareas en Contecflow desde acciones de reunión", dependencies=[Depends(exigir_modulo_ia("meeting_assistant"))])
def create_tasks_from_meeting(
    meeting_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    try:
        return APIResponse.ok(data=_svc.create_tasks_from_meeting(db, meeting_id, payload, current_user))
    except ValueError as e:
        err = str(e)
        if "not_found" in err: raise HTTPException(404)
        if "project_id_required" in err: raise HTTPException(400, "Se requiere project_id para crear tareas")
        raise HTTPException(400, err)


@router.get("/meetings/{meeting_id}", summary="Detalle de reunión")
def get_meeting(
    meeting_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return APIResponse.ok(data=_svc.get_meeting(db, meeting_id))
    except ValueError:
        raise HTTPException(404)


# ═══════════════════════════════════════════════════════════════════════════════
# AI CONTRACT INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/contracts-ai", summary="Listar contratos analizados por IA")
def list_ai_contracts(
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIListResponse.ok(items=_svc.list_ai_contracts(db, project_id=project_id, current_user=current_user))


@router.get("/contracts-ai/{contract_id}", summary="Detalle de un contrato analizado")
def get_ai_contract(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    result = _svc.get_ai_contract(db, contract_id, current_user=current_user)
    if result is None:
        raise HTTPException(404, "Contrato no encontrado o sin permisos")
    return APIResponse.ok(data=result)


from app.schemas.ai_modules import ContractAnalyzePayload


@router.post("/contracts-ai/analyze", summary="Analizar contrato con IA (texto)", dependencies=[Depends(exigir_modulo_ia("contract_intelligence"))])
def analyze_contract(
    payload: ContractAnalyzePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.analyze_contract(db, payload, current_user))


@router.post("/contracts-ai/analyze-pdf", summary="Analizar contrato con IA desde PDF", dependencies=[Depends(exigir_modulo_ia("contract_intelligence"))])
def analyze_contract_pdf(
    file: UploadFile = File(..., description="Archivo PDF del contrato"),
    project_id: Optional[str] = Body(None),
    client_name: Optional[str] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    # H22: extracción de texto del PDF y delegación al mismo pipeline de análisis.
    # Limit 10MB — los contratos típicos son <2MB; >10MB suele indicar PDF
    # con imágenes (requeriría OCR, fuera de scope).
    # Auditoría 2026-08 (P1-8): antes sólo se comprobaba que el NOMBRE acabara en
    # .pdf. El perfil PDF_ONLY valida además los bytes mágicos (%PDF-) y acota el
    # tamaño leyendo por trozos, en vez de bufferizar el fichero y medirlo luego.
    pdf_bytes = read_and_validate_upload_sync(file, UploadProfile.PDF_ONLY)
    if not pdf_bytes:
        raise HTTPException(400, "El archivo está vacío.")

    text = _svc.extract_pdf_text(pdf_bytes)
    if not text or len(text) < 50:
        raise HTTPException(
            422,
            "No se pudo extraer texto del PDF (¿es un PDF escaneado sin OCR?)."
        )

    # Construimos un payload equivalente al endpoint /analyze de texto.
    payload = ContractAnalyzePayload(
        project_id=project_id,
        client_name=client_name,
        filename=file.filename or "contract.pdf",
        contract_text=text,
    )
    return APIResponse.ok(data=_svc.analyze_contract(db, payload, current_user))


# ═══════════════════════════════════════════════════════════════════════════════
# AI KNOWLEDGE BASE
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/kb", summary="Listar artículos de KB generados por IA")
def list_kb(
    published_only: bool = False,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIListResponse.ok(items=_svc.list_kb(db, published_only=published_only, category=category))


@router.post("/kb/generate/{ticket_id}", summary="Generar artículo KB desde ticket resuelto", dependencies=[Depends(exigir_modulo_ia("knowledge_base"))])
def generate_kb_from_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    try:
        return APIResponse.ok(data=_svc.generate_kb_from_ticket(db, ticket_id, current_user))
    except ValueError:
        raise HTTPException(404)


@router.post("/kb/search", summary="Búsqueda semántica en KB", dependencies=[Depends(exigir_modulo_ia("knowledge_base"))])
def search_kb(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    query = payload.get("query", "")
    if not query: raise HTTPException(400, "query required")
    return APIListResponse.ok(items=_svc.search_kb(db, query))


@router.post("/kb/rebuild-embeddings", summary="Reconstruir embeddings de todos los artículos KB")
def rebuild_kb_embeddings(
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.rebuild_kb_embeddings(db))


@router.patch("/kb/{article_id}", summary="Actualizar artículo KB")
def update_kb(
    article_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.update_kb(db, article_id, payload, current_user))
    except ValueError:
        raise HTTPException(404)


# ═══════════════════════════════════════════════════════════════════════════════
# VOICE INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

#: Código interno del proveedor STT → (código HTTP, texto). Auditoría 2026-09
#: (hallazgo 18): eran cuatro `if` seguidos. Lo que no está aquí sale con el
#: código que devolvió el proveedor, o 502 si no dio ninguno: el fallo es de un
#: tercero y un 500 haría pensar que es nuestro.
_ERRORES_STT: dict[int, tuple[int, str]] = {
    504: (504, "Timeout esperando respuesta STT"),
    401: (401, "Credenciales STT inválidas"),
    403: (401, "Credenciales STT inválidas"),
    422: (422, "No se pudo transcribir el audio"),
}


def _http_del_error_stt(exc) -> HTTPException:
    """Traduce un `STTError` al código HTTP que le corresponde."""
    texto = str(exc)
    # Este caso no viene con código: lo dice el mensaje del factory.
    if "Ningún STT provider está disponible" in texto:
        return HTTPException(
            503,
            "No hay un proveedor STT configurado. Activa OPENAI_API_KEY o "
            "configura otro proveedor de transcripción.",
        )
    codigo = exc.status_code or 502
    http, motivo = _ERRORES_STT.get(codigo, (codigo, "Error de STT"))
    return HTTPException(http, f"{motivo}: {texto[:200]}")


def _puente_de_clave_openai_heredada(db: Session) -> None:
    """Retrocompatibilidad: la clave de OpenAI guardada en base de datos.

    El factory de STT lee la clave del entorno, así que si el proveedor
    primario es OpenAI y no hay clave en el entorno se busca en un proveedor
    guardado y se publica ahí. Escribe en `os.environ` **a propósito**: es el
    contrato del SDK de OpenAI.
    """
    if (getattr(settings, "STT_PROVIDER", "openai") or "openai").lower() != "openai":
        return
    if settings.OPENAI_API_KEY:
        return
    clave = _openai_key_from_db(db)
    if clave:
        os.environ["OPENAI_API_KEY"] = clave


@router.post("/voice/transcribe", summary="Transcribir audio (OpenAI / Azure / Google / whisper local) y procesar como comando", dependencies=[Depends(exigir_modulo_ia("voice"))])
def transcribe_voice_audio(
    audio: UploadFile = File(..., description="Archivo de audio (.mp3, .wav, .m4a, .webm, .ogg)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    """Transcribe audio y lo procesa como un comando de voz.

    Item #51: el proveedor primario y los de respaldo se configuran en
    `settings.STT_PROVIDER` / `STT_FALLBACK_PROVIDERS`. Por defecto OpenAI, por
    compatibilidad con las configuraciones existentes.
    """
    audio_bytes = audio.file.read()
    if not audio_bytes:
        raise HTTPException(400, "El archivo de audio está vacío.")
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(413, "El archivo de audio no puede superar 25 MB.")

    _puente_de_clave_openai_heredada(db)

    from app.services.stt import transcribe_audio as _stt_transcribe, STTError as _STTError

    try:
        resultado = _stt_transcribe(
            audio_bytes,
            audio.filename or "audio.wav",
            audio.content_type or "audio/wav",
            language=None,
            db=db,
            org_id=getattr(current_user, "organization_id", None),
        )
        transcripcion = (resultado.text or "").strip()
    except _STTError as exc:
        raise _http_del_error_stt(exc)
    except Exception as exc:
        raise HTTPException(500, f"Error inesperado de transcripción: {str(exc)[:150]}")

    if not transcripcion:
        raise HTTPException(
            422, "El proveedor STT no pudo transcribir el audio (resultado vacío).",
        )

    # Esta ruta entra **siempre** en modo de prueba: el usuario tiene que ver la
    # transcripción y confirmar antes de que se ejecute nada.
    salida = _process_voice_core(transcripcion, db, current_user, confirm=False)
    return APIResponse.ok(data={**salida, "whisper_transcript": transcripcion})


from app.schemas.ai_modules import VoiceCommandPayload


@router.post("/voice/command", summary="Procesar comando de voz", dependencies=[Depends(exigir_modulo_ia("voice"))])
def process_voice_command(
    payload: VoiceCommandPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    return APIResponse.ok(data=_process_voice_core(
        payload.transcript.strip(), db, current_user,
        confirm=bool(payload.confirm),
    ))


# ═══════════════════════════════════════════════════════════════════════════════
# INTELLIGENT CLIENT PORTAL AI
# ═══════════════════════════════════════════════════════════════════════════════

CLIENT_AI_SYSTEM = """Eres el asistente de IA del portal de cliente de Contecflow.
Ayudas a los clientes a entender el estado de sus proyectos de forma clara y profesional.
IMPORTANTE: Solo tienes acceso a los datos del proyecto del cliente. Nunca reveles información de otros clientes,
datos financieros internos (márgenes, costes internos) ni información confidencial del equipo.
Responde siempre en el idioma del cliente. Sé transparente y profesional.
Datos disponibles del proyecto:
{project_data}"""


@router.post("/portal-ai/chat", summary="Chat IA en portal de cliente")
# Rate limit: esto llama a un LLM de pago. Sin tope, un token de cliente filtrado
# —o simplemente un bucle— quema presupuesto de proveedor sin freno.
# (auditoría 2026-08, docs/AUDIT_2026_08_SECOND_PASS.md §6)
@limiter.limit("20/minute")
def client_portal_chat(
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    client=Depends(get_current_portal_client),
):
    """Chat IA del portal.

    CAMBIO DE CONTRATO (auditoría 2026-08 §6): antes el token de cliente viajaba en
    el body como `client_token`. Ahora se autentica por cookie de portal o cabecera
    `Authorization`, como el resto de la superficie de portal. Motivos: un token en
    el body acaba en logs con más facilidad, y la authz por dependencia sí es
    auditable por herramientas (antes esta ruta figuraba como "pública" en el
    guard-test de cobertura de authz).

    El frontend ya usaba la variante por cookie (`POST /portal/ai-chat`), así que
    este cambio no afecta a la aplicación; sí afectaría a integraciones externas que
    siguieran enviando `client_token` en el body.
    """
    try:
        return APIResponse.ok(data=_svc.client_portal_chat_authenticated(
            db, client, payload.get("message", ""), payload.get("session_id"),
        ))
    except ValueError as e:
        err = str(e)
        if "missing_fields" in err: raise HTTPException(400, "message required")
        if "invalid_token" in err: raise HTTPException(401, "Token de cliente inválido")
        raise HTTPException(400, err)


# ─── Revenue forecast (pure-Python linear regression) ────────────────────────

@router.post("/revenue-forecast", summary="Previsión de ingresos con regresión lineal")
def revenue_forecast(
    months_ahead: int = 3,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    return APIResponse.ok(data=_svc.revenue_forecast(db, months_ahead=months_ahead))


# ─── Smart schedule ───────────────────────────────────────────────────────────

from app.schemas.ai_modules import SmartScheduleRequest


@router.post("/smart-schedule", summary="Sugerir calendario de tareas sin fecha con IA")
def smart_schedule(
    payload: SmartScheduleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    return APIResponse.ok(data=_svc.smart_schedule(db, payload, current_user))


# ── AI Overrun Prediction ──────────────────────────────────────────────────────



@router.post("/overrun-prediction", summary="Predicción de sobrecosto/retraso por proyecto")
def overrun_prediction(
    project_id: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    try:
        data = _svc.get_overrun_prediction_data(db, project_id)
    except ValueError as e:
        err = str(e)
        if "not_found" in err: raise HTTPException(404, "Proyecto no encontrado")
        if "no_tasks" in err: raise HTTPException(422, "El proyecto no tiene tareas; sin datos suficientes para predicción.")
        raise HTTPException(400, err)

    project = data["project"]
    result = _svc.predict_overrun_ml(
        cpi=data["cpi"], spi=data["spi"],
        budget_used_pct=data["budget_used_pct"],
        elapsed_pct=data["elapsed_pct"],
        task_completion_pct=data["task_completion_pct"],
        overdue_task_ratio=data["overdue_ratio"],
        team_load_pct=data["team_load_pct"],
    )

    return APIResponse.ok(data={
        "project_id":   project_id,
        "project_name": project.name,
        "cpi": round(data["cpi"], 3),
        "spi": round(data["spi"], 3),
        "budget_used_pct":       round(data["budget_used_pct"], 1),
        "elapsed_pct":           round(data["elapsed_pct"], 1),
        "task_completion_pct":   round(data["task_completion_pct"], 1),
        "overdue_task_ratio":    round(data["overdue_ratio"], 3),
        **result,
    })
