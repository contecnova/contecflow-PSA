"""
CMDB Discovery Service — Modular architecture
===============================================
Descubrimiento de infraestructura IT desde múltiples proveedores.

Exports:
  - Orchestration: run_discovery_for_provider, run_all_active_discoveries, run_due_discoveries, process_agent_checkin
  - Analytics: get_drift_report, get_reconciliation_health, deduplicate_candidates, auto_merge_duplicates
  - Agent Management: generate_agent_token, list_agent_registrations, revoke_agent_token, rotate_agent_token
  - Discovery: discover_aws, discover_kubernetes, discover_vsphere, discover_azure, discover_gcp, discover_snmp, discover_snmp_network
"""

# Orchestration
from app.services.cmdb.discovery import (
    run_discovery_for_provider,
    run_all_active_discoveries,
    run_due_discoveries,
    discover_aws,
    discover_kubernetes,
    discover_vsphere,
    discover_azure,
    discover_gcp,
    discover_snmp,
    discover_snmp_network,
)

# Models & Analytics
from app.services.cmdb.models import (
    get_drift_report,
    get_reconciliation_health,
    deduplicate_candidates,
    auto_merge_duplicates,
    generate_agent_token,
    list_agent_registrations,
    revoke_agent_token,
    rotate_agent_token,
    process_agent_checkin,
    ci_similarity_score,
    reconcile_cis,
)

# Utils
from app.services.cmdb.utils import (
    PROVIDER_AWS,
    PROVIDER_K8S,
    PROVIDER_VSPHERE,
    PROVIDER_AZURE,
    PROVIDER_GCP,
    PROVIDER_SNMP,
    PROVIDER_AGENT,
    SUPPORTED_PROVIDERS,
    utcnow,
)

__all__ = [
    # Orchestration
    "run_discovery_for_provider",
    "run_all_active_discoveries",
    "run_due_discoveries",
    # Discovery providers
    "discover_aws",
    "discover_kubernetes",
    "discover_vsphere",
    "discover_azure",
    "discover_gcp",
    "discover_snmp",
    "discover_snmp_network",
    # Analytics
    "get_drift_report",
    "get_reconciliation_health",
    "deduplicate_candidates",
    "auto_merge_duplicates",
    "ci_similarity_score",
    "reconcile_cis",
    # Agent management
    "generate_agent_token",
    "list_agent_registrations",
    "revoke_agent_token",
    "rotate_agent_token",
    "process_agent_checkin",
    # Constants
    "PROVIDER_AWS",
    "PROVIDER_K8S",
    "PROVIDER_VSPHERE",
    "PROVIDER_AZURE",
    "PROVIDER_GCP",
    "PROVIDER_SNMP",
    "PROVIDER_AGENT",
    "SUPPORTED_PROVIDERS",
    "utcnow",
]
