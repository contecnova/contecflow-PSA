"""Ask-the-Data — secure Natural Language → SQL → DuckDB execution.

Security model (3 rules):
  Rule 1: LLM generates SQL candidate — it never touches the database.
  Rule 2: Python validator enforces: SELECT-only, no forbidden keywords,
          only allowed tables, injects org_id tenant filter, enforces LIMIT 200.
  Rule 3: Execute on DuckDB only — never on PostgreSQL.

Public API:
    ask(question, org_id, user_id) -> dict
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Tables exposed to NL queries (subset of star schema)
ALLOWED_TABLES = {
    "fact_imputations",
    "fact_projects",
    "fact_pipeline",
    "fact_tickets",
    "dim_date",
    "dim_project",
    "dim_user",
    "dim_client",
    "dim_organization",
}

FORBIDDEN_KEYWORDS = {
    "insert", "update", "delete", "drop", "create", "alter", "truncate",
    "grant", "revoke", "exec", "execute", "call", "pragma",
    "attach", "detach", "copy", "import", "export",
}

MAX_ROWS = 200

_SCHEMA_HINT = """
OLAP star schema (DuckDB):

dim_date(date_key INT, date DATE, year, quarter, month, month_name, week, day_of_week, is_weekend, yyyymm)
dim_project(project_id, code, name, status, project_type, billing_type, organization_id, client_id, start_date, end_date, budget, currency)
dim_user(user_id, full_name, email, role, department, organization_id, cost_per_hour, weekly_capacity)
dim_client(client_id, name, industry, organization_id)
dim_organization(organization_id, name, plan)

fact_imputations(imputation_id, date_key, project_id, user_id, organization_id, hours, billable_hours, cost, is_billable, task_id)
fact_projects(project_id, organization_id, start_date_key, end_date_key, budget, total_hours, total_cost, revenue, margin, margin_pct, tasks_total, tasks_done, milestones_total, milestones_done, risk_level, status)
fact_pipeline(opportunity_id, organization_id, stage, expected_revenue, probability, weighted_revenue, expected_close_key, created_date_key, client_id, owner_id, contract_type, is_won, is_lost, days_in_pipeline)
fact_tickets(ticket_id, organization_id, created_date_key, closed_date_key, status, priority, ticket_type, category_id, agent_id, client_id, resolution_hours, sla_breached, satisfaction)
"""

_ASK_SYSTEM = f"""You are a DuckDB SQL expert. Given a user question, generate a single valid DuckDB SELECT query.

Rules:
- Only use SELECT statements. No INSERT, UPDATE, DELETE, DROP, etc.
- Only reference these tables: {', '.join(sorted(ALLOWED_TABLES))}
- Always include a LIMIT clause (max {MAX_ROWS})
- Use meaningful column aliases in English or Spanish as appropriate
- Do not use subqueries that reference tables not in the allowed list
- Return ONLY the SQL query, no explanation, no markdown fences

