"""OLAP star-schema DDL for DuckDB.

Tables:
  Dimensions: dim_date, dim_project, dim_user, dim_client, dim_organization
  Facts:      fact_imputations, fact_projects, fact_pipeline, fact_tickets
"""

CREATE_SCHEMA_SQL = """
-- ── Dimensions ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS dim_date (
    date_key        INTEGER PRIMARY KEY,   -- YYYYMMDD
    date            DATE NOT NULL,
    year            INTEGER,
    quarter         INTEGER,
    month           INTEGER,
    month_name      VARCHAR,
    week            INTEGER,
    day_of_week     INTEGER,
    is_weekend      BOOLEAN,
    yyyymm          VARCHAR(7)             -- e.g. '2025-04'
);

CREATE TABLE IF NOT EXISTS dim_project (
    project_id      VARCHAR PRIMARY KEY,
    code            VARCHAR,
    name            VARCHAR,
    status          VARCHAR,
    project_type    VARCHAR,
    billing_type    VARCHAR,
    organization_id VARCHAR,
    client_id       VARCHAR,
    start_date      DATE,
    end_date        DATE,
    budget          DOUBLE,
    currency        VARCHAR
);

CREATE TABLE IF NOT EXISTS dim_user (
    user_id         VARCHAR PRIMARY KEY,
    full_name       VARCHAR,
    email           VARCHAR,
    role            VARCHAR,
    department      VARCHAR,
    organization_id VARCHAR,
    cost_per_hour   DOUBLE,
    weekly_capacity DOUBLE
);

CREATE TABLE IF NOT EXISTS dim_client (
    client_id       VARCHAR PRIMARY KEY,
    name            VARCHAR,
    industry        VARCHAR,
    organization_id VARCHAR
);

CREATE TABLE IF NOT EXISTS dim_organization (
    organization_id VARCHAR PRIMARY KEY,
    name            VARCHAR,
    plan            VARCHAR
);

-- ── Facts ─────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fact_imputations (
    imputation_id   VARCHAR PRIMARY KEY,
    date_key        INTEGER,
    project_id      VARCHAR,
    user_id         VARCHAR,
    organization_id VARCHAR,
    hours           DOUBLE,
    billable_hours  DOUBLE,
    cost            DOUBLE,
    is_billable     BOOLEAN,
    task_id         VARCHAR
);

CREATE TABLE IF NOT EXISTS fact_projects (
    project_id      VARCHAR PRIMARY KEY,
    organization_id VARCHAR,
    start_date_key  INTEGER,
    end_date_key    INTEGER,
    budget          DOUBLE,
    total_hours     DOUBLE,
    total_cost      DOUBLE,
    revenue         DOUBLE,
    margin          DOUBLE,
    margin_pct      DOUBLE,
    tasks_total     INTEGER,
    tasks_done      INTEGER,
    milestones_total INTEGER,
    milestones_done  INTEGER,
    risk_level      VARCHAR,
    status          VARCHAR
);

CREATE TABLE IF NOT EXISTS fact_pipeline (
    opportunity_id  VARCHAR PRIMARY KEY,
    organization_id VARCHAR,
    stage           VARCHAR,
    expected_revenue DOUBLE,
    probability     DOUBLE,
    weighted_revenue DOUBLE,
    expected_close_key INTEGER,
    created_date_key   INTEGER,
    client_id       VARCHAR,
    owner_id        VARCHAR,
    contract_type   VARCHAR,
    is_won          BOOLEAN,
    is_lost         BOOLEAN,
    days_in_pipeline INTEGER
);

CREATE TABLE IF NOT EXISTS fact_tickets (
    ticket_id       VARCHAR PRIMARY KEY,
    organization_id VARCHAR,
    created_date_key INTEGER,
    closed_date_key  INTEGER,
    status          VARCHAR,
    priority        VARCHAR,
    ticket_type     VARCHAR,
    category_id     VARCHAR,
    agent_id        VARCHAR,
    client_id       VARCHAR,
    resolution_hours DOUBLE,
    sla_breached    BOOLEAN,
    satisfaction    INTEGER
);

-- Revisión 2026-11: cada carga deja su resultado (antes un fallo sólo iba al log).
CREATE TABLE IF NOT EXISTS etl_runs (
    run_at          TIMESTAMP,
    status          VARCHAR,
    detail          VARCHAR
);

-- ── Indexes for common query patterns ────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_fact_imp_date    ON fact_imputations(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_imp_proj    ON fact_imputations(project_id);
CREATE INDEX IF NOT EXISTS idx_fact_imp_user    ON fact_imputations(user_id);
CREATE INDEX IF NOT EXISTS idx_fact_imp_org     ON fact_imputations(organization_id);
CREATE INDEX IF NOT EXISTS idx_fact_proj_org    ON fact_projects(organization_id);
CREATE INDEX IF NOT EXISTS idx_fact_pipe_org    ON fact_pipeline(organization_id);
CREATE INDEX IF NOT EXISTS idx_fact_pipe_stage  ON fact_pipeline(stage);
CREATE INDEX IF NOT EXISTS idx_fact_tick_org    ON fact_tickets(organization_id);
CREATE INDEX IF NOT EXISTS idx_fact_tick_date   ON fact_tickets(created_date_key);
"""


def initialize_schema(conn) -> None:
    """Execute CREATE TABLE / INDEX statements on an open DuckDB connection."""
    conn.execute(CREATE_SCHEMA_SQL)
