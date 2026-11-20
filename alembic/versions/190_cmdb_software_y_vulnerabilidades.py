"""CMDB de software, composición y vulnerabilidades (19-11-2026).

Tablas nuevas (ver `app/models/cmdb_software.py` y
`docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md`): catálogo (`sw_products`,
`sw_versions`, `sw_components`, `sw_sbom_imports`, `sw_product_licenses`),
despliegue (`sw_instances`, `sw_instance_relations`, `sw_config_snapshots`,
`sw_baselines`), vulnerabilidades (`sw_vulnerabilities`,
`sw_vulnerability_affects`, `sw_findings`, `sw_vuln_exceptions`,
`sw_sync_runs`) y configuración por empresa (`sw_config`).

No toca tablas existentes: el vínculo con Activos va en tablas propias
(`sw_product_licenses`) y en columnas de las nuevas (`license_id`,
`alm_install_id`, `alm_vendor_id`).

Idempotente: cada tabla se crea solo si no existe. La política RLS de cada
tabla la aplica `env.py` en cada `upgrade` (`app/db/rls.py`).

Downgrade: borra las quince tablas (con sus datos).

Revision ID: 190_cmdb_software_y_vulnerabilidades
Revises: 189_proveedores_y_externalizacion
"""
import sqlalchemy as sa
from alembic import op

revision = "190_cmdb_software_y_vulnerabilidades"
down_revision = "189_proveedores_y_externalizacion"
branch_labels = None
depends_on = None

S = sa.String
B = sa.Boolean
T = sa.Text
DT = sa.DateTime(timezone=True)


def _tablas() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _fk(nombre, tabla, ondelete="SET NULL", nullable=True):
    return sa.Column(nombre, S(36), sa.ForeignKey(f"{tabla}.id", ondelete=ondelete), nullable=nullable)


def _usuario(nombre):
    return _fk(nombre, "users")


