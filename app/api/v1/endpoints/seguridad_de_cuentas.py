"""Seguridad de cuentas: política, usuarios, sesiones, aprobaciones y recertificación.

23-11-2026 (docs/seguridad/politicas_de_cuenta.md). Todo por empresa (la activa
de la sesión), con `seguridad.administrar` salvo la recertificación del
responsable (`seguridad.recertificar`) y los dispositivos propios. Cada acción
queda en `audit_log` con actor, IP, agente y empresa.

Prueba global 23-11-2026: las consultas y la transacción de cada acción viven en
`app/services/seguridad_de_cuentas/administracion.py`; aquí solo la ruta, la
guarda, la empresa activa y el origen de la petición.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error_http
from app.core.deps import get_current_user, requiere_capacidad
from app.db.session import get_db
from app.models.user import User
from app.services.seguridad_de_cuentas import administracion as adm, mfa as _mfa
from app.services.seguridad_de_cuentas.auditoria import Origen

router = APIRouter()


def _org(db: Session, user: User) -> str:
    org = (db.info or {}).get("organization_id") or user.organization_id
    if not org:
        raise error_http(400, "empresa_requerida")
    return org


# ── Política ────────────────────────────────────────────────────────────────

class CambioDePoliticaIn(BaseModel):
    changes: dict = Field(default_factory=dict, description="Campos de la política que cambian")
    reason: Optional[str] = Field(default=None, max_length=500)


@router.get("/policy", summary="Política de cuenta de la empresa, con los valores recomendados")
def get_policy(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    return adm.describir_politica(db, _org(db, current_user))


@router.put("/policy", summary="Cambiar la política de cuenta (con segundo administrador si se exige)")
def put_policy(request: Request, payload: CambioDePoliticaIn, db: Session = Depends(get_db),
               current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    return adm.cambiar_politica(db, _org(db, current_user), current_user, payload.changes, payload.reason,
                                Origen.de(request))


# ── Usuarios ────────────────────────────────────────────────────────────────

@router.get("/users", summary="Estado de seguridad de los usuarios de la empresa")
def list_users(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    return adm.estado_de_usuarios(db, _org(db, current_user))


@router.post("/users/{user_id}/unlock", summary="Desbloquear una cuenta bloqueada por intentos")
def unlock_user(user_id: str, request: Request, db: Session = Depends(get_db),
                current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    return adm.desbloquear(db, _org(db, current_user), current_user, user_id, Origen.de(request))


@router.post("/users/{user_id}/force-password-change", summary="Obligar a un usuario a cambiar la contraseña al entrar")
def force_password_change(user_id: str, request: Request, db: Session = Depends(get_db),
                          current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    return adm.forzar_cambio(db, _org(db, current_user), current_user, user_id, Origen.de(request))


class RestablecimientoForzadoIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500, description="Motivo (queda en la auditoría)")
    send_link: bool = Field(default=True, description="Enviar al usuario el enlace para elegir una contraseña nueva")


@router.post("/users/{user_id}/force-password-reset",
             summary="Forzar el restablecimiento: cambio obligatorio, cierre de sesiones y enlace por correo")
def force_password_reset(user_id: str, request: Request, payload: RestablecimientoForzadoIn,
                         db: Session = Depends(get_db),
                         current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    """23-11-2026 (incidencia «No hay función de restablecer contraseña»). Marca el
    cambio obligatorio en el próximo acceso, revoca TODAS sus sesiones y, si se
    pide, le manda el enlace de un solo uso. Con motivo y auditoría
    (`PASSWORD_RESET_FORCED`); la contraseña no la ve nadie."""
    return adm.forzar_restablecimiento(db, _org(db, current_user), current_user, user_id, Origen.de(request),
                                       payload.reason, payload.send_link)


@router.post("/force-password-change-all", summary="Obligar a todos los usuarios de la empresa a cambiar la contraseña")
def force_password_change_all(request: Request, db: Session = Depends(get_db),
                              current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    return adm.forzar_cambio_a_todos(db, _org(db, current_user), current_user, Origen.de(request))


class TemporalIn(BaseModel):
    password: Optional[str] = Field(default=None, max_length=1024, description="Vacío: se genera una")


@router.post("/users/{user_id}/temporary-password", summary="Poner una contraseña temporal (caduca y obliga a cambiarla)")
def set_temporary_password(user_id: str, request: Request, payload: TemporalIn = Body(default_factory=TemporalIn),
                           db: Session = Depends(get_db),
                           current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    return adm.poner_temporal(db, _org(db, current_user), current_user, user_id, Origen.de(request), payload.password)


class MotivoIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


@router.post("/users/{user_id}/reset-mfa", summary="Restablecer el segundo factor de un usuario")
def reset_mfa(user_id: str, request: Request, payload: MotivoIn = Body(default_factory=MotivoIn),
              db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    return adm.restablecer_mfa(db, _org(db, current_user), current_user, user_id, Origen.de(request), payload.reason)


@router.post("/users/{user_id}/revoke-sessions", summary="Cerrar todas las sesiones de un usuario")
def revoke_user_sessions(user_id: str, request: Request, db: Session = Depends(get_db),
                         current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    return adm.revocar_sesiones_de(db, _org(db, current_user), current_user, user_id, Origen.de(request))


# ── Sesiones de la empresa ─────────────────────────────────────────────────

@router.get("/sessions", summary="Sesiones activas de la empresa")
def list_sessions(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.services.seguridad_de_cuentas import sesiones
    items = sesiones.de_la_empresa(db, _org(db, current_user))
    return {"items": items, "total": len(items)}


@router.delete("/sessions/{session_id}", summary="Cerrar una sesión de la empresa")
def revoke_session(session_id: str, request: Request, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    return adm.revocar_sesion(db, _org(db, current_user), current_user, session_id, Origen.de(request))


# ── Solicitudes con segundo administrador ──────────────────────────────────

@router.get("/change-requests", summary="Cambios de seguridad pendientes de un segundo administrador")
def list_change_requests(db: Session = Depends(get_db),
                         current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    return adm.listar_solicitudes(db, _org(db, current_user))


class DecisionIn(BaseModel):
    comment: Optional[str] = Field(default=None, max_length=500)


@router.post("/change-requests/{request_id}/approve", summary="Aprobar y aplicar un cambio de seguridad (otro administrador)")
def approve_change_request(request_id: str, request: Request, payload: DecisionIn = Body(default_factory=DecisionIn),
                           db: Session = Depends(get_db),
                           current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    return adm.aprobar_solicitud(db, _org(db, current_user), current_user, request_id, payload.comment,
                                 Origen.de(request))


@router.post("/change-requests/{request_id}/reject", summary="Rechazar un cambio de seguridad")
def reject_change_request(request_id: str, request: Request, payload: DecisionIn = Body(default_factory=DecisionIn),
                          db: Session = Depends(get_db),
                          current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    return adm.rechazar_solicitud(db, _org(db, current_user), current_user, request_id, payload.comment,
                                  Origen.de(request))


# ── Recertificación de accesos ─────────────────────────────────────────────

class CampanaIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    due_at: Optional[datetime] = None


@router.get("/access-reviews", summary="Campañas de recertificación de accesos")
def list_access_reviews(db: Session = Depends(get_db),
                        current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.services.seguridad_de_cuentas import recertificacion
    items = recertificacion.listar(db, _org(db, current_user))
    return {"items": items, "total": len(items)}


@router.post("/access-reviews", summary="Abrir una campaña de recertificación")
def create_access_review(request: Request, payload: CampanaIn, db: Session = Depends(get_db),
                         current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    return adm.abrir_campana(db, _org(db, current_user), current_user, payload.name, payload.due_at,
                             Origen.de(request))


@router.get("/access-reviews/mine", summary="Accesos que me toca revisar (campañas abiertas)")
def my_access_reviews(db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("seguridad.recertificar"))):
    return adm.mis_revisiones(db, _org(db, current_user), current_user)


@router.get("/access-reviews/{campaign_id}/items", summary="Elementos de una campaña")
def access_review_items(campaign_id: str, db: Session = Depends(get_db),
                        current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.services.seguridad_de_cuentas import recertificacion
    items = recertificacion.elementos(db, _org(db, current_user), campaign_id)
    return {"items": items, "total": len(items)}


class DecisionDeAccesoIn(BaseModel):
    decision: str = Field(..., max_length=20)
    comment: str = Field(..., min_length=1, max_length=1000)


@router.post("/access-reviews/{campaign_id}/items/{item_id}/decide", summary="Decidir sobre un acceso (con evidencia)")
def decide_access_review_item(campaign_id: str, item_id: str, request: Request, payload: DecisionDeAccesoIn,
                              db: Session = Depends(get_db),
                              current_user: User = Depends(requiere_capacidad("seguridad.recertificar"))):
    return adm.decidir_elemento(db, _org(db, current_user), current_user, campaign_id, item_id, payload.decision,
                                payload.comment, Origen.de(request))


class CierreIn(BaseModel):
    apply_revocations: bool = False


@router.post("/access-reviews/{campaign_id}/close", summary="Cerrar una campaña (y aplicar las revocaciones)")
def close_access_review(campaign_id: str, request: Request, payload: CierreIn = Body(default_factory=CierreIn),
                        db: Session = Depends(get_db),
                        current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    return adm.cerrar_campana(db, _org(db, current_user), current_user, campaign_id, payload.apply_revocations,
                              Origen.de(request))


@router.get("/access-reviews/{campaign_id}/export", summary="Exportar la campaña con sus evidencias (CSV o JSON)")
def export_access_review(campaign_id: str, request: Request, format: str = Query("csv", pattern="^(csv|json)$"),
                         db: Session = Depends(get_db),
                         current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    contenido, tipo = adm.exportar_campana(db, _org(db, current_user), current_user, campaign_id, format,
                                           Origen.de(request))
    nombre = f"access-review-{campaign_id[:8]}.{format}"
    return Response(contenido, media_type=tipo, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


# ── Lo mío: dispositivos de confianza ──────────────────────────────────────

@router.get("/me/devices", summary="Mis dispositivos de confianza (sin reto MFA)")
def my_devices(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.services.seguridad_de_cuentas import mfa
    items = mfa.dispositivos(db, current_user.id)
    return {"items": items, "total": len(items)}


@router.delete("/me/devices/{device_id}", summary="Olvidar uno de mis dispositivos de confianza")
def forget_my_device(device_id: str, request: Request, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    _mfa.revocar_dispositivo(db, current_user.id, device_id)   # solo los del usuario de la sesión
    return adm.olvido_de_dispositivo_auditado(db, current_user, device_id, Origen.de(request))
