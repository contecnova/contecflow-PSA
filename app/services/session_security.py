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

logger = logging.getLogger("clarive.session_security")


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


def _parse_device_name(user_agent: Optional[str]) -> str:
    ua = (user_agent or "").lower()
    if not ua:
        return "Unknown device"

    if "edg/" in ua or "edge/" in ua:
        browser = "Edge"
    elif "chrome/" in ua and "safari/" in ua:
        browser = "Chrome"
    elif "safari/" in ua and "chrome/" not in ua:
        browser = "Safari"
    elif "firefox/" in ua:
        browser = "Firefox"
    else:
        browser = "Browser"

    if "iphone" in ua:
        os_name = "iPhone"
    elif "ipad" in ua:
        os_name = "iPad"
    elif "android" in ua:
        os_name = "Android"
    elif "windows" in ua:
        os_name = "Windows"
    elif "mac os" in ua or "macintosh" in ua:
        os_name = "macOS"
    elif "linux" in ua:
        os_name = "Linux"
    else:
        os_name = "Unknown OS"

    return f"{browser} on {os_name}"


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

    if existing is None:
        existing = UserSession(
            user_id=user_id,
            refresh_token_jti=refresh_token_jti,
            auth_method=auth_method,
            created_at=_now(),
        )
        db.add(existing)

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
    existing.expires_at = _now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
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
    except Exception:
        pass
    return []
