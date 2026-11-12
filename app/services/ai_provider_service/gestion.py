"""Alta, edicion, borrado y estadisticas de proveedores; probar sin guardar e importar el del `.env`.

Parte de `app.services.ai_provider_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.encryption import encrypt_value
from app.models.ai_providers import AIProvider
from app.models.ai_providers import AIUsageLog
from app.models.user import User
from app.core.asignacion import es_asignable
from sqlalchemy import func as sqlfunc
from app.core.errores import ErrorDeDominio
from app.services.ai_provider_service.catalogo import PROVIDER_CATALOG
from app.services.ai_provider_service.resolucion import proveedor_desde_entorno

# ── CRUD service functions ────────────────────────────────────────────────────

def list_providers(db: Session, *, is_superadmin: bool, organization_id) -> list:
    q = db.query(AIProvider).filter(AIProvider.is_active == True)  # audit #36 soft-delete
    if not is_superadmin and organization_id:
        q = q.filter(AIProvider.organization_id == organization_id)
    return q.order_by(AIProvider.is_default.desc(), AIProvider.name).all()


def _clear_default(db: Session, *, is_superadmin: bool, organization_id) -> None:
    q = db.query(AIProvider)
    if not is_superadmin and organization_id:
        q = q.filter(AIProvider.organization_id == organization_id)
    q.update({"is_default": False})


def create_provider(db: Session, *, organization_id, created_by, data: dict,
                    is_superadmin: bool) -> object:
    count_q = db.query(AIProvider)
    if not is_superadmin and organization_id:
        count_q = count_q.filter(AIProvider.organization_id == organization_id)
    count = count_q.count()
    raw_key = data.get("api_key") or None
    p = AIProvider(
        organization_id=organization_id,
        name=data.get("name", ""),
        provider=data.get("provider", "anthropic"),
        api_key=encrypt_value(raw_key) if raw_key else None,
        api_base_url=data.get("api_base_url") or None,
        default_model=data.get("default_model"),
        available_models=",".join(data.get("available_models", [])) if data.get("available_models") else None,
        is_default=data.get("is_default", count == 0),
        max_tokens=data.get("max_tokens", 2000),
        temperature=data.get("temperature", 0.7),
        priority=int(data.get("priority") or 100),
        created_by=created_by,
    )
    if p.is_default:
        _clear_default(db, is_superadmin=is_superadmin, organization_id=organization_id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def get_provider(db: Session, pid: str, *, is_superadmin: bool, organization_id) -> object | None:
    q = db.query(AIProvider).filter(AIProvider.id == pid)
    if not is_superadmin and organization_id:
        q = q.filter(AIProvider.organization_id == organization_id)
    return q.first()


#: Lo que se puede editar de un proveedor. Revisión 2026-11: se escribía
#: cualquier atributo que llegara (también `organization_id`, `total_cost_usd`
#: o `created_by`), así que un administrador podía mover un proveedor a otra
#: empresa o falsear su gasto acumulado.
CAMPOS_EDITABLES_DEL_PROVEEDOR = frozenset({
    "name", "provider", "api_key", "api_base_url", "api_version", "default_model", "available_models",
    "priority", "is_default", "max_tokens", "temperature", "timeout_seconds", "is_active",
})


def update_provider(db: Session, provider, data: dict, *,
                    is_superadmin: bool, organization_id) -> object:
    fuera = set(data) - CAMPOS_EDITABLES_DEL_PROVEEDOR
    if fuera:
        raise ErrorDeDominio(400, f"No se pueden cambiar: {', '.join(sorted(fuera))}")
    if data.get("is_default"):
        _clear_default(db, is_superadmin=is_superadmin, organization_id=organization_id)

    changed_runtime_fields = False
    for k, v in data.items():
        if k == "available_models" and isinstance(v, list):
            v = ",".join(v)
        if k == "api_key":
            if not v:
                continue
            v = encrypt_value(v)
        if k in {"api_key", "api_base_url", "default_model", "provider", "available_models"}:
            changed_runtime_fields = True
        if es_asignable(provider, k):
            setattr(provider, k, v)

    if changed_runtime_fields:
        provider.status = "active"
        provider.last_error = None

    db.commit()
    db.refresh(provider)
    return provider


def delete_provider(db: Session, provider) -> None:
    # audit #36 soft-delete — preserva trazabilidad de uso (AIUsageLog).
    provider.is_active = False
    db.commit()


def set_default_provider(db: Session, pid: str, *, is_superadmin: bool,
                         organization_id) -> object | None:
    _clear_default(db, is_superadmin=is_superadmin, organization_id=organization_id)
    q = db.query(AIProvider).filter(AIProvider.id == pid)
    if not is_superadmin and organization_id:
        q = q.filter(AIProvider.organization_id == organization_id)
    p = q.first()
    if p:
        p.is_default = True
        db.commit()
    return p


def update_provider_test_result(db: Session, provider, *, success: bool,
                                error: str | None = None) -> None:
    if success:
        provider.status = "active"
        provider.last_error = None
    else:
        provider.status = "error"
        provider.last_error = (error or "")[:500]
        provider.last_error_at = datetime.now(timezone.utc)
    db.commit()


def get_stats(db: Session, *, is_superadmin: bool, organization_id) -> dict:
    p_q = db.query(AIProvider)
    l_q = db.query(
        AIUsageLog.module,
        sqlfunc.count(AIUsageLog.id).label("calls"),
        sqlfunc.sum(AIUsageLog.tokens_in + AIUsageLog.tokens_out).label("tokens"),
        sqlfunc.sum(AIUsageLog.cost_usd).label("cost"),
    )
    if not is_superadmin and organization_id:
        p_q = p_q.filter(AIProvider.organization_id == organization_id)
        org_user_ids = db.query(User.id).filter(
            User.organization_id == organization_id
        ).scalar_subquery()
        l_q = l_q.filter(AIUsageLog.user_id.in_(org_user_ids))
    providers = p_q.all()
    logs = l_q.group_by(AIUsageLog.module).all()
    return {
        "providers": providers,
        "logs": logs,
        "total_cost": round(sum(p.total_cost_usd for p in providers), 4),
        "total_requests": sum(p.total_requests for p in providers),
    }


# ── Probar y descubrir modelos ANTES de guardar (revision 2026-11, de contecmind)

def proveedor_sin_guardar(datos: dict):
    """Un proveedor en memoria con lo escrito en el formulario (nada se guarda)."""
    from types import SimpleNamespace
    tipo = (datos.get("provider") or "").strip()
    if tipo not in PROVIDER_CATALOG:
        raise ValueError(f"Proveedor no soportado: {tipo}")
    clave = (datos.get("api_key") or "").strip()
    return SimpleNamespace(
        provider=tipo, name=datos.get("name") or tipo, api_key=encrypt_value(clave) if clave else None,
        api_base_url=(datos.get("api_base_url") or "").strip() or None,
        default_model=(datos.get("default_model") or PROVIDER_CATALOG[tipo].get("default_model")),
        max_tokens=int(datos.get("max_tokens") or 50), temperature=datos.get("temperature"),
    )


def importar_proveedor_de_entorno(db: Session, actor) -> "AIProvider":
    """El proveedor del `.env`, como fila editable de la empresa de `actor`."""
    entorno = proveedor_desde_entorno()
    if entorno is None:
        raise ValueError("No hay proveedor de IA en el .env")
    org = None if getattr(actor, "is_superadmin", False) else actor.organization_id
    ya = db.query(AIProvider).filter(AIProvider.provider == entorno.provider, AIProvider.is_active == True,  # noqa: E712
                                     AIProvider.organization_id == org).first()
    if ya is not None:
        raise ValueError(f"Ya hay un proveedor {entorno.provider} en la aplicación: «{ya.name}»")
    hay_por_defecto = db.query(AIProvider.id).filter(AIProvider.is_default == True,  # noqa: E712
                                                     AIProvider.is_active == True).first()
    p = AIProvider(
        name=entorno.provider.capitalize(), provider=entorno.provider, organization_id=org,
        api_key=entorno.api_key,  # ya va cifrada (ver ProveedorDeEntorno)
        api_base_url=entorno.api_base_url, default_model=entorno.default_model,
        max_tokens=entorno.max_tokens, temperature=entorno.temperature,
        is_default=hay_por_defecto is None, status="active", is_active=True, created_by=actor.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p
