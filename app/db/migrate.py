"""
Applies any missing column migrations to the existing SQLite database.
Safe to run multiple times — skips columns that already exist.
"""
import logging
from sqlalchemy import text, inspect
from app.db.session import engine
from app.db.base import Base
import re as _re

logger = logging.getLogger("contecflow.migrate")


def column_exists(table, column):
    insp = inspect(engine)
    return any(c['name'] == column for c in insp.get_columns(table))


MIGRATIONS = [
    # Core fields — projects
    ("projects",  "department",            "VARCHAR(100)"),
    ("projects",  "contract_amount",       "FLOAT"),
    ("projects",  "billing_type",          "VARCHAR(20) DEFAULT 'time_material'"),
    ("projects",  "billing_rate",          "FLOAT"),
    ("projects",  "client_name",           "VARCHAR(255)"),
    ("projects",  "end_date_real",         "DATE"),
    ("projects",  "end_date_planned",      "DATE"),
    ("projects",  "budget_hours",          "FLOAT"),
    ("projects",  "budget_amount",         "FLOAT"),
    ("projects",  "currency",              "VARCHAR(10) DEFAULT 'EUR'"),
    ("projects",  "pm_id",                 "VARCHAR(36)"),
    ("projects",  "is_billable",           "BOOLEAN DEFAULT 0"),
    ("projects",  "tags",                  "VARCHAR(500)"),
    ("projects",  "risk_level",            "VARCHAR(20) DEFAULT 'low'"),
    # Users
    ("users",     "hourly_rate",           "FLOAT"),
    ("users",     "weekly_capacity_hours", "FLOAT DEFAULT 40"),
    ("users",     "job_title",             "VARCHAR(100)"),
    ("users",     "status",                "VARCHAR(20) DEFAULT 'active'"),
    ("users",     "is_superadmin",         "BOOLEAN DEFAULT 0"),
    # Imputations
    ("imputations", "cost_amount",         "FLOAT"),
    ("imputations", "hourly_rate_snapshot","FLOAT"),
    ("imputations", "is_billable",         "BOOLEAN DEFAULT 0"),
    ("imputations", "approved_by",         "VARCHAR(36)"),
    ("imputations", "approved_at",         "DATETIME"),
    ("imputations", "is_approved",         "BOOLEAN DEFAULT 0"),
    # Tasks
    ("tasks", "blocked_reason",            "VARCHAR(255)"),
    ("tasks", "estimated_hours",           "FLOAT"),
    ("tasks", "completed_at",              "DATETIME"),
    ("tasks", "code",                      "VARCHAR(30)"),
    # Contracts
    ("contracts", "monthly_retainer",      "FLOAT"),
    ("contracts", "signed_date",           "DATE"),
    ("contracts", "payment_terms",         "VARCHAR(100)"),
    # Risks
    ("risks", "risk_score",                "FLOAT"),
    ("risks", "mitigation_plan",           "TEXT"),
    ("risks", "contingency_plan",          "TEXT"),
    ("risks", "response_type",             "VARCHAR(20)"),
    # Change requests
    ("change_requests", "cost_impact",     "FLOAT"),
    ("change_requests", "scope_impact",    "TEXT"),
    # v22 — Semantic Engine (nuevas tablas — se crean via Base.metadata.create_all)
    # sem_profiles, sem_embedding_cache, sem_assignments, sem_feedback, sem_config
    # No necesitan ALTER TABLE porque son tablas nuevas
    # v22 — Projects: client FK y project members
    ("projects", "client_id",              "VARCHAR(36)"),
    # v19 — Wiki pages visibility
    ("wiki_pages", "visibility",       "VARCHAR(20) DEFAULT 'team'"),

    # v22+ — Client entity hub: nuevas columnas en tablas existentes
    ("contracts",        "client_id",      "VARCHAR(36)"),
    ("opportunities",    "client_id",               "VARCHAR(36)"),
    # v_b7e2 — CRM / SOW Generator (Alembic b7e2c4a91f03)
    ("opportunities",    "hourly_rate",             "FLOAT"),
    ("opportunities",    "contract_type",           "VARCHAR(30)"),
    ("opportunities",    "proposal_template_id",    "VARCHAR(36)"),
    ("opportunities",    "proposal_content",        "TEXT"),
    ("opportunities",    "proposal_generated_at",   "DATETIME"),
    ("opportunities",    "proposal_sent_at",        "DATETIME"),
    ("invoices",         "client_id",               "VARCHAR(36)"),
    ("sd_tickets",       "client_id",      "VARCHAR(36)"),
    ("sd_tickets",       "linked_resource_type", "VARCHAR(50)"),
    ("sd_tickets",       "linked_resource_id",   "VARCHAR(36)"),
    ("client_users",     "client_org_id",  "VARCHAR(36)"),

    # client_portal_configs — nuevas columnas de configuración
    ("client_portal_configs", "default_language",   "VARCHAR(10) DEFAULT 'es'"),
    ("client_portal_configs", "allow_profile_edit", "BOOLEAN DEFAULT 1"),
    ("client_portal_configs", "allow_pwd_change",   "BOOLEAN DEFAULT 1"),
    ("client_portal_configs", "max_portal_users",   "INTEGER DEFAULT 10"),
    ("client_portal_configs", "max_open_tickets",   "INTEGER"),
    ("client_portal_configs", "sla_tier",           "VARCHAR(50)"),
    ("client_portal_configs", "logo_url",           "VARCHAR(500)"),
    ("client_portal_configs", "accent_color",       "VARCHAR(10)"),

    # v23 — Firma digital de documentos del portal
    ("client_documents", "signed_by_name",      "VARCHAR(255)"),
    ("client_documents", "signed_by_job_title",  "VARCHAR(255)"),
    ("client_documents", "signature_ip",         "VARCHAR(64)"),
    ("client_documents", "signed_pdf_path",      "VARCHAR(500)"),
    ("client_users",     "phone",          "VARCHAR(50)"),
    ("client_users",     "language",       "VARCHAR(10) DEFAULT 'es'"),

    # v24 — Flujo SOW Milestone Aprobación Factura
    ("project_milestones", "billing_status",         "VARCHAR(30) DEFAULT 'pending'"),
    ("project_milestones", "completed_by",            "VARCHAR(36)"),
    ("project_milestones", "approval_requested_at",   "DATETIME"),
    ("project_milestones", "approval_requested_by",   "VARCHAR(36)"),
    ("project_milestones", "approved_at",             "DATETIME"),
    ("project_milestones", "approved_by",             "VARCHAR(36)"),
    ("project_milestones", "rejected_at",             "DATETIME"),
    ("project_milestones", "rejected_by",             "VARCHAR(36)"),
    ("project_milestones", "rejection_reason",        "TEXT"),
    ("project_milestones", "invoice_id",              "VARCHAR(36)"),

    # v24 — Rate Cards
    ("rate_entries",       "escalation_pct",          "FLOAT DEFAULT 0.0"),
    ("rate_entries",       "notes",                   "VARCHAR(255)"),

    # v25 — SSO campos en User
    ("users", "sso_provider", "VARCHAR(30)"),
    ("users", "sso_subject",  "VARCHAR(255)"),
    ("users", "mfa_enabled",  "BOOLEAN DEFAULT FALSE"),
    ("users", "mfa_secret",   "VARCHAR(64)"),
    ("tasks", "start_date",   "DATE"),

    # v25 — Rev Rec método milestone_billing
    ("revenue_recognition_rules", "milestone_filter", "VARCHAR(50) DEFAULT 'approved'"),

    # v26 — Security hardening (P1-5: optimistic locking); users.refresh_token_jti dropped via Alembic 018
    ("projects", "version",           "INTEGER DEFAULT 1 NOT NULL"),
    ("tasks",    "version",           "INTEGER DEFAULT 1 NOT NULL"),

    # v26 — Alert deduplication key (P2-5)
    ("alerts", "dedup_key", "VARCHAR(200)"),

    # v27 — Timer session tracking on imputations
    ("imputations", "timer_session_id", "VARCHAR(36)"),

    # v24 — Invoicing state on imputations (Alembic: 024_imputation_is_invoiced)
    ("imputations", "is_invoiced",         "BOOLEAN NOT NULL DEFAULT 0"),
    ("imputations", "invoiced_invoice_id", "VARCHAR(36)"),

    # v28 — KB article vector embeddings (RAG vectorial)
    ("ai_kb_articles", "embedding", "TEXT"),

    # v30 - financial audit segregation and persisted SLA metrics
    ("sd_tickets", "first_response_minutes", "INTEGER"),
    ("sd_tickets", "resolution_minutes", "INTEGER"),
    ("sd_tickets", "sla_response_breached", "BOOLEAN DEFAULT 0"),
    ("sd_tickets", "sla_resolution_breached", "BOOLEAN DEFAULT 0"),

    # v31 — Governed portal conversations
    ("portal_conversations", "source", "VARCHAR(30) DEFAULT 'native'"),
    ("portal_conversations", "legacy_thread_id", "VARCHAR(36)"),
    ("portal_conversations", "policy_id", "VARCHAR(36)"),
    ("portal_conversations", "assigned_group_id", "VARCHAR(36)"),
    ("portal_conversations", "assigned_role_key", "VARCHAR(50)"),
    ("portal_conversations", "first_response_due_at", "DATETIME"),
    ("portal_conversations", "first_response_at", "DATETIME"),
    ("portal_conversations", "escalated_at", "DATETIME"),
    ("portal_conversation_messages", "legacy_message_id", "VARCHAR(36)"),
    ("portal_conversation_messages", "approval_request_id", "VARCHAR(36)"),
    ("portal_conversation_messages", "raw_body", "TEXT"),
    ("portal_conversation_messages", "moderation_notes", "TEXT"),
    ("portal_conversation_messages", "is_redacted", "BOOLEAN DEFAULT 0"),

    # v26 — Document access audit trail (P2-6)
    # (document_access_logs is a new table — created via Base.metadata.create_all)
]




