"""Fix soft-delete uniqueness: partial unique indexes for departments, project/task statuses

Revision ID: 2f165b37fe82
Revises: 060_workflow_runtime
Create Date: 2026-05-09 08:43:33.502288

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '2f165b37fe82'
down_revision: Union[str, None] = '060_workflow_runtime'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old simple UNIQUE constraints on the main columns
    # (These will prevent creating new records with same name/value when old ones are soft-deleted)
    try:
        op.drop_constraint('sqlite_autoindex_custom_project_types_1', 'custom_project_types', type_='unique')
    except Exception:
        pass
    try:
        op.drop_constraint('sqlite_autoindex_custom_project_statuses_1', 'custom_project_statuses', type_='unique')
    except Exception:
        pass
    try:
        op.drop_constraint('sqlite_autoindex_custom_task_statuses_1', 'custom_task_statuses', type_='unique')
    except Exception:
        pass
    try:
        op.drop_constraint('sqlite_autoindex_departments_1', 'departments', type_='unique')
    except Exception:
        pass
    
    # Create new PARTIAL UNIQUE indices for soft-delete entities
    # Using literal SQL for SQLite WHERE clause
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_project_status_value_active 
        ON custom_project_statuses(value, is_active) 
        WHERE is_active = 1
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_project_type_value_active 
        ON custom_project_types(value, is_active) 
        WHERE is_active = 1
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_task_status_value_active 
        ON custom_task_statuses(value, is_active) 
        WHERE is_active = 1
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_department_name_active 
        ON departments(name, is_active) 
        WHERE is_active = 1
    """)


