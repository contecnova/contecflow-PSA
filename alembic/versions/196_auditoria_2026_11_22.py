"""Auditoría 22-11-2026: columnas pendientes, tablas sin uso y borrado de usuarios (23-11-2026).

Tres bloques, cada uno con su deshacer real:

1. Columnas que el código ya necesita (docs/auditoria/2026-11-22):
   - `collaboration_audit_events.hash_version` String(10) NOT NULL, por defecto
     'v1' (C5): las filas existentes se siguen verificando con el sha256 de
     siempre; las nuevas (`v2`) llevan HMAC con clave, actor, IP y fecha.
   - `client_documents.signed_pdf_sha256` String(64) (A17): huella del PDF
     firmado; la descarga la comprueba.
   - `collaboration_webhooks.secret_token_hash` String(64) (A23): la entrega
     busca por la huella del secreto. Se rellena aquí desde `secret_token`.
   - `automation_events.idempotency_key` String(64) con índice único por
     empresa `uq_automation_events_org_idempotency` (A58).
2. DROP de 6 tablas sin modelo ni uso (M-MOD3, M108): `ai_anomalies`,
   `oauth_states`, `subcontractor_worker_skills`, `imputation_snapshots`,
   `whatif_tasks`, `wiki_export_jobs`. Medido en la base local: 0 filas en las
   seis. El deshacer las recrea (vacías) con la forma que tenían en la 195.
3. `ondelete` en las 171 claves ajenas a `users.id` que no lo tenían:
   - SET NULL en las 159 columnas que admiten NULL;
   - RESTRICT en las 8 autorías obligatorias (aprobaciones, evaluaciones,
     votos del CAB, horas de ticket, planes de desarrollo, 360): borrar a la
     persona se rechaza y `user_service.delete_user_record` la anonimiza con
     la supresión RGPD en vez de borrarla;
   - CASCADE en 4 que son de la propia persona (ejecuciones de agente IA,
     comandos de voz, anomalías de acceso, atributos ABAC).
   PostgreSQL: se suelta y se vuelve a crear cada clave con su mismo nombre.
   SQLite no altera claves: `batch_alter_table(recreate="always")` por tabla
   afectada; sus claves no tienen nombre y el lote las nombra con
   `naming_convention` (`fk_<tabla>_<columna>_users`) para poder soltarlas.
   Alembic usa su propio motor, sin `PRAGMA foreign_keys=ON`: recrear una tabla
   no dispara los ON DELETE de sus hijas.

Idempotente: cada paso mira antes si ya está hecho.

Revision ID: 196_auditoria_2026_11_22
Revises: 195_flujo_de_demanda
"""
import hashlib
import logging

import sqlalchemy as sa
from alembic import op

revision = "196_auditoria_2026_11_22"
down_revision = "195_flujo_de_demanda"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

_TZ = sa.DateTime(timezone=True)
#: Nombre que reciben en el lote de SQLite las claves ajenas sin nombre.
CONVENCION = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
INDICE_IDEMPOTENCIA = "uq_automation_events_org_idempotency"

