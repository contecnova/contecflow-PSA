import ipaddress
from typing import Optional

from app.core.config import settings


def _parse_ip(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return str(ipaddress.ip_address(raw))
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except ValueError:
        return None


_PROXY_CACHE = {"expires_at": 0.0, "trust": None, "cidrs_raw": None}
_PROXY_CACHE_TTL = 300.0  # 5 minutes — proxy settings change rarely; hot path


def _effective_proxy_config() -> tuple[bool, str]:
    """Return (TRUST_PROXY_HEADERS, TRUSTED_PROXY_CIDRS) with UI override applied.

    Cached for 5 minutes so the request-path doesn't open a DB session every
    time. Admin changes via Settings → Red / Proxy take effect within 5 min.
    """
    import time as _t
    now = _t.time()
    if _PROXY_CACHE["expires_at"] > now and _PROXY_CACHE["trust"] is not None:
        return bool(_PROXY_CACHE["trust"]), str(_PROXY_CACHE["cidrs_raw"] or "")
    trust = settings.TRUST_PROXY_HEADERS
    cidrs_raw = settings.TRUSTED_PROXY_CIDRS or ""
    try:
        from app.db.session import SessionLocal
        from app.services.settings_service import get_runtime_bool, get_runtime_str
        db = SessionLocal()
        try:
            ui_trust = get_runtime_bool(db, "TRUST_PROXY_HEADERS")
            ui_cidrs = get_runtime_str(db, "TRUSTED_PROXY_CIDRS")
            if ui_trust is not None:
                trust = ui_trust
            if ui_cidrs:
                cidrs_raw = ui_cidrs
        finally:
            db.close()
    except Exception:
        pass
    _PROXY_CACHE["expires_at"] = now + _PROXY_CACHE_TTL
    _PROXY_CACHE["trust"] = trust
    _PROXY_CACHE["cidrs_raw"] = cidrs_raw
    return bool(trust), cidrs_raw


def _trusted_proxy_networks() -> list[ipaddress._BaseNetwork]:
    _, cidrs_raw = _effective_proxy_config()
    cidrs = []
    for raw in cidrs_raw.split(","):
        item = raw.strip()
        if not item:
            continue
        try:
            cidrs.append(ipaddress.ip_network(item, strict=False))
        # intentional: best-effort fallback, log noise outweighs diagnostic value
        except ValueError:
            continue
    return cidrs


def _is_trusted_proxy(ip_raw: Optional[str]) -> bool:
    proxy_ip = _parse_ip(ip_raw)
    if not proxy_ip:
        return False
    ip_obj = ipaddress.ip_address(proxy_ip)
    return any(ip_obj in network for network in _trusted_proxy_networks())


def extract_client_ip(request) -> str:
    direct_ip = _parse_ip(request.client.host if request and request.client else None)
    if not direct_ip:
        return "unknown"

    trust, _ = _effective_proxy_config()
    if not trust or not _is_trusted_proxy(direct_ip):
        return direct_ip

    forwarded_for = request.headers.get("x-forwarded-for", "") if request else ""
    if forwarded_for:
        candidate = _parse_ip(forwarded_for.split(",")[0].strip())
        if candidate:
            return candidate

    real_ip = _parse_ip(request.headers.get("x-real-ip", "") if request else "")
    if real_ip:
        return real_ip

    return direct_ip
