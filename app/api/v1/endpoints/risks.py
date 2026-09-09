from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIResponse, APIListResponse
from app.models.user import User, UserRole
from app.services import risk_service
from app.services.risk_scoring import risk_level, risk_score
from app.services.risk_service import (
    serialize_risk as _risk_out,
)
from app.schemas.risks import RiskIn, RiskUpdate

router = APIRouter()


@router.get("/all/portfolio", response_model=APIListResponse[dict], summary="Riesgos de toda la cartera")
def get_portfolio_risks(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    risks = risk_service.get_portfolio_risks(db)
    result = []
    for r in risks:
        d = _risk_out(r)
        d["project_name"] = r.project.name if r.project else "—"
        d["project_code"] = r.project.code if r.project else "—"
        result.append(d)
    return APIListResponse.ok(items=result)



@router.get("/{project_id}", summary="Registro de riesgos de un proyecto")
def get_risks(
    project_id: str,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    risks = risk_service.get_risks_by_project(db, project_id, status=status)
    result = [_risk_out(r) for r in risks]

    # Summary
    by_level = {}
    for r in result:
        lvl = r["risk_level"]
        by_level[lvl] = by_level.get(lvl, 0) + 1

    return APIResponse.ok(data={
        "risks": result,
        "summary": {
            "total": len(result),
            "open": sum(1 for r in result if r["status"] not in ["closed", "materialized"]),
            "by_level": by_level,
            "critical_count": by_level.get("critical", 0),
            "high_count": by_level.get("high", 0),
        }
    })


@router.post("/{project_id}", summary="Crear riesgo")
def create_risk(
    project_id: str,
    payload: RiskIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Acceso denegado")
    risk = risk_service.create_risk(
        db,
        project_id=project_id,
        identified_by=current_user.id,
        **payload.model_dump(),
    )
    return APIResponse.ok(data=_risk_out(risk))


@router.get("/{project_id}/{risk_id}", summary="Detalle de un riesgo")
def get_risk(
    project_id: str,
    risk_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Auditoria 2026-08 (hallazgo 37): esta ruta **no existia**.

    `risksApi` tiene listar, crear, actualizar y borrar; la lectura de uno era
    la unica sin ruta. `risk_service.get_risk(db, risk_id, project_id)` ya
    existia — la usan el `PATCH` y el `DELETE` de abajo — asi que aqui no se
    escribe consulta nueva.

    **Sin comprobacion de rol, a proposito.** Editar y borrar exigen admin o PM;
    leer, no: quien puede ver el registro de riesgos del proyecto
    (`GET /{project_id}`, que tampoco la tiene) puede ver uno de ellos. Anadir
    un rol aqui seria mas estricto que el listado y dejaria la lectura de uno
    por detras de la lectura de todos.
    """
    risk = risk_service.get_risk(db, risk_id, project_id)
    if not risk:
        raise HTTPException(404, "Riesgo no encontrado")
    return APIResponse.ok(data=_risk_out(risk))


@router.patch("/{project_id}/{risk_id}", summary="Actualizar riesgo")
def update_risk(
    project_id: str,
    risk_id: str,
    payload: RiskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Acceso denegado")
    risk = risk_service.get_risk(db, risk_id, project_id)
    if not risk:
        raise HTTPException(404, "Riesgo no encontrado")
    risk = risk_service.update_risk(db, risk, payload.model_dump(exclude_unset=True))
    return APIResponse.ok(data=_risk_out(risk))


@router.delete("/{project_id}/{risk_id}", summary="Eliminar riesgo")
def delete_risk(
    project_id: str,
    risk_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Acceso denegado")
    risk = risk_service.get_risk(db, risk_id, project_id)
    if not risk:
        raise HTTPException(404, "Riesgo no encontrado")
    enforce_abac(db, current_user, "risk", risk_id, action="delete")
    risk_service.delete_risk(db, risk)
    return APIResponse.ok(data={"ok": True, "message": "Riesgo eliminado correctamente"})
_risk_level = risk_level
_risk_score = risk_score