def table_exists(name):
    insp = inspect(engine)
    return name in insp.get_table_names()


ALLOWED_TABLES = set(
    [t[0] for t in MIGRATIONS] +
    ["financial_approval_audit_logs", "portal_conversation_policies"] +
    ["document_access_logs"]
)


def validate_table_name(table_name: str) -> str:
    """Valida que el nombre de tabla esté en la whitelist (previene SQL injection)."""
    if table_name not in ALLOWED_TABLES:
        raise ValueError(f"Table '{table_name}' not whitelisted for migration")
    return table_name


_COL_NAME_RE = _re.compile(r'^[a-z_][a-z0-9_]*$')
_COL_DEF_RE  = _re.compile(r'^[A-Z][A-Z0-9_(). ,\']*$', _re.IGNORECASE)


def validate_column_name(col: str) -> str:
    """Whitelist column name: lowercase letters, digits, underscores."""
    if not _COL_NAME_RE.match(col):
        raise ValueError(f"Column name '{col}' contains invalid characters")
    return col


def validate_column_def(defn: str) -> str:
    """Whitelist column definition: only safe SQL type characters."""
    if not _COL_DEF_RE.match(defn):
        raise ValueError(f"Column definition '{defn}' contains invalid characters")
    return defn


def run():

    logger.info("🔧 Aplicando migraciones de base de datos...")
    # Crear tablas nuevas que aún no existen
    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        for table, column, definition in MIGRATIONS:
            try:
                # Validar nombre de tabla
                table_safe = validate_table_name(table)
                column_safe = validate_column_name(column)
                definition_safe = validate_column_def(definition)
                insp = inspect(engine)
                tables = insp.get_table_names()
                if table_safe not in tables:
                    continue
                if column_exists(table_safe, column_safe):
                    continue
                conn.execute(text(f"ALTER TABLE {table_safe} ADD COLUMN {column_safe} {definition_safe}"))
                conn.commit()
                logger.info("  ✅ %s.%s añadida", table_safe, column_safe)
            except Exception as e:
                if "duplicate column" not in str(e).lower():
                    logger.error("Migration %s.%s failed: %s", table, column, e, exc_info=True)

    logger.info("✅ Migraciones completadas")


if __name__ == "__main__":
    run()
