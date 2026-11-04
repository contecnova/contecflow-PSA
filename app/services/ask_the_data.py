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


def _comprobar_politica(sql: str) -> None:
    """Rechaza la consulta si viola alguna regla de la política.

    Tres reglas, y las tres son de lista blanca o negra explícita: sólo SELECT,
    sin palabras prohibidas, y sólo tablas permitidas. Esto se aplica a SQL que
    **ha escrito un modelo de lenguaje** a partir de texto del usuario, así que
    la postura es «lo que no está permitido está prohibido».
    """
    if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
        raise SQLValidationError("Only SELECT queries are allowed")

    minuscula = sql.lower()
    for palabra in FORBIDDEN_KEYWORDS:
        # Con límite de palabra: si no, `delete` saltaría dentro de
        # `deleted_at`, que es un nombre de columna corriente.
        if re.search(rf"\b{palabra}\b", minuscula):
            raise SQLValidationError(f"Forbidden keyword: {palabra}")

    referencias = set(re.findall(r"\bFROM\s+(\w+)|\bJOIN\s+(\w+)", sql, re.IGNORECASE))
    tablas = {t for par in referencias for t in par if t}
    if not tablas:
        raise SQLValidationError("Query must reference at least one allowed table")
    desconocidas = tablas - ALLOWED_TABLES
    if desconocidas:
        raise SQLValidationError(f"Unauthorized tables: {desconocidas}")


def _acotar_limite(sql: str) -> str:
    """Garantiza un LIMIT y lo acota a `MAX_ROWS`.

    Si el modelo no puso ninguno se añade; si puso uno mayor, se baja. Sin esto
    una consulta sin límite puede traerse la tabla entera a memoria.
    """
    if not re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        return sql + f" LIMIT {MAX_ROWS}"
    return re.sub(
        r"\bLIMIT\s+(\d+)",
        lambda m: f"LIMIT {min(int(m.group(1)), MAX_ROWS)}",
        sql, flags=re.IGNORECASE,
    )


#: Tablas OLAP comunes a todas las organizaciones (sin columna organization_id).
_SIN_ORGANIZACION = {"dim_date"}

_NO_ES_ALIAS = {"where", "join", "on", "left", "right", "inner", "outer", "full", "cross", "group", "order",
               "limit", "having", "using", "natural", "union", "as"}


def _referencias_de_tabla(sql: str) -> list[str]:
    """El alias (o el nombre) de cada tabla de FROM/JOIN, en orden y sin repetir."""
    refs = []
    for m in re.finditer(r"\b(?:FROM|JOIN)\s+([A-Za-z_][\w.]*)(?:\s+(?:AS\s+)?([A-Za-z_]\w*))?", sql, re.IGNORECASE):
        tabla, alias = m.group(1), m.group(2)
        if tabla.lower() in _SIN_ORGANIZACION:
            continue
        ref = alias if alias and alias.lower() not in _NO_ES_ALIAS else tabla
        if ref not in refs:
            refs.append(ref)
    return refs


def _inyectar_filtro_de_tenant(sql: str) -> str:
    """Mete `organization_id = $org_id` en el WHERE de la consulta.

    **Se inyecta el nuestro y se ignora el que el modelo haya podido escribir**:
    el modelo controla ese valor y podría apuntar a otra organización.

    Se inyecta en el WHERE y no se envuelve la consulta en un
    `SELECT * FROM (...) WHERE ...` porque el envoltorio se rompe con las
    consultas agregadas, que no proyectan la columna. Inyectando, el filtro
    actúa antes del GROUP BY, que además es lo correcto.

    Tres sitios posibles, en orden: si hay WHERE se antepone la condición; si
    no, va justo antes de la primera cláusula que cierre el cuerpo (GROUP BY,
    HAVING, ORDER BY o LIMIT); y si no hay ninguna, al final.
    """
    # Auditoria 2026-11: con JOIN, `organization_id` sin calificar era ambiguo
    # (DuckDB: «Ambiguous reference») y fallaba toda consulta con dos tablas.
    # Ahora la condicion va por cada tabla, con su alias.
    refs = _referencias_de_tabla(sql)
    if not refs and re.search(r"\bFROM\b", sql, re.IGNORECASE):
        return sql  # solo tablas comunes (el calendario): nada que acotar
    clausula = " AND ".join(f"{ref}.organization_id = $org_id" for ref in refs) or "organization_id = $org_id"

    if re.search(r"\bWHERE\b", sql, re.IGNORECASE):
        return re.sub(r"\bWHERE\b", f"WHERE {clausula} AND", sql, count=1, flags=re.IGNORECASE)

    siguiente = re.search(r"\b(GROUP\s+BY|HAVING|ORDER\s+BY|LIMIT)\b", sql, re.IGNORECASE)
    if siguiente:
        return sql[:siguiente.start()] + f" WHERE {clausula} " + sql[siguiente.start():]
    return sql + f" WHERE {clausula}"


def validate_sql(sql: str, org_id: Optional[str] = None) -> tuple[str, dict]:
    """Valida y transforma el SQL generado por el modelo antes de ejecutarlo.

    Devuelve ``(sql_seguro, params)``, donde ``params`` trae los parámetros
    enlazados —entre ellos el ``org_id``— que quien llama **tiene que** pasar al
    driver: nunca interpolados en la cadena.

    El acotado por organización se aplica **siempre** que se pase ``org_id``.

    Levanta `SQLValidationError` ante cualquier violación de política.
    """
    # Los modelos suelen envolver el SQL en vallas de markdown.
    sql = re.sub(r"```(?:sql)?", "", sql, flags=re.IGNORECASE).strip().rstrip(";")

    _comprobar_politica(sql)
    sql = _acotar_limite(sql)

    if not org_id:
        return sql, {}
    return _inyectar_filtro_de_tenant(sql), {"org_id": org_id}


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
    from app.services.ai_provider_service import es_aviso_de_ia
    if es_aviso_de_ia(sql_text):
        # Auditoria 2026-11: el aviso acababa en el campo `sql` como si fuera SQL.
        raise RuntimeError(sql_text)
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
