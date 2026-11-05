# Contecflow vs contecmind and contecintelligence

What the two sister products do, whether Contecflow already has it, and what was decided. Measured on 2026-11-05:
- **Inventory:** contecmind is about 229 services and 127 routers; contecintelligence was read across its services, APIs, agents and connectors. Each was inventoried from its own code.
- **Contecflow column:** each capability was checked in Contecflow's code at its real location (model, service or route), not by name.

**Statuses**
- **Has it**: Contecflow already does it, in the place shown.
- **Brought 2026-11**: added in this revision; the README section is named.
- **Missing**: not in Contecflow.

**Decision**
- **Bring?**: a candidate, waiting for the product owner's decision.
- **Not applicable**: it belongs to another kind of product (a knowledge platform or an analytics platform), not to a PSA/ITSM.
- **No**: considered and rejected, with the reason.

## 1. Already brought in this revision

| From | Capability | In Contecflow |
|---|---|---|
| contecmind | AI provider and model per function, ordered fallback, cooldown after errors, test and discover models without saving | AI Hub (README «AI Hub») |
| contecmind | Knowledge-base quality loop: citations, expert corrections applied at once, unanswered questions, stale and contradictory articles | Service Desk → KB → Calidad (README «Knowledge base → Quality loop») |
| contecintelligence | MCP server with governance (module switch, read-only by default, approval mode, audit) | `POST /api/v1/mcp` (README «External agents (MCP)») |
| contecintelligence | Ask-the-Data verification (time window, breakdown, ranking, units, distinct; es/en/zh) | Data Explorer (README «Ask the Data → Verification») |
| contecintelligence | Postgres row-level security with a non-superuser application role | README «Database isolation (RLS)» |
| both | OIDC SSO, passkeys, TOTP | Login (earlier revision) |

## 2. Contecflow already has it

| Capability (where it comes from) | In Contecflow |
|---|---|
| Unified approval engine: graph, quorum, SoD, SLA timeouts, delegation (mind) | `app/services/approval_engine/`; out of office and email decision were added in this revision |
| Visual workflow designer and BPMN 2.0 modeler (mind) | `/sd/workflow-designer`, `/bpm` (BPMN engine runs saved diagrams) |
| GRC: permission matrix, SoD, risks, controls (mind) | `/grc` (now per company, this revision) |
| Outgoing signed webhooks with retry (both) | `X-Contecflow-Signature` HMAC (`app/services/webhooks.py`), `deliver_webhook_task` with retries |
| Scheduled reports by email (intelligence) | `app/services/scheduled_reports.py` (SMTP + PDF) |
| Anomaly detection on KPIs (intelligence) | `app/services/bi_anomaly_service.py` (z-score) |
| Dashboards with drill-down, report builder, exports (intelligence) | BI module, `/report-builder`, `/exports` |
| Forecasting and what-if (intelligence) | `/scenarios`, `/resource-forecast`, `/predictions` |
| Document versions (mind) | `DocumentVersion` (`app/models/documents.py`) |
| Public forms (mind «forms») | `/public-forms` → ticket |
| Web Push and installable PWA (both) | `frontend/public/manifest.json`, `sw.js`, `collab-sw.js` |
| SAML 2.0 SSO (mind) | `app/api/v1/routers/auth_saml.py` |
| SCIM user provisioning (intelligence) | `app/api/v1/endpoints/scim.py` |
| Per-company AI credentials (mind «BYOK») | AI providers per organisation |
| AI evaluation runs (mind «evals») | `sd_ai_evaluation_runs`, drift snapshots |
| Tenant administration, plans and usage (both) | `/organizations` (create, suspend, delete with quarantine, export, impersonate, usage) |
| Runtime settings editable live (both) | Admin settings (172 keys, README «Runtime settings reference») |
| Weekly or daily digest (both) | Daily notice digest (this revision) |
| Slack and Teams integration (both) | Notifications and slash commands in collaboration bots |
| Embedding and developer access (intelligence «host apps, SDK») | Developer portal, API keys with scopes, OAuth apps |

## 3. Missing: candidates (decision pending)

