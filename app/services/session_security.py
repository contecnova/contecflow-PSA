from __future__ import annotations

import ipaddress
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.network import extract_client_ip
from app.models.sessions import UserSession
from app.models.user import User as UserModel

logger = logging.getLogger("contecflow.session_security")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pick_ip_from_request(request) -> Optional[str]:
    ip = extract_client_ip(request)
    return None if ip == "unknown" else ip


def _ip_is_public(ip_raw: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_raw)
        return not (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        return False


# ── Reconocimiento del `User-Agent` ──────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). Esto eran dos cascadas de `elif` dentro de
# `_parse_device_name`, complejidad 12 para lo que es una lista de reglas
# probadas en orden. **El orden es la parte importante y era justo la que no se
# veia**: el `User-Agent` de Edge contiene `chrome/` y `safari/`, y el de Chrome
# contiene `safari/`. Si alguien reordena estas filas por parecerle mas logico,
# Edge pasa a reconocerse como Chrome sin que nada falle a gritos.
#
# Se prueban de arriba abajo y gana la primera que encaje.
_NAVEGADORES = (
    ("Edge",    lambda ua: "edg/" in ua or "edge/" in ua),
    ("Chrome",  lambda ua: "chrome/" in ua and "safari/" in ua),
    ("Safari",  lambda ua: "safari/" in ua and "chrome/" not in ua),
    ("Firefox", lambda ua: "firefox/" in ua),
)

_SISTEMAS = (
    ("iPhone",  lambda ua: "iphone" in ua),
    ("iPad",    lambda ua: "ipad" in ua),
    ("Android", lambda ua: "android" in ua),
    ("Windows", lambda ua: "windows" in ua),
    ("macOS",   lambda ua: "mac os" in ua or "macintosh" in ua),
    ("Linux",   lambda ua: "linux" in ua),
)


def _primera_regla_que_encaje(tabla, ua: str, por_defecto: str) -> str:
    for nombre, encaja in tabla:
        if encaja(ua):
            return nombre
    return por_defecto


def _parse_device_name(user_agent: Optional[str]) -> str:
    ua = (user_agent or "").lower()
    if not ua:
        return "Unknown device"
    navegador = _primera_regla_que_encaje(_NAVEGADORES, ua, "Browser")
    sistema = _primera_regla_que_encaje(_SISTEMAS, ua, "Unknown OS")
    return f"{navegador} on {sistema}"


def _lookup_ip_intel(ip_address: Optional[str], request) -> dict:
    out = {
        "country_code": request.headers.get("cf-ipcountry") or None,
        "region": None,
        "city": None,
        "ip_asn": request.headers.get("x-asn") or None,
        "ip_org": request.headers.get("x-isp") or request.headers.get("x-org") or None,
    }
    if not ip_address or not _ip_is_public(ip_address):
        return out

    try:
        with httpx.Client(timeout=1.5) as client:
            resp = client.get(f"https://ipapi.co/{ip_address}/json/")
        if resp.status_code != 200:
            return out
        data = resp.json()
        out["country_code"] = out["country_code"] or data.get("country_code")
        out["region"] = data.get("region")
        out["city"] = data.get("city")
        out["ip_asn"] = out["ip_asn"] or data.get("asn")
        out["ip_org"] = out["ip_org"] or data.get("org")
    except Exception as exc:
        logger.debug("IP intel lookup failed for %s: %s", ip_address, exc)
    return out


def _compute_risk(
    db: Session,
    user_id: str,
    ip_address: Optional[str],
    ip_asn: Optional[str],
    country_code: Optional[str],
    user_agent: Optional[str],
    ip_org: Optional[str],
) -> tuple[int, str, list[str]]:
    score = 0
    reasons: list[str] = []

    if not ip_address:
        score += 20
        reasons.append("IP ausente")
    elif not _ip_is_public(ip_address):
        score += 5
        reasons.append("IP privada/no enrutable")
    else:
        score += 10

    previous = (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id)
        .order_by(UserSession.last_seen_at.desc())
        .first()
    )
    if previous is not None:
        if previous.ip_address and ip_address and previous.ip_address != ip_address:
            score += 20
            reasons.append("Cambio de IP")
        if previous.ip_asn and ip_asn and previous.ip_asn != ip_asn:
            score += 25
            reasons.append("Cambio de ASN")
        if previous.country_code and country_code and previous.country_code != country_code:
            score += 20
            reasons.append("Cambio de país")
        prev_ua = (previous.user_agent or "")[:180]
        curr_ua = (user_agent or "")[:180]
        if prev_ua and curr_ua and prev_ua != curr_ua:
            score += 10
            reasons.append("Cambio de agente de usuario")

    org = (ip_org or "").lower()
    if any(word in org for word in ("vpn", "proxy", "hosting", "cloud", "digitalocean", "ovh", "linode")):
        score += 20
        reasons.append("ASN/ISP con perfil de anonimización u hosting")

    score = min(score, 100)
    if score >= 75:
        level = "critical"
    elif score >= 50:
        level = "high"
    elif score >= 25:
        level = "medium"
    else:
        level = "low"
    return score, level, reasons