def _crear(nombre, *columnas, indices=(), extra=()):
    if nombre in _tablas():
        return
    op.create_table(
        nombre,
        sa.Column("id", S(36), primary_key=True),
        sa.Column("organization_id", S(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        *columnas, *extra,
    )
    for c in ("organization_id", *indices):
        op.create_index(f"ix_{nombre}_{c}", nombre, [c])


def _ts():
    return (sa.Column("created_at", DT, server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", DT, server_default=sa.func.now(), nullable=True))


def upgrade() -> None:
    _crear("sw_products",
           sa.Column("name", S(200), nullable=False),
           sa.Column("category", S(30), nullable=False, server_default="application"),
           sa.Column("origin", S(20), nullable=False, server_default="open_source"),
           sa.Column("vendor_name", S(200)),
           _fk("alm_vendor_id", "alm_vendors"),
           sa.Column("description", T),
           sa.Column("purl_type", S(30)), sa.Column("purl_namespace", S(200)), sa.Column("purl_name", S(200)),
           sa.Column("cpe_vendor", S(120)), sa.Column("cpe_product", S(120)),
           sa.Column("match_key", S(300), nullable=False),
           sa.Column("aliases", T), sa.Column("license_spdx", S(200)),
           sa.Column("homepage", S(500)), sa.Column("repository_url", S(500)),
           _usuario("owner_user_id"),
           _fk("project_id", "projects"),
           _fk("service_ci_id", "sd_configuration_items"),
           sa.Column("criticality", S(20), nullable=False, server_default="medium"),
           sa.Column("distribution", S(20)),
           sa.Column("lifecycle_status", S(20), nullable=False, server_default="active"),
           sa.Column("tags", T), sa.Column("notes", T),
           sa.Column("is_active", B, nullable=False, server_default="1"),
           _usuario("created_by"), *_ts(),
           indices=("alm_vendor_id", "cpe_vendor", "cpe_product", "owner_user_id", "project_id", "service_ci_id",
                    "created_by"),
           extra=(sa.UniqueConstraint("organization_id", "match_key", name="uq_sw_products_org_key"),))

    _crear("sw_versions",
           _fk("product_id", "sw_products", "CASCADE", False),
           sa.Column("version", S(100), nullable=False), sa.Column("cycle", S(50)),
           sa.Column("release_date", sa.Date), sa.Column("support_end", sa.Date), sa.Column("eol_date", sa.Date),
           sa.Column("extended_support_end", sa.Date),
           sa.Column("is_latest", B, nullable=False, server_default="0"),
           sa.Column("lifecycle_source", S(30)), sa.Column("notes", T), *_ts(),
           indices=("product_id",),
           extra=(sa.UniqueConstraint("product_id", "version", name="uq_sw_versions_product_version"),))

    _crear("sw_sbom_imports",
           _fk("version_id", "sw_versions", "CASCADE"),
           sa.Column("kind", S(20), nullable=False, server_default="components"),
           sa.Column("format", S(30), nullable=False), sa.Column("filename", S(300)), sa.Column("sha256", S(64)),
           sa.Column("total", sa.Integer, nullable=False, server_default="0"),
           sa.Column("created", sa.Integer, nullable=False, server_default="0"),
           sa.Column("updated", sa.Integer, nullable=False, server_default="0"),
           sa.Column("removed", sa.Integer, nullable=False, server_default="0"),
           sa.Column("status", S(12), nullable=False, server_default="ok"),
           sa.Column("error", T), sa.Column("summary_json", T),
           _usuario("created_by"),
           sa.Column("created_at", DT, server_default=sa.func.now()),
           indices=("version_id", "created_by"))

    _crear("sw_components",
           _fk("parent_version_id", "sw_versions", "CASCADE", False),
           _fk("component_product_id", "sw_products", "CASCADE", False),
           sa.Column("component_version", S(100)),
           sa.Column("relation", S(20), nullable=False, server_default="library"),
           sa.Column("scope", S(12), nullable=False, server_default="required"),
           sa.Column("direct", B, nullable=False, server_default="1"),
           _fk("via_component_id", "sw_components"),
           sa.Column("purl", S(500)), sa.Column("license_spdx", S(200)),
           sa.Column("source", S(12), nullable=False, server_default="manual"),
           _fk("sbom_import_id", "sw_sbom_imports"),
           sa.Column("notes", S(500)), *_ts(),
           indices=("parent_version_id", "component_product_id", "via_component_id", "sbom_import_id"))
    if "ix_sw_components_component" not in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("sw_components")}:
        op.create_index("ix_sw_components_component", "sw_components", ["component_product_id", "component_version"])

    _crear("sw_product_licenses",
           _fk("product_id", "sw_products", "CASCADE", False),
           _fk("license_id", "alm_licenses", "CASCADE", False),
           _usuario("created_by"),
           sa.Column("created_at", DT, server_default=sa.func.now()),
           indices=("product_id", "license_id", "created_by"),
           extra=(sa.UniqueConstraint("product_id", "license_id", name="uq_sw_product_license"),))

    _crear("sw_instances",
           _fk("product_id", "sw_products", "CASCADE", False),
           _fk("version_id", "sw_versions"),
           sa.Column("version", S(100)), sa.Column("name", S(200)),
           _fk("ci_id", "sd_configuration_items"), _fk("own_ci_id", "sd_configuration_items"),
           sa.Column("environment", S(10), nullable=False, server_default="prod"),
           sa.Column("status", S(12), nullable=False, server_default="running"),
           sa.Column("install_path", S(500)), sa.Column("config_path", S(500)), sa.Column("ports", T),
           sa.Column("exposure", S(10), nullable=False, server_default="internal"),
           sa.Column("criticality", S(20)),
           _usuario("owner_user_id"),
           _fk("client_id", "clients"), _fk("service_ci_id", "sd_configuration_items"),
           _fk("license_id", "alm_licenses"), _fk("alm_install_id", "alm_software_installs"),
           sa.Column("config_format", S(20)), sa.Column("config_json", T), sa.Column("config_hash", S(64)),
           sa.Column("baseline_config_json", T), sa.Column("baseline_approved_at", DT),
           _usuario("baseline_approved_by"),
           sa.Column("drift_detected_at", DT),
           sa.Column("source", S(12), nullable=False, server_default="manual"),
           sa.Column("external_key", S(300)), sa.Column("last_seen_at", DT), sa.Column("notes", T),
           sa.Column("is_active", B, nullable=False, server_default="1"),
           _usuario("created_by"), *_ts(),
           indices=("product_id", "version_id", "ci_id", "own_ci_id", "owner_user_id", "client_id", "service_ci_id",
                    "license_id", "alm_install_id", "baseline_approved_by", "external_key", "created_by"))

    _crear("sw_instance_relations",
           _fk("source_instance_id", "sw_instances", "CASCADE", False),
           _fk("target_instance_id", "sw_instances", "CASCADE"),
           _fk("target_ci_id", "sd_configuration_items", "CASCADE"),
           sa.Column("relation_type", S(20), nullable=False), sa.Column("details", S(300)),
           _usuario("created_by"),
           sa.Column("created_at", DT, server_default=sa.func.now()),
           indices=("source_instance_id", "target_instance_id", "target_ci_id", "created_by"))

    _crear("sw_config_snapshots",
           _fk("instance_id", "sw_instances", "CASCADE", False),
           sa.Column("config_json", T), sa.Column("config_hash", S(64)), sa.Column("version", S(100)),
           sa.Column("changed_keys", T),
           sa.Column("source", S(12), nullable=False, server_default="manual"),
           _usuario("created_by"),
           sa.Column("created_at", DT, server_default=sa.func.now()),
           indices=("instance_id", "created_by"))

    _crear("sw_baselines",
           _fk("product_id", "sw_products", "CASCADE", False),
           sa.Column("name", S(200), nullable=False), sa.Column("rules_json", T, nullable=False),
           sa.Column("environment", S(10)),
           sa.Column("is_active", B, nullable=False, server_default="1"),
           _usuario("approved_by"), sa.Column("approved_at", DT),
           _usuario("created_by"), *_ts(),
           indices=("product_id", "approved_by", "created_by"))

    _crear("sw_vulnerabilities",
           sa.Column("vuln_id", S(80), nullable=False), sa.Column("aliases", T),
           sa.Column("source", S(12), nullable=False, server_default="manual"),
           sa.Column("title", S(500)), sa.Column("description", T),
           sa.Column("severity", S(10), nullable=False, server_default="unknown"),
           sa.Column("cvss_score", sa.Float), sa.Column("cvss_vector", S(200)), sa.Column("cvss_version", S(10)),
           sa.Column("epss_score", sa.Float), sa.Column("epss_percentile", sa.Float),
           sa.Column("kev", B, nullable=False, server_default="0"), sa.Column("kev_added", sa.Date),
           sa.Column("cwe", T), sa.Column("references", T),
           sa.Column("published_at", DT), sa.Column("modified_at", DT), sa.Column("withdrawn_at", DT), *_ts(),
           indices=("vuln_id",),
           extra=(sa.UniqueConstraint("organization_id", "vuln_id", name="uq_sw_vulnerabilities_org_id"),))

    _crear("sw_vulnerability_affects",
           _fk("vulnerability_id", "sw_vulnerabilities", "CASCADE", False),
           sa.Column("package_key", S(300)), sa.Column("ecosystem", S(30)),
           sa.Column("cpe_vendor", S(120)), sa.Column("cpe_product", S(120)),
           sa.Column("introduced", S(100)),
           sa.Column("introduced_inclusive", B, nullable=False, server_default="1"),
           sa.Column("fixed", S(100)), sa.Column("last_affected", S(100)), sa.Column("versions", T),
           sa.Column("range_text", S(300)),
           sa.Column("created_at", DT, server_default=sa.func.now()),
           indices=("vulnerability_id", "package_key", "cpe_product"))

    _crear("sw_findings",
           sa.Column("finding_key", S(300), nullable=False),
           _fk("vulnerability_id", "sw_vulnerabilities", "CASCADE", False),
           _fk("product_id", "sw_products", "CASCADE", False),
           sa.Column("affected_version", S(100)),
           _fk("instance_id", "sw_instances", "CASCADE"),
           _fk("parent_version_id", "sw_versions", "CASCADE"),
           _fk("component_id", "sw_components"),
           sa.Column("fixed_version", S(100)),
           sa.Column("status", S(15), nullable=False, server_default="open"),
           sa.Column("severity", S(10), nullable=False, server_default="unknown"),
           sa.Column("priority_score", sa.Float), sa.Column("score_detail", T),
           sa.Column("environment", S(10)), sa.Column("exposure", S(10)),
           sa.Column("first_seen_at", DT), sa.Column("last_seen_at", DT), sa.Column("sla_due_at", DT),
           _usuario("assignee_user_id"),
           _fk("ticket_id", "sd_tickets"), _fk("change_id", "sd_change_requests"), _fk("problem_id", "sd_problems"),
           _fk("task_id", "tasks"),
           sa.Column("notes", T), sa.Column("resolution", S(30)),
           sa.Column("closed_at", DT), sa.Column("verified_at", DT), _usuario("verified_by"), *_ts(),
           indices=("vulnerability_id", "product_id", "instance_id", "parent_version_id", "component_id", "status",
                    "sla_due_at", "assignee_user_id", "ticket_id", "change_id", "problem_id", "task_id",
                    "verified_by"),
           extra=(sa.UniqueConstraint("organization_id", "finding_key", name="uq_sw_findings_org_key"),))

    _crear("sw_vuln_exceptions",
           _fk("finding_id", "sw_findings", "CASCADE", False),
           sa.Column("reason", T, nullable=False), sa.Column("compensating_controls", T),
           sa.Column("expires_at", sa.Date, nullable=False),
           sa.Column("status", S(10), nullable=False, server_default="pending"),
           _usuario("requested_by"), _usuario("decided_by"), sa.Column("decided_at", DT),
           sa.Column("decision_note", T), sa.Column("approval_request_id", S(36)), *_ts(),
           indices=("finding_id", "requested_by", "decided_by", "approval_request_id"))

    _crear("sw_config",
           sa.Column("osv_enabled", B, nullable=False, server_default="0"), sa.Column("osv_url", S(300)),
           sa.Column("nvd_enabled", B, nullable=False, server_default="0"), sa.Column("nvd_url", S(300)),
           sa.Column("nvd_api_key", T),
           sa.Column("ghsa_enabled", B, nullable=False, server_default="0"), sa.Column("ghsa_url", S(300)),
           sa.Column("ghsa_token", T),
           sa.Column("epss_enabled", B, nullable=False, server_default="0"), sa.Column("epss_url", S(300)),
           sa.Column("kev_enabled", B, nullable=False, server_default="0"), sa.Column("kev_url", S(300)),
           sa.Column("eol_enabled", B, nullable=False, server_default="0"), sa.Column("eol_url", S(300)),
           sa.Column("auto_sync", B, nullable=False, server_default="0"),
           sa.Column("max_queries", sa.Integer, nullable=False, server_default="200"),
           sa.Column("timeout_seconds", sa.Integer, nullable=False, server_default="20"),
           sa.Column("sla_days_critical", sa.Integer, nullable=False, server_default="15"),
           sa.Column("sla_days_high", sa.Integer, nullable=False, server_default="30"),
           sa.Column("sla_days_medium", sa.Integer, nullable=False, server_default="90"),
           sa.Column("sla_days_low", sa.Integer, nullable=False, server_default="180"),
           sa.Column("sla_days_kev", sa.Integer, nullable=False, server_default="7"),
           sa.Column("exception_max_days", sa.Integer, nullable=False, server_default="180"),
           sa.Column("licenses_allowed", T), sa.Column("licenses_denied", T),
           sa.Column("auto_ticket_min_severity", S(10)),
           sa.Column("eol_warning_days", sa.Integer, nullable=False, server_default="90"),
           sa.Column("last_sync_at", DT), sa.Column("last_sync_status", S(12)),
           _usuario("updated_by"), *_ts(),
           indices=("updated_by",),
           extra=(sa.UniqueConstraint("organization_id", name="uq_sw_config_org"),))

    _crear("sw_sync_runs",
           sa.Column("source", S(12), nullable=False),
           sa.Column("status", S(12), nullable=False, server_default="running"),
           sa.Column("started_at", DT, server_default=sa.func.now()), sa.Column("finished_at", DT),
           sa.Column("queries", sa.Integer, nullable=False, server_default="0"),
           sa.Column("vulnerabilities", sa.Integer, nullable=False, server_default="0"),
           sa.Column("findings_new", sa.Integer, nullable=False, server_default="0"),
           sa.Column("findings_resolved", sa.Integer, nullable=False, server_default="0"),
           sa.Column("error", T),
           sa.Column("triggered_by", S(12), nullable=False, server_default="manual"),
           _usuario("created_by"),
           indices=("created_by",))


def downgrade() -> None:
    existentes = _tablas()
    for nombre in ("sw_sync_runs", "sw_config", "sw_vuln_exceptions", "sw_findings", "sw_vulnerability_affects",
                   "sw_vulnerabilities", "sw_baselines", "sw_config_snapshots", "sw_instance_relations",
                   "sw_instances", "sw_product_licenses", "sw_components", "sw_sbom_imports", "sw_versions",
                   "sw_products"):
        if nombre in existentes:
            op.drop_table(nombre)
