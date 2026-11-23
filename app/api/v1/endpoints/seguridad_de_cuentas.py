"""Seguridad de cuentas: política, usuarios, sesiones, aprobaciones y recertificación.

23-11-2026 (docs/seguridad/politicas_de_cuenta.md). Todo por empresa (la activa
de la sesión), con `seguridad.administrar` salvo la recertificación del
responsable (`seguridad.recertificar`) y los dispositivos propios. Cada acción
queda en `audit_log` con actor, IP, agente y empresa.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error_http
from app.core.deps import get_current_user, requiere_capacidad
from app.db.session import get_db
from app.models.user import User
from app.services.seguridad_de_cuentas.auditoria import Origen, auditar

router = APIRouter()


def _org(db: Session, user: User) -> str:
    org = (db.info or {}).get("organization_id") or user.organization_id
    if not org:
        raise error_http(400, "empresa_requerida")
    return org


def _miembro(db: Session, org: str, user_id: str, actor: User) -> User:
    from app.db.session import _miembros_de, sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        u = db.query(User).filter(User.id == user_id, _miembros_de(User, org)).first()
    if u is None or (u.is_superadmin and not actor.is_superadmin):
        raise error_http(404, "no_encontrado", que="usuario")
    return u


# ── Política ────────────────────────────────────────────────────────────────

class CambioDePoliticaIn(BaseModel):
    changes: dict = Field(default_factory=dict, description="Campos de la política que cambian")
    reason: Optional[str] = Field(default=None, max_length=500)


@router.get("/policy", summary="Política de cuenta de la empresa, con los valores recomendados")
def get_policy(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.services.seguridad_de_cuentas import politica, separacion
    org = _org(db, current_user)
    salida = politica.describir(db, org)
    salida["pending_requests"] = sum(1 for r in separacion.listar(db, org) if r["status"] == "pending")
    from app.core.config import settings
    salida["platform"] = {"superadmin_bypass_enabled": bool(settings.ENABLE_SUPERADMIN_BYPASS),
                          "geoip_enabled": bool(getattr(settings, "GEOIP_LOOKUP_ENABLED", False)),
                          "environment": settings.ENVIRONMENT}
    db.commit()
    return salida


def _aplicar_politica(db: Session, org: str, actor: User, cambios: dict, origen: Origen, solicitud=None) -> dict:
    from app.services.seguridad_de_cuentas import alertas, politica
    actual = politica.leer(db, org)
    antes = {k: getattr(actual, k) for k in cambios}
    politica.escribir(db, org, cambios, actor, origen.ip)
    auditar(db, actor, "SECURITY_POLICY_CHANGED", org, org_id=org, origen=origen, recurso="security_policy",
            antes=antes, despues=cambios, datos={"change_request_id": solicitud} if solicitud else None)
    alertas.a_los_admins(db, org, "seguridad.alerta.politica", actor=actor.email or actor.full_name,
                         claves=", ".join(sorted(cambios)))
    db.commit()
    return {"applied": True, "changed": sorted(cambios)}


@router.put("/policy", summary="Cambiar la política de cuenta (con segundo administrador si se exige)")
def put_policy(request: Request, payload: CambioDePoliticaIn, db: Session = Depends(get_db),
               current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.services.seguridad_de_cuentas import acceso, politica, separacion
    org = _org(db, current_user)
    actual = politica.leer(db, org)
    cambios = politica.validar(payload.changes, actual)
    if not cambios:
        return {"applied": False, "changed": []}
    origen = Origen.de(request)
    # Que el administrador no se cierre la puerta: su IP tiene que seguir dentro.
    futura = politica.Politica(**{**actual.a_dict(), **cambios})
    if "ACCESS_IP_ALLOWLIST" in cambios and not current_user.is_superadmin and not acceso.ip_permitida(origen.ip, futura):
        raise error_http(409, "ip_fuera_de_la_lista", ip=origen.ip or "?")
    if separacion.exige_segundo(db, org) and not current_user.is_superadmin:
        s = separacion.pedir(db, org, current_user, "policy", cambios, motivo=payload.reason)
        auditar(db, current_user, "SECURITY_CHANGE_REQUESTED", s.id, org_id=org, origen=origen,
                recurso="security_change_requests", despues=cambios, datos={"kind": "policy"})
        db.commit()
        return {"applied": False, "pending_request_id": s.id, "changed": sorted(cambios)}
    return _aplicar_politica(db, org, current_user, cambios, origen)


# ── Usuarios ────────────────────────────────────────────────────────────────

@router.get("/users", summary="Estado de seguridad de los usuarios de la empresa")
def list_users(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from sqlalchemy import func
    from app.db.session import _miembros_de, sin_filtro_de_tenant
    from app.models.sessions import UserSession
    from app.services.seguridad_de_cuentas import bloqueo, contrasenas, mfa
    from app.services.seguridad_de_cuentas.politica import leer
    org = _org(db, current_user)
    p = leer(db, org)
    ahora = datetime.now(timezone.utc)
    with sin_filtro_de_tenant(db):
        usuarios = db.query(User).filter(_miembros_de(User, org), User.is_superadmin.isnot(True)).order_by(User.full_name).all()
        sesiones = dict(db.query(UserSession.user_id, func.count(UserSession.id)).filter(
            UserSession.user_id.in_([u.id for u in usuarios] or [""]), UserSession.revoked_at.is_(None),
            UserSession.expires_at > ahora).group_by(UserSession.user_id).all())
    items = []
    for u in usuarios:
        e = contrasenas.estado(u, p) if u.hashed_password else {}
        m = mfa.estado(db, u, org, p)
        f = mfa.factores(db, u, p)
        items.append({
            "id": u.id, "full_name": u.full_name, "email": u.email, "role": getattr(u.role, "value", u.role),
            "is_active": bool(u.is_active), "sso": bool(u.sso_provider), "last_login": u.last_login,
            "password_changed_at": u.password_changed_at, "password_expired": e.get("password_expired", False),
            "password_must_change": bool(u.password_must_change), "password_temporary": bool(u.password_temporary_until),
            "locked_seconds": bloqueo.segundos_bloqueado(u), "mfa_totp": f["totp"], "mfa_passkey": f["webauthn"],
            "mfa_required": m["mfa_required"], "mfa_required_by": m["mfa_required_by"],
            "mfa_enrollment_required": m["mfa_enrollment_required"], "mfa_grace_until": m["mfa_grace_until"],
            "active_sessions": sesiones.get(u.id, 0),
        })
    return {"items": items, "total": len(items)}


@router.post("/users/{user_id}/unlock", summary="Desbloquear una cuenta bloqueada por intentos")
def unlock_user(user_id: str, request: Request, db: Session = Depends(get_db),
                current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.services.seguridad_de_cuentas import bloqueo
    org = _org(db, current_user)
    u = _miembro(db, org, user_id, current_user)
    antes = u.locked_until
    bloqueo.desbloquear(db, u)
    auditar(db, current_user, "ACCOUNT_UNLOCKED", u, org_id=org, origen=Origen.de(request),
            antes={"locked_until": antes})
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/force-password-change", summary="Obligar a un usuario a cambiar la contraseña al entrar")
def force_password_change(user_id: str, request: Request, db: Session = Depends(get_db),
                          current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.services.seguridad_de_cuentas import alertas
    org = _org(db, current_user)
    u = _miembro(db, org, user_id, current_user)
    if not u.hashed_password:
        raise error_http(409, "cuenta_sso_sin_contrasena")
    u.password_must_change = True
    auditar(db, current_user, "PASSWORD_CHANGE_FORCED", u, org_id=org, origen=Origen.de(request))
    alertas.al_usuario(db, u.id, "seguridad.aviso.cambio_forzado")
    db.commit()
    return {"ok": True}


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
    from app.services.seguridad_de_cuentas import alertas, contrasenas, sesiones
    from app.services.seguridad_de_cuentas.restablecimiento import enviar_enlace_al_operador
    org = _org(db, current_user)
    u = _miembro(db, org, user_id, current_user)
    if u.id == current_user.id:
        raise error_http(403, "separacion_de_funciones_misma_persona")
    if not u.hashed_password:
        raise error_http(409, "cuenta_sso_sin_contrasena")
    contrasenas.forzar_cambio(db, u)
    revocadas = sesiones.revocar_todas(db, u.id, "password_reset_forced")
    enviado = bool(payload.send_link and u.is_active and enviar_enlace_al_operador(db, u, forzado=True))
    auditar(db, current_user, "PASSWORD_RESET_FORCED", u, org_id=org, origen=Origen.de(request),
            datos={"reason": payload.reason, "link_sent": enviado, "sessions_revoked": revocadas})
    alertas.al_usuario(db, u.id, "seguridad.aviso.cambio_forzado")
    db.commit()
    return {"ok": True, "link_sent": enviado, "sessions_revoked": revocadas}


@router.post("/force-password-change-all", summary="Obligar a todos los usuarios de la empresa a cambiar la contraseña")
def force_password_change_all(request: Request, db: Session = Depends(get_db),
                              current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.db.session import _miembros_de, sin_filtro_de_tenant
    org = _org(db, current_user)
    with sin_filtro_de_tenant(db):
        usuarios = db.query(User).filter(_miembros_de(User, org), User.is_active.is_(True),
                                         User.is_superadmin.isnot(True), User.hashed_password.isnot(None),
                                         User.id != current_user.id).all()
    for u in usuarios:
        u.password_must_change = True
    auditar(db, current_user, "PASSWORD_CHANGE_FORCED_ALL", org, org_id=org, origen=Origen.de(request),
            recurso="security_policy", datos={"users": len(usuarios)})
    db.commit()
    return {"ok": True, "users": len(usuarios)}


class TemporalIn(BaseModel):
    password: Optional[str] = Field(default=None, max_length=1024, description="Vacío: se genera una")


@router.post("/users/{user_id}/temporary-password", summary="Poner una contraseña temporal (caduca y obliga a cambiarla)")
def set_temporary_password(user_id: str, request: Request, payload: TemporalIn = Body(default_factory=TemporalIn),
                           db: Session = Depends(get_db),
                           current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.core.security import get_password_hash
    from app.services.seguridad_de_cuentas import bloqueo, contrasenas, sesiones
    org = _org(db, current_user)
    u = _miembro(db, org, user_id, current_user)
    if u.id == current_user.id:
        raise error_http(403, "separacion_de_funciones_misma_persona")
    generada = payload.password is None
    clave = payload.password or (secrets.token_urlsafe(12) + "aA1!")
    p = contrasenas.validar_nueva(db, u, clave, por_admin=True)
    contrasenas.registrar_cambio(db, u, get_password_hash(clave), temporal=True, politica=p)
    bloqueo.desbloquear(db, u)
    revocadas = sesiones.revocar_todas(db, u.id, "temporary_password")
    auditar(db, current_user, "PASSWORD_TEMPORARY_SET", u, org_id=org, origen=Origen.de(request),
            datos={"generated": generada, "expires_at": u.password_temporary_until, "sessions_revoked": revocadas})
    db.commit()
    return {"ok": True, "password": clave if generada else None, "expires_at": u.password_temporary_until}


class MotivoIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


def _aplicar_reset_mfa(db: Session, org: str, actor: User, u: User, origen: Origen, motivo: Optional[str],
                       solicitud: Optional[str] = None) -> dict:
    from app.services.seguridad_de_cuentas import alertas, mfa
    hecho = mfa.restablecer(db, u)
    auditar(db, actor, "MFA_RESET_BY_ADMIN", u, org_id=org, origen=origen,
            datos={**hecho, "reason": motivo, "change_request_id": solicitud})
    alertas.a_los_admins(db, org, "seguridad.alerta.mfa_restablecido", actor=actor.email or actor.full_name,
                         usuario=u.email or u.username)
    db.commit()
    return {"applied": True, **hecho}


@router.post("/users/{user_id}/reset-mfa", summary="Restablecer el segundo factor de un usuario")
def reset_mfa(user_id: str, request: Request, payload: MotivoIn = Body(default_factory=MotivoIn),
              db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.services.seguridad_de_cuentas import separacion
    org = _org(db, current_user)
    u = _miembro(db, org, user_id, current_user)
    origen = Origen.de(request)
    if separacion.exige_segundo(db, org) and not current_user.is_superadmin:
        if u.id == current_user.id:
            raise error_http(403, "separacion_de_funciones_misma_persona")
        s = separacion.pedir(db, org, current_user, "mfa_reset", {"user_id": u.id}, objetivo_id=u.id,
                             motivo=payload.reason)
        auditar(db, current_user, "SECURITY_CHANGE_REQUESTED", s.id, org_id=org, origen=origen,
                recurso="security_change_requests", datos={"kind": "mfa_reset", "user_id": u.id})
        db.commit()
        return {"applied": False, "pending_request_id": s.id}
    return _aplicar_reset_mfa(db, org, current_user, u, origen, payload.reason)


@router.post("/users/{user_id}/revoke-sessions", summary="Cerrar todas las sesiones de un usuario")
def revoke_user_sessions(user_id: str, request: Request, db: Session = Depends(get_db),
                         current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.services.seguridad_de_cuentas import mfa, sesiones
    org = _org(db, current_user)
    u = _miembro(db, org, user_id, current_user)
    n = sesiones.revocar_todas(db, u.id, "revoked_by_admin")
    d = mfa.revocar_dispositivos(db, u.id, "revoked_by_admin")
    auditar(db, current_user, "SESSIONS_REVOKED_BY_ADMIN", u, org_id=org, origen=Origen.de(request),
            datos={"sessions": n, "trusted_devices": d})
    db.commit()
    return {"ok": True, "revoked": n}


# ── Sesiones de la empresa ─────────────────────────────────────────────────

@router.get("/sessions", summary="Sesiones activas de la empresa")
def list_sessions(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.services.seguridad_de_cuentas import sesiones
    items = sesiones.de_la_empresa(db, _org(db, current_user))
    return {"items": items, "total": len(items)}


@router.delete("/sessions/{session_id}", summary="Cerrar una sesión de la empresa")
def revoke_session(session_id: str, request: Request, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.services.seguridad_de_cuentas import sesiones
    org = _org(db, current_user)
    s, u = sesiones.revocar_una_de_la_empresa(db, org, session_id)
    auditar(db, current_user, "SESSION_REVOKED_BY_ADMIN", u, org_id=org, origen=Origen.de(request),
            datos={"session_id": s.id, "ip": s.ip_address})
    db.commit()
    return {"ok": True}


# ── Solicitudes con segundo administrador ──────────────────────────────────

@router.get("/change-requests", summary="Cambios de seguridad pendientes de un segundo administrador")
def list_change_requests(db: Session = Depends(get_db),
                         current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.services.seguridad_de_cuentas import separacion
    items = separacion.listar(db, _org(db, current_user))
    db.commit()
    return {"items": items, "total": len(items)}


class DecisionIn(BaseModel):
    comment: Optional[str] = Field(default=None, max_length=500)


@router.post("/change-requests/{request_id}/approve", summary="Aprobar y aplicar un cambio de seguridad (otro administrador)")
def approve_change_request(request_id: str, request: Request, payload: DecisionIn = Body(default_factory=DecisionIn),
                           db: Session = Depends(get_db),
                           current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.services.seguridad_de_cuentas import politica, separacion
    org = _org(db, current_user)
    s, datos = separacion.decidir(db, org, request_id, current_user, True, payload.comment)
    origen = Origen.de(request)
    auditar(db, current_user, "SECURITY_CHANGE_APPROVED", s.id, org_id=org, origen=origen,
            recurso="security_change_requests", datos={"kind": s.kind, "requested_by": s.requested_by})
    if s.kind == "policy":
        cambios = politica.validar(datos, politica.leer(db, org))
        return _aplicar_politica(db, org, current_user, cambios, origen, solicitud=s.id)
    u = _miembro(db, org, datos.get("user_id") or s.target_user_id, current_user)
    return _aplicar_reset_mfa(db, org, current_user, u, origen, s.reason, solicitud=s.id)


@router.post("/change-requests/{request_id}/reject", summary="Rechazar un cambio de seguridad")
def reject_change_request(request_id: str, request: Request, payload: DecisionIn = Body(default_factory=DecisionIn),
                          db: Session = Depends(get_db),
                          current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.services.seguridad_de_cuentas import separacion
    org = _org(db, current_user)
    s, _ = separacion.decidir(db, org, request_id, current_user, False, payload.comment)
    auditar(db, current_user, "SECURITY_CHANGE_REJECTED", s.id, org_id=org, origen=Origen.de(request),
            recurso="security_change_requests", datos={"kind": s.kind, "comment": payload.comment})
    db.commit()
    return {"ok": True}


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
    from app.services.seguridad_de_cuentas import alertas, recertificacion
    org = _org(db, current_user)
    c, n = recertificacion.abrir(db, org, current_user, payload.name, payload.due_at)
    auditar(db, current_user, "ACCESS_REVIEW_OPENED", c.id, org_id=org, origen=Origen.de(request),
            recurso="access_review_campaigns", despues={"name": c.name, "items": n})
    from app.models.seguridad_de_cuentas import AccessReviewItem
    from sqlalchemy import func
    for revisor, cuantos in db.query(AccessReviewItem.reviewer_id, func.count(AccessReviewItem.id)).filter(
            AccessReviewItem.campaign_id == c.id).group_by(AccessReviewItem.reviewer_id).all():
        if revisor:
            alertas.al_usuario(db, revisor, "seguridad.aviso.recertificacion", n=cuantos, campana=c.name)
    db.commit()
    return {"id": c.id, "items": n}


@router.get("/access-reviews/mine", summary="Accesos que me toca revisar (campañas abiertas)")
def my_access_reviews(db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("seguridad.recertificar"))):
    from app.models.seguridad_de_cuentas import AccessReviewCampaign
    from app.services.seguridad_de_cuentas import recertificacion
    org = _org(db, current_user)
    abiertas = db.query(AccessReviewCampaign).filter(AccessReviewCampaign.organization_id == org,
                                                     AccessReviewCampaign.status == "open").all()
    return {"items": [{"campaign": {"id": c.id, "name": c.name, "due_at": c.due_at},
                       "items": recertificacion.elementos(db, org, c.id, revisor_id=current_user.id)}
                      for c in abiertas]}


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
    from app.core.capacidades import tiene
    from app.services.seguridad_de_cuentas import recertificacion
    org = _org(db, current_user)
    es_admin = current_user.is_superadmin or tiene(db, current_user, "seguridad.administrar")
    e, antes = recertificacion.decidir(db, org, campaign_id, item_id, current_user, payload.decision,
                                       payload.comment, es_admin)
    auditar(db, current_user, "ACCESS_REVIEW_DECIDED", e.user_id, org_id=org, origen=Origen.de(request),
            recurso="access_review_items", antes={"decision": antes},
            despues={"decision": e.decision, "comment": e.comment}, datos={"campaign_id": campaign_id, "item_id": e.id})
    db.commit()
    return {"ok": True}


class CierreIn(BaseModel):
    apply_revocations: bool = False


@router.post("/access-reviews/{campaign_id}/close", summary="Cerrar una campaña (y aplicar las revocaciones)")
def close_access_review(campaign_id: str, request: Request, payload: CierreIn = Body(default_factory=CierreIn),
                        db: Session = Depends(get_db),
                        current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.services.seguridad_de_cuentas import recertificacion
    org = _org(db, current_user)
    hecho = recertificacion.cerrar(db, org, campaign_id, current_user, payload.apply_revocations)
    auditar(db, current_user, "ACCESS_REVIEW_CLOSED", campaign_id, org_id=org, origen=Origen.de(request),
            recurso="access_review_campaigns", datos=hecho)
    db.commit()
    return hecho


@router.get("/access-reviews/{campaign_id}/export", summary="Exportar la campaña con sus evidencias (CSV o JSON)")
def export_access_review(campaign_id: str, request: Request, format: str = Query("csv", pattern="^(csv|json)$"),
                         db: Session = Depends(get_db),
                         current_user: User = Depends(requiere_capacidad("seguridad.administrar"))):
    from app.services.seguridad_de_cuentas import recertificacion
    org = _org(db, current_user)
    contenido, tipo = recertificacion.exportar(db, org, campaign_id, format)
    auditar(db, current_user, "ACCESS_REVIEW_EXPORTED", campaign_id, org_id=org, origen=Origen.de(request),
            recurso="access_review_campaigns", datos={"format": format})
    db.commit()
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
    from app.services.seguridad_de_cuentas import mfa
    mfa.revocar_dispositivo(db, current_user.id, device_id)
    auditar(db, current_user, "TRUSTED_DEVICE_REVOKED", current_user, origen=Origen.de(request),
            datos={"device_id": device_id})
    db.commit()
    return {"ok": True}
