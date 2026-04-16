"""AI Providers — CRUD y despacho multi-proveedor"""
import logging
import time

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models.user import User
from app.services.ai_provider_service import (
    PROVIDER_CATALOG,
    call_ai,
    call_provider as _call_provider,
    create_provider as svc_create_provider,
    delete_provider as svc_delete_provider,
    get_provider,
    get_stats as svc_get_stats,
    list_providers as svc_list_providers,
    set_default_provider as svc_set_default_provider,
    update_provider as svc_update_provider,
    update_provider_test_result,
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
    providers = svc_list_providers(
        db, is_superadmin=current_user.is_superadmin, organization_id=current_user.organization_id
    )
    return [_out(p) for p in providers]


@router.post("")
def create_provider(data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(require_admin)):
    p = svc_create_provider(
        db,
        organization_id=cu.organization_id,
        created_by=cu.id,
        data=data,
        is_superadmin=cu.is_superadmin,
    )
    return _out(p)


@router.patch("/{pid}")
def update_provider(pid: str, data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_admin)):
    p = get_provider(db, pid, is_superadmin=_.is_superadmin, organization_id=_.organization_id)
    if not p:
        raise HTTPException(404)
    p = svc_update_provider(db, p, data, is_superadmin=_.is_superadmin, organization_id=_.organization_id)
    return _out(p)


@router.delete("/{pid}")
def delete_provider(pid: str, db: Session = Depends(get_db), _=Depends(require_admin)):
    p = get_provider(db, pid, is_superadmin=_.is_superadmin, organization_id=_.organization_id)
    if not p:
        raise HTTPException(404)
    svc_delete_provider(db, p)
    return {"ok": True}


@router.post("/{pid}/set-default")
def set_default(pid: str, db: Session = Depends(get_db), _=Depends(require_admin)):
    p = svc_set_default_provider(db, pid, is_superadmin=_.is_superadmin, organization_id=_.organization_id)
    if not p:
        raise HTTPException(404)
    return {"ok": True}


@router.post("/{pid}/test")
def test_provider(pid: str, db: Session = Depends(get_db), _=Depends(require_admin)):
    """Probar la conexión con el proveedor enviando un mensaje de prueba."""
    p = get_provider(db, pid, is_superadmin=_.is_superadmin, organization_id=_.organization_id)
    if not p:
        raise HTTPException(404)

    t0 = time.time()
    try:
        result = _call_provider(p, [{"role": "user", "content": "Di solo 'OK' sin nada más."}],
                                system="Eres un asistente de prueba.", max_tokens=10)
        latency = int((time.time() - t0) * 1000)
        update_provider_test_result(db, p, success=True)
        return {"ok": True, "response": result.get("text", ""), "latency_ms": latency,
                "model": result.get("model", p.default_model)}
    except Exception as e:
        update_provider_test_result(db, p, success=False, error=str(e))
        return {"ok": False, "error": str(e)[:300]}


@router.get("/stats")
def get_stats(db: Session = Depends(get_db), _=Depends(get_current_user)):
    data = svc_get_stats(db, is_superadmin=_.is_superadmin, organization_id=_.organization_id)
    return {
        "providers": [_out(p) for p in data["providers"]],
        "by_module": [{"module": r.module, "calls": r.calls,
                       "tokens": r.tokens or 0, "cost": round(r.cost or 0, 4)} for r in data["logs"]],
        "total_cost": data["total_cost"],
        "total_requests": data["total_requests"],
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
