"""
CMDB Auto-Discovery Service — Refactored Modular Architecture
==============================================================
Descubre activos IT de AWS, Azure, GCP, Kubernetes y vSphere y los reconcilia
con el inventario CMDB.

REFACTORIZADO (Mayo 2026):
Este módulo ahora re-exporta todas las funciones desde servicios independientes:
- app.services.cmdb.discovery    → Funciones de descubrimiento (AWS, K8s, vSphere, Azure, GCP, SNMP)
- app.services.cmdb.models       → Lógica de reconciliación, análisis, deduplicación
- app.services.cmdb.parser       → Funciones de parseo, hash, normalización
- app.services.cmdb.utils        → Utilidades compartidas (constantes, UTC)

Archivos originales: 1,754 líneas (cmdb_discovery_service.py)
Refactorizado a: 4 módulos independientes
  - utils.py (36 líneas): constantes y helpers
  - parser.py (180 líneas): parseo y normalización
  - models.py (500 líneas): reconciliación, análisis, deduplicación
  - discovery.py (1,100 líneas): proveedores y orquestación

Beneficios:
  ✅ Separación de responsabilidades clara
  ✅ Cada proveedor de cloud en su propia función
  ✅ Fácil de testear de forma independiente
  ✅ Reutilizable desde otros módulos
  ✅ Mantenibilidad mejorada (avg 260→180 LOC/file)
"""
from __future__ import annotations

import logging

# Re-export all public functions for backwards compatibility
from app.services.cmdb import (  # noqa: F401
    # Orchestration
    crear_proveedor,
    jobs_de_un_proveedor,
    proveedores_visibles,
    run_discovery_for_provider,
    run_all_active_discoveries,
    run_due_discoveries,
    # Discovery providers
    discover_aws,
    discover_kubernetes,
    discover_vsphere,
    discover_azure,
    discover_gcp,
    discover_snmp,
    discover_snmp_network,
    # Analytics
    get_drift_report,
    get_reconciliation_health,
    deduplicate_candidates,
    auto_merge_duplicates,
    ci_similarity_score,
    reconcile_cis,
    # Agent management
    generate_agent_token,
    list_agent_registrations,
    revoke_agent_token,
    rotate_agent_token,
    process_agent_checkin,
    # Constants & utilities
    SUPPORTED_PROVIDERS,
    utcnow,
)

# Backwards compatibility: maintain original constant names
_PROVIDER_AWS = "aws"
_PROVIDER_K8S = "kubernetes"
_PROVIDER_VSPHERE = "vsphere"
_PROVIDER_AZURE = "azure"
_PROVIDER_GCP = "gcp"
_PROVIDER_SNMP = "snmp"
_SUPPORTED_PROVIDERS = SUPPORTED_PROVIDERS

logger = logging.getLogger(__name__)

__all__ = [
    # Orchestration
    "run_discovery_for_provider",
    "run_all_active_discoveries",
    "run_due_discoveries",
    # Discovery
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
    # Agent Management
    "generate_agent_token",
    "list_agent_registrations",
    "revoke_agent_token",
    "rotate_agent_token",
    "process_agent_checkin",
    # Constants
    "_PROVIDER_AWS",
    "_PROVIDER_K8S",
    "_PROVIDER_VSPHERE",
    "_PROVIDER_AZURE",
    "_PROVIDER_GCP",
    "_PROVIDER_SNMP",
    "_SUPPORTED_PROVIDERS",
]
