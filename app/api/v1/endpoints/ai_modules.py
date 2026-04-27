"""
ai_modules — thin router delegating to app.services.ai_modules_service
"""
from app.core.config import settings
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Body
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User
import app.services.ai_modules_service as _svc

router = APIRouter()

# Local aliases for backward compatibility with tests
def _api_key():
    return _svc.api_key()

def _call_ai_unified(db, messages, system=None, module="v16", user_id=None, max_tokens=1000):
    return _svc.call_ai_unified(db, messages, system=system, module=module,
                                user_id=user_id, max_tokens=max_tokens)

def _call_claude(messages, system=None, model=None, tools=None, max_tokens=1000):
    return _svc.call_claude(messages, system=system, model=model, tools=tools, max_tokens=max_tokens)

def _extract_text(response):
    return _svc.extract_text(response)

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

def _process_voice_core(transcript: str, db, current_user):
    return _svc.process_voice_core(transcript, db, current_user)

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
    return _svc.list_predictions(db, severity=severity, prediction_type=prediction_type, only_unacked=only_unacked)


@router.post("/oracle/run", summary="Alertas Inteligentes — ejecutar análisis de alertas")
def run_oracle(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.run_oracle_analysis(db, current_user)


@router.post("/oracle/predictions/{pred_id}/acknowledge", summary="Reconocer predicción")
def acknowledge_prediction(
    pred_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _svc.acknowledge_prediction(db, pred_id, current_user.id)
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
    return _svc.list_meetings(db, project_id=project_id)


from app.schemas.ai_modules import MeetingProcessPayload


@router.post("/meetings/process", summary="Procesar transcripción de reunión con IA")
def process_meeting(
    payload: MeetingProcessPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _svc.process_meeting(db, payload, current_user)
    except ValueError as e:
        if "invalid_meeting_date" in str(e):
            raise HTTPException(400, "Formato de meeting_date inválido, se espera YYYY-MM-DD[T]HH:MM:SS")
        raise HTTPException(400, str(e))


@router.post("/meetings/{meeting_id}/create-tasks", summary="Crear tareas en Contecflow desde acciones de reunión")
def create_tasks_from_meeting(
    meeting_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _svc.create_tasks_from_meeting(db, meeting_id, payload, current_user)
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
        return _svc.get_meeting(db, meeting_id)
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
    return _svc.list_ai_contracts(db, project_id=project_id)


from app.schemas.ai_modules import ContractAnalyzePayload


@router.post("/contracts-ai/analyze", summary="Analizar contrato con IA")
def analyze_contract(
    payload: ContractAnalyzePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.analyze_contract(db, payload, current_user)


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
    return _svc.list_kb(db, published_only=published_only, category=category)


@router.post("/kb/generate/{ticket_id}", summary="Generar artículo KB desde ticket resuelto")
def generate_kb_from_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _svc.generate_kb_from_ticket(db, ticket_id, current_user)
    except ValueError:
        raise HTTPException(404)


@router.post("/kb/search", summary="Búsqueda semántica en KB")
def search_kb(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = payload.get("query", "")
    if not query: raise HTTPException(400, "query required")
    return _svc.search_kb(db, query)


@router.post("/kb/rebuild-embeddings", summary="Reconstruir embeddings de todos los artículos KB")
def rebuild_kb_embeddings(
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    return _svc.rebuild_kb_embeddings(db)


@router.patch("/kb/{article_id}", summary="Actualizar artículo KB")
def update_kb(
    article_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.update_kb(db, article_id, payload, current_user)
    except ValueError:
        raise HTTPException(404)


# ═══════════════════════════════════════════════════════════════════════════════
# VOICE INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/voice/transcribe", summary="Transcribir audio con Whisper y procesar como comando")
def transcribe_voice_audio(
    audio: UploadFile = File(..., description="Archivo de audio (.mp3, .wav, .m4a, .webm, .ogg)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    openai_key = (settings.OPENAI_API_KEY or None) or _openai_key_from_db(db)
    if not openai_key:
        raise HTTPException(
            400,
            "Se requiere OPENAI_API_KEY para la transcripción de audio con Whisper. "
            "Configura la variable de entorno o añade un proveedor OpenAI en IA & Conectores."
        )

    audio_bytes = audio.file.read()
    if not audio_bytes:
        raise HTTPException(400, "El archivo de audio está vacío.")
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(413, "El archivo de audio no puede superar 25 MB.")

    import httpx as _httpx
    try:
        with _httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{settings.OPENAI_API_URL}/audio/transcriptions",
                headers={"Authorization": f"Bearer {openai_key}"},
                files={"file": (audio.filename or "audio.wav", audio_bytes, audio.content_type or "audio/wav")},
                data={"model": "whisper-1"},
            )
        if resp.status_code != 200:
            raise HTTPException(502, f"Whisper API devolvió {resp.status_code}: {resp.text[:200]}")
        transcript = resp.json().get("text", "").strip()
    except _httpx.TimeoutException:
        raise HTTPException(504, "Timeout esperando respuesta de Whisper API.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Error de transcripción: {str(exc)[:150]}")

    if not transcript:
        raise HTTPException(422, "Whisper no pudo transcribir el audio (resultado vacío).")

    result = _process_voice_core(transcript, db, current_user)
    return {**result, "whisper_transcript": transcript}


from app.schemas.ai_modules import VoiceCommandPayload


@router.post("/voice/command", summary="Procesar comando de voz")
def process_voice_command(
    payload: VoiceCommandPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _process_voice_core(payload.transcript.strip(), db, current_user)


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
def client_portal_chat(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    try:
        return _svc.client_portal_chat(db, payload)
    except ValueError as e:
        err = str(e)
        if "missing_fields" in err: raise HTTPException(400, "client_token and message required")
        if "invalid_token" in err: raise HTTPException(401, "Token de cliente inválido")
        raise HTTPException(400, err)


# ─── Revenue forecast (pure-Python linear regression) ────────────────────────

@router.post("/revenue-forecast", summary="Previsión de ingresos con regresión lineal")
def revenue_forecast(
    months_ahead: int = 3,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return _svc.revenue_forecast(db, months_ahead=months_ahead)


# ─── Smart schedule ───────────────────────────────────────────────────────────

from app.schemas.ai_modules import SmartScheduleRequest


@router.post("/smart-schedule", summary="Sugerir calendario de tareas sin fecha con IA")
def smart_schedule(
    payload: SmartScheduleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.smart_schedule(db, payload, current_user)


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
        team_load_pct=85.0,
    )

    return {
        "project_id":   project_id,
        "project_name": project.name,
        "cpi": round(data["cpi"], 3),
        "spi": round(data["spi"], 3),
        "budget_used_pct":       round(data["budget_used_pct"], 1),
        "elapsed_pct":           round(data["elapsed_pct"], 1),
        "task_completion_pct":   round(data["task_completion_pct"], 1),
        "overdue_task_ratio":    round(data["overdue_ratio"], 3),
        **result,
    }