def downgrade() -> None:
    # Drop partial unique indices
    op.drop_index('uq_department_name_active', table_name='departments')
    op.drop_index('uq_task_status_value_active', table_name='custom_task_statuses')
    op.drop_index('uq_project_type_value_active', table_name='custom_project_types')
    op.drop_index('uq_project_status_value_active', table_name='custom_project_statuses')
    op.create_table('onboarding_states',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('user_id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('current_step', sa.INTEGER(), nullable=True),
    sa.Column('completed_steps', sa.TEXT(), nullable=True),
    sa.Column('is_complete', sa.BOOLEAN(), nullable=True),
    sa.Column('dismissed_at', sa.DATETIME(), nullable=True),
    sa.Column('started_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('completed_at', sa.DATETIME(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_onboarding_states_user_id', 'onboarding_states', ['user_id'], unique=False)
    op.create_table('webhook_triggers',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('organization_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('name', sa.VARCHAR(length=255), nullable=False),
    sa.Column('slug', sa.VARCHAR(length=100), nullable=False),
    sa.Column('slug_rotated_at', sa.DATETIME(), nullable=True),
    sa.Column('slug_expires_at', sa.DATETIME(), nullable=True),
    sa.Column('secret', sa.VARCHAR(length=255), nullable=True),
    sa.Column('workflow_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('rule_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('is_active', sa.BOOLEAN(), nullable=True),
    sa.Column('last_fired_at', sa.DATETIME(), nullable=True),
    sa.Column('fire_count', sa.INTEGER(), nullable=True),
    sa.Column('field_mapping', sa.TEXT(), nullable=True),
    sa.Column('created_by', sa.VARCHAR(length=36), nullable=True),
    sa.Column('created_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['rule_id'], ['automation_rules.id'], ),
    sa.ForeignKeyConstraint(['workflow_id'], ['automation_workflows.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_webhook_triggers_slug', 'webhook_triggers', ['slug'], unique=False)
    op.create_index('ix_webhook_triggers_organization_id', 'webhook_triggers', ['organization_id'], unique=False)
    op.create_table('calendar_events',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('integration_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('external_id', sa.VARCHAR(length=255), nullable=True),
    sa.Column('user_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('title', sa.VARCHAR(length=500), nullable=False),
    sa.Column('start_dt', sa.DATETIME(), nullable=False),
    sa.Column('end_dt', sa.DATETIME(), nullable=False),
    sa.Column('all_day', sa.BOOLEAN(), nullable=True),
    sa.Column('description', sa.TEXT(), nullable=True),
    sa.Column('location', sa.VARCHAR(length=500), nullable=True),
    sa.Column('project_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('sprint_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('milestone_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('sync_direction', sa.VARCHAR(length=10), nullable=True),
    sa.Column('last_synced_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.ForeignKeyConstraint(['integration_id'], ['integration_configs.id'], ),
    sa.ForeignKeyConstraint(['milestone_id'], ['project_milestones.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['sprint_id'], ['sprints.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_calendar_events_user_id', 'calendar_events', ['user_id'], unique=False)
    op.create_index('ix_calendar_events_start_dt', 'calendar_events', ['start_dt'], unique=False)
    op.create_index('ix_calendar_events_external_id', 'calendar_events', ['external_id'], unique=False)
    op.create_table('automation_executions',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('rule_id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('trigger_context', sa.TEXT(), nullable=True),
    sa.Column('actions_taken', sa.TEXT(), nullable=True),
    sa.Column('success', sa.BOOLEAN(), nullable=True),
    sa.Column('error', sa.VARCHAR(length=500), nullable=True),
    sa.Column('executed_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.ForeignKeyConstraint(['rule_id'], ['automation_rules.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_automation_executions_rule_id', 'automation_executions', ['rule_id'], unique=False)
    op.create_table('integration_configs',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('organization_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('integration_type', sa.VARCHAR(length=15), nullable=False),
    sa.Column('name', sa.VARCHAR(length=255), nullable=False),
    sa.Column('is_active', sa.BOOLEAN(), nullable=True),
    sa.Column('access_token', sa.TEXT(), nullable=True),
    sa.Column('refresh_token', sa.TEXT(), nullable=True),
    sa.Column('token_expires_at', sa.DATETIME(), nullable=True),
    sa.Column('config', sa.TEXT(), nullable=True),
    sa.Column('last_sync_at', sa.DATETIME(), nullable=True),
    sa.Column('sync_errors', sa.INTEGER(), nullable=True),
    sa.Column('last_error', sa.VARCHAR(length=500), nullable=True),
    sa.Column('created_by', sa.VARCHAR(length=36), nullable=True),
    sa.Column('created_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DATETIME(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_integration_configs_organization_id', 'integration_configs', ['organization_id'], unique=False)
    op.create_index('ix_integration_configs_integration_type', 'integration_configs', ['integration_type'], unique=False)
    op.create_table('automation_rules',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('name', sa.VARCHAR(length=255), nullable=False),
    sa.Column('description', sa.VARCHAR(length=500), nullable=True),
    sa.Column('project_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('is_active', sa.BOOLEAN(), nullable=True),
    sa.Column('is_global', sa.BOOLEAN(), nullable=True),
    sa.Column('trigger_type', sa.VARCHAR(length=25), nullable=False),
    sa.Column('trigger_conditions', sa.TEXT(), nullable=True),
    sa.Column('actions', sa.TEXT(), nullable=False),
    sa.Column('run_count', sa.INTEGER(), nullable=True),
    sa.Column('last_run_at', sa.DATETIME(), nullable=True),
    sa.Column('last_error', sa.VARCHAR(length=500), nullable=True),
    sa.Column('created_by', sa.VARCHAR(length=36), nullable=True),
    sa.Column('created_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DATETIME(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_automation_rules_trigger_type', 'automation_rules', ['trigger_type'], unique=False)
    op.create_table('dashboard_widgets',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('user_id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('widget_type', sa.VARCHAR(length=50), nullable=False),
    sa.Column('title', sa.VARCHAR(length=255), nullable=True),
    sa.Column('position_x', sa.INTEGER(), nullable=True),
    sa.Column('position_y', sa.INTEGER(), nullable=True),
    sa.Column('width', sa.INTEGER(), nullable=True),
    sa.Column('height', sa.INTEGER(), nullable=True),
    sa.Column('config', sa.TEXT(), nullable=True),
    sa.Column('is_visible', sa.BOOLEAN(), nullable=True),
    sa.Column('created_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DATETIME(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_dashboard_widgets_user_id', 'dashboard_widgets', ['user_id'], unique=False)
    op.create_table('gdpr_requests',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('request_type', sa.VARCHAR(length=13), nullable=False),
    sa.Column('subject_user_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('subject_email', sa.VARCHAR(length=255), nullable=True),
    sa.Column('requestor_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('status', sa.VARCHAR(length=10), nullable=True),
    sa.Column('notes', sa.TEXT(), nullable=True),
    sa.Column('export_url', sa.VARCHAR(length=500), nullable=True),
    sa.Column('export_data', sa.TEXT(), nullable=True),
    sa.Column('deadline', sa.DATE(), nullable=True),
    sa.Column('completed_at', sa.DATETIME(), nullable=True),
    sa.Column('processed_by', sa.VARCHAR(length=36), nullable=True),
    sa.Column('created_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.ForeignKeyConstraint(['processed_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['requestor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['subject_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_gdpr_requests_subject_user_id', 'gdpr_requests', ['subject_user_id'], unique=False)
    op.create_index('ix_gdpr_requests_request_type', 'gdpr_requests', ['request_type'], unique=False)
    op.create_table('apscheduler_jobs',
    sa.Column('id', sa.VARCHAR(length=191), nullable=False),
    sa.Column('next_run_time', sa.FLOAT(), nullable=True),
    sa.Column('job_state', sa.BLOB(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_apscheduler_jobs_next_run_time', 'apscheduler_jobs', ['next_run_time'], unique=False)
    op.create_table('email_templates',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('organization_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('name', sa.VARCHAR(length=255), nullable=False),
    sa.Column('subject', sa.VARCHAR(length=500), nullable=False),
    sa.Column('body_html', sa.TEXT(), nullable=False),
    sa.Column('body_text', sa.TEXT(), nullable=True),
    sa.Column('category', sa.VARCHAR(length=50), nullable=True),
    sa.Column('variables', sa.TEXT(), nullable=True),
    sa.Column('is_system', sa.BOOLEAN(), nullable=True),
    sa.Column('created_by', sa.VARCHAR(length=36), nullable=True),
    sa.Column('created_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DATETIME(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_email_templates_organization_id', 'email_templates', ['organization_id'], unique=False)
    op.create_table('cab_votes',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('change_request_id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('voter_id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('vote', sa.VARCHAR(length=10), nullable=False),
    sa.Column('comment', sa.TEXT(), nullable=True),
    sa.Column('voted_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.ForeignKeyConstraint(['change_request_id'], ['change_requests.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['voter_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cab_votes_change_request_id', 'cab_votes', ['change_request_id'], unique=False)
    op.create_table('maintenance_windows',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('organization_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('name', sa.VARCHAR(length=255), nullable=False),
    sa.Column('description', sa.TEXT(), nullable=True),
    sa.Column('start_dt', sa.DATETIME(), nullable=False),
    sa.Column('end_dt', sa.DATETIME(), nullable=False),
    sa.Column('environment', sa.VARCHAR(length=50), nullable=True),
    sa.Column('is_recurring', sa.BOOLEAN(), nullable=True),
    sa.Column('recurrence', sa.VARCHAR(length=50), nullable=True),
    sa.Column('created_by', sa.VARCHAR(length=36), nullable=True),
    sa.Column('created_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_maintenance_windows_start_dt', 'maintenance_windows', ['start_dt'], unique=False)
    op.create_index('ix_maintenance_windows_organization_id', 'maintenance_windows', ['organization_id'], unique=False)
    op.create_table('email_logs',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('to_address', sa.VARCHAR(length=255), nullable=False),
    sa.Column('cc_addresses', sa.TEXT(), nullable=True),
    sa.Column('subject', sa.VARCHAR(length=500), nullable=False),
    sa.Column('template_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('body_preview', sa.VARCHAR(length=500), nullable=True),
    sa.Column('status', sa.VARCHAR(length=20), nullable=True),
    sa.Column('error', sa.VARCHAR(length=500), nullable=True),
    sa.Column('sent_at', sa.DATETIME(), nullable=True),
    sa.Column('opened_at', sa.DATETIME(), nullable=True),
    sa.Column('source', sa.VARCHAR(length=50), nullable=True),
    sa.Column('source_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('created_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.ForeignKeyConstraint(['template_id'], ['email_templates.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_email_logs_to_address', 'email_logs', ['to_address'], unique=False)
    op.create_table('commit_links',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('task_id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('integration_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('link_type', sa.VARCHAR(length=20), nullable=True),
    sa.Column('external_id', sa.VARCHAR(length=255), nullable=True),
    sa.Column('title', sa.VARCHAR(length=500), nullable=True),
    sa.Column('url', sa.VARCHAR(length=1000), nullable=True),
    sa.Column('author', sa.VARCHAR(length=255), nullable=True),
    sa.Column('state', sa.VARCHAR(length=20), nullable=True),
    sa.Column('created_at_ext', sa.DATETIME(), nullable=True),
    sa.Column('synced_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.ForeignKeyConstraint(['integration_id'], ['integration_configs.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_commit_links_task_id', 'commit_links', ['task_id'], unique=False)
    op.create_table('expenses',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('code', sa.VARCHAR(length=20), nullable=False),
    sa.Column('user_id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('project_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('contract_id', sa.VARCHAR(length=36), nullable=True),
    sa.Column('category', sa.VARCHAR(length=13), nullable=False),
    sa.Column('description', sa.VARCHAR(length=500), nullable=False),
    sa.Column('amount', sa.FLOAT(), nullable=False),
    sa.Column('currency', sa.VARCHAR(length=3), nullable=True),
    sa.Column('expense_date', sa.DATE(), nullable=False),
    sa.Column('is_billable', sa.BOOLEAN(), nullable=True),
    sa.Column('receipt_url', sa.VARCHAR(length=500), nullable=True),
    sa.Column('receipt_name', sa.VARCHAR(length=255), nullable=True),
    sa.Column('status', sa.VARCHAR(length=10), nullable=False),
    sa.Column('submitted_at', sa.DATETIME(), nullable=True),
    sa.Column('reviewed_by', sa.VARCHAR(length=36), nullable=True),
    sa.Column('reviewed_at', sa.DATETIME(), nullable=True),
    sa.Column('rejection_reason', sa.VARCHAR(length=500), nullable=True),
    sa.Column('reimbursed_at', sa.DATETIME(), nullable=True),
    sa.Column('notes', sa.TEXT(), nullable=True),
    sa.Column('created_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DATETIME(), nullable=True),
    sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_expenses_user_id', 'expenses', ['user_id'], unique=False)
    op.create_index('ix_expenses_status', 'expenses', ['status'], unique=False)
    op.create_index('ix_expenses_project_id', 'expenses', ['project_id'], unique=False)
    op.create_table('project_risk_scores',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('project_id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('computed_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('schedule_risk', sa.FLOAT(), nullable=True),
    sa.Column('budget_risk', sa.FLOAT(), nullable=True),
    sa.Column('resource_risk', sa.FLOAT(), nullable=True),
    sa.Column('scope_risk', sa.FLOAT(), nullable=True),
    sa.Column('overall_score', sa.FLOAT(), nullable=True),
    sa.Column('delay_probability_pct', sa.FLOAT(), nullable=True),
    sa.Column('predicted_delay_weeks', sa.FLOAT(), nullable=True),
    sa.Column('predicted_overrun_pct', sa.FLOAT(), nullable=True),
    sa.Column('pct_complete', sa.FLOAT(), nullable=True),
    sa.Column('days_elapsed_pct', sa.FLOAT(), nullable=True),
    sa.Column('budget_consumed_pct', sa.FLOAT(), nullable=True),
    sa.Column('open_risks_count', sa.INTEGER(), nullable=True),
    sa.Column('open_cr_count', sa.INTEGER(), nullable=True),
    sa.Column('overloaded_members', sa.INTEGER(), nullable=True),
    sa.Column('level', sa.VARCHAR(length=10), nullable=True),
    sa.Column('recommendation', sa.TEXT(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_project_risk_scores_project_id', 'project_risk_scores', ['project_id'], unique=False)
    op.create_index('ix_project_risk_scores_computed_at', 'project_risk_scores', ['computed_at'], unique=False)
    op.create_table('change_request_windows',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('change_request_id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('window_id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('rollback_plan', sa.TEXT(), nullable=True),
    sa.Column('test_plan', sa.TEXT(), nullable=True),
    sa.Column('created_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.ForeignKeyConstraint(['change_request_id'], ['change_requests.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['window_id'], ['maintenance_windows.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_change_request_windows_window_id', 'change_request_windows', ['window_id'], unique=False)
    op.create_index('ix_change_request_windows_change_request_id', 'change_request_windows', ['change_request_id'], unique=False)
    op.create_table('revenue_recognition_rules',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('project_id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('method', sa.VARCHAR(length=19), nullable=True),
    sa.Column('contract_value', sa.FLOAT(), nullable=True),
    sa.Column('start_date', sa.DATE(), nullable=True),
    sa.Column('end_date', sa.DATE(), nullable=True),
    sa.Column('notes', sa.TEXT(), nullable=True),
    sa.Column('created_by', sa.VARCHAR(length=36), nullable=True),
    sa.Column('created_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DATETIME(), nullable=True),
    sa.Column('milestone_filter', sa.VARCHAR(length=50), server_default=sa.text("'approved'"), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_revenue_recognition_rules_project_id', 'revenue_recognition_rules', ['project_id'], unique=False)
    op.create_table('webhook_trigger_logs',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('trigger_id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('payload', sa.TEXT(), nullable=True),
    sa.Column('headers', sa.TEXT(), nullable=True),
    sa.Column('status', sa.VARCHAR(length=20), nullable=True),
    sa.Column('error', sa.VARCHAR(length=500), nullable=True),
    sa.Column('received_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.ForeignKeyConstraint(['trigger_id'], ['webhook_triggers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_webhook_trigger_logs_trigger_id', 'webhook_trigger_logs', ['trigger_id'], unique=False)
    op.create_table('revenue_recognition_entries',
    sa.Column('id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('rule_id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('project_id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('period_date', sa.DATE(), nullable=False),
    sa.Column('pct_complete', sa.FLOAT(), nullable=True),
    sa.Column('amount_planned', sa.FLOAT(), nullable=True),
    sa.Column('amount_actual', sa.FLOAT(), nullable=True),
    sa.Column('amount_deferred', sa.FLOAT(), nullable=True),
    sa.Column('cumulative_pct', sa.FLOAT(), nullable=True),
    sa.Column('cumulative_amount', sa.FLOAT(), nullable=True),
    sa.Column('is_locked', sa.BOOLEAN(), nullable=True),
    sa.Column('notes', sa.TEXT(), nullable=True),
    sa.Column('created_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['rule_id'], ['revenue_recognition_rules.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_revenue_recognition_entries_rule_id', 'revenue_recognition_entries', ['rule_id'], unique=False)
    op.create_index('ix_revenue_recognition_entries_project_id', 'revenue_recognition_entries', ['project_id'], unique=False)
    op.create_index('ix_revenue_recognition_entries_period_date', 'revenue_recognition_entries', ['period_date'], unique=False)
    # ### end Alembic commands ###