#: (tabla, columna, ondelete) de las claves ajenas a users.id.
CLAVES_A_USERS = (
    # RESTRICT
    ("approval_decisions", "approver_id", "RESTRICT"),
    ("approval_requests", "requested_by", "RESTRICT"),
    ("cab_votes", "voter_id", "RESTRICT"),
    ("development_plans", "subject_id", "RESTRICT"),
    ("performance_reviews", "reviewee_id", "RESTRICT"),
    ("performance_reviews", "reviewer_id", "RESTRICT"),
    ("review_360_campaigns", "subject_id", "RESTRICT"),
    ("sd_ticket_time_logs", "user_id", "RESTRICT"),
    # CASCADE
    ("ai_agent_executions", "user_id", "CASCADE"),
    ("ai_voice_commands", "user_id", "CASCADE"),
    ("login_anomalies", "user_id", "CASCADE"),
    ("user_attributes", "user_id", "CASCADE"),
    # SET NULL
    ("abac_attribute_definitions", "created_by", "SET NULL"),
    ("abac_policies", "created_by", "SET NULL"),
    ("absences", "approved_by", "SET NULL"),
    ("ai_action_logs", "user_id", "SET NULL"),
    ("ai_agent_executions", "approved_by", "SET NULL"),
    ("ai_contracts", "created_by", "SET NULL"),
    ("ai_governance_configs", "updated_by", "SET NULL"),
    ("ai_guardrail_audit_logs", "user_id", "SET NULL"),
    ("ai_guardrail_policies", "created_by", "SET NULL"),
    ("ai_kb_articles", "reviewed_by", "SET NULL"),
    ("ai_meeting_actions", "assignee_id", "SET NULL"),
    ("ai_meetings", "created_by", "SET NULL"),
    ("ai_predictions", "acknowledged_by", "SET NULL"),
    ("ai_prompt_templates", "created_by", "SET NULL"),
    ("ai_providers", "created_by", "SET NULL"),
    ("ai_ticket_triages", "suggested_agent_id", "SET NULL"),
    ("ai_ticket_triages", "accepted_by", "SET NULL"),
    ("alerts", "resolved_by", "SET NULL"),
    ("alm_asset_history", "changed_by", "SET NULL"),
    ("alm_contracts", "created_by", "SET NULL"),
    ("alm_renewal_alerts", "recipient_id", "SET NULL"),
    ("alm_software_installs", "installed_by", "SET NULL"),
    ("approval_decisions", "delegate_to", "SET NULL"),
    ("approval_steps", "approver_user_id", "SET NULL"),
    ("approval_steps", "escalate_to_user_id", "SET NULL"),
    ("areas", "manager_id", "SET NULL"),
    ("automation_rules", "created_by", "SET NULL"),
    ("automation_workflows", "created_by", "SET NULL"),
    ("bi_tokens", "created_by", "SET NULL"),
    ("bpmn_instance_steps", "completed_by_user_id", "SET NULL"),
    ("bpmn_instances", "started_by_user_id", "SET NULL"),
    ("bpmn_process_versions", "created_by_user_id", "SET NULL"),
    ("bpmn_processes", "created_by_user_id", "SET NULL"),
    ("budgets", "approved_by", "SET NULL"),
    ("budgets", "created_by", "SET NULL"),
    ("calendar_events", "user_id", "SET NULL"),
    ("capacity_plans", "created_by", "SET NULL"),
    ("change_requests", "requested_by", "SET NULL"),
    ("change_requests", "reviewed_by", "SET NULL"),
    ("change_requests", "approved_by", "SET NULL"),
    ("client_documents", "uploaded_by", "SET NULL"),
    ("client_messages", "sender_user_id", "SET NULL"),
    ("clients", "created_by", "SET NULL"),
    ("cmdb_changelog", "user_id", "SET NULL"),
    ("cmdb_discovery_providers", "created_by", "SET NULL"),
    ("contracts", "created_by", "SET NULL"),
    ("deliverables", "owner_id", "SET NULL"),
    ("departments", "manager_id", "SET NULL"),
    ("development_plans", "created_by", "SET NULL"),
    ("email_templates", "created_by", "SET NULL"),
    ("epic_dependency_meta", "created_by", "SET NULL"),
    ("epics", "created_by", "SET NULL"),
    ("expenses", "reviewed_by", "SET NULL"),
    ("gantt_baselines", "created_by", "SET NULL"),
    ("gdpr_requests", "subject_user_id", "SET NULL"),
    ("gdpr_requests", "requestor_id", "SET NULL"),
    ("gdpr_requests", "processed_by", "SET NULL"),
    ("grc_audit_log", "user_id", "SET NULL"),
    ("grc_role_permissions", "updated_by", "SET NULL"),
    ("grc_sod_rules", "created_by", "SET NULL"),
    ("grc_sod_violations", "user_id", "SET NULL"),
    ("import_jobs", "created_by", "SET NULL"),
    ("imputations", "approved_by", "SET NULL"),
    ("integration_configs", "created_by", "SET NULL"),
    ("integration_instances", "created_by", "SET NULL"),
    ("invoices", "created_by", "SET NULL"),
    ("maintenance_windows", "created_by", "SET NULL"),
    ("mentions", "mentioned_by", "SET NULL"),
    ("okr_checkins", "author_id", "SET NULL"),
    ("okr_key_results", "owner_id", "SET NULL"),
    ("okr_objectives", "owner_id", "SET NULL"),
    ("opportunities", "owner_id", "SET NULL"),
    ("opportunity_activities", "user_id", "SET NULL"),
    ("org_brandings", "created_by", "SET NULL"),
    ("pdf_export_jobs", "requested_by", "SET NULL"),
    ("policy_audit_log", "user_id", "SET NULL"),
    ("portal_conversation_audits", "actor_user_id", "SET NULL"),
    ("portal_conversation_messages", "sender_user_id", "SET NULL"),
    ("portal_conversation_participants", "user_id", "SET NULL"),
    ("portal_conversation_participants", "added_by_user_id", "SET NULL"),
    ("portal_conversation_policies", "approval_user_id", "SET NULL"),
    ("portal_conversations", "created_by_user_id", "SET NULL"),
    ("project_changelog_entries", "author_id", "SET NULL"),
    ("project_milestones", "completed_by", "SET NULL"),
    ("project_milestones", "approval_requested_by", "SET NULL"),
    ("project_milestones", "approved_by", "SET NULL"),
    ("project_milestones", "rejected_by", "SET NULL"),
    ("project_permissions", "granted_by", "SET NULL"),
    ("project_templates", "created_by", "SET NULL"),
    ("projects", "pm_id", "SET NULL"),
    ("projects", "created_by", "SET NULL"),
    ("recurring_invoices", "created_by", "SET NULL"),
    ("recurring_tasks", "created_by", "SET NULL"),
    ("report_definitions", "created_by", "SET NULL"),
    ("resource_bookings", "created_by", "SET NULL"),
    ("review_360_campaigns", "created_by", "SET NULL"),
    ("review_cycles", "created_by", "SET NULL"),
    ("risks", "owner_id", "SET NULL"),
    ("risks", "identified_by", "SET NULL"),
    ("saved_filters", "created_by", "SET NULL"),
    ("scenario_models", "created_by", "SET NULL"),
    ("sd_ai_evaluation_runs", "created_by_user_id", "SET NULL"),
    ("sd_announcements", "created_by", "SET NULL"),
    ("sd_canned_responses", "created_by", "SET NULL"),
    ("sd_change_requests", "requester_id", "SET NULL"),
    ("sd_change_requests", "owner_id", "SET NULL"),
    ("sd_change_requests", "approver_id", "SET NULL"),
    ("sd_change_requests", "approved_by", "SET NULL"),
    ("sd_configuration_items", "owner_user_id", "SET NULL"),
    ("sd_jira_configs", "created_by_user_id", "SET NULL"),
    ("sd_kb_article_versions", "changed_by_user_id", "SET NULL"),
    ("sd_kb_articles", "author_id", "SET NULL"),
    ("sd_kb_articles", "reviewer_id", "SET NULL"),
    ("sd_major_incidents", "incident_commander_id", "SET NULL"),
    ("sd_major_incidents", "communication_lead_id", "SET NULL"),
    ("sd_problems", "rca_approved_by", "SET NULL"),
    ("sd_problems", "owner_user_id", "SET NULL"),
    ("sd_service_items", "approval_user_id", "SET NULL"),
    ("sd_sla_events", "created_by", "SET NULL"),
    ("sd_ticket_comments", "author_user_id", "SET NULL"),
    ("sd_ticket_history", "changed_by_user_id", "SET NULL"),
    ("sd_ticket_links", "created_by", "SET NULL"),
    ("sd_ticket_merges", "merged_by_user", "SET NULL"),
    ("sd_ticket_templates", "auto_assign_to_id", "SET NULL"),
    ("sd_tickets", "requester_user_id", "SET NULL"),
    ("sd_tickets", "assigned_to_user_id", "SET NULL"),
    ("sd_tickets", "created_by_user_id", "SET NULL"),
    ("sd_workflow_blueprint_versions", "created_by_user_id", "SET NULL"),
    ("sd_workflow_blueprints", "created_by_user_id", "SET NULL"),
    ("security_detections", "user_id", "SET NULL"),
    ("security_detections", "assigned_to", "SET NULL"),
    ("security_events", "user_id", "SET NULL"),
    ("security_incidents", "lead_analyst", "SET NULL"),
    ("sem_assignments", "suggested_user_id", "SET NULL"),
    ("sem_assignments", "accepted_user_id", "SET NULL"),
    ("sem_feedback", "correct_user_id", "SET NULL"),
    ("sem_feedback", "corrected_by", "SET NULL"),
    ("skill_history", "recorded_by", "SET NULL"),
    ("sla_breach_logs", "agent_id", "SET NULL"),
    ("sprint_plans", "created_by", "SET NULL"),
    ("sprint_retro_notes", "facilitated_by_id", "SET NULL"),
    ("sprints", "created_by", "SET NULL"),
    ("sso_configs", "created_by", "SET NULL"),
    ("task_dependencies", "created_by", "SET NULL"),
    ("tasks", "created_by", "SET NULL"),
    ("threaded_comments", "created_by", "SET NULL"),
    ("timesheets", "reviewed_by", "SET NULL"),
    ("uat_cases", "assigned_to_id", "SET NULL"),
    ("user_attributes", "assigned_by", "SET NULL"),
    ("user_cost_profiles", "created_by_user_id", "SET NULL"),
    ("webhook_triggers", "created_by", "SET NULL"),
    ("webhooks", "created_by", "SET NULL"),
    ("wiki_comments", "created_by", "SET NULL"),
    ("wiki_pages", "created_by", "SET NULL"),
    ("wiki_pages", "updated_by", "SET NULL"),
    ("wiki_spaces", "created_by", "SET NULL"),
    ("wiki_tags", "created_by", "SET NULL"),
    ("wiki_templates", "created_by", "SET NULL"),
    ("wiki_versions", "created_by", "SET NULL"),
)


