"""AI Providers — CRUD y despacho multi-proveedor"""
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.core.encryption import encrypt_value
from app.db.session import get_db
from app.models.user import User
from app.services.ai_provider_service import (
    PROVIDER_CATALOG,
    call_ai,
    call_provider as _call_provider,
    get_default_provider,
)

_logger = logging.getLogger("ai_providers")

router = APIRouter()


def _out(p):
    return {
        "id": p.id, "name": p.name, "provider": p.provider,
        "status": p.status, "is_default": p.is_default,
        "default_model": p.default_model,
        "available_models": p.available_models.split(",") if p.available_models else [],
        "api_base_url": p.api_base_url,
        "has_api_key": bool(p.api_key),
        "max_tokens": p.max_tokens, "temperature": p.temperature,
        "total_requests": p.total_requests,
        "total_cost_usd": round(p.total_cost_usd, 4),
        "last_used_at": str(p.last_used_at) if p.last_used_at else None,
        "last_error": p.last_error,
        "created_at": str(p.created_at),
    }


# ── Endpoints de gestión ──────────────────────────────────────────────────────
@router.get("/catalog")
def get_catalog(_=Depends(get_current_user)):
    """Catálogo completo de proveedores y modelos disponibles."""
    return PROVIDER_CATALOG


@router.get("")
def list_providers(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.models.ai_providers import AIProvider
    q = db.query(AIProvider)
    if not current_user.is_superadmin and current_user.organization_id:
        q = q.filter(AIProvider.organization_id == current_user.organization_id)
    providers = q.order_by(AIProvider.is_default.desc(), AIProvider.name).all()
    return [_out(p) for p in providers]


@router.post("")
def create_provider(data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(require_admin)):
    from app.models.ai_providers import AIProvider
    # Si es el primero, marcarlo como default
    count_q = db.query(AIProvider)
    if not cu.is_superadmin and cu.organization_id:
        count_q = count_q.filter(AIProvider.organization_id == cu.organization_id)
    count = count_q.count()
    raw_key = data.get("api_key") or None
    p = AIProvider(
        organization_id=cu.organization_id,
        name=data.get("name", ""),
        provider=data.get("provider", "anthropic"),
        api_key=encrypt_value(raw_key) if raw_key else None,
        api_base_url=data.get("api_base_url") or None,
        default_model=data.get("default_model"),
        available_models=",".join(data.get("available_models", [])) if data.get("available_models") else None,
        is_default=data.get("is_default", count == 0),
        max_tokens=data.get("max_tokens", 2000),
        temperature=data.get("temperature", 0.7),
        created_by=cu.id,
    )
    if p.is_default:
        q = db.query(AIProvider)
        if not cu.is_superadmin and cu.organization_id:
            q = q.filter(AIProvider.organization_id == cu.organization_id)
        q.update({"is_default": False})
    db.add(p); db.commit(); db.refresh(p)
    return _out(p)


@router.patch("/{pid}")
def update_provider(pid: str, data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_admin)):
    from app.models.ai_providers import AIProvider
    q = db.query(AIProvider).filter(AIProvider.id == pid)
    if not _.is_superadmin and _.organization_id:
        q = q.filter(AIProvider.organization_id == _.organization_id)
    p = q.first()
    if not p: raise HTTPException(404)
    if data.get("is_default"):
        q2 = db.query(AIProvider)
        if not _.is_superadmin and _.organization_id:
            q2 = q2.filter(AIProvider.organization_id == _.organization_id)
        q2.update({"is_default": False})
    for k, v in data.items():
        if k == "available_models" and isinstance(v, list):
            v = ",".join(v)
        if k == "api_key":
            if not v:
                continue  # no borrar la key si se envía vacío
            v = encrypt_value(v)  # cifrar antes de guardar
        if hasattr(p, k): setattr(p, k, v)
    db.commit(); db.refresh(p)
    return _out(p)


@router.delete("/{pid}")
def delete_provider(pid: str, db: Session = Depends(get_db), _=Depends(require_admin)):
    from app.models.ai_providers import AIProvider
    q = db.query(AIProvider).filter(AIProvider.id == pid)
    if not _.is_superadmin and _.organization_id:
        q = q.filter(AIProvider.organization_id == _.organization_id)
    p = q.first()
    if not p: raise HTTPException(404)
    db.delete(p); db.commit()
    return {"ok": True}


