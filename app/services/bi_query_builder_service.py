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
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.models.user import User
from app.services import report_builder_service

_KEY_QUERIES = "bi.query_builder.saved"

SUPPORTED_AGGREGATIONS = ["count", "sum", "avg", "min", "max"]

_DATASET_ALIASES = {
    "timesheets": "imputations",
    "revenue": "contracts",
    "resources": "users",
}

_OPERATOR_ALIASES = {
    "=": "eq",
    "!=": "neq",
    ">": "gt",
    ">=": "gte",
    "<": "lt",
    "<=": "lte",
}


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
    # intentional: best-effort fallback, log noise outweighs diagnostic value
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
    datasets = []
    for name, meta in report_builder_service.ENTITIES.items():
        fields = [
            {
                "name": key,
                "key": key,
                "label": col.get("label", key),
                "type": col.get("type", "str"),
            }
            for key, col in (meta.get("columns") or {}).items()
        ]
        datasets.append({"name": name, "label": meta.get("label", name), "fields": fields})
    return {
        "datasets": datasets,
        "operators": report_builder_service.OPERATORS,
        "groups": report_builder_service.GROUPS,
        "aggregations": SUPPORTED_AGGREGATIONS,
    }


def _normalize_filter_operator(operator: str) -> str:
    if operator in report_builder_service.OPERATORS:
        return operator
    return _OPERATOR_ALIASES.get(operator, operator)


def _resolve_dataset(dataset: str) -> str:
    return _DATASET_ALIASES.get(dataset, dataset)


def _normalize_filters(filters: list[dict]) -> list[dict]:
    normalized = []
    for item in filters or []:
        field = item.get("field")
        if not field:
            continue
        normalized.append(
            {
                "field": field,
                "column": field,
                "operator": _normalize_filter_operator(str(item.get("operator") or "eq")),
                "value": item.get("value"),
            }
        )
    return normalized


