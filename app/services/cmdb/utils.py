"""
CMDB Common Utilities — Constants and shared functions
=========================================================
Definiciones compartidas de constantes, funciones UTC, y tipos.
"""
from datetime import datetime, timezone

# Provider type constants
PROVIDER_AWS = "aws"
PROVIDER_K8S = "kubernetes"
PROVIDER_VSPHERE = "vsphere"
PROVIDER_AZURE = "azure"
PROVIDER_GCP = "gcp"
PROVIDER_SNMP = "snmp"
PROVIDER_AGENT = "agent"

SUPPORTED_PROVIDERS = {
    PROVIDER_AWS,
    PROVIDER_K8S,
    PROVIDER_VSPHERE,
    PROVIDER_AZURE,
    PROVIDER_GCP,
    PROVIDER_SNMP,
    PROVIDER_AGENT,
}

# Agent OS type mapping
AGENT_CI_TYPE_MAP = {
    "windows": "server",
    "linux": "server",
}


def utcnow() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(tz=timezone.utc)
