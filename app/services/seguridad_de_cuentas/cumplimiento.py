"""Controles de seguridad de cuentas para el informe de cumplimiento (medidos en vivo)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def controles(db, org: str, _control) -> list[dict]:
    from app.core.config import settings
    from app.db import auditoria_inmutable
    from app.db.session import _miembros_de
    from app.models.seguridad_de_cuentas import AccessReviewCampaign
    from app.models.sessions import UserSession  # noqa: F401
    from app.models.user import User
    from app.services.seguridad_de_cuentas import contrasenas, mfa
    from app.services.seguridad_de_cuentas.politica import CAPACIDADES_SENSIBLES, leer

    ahora = datetime.now(timezone.utc)
    p = leer(db, org)
    activos = db.query(User).filter(_miembros_de(User, org), User.is_active.is_(True)).all()
    salida: list[dict] = []

    # MFA por política: quién lo necesita y lo tiene.
    exigidos = [u for u in activos if mfa.motivo_de_exigencia(db, u, org, p)]
    sin_factor = [u.email for u in exigidos if not mfa.factores(db, u, p)["alguno"]]
    salida.append(_control("mfa_policy", "pass" if not sin_factor else "attention",
                           {"required_users": len(exigidos), "without_factor": len(sin_factor),
                            "without_factor_sample": sin_factor[:20], "org_wide": p.require_mfa,
                            "roles": sorted(p.roles_con_mfa()), "sensitive_capabilities": p.MFA_REQUIRED_FOR_SENSITIVE,
                            "methods": sorted(p.metodos()), "grace_days": p.MFA_GRACE_DAYS},
                           "users + webauthn_credentials frente a la política MFA (account_security)",
                           ("ISO27001 A.8.5", "CIS 6.3", "CIS 6.5", "NIST 800-63B AAL2")))

    con_contrasena = [u for u in activos if u.hashed_password and not u.sso_provider]
    caducadas = [u.email for u in con_contrasena if contrasenas.estado(u, p)["password_expired"]]
    forzadas = sum(1 for u in con_contrasena if u.password_must_change)
    temporales_vencidas = sum(1 for u in con_contrasena if contrasenas.temporal_caducada(u))
    salida.append(_control("passwords_expired", "pass" if not caducadas and not temporales_vencidas else "attention",
                           {"with_password": len(con_contrasena), "expired": len(caducadas),
                            "expired_sample": caducadas[:20], "change_forced_pending": forzadas,
                            "temporary_expired": temporales_vencidas, "expiry_days": p.PASSWORD_EXPIRY_DAYS},
                           "users.password_changed_at / password_must_change / password_temporary_until",
                           ("ISO27001 A.5.17",)))

    fuerte = (p.PASSWORD_BLOCK_COMMON and p.PASSWORD_BLOCK_PERSONAL and p.PASSWORD_MAX_LENGTH >= 64
              and p.LOGIN_MAX_ATTEMPTS <= 10)
    salida.append(_control("password_policy_strength", "pass" if fuerte else "attention",
                           {"min_length": p.MIN_PASSWORD_LENGTH, "max_length": p.PASSWORD_MAX_LENGTH,
                            "block_common": p.PASSWORD_BLOCK_COMMON, "block_personal": p.PASSWORD_BLOCK_PERSONAL,
                            "history": p.PASSWORD_HISTORY_COUNT, "expiry_days": p.PASSWORD_EXPIRY_DAYS,
                            "lockout_attempts": p.LOGIN_MAX_ATTEMPTS, "lockout_seconds": p.LOGIN_LOCKOUT_SECONDS},
                           "política de contraseñas y bloqueo de la empresa",
                           ("NIST 800-63B §3.1.1.2", "ISO27001 A.5.17", "CIS 5.2")))

    bloqueadas = [u.email for u in activos if u.locked_until and
                  (u.locked_until if u.locked_until.tzinfo else u.locked_until.replace(tzinfo=timezone.utc)) > ahora]
    salida.append(_control("accounts_locked", "info", {"locked_now": len(bloqueadas), "sample": bloqueadas[:20]},
                           "users.locked_until", ("ISO27001 A.8.5",)))

    from app.core.capacidades import capacidades_de
    privilegiados = []
    for u in activos:
        try:
            sens = set(capacidades_de(db, u)) & set(CAPACIDADES_SENSIBLES)
        except Exception:
            sens = set()
        if sens or u.is_superadmin:
            privilegiados.append((u, sens))
    priv_sin_mfa = [u.email for u, _ in privilegiados if not mfa.factores(db, u, p)["alguno"]]
    salida.append(_control("privileged_accounts", "pass" if not priv_sin_mfa else "attention",
                           {"privileged": len(privilegiados), "privileged_pct": round(100 * len(privilegiados) / len(activos), 1) if activos else 0.0,
                            "without_mfa": len(priv_sin_mfa), "without_mfa_sample": priv_sin_mfa[:20],
                            "list": [{"email": u.email, "role": getattr(u.role, "value", u.role),
                                      "capabilities": sorted(s)} for u, s in privilegiados][:200]},
                           "capacidades sensibles efectivas de los usuarios activos",
                           ("ISO27001 A.8.2", "SOC2 CC6.3", "CIS 5.4")))

    salida.append(_control("inactive_accounts_auto_disable",
                           "pass" if p.ACCOUNT_INACTIVE_DISABLE_DAYS > 0 else "attention",
                           {"days": p.ACCOUNT_INACTIVE_DISABLE_DAYS},
                           "ACCOUNT_INACTIVE_DISABLE_DAYS + trabajo diario seguridad-de-cuentas-diario",
                           ("ISO27001 A.5.18", "CIS 5.3")))

    salida.append(_control("session_limits",
                           "pass" if p.idle_timeout_enabled and p.SESSION_MAX_HOURS > 0 else "attention",
                           {"idle_enabled": p.idle_timeout_enabled, "idle_minutes": p.idle_timeout_minutes,
                            "max_hours": p.SESSION_MAX_HOURS, "max_concurrent": p.SESSION_MAX_CONCURRENT,
                            "remember_device_days": p.MFA_REMEMBER_DEVICE_DAYS},
                           "política de sesiones (aplicada en el servidor en cada petición)",
                           ("NIST 800-63B §2.2.3", "ISO27001 A.8.5")))

    salida.append(_control("access_restrictions", "info",
                           {"ip_allowlist": [str(r) for r in p.redes()], "hours": p.ACCESS_HOURS or None,
                            "days": p.ACCESS_DAYS, "blocked_countries": sorted(p.paises_bloqueados()),
                            "geoip_enabled": bool(getattr(settings, "GEOIP_LOOKUP_ENABLED", False)),
                            "superadmin_exempt": True},
                           "ACCESS_* de la empresa", ("ISO27001 A.8.20", "CIS 6.x")))

    ultima = (db.query(AccessReviewCampaign).filter(AccessReviewCampaign.organization_id == org,
                                                    AccessReviewCampaign.status == "closed")
              .order_by(AccessReviewCampaign.closed_at.desc()).first())
    cerrada = ultima.closed_at if ultima else None
    if cerrada is not None and cerrada.tzinfo is None:
        cerrada = cerrada.replace(tzinfo=timezone.utc)
    al_dia = bool(cerrada and (not p.ACCESS_REVIEW_INTERVAL_DAYS
                               or cerrada >= ahora - timedelta(days=p.ACCESS_REVIEW_INTERVAL_DAYS)))
    salida.append(_control("access_review",
                           "info" if not p.ACCESS_REVIEW_INTERVAL_DAYS else ("pass" if al_dia else "attention"),
                           {"last_closed_at": cerrada.isoformat() if cerrada else None,
                            "interval_days": p.ACCESS_REVIEW_INTERVAL_DAYS,
                            "open_campaigns": db.query(AccessReviewCampaign).filter(
                                AccessReviewCampaign.organization_id == org,
                                AccessReviewCampaign.status == "open").count()},
                           "access_review_campaigns cerradas", ("ISO27001 A.5.18", "SOC2 CC6.2")))

    bypass = bool(getattr(settings, "ENABLE_SUPERADMIN_BYPASS", False))
    salida.append(_control("superadmin_bypass", "attention" if bypass else "pass",
                           {"enabled": bypass, "environment": settings.ENVIRONMENT},
                           "ENABLE_SUPERADMIN_BYPASS", ("ISO27001 A.8.2", "ISO27001 A.8.5")))

    inmutable = auditoria_inmutable.instalados(db.connection())
    salida.append(_control("audit_log_immutable", "pass" if inmutable else "attention",
                           {"triggers_installed": inmutable, "dialect": db.connection().dialect.name},
                           "triggers audit_logs_no_update / audit_logs_no_delete (migración 199)",
                           ("ISO27001 A.8.15", "SOC2 CC7.2", "ENS op.exp.10")))
    return salida
