"""Lista de puesta en marcha de una empresa (revisión 2026-11, lo que contecmind tenía).

Qué falta por configurar en la empresa, cada punto MEDIDO sobre sus datos (nada
se marca a mano): proveedor de IA, correo, buzón de soporte, usuarios, clientes,
flujos de aprobación, SLA y, como recomendados, SSO, MFA obligatoria, tope de
gasto en IA y aislamiento en la base. Cada punto dice lo que midió y a qué
pantalla ir para resolverlo.

La marca de la empresa no está: tiene API (`/orgs/{id}/branding`) pero ninguna
pantalla, así que un enlace llevaría a ninguna parte. La MFA obligatoria sí se
mide, pero va sin enlace por lo mismo: sólo el superadmin la activa, por API
(`PATCH /organizations/{id}`); la pantalla de organizaciones no tiene el interruptor.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session


def _contar(db: Session, modelo, org: str, *filtros) -> int:
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        return db.query(func.count(modelo.id)).filter(modelo.organization_id == org, *filtros).scalar() or 0


def _punto(id_: str, hecho: bool, medido, enlace, necesario: bool = True) -> dict:
    return {"id": id_, "done": bool(hecho), "measured": medido, "link": enlace, "required": necesario}


def lista(db: Session, org: str) -> dict:
    from app.core.config import settings
    from app.models.ai_providers import AIProvider
    from app.models.billing_reports import ApprovalWorkflow
    from app.models.clients import Client
    from app.models.enterprise import SSOConfig
    from app.models.mfa import Organization
    from app.models.service_desk.catalog import SLAPolicy
    from app.models.user import User
    from app.services.settings_service import get_runtime_float, get_runtime_str

    proveedores = _contar(db, AIProvider, org, AIProvider.is_active.is_(True))
    del_entorno = bool((settings.AI_PROVIDER or "").strip() and (settings.AI_API_KEY or "").strip())
    usuarios = _contar(db, User, org, User.is_active.is_(True))
    buzon = (get_runtime_str(db, "SD_INBOUND_ADDRESS", org) or "").strip()
    tope = float(get_runtime_float(db, "AI_DAILY_BUDGET_USD", org) or 0)
    empresa = db.get(Organization, org)
    sso = _contar(db, SSOConfig, org, SSOConfig.is_active.is_(True), SSOConfig.is_deleted.is_(False))
    try:
        from app.db import rls
        aislamiento = rls.estado(db.connection())
    except Exception:
        aislamiento = {"armed": False, "reason": "no se pudo medir"}

    puntos = [
        _punto("ai_provider", proveedores or del_entorno,
               {"providers": proveedores, "env_provider": del_entorno}, "/ai-hub"),
        _punto("email", bool((settings.SMTP_HOST or "").strip()),
               {"smtp_host": bool((settings.SMTP_HOST or "").strip())}, None),
        _punto("support_inbox", bool(buzon), {"address": buzon or None}, "/service-desk?tab=config"),
        _punto("users", usuarios >= 2, {"active_users": usuarios}, "/settings?tab=users"),
        _punto("clients", _contar(db, Client, org) >= 1, {"clients": _contar(db, Client, org)}, "/clients"),
        _punto("approval_workflows", _contar(db, ApprovalWorkflow, org, ApprovalWorkflow.is_active.is_(True)) >= 1,
               {"workflows": _contar(db, ApprovalWorkflow, org, ApprovalWorkflow.is_active.is_(True))},
               "/settings/approval-workflows"),
        _punto("sla", _contar(db, SLAPolicy, org, SLAPolicy.is_active.is_(True)) >= 1,
               {"policies": _contar(db, SLAPolicy, org, SLAPolicy.is_active.is_(True))}, "/service-desk?tab=config"),
        _punto("sso", sso >= 1, {"active_sso": sso}, "/enterprise?tab=sso", necesario=False),
        _punto("mfa", bool(getattr(empresa, "require_mfa", False)),
               {"require_mfa": bool(getattr(empresa, "require_mfa", False))}, None, necesario=False),
        _punto("ai_budget", tope > 0, {"daily_budget_usd": tope}, "/settings?tab=runtime-flags", necesario=False),
        _punto("db_isolation", bool(aislamiento.get("armed")), {"reason": aislamiento.get("reason")},
               "/settings?tab=system-state", necesario=False),
    ]
    necesarios = [p for p in puntos if p["required"]]
    return {"items": puntos,
            "required_done": sum(p["done"] for p in necesarios), "required_total": len(necesarios),
            "recommended_done": sum(p["done"] for p in puntos if not p["required"]),
            "recommended_total": sum(1 for p in puntos if not p["required"])}
