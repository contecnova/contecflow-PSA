"""Administración de la seguridad de cuentas: la unidad de trabajo de cada acción.

23-11-2026 (prueba global). Lo que hacía `app/api/v1/endpoints/seguridad_de_cuentas.py`
por su cuenta —consultar usuarios, sesiones y campañas y confirmar la
transacción— vive aquí: la capa API no accede a la base ni hace `commit`
(tests/test_capa_api_sin_acceso_a_base.py, tests/test_sin_commits_en_la_api.py).
Cada función valida, escribe, audita (`audit_log` con actor, IP, agente y
empresa) y confirma. Ver docs/seguridad/politicas_de_cuenta.md.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.user import User
from app.services.seguridad_de_cuentas.auditoria import Origen, auditar


def miembro(db: Session, org: str, user_id: str, actor: User) -> User:
    """El usuario `user_id` de la empresa `org` (un superadmin solo lo ve otro superadmin)."""
    from app.db.session import _miembros_de, sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        u = db.query(User).filter(User.id == user_id, _miembros_de(User, org)).first()
    if u is None or (u.is_superadmin and not actor.is_superadmin):
        raise error(404, "no_encontrado", que="usuario")
    return u


# ── Política ────────────────────────────────────────────────────────────────

def describir_politica(db: Session, org: str) -> dict:
    from app.core.config import settings
    from app.services.seguridad_de_cuentas import politica, separacion
    salida = politica.describir(db, org)
    salida["pending_requests"] = sum(1 for r in separacion.listar(db, org) if r["status"] == "pending")
    salida["platform"] = {"superadmin_bypass_enabled": bool(settings.ENABLE_SUPERADMIN_BYPASS),
                          "geoip_enabled": bool(getattr(settings, "GEOIP_LOOKUP_ENABLED", False)),
                          "environment": settings.ENVIRONMENT}
    db.commit()
    return salida


def aplicar_politica(db: Session, org: str, actor: User, cambios: dict, origen: Origen,
                     solicitud: Optional[str] = None) -> dict:
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


def cambiar_politica(db: Session, org: str, actor: User, cambios_pedidos: dict, motivo: Optional[str],
                     origen: Origen) -> dict:
    """Valida y aplica, o deja la solicitud al segundo administrador si se exige."""
    from app.services.seguridad_de_cuentas import acceso, politica, separacion
    actual = politica.leer(db, org)
    cambios = politica.validar(cambios_pedidos, actual)
    if not cambios:
        return {"applied": False, "changed": []}
    # Que el administrador no se cierre la puerta: su IP tiene que seguir dentro.
    futura = politica.PoliticaDeCuenta(**{**actual.a_dict(), **cambios})
    if "ACCESS_IP_ALLOWLIST" in cambios and not actor.is_superadmin and not acceso.ip_permitida(origen.ip, futura):
        raise error(409, "ip_fuera_de_la_lista", ip=origen.ip or "?")
    if separacion.exige_segundo(db, org) and not actor.is_superadmin:
        s = separacion.pedir(db, org, actor, "policy", cambios, motivo=motivo)
        auditar(db, actor, "SECURITY_CHANGE_REQUESTED", s.id, org_id=org, origen=origen,
                recurso="security_change_requests", despues=cambios, datos={"kind": "policy"})
        db.commit()
        return {"applied": False, "pending_request_id": s.id, "changed": sorted(cambios)}
    return aplicar_politica(db, org, actor, cambios, origen)


# ── Usuarios ────────────────────────────────────────────────────────────────

def estado_de_usuarios(db: Session, org: str) -> dict:
    from sqlalchemy import func
    from app.db.session import _miembros_de, sin_filtro_de_tenant
    from app.models.sessions import UserSession
    from app.services.seguridad_de_cuentas import bloqueo, contrasenas, mfa
    from app.services.seguridad_de_cuentas.politica import leer
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


def desbloquear(db: Session, org: str, actor: User, user_id: str, origen: Origen) -> dict:
    from app.services.seguridad_de_cuentas import bloqueo
    u = miembro(db, org, user_id, actor)
    antes = u.locked_until
    bloqueo.desbloquear(db, u)
    auditar(db, actor, "ACCOUNT_UNLOCKED", u, org_id=org, origen=origen, antes={"locked_until": antes})
    db.commit()
    return {"ok": True}


def forzar_cambio(db: Session, org: str, actor: User, user_id: str, origen: Origen) -> dict:
    from app.services.seguridad_de_cuentas import alertas
    u = miembro(db, org, user_id, actor)
    if not u.hashed_password:
        raise error(409, "cuenta_sso_sin_contrasena")
    u.password_must_change = True
    auditar(db, actor, "PASSWORD_CHANGE_FORCED", u, org_id=org, origen=origen)
    alertas.al_usuario(db, u.id, "seguridad.aviso.cambio_forzado")
    db.commit()
    return {"ok": True}


def forzar_restablecimiento(db: Session, org: str, actor: User, user_id: str, origen: Origen,
                            motivo: str, enviar_enlace: bool) -> dict:
    """Cambio obligatorio en el próximo acceso, revoca TODAS sus sesiones y, si se
    pide, le manda el enlace de un solo uso (`PASSWORD_RESET_FORCED`)."""
    from app.services.seguridad_de_cuentas import alertas, contrasenas, sesiones
    from app.services.seguridad_de_cuentas.restablecimiento import enviar_enlace_al_operador
    u = miembro(db, org, user_id, actor)
    if u.id == actor.id:
        raise error(403, "separacion_de_funciones_misma_persona")
    if not u.hashed_password:
        raise error(409, "cuenta_sso_sin_contrasena")
    contrasenas.forzar_cambio(db, u)
    revocadas = sesiones.revocar_todas(db, u.id, "password_reset_forced")
    enviado = bool(enviar_enlace and u.is_active and enviar_enlace_al_operador(db, u, forzado=True))
    auditar(db, actor, "PASSWORD_RESET_FORCED", u, org_id=org, origen=origen,
            datos={"reason": motivo, "link_sent": enviado, "sessions_revoked": revocadas})
    alertas.al_usuario(db, u.id, "seguridad.aviso.cambio_forzado")
    db.commit()
    return {"ok": True, "link_sent": enviado, "sessions_revoked": revocadas}


def forzar_cambio_a_todos(db: Session, org: str, actor: User, origen: Origen) -> dict:
    from app.db.session import _miembros_de, sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        usuarios = db.query(User).filter(_miembros_de(User, org), User.is_active.is_(True),
                                         User.is_superadmin.isnot(True), User.hashed_password.isnot(None),
                                         User.id != actor.id).all()
    for u in usuarios:
        u.password_must_change = True
    auditar(db, actor, "PASSWORD_CHANGE_FORCED_ALL", org, org_id=org, origen=origen,
            recurso="security_policy", datos={"users": len(usuarios)})
    db.commit()
    return {"ok": True, "users": len(usuarios)}


def poner_temporal(db: Session, org: str, actor: User, user_id: str, origen: Origen,
                   clave_pedida: Optional[str]) -> dict:
    from app.core.security import get_password_hash
    from app.services.seguridad_de_cuentas import bloqueo, contrasenas, sesiones
    u = miembro(db, org, user_id, actor)
    if u.id == actor.id:
        raise error(403, "separacion_de_funciones_misma_persona")
    generada = clave_pedida is None
    clave = clave_pedida or (secrets.token_urlsafe(12) + "aA1!")
    p = contrasenas.validar_nueva(db, u, clave, por_admin=True)
    contrasenas.registrar_cambio(db, u, get_password_hash(clave), temporal=True, politica=p)
    bloqueo.desbloquear(db, u)
    revocadas = sesiones.revocar_todas(db, u.id, "temporary_password")
    auditar(db, actor, "PASSWORD_TEMPORARY_SET", u, org_id=org, origen=origen,
            datos={"generated": generada, "expires_at": u.password_temporary_until, "sessions_revoked": revocadas})
    db.commit()
    return {"ok": True, "password": clave if generada else None, "expires_at": u.password_temporary_until}


def aplicar_reset_mfa(db: Session, org: str, actor: User, u: User, origen: Origen, motivo: Optional[str],
                      solicitud: Optional[str] = None) -> dict:
    from app.services.seguridad_de_cuentas import alertas, mfa
    hecho = mfa.restablecer(db, u)
    auditar(db, actor, "MFA_RESET_BY_ADMIN", u, org_id=org, origen=origen,
            datos={**hecho, "reason": motivo, "change_request_id": solicitud})
    alertas.a_los_admins(db, org, "seguridad.alerta.mfa_restablecido", actor=actor.email or actor.full_name,
                         usuario=u.email or u.username)
    db.commit()
    return {"applied": True, **hecho}


def restablecer_mfa(db: Session, org: str, actor: User, user_id: str, origen: Origen,
                    motivo: Optional[str]) -> dict:
    from app.services.seguridad_de_cuentas import separacion
    u = miembro(db, org, user_id, actor)
    if separacion.exige_segundo(db, org) and not actor.is_superadmin:
        if u.id == actor.id:
            raise error(403, "separacion_de_funciones_misma_persona")
        s = separacion.pedir(db, org, actor, "mfa_reset", {"user_id": u.id}, objetivo_id=u.id, motivo=motivo)
        auditar(db, actor, "SECURITY_CHANGE_REQUESTED", s.id, org_id=org, origen=origen,
                recurso="security_change_requests", datos={"kind": "mfa_reset", "user_id": u.id})
        db.commit()
        return {"applied": False, "pending_request_id": s.id}
    return aplicar_reset_mfa(db, org, actor, u, origen, motivo)


def revocar_sesiones_de(db: Session, org: str, actor: User, user_id: str, origen: Origen) -> dict:
    from app.services.seguridad_de_cuentas import mfa, sesiones
    u = miembro(db, org, user_id, actor)
    n = sesiones.revocar_todas(db, u.id, "revoked_by_admin")
    d = mfa.revocar_dispositivos(db, u.id, "revoked_by_admin")
    auditar(db, actor, "SESSIONS_REVOKED_BY_ADMIN", u, org_id=org, origen=origen,
            datos={"sessions": n, "trusted_devices": d})
    db.commit()
    return {"ok": True, "revoked": n}


def revocar_sesion(db: Session, org: str, actor: User, session_id: str, origen: Origen) -> dict:
    from app.services.seguridad_de_cuentas import sesiones
    s, u = sesiones.revocar_una_de_la_empresa(db, org, session_id)
    auditar(db, actor, "SESSION_REVOKED_BY_ADMIN", u, org_id=org, origen=origen,
            datos={"session_id": s.id, "ip": s.ip_address})
    db.commit()
    return {"ok": True}


# ── Solicitudes con segundo administrador ──────────────────────────────────

def listar_solicitudes(db: Session, org: str) -> dict:
    from app.services.seguridad_de_cuentas import separacion
    items = separacion.listar(db, org)
    db.commit()
    return {"items": items, "total": len(items)}


def aprobar_solicitud(db: Session, org: str, actor: User, request_id: str, comentario: Optional[str],
                      origen: Origen) -> dict:
    from app.services.seguridad_de_cuentas import politica, separacion
    s, datos = separacion.decidir(db, org, request_id, actor, True, comentario)
    auditar(db, actor, "SECURITY_CHANGE_APPROVED", s.id, org_id=org, origen=origen,
            recurso="security_change_requests", datos={"kind": s.kind, "requested_by": s.requested_by})
    if s.kind == "policy":
        cambios = politica.validar(datos, politica.leer(db, org))
        return aplicar_politica(db, org, actor, cambios, origen, solicitud=s.id)
    u = miembro(db, org, datos.get("user_id") or s.target_user_id, actor)
    return aplicar_reset_mfa(db, org, actor, u, origen, s.reason, solicitud=s.id)


def rechazar_solicitud(db: Session, org: str, actor: User, request_id: str, comentario: Optional[str],
                       origen: Origen) -> dict:
    from app.services.seguridad_de_cuentas import separacion
    s, _ = separacion.decidir(db, org, request_id, actor, False, comentario)
    auditar(db, actor, "SECURITY_CHANGE_REJECTED", s.id, org_id=org, origen=origen,
            recurso="security_change_requests", datos={"kind": s.kind, "comment": comentario})
    db.commit()
    return {"ok": True}


# ── Recertificación de accesos ─────────────────────────────────────────────

def abrir_campana(db: Session, org: str, actor: User, nombre: str, vence: Optional[datetime],
                  origen: Origen) -> dict:
    from sqlalchemy import func
    from app.models.seguridad_de_cuentas import AccessReviewItem
    from app.services.seguridad_de_cuentas import alertas, recertificacion
    c, n = recertificacion.abrir(db, org, actor, nombre, vence)
    auditar(db, actor, "ACCESS_REVIEW_OPENED", c.id, org_id=org, origen=origen,
            recurso="access_review_campaigns", despues={"name": c.name, "items": n})
    for revisor, cuantos in db.query(AccessReviewItem.reviewer_id, func.count(AccessReviewItem.id)).filter(
            AccessReviewItem.campaign_id == c.id).group_by(AccessReviewItem.reviewer_id).all():
        if revisor:
            alertas.al_usuario(db, revisor, "seguridad.aviso.recertificacion", n=cuantos, campana=c.name)
    db.commit()
    return {"id": c.id, "items": n}


def mis_revisiones(db: Session, org: str, revisor: User) -> dict:
    from app.models.seguridad_de_cuentas import AccessReviewCampaign
    from app.services.seguridad_de_cuentas import recertificacion
    abiertas = db.query(AccessReviewCampaign).filter(AccessReviewCampaign.organization_id == org,
                                                     AccessReviewCampaign.status == "open").all()
    return {"items": [{"campaign": {"id": c.id, "name": c.name, "due_at": c.due_at},
                       "items": recertificacion.elementos(db, org, c.id, revisor_id=revisor.id)}
                      for c in abiertas]}


def decidir_elemento(db: Session, org: str, actor: User, campaign_id: str, item_id: str, decision: str,
                     comentario: str, origen: Origen) -> dict:
    from app.core.capacidades import tiene
    from app.services.seguridad_de_cuentas import recertificacion
    es_admin = actor.is_superadmin or tiene(db, actor, "seguridad.administrar")
    e, antes = recertificacion.decidir(db, org, campaign_id, item_id, actor, decision, comentario, es_admin)
    auditar(db, actor, "ACCESS_REVIEW_DECIDED", e.user_id, org_id=org, origen=origen,
            recurso="access_review_items", antes={"decision": antes},
            despues={"decision": e.decision, "comment": e.comment}, datos={"campaign_id": campaign_id, "item_id": e.id})
    db.commit()
    return {"ok": True}


def cerrar_campana(db: Session, org: str, actor: User, campaign_id: str, aplicar_revocaciones: bool,
                   origen: Origen) -> dict:
    from app.services.seguridad_de_cuentas import recertificacion
    hecho = recertificacion.cerrar(db, org, campaign_id, actor, aplicar_revocaciones)
    auditar(db, actor, "ACCESS_REVIEW_CLOSED", campaign_id, org_id=org, origen=origen,
            recurso="access_review_campaigns", datos=hecho)
    db.commit()
    return hecho


def exportar_campana(db: Session, org: str, actor: User, campaign_id: str, formato: str,
                     origen: Origen) -> tuple:
    """(contenido, tipo MIME); la exportación queda auditada."""
    from app.services.seguridad_de_cuentas import recertificacion
    contenido, tipo = recertificacion.exportar(db, org, campaign_id, formato)
    auditar(db, actor, "ACCESS_REVIEW_EXPORTED", campaign_id, org_id=org, origen=origen,
            recurso="access_review_campaigns", datos={"format": formato})
    db.commit()
    return contenido, tipo


# ── Lo mío: dispositivos de confianza ──────────────────────────────────────

def olvido_de_dispositivo_auditado(db: Session, usuario: User, device_id: str, origen: Origen) -> dict:
    """Audita y confirma el olvido de un dispositivo de confianza propio (lo revoca
    la ruta con `mfa.revocar_dispositivo(db, current_user.id, ...)`)."""
    auditar(db, usuario, "TRUSTED_DEVICE_REVOKED", usuario, origen=origen, datos={"device_id": device_id})
    db.commit()
    return {"ok": True}
