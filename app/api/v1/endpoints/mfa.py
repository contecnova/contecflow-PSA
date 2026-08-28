"""MFA (TOTP): segundo factor de autenticacion.

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
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIResponse
import app.services.mfa_service as _mfa

router = APIRouter()


@router.get("/mfa/status", summary="Estado MFA del usuario actual")
def mfa_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=_mfa.get_mfa_status(current_user.id, db))


@router.post("/mfa/setup", summary="Iniciar configuración MFA — genera secret y QR URL")
def mfa_setup(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return APIResponse.ok(data=_mfa.setup_mfa(current_user, db))
    except ValueError as e:
        msg = str(e)
        if "pyotp" in msg:
            raise HTTPException(
                501,
                "MFA TOTP no disponible: falta la librería pyotp. Instala con 'pip install pyotp' y reinicia el backend."
            )
        raise HTTPException(400, msg)


class MFAVerifyPayload(BaseModel):
    code: str


@router.post("/mfa/verify", summary="Verificar código TOTP y activar MFA")
def mfa_verify(
    payload: MFAVerifyPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return APIResponse.ok(data=_mfa.verify_and_activate_mfa(current_user, payload.code, db))
    except ValueError as e:
        msg = str(e)
        if "pyotp" in msg:
            raise HTTPException(
                501,
                "MFA TOTP no disponible: falta la librería pyotp. Instala con 'pip install pyotp' y reinicia el backend."
            )
        raise HTTPException(400, msg)


@router.post("/mfa/validate", summary="Validar código MFA durante el login")
def mfa_validate(
    payload: MFAVerifyPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return APIResponse.ok(data=_mfa.validate_mfa_code(current_user, payload.code, db))
    except ValueError as e:
        msg = str(e)
        if "pyotp" in msg:
            raise HTTPException(503, msg)
        raise HTTPException(401, msg)


@router.delete("/mfa/disable", summary="Desactivar MFA")
def mfa_disable(
    payload: MFAVerifyPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "mfa", str(current_user.id), action="delete")
    try:
        return APIResponse.ok(data=_mfa.disable_mfa(current_user, payload.code, db))
    except ValueError as e:
        msg = str(e)
        if "pyotp" in msg:
            raise HTTPException(503, msg)
        raise HTTPException(400, msg)
