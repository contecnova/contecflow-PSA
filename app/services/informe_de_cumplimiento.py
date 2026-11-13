"""Informe de evidencias de cumplimiento, medido sobre el sistema vivo (revisión 2026-11).

Lo que contecmind y contecintelligence tenían: un documento para entregar a un
auditor (ISO 27001, SOC 2, ENS) que no se rellena a mano. Cada control se MIDE
en el momento sobre los datos de la empresa y dice de dónde sale la cifra.

Estados:
- `pass`: medido y cumple;
- `attention`: medido y no cumple (o cumple a medias);
- `info`: medido, sin umbral que aplicar (es contexto para el auditor);
- `not_measurable`: la aplicación no lo puede ver (p. ej. las copias de
  seguridad, que se hacen fuera). Se dice en vez de inventarlo.

Los umbrales son ajustes de la empresa (grupo `audit`):
`COMPLIANCE_STALE_ACCOUNT_DAYS`, `COMPLIANCE_GDPR_MAX_DAYS`,
`COMPLIANCE_MFA_MIN_COVERAGE_PCT` y `COMPLIANCE_MIN_PASSWORD_LENGTH`.

El informe se firma con la misma clave Ed25519 que la exportación del registro
de auditoría (`cadena_auditoria`): el auditor comprueba la firma con la clave
pública, y la cabeza de la cadena va dentro.
"""
from __future__ import annotations
import logging

import base64
from datetime import datetime, timedelta, timezone

from sqlalchemy import func


def _control(id_: str, estado: str, medido: dict, fuente: str, marcos: tuple[str, ...]) -> dict:
    return {"id": id_, "status": estado, "measured": medido, "source": fuente, "frameworks": list(marcos)}


def _umbral(db, clave: str, org) -> float:
    from app.core.config import settings
    from app.services.settings_service import get_runtime_float
    valor = get_runtime_float(db, clave, org)
    return float(valor if valor is not None else getattr(settings, clave))


def _ajuste_general(db, clave: str, org):
    from app.models.settings import AppSetting
    filas = db.query(AppSetting).filter(AppSetting.key == clave,
                                        (AppSetting.organization_id == org) | AppSetting.organization_id.is_(None)).all()
    propia = next((f for f in filas if f.organization_id == org), None)
    return (propia or (filas[0] if filas else None)).value if filas else None