def _normalize_aggregations(aggregations: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for item in aggregations or []:
        field = str(item.get("field") or "").strip()
        func = str(item.get("func") or "").strip().lower()
        alias = str(item.get("alias") or "").strip()
        if not field or not func:
            continue
        if func not in SUPPORTED_AGGREGATIONS:
            raise ValueError(f"Unsupported aggregation function: {func}")
        normalized.append(
            {
                "field": field,
                "func": func,
                "alias": alias or f"{func}_{field}",
            }
        )
    return normalized


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except (TypeError, ValueError):
        return None


def _run_aggregation(values: list[Any], func: str) -> Any:
    if func == "count":
        return len([v for v in values if v is not None])

    nums = [n for n in (_as_float(v) for v in values) if n is not None]
    if not nums:
        return None
    if func == "sum":
        return round(sum(nums), 6)
    if func == "avg":
        return round(sum(nums) / len(nums), 6)
    if func == "min":
        return min(nums)
    if func == "max":
        return max(nums)
    raise ValueError(f"Unsupported aggregation function: {func}")


def _apply_grouping_and_aggregations(
    rows: list[dict],
    *,
    fields: list[str],
    group_by: list[str],
    aggregations: list[dict],
) -> tuple[list[dict], list[str]]:
    if not aggregations and not group_by:
        return rows, fields

    group_fields = [f for f in group_by if f in fields]
    if not group_fields and aggregations:
        # Global aggregation (single bucket)
        bucket_rows = rows
        out_row = {}
        for agg in aggregations:
            alias = agg["alias"]
            out_row[alias] = _run_aggregation([r.get(agg["field"]) for r in bucket_rows], agg["func"])
        out_columns = [agg["alias"] for agg in aggregations]
        return [out_row], out_columns

    if not aggregations:
        # Distinct projection by group_by keys
        seen = set()
        grouped_rows = []
        for row in rows:
            key = tuple(row.get(k) for k in group_fields)
            if key in seen:
                continue
            seen.add(key)
            grouped_rows.append({k: row.get(k) for k in group_fields})
        return grouped_rows, group_fields

    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        key = tuple(row.get(k) for k in group_fields)
        buckets[key].append(row)

    result_rows = []
    for key, bucket_rows in buckets.items():
        out_row = {group_fields[i]: key[i] for i in range(len(group_fields))}
        for agg in aggregations:
            alias = agg["alias"]
            out_row[alias] = _run_aggregation([r.get(agg["field"]) for r in bucket_rows], agg["func"])
        result_rows.append(out_row)

    out_columns = group_fields + [agg["alias"] for agg in aggregations]
    return result_rows, out_columns


def _safe_sort_rows(rows: list[dict], sort_by: Optional[str], sort_dir: str) -> list[dict]:
    if not sort_by:
        return rows

    reverse = str(sort_dir or "desc").lower() == "desc"

    def _key(row: dict):
        v = row.get(sort_by)
        return (v is None, str(v).lower() if isinstance(v, str) else v)

    try:
        return sorted(rows, key=_key, reverse=reverse)
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except Exception:
        return rows


def _validate_fields_against_dataset(dataset: str, fields: list[str]) -> None:
    entity = report_builder_service.ENTITIES.get(dataset, {})
    allowed_cols = set((entity.get("columns") or {}).keys())
    unknown = [f for f in fields if f not in allowed_cols]
    if unknown:
        raise ValueError(f"Unknown fields for dataset '{dataset}': {unknown}")


def _compute_query_result(
    db: Session,
    *,
    current_user: User,
    dataset: str,
    fields: list[str],
    filters: list[dict],
    group_by: list[str],
    aggregations: list[dict],
    sort_by: Optional[str],
    sort_dir: str,
    limit: int,
) -> dict[str, Any]:
    dataset = _resolve_dataset(dataset)
    if dataset not in report_builder_service.ENTITIES:
        raise ValueError(
            f"Dataset '{dataset}' not found. Available: {list(report_builder_service.ENTITIES.keys())}"
        )

    entity_cols = list((report_builder_service.ENTITIES.get(dataset, {}).get("columns") or {}).keys())
    selected_fields = fields or entity_cols
    _validate_fields_against_dataset(dataset, selected_fields)

    normalized_filters = _normalize_filters(filters)
    normalized_aggs = _normalize_aggregations(aggregations)
    normalized_group_by = [g for g in (group_by or []) if g]
    _validate_fields_against_dataset(dataset, normalized_group_by)
    _validate_fields_against_dataset(dataset, [a["field"] for a in normalized_aggs])

    # Fetch base rows from report builder engine (safe model-based query, no raw SQL).
    base_rows = report_builder_service.execute_report(
        dataset,
        selected_fields,
        filters=normalized_filters,
        sort_column=sort_by if sort_by in selected_fields else None,
        sort_direction=sort_dir,
        limit=5000,
        current_user=current_user,
        db=db,
    )

    processed_rows, result_columns = _apply_grouping_and_aggregations(
        base_rows,
        fields=selected_fields,
        group_by=normalized_group_by,
        aggregations=normalized_aggs,
    )

    processed_rows = _safe_sort_rows(processed_rows, sort_by, sort_dir)

    safe_limit = min(max(int(limit or 100), 1), 5000)
    final_rows = processed_rows[:safe_limit]

    return {
        "dataset": dataset,
        "fields": selected_fields,
        "columns": result_columns,
        "rows": final_rows,
        "row_count": len(final_rows),
        "total_before_limit": len(processed_rows),
        "truncated": len(processed_rows) > len(final_rows),
        "group_by": normalized_group_by,
        "aggregations": normalized_aggs,
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
    if dataset not in report_builder_service.ENTITIES:
        dataset = _resolve_dataset(dataset)
    if dataset not in report_builder_service.ENTITIES:
        raise ValueError(
            f"Dataset '{dataset}' not found. Available: {list(report_builder_service.ENTITIES.keys())}"
        )
    queries = _get_queries(db, org_id)
    qid = str(uuid.uuid4())
    entry = {
        "id": qid,
        "name": name,
        "dataset": dataset,
        "fields": fields,
        "filters": _normalize_filters(filters),
        "group_by": group_by,
        "aggregations": _normalize_aggregations(aggregations),
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


def execute_query(
    db: Session,
    *,
    org_id: Optional[str],
    query_id: str,
    current_user: User,
) -> dict[str, Any]:
    """
    Execute a saved query against Report Builder entities (no raw SQL).
    """
    queries = _get_queries(db, org_id)
    if query_id not in queries:
        raise ValueError(f"Query '{query_id}' not found")
    q = queries[query_id]
    result = _compute_query_result(
        db,
        current_user=current_user,
        dataset=q.get("dataset") or "",
        fields=q.get("fields") or [],
        filters=q.get("filters") or [],
        group_by=q.get("group_by") or [],
        aggregations=q.get("aggregations") or [],
        sort_by=q.get("sort_by"),
        sort_dir=q.get("sort_dir", "desc"),
        limit=q.get("limit") or 100,
    )

    return {
        "query_id": query_id,
        "executed_at": _iso_now(),
        "execution_ms": None,
        **result,
    }


def preview_query(
    db: Session,
    *,
    current_user: User,
    dataset: str,
    fields: list[str],
    filters: list[dict],
    group_by: list[str],
    aggregations: list[dict],
    sort_by: Optional[str],
    sort_dir: str,
    limit: int,
) -> dict[str, Any]:
    result = _compute_query_result(
        db,
        current_user=current_user,
        dataset=dataset,
        fields=fields,
        filters=filters,
        group_by=group_by,
        aggregations=aggregations,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
    )
    return {
        "query_id": None,
        "executed_at": _iso_now(),
        "execution_ms": None,
        **result,
    }
