"""Paridad de PostgreSQL con los modelos e indices en todas las claves ajenas.

Segunda auditoria 2026-11 (#5 y #12).

1. Paridad. `alembic upgrade head` sobre un PostgreSQL 16 vacio, comparado con
   `Base.metadata` (`alembic.autogenerate.compare_metadata`), daba tres
   diferencias reales, todas en `budgets` (la 144 anadio las columnas sin lo
   demas):
     · `cliente_id` sin su clave ajena a `clients` (ON DELETE SET NULL);
     · `ix_budgets_estado` y `ix_budgets_origen_id`, declarados en el modelo.
   Antes de crear la clave ajena se ponen a NULL los `cliente_id` que apuntan a
   un cliente inexistente: es lo que la propia clave haria al borrar el cliente.

2. Indices. PostgreSQL no indexa las claves ajenas por su cuenta. Tras la 073 y
   la 163 quedaban 316 en la base (371 en los modelos) sin un indice cuya
   primera columna fuese la clave: cada borrado del padre recorre la hija
   entera y cada filtro por la clave es un recorrido secuencial. Esta revision
   crea los 317 que faltan en la base (316 + `budgets.cliente_id`, cuya clave
   ajena nace en el paso 1); los modelos llevan `index=True` en las 371, y las
   54 restantes ya las creaban la 073 y siguientes con el mismo nombre. No se excluye ninguna por
   tabla pequena: no hay datos de produccion con los que justificarlo y en una
   tabla pequena el indice cuesta casi nada.

Mismo patron que la 073 y la 163: idempotente (se salta tabla, columna o indice
que no existan o ya existan), CONCURRENTLY en PostgreSQL, nombres
`ix_<tabla>_<columna>` iguales a los de `index=True`. El downgrade solo quita lo
que crea esta revision.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "164_paridad_postgres_e_indices_de_claves_ajenas"
down_revision: Union[str, None] = "163_indices_de_claves_ajenas_calientes"
branch_labels = None
depends_on = None

FK_CLIENTE = "fk_budgets_cliente_id_clients"

#: Indices declarados en el modelo de `budgets` que ninguna revision creaba.
INDICES_DE_PARIDAD = [
    ("budgets", "estado"),
    ("budgets", "origen_id"),
]

#: Claves ajenas sin indice propio en una base migrada hasta la 163.
INDICES_DE_CLAVES_AJENAS = [
    ('abac_attribute_definitions', 'created_by'),
    ('abac_policies', 'created_by'),
    ('absences', 'approved_by'),
    ('ai_agent_executions', 'approved_by'),
    ('ai_anomalies', 'resolved_by'),
    ('ai_answer_feedback', 'user_id'),
    ('ai_client_chat_sessions', 'project_id'),
    ('ai_contracts', 'created_by'),
    ('ai_governance_configs', 'updated_by'),
    ('ai_guardrail_policies', 'created_by'),
    ('ai_kb_articles', 'reviewed_by'),
    ('ai_kb_articles', 'source_ticket_id'),
    ('ai_meeting_actions', 'assignee_id'),
    ('ai_meeting_actions', 'task_id'),
    ('ai_meetings', 'created_by'),
    ('ai_predictions', 'acknowledged_by'),
    ('ai_prompt_templates', 'created_by'),
    ('ai_providers', 'created_by'),
    ('ai_ticket_triages', 'accepted_by'),
    ('ai_ticket_triages', 'suggested_agent_id'),
    ('ai_usage_logs', 'provider_id'),
    ('ai_usage_logs', 'user_id'),
    ('alerts', 'resolved_by'),
    ('alerts', 'task_id'),
    ('alm_asset_history', 'changed_by'),
    ('alm_assets', 'assigned_to_id'),
    ('alm_assets', 'cost_center_id'),
    ('alm_assets', 'department_id'),
    ('alm_assets', 'project_id'),
    ('alm_assets', 'refresh_ticket_id'),
    ('alm_assets', 'vendor_id'),
    ('alm_contracts', 'cost_center_id'),
    ('alm_contracts', 'created_by'),
    ('alm_contracts', 'owner_id'),
    ('alm_contracts', 'project_id'),
    ('alm_contracts', 'vendor_id'),
    ('alm_cost_centers', 'department_id'),
    ('alm_cost_centers', 'manager_id'),
    ('alm_license_assignments', 'assigned_by'),
    ('alm_license_assignments', 'project_id'),
    ('alm_licenses', 'contract_id'),
    ('alm_licenses', 'cost_center_id'),
    ('alm_licenses', 'project_id'),
    ('alm_licenses', 'vendor_id'),
    ('alm_renewal_alerts', 'recipient_id'),
    ('alm_software_installs', 'installed_by'),
    ('approval_decisions', 'approver_id'),
    ('approval_decisions', 'delegate_to'),
    ('approval_decisions', 'request_id'),
    ('approval_requests', 'requested_by'),
    ('approval_requests', 'workflow_id'),
    ('approval_steps', 'approver_group_id'),
    ('approval_steps', 'escalate_to_user_id'),
    ('approval_workflows', 'chain_on_approval_workflow_id'),
    ('areas', 'manager_id'),
    ('ask_data_examples', 'created_by'),
    ('automation_rules', 'created_by'),
    ('automation_rules', 'project_id'),
    ('automation_workflows', 'project_id'),
    ('bi_tokens', 'created_by'),
    ('bpmn_instance_steps', 'completed_by_user_id'),
    ('bpmn_instances', 'started_by_user_id'),
    ('bpmn_process_versions', 'created_by_user_id'),
    ('bpmn_processes', 'created_by_user_id'),
    ('budget_closes', 'cerrado_por'),
    ('budget_commitments', 'created_by'),
    ('budget_lines', 'user_id'),
    ('budget_templates', 'created_by'),
    ('budget_transfers', 'decisor_id'),
    ('budget_transfers', 'solicitante_id'),
    ('budget_variance_notes', 'autor_id'),
    ('budgets', 'approved_by'),
    ('budgets', 'cliente_id'),
    ('budgets', 'created_by'),
    ('budgets', 'responsable_id'),
    ('cab_votes', 'voter_id'),
    ('calendar_events', 'integration_id'),
    ('calendar_events', 'milestone_id'),
    ('calendar_events', 'project_id'),
    ('calendar_events', 'sprint_id'),
    ('change_requests', 'approved_by'),
    ('change_requests', 'requested_by'),
    ('change_requests', 'reviewed_by'),
    ('client_documents', 'uploaded_by'),
    ('client_messages', 'feature_request_id'),
    ('client_messages', 'sender_client_id'),
    ('client_messages', 'sender_user_id'),
    ('client_messages', 'uat_session_id'),
    ('client_sessions', 'client_id'),
    ('client_surveys', 'client_id'),
    ('client_surveys', 'milestone_id'),
    ('client_surveys', 'project_id'),
    ('client_user_projects', 'project_id'),
    ('clients', 'account_manager_id'),
    ('clients', 'created_by'),
    ('clients', 'sla_policy_id'),
    ('cmdb_agent_registrations', 'ci_id'),
    ('cmdb_agent_registrations', 'created_by'),
    ('cmdb_changelog', 'user_id'),
    ('cmdb_discovery_providers', 'created_by'),
    ('collaboration_attachment_versions', 'uploaded_by_user_id'),
    ('collaboration_attachments', 'uploaded_by_client_id'),
    ('collaboration_audit_events', 'actor_client_id'),
    ('collaboration_calls', 'initiated_by'),
    ('collaboration_channels', 'created_by'),
    ('collaboration_integrations', 'created_by'),
    ('collaboration_mentions', 'mentioned_team_id'),
    ('collaboration_moderation_cases', 'reviewer_user_id'),
    ('collaboration_webhooks', 'target_channel_id'),
    ('commit_links', 'integration_id'),
    ('compliance_evidence', 'created_by'),
    ('conector_llamadas', 'user_id'),
    ('contracts', 'created_by'),
    ('contracts', 'sla_policy_id'),
    ('custom_field_values', 'field_id'),
    ('deliverables', 'milestone_id'),
    ('deliverables', 'owner_id'),
    ('deliverables', 'phase_id'),
    ('departments', 'manager_id'),
    ('development_plans', 'created_by'),
    ('email_logs', 'template_id'),
    ('email_templates', 'created_by'),
    ('enlaces_documentales', 'created_by'),
    ('epic_dependencies', 'depends_on_id'),
    ('epic_dependency_meta', 'created_by'),
    ('epic_dependency_meta', 'depends_on_id'),
    ('epics', 'created_by'),
    ('esign_envelopes', 'created_by_id'),
    ('esign_signers', 'user_id'),
    ('expense_attachments', 'uploaded_by'),
    ('expense_policies', 'created_by'),
    ('expenses', 'contract_id'),
    ('expenses', 'reviewed_by'),
    ('feature_requests', 'change_request_id'),
    ('feature_requests', 'client_id'),
    ('gantt_baselines', 'created_by'),
    ('gdpr_requests', 'processed_by'),
    ('gdpr_requests', 'requestor_id'),
    ('git_deployments', 'pr_id'),
    ('grc_sod_rules', 'created_by'),
    ('grc_sod_rules', 'mitigated_by_workflow_id'),
    ('grc_sod_violations', 'rule_id'),
    ('import_jobs', 'created_by'),
    ('imputations', 'approved_by'),
    ('integration_configs', 'created_by'),
    ('integration_instances', 'connector_id'),
    ('integration_instances', 'created_by'),
    ('leccion_acciones', 'created_by'),
    ('leccion_usos', 'user_id'),
    ('lecciones', 'autor_id'),
    ('lecciones', 'validada_por'),
    ('legal_holds', 'created_by'),
    ('legal_holds', 'released_by'),
    ('maintenance_windows', 'created_by'),
    ('mentions', 'mentioned_by'),
    ('ml_prediction_logs', 'ml_model_id'),
    ('oauth_apps', 'owner_id'),
    ('oauth_states', 'sso_config_id'),
    ('okr_checkins', 'author_id'),
    ('okr_key_results', 'owner_id'),
    ('okr_objectives', 'owner_id'),
    ('okr_objectives', 'project_id'),
    ('opportunities', 'project_id'),
    ('opportunities', 'proposal_template_id'),
    ('opportunity_activities', 'user_id'),
    ('org_brandings', 'created_by'),
    ('pdf_export_jobs', 'requested_by'),
    ('portal_conversation_participants', 'added_by_user_id'),
    ('portal_conversation_policies', 'approval_user_id'),
    ('portal_conversation_policies', 'default_group_id'),
    ('portal_conversations', 'assigned_group_id'),
    ('portal_conversations', 'created_by_client_id'),
    ('portal_conversations', 'created_by_user_id'),
    ('portal_conversations', 'sla_policy_id'),
    ('portfolios', 'owner_id'),
    ('project_changelog_entries', 'author_id'),
    ('project_custom_field_values', 'field_id'),
    ('project_permissions', 'granted_by'),
    ('project_templates', 'created_by'),
    ('projects', 'created_by'),
    ('proposal_templates', 'created_by'),
    ('public_forms', 'created_by'),
    ('public_forms', 'target_project_id'),
    ('raci_entries', 'user_id'),
    ('rate_overrides', 'client_id'),
    ('rate_overrides', 'project_id'),
    ('rate_overrides', 'table_id'),
    ('recurring_invoices', 'contract_id'),
    ('recurring_invoices', 'created_by'),
    ('recurring_tasks', 'assignee_id'),
    ('recurring_tasks', 'created_by'),
    ('resource_alerts', 'acknowledged_by'),
    ('resource_bookings', 'created_by'),
    ('resource_bookings', 'task_id'),
    ('retention_policies', 'updated_by'),
    ('rev_contracts', 'client_id'),
    ('rev_entries', 'created_by'),
    ('rev_entries', 'milestone_id'),
    ('rev_entries', 'period_close_id'),
    ('rev_entries', 'reverses_entry_id'),
    ('rev_obligations', 'milestone_id'),
    ('rev_period_closes', 'closed_by'),
    ('review_360_campaigns', 'created_by'),
    ('review_cycles', 'created_by'),
    ('risks', 'identified_by'),
    ('risks', 'owner_id'),
    ('saved_filters', 'created_by'),
    ('scenario_models', 'created_by'),
    ('scenario_projects', 'project_id'),
    ('sd_ai_evaluation_runs', 'created_by_user_id'),
    ('sd_announcements', 'created_by'),
    ('sd_change_requests', 'implementer_id'),
    ('sd_change_requests', 'owner_id'),
    ('sd_change_requests', 'related_ticket_id'),
    ('sd_configuration_items', 'discovery_provider_id'),
    ('sd_configuration_items', 'owner_user_id'),
    ('sd_escalation_rules', 'group_id'),
    ('sd_escalation_rules', 'target_group_id'),
    ('sd_incident_to_problem', 'linked_by'),
    ('sd_jira_configs', 'created_by_user_id'),
    ('sd_kb_article_versions', 'changed_by_user_id'),
    ('sd_kb_articles', 'reviewer_id'),
    ('sd_kb_corrections', 'article_id'),
    ('sd_kb_corrections', 'created_by'),
    ('sd_kb_findings', 'article_id'),
    ('sd_kb_findings', 'closed_by'),
    ('sd_kb_findings', 'other_article_id'),
    ('sd_kb_gaps', 'article_id'),
    ('sd_kb_gaps', 'closed_by'),
    ('sd_kb_gaps', 'correction_id'),
    ('sd_known_error_tickets', 'incident_link_id'),
    ('sd_known_errors', 'kb_article_id'),
    ('sd_major_incidents', 'incident_commander_id'),
    ('sd_monitoring_alerts', 'ci_id'),
    ('sd_problems', 'ci_id'),
    ('sd_problems', 'owner_user_id'),
    ('sd_problems', 'rca_approved_by'),
    ('sd_releases', 'owner_id'),
    ('sd_service_items', 'category_id'),
    ('sd_sla_policies', 'calendar_id'),
    ('sd_ticket_approvals', 'decided_by_user_id'),
    ('sd_ticket_comments', 'author_user_id'),
    ('sd_ticket_events', 'actor_client_id'),
    ('sd_ticket_events', 'actor_user_id'),
    ('sd_ticket_history', 'changed_by_user_id'),
    ('sd_ticket_links', 'created_by'),
    ('sd_ticket_templates', 'category_id'),
    ('sd_ticket_templates', 'default_sla_id'),
    ('sd_ticket_time_logs', 'ticket_id'),
    ('sd_tickets', 'assigned_group_id'),
    ('sd_tickets', 'sla_policy_id'),
    ('sd_tickets', 'uc_contract_id'),
    ('sd_workflow_blueprint_versions', 'created_by_user_id'),
    ('sd_workflow_blueprints', 'created_by_user_id'),
    ('sd_workflow_runs', 'blueprint_version_id'),
    ('sd_workflow_runs', 'created_by_user_id'),
    ('security_detections', 'assigned_to'),
    ('security_incidents', 'lead_analyst'),
    ('sem_assignments', 'accepted_user_id'),
    ('sem_assignments', 'suggested_user_id'),
    ('sem_feedback', 'correct_user_id'),
    ('sem_feedback', 'corrected_by'),
    ('skill_history', 'recorded_by'),
    ('skill_history', 'skill_id'),
    ('sla_breach_logs', 'group_id'),
    ('sprint_plan_tasks', 'task_id'),
    ('sprint_plans', 'created_by'),
    ('sprint_retro_notes', 'facilitated_by_id'),
    ('sprints', 'created_by'),
    ('sso_configs', 'created_by'),
    ('subcontractor_assignments', 'rate_id'),
    ('subcontractor_invoices', 'assignment_id'),
    ('subcontractor_rates', 'subcontractor_id'),
    ('subcontractor_timelogs', 'invoice_id'),
    ('subcontractor_worker_skills', 'skill_id'),
    ('task_dependencies', 'created_by'),
    ('task_dependency_meta', 'created_by'),
    ('template_deliverables', 'template_id'),
    ('template_phases', 'template_id'),
    ('template_risks', 'template_id'),
    ('template_tasks', 'phase_id'),
    ('tenant_policy_packs', 'updated_by'),
    ('threaded_comments', 'created_by'),
    ('threaded_comments', 'parent_id'),
    ('timer_sessions', 'imputation_id'),
    ('timer_sessions', 'project_id'),
    ('timer_sessions', 'task_id'),
    ('uat_cases', 'assigned_to_id'),
    ('uat_issues', 'reported_by'),
    ('uat_issues', 'session_id'),
    ('uat_sessions', 'client_signed_by'),
    ('uat_sessions', 'deliverable_id'),
    ('uat_test_cases', 'session_id'),
    ('user_attributes', 'assigned_by'),
    ('user_cost_profiles', 'created_by_user_id'),
    ('user_vacation_balances', 'policy_id'),
    ('users', 'away_delegate_id'),
    ('vendor_scores', 'evaluator_id'),
    ('webhook_triggers', 'created_by'),
    ('webhook_triggers', 'rule_id'),
    ('webhook_triggers', 'workflow_id'),
    ('webhooks', 'created_by'),
    ('webhooks', 'project_id'),
    ('whatif_tasks', 'assigned_user_id'),
    ('whatif_tasks', 'task_id'),
    ('wiki_comments', 'created_by'),
    ('wiki_comments', 'parent_id'),
    ('wiki_export_jobs', 'created_by'),
    ('wiki_pages', 'created_by'),
    ('wiki_pages', 'updated_by'),
    ('wiki_spaces', 'created_by'),
    ('wiki_tags', 'created_by'),
    ('wiki_templates', 'created_by'),
    ('wiki_versions', 'created_by'),
    ('work_orders', 'project_id'),
    ('workflow_transitions', 'from_state_id'),
    ('workflow_transitions', 'to_state_id'),
]


def _nombre(tabla: str, columna: str) -> str:
    return f"ix_{tabla}_{columna}"[:63]


def _clave_ajena_del_cliente(bind) -> None:
    insp = sa.inspect(bind)
    if not {"budgets", "clients"} <= set(insp.get_table_names()):
        return
    if any(fk["constrained_columns"] == ["cliente_id"] for fk in insp.get_foreign_keys("budgets")):
        return
    bind.execute(sa.text(
        "UPDATE budgets SET cliente_id = NULL WHERE cliente_id IS NOT NULL "
        "AND cliente_id NOT IN (SELECT id FROM clients)"))
    if bind.dialect.name == "sqlite":
        # SQLite no altera restricciones: batch recrea la tabla con la clave.
        with op.batch_alter_table("budgets") as t:
            t.create_foreign_key(FK_CLIENTE, "clients", ["cliente_id"], ["id"], ondelete="SET NULL")
    else:
        op.create_foreign_key(FK_CLIENTE, "budgets", "clients", ["cliente_id"], ["id"], ondelete="SET NULL")


def upgrade() -> None:
    bind = op.get_bind()
    _clave_ajena_del_cliente(bind)

    insp = sa.inspect(bind)
    pg = bind.dialect.name == "postgresql"
    tablas = set(insp.get_table_names())
    columnas: dict[str, set[str]] = {}
    existentes: dict[str, set[str]] = {}
    with op.get_context().autocommit_block():
        for tabla, columna in INDICES_DE_PARIDAD + INDICES_DE_CLAVES_AJENAS:
            if tabla not in tablas:
                continue
            if tabla not in columnas:
                columnas[tabla] = {c["name"] for c in insp.get_columns(tabla)}
                existentes[tabla] = {i["name"] for i in insp.get_indexes(tabla)}
            if columna not in columnas[tabla]:
                continue
            nombre = _nombre(tabla, columna)
            if nombre in existentes[tabla]:
                continue
            concurrente = "CONCURRENTLY " if pg else ""
            op.execute(f'CREATE INDEX {concurrente}IF NOT EXISTS "{nombre}" ON "{tabla}" ("{columna}")')


def downgrade() -> None:
    bind = op.get_bind()
    pg = bind.dialect.name == "postgresql"
    with op.get_context().autocommit_block():
        for tabla, columna in INDICES_DE_PARIDAD + INDICES_DE_CLAVES_AJENAS:
            concurrente = "CONCURRENTLY " if pg else ""
            op.execute(f'DROP INDEX {concurrente}IF EXISTS "{_nombre(tabla, columna)}"')
    insp = sa.inspect(bind)
    if "budgets" in insp.get_table_names() and FK_CLIENTE in {fk["name"] for fk in insp.get_foreign_keys("budgets")}:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("budgets") as t:
                t.drop_constraint(FK_CLIENTE, type_="foreignkey")
        else:
            op.drop_constraint(FK_CLIENTE, "budgets", type_="foreignkey")
