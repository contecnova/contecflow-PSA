"""Esquema pendiente de la auditoría 2026-11-22 (23-11-2026).

Lo que los informes 01, 02 y 03 de `docs/auditoria/2026-11-22/` dejaron como
«migración necesaria, no creada»:

1. Facturas de subcontrata (02 A42): `subcontractor_invoices.approved_by` (FK
   users, SET NULL) y `approved_at`; `contracts.currency` (NULL = la moneda de
   la empresa al leer).
2. Textos por clave (02 §6, 03 §6): pares clave/datos para pintar en el idioma
   de cada lector: `texto_clave` + `texto_params` en `grc_sod_rules` (de la
   descripción: la regla no tiene nombre), `issue_types`, `workflow_states`,
   `workflow_transitions` y `approval_groups`; `sprint_plans.ai_reasoning_params`;
   `sd_sla_events.note_*`, `alerts.title_*`/`description_*`, `invoices.notes_*`,
   `rev_entries.description_*` y `timesheets.review_notes_*`. Tipos de aviso
   `milestone_approved` y `milestone_rejected` en `notificationtype` (Postgres:
   `ALTER TYPE ... ADD VALUE` fuera de transacción; SQLite guarda texto).
3. Datos personales fuera de `AppSetting` (03 A-MOD3): tablas
   `sd_voice_sessions` (número y transcripción cifrados, huella HMAC del
   número), `sd_ticket_hold_snapshots`, `sd_dynamic_form_rules` y
   `sd_dynamic_form_rule_history`. Se copian las claves `sd.voice_agent.sessions`,
   `sd.ticket.pending_snapshot.<ticket>` y `sd.dynamic_forms.rules/.history`
   y cada clave se borra SOLO cuando su copia está hecha (lo que no se puede
   copiar —sin empresa, ticket inexistente— se queda en `AppSetting` y se avisa).
4. A-MOD2 (03): `invoices.tax_rate` y `recurring_invoices.tax_rate` a
   Numeric(18,6) (`Rate`) y `rev_obligations.standalone_price` a Numeric(18,2)
   (`Money`). `absences.amount` no es dinero (días u horas): se queda.
5. B-MOD1 (03): `org_id` → `organization_id` en las 11 tablas que lo usaban
   (`abac_*`, `user_attributes`, `policy_audit_log`, `ai_guardrail_*`,
   `security_*`, `login_anomalies`), con sus índices `ix_<tabla>_*`. El modelo
   conserva `org_id` como sinónimo. La RLS la rehace `env.py` tras el upgrade.
6. M-MOD2 (03): `integration_connectors`: fuera los únicos globales de `name` y
   `slug`; `UNIQUE (organization_id, slug)` y único parcial de `slug` en el
   catálogo global (`organization_id IS NULL`). La parte de `client_users`
   queda pendiente (exige antes que el login del portal elija empresa).
7. M-MOD1 (03), paso de datos: las filas de empresa con `organization_id`
   NULL que tienen `project_id` o `ticket_id` toman la empresa de su padre.
   El `SET NOT NULL` por dominios sigue pendiente (los trabajos de fondo aún
   crean filas sin empresa a propósito: `app/db/session.py`).
8. A-MOD1 (03): 440 FK sin `ondelete` (medidas sobre `Base.metadata`):
   `CASCADE` hacia `organizations` (la baja de empresa purga), `SET NULL` si la
   columna admite NULL y `RESTRICT` si no (mismo efecto que hoy, explícito).
   PostgreSQL: `DROP CONSTRAINT` + `ADD ... NOT VALID` + `VALIDATE` (no bloquea
   escrituras mientras valida). SQLite: se reescribe la cláusula en
   `sqlite_master` con `writable_schema` (procedimiento documentado por SQLite
   para cambios que no tocan el formato en disco; cambiar la acción de una FK
   no lo toca) y se comprueba con `PRAGMA integrity_check`: no recrea 350
   tablas ni pierde índices parciales, CHECK ni triggers.

Deshacer real: todo lo anterior al revés, con los datos de vuelta a
`AppSetting` (las sesiones de voz, descifradas) antes de borrar las tablas.
El relleno de M-MOD1 y el redondeo de A-MOD2 no se deshacen (no se sabe qué
fila estaba vacía; el redondeo no pierde nada en un IVA). Las FK vuelven a no
tener acción (`NO ACTION`).

Idempotente: cada paso mira antes si ya está hecho.

Revision ID: 200_esquema_pendiente_auditoria
Revises: 199_seguridad_de_cuentas
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "200_esquema_pendiente_auditoria"
down_revision = "199_seguridad_de_cuentas"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.200")

_TZ = sa.DateTime(timezone=True)

# ── 1-2. Columnas nuevas ──────────────────────────────────────────────────────

#: (tabla, nombre, fábrica de la columna). Las FK van aparte (`_COLUMNAS_FK`).
COLUMNAS = (
    ("subcontractor_invoices", "approved_at", lambda: sa.Column("approved_at", _TZ, nullable=True)),
    ("contracts", "currency", lambda: sa.Column("currency", sa.String(3), nullable=True)),
    ("sprint_plans", "ai_reasoning_params", lambda: sa.Column("ai_reasoning_params", sa.JSON(), nullable=True)),
    *[(t, c, (lambda c=c, tipo=tipo: sa.Column(c, tipo(), nullable=True)))
      for t in ("grc_sod_rules", "issue_types", "workflow_states", "workflow_transitions", "approval_groups")
      for c, tipo in (("texto_clave", lambda: sa.String(120)), ("texto_params", sa.JSON))],
    *[(t, f"{campo}{suf}", (lambda n=f"{campo}{suf}", tipo=tipo: sa.Column(n, tipo(), nullable=True)))
      for t, campo in (("sd_sla_events", "note"), ("alerts", "title"), ("alerts", "description"),
                       ("invoices", "notes"), ("rev_entries", "description"), ("timesheets", "review_notes"))
      for suf, tipo in (("_key", lambda: sa.String(120)), ("_params", sa.JSON))],
)

#: (tabla, columna, tabla referida, ondelete) de las columnas nuevas con FK.
_COLUMNAS_FK = (("subcontractor_invoices", "approved_by", "users", "SET NULL"),)

NUEVOS_TIPOS_DE_AVISO = ("milestone_approved", "milestone_rejected")

# ── 4. Dinero ─────────────────────────────────────────────────────────────────

#: (tabla, columna, decimales, admite NULL)
DINERO = (
    ("invoices", "tax_rate", 6, True),
    ("recurring_invoices", "tax_rate", 6, True),
    ("rev_obligations", "standalone_price", 2, True),
)

# ── 5. B-MOD1 ─────────────────────────────────────────────────────────────────

TABLAS_ORG_ID = (
    "abac_attribute_definitions", "user_attributes", "abac_policies", "policy_audit_log",
    "ai_guardrail_policies", "ai_guardrail_audit_logs",
    "security_events", "security_detections", "security_incidents", "login_anomalies",
    "security_metric_snapshots",
)

# ── 7. M-MOD1 ─────────────────────────────────────────────────────────────────

#: Tablas donde `organization_id` NULL es legítimo (catálogos globales, exentas).
TABLAS_GLOBALES = frozenset((
    "ai_providers", "app_settings", "custom_client_industries", "custom_expense_categories",
    "custom_project_statuses", "custom_project_types", "custom_supplier_billing_units",
    "custom_supplier_service_types", "custom_task_statuses", "exchange_rates", "grc_role_permissions",
    "integration_connectors", "organizations", "settings_audit_log",
))
PADRES = (("project_id", "projects"), ("ticket_id", "sd_tickets"))

# ── 8. A-MOD1: `tabla.columna>referida:politica` (C=CASCADE, N=SET NULL, R=RESTRICT) ──

_FK_SIN_ONDELETE = """
absences.organization_id>organizations:C ai_action_logs.organization_id>organizations:C
ai_agent_executions.organization_id>organizations:C ai_agent_steps.organization_id>organizations:C
ai_answer_feedback.organization_id>organizations:C ai_client_chat_messages.organization_id>organizations:C
ai_client_chat_sessions.organization_id>organizations:C ai_client_chat_sessions.project_id>projects:N
ai_contract_clauses.organization_id>organizations:C ai_contracts.organization_id>organizations:C
ai_contracts.project_id>projects:N ai_conversations.organization_id>organizations:C
ai_governance_configs.organization_id>organizations:C
ai_guardrail_audit_logs.policy_id>ai_guardrail_policies:N ai_kb_articles.organization_id>organizations:C
ai_kb_articles.source_ticket_id>sd_tickets:N ai_meeting_actions.organization_id>organizations:C
ai_meeting_actions.task_id>tasks:N ai_meeting_audio.organization_id>organizations:C
ai_meeting_events.organization_id>organizations:C ai_meeting_participants.organization_id>organizations:C
ai_meeting_segments.organization_id>organizations:C ai_meeting_translations.organization_id>organizations:C
ai_meeting_user_prefs.organization_id>organizations:C ai_meetings.organization_id>organizations:C
ai_meetings.project_id>projects:N ai_messages.organization_id>organizations:C
ai_predictions.organization_id>organizations:C ai_prompt_templates.organization_id>organizations:C
ai_task_estimates.organization_id>organizations:C ai_ticket_triages.organization_id>organizations:C
ai_usage_logs.organization_id>organizations:C ai_voice_commands.organization_id>organizations:C
alert_configs.organization_id>organizations:C alerts.organization_id>organizations:C
alm_actas.organization_id>organizations:C alm_adjuntos.organization_id>organizations:C
alm_asset_history.organization_id>organizations:C alm_assets.organization_id>organizations:C
alm_contracts.organization_id>organizations:C alm_cost_centers.organization_id>organizations:C
alm_eventos.organization_id>organizations:C alm_facturas_proveedor.organization_id>organizations:C
alm_license_assignments.organization_id>organizations:C alm_licenses.organization_id>organizations:C
alm_picos_concurrencia.organization_id>organizations:C alm_renewal_alerts.organization_id>organizations:C
alm_renovaciones.organization_id>organizations:C alm_software_installs.organization_id>organizations:C
alm_vendors.organization_id>organizations:C api_keys.organization_id>organizations:C
approval_decisions.organization_id>organizations:C approval_groups.organization_id>organizations:C
approval_requests.organization_id>organizations:C approval_requests.workflow_id>approval_workflows:N
approval_steps.approver_group_id>approval_groups:N approval_steps.organization_id>organizations:C
approval_workflows.chain_on_approval_workflow_id>approval_workflows:N
approval_workflows.organization_id>organizations:C areas.organization_id>organizations:C
ask_data_examples.organization_id>organizations:C audit_logs.organization_id>organizations:C
automation_events.organization_id>organizations:C automation_executions.organization_id>organizations:C
automation_rules.organization_id>organizations:C automation_rules.project_id>projects:N
automation_workflows.organization_id>organizations:C automation_workflows.project_id>projects:N
bi_tokens.organization_id>organizations:C bpmn_instance_steps.organization_id>organizations:C
bpmn_instances.organization_id>organizations:C bpmn_process_versions.organization_id>organizations:C
budgets.organization_id>organizations:C budgets.project_id>projects:N
burnout_risk_snapshots.organization_id>organizations:C cab_votes.organization_id>organizations:C
calendar_events.integration_id>integration_configs:N calendar_events.milestone_id>project_milestones:N
calendar_events.organization_id>organizations:C calendar_events.project_id>projects:N
calendar_events.sprint_id>sprints:N capacity_plans.organization_id>organizations:C
change_request_windows.organization_id>organizations:C change_requests.organization_id>organizations:C
client_contacts.organization_id>organizations:C client_contract_links.organization_id>organizations:C
client_documents.organization_id>organizations:C client_health_snapshots.organization_id>organizations:C
client_license_links.organization_id>organizations:C client_messages.feature_request_id>feature_requests:N
client_messages.organization_id>organizations:C client_messages.parent_id>client_messages:N
client_messages.sender_client_id>client_users:N client_messages.uat_session_id>uat_sessions:N
client_nps.organization_id>organizations:C client_portal_configs.organization_id>organizations:C
client_sessions.organization_id>organizations:C client_surveys.client_id>client_users:N
client_surveys.milestone_id>project_milestones:N client_surveys.organization_id>organizations:C
client_users.organization_id>organizations:C clients.organization_id>organizations:C
clients.sla_policy_id>sd_sla_policies:N cmdb_agent_registrations.organization_id>organizations:C
cmdb_changelog.organization_id>organizations:C cmdb_discovery_jobs.organization_id>organizations:C
commit_links.integration_id>integration_configs:N commit_links.organization_id>organizations:C
contracts.organization_id>organizations:C contracts.sla_policy_id>sd_sla_policies:N
currency_conversion_logs.organization_id>organizations:C
custom_client_industries.organization_id>organizations:C
custom_expense_categories.organization_id>organizations:C custom_field_values.organization_id>organizations:C
custom_fields.organization_id>organizations:C custom_project_statuses.organization_id>organizations:C
custom_project_types.organization_id>organizations:C custom_roles.organization_id>organizations:C
custom_supplier_billing_units.organization_id>organizations:C
custom_supplier_service_types.organization_id>organizations:C
custom_task_statuses.organization_id>organizations:C dashboard_widgets.organization_id>organizations:C
deliverables.milestone_id>project_milestones:N deliverables.organization_id>organizations:C
deliverables.phase_id>project_phases:N departments.organization_id>organizations:C
dev_goals.organization_id>organizations:C development_plans.organization_id>organizations:C
document_access_logs.organization_id>organizations:C document_collab_snapshots.organization_id>organizations:C
document_permissions.organization_id>organizations:C document_tags.organization_id>organizations:C
document_versions.organization_id>organizations:C documents.organization_id>organizations:C
email_logs.organization_id>organizations:C email_logs.template_id>email_templates:N
epic_dependencies.organization_id>organizations:C epic_dependency_meta.organization_id>organizations:C
epic_tasks.organization_id>organizations:C epics.organization_id>organizations:C
esign_envelopes.organization_id>organizations:C esign_signers.organization_id>organizations:C
exchange_rates.organization_id>organizations:C expenses.contract_id>contracts:N
expenses.organization_id>organizations:C expenses.project_id>projects:N
feature_requests.change_request_id>change_requests:N feature_requests.client_id>client_users:N
feature_requests.organization_id>organizations:C financial_approval_audit_logs.organization_id>organizations:C
fts_index.organization_id>organizations:C gantt_baseline_tasks.organization_id>organizations:C
gantt_baselines.organization_id>organizations:C gdpr_requests.organization_id>organizations:C
git_deployments.organization_id>organizations:C git_pull_requests.organization_id>organizations:C
grc_audit_log.organization_id>organizations:C grc_role_permissions.organization_id>organizations:C
grc_sod_rules.mitigated_by_workflow_id>approval_workflows:N grc_sod_rules.organization_id>organizations:C
grc_sod_violations.organization_id>organizations:C grc_sod_violations.rule_id>grc_sod_rules:R
holidays.organization_id>organizations:C import_jobs.organization_id>organizations:C
imputation_alerts.organization_id>organizations:C imputations.organization_id>organizations:C
integration_connectors.organization_id>organizations:C
integration_instances.connector_id>integration_connectors:R invoice_lines.organization_id>organizations:C
invoices.contract_id>contracts:N invoices.organization_id>organizations:C invoices.project_id>projects:N
issue_type_fields.organization_id>organizations:C issue_types.organization_id>organizations:C
kanban_columns.organization_id>organizations:C kanban_configs.organization_id>organizations:C
legal_holds.organization_id>organizations:C mcp_pending_actions.organization_id>organizations:C
mentions.organization_id>organizations:C mfa_backup_codes.organization_id>organizations:C
mfa_challenges.organization_id>organizations:C notifications.organization_id>organizations:C
numbering_sequences.organization_id>organizations:C oauth_apps.organization_id>organizations:C
oauth_tokens.organization_id>organizations:C offices.organization_id>organizations:C
okr_checkins.organization_id>organizations:C okr_key_results.organization_id>organizations:C
okr_objectives.organization_id>organizations:C onboarding_states.organization_id>organizations:C
opportunities.organization_id>organizations:C opportunities.project_id>projects:N
opportunity_activities.organization_id>organizations:C pdf_export_jobs.organization_id>organizations:C
performance_reviews.organization_id>organizations:C pipeline_stage_configs.organization_id>organizations:C
policy_audit_log.policy_id>abac_policies:N portal_conversation_audits.actor_client_id>client_users:N
portal_conversation_messages.sender_client_id>client_users:N
portal_conversation_participants.client_org_id>clients:N
portal_conversation_participants.client_user_id>client_users:N
portal_conversation_participants.organization_id>organizations:C
portal_conversation_policies.default_group_id>sd_agent_groups:N
portal_conversations.assigned_group_id>sd_agent_groups:N
portal_conversations.created_by_client_id>client_users:N portal_conversations.sla_policy_id>sd_sla_policies:N
portfolio_projects.organization_id>organizations:C portfolios.organization_id>organizations:C
project_changelog_entries.organization_id>organizations:C
project_custom_field_values.organization_id>organizations:C
project_custom_fields.organization_id>organizations:C project_health_snapshots.organization_id>organizations:C
project_members.organization_id>organizations:C project_milestones.invoice_id>invoices:N
project_milestones.organization_id>organizations:C project_permissions.organization_id>organizations:C
project_phases.organization_id>organizations:C project_risk_scores.organization_id>organizations:C
project_templates.organization_id>organizations:C public_form_submissions.organization_id>organizations:C
public_forms.organization_id>organizations:C raci_entries.organization_id>organizations:C
rate_entries.organization_id>organizations:C rate_overrides.organization_id>organizations:C
recurring_invoices.contract_id>contracts:N recurring_invoices.organization_id>organizations:C
recurring_invoices.project_id>projects:N recurring_tasks.organization_id>organizations:C
report_definitions.organization_id>organizations:C resource_alerts.organization_id>organizations:C
resource_bookings.organization_id>organizations:C resource_demand_forecasts.organization_id>organizations:C
resource_utilization_snapshots.organization_id>organizations:C
retention_policies.organization_id>organizations:C revenue_forecasts.organization_id>organizations:C
review_360_campaigns.organization_id>organizations:C review_cycles.organization_id>organizations:C
review_questions.organization_id>organizations:C risks.organization_id>organizations:C
saved_filters.organization_id>organizations:C scenario_models.organization_id>organizations:C
scenario_projects.organization_id>organizations:C scenario_projects.project_id>projects:N
scheduled_reports.organization_id>organizations:C sd_agent_group_members.organization_id>organizations:C
sd_agent_groups.organization_id>organizations:C sd_announcements.ci_id>sd_configuration_items:N
sd_announcements.organization_id>organizations:C
sd_autonomous_playbook_executions.organization_id>organizations:C
sd_autonomous_playbooks.organization_id>organizations:C sd_canned_responses.organization_id>organizations:C
sd_change_approvals.organization_id>organizations:C sd_change_blackouts.organization_id>organizations:C
sd_change_requests.organization_id>organizations:C sd_change_requests.related_problem_id>sd_problems:N
sd_change_requests.related_ticket_id>sd_tickets:N sd_channel_conversations.organization_id>organizations:C
sd_channel_messages.organization_id>organizations:C sd_ci_class_fields.organization_id>organizations:C
sd_ci_classes.organization_id>organizations:C sd_ci_relations.organization_id>organizations:C
sd_compliance_reports.organization_id>organizations:C sd_configuration_items.organization_id>organizations:C
sd_configuration_items.project_id>projects:N sd_configuration_items.sla_policy_id>sd_sla_policies:N
sd_escalation_logs.organization_id>organizations:C sd_escalation_logs.rule_id>sd_escalation_rules:R
sd_escalation_rules.group_id>sd_agent_groups:N sd_escalation_rules.organization_id>organizations:C
sd_escalation_rules.target_group_id>sd_agent_groups:N sd_inbound_messages.organization_id>organizations:C
sd_incident_to_problem.organization_id>organizations:C
sd_itsm_metric_snapshots.organization_id>organizations:C sd_jira_configs.organization_id>organizations:C
sd_jira_field_map.organization_id>organizations:C sd_jira_sync_log.organization_id>organizations:C
sd_jira_sync_map.organization_id>organizations:C sd_kb_article_versions.organization_id>organizations:C
sd_kb_articles.category_id>sd_service_categories:N sd_kb_articles.organization_id>organizations:C
sd_kb_articles.service_item_id>sd_service_items:N sd_kb_corrections.organization_id>organizations:C
sd_kb_findings.organization_id>organizations:C sd_kb_gaps.organization_id>organizations:C
sd_known_error_tickets.organization_id>organizations:C sd_known_errors.organization_id>organizations:C
sd_major_incidents.organization_id>organizations:C sd_monitoring_alerts.organization_id>organizations:C
sd_ola_targets.organization_id>organizations:C sd_oncall_entries.organization_id>organizations:C
sd_oncall_schedules.organization_id>organizations:C
sd_portal_assistant_actions.organization_id>organizations:C
sd_problem_rca_templates.organization_id>organizations:C sd_problems.ci_id>sd_configuration_items:N
sd_problems.organization_id>organizations:C sd_problems.project_id>projects:N
sd_releases.organization_id>organizations:C sd_routing_feedback.organization_id>organizations:C
sd_routing_rules.organization_id>organizations:C sd_service_categories.organization_id>organizations:C
sd_service_item_tasks.organization_id>organizations:C sd_service_items.organization_id>organizations:C
sd_sla_events.organization_id>organizations:C sd_sla_policies.organization_id>organizations:C
sd_sla_rules.organization_id>organizations:C sd_standard_change_models.organization_id>organizations:C
sd_status_components.ci_id>sd_configuration_items:N sd_status_components.organization_id>organizations:C
sd_status_incidents.organization_id>organizations:C sd_status_incidents.ticket_id>sd_tickets:N
sd_ticket_approvals.organization_id>organizations:C sd_ticket_comments.author_client_id>client_users:N
sd_ticket_comments.organization_id>organizations:C sd_ticket_events.organization_id>organizations:C
sd_ticket_history.organization_id>organizations:C sd_ticket_lifecycle_states.organization_id>organizations:C
sd_ticket_lifecycle_transitions.organization_id>organizations:C
sd_ticket_lifecycles.organization_id>organizations:C sd_ticket_links.organization_id>organizations:C
sd_ticket_merges.organization_id>organizations:C sd_ticket_templates.category_id>sd_service_categories:N
sd_ticket_templates.default_group_id>sd_agent_groups:N sd_ticket_templates.default_sla_id>sd_sla_policies:N
sd_ticket_templates.organization_id>organizations:C sd_ticket_time_logs.organization_id>organizations:C
sd_ticket_watchers.organization_id>organizations:C sd_tickets.assigned_group_id>sd_agent_groups:N
sd_tickets.ci_id>sd_configuration_items:N sd_tickets.contract_id>contracts:N
sd_tickets.kb_article_id>sd_kb_articles:N sd_tickets.organization_id>organizations:C
sd_tickets.parent_ticket_id>sd_tickets:N sd_tickets.problem_id>sd_problems:N sd_tickets.project_id>projects:N
sd_tickets.requester_client_id>client_users:N sd_tickets.service_item_id>sd_service_items:N
sd_tickets.sla_policy_id>sd_sla_policies:N sd_workflow_blueprint_versions.organization_id>organizations:C
sd_workflow_blueprints.organization_id>organizations:C sd_workflow_run_steps.organization_id>organizations:C
security_detections.incident_id>security_incidents:N security_events.detection_id>security_detections:N
sem_assignments.organization_id>organizations:C sem_config.organization_id>organizations:C
sem_embedding_cache.organization_id>organizations:C sem_feedback.organization_id>organizations:C
sem_profiles.organization_id>organizations:C skill_history.organization_id>organizations:C
skills.organization_id>organizations:C sla_breach_logs.group_id>sd_agent_groups:N
sla_breach_logs.organization_id>organizations:C sla_calendar_holidays.organization_id>organizations:C
sla_calendars.organization_id>organizations:C sla_holidays.organization_id>organizations:C
sla_schedules.organization_id>organizations:C slack_configs.organization_id>organizations:C
slack_notification_logs.organization_id>organizations:C sprint_plan_tasks.organization_id>organizations:C
sprint_plans.organization_id>organizations:C sprint_retro_notes.organization_id>organizations:C
sprint_tasks.organization_id>organizations:C sprints.organization_id>organizations:C
subcontractor_assignments.organization_id>organizations:C subcontractor_assignments.project_id>projects:R
subcontractor_assignments.rate_id>subcontractor_rates:N
subcontractor_assignments.subcontractor_id>subcontractors:R
subcontractor_assignments.worker_id>subcontractor_workers:N
subcontractor_invoices.assignment_id>subcontractor_assignments:N
subcontractor_invoices.organization_id>organizations:C subcontractor_rates.organization_id>organizations:C
subcontractor_timelogs.invoice_id>subcontractor_invoices:N
subcontractor_timelogs.organization_id>organizations:C subcontractor_timelogs.project_id>projects:N
subcontractor_timelogs.subcontractor_id>subcontractors:R subcontractor_workers.organization_id>organizations:C
subcontractors.organization_id>organizations:C supplier_access_grants.organization_id>organizations:C
supplier_contracts.organization_id>organizations:C supplier_documents.organization_id>organizations:C
supplier_pricing_lines.organization_id>organizations:C supplier_reports.organization_id>organizations:C
supplier_risk_assessments.organization_id>organizations:C supplier_services.organization_id>organizations:C
supplier_statements.organization_id>organizations:C supplier_usage_records.organization_id>organizations:C
supplier_work_packages.organization_id>organizations:C task_comments.organization_id>organizations:C
task_dependencies.organization_id>organizations:C task_movement_logs.organization_id>organizations:C
task_state_snapshots.organization_id>organizations:C task_types.organization_id>organizations:C
tasks.organization_id>organizations:C template_deliverables.organization_id>organizations:C
template_documents.organization_id>organizations:C template_phases.organization_id>organizations:C
template_risks.organization_id>organizations:C template_roles.organization_id>organizations:C
template_task_dependencies.organization_id>organizations:C template_tasks.organization_id>organizations:C
threaded_comments.organization_id>organizations:C timer_sessions.organization_id>organizations:C
timesheets.organization_id>organizations:C training_courses.organization_id>organizations:C
training_enrollments.organization_id>organizations:C uat_cases.organization_id>organizations:C
uat_issues.organization_id>organizations:C uat_issues.reported_by>client_users:N
uat_sessions.client_signed_by>client_users:N uat_sessions.deliverable_id>deliverables:N
uat_sessions.organization_id>organizations:C uat_test_cases.organization_id>organizations:C
user_certifications.organization_id>organizations:C user_preferences.organization_id>organizations:C
user_sessions.organization_id>organizations:C user_skills.organization_id>organizations:C
user_vacation_balances.organization_id>organizations:C user_vacation_balances.policy_id>vacation_policies:N
vacation_policies.organization_id>organizations:C vendor_scores.organization_id>organizations:C
webauthn_credentials.organization_id>organizations:C webhook_deliveries.organization_id>organizations:C
webhook_trigger_logs.organization_id>organizations:C webhook_triggers.rule_id>automation_rules:N
webhook_triggers.workflow_id>automation_workflows:N webhooks.organization_id>organizations:C
webhooks.project_id>projects:N wiki_comments.organization_id>organizations:C
wiki_page_tags.organization_id>organizations:C wiki_pages.organization_id>organizations:C
wiki_spaces.organization_id>organizations:C wiki_tags.organization_id>organizations:C
wiki_templates.organization_id>organizations:C wiki_versions.organization_id>organizations:C
work_orders.organization_id>organizations:C work_orders.project_id>projects:N
workflow_executions.organization_id>organizations:C workflow_queue.organization_id>organizations:C
workflow_states.organization_id>organizations:C workflow_steps.organization_id>organizations:C
workflow_transitions.organization_id>organizations:C
"""
_POLITICAS = {"C": "CASCADE", "N": "SET NULL", "R": "RESTRICT"}


def _fks():
    for item in _FK_SIN_ONDELETE.split():
        izq, der = item.split(">")
        tabla, col = izq.split(".")
        ref, pol = der.split(":")
        yield tabla, col, ref, _POLITICAS[pol]


# ── utilidades ────────────────────────────────────────────────────────────────

def _bind():
    return op.get_bind()


def _pg() -> bool:
    return _bind().dialect.name == "postgresql"


def _insp():
    return sa.inspect(_bind())


def _tablas() -> set:
    return set(_insp().get_table_names())


def _columnas(tabla: str) -> dict:
    return {c["name"]: c for c in _insp().get_columns(tabla)}


def _indices(tabla: str) -> set:
    return {i["name"] for i in _insp().get_indexes(tabla)}


def _q(nombre: str) -> str:
    return '"' + nombre.replace('"', '""') + '"'


# ── 1-2 ───────────────────────────────────────────────────────────────────────

def _anadir_columnas() -> None:
    hay_t = _tablas()
    por_tabla: dict = {}
    for tabla, nombre, fabrica in COLUMNAS:
        por_tabla.setdefault(tabla, []).append((nombre, fabrica))
    for tabla, cols in por_tabla.items():
        if tabla not in hay_t:
            continue
        hay = _columnas(tabla)
        faltan = [f() for n, f in cols if n not in hay]
        if faltan:
            with op.batch_alter_table(tabla) as b:
                for col in faltan:
                    b.add_column(col)
    for tabla, col, ref, accion in _COLUMNAS_FK:
        if tabla not in hay_t or col in _columnas(tabla):
            continue
        if _pg():
            op.add_column(tabla, sa.Column(col, sa.String(36), nullable=True))
            op.create_foreign_key(f"fk_{tabla}_{col}", tabla, ref, [col], ["id"], ondelete=accion)
        else:
            # SQLite admite ADD COLUMN con REFERENCES si el valor por defecto es NULL.
            op.execute(f"ALTER TABLE {_q(tabla)} ADD COLUMN {_q(col)} VARCHAR(36) "
                       f"REFERENCES {_q(ref)} (id) ON DELETE {accion}")
        indice = f"ix_{tabla}_{col}"
        if indice not in _indices(tabla):
            op.create_index(indice, tabla, [col])


def _quitar_columnas() -> None:
    hay_t = _tablas()
    for tabla, col, _ref, _a in _COLUMNAS_FK:
        if tabla not in hay_t or col not in _columnas(tabla):
            continue
        indice = f"ix_{tabla}_{col}"
        if indice in _indices(tabla):
            op.drop_index(indice, table_name=tabla)
        if _pg():
            for fk in _insp().get_foreign_keys(tabla):
                if fk.get("constrained_columns") == [col] and fk.get("name"):
                    op.drop_constraint(fk["name"], tabla, type_="foreignkey")
            op.drop_column(tabla, col)
        else:
            with op.batch_alter_table(tabla) as b:
                b.drop_column(col)
    por_tabla: dict = {}
    for tabla, nombre, _f in COLUMNAS:
        por_tabla.setdefault(tabla, []).append(nombre)
    for tabla, cols in por_tabla.items():
        if tabla not in hay_t:
            continue
        hay = _columnas(tabla)
        sobran = [n for n in cols if n in hay]
        if sobran:
            with op.batch_alter_table(tabla) as b:
                for n in sobran:
                    b.drop_column(n)


def _tipos_de_aviso() -> None:
    if not _pg():
        return   # SQLite: el enum es texto
    with op.get_context().autocommit_block():
        for valor in NUEVOS_TIPOS_DE_AVISO:
            op.execute(f"ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS '{valor}'")


def _quitar_tipos_de_aviso() -> None:
    # Postgres no quita valores de un enum: los avisos de hito vuelven a los tipos
    # de gasto que usaban antes y el valor queda sin uso (inofensivo).
    op.execute("UPDATE notifications SET type = 'expense_approved' WHERE type = 'milestone_approved'")
    op.execute("UPDATE notifications SET type = 'expense_rejected' WHERE type = 'milestone_rejected'")


# ── 3. Tablas nuevas y datos de AppSetting ────────────────────────────────────

TABLAS_NUEVAS = ("sd_dynamic_form_rule_history", "sd_dynamic_form_rules", "sd_ticket_hold_snapshots",
                 "sd_voice_sessions")


def _org(nula: bool = False):
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=nula)


def _crear_tablas() -> None:
    hay = _tablas()
    if "sd_voice_sessions" not in hay:
        op.create_table(
            "sd_voice_sessions",
            sa.Column("id", sa.String(36), primary_key=True),
            _org(),
            sa.Column("caller_id_hash", sa.String(64), nullable=True),
            sa.Column("caller_id_last4", sa.String(4), nullable=True),
            sa.Column("caller_id_enc", sa.Text(), nullable=True),
            sa.Column("channel", sa.String(20), nullable=False, server_default="phone"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("intent", sa.String(40), nullable=True),
            sa.Column("entities_enc", sa.Text(), nullable=True),
            sa.Column("transcript_enc", sa.Text(), nullable=True),
            sa.Column("ticket_id", sa.String(36), sa.ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True),
            sa.Column("resolution", sa.String(40), nullable=True),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", _TZ, server_default=sa.func.now(), nullable=True),
            sa.Column("closed_at", _TZ, nullable=True),
        )
        for col in ("organization_id", "caller_id_hash", "status", "ticket_id"):
            op.create_index(f"ix_sd_voice_sessions_{col}", "sd_voice_sessions", [col])
    if "sd_ticket_hold_snapshots" not in hay:
        op.create_table(
            "sd_ticket_hold_snapshots",
            sa.Column("ticket_id", sa.String(36), sa.ForeignKey("sd_tickets.id", ondelete="CASCADE"),
                      primary_key=True),
            _org(),
            sa.Column("snapshot_json", sa.Text(), nullable=False),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_sd_ticket_hold_snapshots_organization_id", "sd_ticket_hold_snapshots",
                        ["organization_id"])
    if "sd_dynamic_form_rules" not in hay:
        op.create_table(
            "sd_dynamic_form_rules",
            sa.Column("id", sa.String(36), primary_key=True),
            _org(),
            sa.Column("regla_json", sa.Text(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("updated_at", _TZ, server_default=sa.func.now(), nullable=True),
        )
        op.create_index("uq_sd_dynamic_form_rules_org", "sd_dynamic_form_rules", ["organization_id"], unique=True)
        op.create_index("ix_sd_dynamic_form_rules_updated_by", "sd_dynamic_form_rules", ["updated_by"])
    if "sd_dynamic_form_rule_history" not in hay:
        op.create_table(
            "sd_dynamic_form_rule_history",
            sa.Column("id", sa.String(36), primary_key=True),
            _org(),
            sa.Column("rule_id", sa.String(36), sa.ForeignKey("sd_dynamic_form_rules.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("regla_json", sa.Text(), nullable=False),
            sa.Column("reason", sa.String(200), nullable=True),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=False),
        )
        for col in ("organization_id", "rule_id", "created_by", "created_at"):
            op.create_index(f"ix_sd_dynamic_form_rule_history_{col}", "sd_dynamic_form_rule_history", [col])


def _fecha(valor):
    if not valor:
        return None
    try:
        d = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _existe(tabla: str, campo: str, valor) -> bool:
    return _bind().execute(sa.text(f"SELECT 1 FROM {_q(tabla)} WHERE {_q(campo)} = :v"), {"v": valor}).first() \
        is not None


def _usuario_o_none(uid):
    return uid if uid and _existe("users", "id", uid) else None


def _ajustes(patron: str):
    return _bind().execute(sa.text('SELECT id, "key", organization_id, value FROM app_settings WHERE "key" LIKE :k'),
                           {"k": patron}).fetchall()


def _borrar_ajuste(ajuste_id) -> None:
    _bind().execute(sa.text("DELETE FROM app_settings WHERE id = :i"), {"i": ajuste_id})


def huella_del_numero(numero):
    """Copia fija de `voice_agent_service.huella_del_numero` (la migración no depende del servicio)."""
    import hashlib
    import hmac
    from app.core.config import settings
    limpio = re.sub(r"[^\d+]", "", numero or "")
    if not limpio:
        return None
    return hmac.new((settings.SECRET_KEY or "").encode(), limpio.encode(), hashlib.sha256).hexdigest()


def _copiar_voz(cuenta: dict) -> None:
    from app.core.encryption import encrypt_value
    bind = _bind()
    tabla = sa.table("sd_voice_sessions", *[sa.column(c) for c in (
        "id", "organization_id", "caller_id_hash", "caller_id_last4", "caller_id_enc", "channel", "status",
        "intent", "entities_enc", "transcript_enc", "ticket_id", "resolution", "created_at", "updated_at",
        "closed_at")])
    for fila in _ajustes("sd.voice_agent.sessions"):
        if not fila.organization_id:
            logger.warning("200: sesiones de voz sin empresa en app_settings (%s): se quedan", fila.id)
            cuenta["voz_sin_empresa"] = cuenta.get("voz_sin_empresa", 0) + 1
            continue
        try:
            sesiones = json.loads(fila.value or "{}") or {}
        except ValueError:
            logger.warning("200: sesiones de voz ilegibles (%s): se quedan", fila.id)
            continue
        for sid, s in (sesiones.items() if isinstance(sesiones, dict) else []):
            s = s if isinstance(s, dict) else {}
            sid = str(s.get("id") or sid)[:36]
            if _existe("sd_voice_sessions", "id", sid):
                continue
            numero = s.get("caller_id") or ""
            digitos = re.sub(r"\D", "", numero)
            ticket = s.get("ticket_id") if s.get("ticket_id") and _existe("sd_tickets", "id", s.get("ticket_id")) \
                else None
            creada = _fecha(s.get("created_at")) or datetime.now(timezone.utc)
            bind.execute(tabla.insert().values(
                id=sid, organization_id=fila.organization_id, caller_id_hash=huella_del_numero(numero),
                caller_id_last4=digitos[-4:] or None, caller_id_enc=encrypt_value(numero) if numero else None,
                channel=str(s.get("channel") or "phone")[:20], status=str(s.get("status") or "active")[:20],
                intent=(str(s["intent"])[:40] if s.get("intent") else None),
                entities_enc=encrypt_value(json.dumps(s.get("entities") or {}, ensure_ascii=False)),
                transcript_enc=encrypt_value(json.dumps(s.get("transcript") or [], ensure_ascii=False)),
                ticket_id=ticket, resolution=(str(s["resolution"])[:40] if s.get("resolution") else None),
                created_at=creada, updated_at=_fecha(s.get("updated_at")) or creada,
                closed_at=_fecha(s.get("closed_at"))))
            cuenta["voz"] = cuenta.get("voz", 0) + 1
        _borrar_ajuste(fila.id)   # todas sus sesiones ya están copiadas


def _copiar_esperas(cuenta: dict) -> None:
    prefijo = "sd.ticket.pending_snapshot."
    for fila in _ajustes(prefijo + "%"):
        ticket_id = fila.key[len(prefijo):]
        t = _bind().execute(sa.text("SELECT organization_id FROM sd_tickets WHERE id = :i"),
                            {"i": ticket_id}).first()
        org = fila.organization_id or (t.organization_id if t else None)
        if t is None or not org or not fila.value:
            cuenta["esperas_sin_copiar"] = cuenta.get("esperas_sin_copiar", 0) + 1
            continue
        if not _existe("sd_ticket_hold_snapshots", "ticket_id", ticket_id):
            _bind().execute(sa.text(
                "INSERT INTO sd_ticket_hold_snapshots (ticket_id, organization_id, snapshot_json, created_at) "
                "VALUES (:t, :o, :s, :c)"), {"t": ticket_id, "o": org, "s": fila.value,
                                             "c": datetime.now(timezone.utc)})
        cuenta["esperas"] = cuenta.get("esperas", 0) + 1
        _borrar_ajuste(fila.id)


def _copiar_formularios(cuenta: dict) -> None:
    bind = _bind()
    historiales = {f.organization_id: f for f in _ajustes("sd.dynamic_forms.history") if f.organization_id}
    for fila in _ajustes("sd.dynamic_forms.rules"):
        if not fila.organization_id:
            continue   # reglas globales del portal: siguen en app_settings
        try:
            reglas = json.loads(fila.value or "{}")
        except ValueError:
            logger.warning("200: reglas de formularios ilegibles (%s): se quedan", fila.id)
            continue
        existente = bind.execute(sa.text("SELECT id FROM sd_dynamic_form_rules WHERE organization_id = :o"),
                                 {"o": fila.organization_id}).first()
        regla_id = existente.id if existente else str(uuid.uuid4())
        if not existente:
            bind.execute(sa.text(
                "INSERT INTO sd_dynamic_form_rules (id, organization_id, regla_json, version, updated_by, updated_at) "
                "VALUES (:i, :o, :r, :v, :u, :t)"), {
                    "i": regla_id, "o": fila.organization_id, "r": fila.value,
                    "v": int(reglas.get("version", 1) or 1) if isinstance(reglas, dict) else 1,
                    "u": _usuario_o_none(reglas.get("updated_by") if isinstance(reglas, dict) else None),
                    "t": _fecha(reglas.get("updated_at") if isinstance(reglas, dict) else None)
                    or datetime.now(timezone.utc)})
        cuenta["formularios"] = cuenta.get("formularios", 0) + 1
        hist = historiales.pop(fila.organization_id, None)
        if hist is not None:
            try:
                versiones = json.loads(hist.value or "[]")
            except ValueError:
                versiones = None
            if isinstance(versiones, list):
                for v in versiones:
                    if not isinstance(v, dict):
                        continue
                    hid = str(v.get("snapshot_id") or uuid.uuid4())[:36]
                    if _existe("sd_dynamic_form_rule_history", "id", hid):
                        continue
                    bind.execute(sa.text(
                        "INSERT INTO sd_dynamic_form_rule_history "
                        "(id, organization_id, rule_id, regla_json, reason, created_by, created_at) "
                        "VALUES (:i, :o, :r, :j, :m, :u, :c)"), {
                            "i": hid, "o": fila.organization_id, "r": regla_id,
                            "j": json.dumps(v.get("rules") or {}, ensure_ascii=False),
                            "m": (str(v["reason"])[:200] if v.get("reason") else None),
                            "u": _usuario_o_none(v.get("created_by")),
                            "c": _fecha(v.get("created_at")) or datetime.now(timezone.utc)})
                    cuenta["formularios_historial"] = cuenta.get("formularios_historial", 0) + 1
                _borrar_ajuste(hist.id)
        _borrar_ajuste(fila.id)


def _ajuste_nuevo(clave: str, org, valor: str, descripcion: str) -> None:
    _bind().execute(sa.text(
        'INSERT INTO app_settings (id, "key", organization_id, value, description) VALUES (:i, :k, :o, :v, :d)'),
        {"i": str(uuid.uuid4()), "k": clave, "o": org, "v": valor, "d": descripcion})


def _devolver_a_ajustes() -> None:
    """Deshacer 3: los datos vuelven a `AppSetting` con su forma de antes."""
    bind = _bind()
    hay = _tablas()
    if "sd_voice_sessions" in hay:
        from app.core.encryption import decrypt_value
        por_org: dict = {}
        for s in bind.execute(sa.text("SELECT * FROM sd_voice_sessions")).mappings():
            def _json(v, r):
                try:
                    return json.loads(decrypt_value(v) or "null") or r if v else r
                except ValueError:
                    return r
            d = {"id": s["id"], "caller_id": decrypt_value(s["caller_id_enc"]) if s["caller_id_enc"] else None,
                 "channel": s["channel"], "status": s["status"], "intent": s["intent"],
                 "entities": _json(s["entities_enc"], {}), "transcript": _json(s["transcript_enc"], []),
                 "ticket_id": s["ticket_id"], "created_at": str(s["created_at"]), "updated_at": str(s["updated_at"])}
            if s["resolution"]:
                d["resolution"] = s["resolution"]
            if s["closed_at"]:
                d["closed_at"] = str(s["closed_at"])
            por_org.setdefault(s["organization_id"], {})[s["id"]] = d
        for org, sesiones in por_org.items():
            bind.execute(sa.text("DELETE FROM app_settings WHERE \"key\" = 'sd.voice_agent.sessions' "
                                 "AND organization_id = :o"), {"o": org})
            _ajuste_nuevo("sd.voice_agent.sessions", org, json.dumps(sesiones, ensure_ascii=False),
                          "Voice Agent session store")
    if "sd_ticket_hold_snapshots" in hay:
        for s in bind.execute(sa.text("SELECT * FROM sd_ticket_hold_snapshots")).mappings():
            clave = f"sd.ticket.pending_snapshot.{s['ticket_id']}"
            bind.execute(sa.text("DELETE FROM app_settings WHERE \"key\" = :k"), {"k": clave})
            _ajuste_nuevo(clave, s["organization_id"], s["snapshot_json"], "Ticket pending snapshot")
    if "sd_dynamic_form_rules" in hay:
        for r in bind.execute(sa.text("SELECT * FROM sd_dynamic_form_rules")).mappings():
            for clave in ("sd.dynamic_forms.rules", "sd.dynamic_forms.history"):
                bind.execute(sa.text("DELETE FROM app_settings WHERE \"key\" = :k AND organization_id = :o"),
                             {"k": clave, "o": r["organization_id"]})
            _ajuste_nuevo("sd.dynamic_forms.rules", r["organization_id"], r["regla_json"],
                          "Service Desk dynamic forms rules")
            historial = [{"snapshot_id": h["id"], "created_at": str(h["created_at"]), "created_by": h["created_by"],
                          "reason": h["reason"], "rules": json.loads(h["regla_json"] or "{}")}
                         for h in bind.execute(sa.text(
                             "SELECT * FROM sd_dynamic_form_rule_history WHERE rule_id = :r ORDER BY created_at DESC"),
                             {"r": r["id"]}).mappings()]
            if historial:
                _ajuste_nuevo("sd.dynamic_forms.history", r["organization_id"],
                              json.dumps(historial, ensure_ascii=False, default=str),
                              "Service Desk dynamic forms configuration history")


# ── 4 ─────────────────────────────────────────────────────────────────────────

def _es_numeric(tipo, escala) -> bool:
    return isinstance(tipo, sa.Numeric) and not isinstance(tipo, sa.Float) and getattr(tipo, "scale", None) == escala


def _dinero(subir: bool) -> None:
    hay_t = _tablas()
    for tabla, col, escala, nula in DINERO:
        if tabla not in hay_t:
            continue
        actual = _columnas(tabla).get(col)
        if actual is None or _es_numeric(actual["type"], escala) == subir:
            continue
        if _pg():
            if subir:
                op.execute(f'ALTER TABLE {_q(tabla)} ALTER COLUMN {_q(col)} TYPE NUMERIC(18, {escala}) '
                           f'USING round({_q(col)}::numeric, {escala})')
            else:
                op.execute(f'ALTER TABLE {_q(tabla)} ALTER COLUMN {_q(col)} TYPE DOUBLE PRECISION '
                           f'USING {_q(col)}::double precision')
            continue
        if subir:
            op.execute(f'UPDATE {_q(tabla)} SET {_q(col)} = round({_q(col)}, {escala}) WHERE {_q(col)} IS NOT NULL')
        with op.batch_alter_table(tabla) as b:
            if subir:
                b.alter_column(col, type_=sa.Numeric(18, escala), existing_type=sa.Float(), existing_nullable=nula)
            else:
                b.alter_column(col, type_=sa.Float(), existing_type=sa.Numeric(18, escala), existing_nullable=nula)


# ── 5 ─────────────────────────────────────────────────────────────────────────

def _renombrar_org_id(de: str, a: str) -> None:
    hay_t = _tablas()
    for tabla in TABLAS_ORG_ID:
        if tabla not in hay_t:
            continue
        cols = _columnas(tabla)
        if de not in cols or a in cols:
            continue
        viejo, nuevo = f"ix_{tabla}_{de}", f"ix_{tabla}_{a}"
        if viejo in _indices(tabla):
            op.drop_index(viejo, table_name=tabla)
        # SQLite >= 3.25 y Postgres: RENAME COLUMN reescribe índices, FK y políticas que la usan.
        op.execute(f"ALTER TABLE {_q(tabla)} RENAME COLUMN {_q(de)} TO {_q(a)}")
        if nuevo not in _indices(tabla):
            op.create_index(nuevo, tabla, [a])


# ── 6 ─────────────────────────────────────────────────────────────────────────

_IX_CONECTOR_ORG = "uq_integration_connectors_org_slug"
_IX_CONECTOR_GLOBAL = "uq_integration_connectors_global_slug"


def _conectores(subir: bool) -> None:
    if "integration_connectors" not in _tablas():
        return
    t = "integration_connectors"
    unicos = [u for u in _insp().get_unique_constraints(t) if u.get("column_names") in (["name"], ["slug"])]
    if subir:
        if unicos:
            if _pg():
                for u in unicos:
                    op.drop_constraint(u["name"], t, type_="unique")
            else:
                conv = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
                with op.batch_alter_table(t, naming_convention=conv, recreate="always") as b:
                    for u in unicos:
                        b.drop_constraint(f"uq_{t}_{u['column_names'][0]}", type_="unique")
        ix = _indices(t)
        if _IX_CONECTOR_ORG not in ix:
            op.create_index(_IX_CONECTOR_ORG, t, ["organization_id", "slug"], unique=True)
        if _IX_CONECTOR_GLOBAL not in ix:
            op.create_index(_IX_CONECTOR_GLOBAL, t, ["slug"], unique=True,
                            sqlite_where=sa.text("organization_id IS NULL"),
                            postgresql_where=sa.text("organization_id IS NULL"))
        return
    ix = _indices(t)
    for nombre in (_IX_CONECTOR_GLOBAL, _IX_CONECTOR_ORG):
        if nombre in ix:
            op.drop_index(nombre, table_name=t)
    if not unicos:
        with op.batch_alter_table(t) as b:
            b.create_unique_constraint(f"uq_{t}_name", ["name"])
            b.create_unique_constraint(f"uq_{t}_slug", ["slug"])


# ── 7 ─────────────────────────────────────────────────────────────────────────

def _rellenar_empresa(cuenta: dict) -> None:
    bind = _bind()
    hay_t = _tablas()
    for tabla in sorted(hay_t - TABLAS_GLOBALES):
        cols = _columnas(tabla)
        if "organization_id" not in cols:
            continue
        for col, padre in PADRES:
            if col not in cols or padre not in hay_t or tabla == padre:
                continue
            n = bind.execute(sa.text(
                f"UPDATE {_q(tabla)} SET organization_id = (SELECT p.organization_id FROM {_q(padre)} p "
                f"WHERE p.id = {_q(tabla)}.{_q(col)}) WHERE organization_id IS NULL AND {_q(col)} IS NOT NULL "
                f"AND EXISTS (SELECT 1 FROM {_q(padre)} p WHERE p.id = {_q(tabla)}.{_q(col)} "
                f"AND p.organization_id IS NOT NULL)")).rowcount
            if n:
                cuenta[f"empresa_rellenada.{tabla}"] = n


# ── 8 ─────────────────────────────────────────────────────────────────────────

_ACCION = r"(?:\s+ON\s+DELETE\s+(?:SET\s+NULL|SET\s+DEFAULT|NO\s+ACTION|CASCADE|RESTRICT))?"


def _patrones_sqlite(col: str, ref: str):
    c, r = re.escape(col), re.escape(ref)
    tabla_ref = rf'REFERENCES\s+"?{r}"?\s*\(\s*"?id"?\s*\)'
    return (
        re.compile(rf'(FOREIGN\s+KEY\s*\(\s*"?{c}"?\s*\)\s*{tabla_ref}){_ACCION}', re.I),
        re.compile(rf'((?:^|[\s,(])"?{c}"?\s+[^,]*?{tabla_ref}){_ACCION}', re.I),
    )


def _fks_sqlite(accion_de) -> dict:
    """Reescribe la acción ON DELETE en `sqlite_master`. `accion_de(pol)` → texto o None (sin acción)."""
    bind = _bind()
    sql_de = dict(bind.execute(sa.text("SELECT name, sql FROM sqlite_master WHERE type = 'table'")).fetchall())
    nuevos: dict = {}
    cuenta = {"cambiadas": 0, "ya_estaban": 0, "sin_fk_en_bd": 0}
    for tabla, col, ref, pol in _fks():
        sql = nuevos.get(tabla, sql_de.get(tabla))
        if not sql:
            continue
        accion = accion_de(pol)
        sufijo = f" ON DELETE {accion}" if accion else ""
        for patron in _patrones_sqlite(col, ref):
            m = patron.search(sql)
            if m:
                nuevo = sql[:m.start()] + m.group(1) + sufijo + sql[m.end():]
                if nuevo == sql:
                    cuenta["ya_estaban"] += 1
                else:
                    nuevos[tabla] = nuevo
                    cuenta["cambiadas"] += 1
                break
        else:
            cuenta["sin_fk_en_bd"] += 1
            logger.info("200: %s.%s no tiene FK a %s en esta base; se deja", tabla, col, ref)
    if nuevos:
        version = bind.execute(sa.text("PRAGMA schema_version")).scalar()
        bind.execute(sa.text("PRAGMA writable_schema = ON"))
        try:
            for tabla, sql in nuevos.items():
                bind.execute(sa.text("UPDATE sqlite_master SET sql = :s WHERE type = 'table' AND name = :n"),
                             {"s": sql, "n": tabla})
            bind.execute(sa.text(f"PRAGMA schema_version = {int(version) + 1}"))
        finally:
            bind.execute(sa.text("PRAGMA writable_schema = OFF"))
        estado = bind.execute(sa.text("PRAGMA integrity_check")).scalar()
        if estado != "ok":
            raise RuntimeError(f"200: integrity_check tras cambiar las FK: {estado}")
    return cuenta


def _fks_pg(subir: bool) -> dict:
    bind = _bind()
    insp = _insp()
    cuenta = {"cambiadas": 0, "ya_estaban": 0, "creadas": 0, "sin_validar": 0}
    por_tabla: dict = {}
    for tabla, col, ref, pol in _fks():
        por_tabla.setdefault(tabla, []).append((col, ref, pol))
    hay_t = set(insp.get_table_names())
    for tabla, fks in sorted(por_tabla.items()):
        if tabla not in hay_t:
            continue
        actuales = insp.get_foreign_keys(tabla)
        for col, ref, pol in fks:
            fk = next((f for f in actuales if f.get("constrained_columns") == [col]
                       and f.get("referred_table") == ref), None)
            objetivo = pol if subir else None
            hay = ((fk or {}).get("options") or {}).get("ondelete")
            if fk is not None and (hay or None) == objetivo:
                cuenta["ya_estaban"] += 1
                continue
            if fk is None and not subir:
                continue
            nombre = (fk or {}).get("name") or f"fk_{tabla}_{col}"[:63]
            if fk is not None:
                op.execute(f"ALTER TABLE {_q(tabla)} DROP CONSTRAINT {_q(nombre)}")
            accion = f" ON DELETE {objetivo}" if objetivo else ""
            op.execute(f"ALTER TABLE {_q(tabla)} ADD CONSTRAINT {_q(nombre)} FOREIGN KEY ({_q(col)}) "
                       f"REFERENCES {_q(ref)} (id){accion} NOT VALID")
            try:
                with bind.begin_nested():
                    op.execute(f"ALTER TABLE {_q(tabla)} VALIDATE CONSTRAINT {_q(nombre)}")
            except sa.exc.DBAPIError:
                cuenta["sin_validar"] += 1
                logger.warning("200: %s.%s tiene filas sin padre; la FK queda NOT VALID (solo filas nuevas)",
                               tabla, col)
            cuenta["cambiadas" if fk is not None else "creadas"] += 1
    return cuenta


def _ondelete(subir: bool) -> dict:
    if _pg():
        return _fks_pg(subir)
    return _fks_sqlite(lambda pol: pol if subir else None)


# ── upgrade / downgrade ───────────────────────────────────────────────────────

def upgrade() -> None:
    cuenta: dict = {}
    _tipos_de_aviso()
    _renombrar_org_id("org_id", "organization_id")
    _anadir_columnas()
    _dinero(subir=True)
    _conectores(subir=True)
    _crear_tablas()
    _copiar_voz(cuenta)
    _copiar_esperas(cuenta)
    _copiar_formularios(cuenta)
    _rellenar_empresa(cuenta)
    cuenta["fk"] = _ondelete(subir=True)
    logger.warning("200: %s", json.dumps(cuenta, ensure_ascii=False, default=str))


def downgrade() -> None:
    _ondelete(subir=False)
    _devolver_a_ajustes()
    hay = _tablas()
    for t in TABLAS_NUEVAS:
        if t in hay:
            op.drop_table(t)
    _conectores(subir=False)
    _dinero(subir=False)
    _quitar_columnas()
    _renombrar_org_id("organization_id", "org_id")
    _quitar_tipos_de_aviso()