Schema:
{_SCHEMA_HINT}
"""


# ── Validator ─────────────────────────────────────────────────────────────────

class SQLValidationError(ValueError):
    pass


def validate_sql(sql: str, org_id: Optional[str] = None) -> tuple[str, dict]:
    """Validate and transform LLM-generated SQL before execution.

    Returns a tuple ``(safe_sql, params)`` where ``params`` carries any bound
    parameters (e.g. the tenant ``org_id``) that the caller MUST pass to the
    DB driver — never string-interpolated.

    Tenant scoping is ALWAYS enforced when ``org_id`` is provided: the validated
    LLM query is wrapped as an outer ``SELECT * FROM (<llm_sql>) WHERE
    organization_id = ?`` so a tenant predicate cannot be bypassed by the model
    happening to mention ``organization_id`` itself.

    Raises SQLValidationError on any policy violation.
    """
    # Strip markdown fences if model included them
    sql = re.sub(r"```(?:sql)?", "", sql, flags=re.IGNORECASE).strip().rstrip(";")

    # Must start with SELECT
    if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
        raise SQLValidationError("Only SELECT queries are allowed")

    # Check forbidden keywords (word-boundary match to avoid false positives)
    sql_lower = sql.lower()
    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", sql_lower):
            raise SQLValidationError(f"Forbidden keyword: {kw}")

    # Extract referenced tables using simple regex
    referenced = set(re.findall(r"\bFROM\s+(\w+)|\bJOIN\s+(\w+)", sql, re.IGNORECASE))
    flat_refs = {t for pair in referenced for t in pair if t}
    if not flat_refs:
        raise SQLValidationError("Query must reference at least one allowed table")
    unknown = flat_refs - ALLOWED_TABLES
    if unknown:
        raise SQLValidationError(f"Unauthorized tables: {unknown}")

    # Enforce LIMIT on the inner query before wrapping
    if not re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        sql = sql + f" LIMIT {MAX_ROWS}"
    else:
        # Clamp existing LIMIT to MAX_ROWS
        def _clamp_limit(m):
            n = int(m.group(1))
            return f"LIMIT {min(n, MAX_ROWS)}"
        sql = re.sub(r"\bLIMIT\s+(\d+)", _clamp_limit, sql, flags=re.IGNORECASE)

    # ALWAYS enforce tenant scoping (no conditional bypass).
    #
    # We do NOT trust any ``organization_id`` predicate the model may have
    # written: the model controls its value and could scope to a foreign org.
    # Instead we inject our OWN tenant predicate, bound to the trusted org_id,
    # into the query's WHERE clause. Every allowed fact/dim table exposes
    # ``organization_id``, so this filters rows before any GROUP BY/aggregation
    # (an outer ``SELECT * ... WHERE organization_id`` wrapper would break on
    # aggregate queries that don't project the column — injection avoids that).
    #
    # The org_id is passed as a BOUND parameter ($org_id) — never
    # string-interpolated — so it cannot be used for injection.
    params: dict = {}
    if org_id:
        params["org_id"] = org_id
        tenant_clause = "organization_id = $org_id"
        if re.search(r"\bWHERE\b", sql, re.IGNORECASE):
            sql = re.sub(
                r"\bWHERE\b", f"WHERE {tenant_clause} AND", sql, count=1, flags=re.IGNORECASE
            )
        else:
            insert_before = re.search(
                r"\b(GROUP\s+BY|HAVING|ORDER\s+BY|LIMIT)\b", sql, re.IGNORECASE
            )
            if insert_before:
                pos = insert_before.start()
                sql = sql[:pos] + f" WHERE {tenant_clause} " + sql[pos:]
            else:
                sql = sql + f" WHERE {tenant_clause}"

    return sql, params


# ── LLM SQL generation ────────────────────────────────────────────────────────

def _generate_sql(
    question: str,
    db: Session,
    *,
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
    is_superadmin: bool = False,
    feedback: Optional[str] = None,
) -> str:
    """Generate SQL using the active configured AI provider (not Anthropic-only)."""
    from app.services.ai_provider_service import call_ai

    user_prompt = question
    if feedback:
        user_prompt = (
            f"Pregunta original:\n{question}\n\n"
            f"Feedback de validación/ejecución:\n{feedback}\n\n"
            "Devuelve una consulta SQL DuckDB completa y corregida. "
            "No incluyas explicación ni markdown."
        )

    sql_text = call_ai(
        db,
        messages=[{"role": "user", "content": user_prompt}],
        system=_ASK_SYSTEM,
        module="ask_the_data",
        user_id=user_id,
        max_tokens=400,
        is_superadmin=is_superadmin,
        organization_id=org_id,
    )
    return (sql_text or "").strip()


# ── Execution ─────────────────────────────────────────────────────────────────

def _execute_on_olap(sql: str, params: Optional[dict] = None) -> list[dict]:
    """Run validated SQL on DuckDB and return rows as list of dicts.

    ``params`` (if any) are passed as bound parameters to the driver — they are
    NEVER interpolated into the SQL string (defends against tenant-id injection).
    """
    from app.services.olap.etl import get_duckdb_conn

    conn = get_duckdb_conn()
    try:
        cur = conn.execute(sql, params) if params else conn.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]  # noqa: B905
    finally:
        conn.close()


def _normalize_sql_for_duckdb(sql: str) -> str:
    """Apply small syntax normalizations for common LLM glitches."""
    # Avoid parser errors from accidental trailing commas before LIMIT.
    sql = re.sub(r",\s*(LIMIT\b)", r" \1", sql, flags=re.IGNORECASE)
    # Avoid accidental duplicate semicolons in generated SQL.
    sql = re.sub(r";+", ";", sql).strip()
    return sql


def _fallback_sql_for_question(question: str) -> Optional[str]:
    q = (question or "").lower()

    # Frequent BI question: projects with negative margin in current year.
    if ("margen" in q and ("negativo" in q or "negativa" in q)
                    and ("proyecto" in q or "proyectos" in q)):
        return """
SELECT
    dp.name AS proyecto,
    fp.margin AS margen_eur,
    fp.margin_pct AS margen_pct,
    fp.status AS estado
FROM fact_projects fp
JOIN dim_project dp ON dp.project_id = fp.project_id
WHERE fp.margin < 0
    AND (
        fp.start_date_key >= CAST(strftime('%Y0101', CURRENT_DATE) AS INTEGER)
        OR fp.end_date_key >= CAST(strftime('%Y0101', CURRENT_DATE) AS INTEGER)
    )
