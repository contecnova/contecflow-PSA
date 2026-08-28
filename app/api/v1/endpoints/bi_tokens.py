"""Tokens de BI externo y los datos que exponen.

Auditoria 2026-08 (hallazgo 22). Estas rutas vivian en
`app/api/v1/endpoints/mfa.py`, un fichero de 640 lineas con **38 rutas de ocho
dominios** —MFA, organizaciones, Slack, presupuestos, planificacion asistida,
escenarios, PDF y tokens de BI— servidas por un router llamado «mfa».

La mala ubicacion no fue solo desorden: el CRUD de organizaciones estaba
escondido ahi, y por eso nadie noto que a esos endpoints les faltaba la guarda de
superadministrador que su propio `summary` anunciaba. Fue la causa proxima del P0
numero 1 de la auditoria.

**Los paths no han cambiado.** ABAC y GRC derivan el modulo de la ruta, asi que
tocarlos alteraria los permisos en silencio.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from app.db.session import get_db
from app.core.deps import require_admin
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse, APIResponse
import app.services.bi_tokens_service as _bi

router = APIRouter()


def get_bi_token(request: Request) -> Optional[str]:
    """Extrae el BI Personal Access Token del header Authorization.

    Los endpoints `/bi/data/*` usan un esquema propio (tokens `bi_*`) en lugar
    del JWT estándar de usuarios. Centralizar aquí el parseo evita repetir la
    misma lógica en cada handler y facilita testear/instrumentar la entrada.
    Devuelve `None` si no hay token BI; el servicio decide cómo responder
    (típicamente 401 vía ValueError).
    """
    auth_header = request.headers.get("Authorization", "")
    if "bi_" not in auth_header:
        return None
    # Acepta tanto "Bearer bi_xxx" como "bi_xxx" para compatibilidad legacy.
    return auth_header.replace("Bearer bi_", "bi_")


@router.get("/bi/tokens", summary="Listar tokens BI")
def list_bi_tokens(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return APIListResponse.ok(items=_bi.list_bi_tokens(db))


class BITokenCreate(BaseModel):
    name: str
    tool: str = "powerbi"
    scopes: Optional[List[str]] = None
    expires_days: Optional[int] = None


@router.post("/bi/tokens", summary="Crear token BI")
def create_bi_token(
    payload: BITokenCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return APIResponse.ok(data=_bi.create_bi_token(payload.model_dump(), current_user.id, db))


@router.delete("/bi/tokens/{token_id}", summary="Revocar token BI")
def revoke_bi_token(
    token_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    enforce_abac(db, current_user, "bi_token", token_id, action="delete")
    try:
        return APIResponse.ok(data=_bi.revoke_bi_token(token_id, db))
    except ValueError:
        raise HTTPException(404)


@router.get("/bi/data/projects", summary="Datos de proyectos para BI")
def bi_data_projects(
    bi_token: Optional[str] = Depends(get_bi_token),
    db: Session = Depends(get_db),
):
    try:
        # Contrato externo consumido por herramientas BI (PowerBI) vía tokens bi_*:
        # NO se envuelve en el envelope canónico (rompería a esos consumidores externos).
        return _bi.bi_data_projects(bi_token, db)
    except ValueError:
        raise HTTPException(401, "Token BI inválido o caducado")


@router.get("/bi/data/timesheets", summary="Datos de imputaciones para BI")
def bi_data_timesheets(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(500, ge=1, le=5000),
    bi_token: Optional[str] = Depends(get_bi_token),
    db: Session = Depends(get_db),
):
    try:
        # Contrato externo BI (PowerBI): sin envelope.
        return _bi.bi_data_timesheets(bi_token, date_from, date_to, page, page_size, db)
    except ValueError:
        raise HTTPException(401, "Token BI inválido")


@router.get("/bi/data/kpis", summary="KPIs globales para BI")
def bi_data_kpis(
    bi_token: Optional[str] = Depends(get_bi_token),
    db: Session = Depends(get_db),
):
    try:
        # Contrato externo BI (PowerBI): sin envelope.
        return _bi.bi_data_kpis(bi_token, db)
    except ValueError:
        raise HTTPException(401, "Token BI inválido")