# ── Tablas que se retiran (forma que tenían en la 195) ───────────────────────

def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True)


def _creado():
    return sa.Column("created_at", _TZ, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True)


TABLAS_RETIRADAS = {
    "ai_anomalies": (lambda: [
        sa.Column("id", sa.String(36), primary_key=True), _org(),
        sa.Column("anomaly_type", sa.String(50), nullable=False), sa.Column("entity_type", sa.String(30)),
        sa.Column("entity_id", sa.String(36)), sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(20)), sa.Column("data_snapshot", sa.Text()),
        sa.Column("is_resolved", sa.Boolean()),
        sa.Column("resolved_by", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("resolved_at", _TZ), _creado()],
        [("ix_ai_anomalies_organization_id", ["organization_id"], False),
         ("ix_ai_anomalies_resolved_by", ["resolved_by"], False)]),
    "oauth_states": (lambda: [
        sa.Column("id", sa.String(36), primary_key=True), _org(),
        sa.Column("state", sa.String(255), nullable=False),
        sa.Column("sso_config_id", sa.String(36), sa.ForeignKey("sso_configs.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("redirect_to", sa.String(500)), _creado(),
        sa.Column("expires_at", _TZ, nullable=False), sa.Column("used", sa.Boolean())],
        [("ix_oauth_states_sso_config_id", ["sso_config_id"], False),
         ("ix_oauth_states_organization_id", ["organization_id"], False),
         ("ix_oauth_states_state", ["state"], True)]),
    "subcontractor_worker_skills": (lambda: [
        sa.Column("id", sa.String(36), primary_key=True), _org(),
        sa.Column("worker_id", sa.String(36), sa.ForeignKey("subcontractor_workers.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("skill_id", sa.String(36), sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sa.String(20), nullable=False), sa.Column("years_experience", sa.Float()),
        sa.Column("certified", sa.Boolean()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("cert_name", sa.String(255)), sa.Column("notes", sa.String(255)), _creado()],
        [("ix_subcontractor_worker_skills_organization_id", ["organization_id"], False),
         ("ix_subcontractor_worker_skills_worker_id", ["worker_id"], False),
         ("ix_subcontractor_worker_skills_skill_id", ["skill_id"], False)]),
    "imputation_snapshots": (lambda: [
        sa.Column("id", sa.String(36), primary_key=True), _org(),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False), sa.Column("total_hours", sa.Float()),
        sa.Column("billable_hours", sa.Float()), sa.Column("approved_hours", sa.Float()),
        sa.Column("is_complete", sa.Boolean()), _creado()],
        [("ix_imputation_snapshots_snapshot_date", ["snapshot_date"], False),
         ("ix_imputation_snapshots_organization_id", ["organization_id"], False),
         ("ix_imputation_snapshot_user_date", ["user_id", "snapshot_date"], False),
         ("ix_imputation_snapshots_user_id", ["user_id"], False)]),
    "whatif_tasks": (lambda: [
        sa.Column("id", sa.String(36), primary_key=True), _org(),
        sa.Column("scenario_id", sa.String(36), sa.ForeignKey("scenario_models.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id")),
        sa.Column("title", sa.String(255), nullable=False), sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()), sa.Column("estimated_hours", sa.Float()),
        sa.Column("assigned_user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("delta_days", sa.Integer()), sa.Column("delta_hours", sa.Float()), _creado()],
        [("ix_whatif_tasks_organization_id", ["organization_id"], False),
         ("ix_whatif_tasks_task_id", ["task_id"], False),
         ("ix_whatif_tasks_assigned_user_id", ["assigned_user_id"], False),
         ("ix_whatif_tasks_scenario_id", ["scenario_id"], False)]),
    "wiki_export_jobs": (lambda: [
        sa.Column("id", sa.String(36), primary_key=True), _org(),
        sa.Column("page_id", sa.String(36), sa.ForeignKey("wiki_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20)), sa.Column("file_path", sa.String(500)),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id")), _creado()],
        [("ix_wiki_export_jobs_organization_id", ["organization_id"], False),
         ("ix_wiki_export_jobs_page_id", ["page_id"], False),
         ("ix_wiki_export_jobs_created_by", ["created_by"], False)]),
}


# ── Ayudantes ────────────────────────────────────────────────────────────────

def _insp():
    return sa.inspect(op.get_bind())


def _columnas(tabla):
    insp = _insp()
    return {c["name"] for c in insp.get_columns(tabla)} if insp.has_table(tabla) else None


def _anadir(tabla, columna):
    cols = _columnas(tabla)
    if cols is not None and columna.name not in cols:
        op.add_column(tabla, columna)


def _quitar(tabla, nombre):
    cols = _columnas(tabla)
    if cols is not None and nombre in cols:
        with op.batch_alter_table(tabla) as lote:
            lote.drop_column(nombre)


def _indices(tabla):
    return {i["name"] for i in _insp().get_indexes(tabla)} if _columnas(tabla) is not None else set()


def _cambiar_claves(destino):
    """Deja cada clave (tabla, columna) -> users.id con el `ondelete` de `destino`."""
    bind = op.get_bind()
    pg = bind.dialect.name == "postgresql"
    insp = sa.inspect(bind)
    por_tabla = {}
    for tabla, columna, borrar in destino:
        por_tabla.setdefault(tabla, []).append((columna, borrar))
    for tabla, cols in sorted(por_tabla.items()):
        if not insp.has_table(tabla):
            log.info("196: %s no existe; se salta", tabla)
            continue
        claves = insp.get_foreign_keys(tabla)
        cambios = []
        for columna, borrar in cols:
            fk = next((f for f in claves if f["constrained_columns"] == [columna]
                       and f["referred_table"] == "users"), None)
            if fk is None:
                log.info("196: %s.%s no tiene clave a users; se salta", tabla, columna)
                continue
            actual = (fk.get("options") or {}).get("ondelete")
            if (actual or "").upper() == (borrar or "").upper():
                continue
            nombre = fk["name"] or CONVENCION["fk"] % {
                "table_name": tabla, "column_0_name": columna, "referred_table_name": "users"}
            cambios.append((columna, borrar, nombre))
        if not cambios:
            continue
        if pg:
            for columna, borrar, nombre in cambios:
                op.drop_constraint(nombre, tabla, type_="foreignkey")
                op.create_foreign_key(nombre, tabla, "users", [columna], ["id"], ondelete=borrar)
        else:
            with op.batch_alter_table(tabla, recreate="always", naming_convention=CONVENCION) as lote:
                for columna, borrar, nombre in cambios:
                    lote.drop_constraint(nombre, type_="foreignkey")
                    lote.create_foreign_key(nombre, "users", [columna], ["id"], ondelete=borrar)


# ── upgrade / downgrade ──────────────────────────────────────────────────────

def upgrade() -> None:
    bind = op.get_bind()
    # 1. Columnas.
    _anadir("collaboration_audit_events",
            sa.Column("hash_version", sa.String(10), nullable=False, server_default="v1"))
    _anadir("client_documents", sa.Column("signed_pdf_sha256", sa.String(64), nullable=True))
    _anadir("collaboration_webhooks", sa.Column("secret_token_hash", sa.String(64), nullable=True))
    _anadir("automation_events", sa.Column("idempotency_key", sa.String(64), nullable=True))
    if _columnas("automation_events") is not None and INDICE_IDEMPOTENCIA not in _indices("automation_events"):
        op.create_index(INDICE_IDEMPOTENCIA, "automation_events",
                        ["organization_id", "idempotency_key"], unique=True)
    if _columnas("collaboration_webhooks") is not None:
        filas = bind.execute(sa.text(
            "SELECT id, secret_token FROM collaboration_webhooks WHERE secret_token_hash IS NULL")).all()
        for id_, secreto in filas:
            bind.execute(sa.text("UPDATE collaboration_webhooks SET secret_token_hash = :h WHERE id = :id"),
                         {"h": hashlib.sha256((secreto or "").encode()).hexdigest(), "id": id_})

    # 2. Tablas sin uso.
    insp = _insp()
    for tabla in TABLAS_RETIRADAS:
        if insp.has_table(tabla):
            op.drop_table(tabla)

    # 3. ondelete en las claves a users.id.
    _cambiar_claves(CLAVES_A_USERS)


def downgrade() -> None:
    # 3. Las claves vuelven a no tener ondelete.
    _cambiar_claves([(t, c, None) for t, c, _ in CLAVES_A_USERS])

    # 2. Las tablas retiradas, vacías.
    insp = _insp()
    for tabla, (columnas, indices) in TABLAS_RETIRADAS.items():
        if insp.has_table(tabla):
            continue
        op.create_table(tabla, *columnas())
        for nombre, cols, unico in indices:
            op.create_index(nombre, tabla, cols, unique=unico)

    # 1. Columnas.
    if INDICE_IDEMPOTENCIA in _indices("automation_events"):
        op.drop_index(INDICE_IDEMPOTENCIA, table_name="automation_events")
    _quitar("automation_events", "idempotency_key")
    _quitar("collaboration_webhooks", "secret_token_hash")
    _quitar("client_documents", "signed_pdf_sha256")
    _quitar("collaboration_audit_events", "hash_version")
