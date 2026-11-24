"""CMDB de software, composición y vulnerabilidades (19-11-2026, rev. 190).

Diseño completo: `docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md`.

- Catálogo: `sw_products` (producto), `sw_versions` (versión con fin de soporte
  y de vida), `sw_components` (composición/SBOM: versión de software →
  componente con versión, directo o transitivo).
- Despliegue: `sw_instances` (qué producto y versión corre en qué CI y
  entorno, con su configuración enmascarada), `sw_instance_relations`,
  `sw_config_snapshots` (historial de configuración), `sw_baselines` (reglas
  de configuración por producto).
- Importaciones: `sw_sbom_imports`.
- Activos: `sw_product_licenses` (producto ↔ licencia de ALM); las instancias
  apuntan a la licencia y a la instalación de ALM que las cubren.
- Vulnerabilidades: `sw_vulnerabilities`, `sw_vulnerability_affects`,
  `sw_findings`, `sw_vuln_exceptions`, `sw_sync_runs`.
- Configuración por empresa: `sw_config` (credenciales cifradas).

Toda la lógica vive en `app/services/cmdb_software/`.
"""
import uuid

from sqlalchemy import (Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.sql import func

from app.db.base import Base


def _id():
    return Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


def _org():
    return Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)


def _usuario(nullable=True):
    return Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=nullable, index=True)


def _creado():
    return Column(DateTime(timezone=True), server_default=func.now())


def _actualizado():
    return Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ── Catálogo ──────────────────────────────────────────────────────────────────

class SoftwareProduct(Base):
    __tablename__ = "sw_products"
    __table_args__ = (UniqueConstraint("organization_id", "match_key", name="uq_sw_products_org_key"),)

    id = _id()
    organization_id = _org()
    name = Column(String(200), nullable=False)
    #: application | runtime | language | framework | library | web_server | app_server | database |
    #: middleware | os | container_image | tool | other
    category = Column(String(30), nullable=False, default="application")
    #: purchased | saas | open_source | in_house
    origin = Column(String(20), nullable=False, default="open_source")
    vendor_name = Column(String(200), nullable=True)
    alm_vendor_id = Column(String(36), ForeignKey("alm_vendors.id", ondelete="SET NULL"), nullable=True, index=True)
    description = Column(Text, nullable=True)
    # Identificadores normalizados
    purl_type = Column(String(30), nullable=True)
    purl_namespace = Column(String(200), nullable=True)
    purl_name = Column(String(200), nullable=True)
    cpe_vendor = Column(String(120), nullable=True, index=True)
    cpe_product = Column(String(120), nullable=True, index=True)
    #: Clave única de conciliación: purl (tipo/espacio/nombre) → CPE → nombre normalizado.
    match_key = Column(String(300), nullable=False)
    aliases = Column(Text, nullable=True)            # JSON: otros nombres con los que llega
    license_spdx = Column(String(200), nullable=True)
    homepage = Column(String(500), nullable=True)
    repository_url = Column(String(500), nullable=True)
    # Responsabilidad y negocio
    owner_user_id = _usuario()
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    service_ci_id = Column(String(36), ForeignKey("sd_configuration_items.id", ondelete="SET NULL"), nullable=True,
                           index=True)
    criticality = Column(String(20), nullable=False, default="medium")
    #: Cómo se entrega el software hecho en casa o comprado: internal | saas | distributed (licencias)
    distribution = Column(String(20), nullable=True)
    lifecycle_status = Column(String(20), nullable=False, default="active")  # planned|active|deprecated|retired
    tags = Column(Text, nullable=True)               # JSON lista
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_by = _usuario()
    created_at = _creado()
    updated_at = _actualizado()


