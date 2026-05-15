# Composite Index Tuning Audit

Audit of composite (multi-column) indexes declared in `app/models/`, focused on
column ordering. The dominant rule is:

> **Equality before range** — put columns that are filtered with `=` or `IN`
> first, and columns filtered with range operators (`<`, `>`, `BETWEEN`,
> `ORDER BY <col>`) last.

A B-Tree index can only do an index-range scan up to the first range column; any
column after the first range filter is effectively unused for sorting/seeking
and only helps as a covering column.

This document is descriptive: it inventories every composite index and flags
ones whose ordering should be revisited. **No schema changes are made here**;
changing a composite index requires a migration and benchmarking on prod-shaped
data.

---

## Tenant scoping pattern (`org_id` first)

Almost every composite index in this codebase leads with `org_id` or
`organization_id`, which is correct for a multi-tenant app: nearly every query
filters by tenant (`WHERE org_id = :current_org`).

When the trailing column is a timestamp or status, that timestamp/status is
naturally the "range" or "sort" column. The pattern `(org_id, <ts_or_status>)`
is already optimal under equality-before-range.

---

## Inventory + recommendations

### `documents.py`

| Index | Columns | Verdict |
|---|---|---|
| `ix_documents_project_created` | `(project_id, created_at)` | OK — equality (`project_id=`) before range (`created_at` for `ORDER BY DESC`). |
| `ix_documents_client_created` | `(client_id, created_at)` | OK. |
| `ix_doc_perm_document_user` | `(document_id, user_id)` | OK — both equality; matches permission check `WHERE document_id=? AND user_id=?`. |
| `ix_doc_perm_document_role` | `(document_id, role)` | OK. |
| `ix_doc_perm_document_department` | `(document_id, department)` | OK. |

### `security_observability.py`

| Index | Columns | Verdict |
|---|---|---|
| `idx_event_org_cat` | `(org_id, category)` | OK. |
| `idx_event_org_sev` | `(org_id, severity)` | OK. |
| `idx_event_org_type` | `(org_id, event_type)` | OK. |
| `idx_event_org_occurred` | `(org_id, occurred_at)` | OK — tenant equality + time range. |
| `idx_det_org_sev` | `(org_id, severity)` | OK. |
| `idx_det_org_status` | `(org_id, status)` | OK. |
| `idx_inc_org_status` | `(org_id, status)` | OK. |
| `idx_inc_org_severity` | `(org_id, severity)` | OK. |
| `idx_anomaly_org_type` | `(org_id, anomaly_type)` | OK. |
| `idx_snapshot_org_hour` (unique) | `(org_id, snapshot_hour)` | OK — uniqueness scoped to tenant. |

### `ai_governance.py`

| Index | Columns | Verdict |
|---|---|---|
| `idx_guardrail_org_active` | `(org_id, is_active)` | OK — typical "list active guardrails for tenant". |
| `idx_guardrail_audit_org_ts` | `(org_id, evaluated_at)` | OK — tenant + range. |
| `idx_guardrail_audit_blocked` | `(org_id, was_blocked)` | OK. |
| `idx_guardrail_audit_user` | `(user_id, evaluated_at)` | OK — equality + range. |

### `abac.py`

| Index | Columns | Verdict |
|---|---|---|
| `idx_attr_def_org_key` | `(org_id, attribute_key)` | OK — both equality, used for upsert. |
| `idx_user_attr_user_org` | `(user_id, org_id)` | **Revisit**: Most ABAC queries filter by `org_id` first (tenant scoping middleware). Consider `(org_id, user_id)` for consistency with the rest of the codebase. Both columns are equality though, so the order matters only when one of them is dropped from the predicate. |
| `idx_policy_org_active` | `(org_id, is_active)` | OK. |
| `idx_audit_org_user` | `(org_id, user_id)` | OK. |

### `imputation.py`

| Index | Columns | Verdict |
|---|---|---|
| `ix_timer_session_user_active` | `(user_id, ended_at)` | OK — `WHERE user_id=? AND ended_at IS NULL` and `ORDER BY ended_at`. |
| `ix_imputation_snapshot_user_date` | `(user_id, snapshot_date)` | OK. |

### `workflow_designer.py`

| Index | Columns | Verdict |
|---|---|---|
| `ix_sd_workflow_runs_blueprint_status` | `(blueprint_id, status)` | OK. |

### `collaboration.py`

| Index | Columns | Verdict |
|---|---|---|
| `ix_direct_conv_pair` | `(user_a_id, user_b_id)` | OK — both equality. Note: there is an implicit assumption the pair is stored in a canonical order (smaller id first); confirm in the service layer. |
| `ix_conv_member_user` | `(conversation_id, user_id)` | OK. |
| `ix_conv_member_client` | `(conversation_id, client_user_id)` | OK. |
| `ix_msg_conv_sent` | `(conversation_id, sent_at)` | OK — equality + range, ideal for `ORDER BY sent_at DESC LIMIT N`. |

---

## Top-5 most-used indexes (audit focus)

Based on hot endpoints (chat listing, security events, document listing, ABAC
authorization, work-dashboard timers), the five indexes most worth verifying
under EXPLAIN ANALYZE on prod:

1. `ix_msg_conv_sent (conversation_id, sent_at)` — message timeline pagination.
2. `idx_event_org_occurred (org_id, occurred_at)` — security event feed.
3. `ix_documents_project_created (project_id, created_at)` — project document list.
4. `idx_guardrail_audit_org_ts (org_id, evaluated_at)` — guardrail audit log.
5. `ix_timer_session_user_active (user_id, ended_at)` — open-timer lookup.

All five follow equality-before-range — no action required, but capture
`EXPLAIN (ANALYZE, BUFFERS)` on the largest tenant before any future tweaks.

---

## When to add a new composite index

Add a composite index when:

1. The query is on the hot path (request rate or visible in p95 latency).
2. The `WHERE` clause has ≥ 2 columns combined with `AND`.
3. The selectivity of the leading column alone is poor (e.g. `org_id` for a
   noisy tenant) — adding a second equality column collapses the candidate set.

Avoid composite indexes when:

- The leading column is already highly selective (single-column index suffices).
- The "second" column is rarely in the predicate — pay write cost for no read win.
- You are tempted to put a range column first; use a single-column index instead
  and order in the query.

---

## Equality-before-range cheat-sheet

```sql
-- GOOD: tenant + time-range, supports ORDER BY occurred_at
CREATE INDEX idx_event_org_occurred ON events (org_id, occurred_at);
-- WHERE org_id = ? AND occurred_at >= ?
-- ORDER BY occurred_at DESC

-- BAD: range first, equality second
CREATE INDEX idx_event_occurred_org ON events (occurred_at, org_id);
-- Cannot seek directly to (org_id=?), must scan time range and filter.
```

Re-evaluate whenever a query pattern shifts (e.g. a new filter is added to the
endpoint) — the optimal column order may change.