| # | Capability | From | What it would give Contecflow | Effort |
|---|---|---|---|---|
| 1 | ✅ **Done 2026-11-05** (Enterprise → Auditoría → Cadena de integridad; `audit_logs` only) — **Tamper-evident audit log**: each entry chained by hash, a «verify» button and a signed export | both | Proof for audits (ISO 27001, SOC 2, ENS) that nobody altered the log. Today `audit_logs` has no chain. | Medium |
| 2 | ✅ **Done 2026-11-05** (GRC → Explicar acceso) — **Access explainer**: «why can / can't this user do X?» for a user and an action | both | Contecflow stacks role, ABAC, GRC matrix, project permissions, modules and company. Today an admin has no way to see which layer denies. | Medium |
| 3 | ✅ **Done 2026-11-05** — **👍 / 👎 on assistant and portal answers** feeding the quality loop (a 👎 opens an unanswered question) | mind | Closes the loop on internal questions, which today never become gaps on purpose. | Small |
| 4 | ✅ **Done 2026-11-05** — **Daily AI spend cap per company** (hard limit, not only an alert) | intelligence | Cost control for a multi-company SaaS. Today `AI_COST_ALERT_USD_PER_DAY` only logs a warning. | Small |
| 5 | **Ask-the-Data: real values when a filter finds nothing, and a bank of validated question → query pairs reused as examples** | intelligence | Fewer empty answers and fewer wrong queries; complements the verification already added. | Medium |
| 6 | ✅ **Done 2026-11-05** (Settings → Puesta en marcha; branding left out: it has no screen) — **Setup checklist for a new company**: AI provider, email, SSO, approval workflows, SLA, branding… each measured as done or not | mind | Faster onboarding of a new company; today nothing says what is left to configure. | Small |
| 7 | ✅ **Done 2026-11-05** (GRC → Informe de cumplimiento; backups shown as not measurable) — **Compliance evidence report** generated from the live system: MFA, audit chain, RLS state, backups, SSO, retention… | both | A document to hand to an auditor; complements GRC. Depends on #1. | Medium |
| 8 | ✅ **Done 2026-11-05** (Documents → Reservar / Liberar) — **Document check-out / check-in** (reserve while editing) | mind | Avoids two people overwriting the same document version. | Small |
| 9 | **General retention policies and legal hold** (beyond chat and GDPR requests) | both | Required in regulated sectors; today retention exists only for collaboration chat. | Large |
| 10 | **Microsoft Teams bot that answers with the knowledge base** | mind | Answers inside Teams. It needs an Azure Bot registration and cannot be verified without one. | Large |

## 4. Not applicable or rejected

| Capability | From | Reason |
|---|---|---|
| Connectors to external data sources (SQL engines, REST, files, historian/OPC-UA, dbt/LookML/Power BI importers, OSI, semantic layer and metrics compiler, cross-source federation) | intelligence | It is an analytics platform over the customer's sources; Contecflow analyses its own data (OLAP star schema). |
| Document ingestion pipeline (multiformat parsing, transcription, Drive/OneDrive/Notion/Confluence import, folder watch, figures, contextual enrichment, dead-letter queue) | mind | It is a knowledge platform; Contecflow's knowledge base is written by agents and from tickets. |
| Advanced retrieval (BM25 + vectors + rerank, HyDE, graph expansion, deep retrieval, agentic retrieval, semantic cache) | mind | Sized for corpora of thousands of documents; Contecflow's base is small. Revisit if it grows. |
| Studio (audio overview, mind maps, timelines, quizzes, learning paths, debate mode, personas) | mind | Knowledge consumption features, outside a PSA/ITSM. |
| Knowledge graphs and corpus analytics (doc graph, vector map, knowledge DNA) | mind | Same. |
| Records management, legal discovery cases, regulatory radar, compliance scanning of documents | mind | Document-compliance product features. Legal hold is kept as candidate #9. |
| Signed answer receipts and replay, trust per source, customer benchmark | intelligence | Make sense where numbers come from customer sources; Contecflow's numbers come from its own tables. |
| A2A agent card | intelligence | MCP already covers agent access; A2A has no consumer today. |
| Excel add-in, TypeScript SDK and web components | intelligence | No demand; the API and developer portal cover integrations. |
| Settings copilot (natural language → setting) | both | Low value next to a searchable settings screen. |
| Sandboxed code execution (Docker/gVisor) | intelligence | Contecflow does not run user code. |
| Per-company request rate limits | intelligence | Rejected for now: rate limiting is per IP address (`app/core/ratelimit.py`, slowapi). A per-company quota only matters with a noisy tenant, and none has been measured. |
