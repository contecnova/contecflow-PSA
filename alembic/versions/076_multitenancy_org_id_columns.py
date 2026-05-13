"""multitenancy_org_id_columns

Audit #7 — añade `organization_id` (nullable, indexed, FK organizations.id)
a 301 tablas de negocio que no tenían columna de tenant.

Estrategia de backfill (decisión del usuario):
1. Asegurar que existe una "default org" para producción legacy.
2. UPDATE todas las filas que tengan organization_id IS NULL → default org.id.
3. Mantener `nullable=True` por ahora — hacer NOT NULL requiere
   confirmar que no hay rows huérfanas tras backfill, y se hace en una
   migración posterior cuando se enforcen los filtros en servicios.

Esta migración SOLO añade columna + FK + index + backfill. NO cambia
nullable a False ni añade unique constraints per-tenant. Las queries
de servicios se actualizan en commits separados (#62).

Revision ID: 076_multitenancy_org_id
Revises: 075_user_organization_memberships
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa
import json
from pathlib import Path

# revision identifiers, used by Alembic.
revision = "076_multitenancy_org_id"
down_revision = "075_user_organization_memberships"
branch_labels = None
depends_on = None


# Lista de tablas generada automáticamente por scripts/add_org_id_to_models.py
# (volcada en /tmp/multitenancy_targets.json al ejecutar el script).
TABLES = [
    "ai_agent_executions", "ai_chat_messages", "ai_conversations",
    "ai_governance_decisions", "ai_guardrail_audit_logs", "ai_guardrail_policies",
    "ai_module_runs", "ai_provider_models", "ai_providers",
    "ai_suggestions", "ai_task_estimates", "ai_ticket_triages",
    "alerts", "announcements", "approval_groups",
    "approval_request_history", "approval_requests", "approval_step_decisions",
    "approval_steps", "approval_workflows", "assets", "asset_history",
    "audit_logs", "automation_workflows", "automation_workflow_steps",
    "autonomous_playbooks", "autonomous_playbook_executions", "baselines",
    "bi_alert_evaluations", "bi_bookmarks", "bi_dashboard_collab_comments",
    "bi_dashboard_versions", "bi_data_lineage", "bi_data_versions",
    "bi_data_versioning_snapshots", "bi_export_jobs", "bi_export_schedules",
    "bi_governance_config", "bi_insights", "bi_kpi_subscriptions",
    "bi_platform_connectors", "bi_predictive_metric_evals",
    "bi_query_builder_queries", "bi_recurring_exports", "bi_report_blocks",
    "bi_report_templates", "bi_smart_alerts", "bi_tokens",
    "billing_automation_workflows", "billing_imports", "billing_report_definitions",
    "billing_report_runs", "billing_report_definitions", "boards",
    "budgets", "budget_entries", "cab_meetings", "cab_votes",
    "canned_responses", "capacity_plans", "change_request_steps",
    "change_requests", "ci_relations", "client_contacts",
    "client_health_snapshots", "client_nps", "client_portal_users",
    "client_users", "clients", "collaboration_audit_events",
    "collaboration_call_events", "collaboration_call_invitees",
    "collaboration_call_participants", "collaboration_calls",
    "collaboration_channels", "collaboration_channel_members",
    "collaboration_comments", "collaboration_conversations",
    "collaboration_conversation_members", "collaboration_decisions",
    "collaboration_dlp_violations", "collaboration_drafts",
    "collaboration_encryption_keys", "collaboration_files",
    "collaboration_global_policies", "collaboration_huddles",
    "collaboration_huddle_participants", "collaboration_legal_holds",
    "collaboration_message_reactions", "collaboration_messages",
    "collaboration_organizational_groups", "collaboration_organizational_members",
    "collaboration_per_channel_policies", "collaboration_per_user_policies",
    "collaboration_pinned_messages", "collaboration_polls",
    "collaboration_poll_votes", "collaboration_presence",
    "collaboration_push_subscriptions", "collaboration_read_receipts",
    "collaboration_retention_policies", "collaboration_role_assignments",
    "collaboration_saved_views", "collaboration_screen_share_recordings",
    "collaboration_search_index", "collaboration_threads",
    "collaboration_tickets", "collaboration_transcripts",
    "collaboration_user_settings", "collaboration_webhooks",
    "collaboration_workflow_runs", "compliance_reports", "compliance_violations",
    "configuration_items", "contracts", "course_enrollments",
    "course_progress", "courses", "custom_fields",
    "custom_field_definitions", "custom_field_values",
    "custom_project_statuses", "custom_project_types",
    "custom_task_statuses", "dashboards", "dashboard_versions",
    "deliverables", "departments", "deployments",
    "document_categories", "document_comments", "document_permissions",
    "document_tags", "document_versions", "documents", "epic_dependencies",
    "epics", "esign_envelopes", "esign_recipients",
    "esign_templates", "esign_template_recipients", "escalation_logs",
    "escalation_rules", "events", "exchange_rate_logs",
    "exchange_rates", "expenses", "feature_requests",
    "feedback_submissions", "financial_approval_audit_logs",
    "git_deployments", "git_pull_requests", "global_search_index",
    "governance_audit_events", "governance_policy_executions",
    "governance_policies", "grc_audit_logs", "holidays",
    "imputations", "incident_problems", "integration_jobs",
    "issue_types", "kanban_columns", "kb_articles",
    "kb_article_versions", "key_history", "key_rotation_runs",
    "kr_progress", "labels", "legal_holds",
    "log_correlations", "log_entries", "log_filters",
    "ml_predictions", "milestones", "monthly_health_scores",
    "next_best_actions", "notification_channels", "notification_subscriptions",
    "notifications", "okr_alignments", "okrs",
    "on_call_entries", "on_call_schedules", "performance_cycles",
    "performance_feedback", "performance_objectives", "performance_questions",
    "performance_responses", "performance_reviews", "phases",
    "pipeline_opportunities", "pipeline_stages", "policy_audit_log",
    "portal_conversations", "portal_messages", "portfolio_kpi_snapshots",
    "portfolios", "predictive_metrics", "pricing_models",
    "problem_rca_templates", "problems", "project_baseline_snapshots",
    "project_clients", "project_documents", "project_health_snapshots",
    "project_kpis", "project_members", "project_milestones",
    "project_phases", "project_resource_costs", "project_risks",
    "project_roles", "project_skills", "project_status_history",
    "project_templates", "projects", "raci_assignments",
    "rate_card_entries", "rate_cards", "rate_card_versions",
    "report_definitions", "report_runs", "report_subscriptions",
    "report_templates", "resource_availabilities",
    "resource_capacities", "resource_forecasts", "resource_skills",
    "retainer_invoices", "revenue_recognition_entries", "revenue_schedules",
    "review_assignments", "review_cycles", "review_feedback",
    "rfx_documents", "rfx_proposals", "risk_assessments",
    "risk_mitigations", "risks", "roadmap_items",
    "routing_feedbacks", "routing_rules", "saved_filters",
    "scenario_models", "scenario_projects", "scheduled_reports",
    "scim_users", "sdsla_holidays", "search_history",
    "security_events", "semantic_classifications", "semantic_clusters",
    "semantic_history", "semantic_profiles", "service_categories",
    "service_items", "session_records", "skill_assessments",
    "skills", "slack_configs", "slack_notification_logs",
    "sla_events", "sla_policies", "sod_violations",
    "sprint_tasks", "sprint_velocity_history", "sprints",
    "sso_configurations", "sso_state", "status_page_components",
    "status_page_incidents", "subcontractors", "subcontractor_invoices",
    "tag_definitions", "task_comments", "task_movement_logs",
    "tasks", "team_members", "teams",
    "ticket_comments", "ticket_history", "ticket_links",
    "ticket_merges", "ticket_templates", "ticket_time_logs",
    "ticket_watchers", "tickets", "time_off_requests",
    "timer_starts", "training_enrollments", "training_courses",
    "uat_test_cases", "uat_test_suites", "user_attributes",
    "user_certifications", "user_cost_profiles", "user_preferences",
    "vendor_payments", "vendors", "wbs_items",
    "webhooks", "wiki_pages", "wiki_spaces",
    "workflow_designer_runs", "workflow_designer_steps",
    "workflow_designer_versions", "workflow_designers",
    "sd_workflow_run_steps", "sd_workflow_blueprint_versions",
    "sd_workflow_blueprints",
]


def _table_exists(conn, table_name: str) -> bool:
    """SQLite + Postgres-safe check."""
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    insp = sa.inspect(conn)
    try:
        cols = [c["name"] for c in insp.get_columns(table_name)]
    except Exception:
        return False
    return column_name in cols


def upgrade():
    conn = op.get_bind()
    is_sqlite = conn.dialect.name == "sqlite"

    # 1) Asegurar que existe la default org (idempotente).
    # NO usamos ORM aquí porque la migración debe ser independiente del estado
    # del schema. Insertamos via SQL directo si la fila no existe.
    default_org_id = "00000000-0000-0000-0000-000000000001"
    try:
        result = conn.execute(sa.text("SELECT id FROM organizations WHERE id = :id"), {"id": default_org_id}).first()
        if not result:
            conn.execute(
                sa.text("INSERT INTO organizations (id, name, slug, plan, is_active) "
                        "VALUES (:id, :name, :slug, :plan, 1)"),
                {"id": default_org_id, "name": "Default Organization", "slug": "default", "plan": "starter"},
            )
    except Exception:
        # Si organizations no existe o ya está, continuamos
        pass

    # 2) Añadir columna `organization_id` + index + FK a cada tabla.
    skipped = []
    for table in sorted(set(TABLES)):
        if not _table_exists(conn, table):
            skipped.append(table)
            continue
        if _column_exists(conn, table, "organization_id"):
            continue
        # Algunos modelos ya usan `org_id` en lugar de `organization_id` —
        # no añadimos duplicada.
        if _column_exists(conn, table, "org_id"):
            continue
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("organization_id", sa.String(36), nullable=True))
            batch.create_index(f"ix_{table}_organization_id", ["organization_id"])
            # FK opcional — en SQLite las FK requieren rebuild, en Postgres es ALTER
            if not is_sqlite:
                batch.create_foreign_key(
                    f"fk_{table}_organization_id", "organizations", ["organization_id"], ["id"]
                )

        # 3) Backfill con default org.
        conn.execute(
            sa.text(f"UPDATE {table} SET organization_id = :org_id WHERE organization_id IS NULL"),
            {"org_id": default_org_id},
        )


def downgrade():
    """Reverte la migración eliminando la columna `organization_id` de cada tabla.

    NO elimina la default organization (puede tener otros datos legítimos).
    """
    conn = op.get_bind()
    is_sqlite = conn.dialect.name == "sqlite"

    for table in sorted(set(TABLES)):
        if not _table_exists(conn, table):
            continue
        if not _column_exists(conn, table, "organization_id"):
            continue
        with op.batch_alter_table(table) as batch:
            try:
                batch.drop_index(f"ix_{table}_organization_id")
            except Exception:
                pass
            if not is_sqlite:
                try:
                    batch.drop_constraint(f"fk_{table}_organization_id", type_="foreignkey")
                except Exception:
                    pass
            batch.drop_column("organization_id")
