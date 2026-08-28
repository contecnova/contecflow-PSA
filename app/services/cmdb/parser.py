"""
CMDB Parser Utilities — Data normalization and format conversion
===================================================================
Funciones de bajo nivel para parseo, hash, similitud de strings y
normalización de payloads de agentes.
"""
import hashlib
import json
import logging
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger(__name__)


def load_config(provider) -> dict[str, Any]:
    """Devuelve config_json parseado como dict. Devuelve {} si vacío o inválido.

    Args:
        provider: Objeto con atributo config_json

    Returns:
        Diccionario parseado o {} si no es JSON válido
    """
    raw = provider.config_json or "{}"
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def compute_config_hash(attributes: str | dict | list | None) -> str:
    """SHA-256 of attributes normalized to stable JSON/string.

    Normaliza cualquier tipo de entrada a JSON canonicalizado.
    Esto asegura que la misma configuración produce el mismo hash
    independientemente del formato de entrada (dict vs JSON string).

    Args:
        attributes: Configuración como JSON string, dict, list o None

    Returns:
        SHA-256 hexdigest de la representación canónica (vacío si None/vacío)
    """
    if not attributes:
        return ""
    if isinstance(attributes, (dict, list)):
        canonical = json.dumps(attributes, sort_keys=True, separators=(",", ":"))
    elif isinstance(attributes, str):
        try:
            # Normalise: parse then re-dump with sorted keys so ordering differences are ignored
            parsed = json.loads(attributes)
            canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
        except (json.JSONDecodeError, TypeError):
            canonical = attributes
    else:
        canonical = str(attributes)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def string_similarity(a: str | None, b: str | None) -> float:
    """Calcula similitud entre dos strings usando SequenceMatcher.

    Normaliza ambas strings (strip + lowercase) y compara.
    Usada para deduplicación de CIs basada en nombres.

    Args:
        a: Primera string (o None)
        b: Segunda string (o None)

    Returns:
        Similitud en [0.0, 1.0], donde 1.0 es idéntica
    """
    aa = (a or "").strip().lower()
    bb = (b or "").strip().lower()
    if not aa or not bb:
        return 0.0
    return SequenceMatcher(None, aa, bb).ratio()


def resolve_agent_by_token(db, raw_token: str):
    """Look up a CMDBAgentRegistration by raw bearer token.

    Returns the registration object or None if token is invalid/revoked.
    """
    from app.models.cmdb import CMDBAgentRegistration

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return (
        db.query(CMDBAgentRegistration)
        .filter(
            CMDBAgentRegistration.token_hash == token_hash,
            CMDBAgentRegistration.is_active.is_(True),
        )
        .first()
    )


def normalize_agent_payload(payload: dict, agent_id: str) -> dict:
    """Convert an agent checkin payload into a standard CI dict for reconcile_cis.

    Agent payload fields:
        os_type, hostname, fqdn, ip_address, os_version, kernel_version,
        cpu_count, memory_mb, disk_gb, uptime_seconds,
        interfaces: [{name, ip, mac}],
        services: [str],
        tags: {k: v},
    """
    from app.services.cmdb.utils import utcnow, AGENT_CI_TYPE_MAP, PROVIDER_AGENT

    os_type = (payload.get("os_type") or "").lower()
    hostname = payload.get("hostname") or payload.get("fqdn") or agent_id
    ip = payload.get("ip_address") or ""
    os_version = payload.get("os_version") or ""
    kernel = payload.get("kernel_version") or ""
    cpu = payload.get("cpu_count") or 0
    memory_mb = payload.get("memory_mb") or 0
    disk_gb = payload.get("disk_gb") or 0
    uptime_s = payload.get("uptime_seconds") or 0

    interfaces: list[dict] = payload.get("interfaces") or []
    services: list[str] = payload.get("services") or []
    tags: dict = payload.get("tags") or {}

    ci_type = AGENT_CI_TYPE_MAP.get(os_type, "server")
    version = os_version

    attributes = {
        "os_type": os_type,
        "os_version": os_version,
        "kernel_version": kernel,
        "cpu_count": cpu,
        "memory_mb": memory_mb,
        "disk_gb": disk_gb,
        "uptime_seconds": uptime_s,
        "interfaces": interfaces,
        "services": services,
        "tags": tags,
    }

    environment = tags.get("env") or tags.get("environment") or "production"

    return {
        "external_id": f"agent:{agent_id}",
        "name": hostname,
        "ci_type": ci_type,
        "status": "active",
        "environment": environment,
        "ip_address": ip,
        "hostname": hostname,
        "version": version,
        "description": f"On-premise {os_type.upper() if os_type else 'host'} — {os_version}",
        "attributes": json.dumps(attributes),
        "discovery_provider": PROVIDER_AGENT,
        "last_discovered_at": utcnow().isoformat(),
    }


def snmp_get_interfaces(ip: str, port: int, auth_data, engine) -> list[dict]:
    """Walk ifTable (1.3.6.1.2.1.2.2) and return interface info dicts.

    Returns list of {ifIndex, ifDescr, ifType, ifSpeed, ifPhysAddress,
    ifOperStatus, ifAdminStatus} per network interface on the device.
    Silently returns [] if the walk fails or pysnmp is not available.
    """
    try:
        from pysnmp.hlapi import (
            ContextData, ObjectIdentity, ObjectType,
            UdpTransportTarget, nextCmd,
        )
    except ImportError:
        return []

    _OID_IF_TABLE = "1.3.6.1.2.1.2.2.1"
    _IF_COLUMNS = {
        "1": "ifIndex",
        "2": "ifDescr",
        "3": "ifType",
        "5": "ifSpeed",
        "6": "ifPhysAddress",
        "7": "ifAdminStatus",
        "8": "ifOperStatus",
    }

    interfaces: dict[str, dict] = {}

    try:
        transport = UdpTransportTarget((ip, port), timeout=3, retries=1)
        for error_indication, error_status, _, var_binds in nextCmd(
            engine,
            auth_data,
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(_OID_IF_TABLE)),
            lexicographicMode=False,
            maxRows=512,
        ):
            if error_indication or error_status:
                break
            for var_bind in var_binds:
                oid_str = str(var_bind[0])
                val_str = str(var_bind[1])

                # OID form: 1.3.6.1.2.1.2.2.1.<column>.<index>
                parts = oid_str.split(".")
                if len(parts) < 2:
                    continue
                col = parts[-2]
                idx = parts[-1]

                if col not in _IF_COLUMNS:
                    continue
                field = _IF_COLUMNS[col]

                if idx not in interfaces:
                    interfaces[idx] = {"ifIndex": idx}
                interfaces[idx][field] = val_str

    except Exception as exc:
        logger.debug("SNMP ifTable walk %s: %s", ip, exc)

    return list(interfaces.values())
