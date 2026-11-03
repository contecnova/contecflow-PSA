import json
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.cmdb import CMDBChangelog
from app.models.project import Project
from app.models.alm import ALMAsset
from app.models.service_desk import ConfigurationItem
from app.models.user import User
from app.schemas.service_desk import CIIn
from app.services.service_desk.cmdb_relation_service import get_ci_impact_payload
from app.services.service_desk.scoping import scope_ci_query as _scope_ci_query
from app.services.sla_service import next_ci_number as _next_ci_number
import logging

logger = logging.getLogger(__name__)


def list_cmdb_items(
    db: Session,
    current_user: User,
    page: int,
    page_size: int,
    *,
    q: Optional[str] = None,
    ci_type: Optional[str] = None,
    status: Optional[str] = None,
) -> list[ConfigurationItem]:
    """Los CIs activos (no borrados) que ve el usuario, con filtros."""
    consulta = db.query(ConfigurationItem).options(
        joinedload(ConfigurationItem.project),
        joinedload(ConfigurationItem.owner),
    ).filter(ConfigurationItem.is_active.is_(True))
    consulta = _scope_ci_query(consulta, db, current_user)
    if ci_type:
        consulta = consulta.filter(ConfigurationItem.ci_type == ci_type)
    if status:
        consulta = consulta.filter(ConfigurationItem.status == status)
    if q and q.strip():
        patron = f"%{q.strip()}%"
        consulta = consulta.filter(or_(
            ConfigurationItem.name.ilike(patron), ConfigurationItem.code.ilike(patron),
            ConfigurationItem.hostname.ilike(patron), ConfigurationItem.ip_address.ilike(patron),
        ))
    return (
        consulta.order_by(ConfigurationItem.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )


def _atributos(ci: ConfigurationItem) -> dict:
    try:
        datos = json.loads(ci.attributes) if ci.attributes else {}
    except (TypeError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _valor(v):
    return getattr(v, "value", v)


def serialize_ci(ci: ConfigurationItem) -> dict:
    return {
        "id": ci.id,
        "code": ci.code,
        "name": ci.name,
        "ci_type": _valor(ci.ci_type),
        "status": _valor(ci.status),
        "criticality": ci.criticality,
        "environment": ci.environment,
        "version": ci.version,
        "description": ci.description,
        "location": ci.location,
        "vendor": ci.vendor,
        "ip_address": ci.ip_address,
        "hostname": ci.hostname,
        "attributes": _atributos(ci),
        "project_id": ci.project_id,
        "project_name": ci.project.name if ci.project else None,
        "owner_user_id": ci.owner_user_id,
        "owner_name": ci.owner.full_name if ci.owner else None,
        "sla_policy_id": ci.sla_policy_id,
        "is_discovered": bool(ci.is_discovered),
        "discovery_provider": ci.discovery_provider,
        "last_discovered_at": ci.last_discovered_at.isoformat() if ci.last_discovered_at else None,
        "drift_detected_at": ci.drift_detected_at.isoformat() if ci.drift_detected_at else None,
    }


def serialize_cmdb_items(items: list[ConfigurationItem]) -> list[dict]:
    return [serialize_ci(ci) for ci in items]


def enforce_ci_org_constraints(db: Session, current_user: User, payload: CIIn, *, is_update: bool) -> None:
    if current_user.is_superadmin or not current_user.organization_id:
        return

    if payload.project_id:
        project = db.query(Project).filter(
            Project.id == payload.project_id,
            Project.organization_id == current_user.organization_id,
        ).first()
        if not project:
            if is_update:
                raise HTTPException(403, "No puedes mover CIs fuera de tu organización")
            raise HTTPException(403, "No puedes crear CIs para proyectos fuera de tu organización")

    if payload.owner_user_id:
        owner = db.query(User).filter(User.id == payload.owner_user_id).first()
        if not owner or owner.organization_id != current_user.organization_id:
            raise HTTPException(403, "No puedes asignar owner fuera de tu organización")


def _columnas(payload: CIIn) -> dict:
    datos = payload.model_dump()
    datos["attributes"] = json.dumps(datos["attributes"]) if datos.get("attributes") else None
    return datos


def build_ci(db: Session, payload: CIIn, current_user: User) -> ConfigurationItem:
    """Nace en la organizacion de quien lo crea: sin ella, nadie mas lo veria."""
    ci = ConfigurationItem(code=_next_ci_number(db), organization_id=current_user.organization_id,
                           **_columnas(payload))
    db.add(ci)
    db.flush()
    _historial(db, ci, current_user, "created", None, None, None, f"CI {ci.code} creado")
    return ci


def get_scoped_ci_by_id(
    db: Session,
    current_user: User,
    ci_id: str,
) -> Optional[ConfigurationItem]:
    return _scope_ci_query(db.query(ConfigurationItem), db, current_user).filter(ConfigurationItem.id == ci_id).first()


def get_scoped_ci_or_404(
    db: Session,
    current_user: User,
    ci_id: str,
) -> ConfigurationItem:
    ci = get_scoped_ci_by_id(db, current_user, ci_id)
    if not ci:
        raise HTTPException(404)
    return ci


def _historial(db: Session, ci: ConfigurationItem, user: Optional[User], accion: str,
               campo: Optional[str], antes, despues, resumen: str) -> None:
    db.add(CMDBChangelog(
        organization_id=ci.organization_id, item_id=ci.id,
        user_id=user.id if user else None, action=accion, field=campo,
        old_value=None if antes is None else str(_valor(antes))[:4000],
        new_value=None if despues is None else str(_valor(despues))[:4000],
        summary=resumen[:500],
    ))


def apply_ci_update(db: Session, ci: ConfigurationItem, payload: CIIn, current_user: User) -> None:
    """Aplica el cambio y deja en el historial cada campo que cambia."""
    for k, v in _columnas(payload).items():
        antes = getattr(ci, k)
        if _valor(antes) == _valor(v):
            continue
        setattr(ci, k, v)
        _historial(db, ci, current_user, "updated", k, antes, v, f"Campo '{k}' actualizado")


def delete_ci(db: Session, ci: ConfigurationItem, current_user: User) -> None:
    """Borrado logico: los tickets, problemas y cambios que lo citan lo conservan."""
    ci.is_active = False
    _historial(db, ci, current_user, "deleted", None, None, None, f"CI {ci.code} borrado")


def ci_changelog(db: Session, ci: ConfigurationItem, limit: int = 100) -> list[dict]:
    filas = (db.query(CMDBChangelog).filter(CMDBChangelog.item_id == ci.id)
             .order_by(CMDBChangelog.created_at.desc()).limit(limit).all())
    return [{
        "id": f.id, "action": f.action, "field": f.field,
        "old_value": f.old_value, "new_value": f.new_value, "summary": f.summary,
        "user_name": f.user.full_name if f.user else None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    } for f in filas]


def get_ci_deprecation_impact_payload(
    db: Session,
    current_user: User,
    ci_id: str,
    *,
    max_depth: int = 5,
    limit: int = 500,
    include_root_assets: bool = True,
) -> dict:
    """Estimate deprecation impact for one CI, including linked assets.

    Uses the CMDB dependency impact graph and maps impacted CIs to assets via
    ``Asset.ci_id``.
    """
    root_ci = get_scoped_ci_or_404(db, current_user, ci_id)
    impact = get_ci_impact_payload(db, current_user, ci_id, max_depth=max_depth, limit=limit)

    impacted_ci_ids = {item["ci_id"] for item in impact.get("impacted", [])}
    if include_root_assets:
        impacted_ci_ids.add(ci_id)

    # Solo los activos en vigor de ALM (auditoria 2026-11: un solo inventario).
    impacted_assets = (
        db.query(ALMAsset)
        .options(joinedload(ALMAsset.assigned_to), joinedload(ALMAsset.ci))
        .filter(ALMAsset.ci_id.in_(impacted_ci_ids), ALMAsset.is_active.is_(True),
                ALMAsset.status != "retired")
        .order_by(ALMAsset.name).all()
    )

    assets_by_status: dict[str, int] = {}
    assets_by_type: dict[str, int] = {}
    for a in impacted_assets:
        st, tp = str(_valor(a.status)), str(_valor(a.type))
        assets_by_status[st] = assets_by_status.get(st, 0) + 1
        assets_by_type[tp] = assets_by_type.get(tp, 0) + 1

    highest = impact.get("highest_criticality")
    if not highest:
        criticality_values = [
            str((i.get("criticality") or "medium")).lower()
            for i in impact.get("impacted", [])
        ]
        highest = (
            "critical" if "critical" in criticality_values
            else "high" if "high" in criticality_values
            else "medium" if criticality_values
            else "low"
        )

    risk_level = (
        "critical" if highest == "critical" or len(impacted_assets) >= 25
        else "high" if highest == "high" or len(impacted_assets) >= 10
        else "medium" if impact.get("impacted_count", 0) > 0 or len(impacted_assets) > 0
        else "low"
    )

    recommendations = [
        "Identificar y planificar reemplazo de activos desplegados ligados al CI deprecado.",
        "Definir ventana de cambio y rollback antes de retirar dependencias aguas abajo.",
    ]
    if assets_by_status.get("in_use", 0) > 0:
        recommendations.append("Coordinar comunicación con usuarios propietarios de activos en estado deployed.")
    if impact.get("impacted_count", 0) > 0:
        recommendations.append("Ejecutar pruebas de regresión sobre CIs impactados directos e indirectos.")

    return {
        "ci": {
            "id": root_ci.id,
            "code": root_ci.code,
            "name": root_ci.name,
            "ci_type": str(root_ci.ci_type.value if hasattr(root_ci.ci_type, "value") else root_ci.ci_type),
            "status": str(root_ci.status.value if hasattr(root_ci.status, "value") else root_ci.status),
            "criticality": root_ci.criticality,
        },
        "summary": {
            "risk_level": risk_level,
            "impacted_ci_count": impact.get("impacted_count", 0),
            "impacted_asset_count": len(impacted_assets),
            "direct_impacted_ci_count": len([i for i in impact.get("impacted", []) if i.get("depth") == 1]),
            "max_depth": impact.get("max_depth", max_depth),
            "truncated": impact.get("truncated", False),
            "highest_criticality": highest,
            "assets_by_status": assets_by_status,
            "assets_by_type": assets_by_type,
        },
        "impacted_cis": impact.get("impacted", []),
        "impacted_assets": [
            {
                "id": a.id,
                "asset_tag": a.asset_tag,
                "name": a.name,
                "type": str(_valor(a.type)),
                "status": str(_valor(a.status)),
                "assigned_to_id": a.assigned_to_id,
                "assigned_to_name": a.assigned_to.full_name if a.assigned_to else None,
                "ci_id": a.ci_id,
                "ci_name": a.ci.name if a.ci else None,
            }
            for a in impacted_assets
        ],
        "recommendations": recommendations,
    }
