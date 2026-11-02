# Search Performance Audit (LIKE / ILIKE hotspots)

This document inventories the substring-search hotspots (`column.like("%term%")`
and `column.ilike("%term%")`) used in services/endpoints, and gives a
PostgreSQL-only mitigation plan. The SQLite developer database is unaffected:
SQLite already does a sequential scan and adding pg_trgm/tsvector indexes there
is a no-op.

> Why this matters: `LIKE '%term%'` with a leading wildcard cannot use a
> standard B-Tree index. PostgreSQL falls back to a sequential scan, which is
> fine on tens of thousands of rows but becomes a p95 latency problem on
> tens of millions.

---

## Hotspots inventory

The audit covers `app/services/` and `app/api/v1/endpoints/`. The pattern
`.like(...)` / `.ilike(...)` is used in ~140 call sites; the ones below
operate on substring searches (leading `%`) on text columns that are likely
to grow large.

### High traffic / large tables

| Service | Column(s) | Pattern | Notes |
|---|---|---|---|
| `client_service.py` (search by `q`) | `Client.name`, `Client.short_name`, `Client.contact_email` | `ilike("%q%")` on 3 cols `OR`-ed | Multi-column OR — `pg_trgm` GIN on each, or one tsvector covering all 3. |
| `user_service.py` (search by `q`) | `User.full_name`, `User.username`, `User.email` | `ilike("%q%")` on 3 cols `OR`-ed | Same pattern; **directory lookups, runs on every type-ahead**. |
| `cmdb_service.py` | `CMDBItem.name`, `CMDBItem.hostname` (and more) | `ilike("%q%")` on N cols `OR`-ed | CMDB grows fast in mature tenants. |
| `cab_service.py` (global "command palette" search) | `Project.{name,code,client_name}`, `Task.{title,code,description}`, `Ticket.{title,number,requester_name}`, `User.{full_name,email,username}`, `Inv.{number,client_name}`, `Opp.{name,client_name}` | `func.lower(col).like(q_lower)` on many cols `OR`-ed | **Highest-value optimization target** — touched on every cmd-K invocation, scans up to 6 tables. |
| `epics_service.py` | `WikiPage.{title,content_text}`, `Task.title`, `Project.name`, `Epic.title` | `ilike("%q%")` `OR`-ed | Wiki content_text grows unbounded → biggest seq-scan cost. |
| `portal_conversation_service.py` (KB search) | `KBArticle.{title,body,tags}` | `ilike("%query%")` truncated to 80 chars | KB grows but reads are batched — moderate priority. |
| `issue_type_service.py` (FTS table) | `FTSEntry.{title,body,tags}` | `ilike("%term%")` | Despite the "FTS" name, this is still a `LIKE` scan; revisit to use a real FTS index. |
| `report_builder_service.py` | dynamic `col.ilike("%v%")` and `ilike("v%")` | user-driven | Hot only if reports run frequently with substring filters. |

### Low impact (already tractable)

These use a **trailing** wildcard only (`prefix%`), which a regular B-Tree
index on the column can satisfy via index range scan. No action needed.

- `sla_service.py`: `Ticket.number.like(f"{prefix}-%")`
- `bookings_service.py`: `Invoice.number.like(f"INV-{year}-%")`
- `scim_service.py`: `User.username.ilike(f"{val}%")`
- `accounting_hub_service.py`: `Invoice.internal_notes.like("%[XERO sync%")` —
  the leading `%` makes it a seq scan, but `internal_notes` filtering is run
  on a small subset; low priority.

### Special cases

- `abac.py:556-562`: `func.json_extract(...).like(f"%{p.id}%")` —
  this searches inside a JSON column for a policy id; the right fix is to
  promote `matched_policies` into a junction table (already discussed under the
  ABAC audit) rather than indexing the substring search.
- `integrations.py`: small `User`/`Project` lookups by name fragments from
  inbound webhooks. Single-row results, low volume.

---

## Recommendations (PostgreSQL only)

### Option A — `pg_trgm` + GIN index (fastest fix, no API change)

For each hot column we want fast `ILIKE '%term%'` on:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Example: clients global search
CREATE INDEX CONCURRENTLY idx_clients_name_trgm
  ON clients USING gin (name gin_trgm_ops);
CREATE INDEX CONCURRENTLY idx_clients_short_name_trgm
  ON clients USING gin (short_name gin_trgm_ops);
CREATE INDEX CONCURRENTLY idx_clients_email_trgm
  ON clients USING gin (contact_email gin_trgm_ops);
