"""ai_modules.contracts — extracted from the former ai_modules_service god-file."""

from __future__ import annotations
import json
import time
import logging
from datetime import datetime, timedelta, date, timezone
from app.core.timeutil import utcnow
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings
from app.services.ai_dispatch import call_ai
from app.core.security import verify_client_token
from app.models.ai_chat import (
    AIActionLog, AIPrediction, AIVoiceCommand,
    AIMeeting, AIMeetingAction, AIContract, AIContractClause,
    AIKBArticle, AIClientChatSession, AIClientChatMessage,
    AIAgentExecution as _ExecRecord,
)
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.service_desk import Ticket
from app.models.task import Task
from app.models.user import User
from app.worker import run_agent_task
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

_log = logging.getLogger(__name__)


from app.services.ai_modules._base import (
    log_action, map_reduce_analysis,
)

def list_ai_contracts(db: Session, project_id=None, current_user=None):
    # H22: filtro multi-tenant — los AIContract sin project_id (textos pegados
    # ad-hoc) se filtran por created_by; los enlazados a project se filtran
    # vía Project.organization_id. Superadmin sin filtro.
    q = db.query(AIContract).options(joinedload(AIContract.clauses))
    if project_id:
        q = q.filter(AIContract.project_id == project_id)
    if current_user is not None and not bool(getattr(current_user, "is_superadmin", False)):
        cu_org = getattr(current_user, "organization_id", None)
        cu_id  = getattr(current_user, "id", None)
        if cu_org:
            # AIContract ligado a project: filtrar por org del proyecto
            q_proj = q.join(Project, AIContract.project_id == Project.id).filter(
                Project.organization_id == cu_org
            )
            # AIContract ad-hoc (sin project) creado por el caller
            q_adhoc = q.filter(AIContract.project_id.is_(None), AIContract.created_by == cu_id)
            contracts = (q_proj.all() + q_adhoc.all())
            # Dedupe + sort
            seen = set()
            uniq = []
            for c in sorted(contracts, key=lambda c: c.created_at or datetime.min, reverse=True):
                if c.id in seen:
                    continue
                seen.add(c.id)
                uniq.append(c)
            contracts = uniq[:50]
        else:
            contracts = q.filter(AIContract.created_by == cu_id).order_by(
                AIContract.created_at.desc()
            ).limit(50).all()
    else:
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

def get_ai_contract(db: Session, contract_id: str, current_user=None) -> dict:
    """Detalle de un AIContract con todas sus cláusulas. Respeta multi-tenant."""
    contract = db.query(AIContract).options(joinedload(AIContract.clauses)).filter(
        AIContract.id == contract_id
    ).first()
    if not contract:
        return None
    # Visibility check: o eres superadmin, o lo creaste, o el project pertenece
    # a tu org.
    if current_user is not None and not bool(getattr(current_user, "is_superadmin", False)):
        cu_id  = getattr(current_user, "id", None)
        cu_org = getattr(current_user, "organization_id", None)
        allowed = False
        if contract.created_by and contract.created_by == cu_id:
            allowed = True
        elif contract.project_id and cu_org:
            proj = db.query(Project).filter(Project.id == contract.project_id).first()
            if proj and getattr(proj, "organization_id", None) == cu_org:
                allowed = True
        if not allowed:
            return None
    return {
        "id": contract.id,
        "client_name": contract.client_name,
        "project_id": contract.project_id,
        "filename": contract.filename,
        "status": contract.status,
        "total_value": contract.total_value,
        "scope_summary": contract.scope_summary,
        "risk_level": contract.risk_level,
        "scope_creep_alerts": contract.scope_creep_alerts,
        "created_at": str(contract.created_at)[:16],
        "clauses": [{
            "id": cl.id,
            "clause_type": cl.clause_type,
            "title": cl.title,
            "description": cl.description,
            "original_text": cl.original_text,
            "impact_amount": cl.impact_amount,
            "due_date": str(cl.due_date)[:10] if cl.due_date else None,
            "is_at_risk": cl.is_at_risk,
            "risk_reason": cl.risk_reason,
        } for cl in contract.clauses],
    }

def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extrae texto plano de un PDF (pypdf). Devuelve "" si falla."""
    try:
        from pypdf import PdfReader  # noqa: PLC0415
        from io import BytesIO  # noqa: PLC0415
        reader = PdfReader(BytesIO(pdf_bytes))
        chunks = []
        for page in reader.pages:
            try:
                chunks.append(page.extract_text() or "")
            except Exception:
                _log.debug("PDF page extract_text failed, skipping page", exc_info=True)
                continue
        return "\n\n".join(chunks).strip()
    except Exception as exc:
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning("PDF extraction failed: %s", exc)
        return ""

def analyze_contract(db: Session, payload, current_user) -> dict:
    import re

    t0 = time.time()
    # Item #69: registramos truncación. El LLM analiza ``contract_text``
    # completo vía map-reduce; en DB solo guardamos los primeros 20K para no
    # inflar la tabla. Si el contrato es más largo, anotamos el tamaño
    # original en ``scope_summary`` (queda registrado aunque el LLM falle).
    _full_contract = payload.contract_text or ""
    _was_truncated = len(_full_contract) > 20000
    contract = AIContract(
        project_id=payload.project_id,
        client_name=payload.client_name,
        filename=payload.filename,
        file_content=_full_contract[:20000],
        status="analyzing",
        created_by=current_user.id,
    )
    if _was_truncated:
        contract.scope_summary = (
            f"[TRUNCADO: contrato original {len(_full_contract)} chars; "
            f"guardados primeros 20000. Citas LLM pueden referirse a partes no persistidas.]"
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
        text = map_reduce_analysis(
            payload.contract_text,
            map_system=MAP_SYSTEM, map_user_prefix=MAP_PREFIX,
            reduce_system=REDUCE_SYSTEM, reduce_user_suffix=REDUCE_SUFFIX,
            db=db, module="contract_intelligence", user_id=current_user.id,
            map_tokens=1500, reduce_tokens=3000,
        )
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                _cleaned = re.sub(r",\s*([}\]])", r"\1", match.group())
                data = json.loads(_cleaned)
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
                        _log.warning(f"Invalid due_date in contract clause: {cl_data.get('due_date')}")
                db.add(cl)
                if cl.is_at_risk: at_risk += 1
            contract.scope_creep_alerts = at_risk
        contract.status = "done"
    except Exception as e:
        _log.exception("Contract intelligence analysis failed for contract=%s", getattr(contract, "id", None))
        contract.scope_summary = f"Error: {str(e)[:100]}"
        contract.status = "failed"

    latency = int((time.time() - t0) * 1000)
    log_action(db, current_user.id, "contract_intelligence", "analyze",
               f"contract_len={len(payload.contract_text)}", f"risk={contract.risk_level}",
               latency=latency)
    db.commit(); db.refresh(contract)

    return {
        "contract_id": contract.id, "status": contract.status,
        "risk_level": contract.risk_level, "scope_summary": contract.scope_summary,
        "total_value": contract.total_value,
        "clauses_count": len(contract.clauses),
        "at_risk_clauses": contract.scope_creep_alerts, "latency_ms": latency,
    }