def _organizacion_del_usuario(db: Session, user_id: str) -> Optional[str]:
    """La organizacion del usuario que esta iniciando sesion.

    Auditoria 2026-08. `user_sessions.organization_id` existe desde la auditoria
    #7 y **nadie la rellenaba**, asi que toda sesion nacia con NULL. Con el
    filtro de tenant —`organization_id == org`— una fila con NULL no la ve su
    propia organizacion, de modo que `GET /auth/sessions/active` devolvia
    **cero sesiones a cualquier usuario** y `DELETE /auth/sessions/{id}` no
    encontraba nada que revocar. Un panel vacio y un boton de seguridad muerto,
    sin un solo error en los registros.

    El sellado automatico del `flush` no puede taparlo, y no es un descuido
    suyo: **iniciar sesion es anonimo por definicion**. Cuando se crea esta fila
    todavia no hay usuario autenticado, asi que la sesion de base de datos no
    tiene contexto publicado y `_sellar_organizacion` sale por la puerta de
    atras. Aqui hay que preguntarlo explicitamente.

    Se consulta con la sesion tal cual, sin contexto y por tanto sin filtrar,
    que es lo correcto: buscar al usuario por id es justo el paso que todavia no
    sabe de que organizacion es. Es el mismo patron que `get_current_user` y que
    los WebSocket, documentado en `publicar_contexto_de_tenant`.

    Devuelve `None` solo si el usuario **no existe**, porque
    `users.organization_id` es NOT NULL: no hay usuario sin organizacion, ni
    siquiera un superadmin. Y una sesion cuyo usuario no existe no vale nada
    —no se puede refrescar, porque el refresco busca por usuario—, asi que se
    queda sin organizacion en lugar de adoptarla una cualquiera. La revision 095
    de alembic hace lo mismo con el relleno historico, y por la misma razon.
    """
    fila = (
        db.query(UserModel.organization_id)
        .filter(UserModel.id == user_id)
        .first()
    )
    return fila[0] if fila else None


def register_or_rotate_user_session(
    db: Session,
    user_id: str,
    request,
    refresh_token_jti: str,
    auth_method: str,
    previous_refresh_token_jti: Optional[str] = None,
) -> UserSession:
    user_agent = request.headers.get("user-agent") if request else None
    ip_address = _pick_ip_from_request(request) if request else None
    intel = _lookup_ip_intel(ip_address, request) if request else {
        "country_code": None,
        "region": None,
        "city": None,
        "ip_asn": None,
        "ip_org": None,
    }
    risk_score, risk_level, risk_reasons = _compute_risk(
        db=db,
        user_id=user_id,
        ip_address=ip_address,
        ip_asn=intel.get("ip_asn"),
        country_code=intel.get("country_code"),
        user_agent=user_agent,
        ip_org=intel.get("ip_org"),
    )

    existing = None
    if previous_refresh_token_jti:
        existing = (
            db.query(UserSession)
            .filter(
                UserSession.user_id == user_id,
                UserSession.refresh_token_jti == previous_refresh_token_jti,
                UserSession.revoked_at.is_(None),
            )
            .first()
        )

    if existing is None:
        existing = (
            db.query(UserSession)
            .filter(
                UserSession.user_id == user_id,
                UserSession.refresh_token_jti == refresh_token_jti,
                UserSession.revoked_at.is_(None),
            )
            .first()
        )

    organizacion = _organizacion_del_usuario(db, user_id)

    if existing is None:
        existing = UserSession(
            user_id=user_id,
            organization_id=organizacion,
            refresh_token_jti=refresh_token_jti,
            auth_method=auth_method,
            created_at=_now(),
        )
        db.add(existing)

    # Auditoria 2026-08. Las filas que ya existen con NULL se curan al rotar el
    # refresh, asi que un usuario que vuelve a entrar recupera su panel sin
    # esperar a nada. La migracion 095 hace el relleno de una vez para los que
    # no vuelvan pronto; esto es el cinturon.
    if existing.organization_id is None:
        existing.organization_id = organizacion

    existing.refresh_token_jti = refresh_token_jti
    existing.ip_address = ip_address
    existing.ip_asn = intel.get("ip_asn")
    existing.ip_org = intel.get("ip_org")
    existing.country_code = intel.get("country_code")
    existing.region = intel.get("region")
    existing.city = intel.get("city")
    existing.user_agent = user_agent[:512] if user_agent else None
    existing.device_name = _parse_device_name(user_agent)
    existing.risk_score = risk_score
    existing.risk_level = risk_level
    existing.risk_reasons = json.dumps(risk_reasons)
    existing.auth_method = auth_method
    existing.last_seen_at = _now()
    try:
        from app.services.settings_service import get_runtime_int
        _refresh_days = get_runtime_int(db, "REFRESH_TOKEN_EXPIRE_DAYS") or settings.REFRESH_TOKEN_EXPIRE_DAYS
    except Exception:
        _refresh_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
    existing.expires_at = _now() + timedelta(days=_refresh_days)
    existing.revoked_at = None
    existing.revoke_reason = None
    return existing


def revoke_session_by_jti(db: Session, user_id: str, refresh_token_jti: Optional[str], reason: str) -> None:
    if not refresh_token_jti:
        return
    session = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user_id,
            UserSession.refresh_token_jti == refresh_token_jti,
            UserSession.revoked_at.is_(None),
        )
        .first()
    )
    if session is None:
        return
    session.revoked_at = _now()
    session.revoke_reason = reason[:255]


def parse_risk_reasons(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        if isinstance(value, list):
            return [str(v) for v in value]
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except Exception:
        logger.debug("parse_risk_reasons: fallo best-effort ignorado", exc_info=True)
    return []