```

Properties:

- Works transparently with the existing `ILIKE '%q%'` SQL — no code change.
- 3-char minimum term length for index use; shorter terms fall back to seq scan.
- ~3-5x storage overhead per indexed column. Plan for it on large tables.
- Build with `CONCURRENTLY` in prod to avoid table locks.

Apply to (priority order):

1. `users` (full_name, username, email)
2. `clients` (name, short_name, contact_email)
3. `tasks` (title, description, code)
4. `tickets` (title, number, requester_name)
5. `projects` (name, code, client_name)
6. `wiki_pages` (title, content_text) — but consider Option B for `content_text`.
7. `sd_configuration_items` (name, hostname, ip_address)

### Option B — Full-text search (`tsvector` + GIN)

For long-form text (`wiki_pages.content_text`, `kb_articles.body`,
`fts_entries.body`), `pg_trgm` indexes get huge. Use a `tsvector` column instead:

```sql
ALTER TABLE wiki_pages
  ADD COLUMN search_vec tsvector
  GENERATED ALWAYS AS (
    setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(content_text, '')), 'B')
  ) STORED;

CREATE INDEX idx_wiki_pages_search_vec
  ON wiki_pages USING gin (search_vec);
```

Querying:

```python
# requires a code change at the call site
q = q.filter(WikiPage.search_vec.op('@@')(func.plainto_tsquery('simple', term)))
```

Trade-off: lexeme tokenization is great for natural-language search but does
not match arbitrary substrings (e.g. won't match "esti" inside "estimación").
For codes, hostnames, and short identifiers, stick with Option A.

### Option C — `citext` for case-insensitive equality (different problem)

Several sites already do `func.lower(col).like(q_lower)` to dodge case. Where
the search is **equality** or **prefix only**, swap the column type to `citext`:

```sql
CREATE EXTENSION IF NOT EXISTS citext;
ALTER TABLE users ALTER COLUMN email TYPE citext;
```

Then `WHERE email = :e` works case-insensitively and uses the B-Tree index.
Does **not** help substring search — orthogonal to Options A/B.

---

## Suggested rollout

1. **Phase 1 (high traffic, fast win)**: pg_trgm GIN on `users`, `clients`,
   `tasks`, `projects` short-text columns. Estimated effort: one Alembic
   migration guarded with `if dialect == 'postgresql'`.
2. **Phase 2 (cmd-K cab_service)**: same approach across the 6 tables it
   touches, but also benchmark — `cab_service` already truncates `q` and
   runs per-table; the win comes from removing seq scans on the biggest
   tenant.
3. **Phase 3 (long-text)**: introduce a generated `tsvector` column on
   `wiki_pages.content_text`, `kb_articles.body`, `fts_entries.body` and
   migrate the corresponding query sites.

---

## Production measurement playbook (p95/p99)

Use this sequence in a real PostgreSQL environment to prove impact before and
after deploying `pg_trgm` indexes.

1. Enable extension and telemetry prerequisites:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

2. Capture baseline (before index deployment):

```bash
DATABASE_URL='postgresql+psycopg://<user>:<pass>@<host>/<db>' \
  venv/bin/python scripts/pg_trgm_latency_report.py > reports/qa/pg_trgm_before.json
```

3. Deploy migration `083_pg_trgm_search_indexes` in maintenance window.

4. Warm up representative traffic for 30-60 minutes.

5. Capture post-deploy metrics:

```bash
DATABASE_URL='postgresql+psycopg://<user>:<pass>@<host>/<db>' \
  venv/bin/python scripts/pg_trgm_latency_report.py > reports/qa/pg_trgm_after.json
```

6. Compare p95/p99 at APM level (Datadog/New Relic/Grafana) for:
   - `GET /api/v1/users?q=...`
   - `GET /api/v1/clients?q=...`
   - command palette/global search endpoints

Acceptance target for this P1:
- No regression in error rate.
- Search endpoints reduce p95 and p99 latency by at least 30% on production-like traffic.
- `EXPLAIN (ANALYZE, BUFFERS)` shows index usage (`Bitmap Index Scan` / `Index Scan`) for representative `ILIKE '%term%'` queries.

---

## Migration template (PostgreSQL-only, idempotent)

```python
def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return  # SQLite dev DB: NOOP
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_full_name_trgm "
        "ON users USING gin (full_name gin_trgm_ops)"
    )
    # ...repeat per column...

def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    op.execute("DROP INDEX IF EXISTS idx_users_full_name_trgm")
```

Always run `CREATE INDEX CONCURRENTLY` in production (Alembic `op.execute` with
`autocommit_block`) to avoid blocking writes. The template above uses the
non-concurrent form for readability — switch to `CONCURRENTLY` in real prod
migrations.

---

## SQLite (dev) behavior

SQLite does not have `pg_trgm` and does not benefit from a `tsvector`-style
GIN. It does have FTS5 virtual tables, but adopting them in the dev DB only
would diverge from prod. Recommendation: leave SQLite queries as plain `LIKE`
scans. Dev datasets are small enough that seq scans are imperceptible.
