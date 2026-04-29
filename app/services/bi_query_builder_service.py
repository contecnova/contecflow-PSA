"""
bi_query_builder_service.py — Self-service visual query builder for BI.

Allows non-technical users to build analytic queries by composing:
  - Dataset selection (projects, tickets, timesheets, revenue, etc.)
  - Field/column selection with type info
  - Filters (field, operator, value)
  - Grouping and aggregations
  - Sort and limit

Query definitions are persisted as JSON in AppSetting.
Query execution uses safe, parameterized lookups against the OLAP layer or
raw metric aggregations — never arbitrary SQL.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting

_KEY_QUERIES = "bi.query_builder.saved"

AVAILABLE_DATASETS = {
    "projects": {
        "label": "Proyectos",
        "fields": [
            {"key": "name", "label": "Nombre", "type": "string"},
            {"key": "status", "label": "Estado", "type": "enum"},
            {"key": "budget_amount", "label": "Presupuesto", "type": "number"},
            {"key": "start_date", "label": "Fecha inicio", "type": "date"},
            {"key": "end_date_planned", "label": "Fecha fin", "type": "date"},
        ],
    },
    "tickets": {
        "label": "Tickets ITSM",
        "fields": [
            {"key": "title", "label": "Título", "type": "string"},
            {"key": "priority", "label": "Prioridad", "type": "enum"},
            {"key": "status", "label": "Estado", "type": "enum"},
            {"key": "ticket_type", "label": "Tipo", "type": "enum"},
            {"key": "created_at", "label": "Fecha creación", "type": "date"},
        ],
    },
    "timesheets": {
        "label": "Partes de horas",
        "fields": [
            {"key": "hours", "label": "Horas", "type": "number"},
            {"key": "date", "label": "Fecha", "type": "date"},
            {"key": "cost_amount", "label": "Coste", "type": "number"},
        ],
    },
    "revenue": {
        "label": "Ingresos",
        "fields": [
            {"key": "amount", "label": "Importe", "type": "number"},
            {"key": "month", "label": "Mes", "type": "date"},
            {"key": "client", "label": "Cliente", "type": "string"},
        ],
    },
    "resources": {
        "label": "Recursos",
        "fields": [
            {"key": "full_name", "label": "Nombre", "type": "string"},
            {"key": "role", "label": "Rol", "type": "enum"},
            {"key": "utilization_pct", "label": "Utilización %", "type": "number"},
        ],
    },
}

SUPPORTED_OPERATORS = {
    "string": ["eq", "neq", "contains", "starts_with"],
    "number": ["eq", "neq", "gt", "gte", "lt", "lte", "between"],
    "date": ["eq", "before", "after", "between"],
    "enum": ["eq", "neq", "in"],
}

SUPPORTED_AGGREGATIONS = ["count", "sum", "avg", "min", "max"]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_queries(db: Session, org_id: Optional[str]) -> dict:
    q = db.query(AppSetting).filter(AppSetting.key == _KEY_QUERIES)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except Exception:
        return {}


def _save_queries(db: Session, org_id: Optional[str], queries: dict) -> None:
    payload = json.dumps(queries, ensure_ascii=False)
    q = db.query(AppSetting).filter(AppSetting.key == _KEY_QUERIES)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row:
        row = AppSetting(key=_KEY_QUERIES, organization_id=org_id, value=payload, description="BI Query Builder: saved queries")
        db.add(row)
    else:
        row.value = payload
    db.commit()


def get_schema() -> dict:
    """Return available datasets, fields, operators and aggregations."""
    return {
        "datasets": AVAILABLE_DATASETS,
        "operators": SUPPORTED_OPERATORS,
        "aggregations": SUPPORTED_AGGREGATIONS,
    }


def save_query(
    db: Session,
    *,
    org_id: Optional[str],
    name: str,
    dataset: str,
    fields: list[str],
    filters: list[dict],
    group_by: list[str],
    aggregations: list[dict],
    sort_by: Optional[str],
    sort_dir: str,
    limit: int,
    created_by: str,
) -> dict:
    if dataset not in AVAILABLE_DATASETS:
        raise ValueError(f"Dataset '{dataset}' not found. Available: {list(AVAILABLE_DATASETS.keys())}")
    queries = _get_queries(db, org_id)
    qid = str(uuid.uuid4())
    entry = {
        "id": qid,
        "name": name,
        "dataset": dataset,
        "fields": fields,
        "filters": filters,
        "group_by": group_by,
        "aggregations": aggregations,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "limit": limit,
        "created_by": created_by,
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
    }
    queries[qid] = entry
    _save_queries(db, org_id, queries)
    return entry


def list_queries(db: Session, *, org_id: Optional[str]) -> list[dict]:
    return sorted(_get_queries(db, org_id).values(), key=lambda q: q["created_at"], reverse=True)


def delete_query(db: Session, *, org_id: Optional[str], query_id: str) -> None:
    queries = _get_queries(db, org_id)
    if query_id not in queries:
        raise ValueError(f"Query '{query_id}' not found")
    del queries[query_id]
    _save_queries(db, org_id, queries)


def execute_query(db: Session, *, org_id: Optional[str], query_id: str) -> dict[str, Any]:
    """
    Execute a saved query.
    Currently returns a metadata stub; full OLAP execution is wired
    through the OLAP service in bi_platform.
    """
    queries = _get_queries(db, org_id)
    if query_id not in queries:
        raise ValueError(f"Query '{query_id}' not found")
    q = queries[query_id]
    # Stub execution — real execution routes to OLAP/DuckDB layer
    return {
        "query_id": query_id,
        "dataset": q["dataset"],
        "fields": q["fields"],
        "executed_at": _iso_now(),
        "rows": [],
        "row_count": 0,
        "execution_ms": 0,
        "note": "Query execution stubbed; connect to OLAP service for live results",
    }
