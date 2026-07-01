"""
Auth Sessions Router — User session management endpoints.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.db.session import get_db
from app.core.deps import get_current_user, Request
from app.models.user import User
from app.schemas.auth import ActiveSessionOut
from app.services.session_security import parse_risk_reasons
from app.core.responses import APIListResponse

import app.services.auth_service as _svc
from app.services.auth_service import (
    current_refresh_jti as _current_refresh_jti,
)

router = APIRouter()


@router.get("/sessions/active", response_model=APIListResponse[ActiveSessionOut], summary="Panel de sesiones activas del usuario")
def list_active_sessions(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve todas las sesiones activas del usuario actual con detalles de riesgo."""
    current_jti = _current_refresh_jti(request)
    now = datetime.now(timezone.utc)
    sessions = _svc.get_active_user_sessions(db, current_user.id, now)
    items = [
        ActiveSessionOut(
            id=s.id,
            ip_address=s.ip_address,
            ip_asn=s.ip_asn,
            ip_org=s.ip_org,
            country_code=s.country_code,
            region=s.region,
            city=s.city,
            user_agent=s.user_agent,
            device_name=s.device_name,
            risk_score=s.risk_score or 0,
            risk_level=s.risk_level or "low",
            risk_reasons=parse_risk_reasons(s.risk_reasons),
            auth_method=s.auth_method,
            last_seen_at=s.last_seen_at,
            expires_at=s.expires_at,
            created_at=s.created_at,
            is_current=(current_jti is not None and s.refresh_token_jti == current_jti),
        )
        for s in sessions
    ]
    return APIListResponse.ok(items=items, total=len(items))


@router.delete("/sessions/{session_id}", summary="Revocar dispositivo/sesión específica")
def revoke_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoca una sesión específica del usuario actual."""
    return _svc.revoke_one_session(db, session_id, current_user.id)


@router.post("/sessions/revoke-all", summary="Revocar todas las sesiones activas del usuario")
def revoke_all_sessions(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoca todas las sesiones activas EXCEPTO la actual."""
    current_jti = _current_refresh_jti(request)
    revoked = _svc.revoke_all_user_sessions_except_current(db, current_user.id, current_jti)
    return {"ok": True, "revoked": revoked}
