import ipaddress
from typing import Optional

from app.core.config import settings


def _parse_ip(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


def _trusted_proxy_networks() -> list[ipaddress._BaseNetwork]:
    cidrs = []
    for raw in (settings.TRUSTED_PROXY_CIDRS or "").split(","):
        item = raw.strip()
        if not item:
            continue
        try:
            cidrs.append(ipaddress.ip_network(item, strict=False))
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

    if not settings.TRUST_PROXY_HEADERS or not _is_trusted_proxy(direct_ip):
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
