"""
ai_modules — thin router delegating to app.services.ai_modules_service
"""
from app.core.config import settings
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Body
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from typing import Optional, List
from datetime import datetime, timedelta, date, timezone
from pydantic import BaseModel
import json
import os
import time
import logging

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User
from app.models.project import Project
from app.models.task import Task
from app.models.service_desk import Ticket
from app.models.imputation import Imputation
from app.models.ai_chat import (
    AIPrediction, AIActionLog,
    AIMeeting, AIMeetingAction,
    AIContract, AIContractClause,
    AIKBArticle, AIVoiceCommand,
    AIClientChatSession, AIClientChatMessage,
)
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
    q = db.query(AIPrediction)
    if severity:         q = q.filter(AIPrediction.severity == severity)
    if prediction_type:  q = q.filter(AIPrediction.prediction_type == prediction_type)
    if only_unacked:     q = q.filter(AIPrediction.is_acknowledged == False)
    preds = q.order_by(AIPrediction.created_at.desc()).limit(50).all()
    return [{
        "id": p.id, "type": p.prediction_type, "severity": p.severity,
        "title": p.title, "explanation": p.explanation,
        "recommended_action": p.recommended_action,
        "probability": p.probability, "entity_type": p.entity_type,
        "entity_id": p.entity_id, "created_at": str(p.created_at)[:16],
        "methodology": "rules_based",
    } for p in preds]


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
    pred = db.query(AIPrediction).filter(AIPrediction.id == pred_id).first()
    if not pred: raise HTTPException(404)
    pred.is_acknowledged = True
    pred.acknowledged_by = current_user.id
    pred.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# SMART MEETING ASSISTANT
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/meetings", summary="Listar reuniones procesadas")
def list_meetings(
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(AIMeeting).options(joinedload(AIMeeting.actions))
    if project_id: q = q.filter(AIMeeting.project_id == project_id)
    meetings = q.order_by(AIMeeting.created_at.desc()).limit(50).all()
    return [{
        "id": m.id, "title": m.title, "project_id": m.project_id,
        "platform": m.platform, "duration_min": m.duration_min,
        "status": m.status,
        "actions_count": len(m.actions),
        "created_actions": sum(1 for a in m.actions if a.is_created),
        "meeting_date": str(m.meeting_date)[:16] if m.meeting_date else None,
        "created_at": str(m.created_at)[:16],
    } for m in meetings]


class MeetingProcessPayload(BaseModel):
    title: Optional[str] = None
    project_id: Optional[str] = None
    platform: str = "upload"
    transcript: str
    participants: Optional[List[str]] = None
    meeting_date: Optional[str] = None
    duration_min: Optional[int] = None


@router.post("/meetings/process", summary="Procesar transcripción de reunión con IA")
def process_meeting(
    payload: MeetingProcessPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    t0 = time.time()
    meeting = AIMeeting(
        project_id=payload.project_id,
        title=payload.title or "Reunión procesada por IA",
        platform=payload.platform,
        duration_min=payload.duration_min,
        participants=json.dumps(payload.participants or []),
        transcript=payload.transcript[:50000],
        status="processing",
        created_by=current_user.id,
    )
    if payload.meeting_date:
        try:
            meeting.meeting_date = datetime.fromisoformat(payload.meeting_date)
        except ValueError:
            raise HTTPException(400, "Formato de meeting_date inválido, se espera YYYY-MM-DD[T]HH:MM:SS")
    db.add(meeting); db.commit(); db.refresh(meeting)

    try:
        MAP_SYSTEM = (
            "Eres un asistente experto en análisis de reuniones de trabajo. "
            "Analiza el texto dado y extrae puntos clave: decisiones, acciones, riesgos."
        )
        REDUCE_SYSTEM = MAP_SYSTEM
        MAP_PREFIX = "Analiza este fragmento de transcripción de reunión:"
        REDUCE_SUFFIX = """Basándote en el análisis anterior, genera el informe final completo.

Responde SOLO con JSON:
{
  "title": "...",
  "summary": "...",
  "decisions": ["...", "..."],
  "actions": [{"description": "...", "assignee_name": "...", "due_date_text": "..."}],
  "risks": ["...", "..."]
}"""
        text = _map_reduce_analysis(
            payload.transcript,
            map_system=MAP_SYSTEM,
            map_user_prefix=MAP_PREFIX,
            reduce_system=REDUCE_SYSTEM,
            reduce_user_suffix=REDUCE_SUFFIX,
            db=db,
            module="meeting_assistant",
            user_id=current_user.id,
            map_tokens=1500,
            reduce_tokens=2000,
        )
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            meeting.title   = data.get("title", meeting.title)
            meeting.summary = data.get("summary")
            meeting.decisions = json.dumps(data.get("decisions", []))
            meeting.risks_mentioned = json.dumps(data.get("risks", []))

            for action_data in data.get("actions", []):
                action = AIMeetingAction(
                    meeting_id=meeting.id,
                    description=action_data.get("description", ""),
                    assignee_name=action_data.get("assignee_name"),
                    due_date_text=action_data.get("due_date_text"),
                )
                if action_data.get("assignee_name"):
                    user = db.query(User).filter(
                        User.full_name.ilike(f"%{action_data['assignee_name']}%")
                    ).first()
                    if user: action.assignee_id = user.id
                db.add(action)

        meeting.status = "done"
    except Exception as e:
        meeting.summary = f"Error procesando con IA: {str(e)[:100]}"
        meeting.status = "failed"

    latency = int((time.time() - t0) * 1000)
    _log_action(db, current_user.id, "meeting_assistant", "process",
                f"transcript_len={len(payload.transcript)}", meeting.summary, latency=latency)
    db.commit()
    db.refresh(meeting)

    return {
        "meeting_id": meeting.id,
        "title": meeting.title,
        "summary": meeting.summary,
        "decisions": json.loads(meeting.decisions or "[]"),
        "risks": json.loads(meeting.risks_mentioned or "[]"),
        "actions": [{"id": a.id, "description": a.description,
                     "assignee_name": a.assignee_name,
                     "due_date_text": a.due_date_text} for a in meeting.actions],
        "status": meeting.status,
        "latency_ms": latency,
    }


@router.post("/meetings/{meeting_id}/create-tasks", summary="Crear tareas en Clarive desde acciones de reunión")
def create_tasks_from_meeting(
    meeting_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meeting = db.query(AIMeeting).options(joinedload(AIMeeting.actions)).filter(
        AIMeeting.id == meeting_id
    ).first()
    if not meeting: raise HTTPException(404)

    project_id = payload.get("project_id") or meeting.project_id
    if not project_id:
        raise HTTPException(400, "Se requiere project_id para crear tareas")
    action_ids = payload.get("action_ids", [a.id for a in meeting.actions])
    created = []

    for action in meeting.actions:
        if action.id not in action_ids or action.is_created: continue

        task = Task(
            project_id=project_id,
            title=action.description[:255],
            status="todo", priority="medium",
            assignee_id=action.assignee_id,
            created_by=current_user.id,
        )
        db.add(task); db.flush()
        action.task_id    = task.id
        action.is_created = True
        created.append({"action_id": action.id, "task_id": task.id, "title": task.title})

    db.commit()
    return {"ok": True, "tasks_created": len(created), "tasks": created}


@router.get("/meetings/{meeting_id}", summary="Detalle de reunión")
def get_meeting(
    meeting_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = db.query(AIMeeting).options(joinedload(AIMeeting.actions)).filter(
        AIMeeting.id == meeting_id
    ).first()
    if not m: raise HTTPException(404)
    return {
        "id": m.id, "title": m.title, "project_id": m.project_id,
        "platform": m.platform, "duration_min": m.duration_min,
        "summary": m.summary,
        "decisions": json.loads(m.decisions or "[]"),
        "risks": json.loads(m.risks_mentioned or "[]"),
        "participants": json.loads(m.participants or "[]"),
        "status": m.status,
        "actions": [{
            "id": a.id, "description": a.description,
            "assignee_name": a.assignee_name, "assignee_id": a.assignee_id,
            "due_date_text": a.due_date_text, "is_created": a.is_created,
            "task_id": a.task_id,
        } for a in m.actions],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AI CONTRACT INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/contracts-ai", summary="Listar contratos analizados por IA")
def list_ai_contracts(
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    q = db.query(AIContract).options(joinedload(AIContract.clauses))
    if project_id: q = q.filter(AIContract.project_id == project_id)
    contracts = q.order_by(AIContract.created_at.desc()).limit(50).all()
    return [{
        "id": c.id, "client_name": c.client_name, "project_id": c.project_id,
        "filename": c.filename, "status": c.status,
        "total_value": c.total_value, "risk_level": c.risk_level,
        "scope_creep_alerts": c.scope_creep_alerts,
        "clauses_count": len(c.clauses),
        "at_risk_clauses": sum(1 for cl in c.clauses if cl.is_at_risk),
        "created_at": str(c.created_at)[:16],
    } for c in contracts]


class ContractAnalyzePayload(BaseModel):
    project_id: Optional[str] = None
    client_name: Optional[str] = None
    filename: Optional[str] = None
    contract_text: str


@router.post("/contracts-ai/analyze", summary="Analizar contrato con IA")
def analyze_contract(
    payload: ContractAnalyzePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    t0 = time.time()
    contract = AIContract(
        project_id=payload.project_id,
        client_name=payload.client_name,
        filename=payload.filename,
        file_content=payload.contract_text[:20000],
        status="analyzing",
        created_by=current_user.id,
    )
    db.add(contract); db.commit(); db.refresh(contract)

    try:
        MAP_SYSTEM = (
            "Eres un experto en análisis de contratos de servicios profesionales. "
            "Analiza el fragmento dado y extrae cláusulas relevantes, penalizaciones, "
            "entregables, hitos de pago, SLAs, terminación y riesgos."
        )
        REDUCE_SYSTEM = MAP_SYSTEM
        MAP_PREFIX = "Analiza este fragmento del contrato:"
        REDUCE_SUFFIX = """Basándote en el análisis anterior del contrato completo, genera el informe consolidado.

Responde SOLO con JSON:
{
  "total_value": 0.0,
  "scope_summary": "...",
  "risk_level": "medium",
  "clauses": [
    {"type": "deliverable|penalty|milestone|sla|termination|payment|scope",
     "title": "...", "description": "...", "original_text": "...",
     "impact_amount": null, "due_date": null, "is_at_risk": false, "risk_reason": null}
  ]
}"""
        text = _map_reduce_analysis(
            payload.contract_text,
            map_system=MAP_SYSTEM,
            map_user_prefix=MAP_PREFIX,
            reduce_system=REDUCE_SYSTEM,
            reduce_user_suffix=REDUCE_SUFFIX,
            db=db,
            module="contract_intelligence",
            user_id=current_user.id,
            map_tokens=1500,
            reduce_tokens=3000,
        )
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            contract.total_value   = data.get("total_value")
            contract.scope_summary = data.get("scope_summary")
            contract.risk_level    = data.get("risk_level", "medium")
            at_risk = 0
            for cl_data in data.get("clauses", []):
                cl = AIContractClause(
                    contract_id=contract.id,
                    clause_type=cl_data.get("type", "scope"),
                    title=cl_data.get("title", "")[:255],
                    description=cl_data.get("description"),
                    original_text=cl_data.get("original_text"),
                    impact_amount=cl_data.get("impact_amount"),
                    is_at_risk=cl_data.get("is_at_risk", False),
                    risk_reason=cl_data.get("risk_reason"),
                )
                if cl_data.get("due_date"):
                    try:
                        cl.due_date = datetime.fromisoformat(cl_data["due_date"])
                    except ValueError:
                        logging.getLogger(__name__).warning(
                            f"Invalid due_date in contract clause: {cl_data.get('due_date')}")
                db.add(cl)
                if cl.is_at_risk: at_risk += 1
            contract.scope_creep_alerts = at_risk
        contract.status = "done"
    except Exception as e:
        contract.scope_summary = f"Error: {str(e)[:100]}"
        contract.status = "failed"

    latency = int((time.time() - t0) * 1000)
    _log_action(db, current_user.id, "contract_intelligence", "analyze",
                f"contract_len={len(payload.contract_text)}", f"risk={contract.risk_level}",
                latency=latency)
    db.commit()
    db.refresh(contract)

    return {
        "contract_id": contract.id,
        "status": contract.status,
        "risk_level": contract.risk_level,
        "scope_summary": contract.scope_summary,
        "total_value": contract.total_value,
        "clauses_count": len(contract.clauses),
        "at_risk_clauses": contract.scope_creep_alerts,
        "latency_ms": latency,
    }


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
    q = db.query(AIKBArticle)
    if published_only: q = q.filter(AIKBArticle.is_published == True)
    if category:       q = q.filter(AIKBArticle.category == category)
    articles = q.order_by(AIKBArticle.created_at.desc()).limit(100).all()
    return [{
        "id": a.id, "title": a.title, "category": a.category,
        "tags": json.loads(a.tags or "[]"),
        "view_count": a.view_count, "helpful_votes": a.helpful_votes,
        "is_published": a.is_published, "is_ai_generated": a.is_ai_generated,
        "source_ticket_id": a.source_ticket_id,
        "created_at": str(a.created_at)[:10],
    } for a in articles]


@router.post("/kb/generate/{ticket_id}", summary="Generar artículo KB desde ticket resuelto")
def generate_kb_from_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket: raise HTTPException(404)

    title   = f"Cómo resolver: {ticket.title}"
    content = ""
    tags    = []

    try:
        prompt = f"""Crea un artículo de base de conocimiento profesional basado en este ticket de soporte resuelto.

Título del ticket: {ticket.title}
Descripción: {ticket.description or 'Sin descripción'}
Categoría: {ticket.ticket_type or 'General'}
Prioridad: {ticket.priority or 'medium'}

Responde SOLO con JSON:
{{
  "title": "Cómo [resolver/configurar/solucionar] ...",
  "content": "## Síntoma\\n...\\n## Causa\\n...\\n## Solución\\n...\\n## Pasos\\n1. ...\\n## Verificación\\n...",
  "tags": ["tag1", "tag2"],
  "category": "..."
}}"""
        text = _call_ai_unified(
            db, [{"role": "user", "content": prompt}],
            module="knowledge_base", user_id=current_user.id, max_tokens=1500
        )
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            data  = json.loads(match.group())
            title   = data.get("title", title)
            content = data.get("content", "")
            tags    = data.get("tags", [])
    except Exception as e:
        content = f"Error generando artículo: {str(e)[:100]}"

    article = AIKBArticle(
        source_ticket_id=ticket_id,
        title=title,
        content=content,
        tags=json.dumps(tags),
        category=ticket.ticket_type or "General",
        is_ai_generated=True,
        is_published=False,
    )
    db.add(article)
    _log_action(db, current_user.id, "knowledge_base", "generate_from_ticket",
                f"ticket={ticket_id}", f"title={title}")
    db.commit()
    db.refresh(article)
    _compute_kb_embedding(db, article.id, title + " " + (content or ""))
    return {"article_id": article.id, "title": article.title, "is_published": article.is_published}


@router.post("/kb/search", summary="Búsqueda semántica en KB")
def search_kb(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = payload.get("query", "")
    if not query: raise HTTPException(400, "query required")

    articles = _kb_vector_search(db, query, limit=10)
    if not articles:
        articles = db.query(AIKBArticle).filter(
            AIKBArticle.is_published == True,
            or_(
                AIKBArticle.title.ilike(f"%{query}%"),
                AIKBArticle.content.ilike(f"%{query}%"),
            )
        ).limit(10).all()

    for a in articles:
        a.view_count = (a.view_count or 0) + 1
    db.commit()

    return [{
        "id": a.id, "title": a.title, "category": a.category,
        "content_preview": a.content[:300] if a.content else "",
        "tags": json.loads(a.tags or "[]"),
    } for a in articles]


@router.post("/kb/rebuild-embeddings", summary="Reconstruir embeddings de todos los artículos KB")
def rebuild_kb_embeddings(
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    articles = db.query(AIKBArticle).all()
    count = 0
    for a in articles:
        _compute_kb_embedding(db, a.id, (a.title or "") + " " + (a.content or ""))
        count += 1
    return {"rebuilt": count}


@router.patch("/kb/{article_id}", summary="Actualizar artículo KB")
def update_kb(
    article_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    article = db.query(AIKBArticle).filter(AIKBArticle.id == article_id).first()
    if not article: raise HTTPException(404)
    for field in ["title", "content", "category", "is_published"]:
        if field in payload: setattr(article, field, payload[field])
    if "tags" in payload: article.tags = json.dumps(payload["tags"])
    if payload.get("is_published"): article.reviewed_by = current_user.id
    db.commit()
    if "title" in payload or "content" in payload:
        _compute_kb_embedding(db, article.id, article.title + " " + (article.content or ""))
    return {"ok": True}


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


class VoiceCommandPayload(BaseModel):
    transcript: str
    confidence: Optional[float] = None


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

CLIENT_AI_SYSTEM = """Eres el asistente de IA del portal de cliente de Clarive.
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
    client_token = payload.get("client_token")
    message      = payload.get("message", "")
    session_id   = payload.get("session_id")

    if not client_token or not message:
        raise HTTPException(400, "client_token and message required")

    from app.core.security import verify_client_token
    try:
        client_user = verify_client_token(client_token, db)
    except Exception:
        raise HTTPException(401, "Token de cliente inválido")

    if not client_user: raise HTTPException(401)

    session = None
    if session_id:
        session = db.query(AIClientChatSession).filter(
            AIClientChatSession.id == session_id,
            AIClientChatSession.client_user_id == client_user.id,
        ).first()
    if not session:
        session = AIClientChatSession(client_user_id=client_user.id)
        db.add(session); db.flush()

    project_data = _get_client_project_data(client_user, db)

    db.add(AIClientChatMessage(session_id=session.id, role="user", content=message))

    history = db.query(AIClientChatMessage).filter(
        AIClientChatMessage.session_id == session.id
    ).order_by(AIClientChatMessage.created_at.desc()).limit(8).all()
    history.reverse()

    messages = [{"role": m.role, "content": m.content} for m in history[:-1]]
    messages.append({"role": "user", "content": message})

    system = CLIENT_AI_SYSTEM.format(project_data=json.dumps(project_data, ensure_ascii=False))

    try:
        response_text = _call_ai_unified(
            db, messages, system=system,
            module="client_portal", max_tokens=800
        )
    except Exception as e:
        response_text = f"Error del asistente: {str(e)[:80]}"

    db.add(AIClientChatMessage(session_id=session.id, role="assistant", content=response_text))
    db.commit()

    return {"session_id": session.id, "response": response_text}


# ─── Revenue forecast (pure-Python linear regression) ────────────────────────

@router.post("/revenue-forecast", summary="Previsión de ingresos con regresión lineal")
def revenue_forecast(
    months_ahead: int = 3,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from calendar import monthrange

    now   = datetime.utcnow()
    start = (now.replace(day=1) - timedelta(days=365)).replace(day=1)

    try:
        from app.models.invoicing import Invoice
        rows = (
            db.query(
                func.date_trunc("month", Invoice.invoice_date).label("month"),
                func.sum(Invoice.amount).label("total"),
            )
            .filter(Invoice.invoice_date >= start, Invoice.status != "cancelled")
            .group_by(func.date_trunc("month", Invoice.invoice_date))
            .order_by(func.date_trunc("month", Invoice.invoice_date))
            .all()
        )
        history = [{"month": str(r.month)[:7], "amount": float(r.total or 0)} for r in rows]
    except Exception:
        rows = (
            db.query(
                func.date_trunc("month", Imputation.date).label("month"),
                func.sum(Imputation.hours).label("total_hours"),
            )
            .filter(Imputation.date >= start.date())
            .group_by(func.date_trunc("month", Imputation.date))
            .order_by(func.date_trunc("month", Imputation.date))
            .all()
        )
        history = [{"month": str(r.month)[:7], "amount": float((r.total_hours or 0) * 85)} for r in rows]

    if len(history) < 3:
        return {"error": "Insufficient data", "message": "Need at least 3 months of data", "history": history}

    n   = len(history)
    xs  = list(range(n))
    ys  = [h["amount"] for h in history]
    sx  = sum(xs);      sy  = sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sxx = sum(x * x for x in xs)
    denom = n * sxx - sx * sx
    if denom == 0:
        return {"error": "Degenerate data", "history": history}
    b = (n * sxy - sx * sy) / denom
    a = (sy - b * sx) / n

    y_mean = sy / n
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    r2     = 1 - ss_res / ss_tot if ss_tot > 0 else 1.0

    forecast = []
    last_month_str = history[-1]["month"]
    lm_year, lm_mon = int(last_month_str[:4]), int(last_month_str[5:7])
    for i in range(1, months_ahead + 1):
        xi    = n - 1 + i
        pred  = max(0.0, a + b * xi)
        fm    = lm_mon + i
        fy    = lm_year + (fm - 1) // 12
        fm    = (fm - 1) % 12 + 1
        label = f"{fy}-{fm:02d}"
        res_std = (ss_res / max(n - 2, 1)) ** 0.5
        ci    = 1.28 * res_std
        forecast.append({"month": label, "amount": round(pred, 2), "ci_low": round(max(0, pred - ci), 2), "ci_high": round(pred + ci, 2)})

    return {
        "history":       history,
        "forecast":      forecast,
        "r2":            round(r2, 4),
        "trend_monthly": round(b, 2),
        "model":         "OLS linear regression (pure Python)",
    }


# ─── Smart schedule ───────────────────────────────────────────────────────────

class SmartScheduleRequest(BaseModel):
    project_id: Optional[str] = None
    max_tasks: int = 20


@router.post("/smart-schedule", summary="Sugerir calendario de tareas sin fecha con IA")
def smart_schedule(
    payload: SmartScheduleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Task).filter(Task.start_date == None, Task.due_date == None)
    if payload.project_id:
        q = q.filter(Task.project_id == payload.project_id)
    unscheduled = q.filter(Task.status.notin_(["done", "cancelled", "closed"])).limit(payload.max_tasks).all()

    if not unscheduled:
        return {"scheduled": [], "message": "No unscheduled tasks found"}

    now   = datetime.utcnow()
    w4ago = (now - timedelta(weeks=4)).date()
    capacity = []
    users = db.query(User).filter(User.is_active == True).all()
    for u in users:
        hrs = db.query(func.sum(Imputation.hours)).filter(
            Imputation.user_id == u.id, Imputation.date >= w4ago
        ).scalar() or 0
        available = max(0, 40 - round(hrs / 4, 1))
        capacity.append({"name": u.full_name, "available_hours_per_week": available})

    task_list    = "\n".join(
        f"- [{t.id}] {t.title} (priority={t.priority or 'medium'}, points={t.story_points or '?'})"
        for t in unscheduled
    )
    capacity_str = "\n".join(f"  {c['name']}: ~{c['available_hours_per_week']}h/week free" for c in capacity[:10])
    today_str    = now.strftime("%Y-%m-%d")

    system = (
        "You are a project scheduling AI. Given a list of unscheduled tasks and team capacity, "
        "produce a realistic schedule starting from today. "
        "Return ONLY a JSON array of objects, no prose:\n"
        '[{"task_id": <int>, "suggested_start": "YYYY-MM-DD", "suggested_due": "YYYY-MM-DD", "rationale": "..."}]'
    )
    user_msg = (
        f"Today: {today_str}\n\n"
        f"Unscheduled tasks:\n{task_list}\n\n"
        f"Team capacity (available hours/week):\n{capacity_str}\n\n"
        "Schedule these tasks considering priority and capacity. "
        "Assume 1 story point ≈ 8 hours. Use a 40h/week team capacity baseline."
    )

    try:
        response = _call_ai_unified(db, [{"role": "user", "content": user_msg}], system=system,
                                    module="smart_schedule", user_id=current_user.id, max_tokens=2000)
        text = _extract_text(response)
        import re as _re
        import json as _json
        match = _re.search(r'\[.*\]', text, _re.DOTALL)
        scheduled = _json.loads(match.group(0)) if match else []
    except Exception as exc:
        return {"scheduled": [], "error": str(exc),
                "message": "AI scheduling failed — configure ANTHROPIC_API_KEY or OPENAI_API_KEY"}

    return {"scheduled": scheduled, "unscheduled_count": len(unscheduled), "capacity_summary": capacity[:10]}


# ── AI Overrun Prediction ──────────────────────────────────────────────────────

class OverrunPredictionOut(BaseModel):
    project_id:             str
    project_name:           str
    cost_overrun_prob:      float
    schedule_overrun_prob:  float
    cost_overrun_pct:       float
    schedule_overrun_days:  int
    confidence:             str
    signals:                list
    recommendation:         str


@router.post("/overrun-prediction", summary="Predicción de sobrecosto/retraso por proyecto")
def overrun_prediction(
    project_id: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    today = date.today()

    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    if not tasks:
        raise HTTPException(422, "El proyecto no tiene tareas; sin datos suficientes para predicción.")

    total_tasks   = len(tasks)
    done_tasks    = sum(1 for t in tasks if t.status in ("done", "closed", "cancelled"))
    overdue_tasks = sum(1 for t in tasks if t.due_date and str(t.due_date) < str(today)
                        and t.status not in ("done", "closed", "cancelled"))

    task_completion_pct = done_tasks / total_tasks * 100 if total_tasks > 0 else 0
    overdue_ratio       = overdue_tasks / total_tasks if total_tasks > 0 else 0

    budget      = float(project.budget_amount or 0)
    actual_cost = float(
        db.query(func.sum(Imputation.hours * 1)).filter(
            Imputation.project_id == project_id
        ).scalar() or 0
    )
    actual_cost_full = float(
        db.query(func.sum(Imputation.cost_amount)).filter(
            Imputation.project_id == project_id,
            Imputation.cost_amount != None,
        ).scalar() or actual_cost
    )
    budget_used_pct = (actual_cost_full / budget * 100) if budget > 0 else 0

    start = project.start_date
    end   = project.end_date_planned
    if start and end and end > start:
        total_days   = (end - start).days
        elapsed_days = min((today - start).days, total_days)
        elapsed_pct  = elapsed_days / total_days * 100
    else:
        elapsed_pct = task_completion_pct

    budget_per_task = budget / total_tasks if budget > 0 and total_tasks > 0 else 0
    ev = budget_per_task * done_tasks
    pv = budget * elapsed_pct / 100 if budget > 0 else 0
    ac = actual_cost_full

    cpi = ev / ac if ac > 0 else 1.0
    spi = ev / pv if pv > 0 else 1.0

    team_load_pct = 85.0

    result = _predict_overrun_ml(
        cpi=cpi, spi=spi,
        budget_used_pct=budget_used_pct,
        elapsed_pct=elapsed_pct,
        task_completion_pct=task_completion_pct,
        overdue_task_ratio=overdue_ratio,
        team_load_pct=team_load_pct,
    )

    return {
        "project_id":   project_id,
        "project_name": project.name,
        "cpi": round(cpi, 3),
        "spi": round(spi, 3),
        "budget_used_pct":       round(budget_used_pct, 1),
        "elapsed_pct":           round(elapsed_pct, 1),
        "task_completion_pct":   round(task_completion_pct, 1),
        "overdue_task_ratio":    round(overdue_ratio, 3),
        **result,
    }