class SoftwareVersion(Base):
    __tablename__ = "sw_versions"
    __table_args__ = (UniqueConstraint("product_id", "version", name="uq_sw_versions_product_version"),)

    id = _id()
    organization_id = _org()
    product_id = Column(String(36), ForeignKey("sw_products.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(String(100), nullable=False)
    #: Rama a la que se aplica el ciclo de vida («8.1», «1.24»); vacío = esta versión.
    cycle = Column(String(50), nullable=True)
    release_date = Column(Date, nullable=True)
    support_end = Column(Date, nullable=True)       # fin del soporte activo (o de seguridad)
    eol_date = Column(Date, nullable=True)          # fin de vida
    extended_support_end = Column(Date, nullable=True)
    is_latest = Column(Boolean, nullable=False, default=False, server_default="0")
    lifecycle_source = Column(String(30), nullable=True)   # manual | endoflife | import
    notes = Column(Text, nullable=True)
    created_at = _creado()
    updated_at = _actualizado()


class SoftwareComponent(Base):
    """Un componente de una versión de software (SBOM)."""
    __tablename__ = "sw_components"
    __table_args__ = (Index("ix_sw_components_component", "component_product_id", "component_version"),)

    id = _id()
    organization_id = _org()
    parent_version_id = Column(String(36), ForeignKey("sw_versions.id", ondelete="CASCADE"), nullable=False,
                               index=True)
    component_product_id = Column(String(36), ForeignKey("sw_products.id", ondelete="CASCADE"), nullable=False,
                                  index=True)
    component_version = Column(String(100), nullable=True)
    #: runtime | language | framework | library | bundled | base_image | driver | build_tool | plugin | service
    relation = Column(String(20), nullable=False, default="library")
    scope = Column(String(12), nullable=False, default="required")   # required | optional | dev | test
    direct = Column(Boolean, nullable=False, default=True, server_default="1")
    #: Componente directo que lo trae (transitivas); vacío = directo.
    via_component_id = Column(String(36), ForeignKey("sw_components.id", ondelete="SET NULL"), nullable=True,
                              index=True)
    purl = Column(String(500), nullable=True)
    license_spdx = Column(String(200), nullable=True)
    source = Column(String(12), nullable=False, default="manual")   # manual | sbom | lockfile | agent | scan
    sbom_import_id = Column(String(36), ForeignKey("sw_sbom_imports.id", ondelete="SET NULL"), nullable=True,
                            index=True)
    notes = Column(String(500), nullable=True)
    created_at = _creado()
    updated_at = _actualizado()


class SoftwareSbomImport(Base):
    __tablename__ = "sw_sbom_imports"

    id = _id()
    organization_id = _org()
    version_id = Column(String(36), ForeignKey("sw_versions.id", ondelete="CASCADE"), nullable=True, index=True)
    kind = Column(String(20), nullable=False, default="components")  # components | catalog | vulnerabilities | scan
    format = Column(String(30), nullable=False)
    filename = Column(String(300), nullable=True)
    sha256 = Column(String(64), nullable=True)
    total = Column(Integer, nullable=False, default=0)
    created = Column(Integer, nullable=False, default=0)
    updated = Column(Integer, nullable=False, default=0)
    removed = Column(Integer, nullable=False, default=0)
    status = Column(String(12), nullable=False, default="ok")   # ok | error | partial
    error = Column(Text, nullable=True)
    summary_json = Column(Text, nullable=True)
    created_by = _usuario()
    created_at = _creado()


class SoftwareProductLicense(Base):
    """Producto del catálogo ↔ licencia de ALM (lo que se posee)."""
    __tablename__ = "sw_product_licenses"
    __table_args__ = (UniqueConstraint("product_id", "license_id", name="uq_sw_product_license"),)

    id = _id()
    organization_id = _org()
    product_id = Column(String(36), ForeignKey("sw_products.id", ondelete="CASCADE"), nullable=False, index=True)
    license_id = Column(String(36), ForeignKey("alm_licenses.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by = _usuario()
    created_at = _creado()


# ── Despliegue ────────────────────────────────────────────────────────────────

class SoftwareInstance(Base):
    """Un producto (en una versión) corriendo en un CI y un entorno."""
    __tablename__ = "sw_instances"

    id = _id()
    organization_id = _org()
    product_id = Column(String(36), ForeignKey("sw_products.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey("sw_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    version = Column(String(100), nullable=True)      # la observada
    name = Column(String(200), nullable=True)
    #: Dónde corre: servidor, VM, contenedor, nube (CI de la CMDB).
    ci_id = Column(String(36), ForeignKey("sd_configuration_items.id", ondelete="SET NULL"), nullable=True,
                   index=True)
    #: CI que representa a la instancia en la CMDB (aplicación «Portal»), si lo tiene.
    own_ci_id = Column(String(36), ForeignKey("sd_configuration_items.id", ondelete="SET NULL"), nullable=True,
                       index=True)
    environment = Column(String(10), nullable=False, default="prod")  # prod | pre | test | dev | dr
    status = Column(String(12), nullable=False, default="running")    # planned | running | stopped | retired
    install_path = Column(String(500), nullable=True)
    config_path = Column(String(500), nullable=True)
    ports = Column(Text, nullable=True)               # JSON lista de puertos
    exposure = Column(String(10), nullable=False, default="internal")  # internet | internal | isolated
    #: rev. 194: de dónde sale la exposición: manual | ports | ci | import
    exposure_source = Column(String(10), nullable=True)
    criticality = Column(String(20), nullable=True)   # vacío: la del producto
    owner_user_id = _usuario()
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    service_ci_id = Column(String(36), ForeignKey("sd_configuration_items.id", ondelete="SET NULL"), nullable=True,
                           index=True)
    # Activos (ALM)
    license_id = Column(String(36), ForeignKey("alm_licenses.id", ondelete="SET NULL"), nullable=True, index=True)
    alm_install_id = Column(String(36), ForeignKey("alm_software_installs.id", ondelete="SET NULL"), nullable=True,
                            index=True)
    # Configuración (enmascarada: nunca secretos)
    config_format = Column(String(20), nullable=True)   # nginx | apache | php_ini | ini | keyvalue | json
    config_json = Column(Text, nullable=True)
    config_hash = Column(String(64), nullable=True)
    baseline_config_json = Column(Text, nullable=True)
    baseline_approved_at = Column(DateTime(timezone=True), nullable=True)
    baseline_approved_by = _usuario()
    drift_detected_at = Column(DateTime(timezone=True), nullable=True)
    # Descubrimiento
    source = Column(String(12), nullable=False, default="manual")   # manual | csv | agent | scan | alm
    external_key = Column(String(300), nullable=True, index=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_by = _usuario()
    created_at = _creado()
    updated_at = _actualizado()


class SoftwareInstanceRelation(Base):
    __tablename__ = "sw_instance_relations"

    id = _id()
    organization_id = _org()
    source_instance_id = Column(String(36), ForeignKey("sw_instances.id", ondelete="CASCADE"), nullable=False,
                                index=True)
    target_instance_id = Column(String(36), ForeignKey("sw_instances.id", ondelete="CASCADE"), nullable=True,
                                index=True)
    target_ci_id = Column(String(36), ForeignKey("sd_configuration_items.id", ondelete="CASCADE"), nullable=True,
                          index=True)
    #: depends_on | runs_on | connects_to | publishes_via | uses_database | uses_runtime | part_of
    relation_type = Column(String(20), nullable=False)
    details = Column(String(300), nullable=True)      # puerto, protocolo, base de datos...
    created_by = _usuario()
    created_at = _creado()


class SoftwareConfigSnapshot(Base):
    __tablename__ = "sw_config_snapshots"

    id = _id()
    organization_id = _org()
    instance_id = Column(String(36), ForeignKey("sw_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    config_json = Column(Text, nullable=True)
    config_hash = Column(String(64), nullable=True)
    version = Column(String(100), nullable=True)
    changed_keys = Column(Text, nullable=True)        # JSON lista
    source = Column(String(12), nullable=False, default="manual")
    created_by = _usuario()
    created_at = _creado()


class SoftwareBaseline(Base):
    """Reglas de configuración de un producto (p. ej. nginx sin TLS 1.0)."""
    __tablename__ = "sw_baselines"

    id = _id()
    organization_id = _org()
    product_id = Column(String(36), ForeignKey("sw_products.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    rules_json = Column(Text, nullable=False)   # [{key, op, value, severity, description}]
    environment = Column(String(10), nullable=True)   # vacío: todos
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    approved_by = _usuario()
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_by = _usuario()
    created_at = _creado()
    updated_at = _actualizado()


# ── Vulnerabilidades ──────────────────────────────────────────────────────────

class Vulnerability(Base):
    __tablename__ = "sw_vulnerabilities"
    __table_args__ = (UniqueConstraint("organization_id", "vuln_id", name="uq_sw_vulnerabilities_org_id"),)

    id = _id()
    organization_id = _org()
    vuln_id = Column(String(80), nullable=False, index=True)   # CVE-…, GHSA-…, OSV id
    aliases = Column(Text, nullable=True)            # JSON lista
    source = Column(String(12), nullable=False, default="manual")   # nvd | osv | ghsa | manual | file | trivy | grype
    title = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    severity = Column(String(10), nullable=False, default="unknown")  # critical | high | medium | low | none | unknown
    cvss_score = Column(Float, nullable=True)
    cvss_vector = Column(String(200), nullable=True)
    cvss_version = Column(String(10), nullable=True)
    epss_score = Column(Float, nullable=True)
    epss_percentile = Column(Float, nullable=True)
    kev = Column(Boolean, nullable=False, default=False, server_default="0")
    kev_added = Column(Date, nullable=True)
    cwe = Column(Text, nullable=True)                 # JSON lista
    references = Column(Text, nullable=True)          # JSON lista de URLs
    published_at = Column(DateTime(timezone=True), nullable=True)
    modified_at = Column(DateTime(timezone=True), nullable=True)
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    created_at = _creado()
    updated_at = _actualizado()


class VulnerabilityAffect(Base):
    __tablename__ = "sw_vulnerability_affects"

    id = _id()
    organization_id = _org()
    vulnerability_id = Column(String(36), ForeignKey("sw_vulnerabilities.id", ondelete="CASCADE"), nullable=False,
                              index=True)
    #: Clave de paquete (`tipo/espacio/nombre` del purl) o vacía si va por CPE.
    package_key = Column(String(300), nullable=True, index=True)
    ecosystem = Column(String(30), nullable=True)
    cpe_vendor = Column(String(120), nullable=True)
    cpe_product = Column(String(120), nullable=True, index=True)
    introduced = Column(String(100), nullable=True)
    introduced_inclusive = Column(Boolean, nullable=False, default=True, server_default="1")
    fixed = Column(String(100), nullable=True)        # límite superior excluido
    last_affected = Column(String(100), nullable=True)  # límite superior incluido
    versions = Column(Text, nullable=True)            # JSON: versiones exactas afectadas
    range_text = Column(String(300), nullable=True)   # el rango tal cual llegó
    created_at = _creado()


class VulnerabilityFinding(Base):
    """Un aviso que afecta a algo de la empresa."""
    __tablename__ = "sw_findings"
    __table_args__ = (UniqueConstraint("organization_id", "finding_key", name="uq_sw_findings_org_key"),)

    id = _id()
    organization_id = _org()
    finding_key = Column(String(300), nullable=False)
    vulnerability_id = Column(String(36), ForeignKey("sw_vulnerabilities.id", ondelete="CASCADE"), nullable=False,
                              index=True)
    product_id = Column(String(36), ForeignKey("sw_products.id", ondelete="CASCADE"), nullable=False, index=True)
    affected_version = Column(String(100), nullable=True)
    #: Ocurrencia: instancia desplegada, o versión de software que lo lleva como componente.
    instance_id = Column(String(36), ForeignKey("sw_instances.id", ondelete="CASCADE"), nullable=True, index=True)
    parent_version_id = Column(String(36), ForeignKey("sw_versions.id", ondelete="CASCADE"), nullable=True,
                               index=True)
    component_id = Column(String(36), ForeignKey("sw_components.id", ondelete="SET NULL"), nullable=True, index=True)
    fixed_version = Column(String(100), nullable=True)
    #: open | triaged | in_progress | mitigated | resolved | false_positive | accepted
    status = Column(String(15), nullable=False, default="open", index=True)
    severity = Column(String(10), nullable=False, default="unknown")
    priority_score = Column(Float, nullable=True)
    score_detail = Column(Text, nullable=True)        # JSON: desglose de la prioridad
    environment = Column(String(10), nullable=True)
    exposure = Column(String(10), nullable=True)
    first_seen_at = Column(DateTime(timezone=True), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    sla_due_at = Column(DateTime(timezone=True), nullable=True, index=True)
    assignee_user_id = _usuario()
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    change_id = Column(String(36), ForeignKey("sd_change_requests.id", ondelete="SET NULL"), nullable=True,
                       index=True)
    problem_id = Column(String(36), ForeignKey("sd_problems.id", ondelete="SET NULL"), nullable=True, index=True)
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    resolution = Column(String(30), nullable=True)    # upgraded | removed | not_affected | mitigated | ...
    closed_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = _usuario()
    # rev. 194 (índice de riesgo): quién lo detecta (JSON: correlation, defender, qualys...),
    # intentos de explotación vistos y riesgo del hallazgo (0-100) de la última evaluación.
    detected_by = Column(Text, nullable=True)
    exploit_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    last_exploit_at = Column(DateTime(timezone=True), nullable=True)
    risk_points = Column(Float, nullable=True)
    created_at = _creado()
    updated_at = _actualizado()


class VulnerabilityException(Base):
    __tablename__ = "sw_vuln_exceptions"

    id = _id()
    organization_id = _org()
    finding_id = Column(String(36), ForeignKey("sw_findings.id", ondelete="CASCADE"), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    compensating_controls = Column(Text, nullable=True)
    expires_at = Column(Date, nullable=False)
    status = Column(String(10), nullable=False, default="pending")  # pending|approved|rejected|expired|revoked
    requested_by = _usuario()
    decided_by = _usuario()
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decision_note = Column(Text, nullable=True)
    approval_request_id = Column(String(36), nullable=True, index=True)   # motor de aprobaciones
    created_at = _creado()
    updated_at = _actualizado()


class SoftwareConfig(Base):
    """Configuración del módulo por empresa (una fila)."""
    __tablename__ = "sw_config"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_sw_config_org"),)

    id = _id()
    organization_id = _org()
    # Fuentes de avisos y ciclo de vida
    osv_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    osv_url = Column(String(300), nullable=True)
    nvd_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    nvd_url = Column(String(300), nullable=True)
    nvd_api_key = Column(Text, nullable=True)          # cifrada
    ghsa_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    ghsa_url = Column(String(300), nullable=True)
    ghsa_token = Column(Text, nullable=True)           # cifrada
    epss_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    epss_url = Column(String(300), nullable=True)
    kev_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    kev_url = Column(String(300), nullable=True)
    eol_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    eol_url = Column(String(300), nullable=True)
    auto_sync = Column(Boolean, nullable=False, default=False, server_default="0")
    max_queries = Column(Integer, nullable=False, default=200, server_default="200")
    timeout_seconds = Column(Integer, nullable=False, default=20, server_default="20")
    # SLA de remediación (días desde la detección)
    sla_days_critical = Column(Integer, nullable=False, default=15, server_default="15")
    sla_days_high = Column(Integer, nullable=False, default=30, server_default="30")
    sla_days_medium = Column(Integer, nullable=False, default=90, server_default="90")
    sla_days_low = Column(Integer, nullable=False, default=180, server_default="180")
    sla_days_kev = Column(Integer, nullable=False, default=7, server_default="7")
    exception_max_days = Column(Integer, nullable=False, default=180, server_default="180")
    # Licencias (SPDX, separadas por comas)
    licenses_allowed = Column(Text, nullable=True)
    licenses_denied = Column(Text, nullable=True)
    # Ticket automático para hallazgos nuevos desde esta severidad (vacío: nunca)
    auto_ticket_min_severity = Column(String(10), nullable=True)
    eol_warning_days = Column(Integer, nullable=False, default=90, server_default="90")
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_status = Column(String(12), nullable=True)
    #: rev. 194: pesos y constantes del índice de riesgo, rangos, objetivo, avisos (JSON; ver riesgo/ajustes.py)
    risk_settings = Column(Text, nullable=True)
    updated_by = _usuario()
    created_at = _creado()
    updated_at = _actualizado()


class VulnerabilitySyncRun(Base):
    __tablename__ = "sw_sync_runs"

    id = _id()
    organization_id = _org()
    source = Column(String(12), nullable=False)     # osv | nvd | ghsa | epss | kev | eol | file | correlate
    status = Column(String(12), nullable=False, default="running")   # running | ok | error | partial
    started_at = _creado()
    finished_at = Column(DateTime(timezone=True), nullable=True)
    queries = Column(Integer, nullable=False, default=0)
    vulnerabilities = Column(Integer, nullable=False, default=0)
    findings_new = Column(Integer, nullable=False, default=0)
    findings_resolved = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    triggered_by = Column(String(12), nullable=False, default="manual")   # manual | scheduler | import
    created_by = _usuario()