def generar(db, org: str) -> dict:
    from app.core.config import settings
    from app.db.session import sin_filtro_de_tenant
    from app.models.bookings import ApiKey
    from app.models.billing_reports import SodViolation
    from app.models.cab import GDPRRequest, GDPRRequestStatus
    from app.models.enterprise import SSOConfig
    from app.models.mfa import Organization, WebAuthnCredential
    from app.models.user import User, UserRole
    from app.db import cadena_auditoria
    from app.services import ai_provider_service
    from app.services.settings_service import get_runtime_bool, get_runtime_int

    ahora = datetime.now(timezone.utc)
    controles: list[dict] = []
    with sin_filtro_de_tenant(db):
        empresa = db.get(Organization, org)
        # Revisión GRC 2026-11b: con varias empresas por usuario, sus miembros
        # son los de su ficha y los que tienen pertenencia (el mismo criterio
        # que el filtro de tenant); antes sólo contaban los de su ficha.
        from app.db.session import _miembros_de
        activos = db.query(User).filter(_miembros_de(User, org), User.is_active.is_(True))
        n_activos = activos.count()

        # ── Acceso ──────────────────────────────────────────────────────────
        exige = bool(getattr(empresa, "require_mfa", False))
        controles.append(_control("mfa_required", "pass" if exige else "attention", {"require_mfa": exige},
                                  "organizations.require_mfa", ("ISO27001 A.8.5", "SOC2 CC6.1", "ENS op.acc.5")))
        ids = [u for (u,) in activos.with_entities(User.id)]
        # Auditoria 2026-11: lo que exige el login (auth_core._segundo_factor_o_sesion):
        # `users.mfa_enabled` con `users.mfa_secret`, o una passkey activa. Antes se
        # contaba `mfa_configs`, el segundo sistema TOTP que el login no miraba.
        con_totp = {u for (u,) in activos.filter(User.mfa_enabled.is_(True), User.mfa_secret.isnot(None))
                    .with_entities(User.id)}
        con_llave = {u for (u,) in db.query(WebAuthnCredential.user_id).filter(
            WebAuthnCredential.user_id.in_(ids), WebAuthnCredential.is_active.is_(True)).distinct()} if ids else set()
        cubiertos = len(con_totp | con_llave)
        pct = round(100 * cubiertos / n_activos, 1) if n_activos else 0.0
        minimo = _umbral(db, "COMPLIANCE_MFA_MIN_COVERAGE_PCT", org)
        controles.append(_control("mfa_coverage", "pass" if n_activos and pct >= minimo else "attention",
                                  {"active_users": n_activos, "with_second_factor": cubiertos, "pct": pct,
                                   "totp": len(con_totp), "passkey": len(con_llave), "min_pct": minimo},
                                  "users.mfa_enabled + users.mfa_secret (TOTP) y webauthn_credentials activas, usuarios activos",
                                  ("ISO27001 A.8.5", "SOC2 CC6.1")))
        sso = db.query(SSOConfig).filter(SSOConfig.organization_id == org, SSOConfig.is_active.is_(True),
                                         SSOConfig.is_deleted.is_(False)).count()
        controles.append(_control("sso", "info", {"active_providers": sso}, "sso_configs", ("ISO27001 A.5.16",)))
        longitud = int(get_runtime_int(db, "MIN_PASSWORD_LENGTH", org) or settings.MIN_PASSWORD_LENGTH)
        exigida = int(_umbral(db, "COMPLIANCE_MIN_PASSWORD_LENGTH", org))
        controles.append(_control("password_policy", "pass" if longitud >= exigida else "attention",
                                  {"min_length": longitud, "required": exigida}, "ajuste MIN_PASSWORD_LENGTH",
                                  ("ISO27001 A.5.17", "ENS op.acc.5")))
        inactividad = str(_ajuste_general(db, "idle_timeout_enabled", org) or "false").lower() == "true"
        controles.append(_control("idle_logout", "pass" if inactividad else "attention",
                                  {"enabled": inactividad,
                                   "minutes": _ajuste_general(db, "idle_timeout_minutes", org)},
                                  "app_settings idle_timeout_*", ("ISO27001 A.8.5", "ENS op.acc.6")))

        # ── Cuentas y privilegios ───────────────────────────────────────────
        admins = activos.filter(User.role == UserRole.admin).count()
        controles.append(_control("admins", "info", {"active_admins": admins, "active_users": n_activos},
                                  "users.role = admin", ("ISO27001 A.8.2", "SOC2 CC6.3")))
        dias = int(_umbral(db, "COMPLIANCE_STALE_ACCOUNT_DAYS", org))
        limite = ahora - timedelta(days=dias)
        dormidas = activos.filter((User.last_login.is_(None)) | (User.last_login < limite)).count()
        controles.append(_control("stale_accounts", "pass" if dormidas == 0 else "attention",
                                  {"active_without_login_in_days": dormidas, "days": dias},
                                  "users.last_login de los activos", ("ISO27001 A.5.18", "SOC2 CC6.2")))
        claves = db.query(ApiKey).filter(ApiKey.organization_id == org, ApiKey.is_active.is_(True))
        sin_caducidad = claves.filter(ApiKey.expires_at.is_(None)).count()
        controles.append(_control("api_keys", "pass" if sin_caducidad == 0 else "attention",
                                  {"active": claves.count(), "without_expiry": sin_caducidad},
                                  "api_keys activas", ("ISO27001 A.5.17", "SOC2 CC6.1")))
        sod = db.query(SodViolation).filter(SodViolation.organization_id == org,
                                            SodViolation.resolved.is_(False)).count()
        controles.append(_control("sod_open", "pass" if sod == 0 else "attention", {"open_violations": sod},
                                  "grc_sod_violations sin resolver", ("SOC2 CC6.3", "ISO27001 A.5.3")))

        # ── Registro y datos ────────────────────────────────────────────────
        cadena = cadena_auditoria.verificar(db, org)
        controles.append(_control("audit_chain", "pass" if cadena["ok"] and cadena["rows_checked"] else "attention",
                                  {k: cadena[k] for k in ("ok", "rows_checked", "breaks_total", "head")},
                                  "audit_logs, cadena verificada ahora", ("ISO27001 A.8.15", "SOC2 CC7.2", "ENS op.exp.8")))
        try:
            from app.db import rls
            aislamiento = rls.estado(db.connection())
        except Exception as e:   # se informa, no se inventa
            logging.getLogger(__name__).debug("generar: excepcion ignorada", exc_info=True)
            aislamiento = {"armed": False, "reason": f"no se pudo medir: {type(e).__name__}"}
        controles.append(_control("db_isolation", "pass" if aislamiento.get("armed") else "attention",
                                  {"armed": bool(aislamiento.get("armed")), "reason": aislamiento.get("reason")},
                                  "pg_roles + pg_class (RLS)", ("ISO27001 A.8.3", "SOC2 CC6.1")))
        kms = (settings.KMS_PROVIDER or "").lower() == "aws" and bool(getattr(settings, "AWS_KMS_KEY_ID", ""))
        rotacion = bool(get_runtime_bool(db, "KEY_ROTATION_ENABLED", org))
        controles.append(_control("secrets_encryption", "pass" if rotacion else "attention",
                                  {"kms": kms, "local_key": not kms, "key_rotation_enabled": rotacion},
                                  "KMS_PROVIDER, KEY_ROTATION_ENABLED", ("ISO27001 A.8.24",)))
        plazo = int(_umbral(db, "COMPLIANCE_GDPR_MAX_DAYS", org))
        abiertas = db.query(GDPRRequest).filter(GDPRRequest.organization_id == org, GDPRRequest.status.in_(
            [GDPRRequestStatus.pending, GDPRRequestStatus.processing]))
        vencidas = abiertas.filter(GDPRRequest.created_at < ahora - timedelta(days=plazo)).count()
        controles.append(_control("gdpr_requests", "pass" if vencidas == 0 else "attention",
                                  {"open": abiertas.count(), "older_than_days": vencidas, "days": plazo},
                                  "gdpr_requests pendientes", ("RGPD art. 12.3",)))
        tope = ai_provider_service.presupuesto_diario(db, org)
        controles.append(_control("ai_spend_cap", "info", {"daily_budget_usd": tope,
                                                          "spent_today_usd": round(ai_provider_service.gasto_de_hoy(db, org), 4)},
                                  "AI_DAILY_BUDGET_USD + ai_usage_logs de hoy", ()))
        # Revisión GRC 2026-11b: la retención y el bloqueo legal existen desde la
        # revisión 2026-11 y el informe no los mencionaba.
        from app.models.governance import LegalHold, RetentionPolicy
        politicas = db.query(RetentionPolicy).filter(RetentionPolicy.organization_id == org,
                                                     RetentionPolicy.is_active.is_(True)).count()
        bloqueos = db.query(LegalHold).filter(LegalHold.organization_id == org, LegalHold.is_active.is_(True)).count()
        controles.append(_control("retention", "info", {"active_policies": politicas, "active_legal_holds": bloqueos},
                                  "retention_policies y legal_holds activos", ("ISO27001 A.5.33", "RGPD art. 5.1.e")))
        controles.append(_control("backups", "not_measurable", {},
                                  "las copias se hacen fuera de la aplicación (base de datos y almacenamiento)",
                                  ("ISO27001 A.8.13", "SOC2 A1.2")))
        primera = db.query(func.min(User.created_at)).filter(User.organization_id == org).scalar()

    resumen = {e: sum(c["status"] == e for c in controles) for e in ("pass", "attention", "info", "not_measurable")}
    return {"format": "contecflow-compliance-report/v1", "organization_id": org,
            "organization_name": getattr(empresa, "name", None), "generated_at": ahora.isoformat(),
            "company_since": primera.isoformat() if primera else None,
            "summary": resumen, "controls": controles, "audit_chain_head": cadena["head"]}


def firmar(doc: dict) -> dict:
    """Añade la clave pública y la firma Ed25519 (la misma que la cadena de auditoría)."""
    from app.db import cadena_auditoria
    doc = {**doc, "public_key_pem": cadena_auditoria.clave_publica_pem(),
           "signature_alg": "Ed25519 over the canonical JSON of this document without «signature»"}
    doc["signature"] = base64.b64encode(cadena_auditoria._clave_de_firma().sign(cadena_auditoria._canon(doc))).decode()
    return doc


def firmar_y_registrar(db, usuario, informe: dict) -> dict:
    """Firma el informe, deja traza de la exportacion y confirma."""
    from app.services.audit import audit_log
    doc = firmar(informe)
    audit_log(db, usuario, "EXPORT", "compliance_report", resource_name="signed report",
              metadata={"summary": doc["summary"]})
    db.commit()
    return doc