@router.post("/{pid}/set-default")
def set_default(pid: str, db: Session = Depends(get_db), _=Depends(require_admin)):
    from app.models.ai_providers import AIProvider
    q = db.query(AIProvider)
    if not _.is_superadmin and _.organization_id:
        q = q.filter(AIProvider.organization_id == _.organization_id)
    q.update({"is_default": False})
    p_q = db.query(AIProvider).filter(AIProvider.id == pid)
    if not _.is_superadmin and _.organization_id:
        p_q = p_q.filter(AIProvider.organization_id == _.organization_id)
    p = p_q.first()
    if not p: raise HTTPException(404)
    p.is_default = True
    db.commit()
    return {"ok": True}


@router.post("/{pid}/test")
def test_provider(pid: str, db: Session = Depends(get_db), _=Depends(require_admin)):
    """Probar la conexión con el proveedor enviando un mensaje de prueba."""
    from app.models.ai_providers import AIProvider
    q = db.query(AIProvider).filter(AIProvider.id == pid)
    if not _.is_superadmin and _.organization_id:
        q = q.filter(AIProvider.organization_id == _.organization_id)
    p = q.first()
    if not p: raise HTTPException(404)

    t0 = time.time()
    try:
        result = _call_provider(p, [{"role": "user", "content": "Di solo 'OK' sin nada más."}],
                                system="Eres un asistente de prueba.", max_tokens=10)
        latency = int((time.time() - t0) * 1000)
        p.status = "active"
        p.last_error = None
        db.commit()
        return {"ok": True, "response": result.get("text", ""), "latency_ms": latency,
                "model": result.get("model", p.default_model)}
    except Exception as e:
        p.status = "error"
        p.last_error = str(e)[:500]
        p.last_error_at = datetime.now(timezone.utc)
        db.commit()
        return {"ok": False, "error": str(e)[:300]}


@router.get("/stats")
def get_stats(db: Session = Depends(get_db), _=Depends(get_current_user)):
    from app.models.ai_providers import AIProvider, AIUsageLog
    from sqlalchemy import func as sqlfunc
    p_q = db.query(AIProvider)
    l_q = db.query(
        AIUsageLog.module,
        sqlfunc.count(AIUsageLog.id).label("calls"),
        sqlfunc.sum(AIUsageLog.tokens_in + AIUsageLog.tokens_out).label("tokens"),
        sqlfunc.sum(AIUsageLog.cost_usd).label("cost"),
    )
    if not _.is_superadmin and _.organization_id:
        p_q = p_q.filter(AIProvider.organization_id == _.organization_id)
        org_user_ids = db.query(User.id).filter(User.organization_id == _.organization_id).scalar_subquery()
        l_q = l_q.filter(AIUsageLog.user_id.in_(org_user_ids))
    providers = p_q.all()
    logs = l_q.group_by(AIUsageLog.module).all()
    return {
        "providers": [_out(p) for p in providers],
        "by_module": [{"module": r.module, "calls": r.calls,
                       "tokens": r.tokens or 0, "cost": round(r.cost or 0, 4)} for r in logs],
        "total_cost": round(sum(p.total_cost_usd for p in providers), 4),
        "total_requests": sum(p.total_requests for p in providers),
    }


# ── Endpoint de chat unificado ────────────────────────────────────────────────
@router.post("/chat")
def unified_chat(data: dict = Body(...), db: Session = Depends(get_db),
                 cu=Depends(get_current_user)):
    """Chat unificado que usa el proveedor configurado."""
    messages = data.get("messages", [])
    if not messages:
        raise HTTPException(400, "messages requerido")
    system   = data.get("system", "Eres NexusAssist, el asistente IA de Clarive.")
    module   = data.get("module", "chat")
    provider_id = data.get("provider_id")
    model    = data.get("model")

    text = call_ai(db, messages, system=system, module=module,
                   user_id=cu.id, model=model, provider_id=provider_id)
    return {"text": text, "module": module}