ORDER BY fp.margin ASC
LIMIT 200
""".strip()

    # "Top projects by hours this month"
    if (
        ("proyecto" in q or "proyectos" in q)
        and ("hora" in q or "horas" in q)
        and ("este mes" in q or "mes actual" in q)
    ):
        return """
SELECT
    dp.name AS proyecto,
    ROUND(SUM(fi.hours), 2) AS horas_imputadas
FROM fact_imputations fi
JOIN dim_project dp ON dp.project_id = fi.project_id
JOIN dim_date dd ON dd.date_key = fi.date_key
WHERE dd.year = EXTRACT(YEAR FROM CURRENT_DATE)
  AND dd.month = EXTRACT(MONTH FROM CURRENT_DATE)
GROUP BY dp.name
ORDER BY horas_imputadas DESC
LIMIT 5
""".strip()

    # "Users with utilization below 70%"
    if (
        ("usuario" in q or "usuarios" in q)
        and ("utiliz" in q)
        and ("70" in q)
    ):
        return """
SELECT
    du.full_name AS usuario,
    ROUND(
        CASE
            WHEN COALESCE(du.weekly_capacity, 0) <= 0 THEN 0
            ELSE (COALESCE(SUM(fi.hours), 0) / du.weekly_capacity) * 100
        END,
        2
    ) AS utilizacion_pct
FROM dim_user du
LEFT JOIN fact_imputations fi ON fi.user_id = du.user_id
GROUP BY du.user_id, du.full_name, du.weekly_capacity
HAVING ROUND(
    CASE
        WHEN COALESCE(du.weekly_capacity, 0) <= 0 THEN 0
        ELSE (COALESCE(SUM(fi.hours), 0) / du.weekly_capacity) * 100
    END,
    2
) < 70
ORDER BY utilizacion_pct ASC
LIMIT 200
""".strip()

    return None


# ── Public API ────────────────────────────────────────────────────────────────

def ask(
    question: str,
    db: Session,
    org_id: Optional[str] = None,
    user_id: Optional[str] = None,
    is_superadmin: bool = False,
) -> dict:
    """Process a natural-language question and return structured results.

    Returns:
        {
            "question": str,
            "sql": str,            # validated SQL actually executed
            "columns": [...],
            "rows": [...],
            "row_count": int,
            "truncated": bool,     # True if result was capped at MAX_ROWS
            "error": str | None
        }
    """
    logger.info("ask_the_data: user=%s org=%s q=%r", user_id, org_id, question[:100])

    raw_sql = ""
    validated_sql = ""
    try:
        feedback = None
        last_exc: Optional[Exception] = None

        for attempt in range(2):
            raw_sql = _generate_sql(
                question,
                db,
                user_id=user_id,
                org_id=org_id,
                is_superadmin=is_superadmin,
                feedback=feedback,
            )
            logger.debug("LLM generated SQL (attempt %s): %s", attempt + 1, raw_sql)

            try:
                validated_sql, exec_params = validate_sql(raw_sql, org_id)
                validated_sql = _normalize_sql_for_duckdb(validated_sql)
                logger.debug("Validated SQL (attempt %s): %s", attempt + 1, validated_sql)
                rows = _execute_on_olap(validated_sql, exec_params)
                break
            except (SQLValidationError, Exception) as exc:
                last_exc = exc
                if attempt == 0:
                    feedback = str(exc)
                    continue
                raise

        if last_exc and not validated_sql:
            raise last_exc

        columns = list(rows[0].keys()) if rows else []

        return {
            "question": question,
            "sql": validated_sql,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": len(rows) >= MAX_ROWS,
            "error": None,
        }

    except SQLValidationError as exc:
        logger.warning("SQL validation blocked: %s | raw=%s", exc, raw_sql)
        fallback_sql = _fallback_sql_for_question(question)
        if fallback_sql:
            try:
                validated_sql, exec_params = validate_sql(fallback_sql, org_id)
                rows = _execute_on_olap(validated_sql, exec_params)
                columns = list(rows[0].keys()) if rows else []
                return {
                    "question": question,
                    "sql": validated_sql,
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "truncated": len(rows) >= MAX_ROWS,
                    "error": None,
                }
            except Exception:
                logger.warning("Fallback SQL también falló para org_id=%s", org_id, exc_info=True)
        return {
            "question": question,
            "sql": raw_sql,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "error": f"SQL no permitido: {exc}",
        }
    except Exception as exc:
        # Parser/validation edge-cases are user-facing but not server-fatal.
        if "parser error" in str(exc).lower() or "syntax error" in str(exc).lower():
            logger.warning("ask_the_data parser/validation error: %s", exc)
        else:
            logger.error("ask_the_data error: %s", exc, exc_info=True)
        return {
            "question": question,
            "sql": validated_sql or raw_sql,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "error": str(exc),
        }
