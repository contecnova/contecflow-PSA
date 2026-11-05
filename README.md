# Contecflow PSA

Contecflow is a multi-tenant Professional Services Automation platform: projects and delivery, time and resources, CRM and finance, an ITSM Service Desk (incidents, requests, problems, changes, CMDB, assets, SLA/OLA/UC), BI and AI features, a client portal, and administration for several organizations in one installation.

What was taken from the sister products contecmind and contecintelligence, what Contecflow already had, and what is still a candidate: [docs/COMPARATIVA_CONTECMIND_CONTECINTELLIGENCE.md](docs/COMPARATIVA_CONTECMIND_CONTECINTELLIGENCE.md).

This README is the complete functional and technical documentation of the solution. It was written on **2026-11-03** by reading the code and measuring it: every screen was traced to the API calls it makes, and every API call to the service, table and background job behind it. Where something could not be verified, it says **"Not verified"**. Where the code does not do what the screen suggests, it says so. Defects found while writing are listed in each section under **Limitations**; nothing was hidden to make the product look complete.

| Measured (2026-11-03) | Value |
|---|---|
| Menu entries (screens reachable from the sidebar) | 97, plus the client portal and public forms |
| HTTP API routes | 2,051 (2,043 under `/api/v1`, 3 under `/api/v2`, 5 public) and 6 WebSockets |
| Mapped database models | 395 (394 scoped by organization, 1 exempt) |
| Alembic migrations | 71, one linear chain, head `117_esign_secretos_cifrados` |
| Backend tests | Last full run (2026-11-04): 4,139 passed, 22 skipped, 1 xfailed, 2 failed — both structural checks on the new BPM endpoints, fixed in the next commit and passing on their own |
| Frontend tests | 40 files, 130 tests, all passing |
| Celery beat entries | 53 (over 35 tasks); `setup.sh`, `setup.bat` and Docker run them with Celery beat (APScheduler off) |
| Runtime settings (editable in Admin) | 123 keys in 15 groups |
| UI languages | Spanish, English, Chinese |

## How to read this document

- **Part 1 — Functional guide** (sections 1–6): one section per area of the menu. For each screen: who can open it, what it is for, how to use it step by step, what configures it, the endpoints and tables behind it, and its measured limitations. Functional users can skip the *Technical notes* paragraphs.
- **Part 2 — Technical guide** (section 7): architecture, installation, every environment variable, database and migrations, API, security model, background jobs, observability, testing, extending the code, troubleshooting.
- Other documents in the repository, in Spanish: `docs/SERVICE_DESK.md` (Service Desk manual), `docs/GUIA_DE_DISENO.md` (design guide reusable in other solutions), `DOCS.md` (older general documentation; section 7.13.3 of this README lists the statements in it that are wrong).

## Table of contents

- [Quick start](#quick-start)
- [Read this first: critical issues found while documenting](#read-this-first-critical-issues-found-while-documenting)
- **Part 1 — Functional guide**
  1. [Work & Delivery](#work--delivery)
  2. [People & Resources](#people--resources)
  3. [Finance, CRM & Client Portal](#finance-crm--client-portal) — including the [external client portal](#client-portal-external--portal)
  4. [Service Desk & ITSM](#service-desk--itsm)
  5. [Analytics, BI, AI & Automation](#analytics-bi-ai--automation)
  6. [Administration, Configuration & Integrations](#administration-configuration--integrations)
- **Part 2 — Technical guide**
  7. [Technical Guide](#technical-guide)

## Quick start

```bash
./setup.sh demo        # first time: dependencies, database, migrations, demo data, then starts API (:8000) and web (:3000)
./setup.sh start       # later starts
./setup.sh stop
```

- Web app: <http://localhost:3000> — sign in as user `admin` (or `admin@company.com`) with `SUPERADMIN_PASSWORD` from `.env`. In demo mode the admin's email comes from `seed_users_data.json` and `SUPERADMIN_EMAIL` is ignored; other demo users and password caveats are in [7.3.6](#36-first-login).
- Client portal: <http://localhost:3000/portal> — portal users are created in *Clients → (client) → Portal → Accesos*.
- API documentation (OpenAPI): <http://localhost:8000/docs>.
- `setup.sh start` applies pending migrations before starting (since 2026-11-04; before, only `demo`/`clean`/`update` did, and a `git pull` with new revisions left the API reading columns the database did not have).
- `setup.sh start`/`demo` also start a **Celery worker and Celery beat** (logs in `/tmp/contecflow-worker.log` and `/tmp/contecflow-beat.log`) and run the API with `ENABLE_APSCHEDULER=0 ENABLE_CELERY_BEAT=1`, so every scheduled job runs exactly once. Redis must be up (the setup starts it with Docker).

All modes of `setup.sh`/`setup.bat`, the Docker stack and manual installation are in [7.3](#3-requirements-and-installation).

## Read this first: critical issues found while documenting

Each item was measured in the code; the ones marked ✔ were re-checked by hand by the editor of this README. Details, and many smaller limitations, are in the section named in brackets.

**Operation**
- **Fixed 2026-11-03:** `setup.sh` did not start Celery, so 48 of the 52 scheduled jobs (SLA/OLA/UC scan, mailbox reading, the ticket event outbox that sends notifications, emails, webhooks and workflows) never ran locally. It now starts a worker and beat (verified: beat enqueued the ticket-event job and the worker ran it; the SLA scan, mailbox and asset-expiry jobs ran on the worker). `setup.bat` got the same change (`--pool=solo`; **not verified on Windows**). The Docker stack ran APScheduler in the API and the `beat` container at the same time; it now sets `ENABLE_APSCHEDULER=0`/`ENABLE_CELERY_BEAT=1`. Performance reminders, which only existed in APScheduler, are now a beat entry. [7.3, 7.8]
- ~~`scripts/rotate_keys.sh` replaces `SECRET_KEY` without re-encrypting stored secrets and prints the new key.~~ Fixed 2026-11-03 (`SECRET_KEY_PREVIOUS` + `scripts/reencrypt_secrets.py`). There is still no working backup procedure in the repository. [7.7, 7.13]

**Security**
- **Fixed 2026-11-03:** `GET /api/v1/settings/general` (open to any signed-in user) returned every `app_settings` row, including e-signature tokens and secrets in plain text. It now returns only general settings to non-admins and masks sensitive values for everyone. Since 2026-11-03 the e-sign credentials are also stored encrypted (migration 117 encrypts the existing ones). [6]
- ~~MFA enrolled on the `/mfa` screen does not protect sign-in; its QR sent the TOTP secret to Google.~~ Fixed 2026-11-03: enrolling there now sets the factor sign-in checks, its backup codes work at sign-in, and the QR is generated locally. [6]
- ~~Several endpoints accept wider roles than their screens (employees can read cost, GDPR and audit data); BI embed tokens are full access tokens.~~ Fixed 2026-11-03 for the routes listed in section 5 (report builder, Data Explorer previews, GDPR and governance reads, M365, ETL, AI narrative, scheduled reports) and for special-purpose tokens. The earlier claim that scheduled reports and the alert engine act across organizations was wrong: measured, the tenant filter scopes both. [5]
- ~~API keys and developer-portal tokens cannot authenticate API calls.~~ Fixed 2026-11-03: both authenticate on the whole API as their owner, cut down by scope, never for managing credentials; portal tokens were stored so they could never be found, now fixed (migration 119). [6]
- **Fixed 2026-11-03:** org admins could overwrite a global setting shared by all organizations through `PATCH /settings/general/{key}`; writes now go to the organization's row and only general keys are accepted. [6]
- ~~Slack/Teams inbound commands resolve the user by partial name/email match without organization context.~~ Fixed 2026-11-03: exact, unambiguous match, and the command runs in that user's organization. [6]

**Wrong data shown**
- ~~Finance dashboard: revenue, cost and margin always show 0, and PMs get 403 on the profitability summary.~~ Fixed 2026-11-03, with the pipeline KPIs and the project table that read fields the API does not send. Since 2026-11-04 the period selector (30/90/365 days) filters revenue, cost, margin and the project table on the server (imputations by date, milestones by billing date). [3]
- The Approval Inbox receives documents and client-portal requests, plus expenses, timesheets and absences (2026-11-03) and change requests from `/changes` and invoices (2026-11-04) when the organization has a default workflow for them. Timeouts now reach the entity. Purchases have no entity in the data model, so there is nothing to route. [1]
- ~~Executive dashboard KPIs always show €0; the agent dashboard (`/agent-dashboard`) shows zeros.~~ Fixed 2026-11-03, as is the resource forecast counting deleted bookings and ignoring absences. [5, 4, 2]
- ~~Many lists stop at 50 (or 25) items without pagination.~~ Fixed: the Service Desk ticket lists on 2026-11-03; on 2026-11-04 the project, people, task and absence lists the screens and pickers load now walk every page (`frontend/src/services/api/todasLasPaginas.ts`), `/absences` pages with a total, and `/tasks` honours the calendar's date range. Lists with a fixed cap by design (portfolio risks top 50, CSV 2,000 rows) are unchanged. [1, 4]

**Service Desk**
- ~~The ticket panel cannot write an internal note.~~ Fixed 2026-11-03: the panel has an *Internal note* checkbox; internal notes show to agents with a badge and never reach the requester or the portal. [4]
- ~~Setting priority by hand does not recalculate SLA due dates; "Back to previous status" loses the paused time.~~ Fixed 2026-11-03, also for escalation, major incident, AI triage and Jira sync. [4]
- ~~The autonomous agent runs every 5 minutes for every organization with no off switch.~~ Fixed 2026-11-03: off by default, switch and thresholds per organization; each ticket is evaluated once. [4]

**Features that look real but are not (or not fully)**
- Most "AI" features are rules or statistics; only NexusAssist, NexusAgent, the BI narrative, Ask the Data, the AI-assignment tie-break and AI Hub test/sync call an LLM provider. ML extras (Prophet, LightGBM, sentence-transformers) are not in the Docker image. [5]
- ~~Automations never fire on their own (only "Test" runs them, and it runs the real actions).~~ Fixed 2026-11-03: rules fire on record changes and on a periodic scan, per organization; "Test" simulates (migration 118). [5]
- ~~BPM is a diagram editor without an execution engine.~~ Fixed 2026-11-04: saved diagrams run (human tasks in an inbox, exclusive and parallel gateways, timers), with a documented subset of BPMN; anything outside it is refused at start (migration 121). [5]
- Sprint Planning "AI" is a greedy fill by story points. [1]
- ~~Custom roles, role `module_access`, project permissions and issue types are stored but not enforced.~~ Fixed 2026-11-03: module access closes API routes and screens, custom roles can be assigned, project permissions restrict per project, and tasks carry an issue type from the project catalogue (migration 120). What still is not enforced: the role `permissions` JSON (no screen edits it), `can_see_rates`, and levels never grant more than the base role. [2, 6]

---

# Part 1 — Functional guide

## Work & Delivery

This section covers the day-to-day work screens (the **My Work** menu group: My day, Inbox, Chat, Tasks, Kanban, Time, Calendar, Absences, Documents, Expenses, Approvals) and project delivery (the **Projects** menu group: portfolio health, projects, sprints, RACI, changelog, UAT, Gantt, epics, deliverables, change requests, risks, dependencies, Git, wiki, meeting assistant).
Everything here was checked against the code (`frontend/src/App.tsx`, `frontend/src/components/layout/Layout.tsx`, the page components, `frontend/src/services/api/*`, `app/api/v1/endpoints/*`, `app/services/*`, `app/models/*`). All API calls made by these 28 pages (including the sub-pages embedded by Inbox and Time) were matched against the 2,051 routes the FastAPI app registers at startup. Every call resolves to an existing route with the right HTTP method. The bugs listed below are about behaviour, not missing endpoints.

**How to read the role lines.** *Menu* is who sees the entry in the sidebar (`Layout.tsx`). *Route* is what `ProtectedRoute` in `App.tsx` enforces. When the route has no `roles=` list, any logged-in user who types the URL can open the page. The backend then decides what they can do. Roles: `admin`, `pm`, `team_lead`, `hr`, `employee` (plus `subcontractor` in the backend). Backend guards used below: `require_admin_or_pm` = admin, pm; `require_any_manager` = admin, pm, team_lead, hr; `require_internal_user` = all except subcontractor.

**Cross-cutting limitations (measured)**

- ~~Lists stop at the backend's default page size.~~ Fixed 2026-11-04: `projectsApi.list`, `usersApi.list`, `tasksApi.list` and `absencesApi.list` request every page (200 per request) unless the caller asks for a specific `page`, so the pickers in Tasks, Kanban, Sprints, Gantt, Epics, Risks, Documents, RACI, Changelog, UAT, Deliverables, Changes and Dependencies, and ProjectsPage, show all visible items. With thousands of projects this loads them all; there is still no pagination UI on ProjectsPage.
- **Hidden buttons don't match backend permissions.** Most delivery pages (Sprints, RACI, UAT, Changelog, Epics, Risks, Dependencies, Wiki, Meeting Assistant, Documents) contain no `hasRole` check. Users who can open the page see create/edit buttons that the backend answers with 403.
- **UI text is not fully translated.** Many labels, toasts and prompts are hard-coded in Spanish rather than going through `useAppT()`. Examples: month names in Calendar, the Expenses form, the Kanban "reopen" prompt, the CAB buttons and the Projects table columns.
- **Few frontend tests.** The frontend has 32 `*.test.ts(x)` files. Only one touches these screens (`GanttChart.test.tsx`). Backend tests exist for most endpoint families. No test file references `/cmdb/sprint-plans`, `/ai-modules/meetings` or `/ai-modules/smart-schedule`.
- **AI features need a provider.** Every "AI" button calls the configured AI provider (`ANTHROPIC_API_KEY` / `CONTECFLOW_AI_MODEL`, or the provider routing in `call_ai_unified`). Without one, these calls fail. Exceptions (no AI involved) are flagged per module.

---

### My day (Mi día) — `/work-dashboard`
*Roles:* Menu: admin, pm, team_lead, employee, hr. Route: any authenticated user. It is the default landing page for `employee` (`landingPathFor` in `App.tsx`).

**Purpose.** A read-only personal dashboard: my open and overdue tasks, hours this week and month, my pending approvals, expenses and absences.

**How to use it.**
1. Open *Mi día*. The KPI cards show:
   - **Open tasks:** statuses `backlog,todo,in_progress,blocked,in_review`, assigned to me.
   - **Overdue tasks.**
   - **Hours this week** and **hours this month:** analytics metric `hours_by_week`.
   - **Approvals waiting for me.**
   - **Pending expenses:** `status=pending`, which the backend maps to `submitted`.
2. Two gauges:
   - **Weekly hours vs target.** Target = `user.weekly_capacity_hours`, or 40 if it is null. Green ≥80 %, amber ≥50 %.
   - **Task completion ratio.**
3. Below the gauges: an activity summary and a 180-day monthly hours trend (`hours_by_month`).
4. Shortcuts:
   - *New task* → `/tasks`
   - *Log hours* → `/imputar`
   - *New ticket* → `/service-desk`
   - *Timer* → `/time`

   KPI cards link to filtered views, for example `/tasks?view=list&mine=1&status=open&overdue=1`.

**Configuration.** Only the user's `weekly_capacity_hours` (users table). The colour thresholds (80/50) and the 40 h fallback are hard-coded in `WorkDashboardPage.tsx`. They do not read `DEFAULT_WEEKLY_CAPACITY_HOURS`.

**Technical notes.**
- `GET /api/v1/tasks` is called 3 times: open, overdue and done, with `page_size` 500 and 1.
- `GET /api/v1/analytics/query/{metric_id}`
- `GET /api/v1/approvals/requests/pending-my-action`
- `GET /api/v1/expenses/my`
- `GET /api/v1/absences/my`

**Limitations.**
- The *Timer* shortcut opens `/time` on the **Log hours** tab, not the Timer tab. The `TimePage` tab lives in component state, not in the URL.
- If a query fails, its KPI quietly shows 0 (each query has `.catch(() => [])`). The only error toast is for the task metrics.

### Inbox (Bandeja de entrada) — `/inbox`
*Roles:* Menu: all five roles. Route: any authenticated user.

**Purpose.** One inbox with three tabs: **Notifications**, **Mentions** and **Approvals**. It embeds `NotificationsPage`, `MentionsPage` and `ApprovalsPage`. The active tab is kept in `?tab=`.

**How to use it.**
- **Notifications** merges system alerts (`/alerts`) and enterprise notifications (`/enterprise/notifications`). You can mark one item read or all items read.
- **Mentions** lists `@mentions` (`/activity/mentions/my`) with *mark read* and *mark all read*. It also uses threaded comments (`/epics/comments`: create, resolve, delete).
- **Approvals** shows "my pending approvals". It is the same component and behaviour as `/approvals` (see below).

The tab badges are refreshed every 60 s (`useNotificationBadges`).

**Configuration.** None found.

**Technical notes.**
- Endpoints: `GET /api/v1/alerts`, `PATCH /api/v1/alerts/{id}/read`, `GET /api/v1/enterprise/notifications`, `POST …/{id}/read`, `POST …/read-all`, `GET /api/v1/activity/mentions/my`, `POST /api/v1/activity/mentions/{id}/read`, `POST /api/v1/epics/mentions/read-all`, `GET /api/v1/ws/ticket` (live notifications over WebSocket `/api/v1/ws/notifications`).
- Tables: `alerts`, `notifications`, `mentions`, `threaded_comments`.
- Job `run-alert-engine-daily` (08:00) generates alerts.

**Limitations.** Everyone can reach the Approvals tab here, including employees. The standalone `/approvals` route is limited to admin, pm and team_lead.

### Chat (Teams) — `/chat`
*Roles:* Menu: all five roles. Route: any authenticated user. `/chat/admin` redirects to `/settings/chat-admin` (admin only, documented elsewhere). `/chat/call/:callId` opens the call window.

**Purpose.** A Teams-style internal chat:
- workspace, teams and channels
- direct and group conversations
- threads, reactions, pins and saved messages, drafts, search
- presence and notification rules
- attachments
- voice/video calls
- slash commands and bots

**How to use it.**
- Create a channel or group with *+*. Open a DM from a user.
- Type `@` for mention suggestions.
- Attach files with the paperclip.
- Message menu: react, edit, delete, pin, save, or *link* the message to another record (`/messages/{id}/link`). Run `/collaboration/messages/{id}/link/candidates?kind=…` to see which records can be linked.
- Slash commands, typed as a message starting with `/`, are handled on the server by `maybe_handle_inline_command`: `/ask`, `/task`, `/ticket`, `/imputar 30m`, `/risk`, `/decision`, `/poll Q? | A | B`, `/standup`, `/findfile`, `/onboard`, `/meet`, `/recap`, `/escalate`. The help list comes from `GET /collaboration/slash/help`.
- The phone/video buttons start a call (`POST /collaboration/calls/start`) and open `/chat/call/:id`.

**Configuration.** Read straight from `os.environ`, not from `Settings` or Admin runtime settings:

| Area | Variables |
|---|---|
| Calls | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` |
| Realtime fan-out | `COLLAB_BUS_BACKEND` (default `memory`; `redis` and `nats` modules exist) |
| File storage | `COLLAB_STORAGE_BACKEND` (default `local`), `UPLOADS_DIR` |
| Antivirus | `CLAMAV_ENABLED`, `CLAMAV_HOST`, `CLAMAV_PORT`, `CLAMAV_SOCKET`, `CLAMAV_TIMEOUT` |
| Search | `OPENSEARCH_URL`, `OPENSEARCH_USER` |
| Transcription | `OPENAI_API_KEY`, `OPENAI_STT_MODEL`, `WHISPER_LOCAL`, `WHISPER_BIN`, `WHISPER_MODEL` |

These are `Settings` fields: `COLLAB_CALL_START_PER_MIN`, `COLLAB_CALL_JOIN_PER_MIN`, `COLLAB_CALL_HISTORY_LIMIT`, `COLLAB_WEBHOOK_INCOMING_PER_MIN`, `COLLAB_CALENDAR_MAX_EVENTS`, `COLLAB_PORTAL_MESSAGE_PER_MIN`.

**Technical notes.**
- About 40 endpoints under `/api/v1/collaboration/*` (workspaces, messages, files, calls, bots, compliance, admin).
- Realtime: WebSocket `/api/v1/collaboration/ws?ticket=…`, opened app-wide by `ChatRealtimeContext`. Polling every 30–60 s is the fallback.
- Scheduled messages are delivered by an in-process scheduler started with the app (`services/collaboration/_scheduler.py`, every 30 s), not by Celery.
- Tables: 38 `collaboration_*` tables (messages, conversations, channels, calls, recordings, transcripts, retention policies, legal holds, audit events, …).

**Limitations.**
- **Calls without LiveKit are not real calls.** Without LiveKit credentials the backend issues a `dev:` token and `CallPage` falls back to a local `getUserMedia` preview: no media is exchanged between participants.
- **Recording does not record.** *Start recording* only inserts a `collaboration_recordings` row with `status="recording"`. No LiveKit egress call exists in the code.
- **Chat calendar needs an external account.** The calendar panel needs a connected Google Calendar or M365 integration (`google_calendar_list` / `m365_calendar_list`).
- **Multiple workers: Not verified.** With the default `memory` bus, realtime delivery across several API workers was not verified.

### Tasks — `/tasks`
*Roles:* Menu: admin, pm, team_lead, employee. Route: any authenticated user. *New task* and *Auto-planificar* are shown only to admin, pm and team_lead.

**Purpose.** The main task list and board, with filters, bulk edit, task detail, comments, documents, custom fields and AI helpers.

**How to use it.**
1. Pick a view with the toggle: `kanban` (default) or `list`.
   - Filters go into the URL: `project_id`, `status`, `search`, `priority`, `assignee`, `overdue=1`, `mine=1`.
   - The board with a project selected uses `GET /tasks/kanban/{project_id}`. Its columns are `todo`, `in_progress`, `blocked`, `in_review`, `done`.
2. **Create:** title, project, assignee, priority (`critical | high | medium | low`), start and due dates, estimated hours, tags, description. The description has an inline AI editor that calls `/ai/chat`. A blocked reason is also editable.
3. **Detail modal** tabs: detail, comments, docs.
   - Edit any field. Status options come from the project workflow (`GET /project-workflows/{project_id}`, table `workflow_states`). If the project has none, the default list is used.
   - Custom field values: `/custom-fields/{project_id}/values/{task_id}`.
   - *Suggest assignee* (`/semantic/suggest/task`) and *Estimate effort* (`/semantic/estimate/effort`).
4. **Statuses and allowed transitions.** The backend enforces these on `PATCH /tasks/{id}` (`app/services/tasks/core.py`) and returns 400 for anything else:

   | From | Allowed to |
   |---|---|
   | `backlog` | `todo`, `cancelled` |
   | `todo` | `in_progress`, `done`, `backlog`, `cancelled` |
   | `in_progress` | `in_review`, `todo`, `done`, `blocked`, `cancelled` |
   | `in_review` | `done`, `in_progress`, `cancelled` |
   | `blocked` | `in_progress`, `todo`, `cancelled` |
   | `done` | `in_progress` (reopen) |
   | `cancelled` | nothing (terminal) |

   Moving to `in_progress` sets `started_at`; moving to `done` sets `completed_at` and triggers an OKR sync.
5. **Bulk edit (list view):** select rows, then set status, assignee and/or priority. Calls `POST /tasks/bulk-update`.
6. **Auto-planificar** opens `SmartScheduleModal`:
   - `POST /ai-modules/smart-schedule` (uses the AI provider) proposes dates.
   - Applying them calls `POST /tasks/bulk-dates`.

**Configuration.** Per project:
- workflow states (`/settings/project-workflows`)
- custom fields
- task statuses catalogue (`/settings/task-statuses`, table `custom_task_statuses`)

Task status values must still be one of the `TaskStatus` enum values; the Pydantic schema rejects anything else.

**Technical notes.**
- `GET/POST /api/v1/tasks`, `PATCH/DELETE /api/v1/tasks/{id}`, `POST /tasks/{id}/comments`, `POST /tasks/bulk-update`, `POST /tasks/bulk-dates`.
- Permissions:
  - Delete and bulk-dates: admin and pm only.
  - Create and comment: all internal users.
  - Update: ABAC (`enforce_abac`).
- Tables: `tasks`, `task_comments`, `task_movement_logs`, `workflow_states`.

**Limitations.**
- **Bulk edit skips the transition rules.** `POST /tasks/bulk-update` does not call `validate_task_transition` (`services/tasks/bulk.py`), so it can make jumps that the single edit rejects (e.g. `cancelled → todo`).
- ~~List limited to 50.~~ Fixed 2026-11-04: the list loads every page.
- **Kanban without a project hides two statuses.** It groups the flat list into the 5 columns above; `backlog` and `cancelled` tasks are not shown.
- **team_lead gets 403 on two actions.** Auto-planificar's apply step (`bulk-dates`) and task deletion require admin or pm, but the UI shows them to team_lead.

### Kanban — `/kanban-advanced`
*Roles:* Menu: admin, pm, team_lead, employee. Route: any authenticated user.

**Purpose.** A board with drag-and-drop, swimlanes (by assignee, priority or epic), quick-add per column, WIP gauges, filters (priority, assignee, search, sprint) and a movement log per card.

**How to use it.**
- Pick a project, or none for all.
- Drag a card to another column. This calls `PATCH /tasks/{id}` with the new status.
- When moving a card **out of** `done` or `cancelled`, a browser `prompt` asks for a reason. It is stored as `move_reason` in `task_movement_logs`.
- Click a card to see its movement log (`GET /tasks/{id}/movement-log`).
- Set WIP limits per column in the WIP panel.
- Keyboard: `/` or `f` focuses search; `Esc` cancels a drag.

**Configuration.** None found. WIP limits are React state only.

**Technical notes.** `GET /api/v1/tasks?page_size=500`, `GET /api/v1/sprints`, `POST /api/v1/tasks`, `PATCH /api/v1/tasks/{id}`, `GET /api/v1/tasks/{id}/movement-log`.

**Limitations.**
- **Only 5 columns.** Columns are `backlog`, `todo`, `in_progress`, `in_review`, `done`. Tasks in `blocked` or `cancelled` **are not displayed** at all.
- **Some drags always fail.** The server rejects moves outside the transition table with 400 and the UI shows a toast. Examples: `backlog → in_progress`, `todo → in_review`.
- **WIP limits are not saved or enforced.** They are lost on reload; going over a limit only colours the counter.
- **The sprint filter lists other projects' sprints.** It calls `GET /api/v1/sprints?project_id=…`, but that endpoint (`list_all_sprints`) has no `project_id` parameter. It returns up to 20 sprints from the whole organisation.

### Time (Tiempo) — `/time`
*Roles:* Menu: all five roles. Route: any authenticated user.

**Purpose.** A container with three tabs: **Log hours** (`ImputarPage`, also at `/imputar`), **Timer** (`TimerPage`) and **Week** (`TimesheetsPage`).

**How to use it.**
- **Log hours:** pick project, task, date and hours, then save (`POST /imputations`). You can edit or delete entries. The week grid comes from `GET /imputations/my/week`. An AI anomaly check is available (`GET /ai/suggestions/timesheets/{user_id}`). Entries made offline go through `services/offlineQueue.ts` (offline replay behaviour: Not verified).
- **Timer:** start, pause, resume, stop or cancel (`/imputations/timer/*`). *Stop* creates the time entry.
- **Week (timesheets):** submit the week with `POST /timesheets/my/{week_start}/submit`. Managers see the *pending* and *team* lists and can approve or reject (`POST /timesheets/{id}/review`). There is also a `send-back` endpoint (`POST /timesheets/{id}/send-back`).

  Timesheet statuses:
  - `draft` → `submitted`
  - `submitted` → `approved` or `rejected` (review); `submitted` → `rejected` (send-back)
  - `rejected` → `submitted` (resubmit)

  An empty week cannot be submitted. Approving marks the week's entries `is_approved`.

Rules enforced in `imputation_service.py`:
- You can only log time on projects where you are PM, a member, or assignee of the task.
- At most 24 h per day.
- No dates older than the lockout cutoff.
- An approved entry, or an entry in a submitted or approved timesheet, can only be changed by an admin.

**Configuration.**
- Lockout window = `organizations.imputation_lockout_days`, falling back to the env setting `DEFAULT_IMPUTATION_LOCKOUT_DAYS` (default 14).
- `SD_TIME_TO_TIMESHEET` (runtime group `service_desk`): time logged on service-desk tickets that belong to a project is copied to the agent's timesheet.

**Technical notes.**
- Tables: `imputations`, `timer_sessions`, `timesheets`, `imputation_alerts`.
- Job `check-missing-imputations` runs Mon–Fri at 18:00.
- Timesheet review is `require_any_manager`.

**Limitations.**
- **The Admin setting for lockout has no effect.** The runtime setting `DEFAULT_IMPUTATION_LOCKOUT_DAYS` (Admin → runtime group `locale`) is **not read** by the lockout code, which uses the static `settings` object. Changing it in Admin does not change the lockout fallback.
- **The tab is not in the URL.** You cannot deep-link to the Timer or Week tab.

### Calendar — `/calendar`
*Roles:* Menu: all five roles. Route: any authenticated user.

**Purpose.** A read-only month view showing:
- task due dates
- project milestones
- sprint start and end dates
- absences

**How to use it.** Move between months with the arrows. Filter by type: `all | task | milestone | sprint | absence`. There is no create or edit from this page.

**Configuration.** None found.

**Technical notes.** `GET /api/v1/tasks`, `GET /api/v1/projects/milestones?date_from&date_to`, `GET /api/v1/sprints?limit=20`, `GET /api/v1/absences?date_from&date_to&limit=50`.

**Limitations.**
- ~~Tasks are not filtered by month on the server.~~ Fixed 2026-11-04: `GET /tasks` accepts `due_date_from`/`due_date_to`, and the page loads every task of the month.
- **Sprints are not filtered by month either.** It shows at most 20 sprints org-wide.
- **Absences appear only on their start date.**
- **Two event types are never loaded.** The legend has `contract` and `license` event types, but no query loads them.
- **Hard-coded Spanish.** Month and day names are hard-coded in Spanish.

### Absences — `/absences`
*Roles:* Menu: admin, pm, hr, team_lead, employee. Route: any authenticated user. The *Pending* and *Team* tabs are shown only to admin, hr and pm.

**Purpose.** Request and approve leave, see your vacation balance and the team absence calendar.

**How to use it.**
1. **Mine** tab: see your vacation balance for the year (`GET /absences/my/vacation-balance`), then *New request*:
   - type: `vacation | sick | personal | training | maternity | paternity | other`
   - start date and end date
   - reason

   The server rejects:
   - end date before start date
   - overlap with another of your absences

   It computes `working_days` excluding weekends and the `holidays` table.
2. While a request is `pending` you can edit it (`PATCH /absences/my/{id}`). You can cancel it with `DELETE /absences/my/{id}` unless it is approved and has already started.
3. **Pending** tab (managers): approve or reject with a reason (`POST /absences/{id}/review`). Only `pending` requests can be reviewed.
4. Statuses: `pending → approved | rejected`; any user cancellation sets `cancelled`.
5. **Calendar** tab: `GET /absences/calendar`.

**Configuration.**
- Entitlement = `user_vacation_balances.days_entitled` (+ `days_carried_over`), managed in Advanced config (`/advanced-config/vacation-balances`).
- Fallback is the env setting `DEFAULT_VACATION_DAYS_PER_YEAR` (default 23).
- Holidays come from `/settings/holidays`.

**Technical notes.**
- Endpoints: `/api/v1/absences/my`, `/my/{id}`, `/my/vacation-balance`, `/pending`, `/team`, `/calendar`, `/{id}/review`, `/summary/{user_id}`.
- Tables: `absences`, `holidays`, `user_vacation_balances`.

**Limitations.**
- **Balance is not enforced.** A request is accepted even if it exceeds the remaining days.
- **Self-approval is not blocked.** No check prevents a manager from approving their own request.
- **No notifications.** None are sent on request or review: there are no `notify`/`emit` calls in the absence endpoints or service.
- **The Admin setting for vacation days has no effect.** The balance code reads the static env `DEFAULT_VACATION_DAYS_PER_YEAR`, not the runtime setting of the same name in Admin → `locale`.
- **Absences skip the approval engine.** They don't use Approval workflows (`entity_type` `leave` exists in the workflow designer but nothing opens a request for it).
- **team_lead can't see the review tabs.** The backend lets team_lead review absences (`require_any_manager`), but the UI hides the Pending and Team tabs from them.

### Documents — `/documents`
*Roles:* Menu: admin, pm, hr, team_lead, employee. Route: any authenticated user.

**Purpose.** A document repository with:
- categories, tags
- versions
- per-document permissions
- optional approval
- AI summary

**How to use it.**
1. *Upload*: title, description, category, tags (comma-separated), optional project, and *requires approval*. Calls `POST /documents/upload` (multipart).
   - Categories: `contract | deliverable | proposal | sop | requirements | meeting_notes | legal | other`.
2. Open a document. The drawer has three tabs:
   - **Preview:** choose a version.
   - **Versions:** upload a new version (`POST /documents/{id}/versions`).
   - **Meta:** edit with `PATCH /documents/{id}`.
3. **Permissions:** grant a user `viewer | editor | admin` (`/documents/{id}/permissions`).
4. **Approval** (only if *requires approval*):
   - On upload, if an approval workflow matches the category, an `ApprovalRequest` is opened automatically. Otherwise, *Submit for approval* (`POST /documents/{id}/submit-approval`, needs `editor` access) opens one.
   - `POST /documents/{id}/approve` (needs document `admin` access) decides through the approval engine if a request is linked. Otherwise it sets `approval_status` (`pending | approved | rejected`) directly.
   - After a rejection you can resubmit.
5. *AI summary* (`POST /documents/{id}/ai-summary`) works only when text can be extracted: a PDF with a text layer, `.txt` or `.md`. OCR is used only if tesseract, pytesseract and pypdfium2 are installed. Otherwise you get a 422.
6. *Delete* archives the document (soft delete).

**Configuration.**
- Storage is chosen at startup: AWS S3 / S3-compatible if credentials are present (`AWS_S3_BUCKET`, `AWS_S3_ENDPOINT_URL`, `AWS_S3_FORCE_PATH_STYLE`), otherwise the local `uploads/` folder (`app/services/s3_service.py::_build_storage`).
- Runtime group `storage`: `S3_URL_EXPIRATION_HOURS`, `MAX_FILE_SIZE_MB` (default 100).

**Technical notes.**
- `/api/v1/documents` (list, create), `/{id}`, `/{id}/versions`, `/{id}/permissions`, `/{id}/approve`, `/{id}/submit-approval`, `/upload`, `/file/{key}`, `/by-project|by-task|by-ticket/{id}`, `/{id}/tags`, `/{id}/ai-summary`.
- Tables: `documents`, `document_versions`, `document_permissions`, `document_tags`, `document_access_logs`, plus `approval_requests` when a workflow is used.

**Limitations.** The AI summary needs both text extraction and a configured AI provider.

### Expenses — `/expenses`
*Roles:* Menu: admin, pm, hr, employee (**not** team_lead). Route: any authenticated user. The *Pending* and *Team* tabs are shown to admin, pm and hr.

**Purpose.** Record expenses against projects, submit them, and get them approved and reimbursed.

**How to use it.**
1. **My expenses** → *New*:
   - category: `travel | accommodation | meals | software | hardware | training | subcontract | other`
   - description, amount
   - currency: the UI offers `EUR, USD, GBP, PLN, CHF`
   - date, *billable* flag, notes
   - receipt **URL** (text field)

   *Upload receipt* sends the image to `POST /expenses/ocr` and pre-fills amount, currency, merchant, date and category.
2. Expense statuses and actions:

   | From | Action | To | Who |
   |---|---|---|---|
   | `draft` | Submit | `submitted` | owner |
   | `submitted` | Recall | `draft` | owner |
   | `submitted` | Approve / Reject (with reason) | `approved` / `rejected` | manager |
   | `approved` | Mark reimbursed | `reimbursed` | manager |

   Only drafts can be edited or deleted by the owner. The owner is notified on approve and reject.
3. Billable expenses are refused on projects that are not `active` or `planning`.

**Configuration.** The default currency comes from `GET /settings/org-defaults` (`DEFAULT_CURRENCY`, default EUR). OCR uses the AI model in `CONTECFLOW_AI_MODEL` and needs `ANTHROPIC_API_KEY`, otherwise it returns 503.

**Technical notes.**
- `/api/v1/expenses/my`, `/my/{id}`, `/my/{id}/submit`, `/my/{id}/recall`, `/pending`, `/team`, `/{id}/review`, `/{id}/reimburse`, `/ocr`, `/export` (Excel).
- Review and reimburse are `require_any_manager`.
- Table: `expenses`.

**Limitations.**
- **A rejected expense is a dead end for its owner.** The UI shows *Edit* on `rejected` expenses, but `PATCH /expenses/my/{id}` only accepts `draft` and returns 400. No endpoint moves `rejected` back to `draft`; recall only works on `submitted`.
- **Receipts are links, not files.** The receipt is not stored: OCR only reads the file, and `receipt_url` is free text.
- **PDF receipts are probably rejected.** They are sent to the AI with media type `image/png` (`expense_service.ocr_receipt`); the provider is likely to reject them (Not verified at runtime).
- **Creating a draft fires a "submitted" event.** Creating an expense emits `EXPENSE_SUBMITTED` even though it starts as `draft`.
- **Reimburse has no ABAC check**, unlike review.
- **The currency list is hard-coded** in the UI.

### Approval Inbox — `/approvals`
*Roles:* Menu and route: admin, pm, team_lead, hr, employee (since 2026-11-05: any internal user can be an approver; it used to block hr and employees named as approvers). The same component is embedded in `/inbox` for every role. Workflow design lives at `/settings/approval-workflows` (config mode, documented in the Settings section).

**Purpose.** Shows the approval-engine requests where the current user is the approver for the current step.

**How to use it.**
1. Filter by entity type.
2. Open a request and decide *approve* or *reject* with a note (`POST /approvals/requests/{id}/decide`). You can also select several and *approve selected*; this sends one decide call per request.
3. Workflows are multi-step:
   - quorum, delegation, timeout actions
   - SLA
   - chaining to another workflow
4. Timeouts are processed by the hourly job.

**Configuration.** Workflows, steps, groups and templates are defined in config mode (`/settings/approval-workflows`).

**Technical notes.**
- `GET /api/v1/approvals/requests/pending-my-action`, `POST /api/v1/approvals/requests/{id}/decide`.
- Tables: `approval_workflows`, `approval_steps`, `approval_requests`, `approval_decisions`, `approval_groups`.
- Job `process-approval-timeouts` runs hourly; the step's `on_timeout` is escalate, auto_approve or reject.
- **Fixed 2026-11-05** (`tests/test_aprobaciones_nucleo_2026_11.py`):
  - **Which workflow:** a request goes to the most specific active workflow whose conditions match (`trigger_conditions`: `amount_gt/gte/lt/lte`, `department`, `category`; the requester's department is added automatically), otherwise to the default one (`approval_engine._base.elegir_flujo`). Before, only the simulation used the conditions and every request took the default workflow. Invoices, expenses, timesheets, leave and change requests use the same chooser.
  - **Delegation works:** the delegate is stored in the decision row (`approval_decisions.delegate_to`, migration 129) and can decide; before, they were notified and got 403.
  - **Everyone who can decide is notified,** in the app and by email with a link to the inbox: the user, every active user of the role, the group members, the department, or the requester's manager. Before: only a named user or the *first* user of the role, in the app only; group, department and manager steps notified nobody.
  - **Reminders:** `reminder_hours` of a step re-notifies the approvers every N hours while it is pending (it was stored and never read).
  - **Approve or reject from the email** (`app/services/approval_engine/por_correo.py`): each approver's email carries a signed link for that approver and that step, valid `APPROVAL_EMAIL_LINK_HOURS` (72). It opens `/approvals/decide`, a page without login that shows the summary; deciding is a button (POST), never opening the link, because mail scanners open links on their own. The decision goes through the same checks as the inbox (authorization, segregation of duties, double vote, quorum); rejecting needs a reason; once decided or once the step changes, the link answers 410. Endpoints: `GET /api/v1/approvals/email-decision?token=` (summary) and `POST /api/v1/approvals/email-decision` (`{token, decision, note}`), both public and authorised by the signed token.
  - **Slack / Teams:** a pending approval is posted once per step to the configured Slack/Teams integrations (event `approval.required`). The Block Kit approval card existed only in the preview and its buttons pointed to a route that does not exist; they now open the inbox. The preview endpoint had a dead duplicate of the card, removed.
  - **Out of office:** in the inbox («Fuera de la oficina») each user can set a delegate between two dates. While it lasts, their approval notices also go to the delegate, and the delegate can decide the steps they would have decided (one level: A→B and B→A does not loop). Columns `users.away_delegate_id/away_from/away_until` (migration 131). Endpoints: `GET/PUT /api/v1/approvals/out-of-office` (only the session user's own absence; the delegate must be an active user of the same company).

**Limitations.**
- **Only three sources create requests.** Requests are opened automatically only for:
  - documents with *requires approval*
  - client-portal feature requests converted to change requests (if a default `change_request` workflow exists)
  - portal conversation messages
- **Expenses, timesheets and absences** (since 2026-11-03; `app/services/approval_engine/fuentes.py`, test `tests/test_bandeja_gastos_horas_ausencias.py`):
  - To route them here, create an **active, default** workflow with entity type *Expense* (`expense`), *Timesheet* (`timesheet`) or *Absence* (`leave`). Without one, nothing changes: they are reviewed only on their own screens.
  - A request is opened when an expense is **submitted**, a timesheet is **submitted** or an absence is **requested**. Context for auto-approval rules and step conditions: expense `amount`, `category`; timesheet `hours`, `billable_hours`; absence `days`, `type`.
  - The inbox's final decision applies the same review as the original screen: the expense is approved or rejected (the note is the rejection reason); the timesheet is approved (its hours are marked approved) or rejected; the absence is approved or rejected.
  - Reviewing on the original screen (or returning a timesheet, recalling an expense, cancelling an absence) closes the pending request with that outcome, so it leaves the inbox.
  - Both paths stay open: an approver on the original screen does not need to be the workflow's approver.
- **Change requests and invoices** (since 2026-11-04, same file, test `tests/test_aprobaciones_cambios_facturas_caducidad.py`):
  - With a default *change_request* workflow, **submitting** a change in `/changes` opens a request (context `cost_impact`, `schedule_impact_days`, `impact`). The final decision approves or rejects the change; reviewing it in `/changes` closes the request.
  - With a default *invoice* workflow, moving an invoice from draft to **sent** opens a request and the invoice stays in draft (the API answers 409 with the reason; asking again while pending answers 409 too). Approving it in the inbox marks it sent; rejecting leaves it in draft.
  - Segregation of duties applies: whoever requested it cannot approve it.
- **Timeouts** (hourly job, `on_timeout` per step; fixed 2026-11-04):
  - `reject` closes the request **and applies the rejection to the entity** (expense, timesheet, absence, change, document). Before, the entity stayed pending.
  - `auto_approve` moves to the next applicable step or, if it was the last, approves and applies it. Before, it added 1 to the step and the request stayed pending on a step that does not exist.
  - `escalate` keeps the step, restarts its clock and notifies the step's *escalate to* user, who can now decide it. Before, it skipped the step. If it times out again after escalating, or there is nobody to escalate to, it is rejected.
  - Decisions taken by the clock are signed by the step's approver, else the escalation user, else an active admin of the organization. Each request is processed in its own organization; one failure does not stop the rest.
  - `on_timeout` only accepts `escalate`, `auto_approve` or `reject` (`auto_reject`, which the API documented and the job ignored, is stored as `reject`).
- **Other types still bypass this inbox.** `purchase`, `contract`, `budget` and the rest of the designer types have no code that opens requests (there is no purchase entity at all).
- **No UI to create a request by hand.** The frontend hook `useCreateApprovalRequest` has no caller.

### Portfolio health (Salud del portfolio) — `/projects-dashboard`
*Roles:* Menu: admin, pm, team_lead. Route: admin, pm, team_lead. It is the default landing page for these three roles.

**Purpose.** Portfolio KPIs, read-only:
- total and active projects
- critical and at-risk projects
- open risks
- overdue tasks
- on-time %
- budget usage
- projects by type and by status
- list of critical projects

**How to use it.** Read-only. The period selector (default 30 days) changes only the "projects by type" query.

**Configuration.** None used by this page. The `PROJECT_HEALTH_*` runtime settings (group `health`) are not referenced here.

**Technical notes.** `GET /api/v1/dashboard/projects-health`, `GET /api/v1/dashboard/kpis`, `GET /api/v1/analytics/query/projects_by_type`, `GET /api/v1/risks/all/portfolio`, `GET /api/v1/projects`.

**Limitations.**
- **Status is computed in the browser with fixed thresholds.**
  - Critical: schedule deviation > 0 days, or budget > 100 %.
  - Warning: budget > 80 %, or any alerts.
  - Gauge colours: 80/60 and 90/70.
- **The "high severity" risk count is always 0.** It filters on `r.severity`, but the risk payload has no `severity` field (it has `risk_level`).
- **"Open risks" is capped at 50.** `get_portfolio_risks` uses `.limit(50)`.
- **"Total projects" is capped at 50.** It counts `GET /projects` without `page_size`.
- **The health endpoint ignores the period.** `/dashboard/projects-health` takes no date parameters.

### Projects — `/projects` and `/projects/:id`
*Roles:* Menu: admin, pm, team_lead. Route: any authenticated user, for both the list and the detail page. *New project* is shown to admin and pm. `/projects/:id/analytics` is admin and pm only.

**Purpose.** The project list and the project detail page.

**How to use it.**
1. **List views:** `grid` (default), `list` (sortable columns, column toggle), `gantt` (portfolio or project, with dependencies), `templates`. Filters: search, status.
2. **Create or edit** (admin, pm):
   - name, code, type, client, PM, dates, budget
   - billing type: `recurring_retainer` requires an invoicing day from 1 to 28
   - department
3. **Quick-view modal** tabs:
   - *Info*
   - *Team*: add a member with role and allocation %, or remove one.
   - *Phases*
   - *Documents*
   - *Requests*: client-portal feature requests; reply with `POST /portal/feature-requests/{id}/respond`.
4. **Templates tab:** list templates and instantiate a project from one (`/billing-reports/templates/*`).
5. **Detail page** `/projects/:id`:
   - tabs Overview, Tasks, Team, Risks
   - inline edit of the overview
   - links to `/tasks?project_id=`, `/gantt?project=`, `/contracts-ai?project_id=`
   - *Smart schedule* (AI)
6. Project statuses: `planning | active | on_hold | paused | completed | closed | cancelled | archived`. The status catalogue can be customised at `/settings/project-statuses`.

**Configuration.** Project types and statuses (`/settings/project-types`, `/settings/project-statuses`), runtime `DEFAULT_PROJECT_TYPE` and `DEFAULT_BILLING_TYPE` (group `locale`), departments.

**Technical notes.**
- `GET/POST /api/v1/projects`; `GET/PATCH/DELETE /api/v1/projects/{id}`. Create and update need admin or pm; delete needs admin.
- `/projects/{id}/members`, `/projects/{id}/team`, `/projects/{id}/evm`, `/task-dependencies/{project_id}`.
- Tables: `projects`, `project_phases`, `project_members`.

**Limitations.**
- **50-project cap** (see cross-cutting).
- **The Gantt link opens the wrong view.** "View in Gantt" goes to `/gantt?project=…`, but `GanttPage` ignores the query string and opens with all projects.

### Sprints — `/sprints`
*Roles:* Menu: admin, pm, team_lead. Route: any authenticated user. Writes are `require_any_manager`.

**Purpose.** Scrum sprints per project:
- backlog
- sprint scope
- start and close
- burndown and velocity
- retrospective

**How to use it.**
1. Select a project.
2. *New sprint*: name, goal, dates.
3. Add backlog tasks to the sprint, or remove them (`/sprints/{project_id}/sprints/{sprint_id}/tasks`).
4. *Start*. Only one sprint per project can be active. Starting sets `start_date` if it is empty and stores `planned_points` (the sum of story points).
5. *Close*:
   - `completed_points` = done tasks only
   - `velocity` = points per week
   - every unfinished task is set to `backlog`
6. Retrospective notes: `GET/PUT /projects/{project_id}/sprints/{sprint_id}/retrospective`.
7. Sprint statuses: `planning | active | completed | cancelled`.

**Configuration.** None found.

**Technical notes.**
- `/api/v1/sprints/{project_id}/sprints`, `…/{sprint_id}`, `…/start`, `…/close`, `…/tasks`, `…/burndown`, `/sprints/{project_id}/backlog`, `/sprints/{project_id}/velocity`.
- Tables: `sprints`, `sprint_tasks`, `sprint_retro_notes`.

**Limitations.**
- **Start does not check the current status.** A `completed` sprint can be started again.
- **Close reopens cancelled tasks.** It moves every task whose status is not `done` (including `cancelled`) to `backlog`, bypassing the task transition rules.

### Sprint Planning AI — `/sprint-planning`
*Roles:* Menu: admin, pm. Route: any authenticated user. Generate, status change and delete need admin or pm.

**Purpose.** Proposes the content of a sprint from the project's `todo` tasks and a capacity in story points.

**How to use it.**
1. Pick a project, an optional target sprint and a capacity.
2. Optionally run *Estimate backlog*, which calls the semantic engine (`POST /semantic/estimate/sprint-backlog`).
3. *Generate* creates a plan in `draft`. You can then set it to `accepted` or `rejected`, or delete it. An accepted plan cannot be deleted.

**Configuration.** None found.

**Technical notes.** `POST /api/v1/cmdb/sprint-plans/generate`, `GET /api/v1/cmdb/sprint-plans/{project_id}`, `PATCH /api/v1/cmdb/sprint-plans/{plan_id}/status?status=`, `DELETE /api/v1/cmdb/sprint-plans/{plan_id}`. Tables: `sprint_plans`, `sprint_plan_tasks`.

**Limitations.**
- **It is not AI.** The generator (`cmdb_service.generate_sprint_plan`) is a deterministic greedy fill. It only considers tasks in `todo`, sorted by **story points descending** and then by priority, so large low-priority tasks are picked before small critical ones.
- **Generating changes tasks.** It **writes `story_points = 1` to every unestimated task** and commits that change to `tasks`.
- **Accepting a plan does nothing else.** It only changes `sprint_plans.status`. No tasks are added to the sprint.
- **No backend test** references `/cmdb/sprint-plans`.

### RACI Matrix — `/raci`
*Roles:* Menu: admin, pm, team_lead. Route: any authenticated user. Writes are `require_any_manager`.

**Purpose.** A per-project RACI grid of items against people.

**How to use it.**
- Select a project.
- Add an entry:
  - item type: `deliverable | milestone | phase | custom`
  - free item label
  - user
  - role: `R` Responsible, `A` Accountable, `C` Consulted, `I` Informed

  Saved with `PUT /projects/{project_id}/raci` (batch upsert).
- Delete an entry with `DELETE /projects/{project_id}/raci/{entry_id}`.

**Configuration.** None found.

**Technical notes.** Table `raci_entries`.

**Limitations.**
- **Documentation only.** No other service reads `raci_entries`: no notifications, permissions or approvals use it.
- **No check for exactly one Accountable per item.**
- **Item links are optional.** Item labels are free text and `item_id` is optional.

### Changelog — `/changelog`
*Roles:* Menu: admin, pm, team_lead. Route: any authenticated user. Writes are `require_any_manager`.

**Purpose.** A per-project release changelog.

**How to use it.**
- Select a project.
- Add an entry by hand: version tag, date, type (`feature | bugfix | improvement | milestone | breaking`), title, description.
- *Generate* (`POST /projects/{project_id}/changelog/generate`, `weeks` 1–52, optional `version_tag`) builds entries from tasks in `done` in that window. No AI is involved.
- Delete entries.

**Configuration.** None found.

**Technical notes.** `GET/POST /api/v1/projects/{project_id}/changelog`, `…/generate`, `PATCH|DELETE …/{entry_id}`. Table `project_changelog_entries`.

**Limitations.**
- **No editing in the UI.** `PATCH …/changelog/{entry_id}` exists, but the page never calls it.
- **The generator uses `updated_at`, not `completed_at`.** Any later edit puts an old task back in the window. Done tasks with a null `updated_at` are always included.

### UAT — `/uat`
*Roles:* Menu: admin, pm, team_lead. Route: any authenticated user. Create, update and delete are `require_any_manager`.

**Purpose.** User acceptance test cases per project.

**How to use it.**
- Select a project.
- Create a case:
  - title, steps (description), expected result
  - priority: `low | medium | high | critical`
  - linked task, assignee
- Record each run: set status and actual result. Setting `passed`, `failed` or `blocked` stamps `executed_at`.
- *Export for client* calls `GET /projects/{project_id}/uat/export` and shows the returned report in the page.
- Case statuses: `pending | passed | failed | blocked | skipped`.

**Configuration.** None found.

**Technical notes.** `/api/v1/projects/{project_id}/uat`, `…/{case_id}`, `…/export`. Table `uat_cases`.

**Limitations.**
- **A failed case creates nothing.** Setting `failed` does not open a bug or task.
- **There is a second UAT model.** The client portal has its own UAT tables (`uat_sessions`, `uat_test_cases`, `uat_issues`), not connected to `/uat`.

### Gantt — `/gantt`
*Roles:* Menu: admin, pm, team_lead, employee. Route: admin, pm, team_lead, employee.

**Purpose.** A task Gantt chart with dependencies, critical path, drag rescheduling, AI suggestions and auto-planning.

**How to use it.**
- Pick a project, or *all projects*. Up to 300 tasks are loaded.
- Drag bars to change dates (`POST /tasks/bulk-dates`).
- Shift+drag from one bar to another creates an `FS` dependency (`POST /tasks/dependencies`).
- With a project selected, AI suggestions (overdue or stalled tasks) are loaded from `GET /ai/suggestions/gantt/{project_id}`.
- *Auto-planificar* opens the AI smart-schedule modal.

**Configuration.** None found.

**Technical notes.** `GET /api/v1/tasks?page_size=300`, `GET /api/v1/tasks/dependencies/{project_id}`, `POST /api/v1/tasks/dependencies`, `POST /api/v1/tasks/bulk-dates`, `POST /api/v1/ai-modules/smart-schedule`. Tables: `tasks`, `task_dependencies`.

**Limitations.**
- **Baseline draws nothing.** The *Baseline* toggle needs `baseline_start` and `baseline_end`, which no backend model or schema provides.
- **Saving changes needs admin or pm.** Employees and team_leads can open the page, but dragging (`bulk-dates`) and creating dependencies require admin or pm, so they get 403.
- **`?project=` is ignored.**

### Epics & Roadmap — `/epics`
*Roles:* Menu: admin, pm, team_lead. Route: any authenticated user. Create, update and delete need admin or pm.

**Purpose.** Epics per project and a roadmap timeline.

**How to use it.**
- Select a project.
- Create or edit an epic: title, description, colour, priority, start and end dates, status `open | in_progress | done | cancelled`.
- The roadmap view comes from `GET /epics/roadmap?project_id=`.
- Delete an epic.

**Configuration.** None found.

**Technical notes.** `GET/POST /api/v1/epics?project_id=`, `PATCH/DELETE /api/v1/epics/{id}`, `GET /api/v1/epics/roadmap`. Tables: `epics`, `epic_tasks`, `epic_dependencies`.

**Limitations.**
- **Progress stays at 0 when using the UI only.** Epic progress = done tasks / linked tasks (`epic_tasks`). Linking a task to an epic exists only as an API endpoint (`POST /epics/{id}/tasks/{task_id}`) with **no frontend caller**. Whether imports (e.g. Jira) fill `epic_tasks`: Not verified.
- **team_lead gets 403 when saving.** They see the menu entry, but the backend refuses.
- **Epic `status` is a free string column**, not an enum.

### Deliverables — `/deliverables`
*Roles:* Menu: admin, pm. Route: admin, pm.

**Purpose.** Formal project deliverables with an acceptance step.

**How to use it.**
1. Select a project, or use the overview of all projects (`/deliverables/all/overview`).
2. Create a deliverable (schema `DeliverableCreate`): name, description, format, planned date, owner, client contact, acceptance criteria, milestone, phase.
3. Change its status from the dropdown: `planned | in_progress | in_review | delivered | accepted | rejected`.
4. When a deliverable is `delivered`, *Accept* (`POST …/accept`) and *Reject* (`POST …/reject?reason=`) buttons appear.

**Configuration.** None found.

**Technical notes.** `/api/v1/deliverables/{project_id}`, `…/{del_id}`, `…/{del_id}/deliver`, `…/accept`, `…/reject`. Table `deliverables`.

**Limitations.**
- **Accept can be done without delivering.** The status dropdown sends a plain `PATCH` and offers every status, including `accepted` and `rejected`, so the "only delivered can be accepted" rule of `/accept` can be skipped.
- **Reject checks nothing.** It checks neither the current status nor that the deliverable belongs to the project in the URL (`get_deliverable(db, del_id)`).
- **`/deliver` is unused.** The endpoint, which stores `document_url`, is not called by the page.
- **No notifications.** None are sent.

### Changes (change requests) — `/changes`
*Roles:* Menu: admin, pm. Route: admin, pm. API writes are `require_any_manager`; closing a CAB vote needs admin.

**Purpose.** Project change requests (scope, cost, schedule) with review, plus a CAB (change advisory board) voting board and maintenance windows.

**How to use it.**
1. **By project:** create a CR:
   - title, description, justification
   - impact `low | medium | high`
   - `cost_impact`, `schedule_impact_days`, scope impact
2. CR statuses and actions:

   | From | Action | To |
   |---|---|---|
   | `draft` | Submit | `submitted` |
   | `submitted` / `under_review` | Review | `approved` or `rejected` |
   | `approved` | Implement | `implemented` |

   Editing is allowed in `draft` and `submitted` only. Approved and implemented CRs cannot be deleted.
3. **Pending** tab (admin, pm): all submitted CRs.
4. **CAB & windows** tab:
   - Members vote (`POST /cab/changes/{id}/vote`). The first vote moves the CR to `under_review`.
   - Close with *Cerrar: Aprobada / Rechazada* (`POST /cab/changes/{id}/close`).
   - Maintenance windows are listed from `/cab/windows`.

**Configuration.** None verified for project CRs. `SD_CAB_APPROVAL_RULE`, `SD_CAB_GROUP_ID` and `SD_CHANGE_AUTO_APPROVE_MAX_RISK` (runtime group `service_desk`) are not referenced in `cab_service.py`.

**Technical notes.** `/api/v1/changes/{project_id}`, `…/{cr_id}`, `…/submit`, `…/review`, `…/implement`, `/changes/all/pending`, `/api/v1/cab/changes`, `/cab/windows`, `/cab/changes/{id}/vote`, `/cab/changes/{id}/close`. Tables: `change_requests`, `cab_votes`, `maintenance_windows`, `change_request_windows`.

**Limitations.**
- **Closing ignores the votes.** The person closing picks approved or rejected; the vote tally plays no part.
- **Closing checks no status.** Any CR can be closed, even an `implemented` one.
- **pm gets 403 on Close.** The close buttons are shown to pm, but the endpoint needs admin.
- **Impacts are informational only.** Approving or implementing a CR does not apply `cost_impact` or `schedule_impact_days` to the project budget or dates.
- **No approval engine and no notifications.**

### Risks — `/risks`
*Roles:* Menu: admin, pm. Route: admin, pm. Create, update and delete need admin or pm; the portfolio view is `require_any_manager`.

**Purpose.** A risk register per project and a portfolio-wide view.

**How to use it.**
- Select an active project.
- Create a risk:
  - title, category
  - probability: `very_low | low | medium | high | very_high`
  - impact: `negligible | minor | moderate | major | critical`
  - response type, mitigation and contingency plans
  - owner, review date
  - cost range, schedule impact
- `risk_score` and `risk_level` are computed: `critical ≥3`, `high ≥2`, `medium ≥1`, `low` otherwise.
- Statuses: `identified | analyzing | mitigating | monitoring | closed | materialized`.

**Configuration.** None. The level thresholds are hard-coded in `app/services/risk_scoring.py`.

**Technical notes.** `/api/v1/risks/{project_id}`, `…/{risk_id}`, `/risks/all/portfolio`. Table `risks`.

**Limitations.**
- **Inactive projects can't be picked.** The project picker lists only `status=active` projects, so you cannot add a risk to a project in `planning`.
- **Portfolio view stops at 50.** It returns the top 50 non-closed risks.

### Dependencies — `/dependencies`
*Roles:* Menu: admin, pm, team_lead, employee. Route: any authenticated user. Create and delete need admin or pm.

**Purpose.** Manage dependencies between tasks of a project and see which tasks are blocked.

**How to use it.**
- Select a project.
- Pick a predecessor, a successor, a type and a lag.
- Types offered: `blocks | blocked_by | relates_to | duplicates | cloned_from`.
- Delete a dependency.

**Configuration.** None found.

**Technical notes.** `GET /api/v1/tasks/dependencies/{project_id}`, `POST /api/v1/tasks/dependencies`, `DELETE /api/v1/tasks/dependencies/{dep_id}`. Table `task_dependencies`.

**Limitations.**
- **Two vocabularies for the same field.** This page uses Jira-style link types, while the Gantt stores `FS`. The backend accepts any string for `dependency_type`.
- **Only self-dependencies are blocked.** There is no cycle detection.
- **team_lead and employee get 403 on writes.**

### Git Integration — `/git`
*Roles:* Menu: admin, pm. Route: admin, pm.

**Purpose.** Read-only lists of pull/merge requests and deployments received from GitHub and GitLab webhooks, with automatic linking to tasks.

**How to use it.**
1. Tabs: *PRs*, *Deployments*, *Config*. The Config tab shows the webhook URL.
2. In GitHub or GitLab, point a webhook to:
   - `/api/v1/git/webhooks/github` (signed with `X-Hub-Signature-256`)
   - `/api/v1/git/webhooks/gitlab` (token header)
3. A PR is linked to a task when its branch name or title contains the task code, e.g. `PROJ-123` (regex `[A-Z]{2,10}-\d+`).
4. When a linked PR is merged, the task is set to `done`.

**Configuration.** `GITHUB_WEBHOOK_SECRET`, `GITLAB_WEBHOOK_SECRET` (env, global). If either is empty, all webhooks for that provider are rejected.

**Technical notes.** `GET /api/v1/git/pull-requests`, `GET /api/v1/git/deployments`, plus the two webhook endpoints, `GET /git/pull-requests/{id}`, `POST /git/tasks/{task_id}/branch` and `GET /git/tasks/{task_id}/pr-status`. The last two have no frontend caller. Tables: `git_pull_requests`, `git_deployments`.

**Limitations.**
- **Nothing shows without webhooks.** The page has no data until a webhook is configured. There are no outbound calls to the GitHub or GitLab APIs.
- **One secret per provider for the whole install.** The webhook secret is not per organisation.
- **Task lookup is not filtered by organisation.** `find_task_by_ref` searches `Task.code` across all organisations.
- **`#123` references never link.** They are compared with the UUID `tasks.id`.
- **Rows have no organisation.** `git_service.py` never sets `organization_id` on the rows it writes. Whether tenant scoping hides other tenants' PRs: Not verified.
- **Auto-close skips the transition rules.** It sets `done` directly.

### Wiki — `/wiki`
*Roles:* Menu: admin, pm, team_lead, employee, hr. Route: any authenticated user. Creating, editing and deleting spaces and pages, and restoring versions, need admin or pm. Reading and search are open to all.

**Purpose.** A block-based wiki: spaces, pages, versions, tags, search, real-time co-editing, and AI "improve text".

**How to use it.**
- Create a space, then pages inside it.
- Edit blocks. A per-block *Improve* button calls `/ai/chat`.
- Each save creates a version. You can list versions and restore one.
- Tags per space: `/cmdb/wiki-tags/*`.
- Search: `GET /epics/wiki/search`.
- Co-editing uses Yjs over the WebSocket `/api/v1/ws/doc/{doc_id}` (token from `/ws/token`). A peer counter shows how many editors are active.

**Configuration.** None found.

**Technical notes.** `/api/v1/epics/wiki/spaces`, `/spaces/{id}/pages`, `/pages/{id}`, `/pages/{id}/versions`, `/pages/{id}/restore/{n}`, `/wiki/search`, `/api/v1/cmdb/wiki-tags/*`. Tables: `wiki_spaces`, `wiki_pages`, `wiki_versions`, `wiki_tags`.

**Limitations.**
- **Read-only users still see edit buttons.** `WikiPage.tsx` has no role check, so employees, hr and team_leads get 403 when they try to create or edit.
- **Templates and comments have no UI.** Endpoints exist (`/epics/wiki/templates`, `/epics/wiki/pages/{id}/comments`) but the page does not use them.
- **Co-editing across several API workers: Not verified.**

### Meeting Assistant — `/meetings-ai`
*Roles:* Menu: admin, pm, team_lead. Route: any authenticated user. Processing needs an internal user.

**Purpose.** Turns a pasted meeting transcript into a summary and action items, and creates tasks from those actions.

**How to use it.**
1. Enter:
   - title
   - platform: a label only, e.g. `teams`
   - participants, duration
   - optional project
   - the transcript **text**

   A *demo transcript* button fills in an example.
2. *Process* calls `POST /ai-modules/meetings/process`. The LLM does a map-reduce analysis.
3. Open a processed meeting.
4. *Create tasks* from selected actions (`POST /ai-modules/meetings/{id}/create-tasks`). This needs a project, otherwise you get `project_id_required`.

**Configuration.** AI provider only.

**Technical notes.** `GET /api/v1/ai-modules/meetings` (last 50), `GET /ai-modules/meetings/{id}`, `POST …/process`, `POST …/{id}/create-tasks`. Tables: `ai_meetings`, `ai_meeting_actions`.

**Limitations.**
- **Text only.** No audio upload or transcription on this page, and no integration that fetches Teams, Zoom or Meet meetings.
- **Only the last 50 meetings are listed.**
- **No backend test** references these endpoints.

---

## People & Resources

Who works here, how loaded they are, what they know, how they are evaluated and what an hour of their time costs. The screens live in the sidebar group **Team & People** (plus **Estructura de coste** under *Clients & Finance*). Everything below was read from the code on 03-11-2026 (frontend pages, API clients, FastAPI endpoints, services, models). Nothing was exercised in a running instance unless stated; where behaviour could only be inferred, it says so.

Two separate planning stores coexist and are easy to confuse: **capacity plans** (`capacity_plans`, edited in */capacity*) and **resource bookings** (`resource_bookings`, edited in the *Resources → Heatmap* tab and in */resource-scheduler*). *Resource Forecast* adds both together; the other screens read only one of them.

### Roles and permissions

**Roles that exist.** `UserRole` in `app/models/user.py`: `admin` (tenant administrator, sees costs), `pm`, `team_lead`, `hr`, `employee`, `subcontractor`. `users.role` is a `String(100)`, not a DB enum. `users.is_superadmin` is a separate boolean for the cross-tenant platform owner. `users.status`: `active | inactive | vacation | leave`.

**Backend guards** (`app/core/deps.py`): `RequireRole(...)` returns 403 unless the role matches; `is_superadmin` always passes. Shortcuts: `require_admin` (admin), `require_admin_or_hr`, `require_admin_or_pm`, `require_any_manager` (admin, pm, team_lead, hr), `require_internal_user` (everyone except subcontractor), `require_superadmin`. Tenant isolation is applied automatically by `TenantSession` (`app/db/session.py`), which adds `organization_id` filters to ORM queries. `enforce_abac()` is **fail-open**: if the organisation has no active ABAC policies it checks nothing (its own docstring says so).

**Frontend guards.** `ProtectedRoute roles={[...]}` in `App.tsx` redirects to `/403`; the sidebar (`Layout.tsx`, `NAV_GROUPS`) hides items whose `roles` don't match. `hasRole()` in `AuthContext.tsx` is a plain string comparison: unlike the backend, it does **not** let `is_superadmin` through.

**Default landing page by role** (`landingPathFor` in `App.tsx`): employee → `/work-dashboard`; hr → `/team-dashboard`; admin/pm/team_lead → `/projects-dashboard`; anything else → `/tasks`.

| Screen | Sidebar shows it to | Route allows | Main backend guard(s) |
|---|---|---|---|
| `/team-dashboard` | admin, pm, hr, team_lead | same | per call (see module) |
| `/resources` | admin, hr, pm | same | `require_any_manager`; editing a person: admin only |
| `/capacity` | admin, hr, pm | same | board/create: any logged-in user; move/delete: `require_any_manager` |
| `/resource-forecast` | admin, pm, team_lead | same | `require_any_manager` (includes hr, but hr can't open the route) |
| `/resource-scheduler` | admin, pm, team_lead | same | `require_any_manager` |
| `/skills` | admin, pm, hr, employee | **any logged-in user** | matrix/search/catalogue writes: `require_admin_or_hr` |
| `/org-chart` | admin, pm, hr | same | editing: `require_admin`; another person's approval chain: `require_admin_or_pm` |
| `/okrs` | admin, pm, hr | same | writes: `require_any_manager`; check-in: `require_internal_user` |
| `/performance-reviews` | admin, pm, hr | same | cycles: `require_admin_or_hr`; 360 campaigns: `require_any_manager`; reviewer edits only their own review |
| `/training` | admin, pm, hr, employee | **any logged-in user** | courses/certificate creation: `require_admin_or_hr` |
| `/user-costs` | admin, hr | same | `require_admin_or_hr` on every endpoint |

Mismatches found:
- `team_lead` gets no sidebar link to `/skills` or `/training`, but can open both by URL.
- `hr` gets no sidebar link to `/resource-forecast` or `/resource-scheduler`, and the routes refuse hr, even though the backend would accept hr.
- `employee` and `team_lead` can't open `/performance-reviews`, yet that page is the only place to fill in a review assigned to them. The assignment notification, the assignment e-mail and the daily reminder all send them there (`action_url="/performance-reviews"` in `performance_service.py` and `perf_reminder_service.py`), and the route redirects them to `/403`. The e-mail link is also relative (`href='/performance-reviews'`), so it won't open from a mail client. **Practical effect: only admin/pm/hr can complete self, peer or upward reviews from the UI.**
- The frontend `Role` type also lists `finance`, `sales` and `client`, which the backend `UserRole` doesn't have.

**Custom roles and module access** (`app/core/modulos.py`, since 2026-11-03).
- Settings → Roles lists one *system* row per base role and organization, plus the custom roles. Each has a `module_access` map over 19 modules (dashboard, projects, tasks, imputations, timesheets, resources, capacity, profitability, pipeline, contracts, risks, changes, deliverables, skills, absences, reports, alerts, exports, settings).
- A module set to off is **closed**: its API routes return 403 ("Tu rol no tiene acceso al módulo …"), its screens disappear from the menu and their routes redirect to /403. A module missing from the map stays open.
- The effective row is the **custom role assigned to the person** (Settings → Usuarios → Editar → *Rol personalizado*, `users.custom_role_id`), or else the system row of their base role in their organization.
- It **only restricts**: the base role (`users.role`) still decides what a person may do. An **admin is never restricted** (so nobody can lock the organization out), nor is the superadmin.
- Always open even with *settings* closed: `GET /settings/org-defaults` and `GET /settings/general` (the app needs them to start).
- `GET /auth/me` and the login response carry `blocked_routes` (screen routes closed for that user).
- Validation: unknown module keys → 422; a custom role cannot use a base-role name; a custom role from another organization cannot be assigned (422); the *Rol* field accepts only base roles (it used to list custom roles and saving one failed).
- Not enforced: the `permissions` JSON of a role (no screen edits it).
- Before this revision role names were unique across the whole installation, so the second organization that opened Settings → Roles failed when seeding `admin`; they are now unique per organization (migration 120).

**Who may edit a person** (`_autorizar_edicion` in `app/services/user_service.py`): an admin may change anything. Anyone else may edit only their own record, and only the fields of `UserSelfUpdate`: `email, first_name, last_name, full_name, phone, job_title, avatar_url, timezone`. HR can't edit other users.

#### User profile panel (`frontend/src/components/layout/UserProfilePanel.tsx`)
Open it by clicking your name or avatar at the bottom of the sidebar. It has four tabs:
1. **Perfil**: email, first name, last name, job title, phone and avatar URL, saved with `PATCH /api/v1/users/me`. Note that **users can change their own e-mail here**, and nothing in the panel asks for re-verification.
2. **Apariencia**:
   - Theme: `freight` (default), `dark`, `midnight`, `slate`, `light`, `high-contrast`, `system` (follows `prefers-color-scheme`).
   - Accent: 8 presets or a custom colour picker. "None" uses the theme's own accent.
   - Density: `compact | normal | comfortable`.
   - The theme is applied immediately when you click it. Nothing is stored until you press save, which sends `PATCH /api/v1/users/me/preferences` (table `user_preferences`), and `useUserPreferences` re-applies the stored values to the DOM on every load.
3. **Idioma**: `es`, `en`, `zh` (`APP_LANGUAGES` in `i18n/appTranslations.mjs`). The choice is saved to preferences and mirrored to `localStorage` (`contecflow_operator_lang`).
4. **Seguridad**: change password (`POST /api/v1/auth/change-password`) and MFA status. The MFA button only navigates to `/mfa` (`MFAPage`); setup happens there through `/api/v1/auth/mfa/setup`.

---

### Team dashboard — `/team-dashboard`
*Roles:* admin, pm, hr, team_lead. This is hr's landing page. Its sidebar label is "Capacidad del equipo".

**Purpose.** A read-only snapshot of the team: headcount, OKRs, reviews, training and today's absences.

**How to use it.** Open the page and pick a period (30/90/365 days). It shows:
- KPI cards: team size, OKRs (and how many are completed), pending reviews, trainings (completed / in progress), people absent today (approved absence spanning today), and absence requests pending approval.
- Gauges for utilisation, OKR completion and training completion.
- Bars for headcount by department and by role (top 6 of each).
- An OKR breakdown: completed / in progress / not started / cancelled.

There are no actions on this page.

**Configuration.** None found.

**Technical notes.** It makes six parallel reads:
- `GET /api/v1/users?page_size=200`
- `GET /api/v1/analytics/utilization/advanced`
- `GET /api/v1/okrs`
- `GET /api/v1/performance/my-reviews`
- `GET /api/v1/training/enrollments`
- `GET /api/v1/absences`

**Limitations (measured in code).**
- **The utilisation gauge never shows.** The page reads `avg_utilization_pct`, but `analytics_service.get_advanced_utilization` returns `summary.actual_utilization_pct`/`booked_utilization_pct` and no `avg_utilization_pct`. The period selector is also sent as `date_from/date_to`, which that endpoint ignores (it only takes `weeks_ahead`).
- **The "pending reviews" KPI shows the viewer's own pending reviews** (`/performance/my-reviews`), not the team's. Its "completed" sub-count checks status `completed`, which doesn't exist (`ReviewStatus` is `pending | submitted | approved`), so it is always 0.
- Truncation: users and absences now load every page (2026-11-04; `/absences` accepts `page`/`page_size` and returns the total, `limit` is kept as an alias). OKRs are only those of the current year (the endpoint defaults `year` to the current year).
- The period selector affects none of the other cards either: none of their queries takes the dates.

### Resources — `/resources`
*Roles:* admin, hr, pm. The edit (pencil) button is admin-only, and rates are shown to admin/hr.

**Purpose.** The team's current load, a bookings heatmap, a "who fits this job" search (SmartMatch) and a burnout monitor.

**How to use it.** The KPI bar shows total people, available (<60 % load), overloaded (>100 %) and average load. The page has four tabs:
1. **Equipo**: cards in a grid or list. Search by name/title/department and filter by department.
   - As admin, use the pencil to edit email, name, title, department (from Settings → departments), weekly capacity and hourly rate. If capacity is left blank, the frontend sends 40.
2. **Heatmap** (`components/ResourceHeatmap.tsx`): people × weeks (4–12 selectable) coloured by status: `free` <20 %, `ok`, `high` >85 %, `overloaded` >100 %.
   - **+ Reserva** creates a booking: user, project, start/end date, hours per day, and type `hard` (confirmed, counts against capacity) or `soft` (tentative, displayed only).
   - The bookings panel lists bookings and deletes them, which is a soft delete.
3. **SmartMatch**: enter skills (from the catalogue, or quick chips: React, Python, AWS…), a role, hours needed, dates and an optional maximum hourly rate, then press search.
   - It returns the top 5 candidates scored on skills, availability, cost and active tasks.
   - The maximum rate excludes candidates rather than penalising them.
4. **Burnout Monitor**: filter by Todos/Atención (yellow)/Riesgo (orange)/Crítico (red). **↻ Recalcular** persists snapshots.

**Configuration.** `DEFAULT_WEEKLY_CAPACITY_HOURS` (env, default 40) is used when a user has no capacity. `DEFAULT_WORKING_HOURS_PER_DAY` (env, default 8) is the default `hours_per_day` for a booking.

**Technical notes.**
- `GET /api/v1/users/load`: load = hours **imputed** this ISO week (Mon–Sun) ÷ weekly capacity. It also returns month hours, active tasks and active projects.
- `PATCH /api/v1/users/{id}`
- `GET /api/v1/bookings/heatmap?weeks=` (Mon–Fri only, hard bookings only), `GET/POST/PATCH/DELETE /api/v1/bookings`
- `POST /api/v1/billing-reports/smartmatch`
- `GET /api/v1/resources/burnout-risk`, `POST /api/v1/resources/burnout-risk/compute` (rate limit 10/min)
- Tables: `users`, `imputations`, `resource_bookings`, `burnout_risk_snapshots`, `skills`, `user_skills`.
- Burnout score (`raci_service.compute_user_burnout_risk`) is based on the last 8 weeks of imputed hours:
  - +25 if this week >100 %
  - +20 if the 4-week average >90 %
  - +10 per consecutive week >100 % (counted from 2 weeks on)
  - +20 if >130 %
  - The total is capped at 100. Levels: red ≥70, orange ≥45, yellow ≥20, otherwise green.

**Limitations.**
- **Load is based on hours already imputed in the current week**, so on Monday almost everyone shows as "available" (<60 %). It does not reflect planned work.
- **↻ Recalcular doesn't refresh the list** (`onSuccess: () => {}`; the query keeps a 5-minute `staleTime`). The live list is computed on every GET anyway.
- **`burnout_risk_snapshots` is written but never read**: the only references are the write in `compute_and_save_burnout_snapshots`.
- Thresholds are code constants, not settings:
  - Burnout points/levels: `_SENALES_DE_AGOTAMIENTO`, `_NIVELES_DE_AGOTAMIENTO`.
  - Heatmap 20/85/100 %: `bookings_service.py`.
  - Card thresholds 60/85/100 %: frontend.
- The heatmap ignores absences and holidays.
- Creating a booking only blocks an exact duplicate (same user and project with overlapping dates). There is no capacity check.
- SmartMatch's "role" filters on `users.role` (admin/pm/…), not on job title.

### Capacity planning — `/capacity`
*Roles:* admin, hr, pm.

**Purpose.** Week-by-week planned hours per person and project (`capacity_plans`), as a drag-and-drop board.

**How to use it.**
1. Choose a horizon (4/8/13/26 weeks) and optionally a department.
2. Click an empty cell, or press **Nueva asignación**, and fill in person, project (active projects only, optional), week, hours and notes.
   - The server rejects an assignment that pushes the week over the person's weekly capacity (400 *Sobreasignación*).
   - It also rejects one that overlaps an **approved** absence (409).
3. Drag a plan chip to another person or week to move it. Use the trash icon (with confirmation) to delete it; this is a soft delete (`is_active=false`).

Cell colour: >100 % red, >85 % amber, >60 % accent, otherwise green.

**Configuration.** `DEFAULT_WEEKLY_CAPACITY_HOURS` (fallback when a user has no capacity).

**Technical notes.**
- `GET /api/v1/capacity/board?week_from&week_to`, `POST /api/v1/capacity/plans`, `PATCH /api/v1/capacity/plans/{id}`, `DELETE /api/v1/capacity/plans/{id}`
- Creation logic: `psa_flows.create_capacity_plan_flow`.
- Table: `capacity_plans` (`user_id, project_id, week_start, planned_hours, is_active, notes, created_by`).
- API-only endpoints with no UI caller (grep of `frontend/src`): `GET /capacity/overview`, `GET /capacity/plans`, `GET /capacity/availability`, `GET /capacity/leveling`.

**Limitations.**
- **Moving a plan by drag-and-drop skips both the over-capacity check and the absence check.** `capacity_service.update_capacity_plan` just sets the fields.
- **`POST /capacity/plans` and `GET /capacity/board` only require a logged-in user** (`get_current_user`). Through the API, an employee or subcontractor can read the whole board and create plans for any `user_id`; only move/delete require a manager.
- ~~People and projects stop at 50.~~ Fixed 2026-11-04: both lists load every page.
- Capacity plans are not shown on the Resources heatmap or in the Visual Scheduler, which read bookings only.

### Resource forecast — `/resource-forecast`
*Roles:* admin, pm, team_lead.

**Purpose.** A forward-looking load heatmap per person and week, plus an executive summary.

**How to use it.**
1. Pick a horizon (4/8/13/26/52 weeks; at most 16 columns are drawn) and a department.
2. Choose a view:
   - **Heatmap**: click a person to open their per-week detail panel.
   - **Resumen**: average team load, at-risk weeks, and similar figures.

Status per week: `overloaded` >100 %, `high` >85 %, `medium` >50 %, `low` >10 %, otherwise `available`.

**Configuration.** `DEFAULT_WEEKLY_CAPACITY_HOURS`, `DEFAULT_WORKING_HOURS_PER_DAY`.

**Technical notes.**
- `GET /api/v1/resource-forecast/weeks?weeks=4..52&department&from_date`, `GET /api/v1/resource-forecast/summary`, `GET /api/v1/resource-forecast/users/{id}`
- API-only: `/resource-forecast/availability`, `/resource-forecast/utilization-trend`.
- Committed hours per week (`resource_analytics.get_user_week_hours`) = booking hours on weekdays + `capacity_plans.planned_hours`.
- Performance: the heatmap runs one query set per user per week (a nested loop in the endpoint), so cost grows with users × weeks. Not measured.

**Limitations (code reading, not reproduced at runtime).**
- ~~Deleted bookings and deleted capacity plans are still counted; absences are not subtracted from capacity.~~ Fixed 2026-11-03: `get_user_week_hours` skips rows with `is_active = false`; approved absences (working days × `DEFAULT_WORKING_HOURS_PER_DAY`, before a fixed 8 h) are subtracted from that week's capacity in the heatmap, the person detail, *availability* and the summary, and each week returns `absence_hours`. A week with zero capacity and some committed hours shows 100 %. Test: `tests/test_proyeccion_recursos_ausencias_y_borrados.py`.
- `GET /resource-forecast/users/{id}` is limited to admin, pm, team_lead, hr or the person themself (since 2026-11-03; before, any user could read anyone's load).
- **`soft` (tentative) bookings count the same as `hard` ones.**
- Public holidays are not subtracted from capacity.
- Backend tests: `tests/test_resource_forecast.py` exists. No frontend tests.

### Visual scheduler — `/resource-scheduler`
*Roles:* admin, pm, team_lead.

**Purpose.** A Runn-style timeline for creating and moving **bookings** with the mouse.

**How to use it.** Choose 8/12/16/24 weeks and an optional department. There are two modes:
- **Scheduler**:
  - Mouse-down on an empty cell and drag right to select a range; a panel opens to set project, hours per day (default 8) and `hard/soft` (default `soft`), then save.
  - Drag an existing bar sideways to shift it by whole weeks.
  - Click a bar to edit or delete it.
  - Keys: `Esc` cancels; `Delete`/`Backspace` deletes the selected booking after confirmation.
- **Assign**: drag a person onto a project row. This pre-fills a `soft` booking from this Monday for 4 weeks.

Cell shading comes from the forecast endpoint.

**Configuration.** None beyond the forecast settings.

**Technical notes.** `GET /api/v1/resource-forecast/weeks`, `GET /api/v1/bookings?page_size=500` (the service ignores `page_size` and returns all active bookings of the organisation), `POST/PATCH/DELETE /api/v1/bookings`. Table: `resource_bookings`.

**Limitations.**
- **Mouse-only.** Drag handling uses `mousedown/mousemove/mouseup`; there are no touch handlers, so it won't work on a touchscreen.
- No capacity or absence check when creating or moving a booking.
- The shading inherits the forecast rules above (soft counted as hard; holidays not subtracted).
- No frontend tests.

### Skills — `/skills`
*Roles:* the route is open to any logged-in user; the sidebar shows it to admin, pm, hr and employee. The **Catálogo** tab appears only for admin/hr.

**Purpose.** The skills catalogue, each person's skill levels, the team skills matrix and a staffing search.

**How to use it.** Levels: `basic`, `intermediate`, `advanced`, `expert` (1–4). Categories: `technical, language, methodology, tool, soft, certification`. Tabs:
1. **Matriz**: people × skills.
2. **Perfiles**: click a person to manage their skills: level, years of experience, certified flag/name, notes. The **History** sub-tab shows level changes.
   - An employee can add or modify only their own skills.
   - Removing any skill requires admin/hr.
3. **Staffing**: choose skills and a minimum level to list matching people.
4. **Catálogo** (admin/hr): create or delete skills.

**Configuration.** None found.

**Technical notes.**
- `GET/POST /api/v1/skills/catalog`, `PATCH/DELETE /api/v1/skills/catalog/{id}`
- `GET/POST /api/v1/skills/users/{user_id}` (upsert; writes `skill_history` when the level changes), `DELETE /api/v1/skills/users/{user_id}/{user_skill_id}`
- `GET /api/v1/skills/users/{id}/history`, `GET /api/v1/skills/matrix`, `GET /api/v1/skills/search`
- Tables: `skills`, `user_skills`, `skill_history`.

**Limitations.**
- **For pm and employee the default tab (Matriz) and Staffing call admin/hr-only endpoints**, so the requests fail with 403. Only Perfiles works for them.
- An employee can add skills to their own profile but can't remove them.
- Perfiles loads `GET /users` with the default `page_size` of 50, then fires one `GET /skills/users/{id}` per card (N+1 requests).
- `subcontractor` gets 403 on `/users` (`require_internal_user`).

### Org chart — `/org-chart`
*Roles:* admin, pm, hr. Editing is admin-only.

**Purpose.** The reporting hierarchy, the positions list and the approval chains derived from `users.manager_id`.

**How to use it.** Three tabs:
1. **Árbol jerárquico**: an expandable tree; the first 2 levels are open by default. As admin, use edit on a node to change job title, department and manager.
2. **Posiciones**: a table filterable by department and search, where admin can edit title, department and manager inline.
3. **Cadenas de aprobación**: the manager chain for yourself, or (admin/pm) for a selected person.
   - The explanatory cards say expenses, absences and timesheets are approved by the direct manager. Not verified here that every approval flow actually uses this chain.

**Configuration.** The department list comes from Settings (`GET /api/v1/settings/departments`).

**Technical notes.**
- `GET /api/v1/users/org-chart`, `GET /api/v1/users`
- `PATCH /api/v1/users/{id}` (title/department), `PATCH /api/v1/users/{id}/manager` (`require_admin`)
- `GET /api/v1/users/me/approval-chain`, `GET /api/v1/users/{id}/approval-chain` (`require_admin_or_pm`)
- Chain walk: `user_service.approval_chain_for_user` follows `manager_id` and stops on cycles.

**Limitations.**
- **hr can open the page but gets 403 when selecting another person's approval chain**, because that endpoint is admin/pm only.
- ~~`GET /users` stops at 50 people in selectors.~~ Fixed 2026-11-04: every page is loaded.
- Saving a node makes two sequential calls (profile, then manager). If the second fails, the first is already saved.

### OKRs — `/okrs`
*Roles:* admin, pm, hr.

**Purpose.** Objectives with measurable key results and progress check-ins.

**How to use it.**
1. Filter by year and period: `Q1–Q4`, `H1`, `H2`, `annual`.
2. **New objective**: title, description, owner, department (`team_id`, free text), linked project, period, year, and status `draft | active | completed | cancelled`.
3. **Add a key result** to an objective: title, type (`percentage | number | boolean | currency`), target, unit, owner, due date.
4. **Check-in** on a KR with a value and a note.
   - KR progress = `current/target × 100`, clamped to 0–100. For `boolean` it is 100 if the value is ≥1.
   - Objective progress = the mean of its KRs' progress.
5. Objectives and KRs are deleted with a soft delete.

The KPI row shows active objectives, average progress and on-track objectives (≥60 %).

**Configuration.** None found.

**Technical notes.**
- `GET/POST /api/v1/okrs`, `PATCH/DELETE /api/v1/okrs/{id}`
- `POST /api/v1/okrs/key-results`, `PATCH/DELETE /api/v1/okrs/key-results/{id}`, `POST /api/v1/okrs/key-results/{id}/checkin`
- API-only: `POST /api/v1/okrs/key-results/{id}/sync-from-tasks` (sets the KR from the linked project's task progress; no button calls it).
- Tables: `okr_objectives`, `okr_key_results`, `okr_checkins`.
- E2E test: `tests_e2e/test_e2e_okrs.py`.

**Limitations (code reading, not reproduced at runtime).**
- **A deleted KR keeps showing and keeps counting.** `Objective.key_results` has no `is_active` filter: `serialize_objective` lists every KR and `propagate_to_objective` averages them all.
- **Any internal user can check in on any KR.** The guard is `require_internal_user` with no ownership check, although the code comment says "avance del propio KR" (progress on one's own KR).
- `OKRStatus` has no `in_progress`. Objective status never changes automatically: reaching 100 % doesn't mark the objective `completed`.
- Organisation scoping in `list_objectives` keeps an objective only if its owner or its project belongs to the organisation. On top of that, the automatic tenant filter on `okr_objectives.organization_id` also applies.

### Performance reviews — `/performance-reviews`
*Roles:* admin, pm, hr. Cycle management buttons are admin/hr only (`isManager` = admin or hr). See the role caveat at the top: employees and team leads can't reach this page.

**Purpose.** Review cycles with configurable questionnaires, individual and 360° reviews (self / peer / manager / upward), KPI dashboards and development plans.

**How to use it.** Tabs: **Ciclos**, **Pendientes** (my reviews), **Planes de desarrollo**, and **KPIs** (admin/hr only). The process:
1. **Nuevo ciclo** (admin/hr): name and dates, plus a question template: *Por defecto* (5 ratings + 3 text questions), *Clonar de otro ciclo*, or *Vacía*.
   - Question types: `rating_5, rating_10, scale_likert, yes_no, text_short, text_long`.
   - Questions can be edited while the cycle is a draft.
2. **Activate** the cycle. Status goes `draft → active`.
3. Assign reviews in one of two ways:
   - **Asignar** (admin/hr): reviewee + type + reviewer, restricted to eligible reviewers from the org chart (peers share a team or department; manager = `manager_id`; upward = direct reports).
   - **Nueva campaña 360°** (`require_any_manager` on the backend): a subject plus self/manager/peer/upward reviewers. It has an anonymity threshold (default 3, minimum 1) and is active immediately by default.
4. The reviewer opens the review from **Pendientes**, saves answers and **submits** it. Status goes `pending → submitted`. Only the assigned reviewer can edit, and only while the cycle isn't closed.
5. **Dashboard** per campaign: aggregated by reviewer type, with PDF export (admin/hr) and 360° history per person.
6. **Close** the cycle. Status goes `active → closed` and answers freeze.
7. **Planes de desarrollo**: plan status `draft | active | completed | archived`, with goals `pending | in_progress | done | blocked | cancelled`. A plan can be created by its subject, the subject's direct manager, or admin/hr.

**Configuration.** No settings. Reminders run daily at 09:00: Celery beat entry `perf-reminders-daily` (added 2026-11-03; before, they only existed as the APScheduler job `scheduled_perf_reminders`, which is off whenever Celery beat runs). They can also be triggered from the KPIs tab (`POST /performance/admin/run-reminders`). Window and dedup are code constants: `REMINDER_WINDOW_DAYS=7`, `DEDUP_WINDOW_HOURS=20`.

**Technical notes.**
- 34 routes under `/api/v1/performance/*`:
  - Cycles: `GET/POST /cycles`, `POST /cycles/{id}/activate`, `POST /cycles/{id}/close`.
  - Questions: `GET/POST /cycles/{id}/questions`, `PATCH/DELETE /questions/{id}`.
  - Reviews: `GET /cycles/{id}/reviews` (filtered by `_can_view_review`), `GET /my-reviews`, `POST /cycles/{id}/reviews`, `PATCH /reviews/{id}`, `POST /reviews/{id}/submit`.
  - 360° campaigns: `GET/POST /cycles/{id}/campaigns`, `GET /campaigns/{id}/dashboard`, `GET /campaigns/{id}/dashboard.pdf`.
  - KPIs: `GET /kpis`, `GET /cycles/{id}/kpis`.
  - Development plans: `GET /users/{id}/dev-plans`, `GET/POST/PATCH /dev-plans…`, `POST /dev-plans/{id}/goals`, `PATCH/DELETE /dev-goals/{id}`.
- Tables: `review_cycles`, `review_questions`, `review_360_campaigns`, `performance_reviews`, `development_plans`, `dev_goals`.

**Limitations.**
- ~~Reminders don't run in Celery Beat mode.~~ Fixed 2026-11-03: `perf-reminders-daily` in `beat_schedule`.
- `ReviewStatus.approved` is never set anywhere, so there is no approval step after submission.
- API-only, no button: closing a single 360° campaign (`POST /campaigns/{id}/close`), `GET /campaigns/{id}/reviews`, `POST /cycles/{id}/questions/seed-default`, `POST /cycles/{id}/clone-questions/...`. The last two are reachable only through the *Nuevo ciclo* options.
- No frontend tests for this 2,256-line page.

### Training & certifications — `/training`
*Roles:* the route is open to any logged-in user; the sidebar shows it to admin, pm, hr and employee. Create and edit buttons for courses and certificates are shown to admin/hr.

**Purpose.** The course catalogue, the enrolment list and employee certifications with expiry warnings.

**How to use it.** Tabs:
1. **Catálogo**: courses with title, description, provider, category, duration (h), URL and cost. Admin/hr can create, edit and delete.
2. **Inscripciones**: a read-only list. Status: `planned | in_progress | completed | cancelled`.
3. **Certificaciones**: name, issuer, certificate ID, obtained/expiry dates, URL and notes.
   - Banners list expired certificates and those expiring within 60 days.
   - Admin/hr create certificates. Editing and deleting is allowed to the owner or to admin/hr.

**Configuration.** None. The 60-day "expiring soon" window is a constant in `training_service.py`.

**Technical notes.**
- `GET/POST /api/v1/training/courses`, `PATCH/DELETE /api/v1/training/courses/{id}`
- `GET/POST /api/v1/training/enrollments`, `PATCH/DELETE /api/v1/training/enrollments/{id}`
- `GET/POST /api/v1/training/certifications` (`?expiring_days=`), `PATCH/DELETE /api/v1/training/certifications/{id}`
- Tables: `training_courses`, `training_enrollments`, `user_certifications`.

**Limitations.**
- **There is no way to enrol anyone from the UI.** `trainingApi.enroll` exists but no component calls it, and there is no control to change an enrolment's status. Enrolments only exist if created through the API or seed data.
- Most training endpoints answer with `x-api-deprecated: true` / `deprecation: true` headers. No successor API was found (Not verified whether one is planned).
- An employee can't create their own certificate (admin/hr only) but can edit and delete it once it exists.
- The certificate list returns every certificate in the organisation to any logged-in user (no per-user filter unless `user_id` is passed).

### Cost structure — `/user-costs`
*Roles:* admin, hr (frontend and backend). Sidebar label: "Estructura de coste", under *Clients & Finance*.

**Purpose.** The real employer cost per hour of each person, versioned over time. This is the rate used to cost every timesheet entry (imputation).

**How to use it.**
1. **Country presets**:
   - **Seed** loads 18 global defaults (ES 32 % / 1,700 h, PT, FR, DE, IT, GB, IE, NL, PL, US, MX, BR, AR, CO, CH, BE, SE, AT).
   - You can create organisation-specific overrides with ISO code, name, currency, employer cost % and productive hours per year. Only organisation-scoped presets can be deleted.
2. **Users table**: cost per hour and source for each person.
   - `profile`: a versioned cost profile is active.
   - `legacy_hourly_rate`: falls back to `users.hourly_rate`, which admins also edit in Resources.
   - `none`: no cost data.
3. **New version** for a person: valid-from date, country preset, currency, gross annual salary, employer cost %, extra annual costs, productive hours per year.
   - The live preview computes `total = salary × (1 + %) + extras` and `cost/h = total ÷ hours`.
   - Saving closes the previous open profile on the day before the new valid-from date.
4. KPIs: average cost per hour, total annual cost (approximate), people without cost data, and countries configured.

**How it connects to timesheets.**
- `imputation_service.resolve_user_rate` uses the active profile on the entry's date, or else `users.hourly_rate`.
- **Without either, a non-subcontractor can't log time** (400 "No puedes imputar horas sin tener una tarifa horaria asignada").
- Each imputation stores `hourly_rate_snapshot` and `cost_amount = rate × hours`, so later salary changes don't recompute hours already logged.

**Configuration.** `DEFAULT_CURRENCY` (env). The presets are data, not settings.

**Technical notes.**
- `GET/POST /api/v1/user-costs/countries`, `POST /api/v1/user-costs/countries/seed`, `PATCH/DELETE /api/v1/user-costs/countries/{id}`
- `GET/POST /api/v1/user-costs/users/{id}/profiles`, `GET /api/v1/user-costs/users/{id}/active`, `POST /api/v1/user-costs/users/{id}/preview`
- `PATCH/DELETE /api/v1/user-costs/profiles/{id}`
- `GET /api/v1/user-costs/summary?on=` (hard cap 2,000 users, returns `truncated`)
- Service: `app/services/cost_service.py`. Tables: `country_employer_costs`, `user_cost_profiles`.

**Limitations.**
- **Profiles can't be edited or deleted from the UI.** `PATCH`/`DELETE /profiles/{id}` exist and are not called; the only action is adding a new version.
- "Coste anual total (aprox.)" multiplies each person's cost per hour by a hard-coded 1,700 h, ignoring their real productive hours.
- **Possible currency issue (code reading):** imputations store `rate × hours` in the profile's currency. The currency-converting helper `cost_service.cost_amount` and its wrapper `imputation_service.compute_cost` are not used when imputations are created. So a profile in a currency other than the organisation's would be costed unconverted. Not reproduced.
- `cost_service.py`'s docstring says it is used by "profitability, project cost forecasts, dashboards". A grep finds it imported only by `imputation_service.py` and the `user_costs` endpoints. Other modules read the stored `cost_amount` (Not verified per module).
- The users table loads `GET /users?page_size=200`.
- Two places set a person's rate (Resources → *Tarifa por hora* and this page). The versioned profile wins whenever one is active.

---

#### Cross-cutting configuration note
`DEFAULT_WEEKLY_CAPACITY_HOURS`, `DEFAULT_WORKING_HOURS_PER_DAY` and `DEFAULT_VACATION_DAYS_PER_YEAR` appear in the Admin runtime-settings group `locale` (`RUNTIME_FLAG_GROUPS` in `app/services/settings_service.py`). However, every capacity, forecast, heatmap and burnout calculation in this section reads the static `settings.X` from `app/core/config.py` (env value). `settings` is a plain `Settings()` object with no runtime override, so **changing these values in Admin does not change those calculations**. Only `GET /api/v1/settings` reads the runtime value.

The practical impact is limited: new users get `weekly_capacity_hours` from the same static default at creation, and the fallback only applies to users whose capacity is null.

#### Background jobs touching this area
- **Performance reminders**: daily at 09:00, Celery beat `perf-reminders-daily` (APScheduler `scheduled_perf_reminders` when APScheduler is the active scheduler).
- **Missing-imputations check**: `check-missing-imputations`, Celery Beat on weekdays at 18:00; uses `weekly_capacity_hours` (`app/worker.py`).
- No scheduled job recomputes burnout snapshots, resource alerts or utilisation snapshots. `resource_alerts` and `resource_utilization_snapshots` are only reachable through API-only `/resources/*` endpoints that no screen calls (`/resources/alerts`, `/resources/utilization-history`, `/resources/team-health`, `/resources/load-scoring`, `/resources/availability-matrix`, `/resources/forecast`, `/resources/{project_id}/skill-gaps`, `/resources/available-by-skill/{skill_id}`).

#### Test coverage (file counts, not a coverage measurement)
- **Backend** (`tests/`, files mentioning each area): capacity 26, bookings 17, performance 9, skills 6, user_cost 6, training 5, okrs 2, burnout 2 (`test_raci.py`), resource forecast 1. None found for SmartMatch or the org chart.
- **Frontend**: of 32 test files, only `src/__tests__/ResourceHeatmap.test.tsx` touches this section. None of the 11 pages or `UserProfilePanel` has a test.
- **E2E**: `tests_e2e/test_e2e_okrs.py`.

---

## Finance, CRM & Client Portal

This section covers the commercial and financial screens of the internal app (sidebar group **Finance**, routes restricted to `admin` and `pm` in `frontend/src/App.tsx`) and the external client portal (`/portal`), which has its own login, cookie and HTTP client.
Everything below was read from the code on 2026-11-03: page components, their API clients (`frontend/src/services/api/_core.ts`), the FastAPI routers (the route table was dumped from `app.main:app`) and the services and models behind them. Nothing was clicked through in a browser for this write-up. Any statement about runtime behaviour that rests only on reading the code says so.

General notes that apply to every module here:

- **Role gap.** Routes are open to `admin` and `pm` only, but most backend endpoints use `require_any_manager` (admin, pm, team_lead, hr). Some endpoints are stricter than the route (`require_admin`), so a PM sees buttons that return 403. Each case is listed under its module.
- **Envelope.** Responses are `{data, meta}` or `{items, meta}`. The main axios client (`services/api/_core.ts`) unwraps both. The portal client (`CLIENT_API` in `pages/portal-client/portalClientContext.tsx`) unwraps both since commit `89bd5c1`. The public share page (`PortalPublicViewPage.tsx`) uses a bare axios that unwraps nothing (see `/portal/view/:token`).
- **Numbering.** Codes come from `app/services/numbering.py:next_numbered_code`, configurable per organization in the `NumberingSequence` table (Settings → numbering, `/advanced-config/numbering`). Code defaults:
  - opportunity `OPP-0001`
  - contract `CTR-0001`
  - work order `WO-0001`
  - project created from the pipeline `PRJ-0001`
  - invoice: prefix `INV`, year, 4 digits, counter reset every year (exact separator rendering not verified at runtime)
- **Currency and tax.** These come from `DEFAULT_CURRENCY` (default `EUR`) and `DEFAULT_TAX_RATE` (default `21.0`) in `app/core/config.py`, both also exposed in the runtime settings group `locale` (`app/services/settings_service.py`). Several screens hardcode `€` or `21`; those are listed per module.

---

### Finance dashboard — `/finance-dashboard`
*Roles:* admin, pm (sidebar label "Resumen financiero"). Component: `pages/FinanceDashboardPage.tsx`.

**Purpose.** A one-page summary of revenue, cost, margin, clients, pipeline, outstanding invoices, cost per hour and exchange rates.

**How to use it.**
1. Pick a period. The page computes `date_from`/`date_to` from a number of days (default 90).
2. Read the KPIs: Ingresos, Costes, Margen bruto, Clientes activos, Pipeline, Facturas pendientes, Coste/hora medio, Sin estructura de coste, and Margen real estimado.
3. Read the gauges and lists: top clients, pipeline by stage, profitability by project.
4. To add or update an exchange rate, open **Tipos de cambio → add**, enter from-currency, to-currency and rate, then save.

**Configuration.** Exchange rates live in the `/currency/rates` table. `EXCHANGE_RATES_AUTO_UPDATE` exists in config and in the runtime group `feature_flags`, but no code reads it. ECB and OpenExchangeRates syncs exist only as admin endpoints (`POST /api/v1/currency/sync-ecb`, `/currency/sync-openexchangerates`); no screen calls them and no worker job runs them.

**Technical notes.** The page calls:
- `GET /api/v1/profitability/summary`
- `GET /api/v1/profitability/projects`
- `GET /api/v1/clients?page_size=200`
- `GET /api/v1/pipeline?page_size=100`
- `GET /api/v1/invoices?page_size=200`
- `GET|POST /api/v1/currency/rates` (with fallbacks to legacy paths on 404)
- `GET /api/v1/user-costs/summary`

**Limitations (measured in the code).** Several KPIs do not show what their label says:
- ~~Revenue, cost and margin are always 0~~, ~~PMs get an error toast~~, ~~Pipeline KPI and pipeline-by-stage always 0~~, ~~"Open opportunities" counts won and lost deals~~, ~~"Top clients by revenue" and the project table use budget as revenue and 0 as cost~~. Fixed 2026-11-03: the page reads `portfolio.total_revenue/total_cost`, the projects' `billing_revenue/internal_cost`, and the opportunities' `expected_revenue` and `stage` (open = not `won`/`lost`; the Pipeline KPI sums open ones only); `/profitability/summary` (v1 and v2) and `/profitability/projects` accept admin and PM, like the screen. Test: `frontend/src/__tests__/FinanceDashboardPage.test.tsx`, `tests/test_rentabilidad_roles_de_pantalla.py`.
- ~~The period selector does nothing.~~ Fixed 2026-11-04: `/profitability/summary` (v1 and v2) and `/profitability/projects` accept `date_from`/`date_to`; costs and hourly revenue count imputations in the range, fixed-price revenue counts milestones billed in the range. The clients, pipeline and invoices cards are not period-bound.
- **Cost per hour is hidden from PMs.** `/user-costs/summary` is `require_admin_or_hr`, so PMs get `null` and the card is empty.
- **Saving an exchange rate fails for PMs.** `POST /currency/rates` is `require_admin`, so a PM gets 403.
- **Errors are hidden.** The client, pipeline and invoice lists use `.catch(() => [])`, so a failure looks like "no data".

---

### Clients / CRM — `/clients`
*Roles:* admin, pm. Components: `pages/ClientsPage.tsx` with tabs from `pages/clients/ClientsPageTabs.tsx` and `pages/clients/PortalUsersTab.tsx`.

**Purpose.** This is the client master record (table `clients`). Projects, contracts, licences, Service Desk tickets and portal access hang off it.

**How to use it.**
1. **Clientes → New.** Fill in name, short name, tax ID, contact, industry and status. Status values are `prospect`, `active`, `inactive`, `churned`. Industry values are `technology`, `finance`, `healthcare`, `retail`, `manufacturing`, `education`, `consulting`, `real_estate`, `media`, `other`.
2. Use the search box and status filter to find a client. You can switch between list and card view.
3. Select a client to open its tabs:
   - **Contactos**: contact types primary, billing, technical, executive, support, other.
   - **Proyectos**: link or unlink projects.
   - **Contratos**: link or unlink.
   - **Licencias**: link or unlink.
   - **Tickets SD**: read-only.
   - **Portal**: has its own sub-tabs, listed below.
4. **Portal sub-tabs:**
   - **Accesos** creates portal users: name, email, password with confirmation, project list and permission flags. It calls `POST /api/v1/portal/clients` with `client_org_id`. The created credentials are shown once.
   - **UAT**, **Solicitudes**, **Mensajes**, **Documentos**: the team side of the portal for this client.
   - **Configuración** stores `client_portal_configs`: enabled modules, SD without project, SLA tier, max portal users, default language, allow profile edit, allow password change.
5. Edit a client with the **Editar** modal. There is no delete button, even though `DELETE /api/v1/clients/{cid}` exists.

**Configuration.** The `client_portal_configs` row for each client (above). There are no runtime settings for this screen.

**Technical notes.**
- **Endpoints:**
  - `GET/POST /api/v1/clients`, `GET/PATCH/DELETE /api/v1/clients/{cid}`
  - `/clients/{cid}/contacts|projects|projects/available|projects/{pid}/link|licenses|contracts|portal-config|tickets|invoices|360`
  - `/clients/{client_id}/health-composite`
  - Portal users: `GET/POST/PATCH /api/v1/portal/clients`
- **Tables:** `clients`, `client_portal_configs`, `client_users`, `client_user_projects`.
- **Deprecation headers.** `GET/POST/PATCH/DELETE /clients…` answer with `x-api-deprecated: true` even though they are the endpoints this screen uses.

**Limitations.**
- **`POST /api/v1/clients/{cid}/portal-users` has no screen.** Neither do its siblings `GET` and `PATCH /clients/{cid}/portal-users/{uid}`: no frontend code calls them (checked with grep across `frontend/src`). The screen creates portal users through a different service, `POST /portal/clients` → `client_portal_service.create_client`.
- **Organization of new portal users.** `89bd5c1` made `client_service.create_portal_user` (the endpoint with no screen) take `organization_id` from the client; `bdd6fdf` did the same for the path the screen uses (`POST /portal/clients` → `client_portal_service.create_client`): the client company's organization or, without one, the first project's. With a normal admin both already matched (the tenant filter only shows clients of the admin's own organization); they differed for a superadmin. Both paths are covered by `tests/test_portal_usuario_organizacion.py`.
- **On the screen path, the organization comes from the tenant auto-stamp.** `create_client` sets no `organization_id`. It is filled by the `before_flush` auto-stamp in `app/db/session.py` (on by default via `TENANT_AUTO_STAMP_ON_INSERT=1`), which stamps the organization of the staff user doing the creating, not the client's. The two only differ if staff and client belong to different organizations. Not verified at runtime.
- **Max portal users is not enforced on the screen path.** `max_portal_users` is checked only in the endpoint with no screen.
- **Most portal settings are stored but never used.** `enabled_modules`, `sd_without_project`, `sla_tier` and `default_language` are saved but read by nothing in the portal backend or frontend. Only `allow_profile_edit` and `allow_pwd_change` take effect (in `client_portal_service`, portal profile update).
- **`PATCH /clients/{cid}/portal-users/{uid}` is loosely guarded.** It does not call `_get_scoped_client_or_404` and only requires a logged-in user. It writes any attribute except `id`, `hashed_password` and `client_org_id`. It is not reachable from the UI, but it is reachable from the API.
- **`GET /clients/{cid}/projects/available` lists projects from all clients.** It queries `Project` with no explicit organization filter in the service. Whether the session's tenant filter scopes it at runtime is not verified.

---

### Sales pipeline — `/pipeline`
*Roles:* admin, pm. Component: `pages/PipelinePage.tsx` with hooks in `hooks/usePipeline.ts`.

**Purpose.** A kanban of opportunities from lead to won, with proposal generation and conversion into a project.

**How to use it.**
1. **New opportunity.** Fields: name, client name (free text), stage, probability, expected revenue, expected close date, description.
2. Move a card by changing its stage in the card's select. The allowed transitions come from `STAGE_TRANSITIONS` in the page:
   - `lead` → qualification, proposal, lost, cancelled
   - `qualification` → lead, proposal, lost, cancelled
   - `proposal` → qualification, negotiation, lost, cancelled
   - `negotiation` → proposal, won, lost, cancelled
   - `lost` → lead
   - `won` and `cancelled` are final
3. Open a card. In the detail view:
   - **Generar propuesta** renders a Markdown proposal from the default template.
   - **Ver propuesta** shows it.
   - **Marcar enviada** sets `proposal_sent_at`.
   - The proposal status reads `none`, `generated` or `sent`.
4. **Convertir a proyecto** creates the project. What it writes:
   - a project in `planning`, `billing_type=time_material`, `budget_amount = expected_revenue`
   - an ASC 606 `RevenueContract` (method mapped from `contract_type`, defaulting to `over_time`)
   - the opportunity's stage set to `won`
   - a note activity
5. Delete an opportunity from the card. You must confirm.

**Configuration.** OPP numbering. Proposal templates (`proposal_templates`) and custom stages (`pipeline_stage_configs`) have endpoints but no screen. The kanban uses the 7 hardcoded `OpportunityStage` values.

**Technical notes.**
- **Endpoints:**
  - `GET/POST /api/v1/pipeline`, `GET/PATCH/DELETE /api/v1/pipeline/{opp_id}`
  - `POST /pipeline/{id}/generate-proposal|mark-proposal-sent|convert`, `GET /pipeline/{id}/proposal`
  - With no UI: `GET/POST /pipeline/{id}/activities`, `/pipeline/proposals/templates*`, `/pipeline/stages*`, `/pipeline/stage-configs*`, `GET /pipeline/forecast`
- **Tables:** `opportunities`, `opportunity_activities`, `proposal_templates`, `pipeline_stage_configs`.

**Limitations.**
- **The create form is thin, and conversion inherits the gaps.** There is no `client_id` selector, `contract_type`, `hourly_rate`, start date or duration. A converted project therefore has no client link, no billing rate, and an ASC 606 contract defaulting to `over_time`.
- **Only the stage can be edited.** The page sends only `{stage}` in PATCH. No other field can be changed after creation from this screen.
- **"Generate proposal" is template substitution, not AI.** `proposal_service.render_proposal`.
- **"Mark sent" sends nothing.** It only records a timestamp.
- **Conversion ignores the stage.** "Convertir a proyecto" is offered whatever the stage is, and it forces `won`.

---

### Contracts — `/contracts`
*Roles:* admin, pm. Component: `pages/ContractsPage.tsx`.

**Purpose.** Commercial contracts per project, with work orders under them.

**How to use it.**
1. **Nuevo contrato.** Choose the project (required), name, client, type and status. Required fields depend on the type:
   - `fixed_price` → total amount
   - `time_material` → hourly rate
   - `hourly_bag` → hours in the bag
   - `retainer` → monthly amount
2. Set the status: `draft`, `active`, `expired` or `cancelled`. The list filters by status and highlights contracts that are about to expire.
3. Open a contract to add **work orders**. Change a work order's status between `open`, `in_progress`, `completed` and `invoiced`.

**Configuration.** CTR and WO numbering.

**Technical notes.**
- **Endpoints:**
  - `GET/POST /api/v1/contracts`, `GET/PATCH /api/v1/contracts/{id}`
  - `DELETE /api/v1/contracts/{id}` (`require_admin`, no button in the UI)
  - `POST /contracts/{id}/work-orders`, `PATCH /contracts/{id}/work-orders/{wo}/status?status=`
- **Tables:** `contracts`, `work_orders`.

**Limitations.**
- **The hours bag never moves.** `contracts.hours_used` is never written anywhere in `app/` (grep found no writer), so `hours_pct` stays at 0% unless someone edits the database.
- **Nothing expires on its own.** No job moves contracts to `expired`.
- **Work order "invoiced" is only a label.** It creates no invoice.
- **This is not the ASC 606 contract.** Those live in `rev_contracts` under `/revenue`. There is no link between the two tables.

---

### Invoicing — `/invoices`
*Roles:* admin, pm. Component: `pages/InvoicesPage.tsx`.

**Purpose.** Create invoices from approved billable timesheets, track their status, download PDFs and push them to Xero or QuickBooks.

**How to use it.**
1. **Nueva factura.**
   - Choose project and client, set issue and due dates, tax rate (pre-filled with **21**), PO reference and period.
   - Press **Generar líneas**. It calls `POST /invoices/from-timesheets`, which builds lines from imputations that are `is_billable`, `is_approved` and not yet `is_invoiced`. The rate is the project's `billing_rate`, falling back to the user's `hourly_rate`.
   - Save. The invoice is created as `draft` and its imputations are marked `is_invoiced`.
2. Move it through its statuses with the row buttons. The backend accepts these transitions (`billing_reports_service.update_invoice_status`):
   - `draft` → `sent` | `cancelled`
   - `sent` → `paid` | `overdue` | `cancelled`
   - `overdue` → `paid` | `cancelled`

   The UI has only two buttons: **Enviar** (draft → sent) and **Pagada** (sent → paid). A `sent` invoice past its due date is only shown in red.
3. Download a PDF with the per-row download button.
4. **Sync.** Choose `xero` or `quickbooks` and press bulk sync (`POST /accounting/push-invoices-bulk`, limit 100). The last sync and the pending count are shown.

**Configuration.**
- `DEFAULT_TAX_RATE` and `DEFAULT_CURRENCY`.
- Invoice numbering.
- Xero and QuickBooks need an active `IntegrationConfig` row of that type. Their base URLs are `XERO_API_BASE` and `QB_API_BASE`.
- Stripe (`STRIPE_*`) is used only by `POST /invoices/{id}/payment-link`, which has no button.

**Technical notes.**
- **Endpoints:**
  - `GET/POST /api/v1/invoices`, `GET /invoices/summary`, `GET /invoices/{id}/pdf`, `POST /invoices/from-timesheets`
  - Status changes go to a different router: `PATCH /api/v1/billing-reports/invoices/{id}/status`
  - `GET /accounting/sync-status`, `POST /accounting/push-invoices-bulk`, `/accounting/xero/test`, `/accounting/qb/test`
- **Tables:** `invoices`, `invoice_lines`, `imputations.is_invoiced`.
- **Worker:** `generate_retainer_invoices` (Celery beat, daily at 07:00) creates monthly invoices for `recurring_retainer` projects on their `retainer_day`, using the client's time zone.

**Limitations.**
- **Lines cannot be typed by hand.** They come only from timesheets, and they are displayed with a hardcoded `€` and `h`.
- **Nothing ever sets `overdue`.** No job does it. `/invoices/summary` computes "overdue" on the fly.
- **Cancelling locks the hours.** Cancelling does not clear `is_invoiced`, so those hours cannot be invoiced again.
- **Accounting sync status is free text.** It is tracked as text markers in `invoices.internal_notes` (`[XERO sync …]`), and bulk sync picks every invoice in `sent`. It depends on an external service and has not been verified against live Xero or QuickBooks.

---

### Milestone billing — `/milestone-billing`
*Roles:* admin, pm. Component: `pages/MilestoneBillingPage.tsx`.

**Purpose.** A statement-of-work flow: milestone → completed → approved → draft invoice.

**How to use it.**
1. Choose a project and create a milestone: name, due date, and either `billing_amount` or `billing_pct`.
   - With a percentage, the amount is that share of the sum of the project's `contracts.total_amount`, or of `budget_amount` if there are no contracts.
2. Walk it through `billing_status`:
   - `pending` → **Completar** → `completed` (**Deshacer** returns it to `pending`)
   - → **Solicitar aprobación** → `pending_approval`
   - → **Aprobar** → `approved`, or **Rechazar** (a reason is required) → `rejected`
   - From `rejected` you can complete it again.
   - → **Generar factura** → `invoiced`
3. Generating the invoice creates a `draft` with one line, at `DEFAULT_TAX_RATE`, numbered with the invoice sequence. It is then managed in `/invoices`.

**Configuration.** `DEFAULT_TAX_RATE` and invoice numbering.

**Technical notes.**
- **Endpoints:** `GET/POST /api/v1/milestones/project/{pid}`, `PATCH/DELETE /milestones/{id}`, `POST /milestones/{id}/complete|uncomplete|request-approval|approve|generate-invoice`, `GET /milestones/dashboard/pending`.
- **Table:** `project_milestones`.
- **ASC 606 hook.** Completing a milestone calls `revenue_service.recognize_on_milestone` (for milestone-method obligations).

**Limitations.**
- **No separation of duties.** No check stops the user who requested approval from approving it (none found in `decide_milestone_approval`).
- **A second screen edits the same table.** `/profitability` changes these milestones through different endpoints (see that module), and its **Facturar** button bypasses this flow entirely.

---

### Profitability — `/profitability`
*Roles:* admin, pm. Component: `pages/ProfitabilityPage.tsx`.

**Purpose.** Margin and earned value per project: cost, revenue, CPI/SPI, cost at completion and a risk flag.

**How to use it.**
1. Filter the portfolio list by project status, then open a project.
2. Read the figures:
   - **Revenue** = `billing_rate × billable hours`. For fixed-price projects without a rate, it is the sum of `billing_amount` of milestones with `is_billed`.
   - **Cost** = the sum of `imputations.cost_amount`, converted to the organization's currency through `get_fx_rate`.
   - Also shown: CPI/SPI/EAC, `margin_at_completion`, and `risk_flag` (`critical`, `warning` or `ok`).
3. Manage milestones from the project detail: add (amount or %), edit, delete, and **Facturar**.

**Configuration.** Exchange rates for multi-currency projects. No dedicated runtime settings were found.

**Technical notes.**
- **Endpoints:** `GET /api/v1/profitability/summary` and `GET /profitability/projects` (admin or PM since 2026-11-03; `/projects` was open to every user), `GET /profitability/{project_id}` (admin or PM, checked in the handler), `GET/POST/PATCH/DELETE /profitability/{pid}/milestones[/{id}]`. There is also a v2 router, `/api/v2/profitability`.
- **Tables:** `projects`, `imputations`, `project_milestones`, currency rates.

**Limitations.**
- ~~PMs cannot see the list.~~ Fixed 2026-11-03: `/profitability/summary` accepts admin and PM.
- **"Facturar" only flips a flag.** It sends `PATCH {is_billed: true, billed_at}`. No invoice is created, and `billing_status` is not changed.
- **Percentage-only milestones add no revenue.** They count as 0 here, because revenue sums `billing_amount` only.

---

### Revenue recognition — `/revenue`
*Roles:* admin, pm. Component: `pages/RevenuePage.tsx`.

**Purpose.** Recognized and deferred revenue. The page runs **two separate engines** side by side.

**How to use it.** The page has five tabs: **Resumen**, **Reglas por proyecto**, **Contratos ASC 606**, **Entradas contables**, **ASC 606 / IFRS 15** (help).
- **Legacy engine (tabs Resumen and Reglas).**
  - Create a rule per project. Methods offered: `percentage_complete`, `time_and_material`, `straight_line`, `milestone`, `completed_contract`.
  - **Compute** a period for a rule. It writes `revenue_recognition_entries`.
- **ASC 606 engine (tabs Contratos and Entradas).**
  - Create a `RevenueContract`. Methods: `over_time`, `milestone`, `consumption`, `straight_line`. Add performance obligations to it.
  - **Run monthly** recognizes revenue for a year and month.
  - Close or reopen periods. A closed period is skipped.
  - Reverse an entry. This needs confirmation and cannot be undone.

**Configuration.**
- `over_time` and `consumption` use the project's `billing_rate` × **approved** billable hours. With no rate, nothing is recognized and a warning is logged.
- Each organization's time zone decides when its "day 1" falls.

**Technical notes.**
- **Endpoints:**
  - Legacy engine (served by `app/api/v1/endpoints/cab.py`): `GET/POST /api/v1/revenue/rules`, `POST /revenue/rules/{id}/compute`, `POST /revenue/auto-compute`, `GET /revenue/summary`, `GET /revenue/journal/{pid}[/export]`
  - ASC 606: `/api/v1/revenue-recognition/contracts|obligations|entries|period-closes|run-monthly|dashboard`
- **Tables:**
  - Legacy: `revenue_recognition_rules`, `revenue_recognition_entries`
  - ASC 606: `rev_contracts`, `rev_obligations`, `rev_entries`, `rev_period_closes`
- **Worker:** `revenue_monthly_recognition` (beat, daily at 02:00 UTC) runs `run_monthly_recognition` for the previous month for every active organization whose local date is day 1. It skips `milestone` contracts and is idempotent (`_ya_reconocido` plus a unique index).

**Limitations.**
- **The two engines write to different tables.** They do not reconcile with each other.
- **Two legacy methods recognize nothing.** `milestone` and `completed_contract` have no branch in `compute_revenue_period`, so they recognize 0.
- **Legacy auto-compute only handles `milestone_billing`.** The UI does not offer that method, and the auto-compute mutation (`_autoCompute`) has no button.
- **"Run monthly" defaults to the current, unfinished month.** It is called with `currentMonth`.
- **Very few tests.** No backend test was found for the legacy engine or for the `/revenue-recognition` endpoints. Only `tests/test_revenue_idempotency.py` covers the ASC 606 service.

---

### Budgets — `/budgets`
*Roles:* admin, pm. Component: `pages/BudgetsPage.tsx`.

**Purpose.** Annual budgets by department or project, with planned, actual and committed amounts per month.

**How to use it.**
1. Create a budget: name, year, department (from `settingsApi.getDepartments`), total, and optional monthly plan. If no plan is given, the total is split into twelve equal months.
2. Click a monthly cell to edit `planned`, `actual`, `committed` and notes.
3. **Aprobar** sets `is_approved`.
4. The summary shows planned against actual by month, and the deviation.

**Configuration.** `DEFAULT_CURRENCY` for the budget's currency.

**Technical notes.**
- **Endpoints:** `GET/POST /api/v1/budgets`, `PATCH /budgets/{id}/entry`, `POST /budgets/{id}/approve` (`require_admin`), `GET /budgets/summary`.
- **Tables:** `budgets`, `budget_entries`.

**Limitations.**
- **Actuals are typed by hand.** They are not fed from imputations, expenses or invoices.
- **Months never lock.** `budget_entries.is_locked` is never set anywhere, so the "Mes cerrado contablemente" guard never fires.
- **Approval locks nothing.** It does not freeze the budget.
- **PMs get 403 on Aprobar.** The endpoint is admin-only.

---

### Rate cards — `/rate-cards`
*Roles:* admin, pm. Component: `pages/RateCardsPage.tsx`.

**Purpose.** Tables of billing and cost rates per role or profile, with annual escalation and date validity.

**How to use it.**
1. Create a table.
2. Add entries: label (role), billing rate, cost rate, escalation %, valid from and to, notes.
3. Edit or delete entries. Duplicate a table, optionally applying an escalation %. Delete a table.

**Configuration.** `DEFAULT_CURRENCY` as the entry currency.

**Technical notes.**
- **Endpoints:** `GET/POST /api/v1/rate-cards`, `GET/PATCH/DELETE /rate-cards/{id}`, `POST /rate-cards/{id}/duplicate`, `/rate-cards/{id}/entries[/{eid}]`, `/rate-cards/{id}/overrides[/{oid}]`, `GET /rate-cards/effective`.
- **Tables:** `rate_tables`, `rate_entries`, `rate_overrides`. A second API over `rate_tables` exists in `advanced_config`.

**Limitations.**
- **Nothing reads these rates.** Invoices, profitability and revenue use `projects.billing_rate` and `users.hourly_rate`. `revenue_service` says so explicitly in a comment.
- **Client and project overrides have no UI.** `addOverride` is never called.
- **The effective-rate lookup is not shown anywhere.** The `useEffectiveRate` hook has no consumer.

---

### Subcontractors — `/subcontractors`
*Roles:* admin, pm. Component: `pages/SubcontractorsPage.tsx`.

**Purpose.** External vendors: their workers and skills, project assignments, logged hours and incoming invoices.

**How to use it.**
1. Create a subcontractor. The dashboard shows active subcontractors, hours logged and pending invoices.
2. Open it. Tabs: **Personas** (workers and skills from the skills catalog), **Asignaciones** (to active projects), **Horas** (time logs), **Facturas**.
3. Invoice statuses are `received` → **Aprobar** → `approved` → **Marcar pagada** → `paid`. `rejected` exists in the model but has no button.

**Configuration.** The organization's currency, read via `useOrgSettings`.

**Technical notes.**
- **Endpoints:** `/api/v1/enterprise/subcontractors*`, `/enterprise/subcontractors-dashboard`, `/enterprise/subcontractors/workers/*`. `POST/DELETE /enterprise/subcontractors/{id}/rates` has no UI.
- **Tables:** `subcontractors`, `subcontractor_rates`, `subcontractor_workers`, `subcontractor_worker_skills`, `subcontractor_assignments`, `subcontractor_timelogs`, `subcontractor_invoices`.

**Limitations.**
- **Subcontractor cost does not reach profitability or budgets.** No reference to `SubcontractorTimeLog` or `SubcontractorInvoice` was found outside `enterprise_service`.
- **Minimal backend tests.** Only one backend test file mentions subcontractors.

---

### What-if scenarios — `/scenarios`
*Roles:* admin, pm. Component: `pages/ScenariosPage.tsx`.

**Purpose.** Check whether the team's capacity can absorb a set of hypothetical projects. Despite its place under Finance, this is a capacity model, not a financial one.

**How to use it.**
1. Create a scenario: name, description, horizon in weeks (default 12), and projects (name, start date, end date, total hours).
2. **Compute.** It shows total demand, weekly capacity, peak and average utilization, and overloaded weeks. Status goes from `draft` to `computed`.
3. Delete a scenario when you no longer need it.

**Configuration.** `DEFAULT_WEEKLY_CAPACITY_HOURS` (default 40, also listed in the runtime settings). Whether an Admin runtime override reaches this read (`settings.DEFAULT_WEEKLY_CAPACITY_HOURS`) is not verified.

**Technical notes.**
- **Endpoints:** `GET/POST /api/v1/scenarios`, `GET/DELETE /scenarios/{id}`, `POST /scenarios/{id}/compute`.
- **Tables:** `scenario_models`, `scenario_projects`.

**Limitations.**
- **Capacity is a rough count.** It is the number of **all active users** (any role) × the weekly hours. It ignores current allocations and absences.
- **Only scenario projects count as demand.**
- **No backend tests found.**

---

### NPS & Health — `/nps`
*Roles:* admin, pm. Component: `pages/NPSPage.tsx`.

**Purpose.** Record NPS answers per client and keep health-score snapshots.

**How to use it.**
1. Choose a client and record a response with a score from 0 to 10. The category is derived as promoter, passive or detractor.
2. See the NPS summary for N days and the health history.
3. **Calcular salud** saves a new snapshot.
4. The leaderboard ranks clients by their latest snapshot.

**Configuration.** The runtime group `health` (`HEALTH_*` weights and thresholds in `app/core/config_groups/health_config.py`) exists, but **this screen's computation does not use it** (see Limitations).

**Technical notes.**
- **Endpoints:** `POST/GET /api/v1/nps/{client_id}/responses`, `GET /nps/{id}/summary`, `GET /nps/{id}/health`, `POST /nps/{id}/health-compute|health-snapshot`, `GET /nps/leaderboard`, `GET /nps/health/trend`.
- **Tables:** `client_nps`, `client_health_snapshots`.

**Limitations.**
- **The health score is mostly a placeholder.** `nps_service.compute_and_save_health` computes `nps_component×0.4 + 70×0.2 + 70×0.2 + 70×0.2`. That is 60% fixed constants, with a 90-day window hardcoded.
- **The real health model is not used here.** The `/clients/{id}/health-composite` endpoint, which uses the configurable `HEALTH_*` model, is not called by this page.
- **Portal surveys do not feed NPS.** Survey answers (`client_surveys`) never reach `client_nps`. Only staff can enter NPS answers.

---

## Client portal (external) — `/portal`

*Who:* portal users (`client_users`), not app users. The portal is not behind `ProtectedRoute` and has no Layout. Components: `pages/PortalClientePage.tsx` and `pages/portal-client/*`.

**Purpose.** Give a client's contacts a self-service view of their projects: progress, UAT, requests, support, messages, documents, knowledge base, invoices and surveys.

**How to use it (client side).**
1. **Log in** at `/portal` with the email and password created by staff in Clients → Portal → Accesos.
   - Endpoint: `POST /api/v1/portal/auth/login`, rate-limited to 5 per minute.
   - It sets the httpOnly cookie `portal_access_token`, a JWT signed with `CLIENT_PORTAL_SECRET` that lasts `CLIENT_TOKEN_EXPIRE_HOURS` (default 72).
   - The idle timeout comes from `GET /portal/auth/session-config` (the `idle_timeout_*` app settings; disabled and 30 minutes by default).
2. **Sections** (from the `PortalUI.tsx` navigation):
   - **Dashboard**: `GET /portal/dashboard`.
   - **Roadmap**: `GET /portal/project`.
   - **UAT**: list sessions, submit results, report issues. Uses `GET /portal/uat`, `POST /portal/uat/{id}/submit-result`, `POST /portal/uat/{id}/issues`.
   - **Solicitudes** (feature requests): create, edit, decide on a quote, withdraw. Uses `/portal/feature-requests`, `…/{id}/decide`, `…/{id}/withdraw`.
   - **Service Desk**: my tickets, new ticket from the public catalog or dynamic forms, comments, CSAT, and knowledge-base suggestions with deflection tracking. Uses `/sd/tickets/client*`, `/sd/catalog?public_only=true`, `/sd/dynamic-forms/public`, `/sd/kb*`, `/sd/announcements`. These belong to the Service Desk section.
   - **Mensajes**: chat (`/portal/collaboration/conversations|messages`) and the *Solicitudes formales* tab: governed conversations with the team (`/portal/conversations`, create, message, bot reply).
   - **Documentos**: list and sign. `POST /portal/documents/{id}/sign` records name, job title, IP and timestamp and generates a signature PDF. It is a click-to-sign record, not a qualified e-signature.
   - **Wiki**: `/portal/wiki/pages`.
   - **Facturas**: list, approve or reject (`GET /portal/invoices`, `POST /portal/invoices/{id}/approve`).
   - **Encuestas**: `GET /portal/surveys`, `POST /portal/surveys/{id}/respond`.
   - **Mi perfil**: profile, appearance, language, password, via `PATCH /portal/auth/me`. Profile and password changes are allowed or blocked per client by `allow_profile_edit` and `allow_pwd_change`.
   - **Theme.** The portal keeps its own theme in the browser (`portal_theme_mode`, default Freight Pro) and applies it on entering the portal, login included. Choosing one in Appearance previews it; leaving without saving restores the saved one. Until 2026-11-04 only the profile applied it, so the theme changed when the client opened My profile.
   - An AI chat widget on every page (`POST /portal/ai-chat`).

**Recent fixes (commit `89bd5c1`, 2026-11-03).**
- **Login.** Login used to return 200 and bounce back to the login screen. Since `4e2aade` the login answers `{data, meta}`, and `CLIENT_API` unwrapped only lists, so `res.data.client` was empty. The interceptor now also unwraps `{data, meta}`, with the same exactly-two-keys rule as the main client. A vitest covers it (`frontend/src/__tests__/portalClienteApi.test.ts`).
- **Organization.** Portal users now inherit their client's organization on both creation paths (`89bd5c1` and `bdd6fdf`), so the portal's organization filter no longer hides their projects ("El proyecto asignado no existe").
- **Not re-verified.** I did not re-run these fixes in a browser for this README. The commit message says they were checked in the browser and with 139 portal and client tests.

**Review of 2026-11-04 (measured with the demo client on a copy of the database).** Every route the portal calls exists, the 24 reads return 200, and data stays within the client's projects (another project's id gives 403, another client's ticket 404, no cookie 401). Fixed:
- **The client saw almost nothing.** The demo seed and everything a superadmin created had no organization, and the organization filter hid it: the dashboard showed 0 hours, 0 milestones, 0 deliverables, 0 tickets; UAT, documents, surveys, the public knowledge base and the catalogue were empty. Now the seed publishes its organization, rows without one take it from their project or user (`db/session.py: _org_del_registro`), and migration 123 fixes existing data. Measured after the migration: 465 h, 3 milestones, 3 deliverables, 1 open ticket; 3 public KB articles and 4 catalogue items.
- Tickets created in the portal now carry the client's organization (the portal Service Desk dependency did not publish it), so they count in the dashboard and CSAT.
- **Requests could not be edited or withdrawn** (always 400) and the buttons never showed: the status comparison used `str()` of an enum.
- **CSAT stars never showed**: the ticket detail lacked `csat_requested_at`.
- **Invoice approve/reject buttons never showed**: `client_approval_status` did not exist. Now a sent invoice is *pending* until the client decides; the decision is stored (migration 123).
- **The public share page was empty** (it read the response without unwrapping `{data}`).
- **Saving the profile erased phone and job title** (they were not loaded into the form; `/portal/auth/me` did not return the phone).
- The password rule on screen said 6 characters; the server requires 8. It now says 8.
- **`GET /sd/announcements` needed no login** and returned internal announcements of every organization. It now requires a user or a portal client, and clients get only `show_to_clients` ones.
- Signed documents now return `signed_at`.
- The conversations router was mounted twice, once with a doubled prefix (`/portal/conversations/conversations/…`). Only the working mount remains.
Still open: times are shown in UTC; the profile password change does not ask for the current password; `GET /portal/documents/{id}/signed-pdf` has no button; the wiki has no content to show in the demo.

**Configuration.**
- `CLIENT_PORTAL_SECRET` is required. In staging and production it must be at least 32 characters and not a placeholder.
- `CLIENT_TOKEN_EXPIRE_HOURS`, `PORTAL_SHARE_LINK_EXPIRE_HOURS` (both default 72), `COLLAB_PORTAL_MESSAGE_PER_MIN` (default 25).
- `GET /portal/branding`.
- `GET/POST /portal/translations`.

**Technical notes.**
- **Tables:** `client_users`, `client_user_projects`, `client_portal_configs`, `client_surveys`, `client_messages`, and the UAT, feature-request and document tables of `app/models/client_portal.py`.
- **Router:** `app/api/v1/endpoints/client_portal.py`, service `app/services/client_portal_service.py`. Conversations: `/portal/conversations/*` (one mount since 2026-11-04). WebSockets: `/ws/portal-ticket`, `/ws/portal-notifications`.
- **Base URL.** `CLIENT_API` uses a hardcoded `baseURL: '/api/v1'` and ignores `VITE_API_URL`, unlike the main client.

**Limitations (measured).**
- **Clients see draft invoices, and approving one sends it.** `GET /portal/invoices` returns **all** invoices of the user's projects, including `draft`, with no `can_view_budget` gate. Approving a `draft` from the portal switches it to `sent` (`approve_client_invoice`). Invoices with no `project_id` are never shown.
- **No screen creates surveys.** Surveys are created only through `POST /portal/surveys` (manager), so the Encuestas section stays empty unless they are created via the API.
- **Most module toggles are ignored.** `enabled_modules` and the other portal settings listed under Clients do not hide portal sections.
- **The AI chat needs an AI provider.** Without one, the client gets a short summary of their project and is pointed to Messages; before 2026-11-04 they saw an internal instruction ("configure IA & Conectores") cut off mid-word.
- **The AI chat only sees the client's assigned projects** (fixed 2026-11-04). It used to match projects by `client_name ILIKE '%<company>%'`; with the optional company field empty that matched every project of the organization, so the model received other clients' projects. Measured on a database copy before the fix.

### Public project status — `/portal/view/:token`
*Who:* anyone with the link (no login). Component: `pages/PortalPublicViewPage.tsx`.

**Purpose.** A read-only page with a project's status, milestones and deliverables, reached through a signed share link.

**How it works.** Staff create a link with `POST /api/v1/portal/share-link/{project_id}`, a JWT valid for `PORTAL_SHARE_LINK_EXPIRE_HOURS`. The page then calls `GET /api/v1/portal/view/{token}`.

**Limitations.**
- **No screen creates the link.** There is no frontend call to `/portal/share-link`.
- ~~The page shows nothing.~~ Fixed 2026-11-04: it unwraps `{data, meta}`. (Old note, kept for context: it read `data.project`, `data.milestones` and `data.deliverables` from the raw body. Reading the code, it would show the fallback project name and empty lists. This is the same class of defect fixed for login in `89bd5c1`. Not verified in a browser; there is no frontend test for this page.

### Client portal administration (internal) — `/client-portal`
*Roles:* admin, pm. Component: `pages/ClientPortalPage.tsx`.

**Purpose.** The team-side management of the portal, organized per project.

**How to use it.** Choose a project, then use the tabs:
- **Contactos** (portal users): `GET/POST/PATCH/DELETE /portal/clients`.
- **UAT**: `GET /portal/uat/team`, `POST /portal/uat/{project_id}`, `POST /portal/uat/{id}/test-cases`, `PATCH /portal/uat/issues/{id}`.
- **Solicitudes**: `GET /portal/feature-requests/team`, `POST …/{id}/respond`.
- **Mensajes**: governed conversations (`components/portal/GovernedConversations`).
- **Documentos**: `GET /portal/documents/team`, `POST /portal/documents?project_id=`.
- **Wiki**: edits wiki pages published to the portal (`/wiki/spaces`, `/wiki/pages/{id}`).

**Limitations.**
- **It is not in any menu.** No sidebar entry or link points to `/client-portal` (checked `Layout.tsx` and the whole `frontend/src` with grep). It is reachable only by typing the URL.
- **It duplicates the Clients → Portal tab.** Both cover the same data; Clients works per client, this screen per project.

---

**Not verified (stated explicitly):**
- The exact rendered format of invoice numbers.
- Runtime behaviour of the portal login and organization fixes (taken from commit `89bd5c1`, not re-run here).
- Whether the tenant filter scopes `/clients/{cid}/projects/available`.
- Whether Admin runtime overrides reach `DEFAULT_WEEKLY_CAPACITY_HOURS` and `DEFAULT_TAX_RATE` at the points that read them.
- Xero, QuickBooks, Stripe, ECB and OpenExchangeRates against the real services.
- The portal AI chat with a live provider: there is no provider configured in the database, so only the no-provider path and the project scoping were checked.
- The rendering of `/portal/view/:token`, which was inferred from code.

---

## Service Desk & ITSM

This section covers the support side of Contecflow: tickets, SLAs and their internal (OLA) and supplier (UC) counterparts, changes, problems, major incidents, the knowledge base, the CMDB, licences and assets (ALM), SLA calendars, the workflow designer and the inbound channels (email, SMS, monitoring alerts). It was checked against the code on 2026-11-03: `app/services/service_desk/*`, `app/api/v1/endpoints/service_desk/*`, `app/models/service_desk/*`, `app/worker.py`, `alembic/versions/098`–`116`, and the frontend pages under `frontend/src/pages/`. The endpoint list comes from the registered FastAPI routes: 357 routes under `/api/v1/sd/` alone. No test was run to write this section. Wherever a statement comes only from reading the code, it is marked **(code reading)**. Anything not checked is marked **Not verified**.

Conventions:

- Unless stated otherwise, all API paths are under `/api/v1`.
- Responses use the `{data, meta}` envelope (`APIResponse` / `APIListResponse`).
- Tenant isolation is global. `TenantSession.query()`/`execute()` and a `do_orm_execute` hook filter every model that has `organization_id` (`app/db/session.py`). A `before_flush` hook stamps the session's organisation on new rows that don't carry one. Background jobs (Celery) run with no tenant filter and set the organisation explicitly where it matters (`como_organizacion`).
- Role names: `admin`, `pm`, `team_lead`, `employee`, `hr` (internal) and `client` (portal).

### Navigation and roles (measured)

| Route | Sidebar label | Route guard (`App.tsx`) | Sidebar visible to (`Layout.tsx`) |
|---|---|---|---|
| `/support-dashboard` | Support status / Support dashboard | admin, pm, employee, hr, team_lead | same |
| `/service-desk` | Service Desk | **admin, pm, employee, hr** | admin, pm, employee, hr, **team_lead** |
| `/cmdb` | CMDB | admin, pm | admin, pm |
| `/sd/workflow-designer` | Workflow Designer | admin, pm | admin, pm |
| `/alm` | Licenses & Assets | admin, pm | admin, pm |
| `/sla-calendars` | SLA Calendars | admin, pm | admin, pm |
| `/agent-dashboard` | Agent Dashboard | admin, pm | admin, pm |

**Inconsistency:** a `team_lead` sees *Service Desk* in the sidebar, but the route guard does not list that role. `ProtectedRoute` sends them to `/403`, because `hasRole` is an exact match on `user.role`.

---

### Ticket lifecycle — `/service-desk`

*Roles:* admin, pm, employee, hr (UI). Backend: most ticket endpoints need `get_current_user` and scope through `get_scoped_ticket_or_404`. Comments and time logging also need `require_internal_user`.

**Purpose.** This is where agents work tickets: incidents, service requests, changes, problems and questions (`TicketType`: `incident`, `service_request`, `change`, `problem`, `question`).

**Tabs (in order).**

| Tab | What it shows |
|---|---|
| My queue | `GET /sd/tickets/my-queue`. Tickets **assigned to me** that are not `resolved`/`closed`/`cancelled`, ordered by priority, then creation date. Paged by 50 with the total and page buttons under the list (since 2026-11-03; before, only the first 25 were shown). The search box filters the loaded page. |
| All | `GET /sd/tickets?page=&page_size=50&search=`, with filters for priority, status and type. The search goes to the server (title, number, requester…) and the list is paged with the total shown (since 2026-11-03; before, the 100 newest only, searched in the browser). |
| Kanban | Up to 200 live tickets (`status=new,assigned,in_progress,pending_client,pending_third,resolved`), with a notice when there are more. Columns: Open (`new` + `assigned`), In progress, Pending client, Pending third party, Resolved. Drag and drop sends `PATCH {status}`. |
| To approve | Shown only when `GET /sd/approvals/mine` returns at least one item (polled every 60 s). |
| Changes | Change management, with four views: List, Calendar, Releases, Blackouts. |
| Major incidents | `GET/POST /sd/major-incidents`, `PATCH /sd/major-incidents/{id}`. Statuses: `active`, `resolved`, `closed`. |
| Problems / KEDB / KB | Each one is `ITSMKnowledgeTab` in a different mode. |
| Tools | Recommended assignment, Auto-resolution, Alert correlation, Change rollout, Call assistant. |
| Config | Catalogue, SLAs, Groups, Routing, Escalation, Notifications, Inbound email, Monitoring, On-call, Status page, Templates, Canned replies, Announcements. |

Opening `/service-desk?ticket=<id>` (the link in every notification) switches to *All* and opens that ticket in the split view.

**Statuses** (`TicketStatus`): `new`, `assigned`, `in_progress`, `pending_client`, `pending_third`, `resolved`, `closed`, `cancelled`. The legacy values `waiting_client` and `pending_change` are rewritten to `pending_client` and `pending_third`.

**Transitions.** There is no transition matrix: `PATCH /sd/tickets/{id}` accepts any status string. Only these rules are enforced:

- **Catalogue approval.** While `approval_status = pending`, moving to `in_progress`, `resolved`, `closed`, `pending_client` or `pending_third` returns 409. Cancelling is still allowed.
- **Side effects of each status** (`ticket_update_service._POR_ESTADO`):
  - `in_progress` stamps the first response, if there is none yet, and resumes the SLA.
  - `resolved` stamps `resolved_at` and `resolution_minutes` and evaluates the resolution SLA.
  - `closed` stamps `closed_at` and sets `csat_requested_at` once.
  - `pending_client` and `pending_third` save a snapshot and pause the SLA (`sla_paused_at`).
  - Any other status resumes a paused SLA, adding the paused minutes to `sla_pause_minutes`.

**Priority** (`p1_critical`, `p2_high`, `p3_medium`, `p4_low`) comes from the urgency × impact matrix (`POST /sd/priority-matrix`). Urgency: `critical`, `high`, `medium`, `low`. Impact: `enterprise`, `department`, `user`, `minimal`. Support levels: `l1`, `l2`, `l3`.

**Ticket detail panel (`TicketDetail.tsx`).**

- **Quick actions** (shown while the ticket is not resolved, closed or cancelled):
  - *Start* sets `in_progress`.
  - *Resolve* asks for the resolution text, which is what the requester receives.
  - *Escalate* calls `POST /sd/tickets/{id}/escalate`.
  - *Back to previous*, shown only in `pending_*`, calls `POST /sd/tickets/{id}/restore-pending`.
  - *Pause/Resume SLA* calls `POST /sd/tickets/{id}/sla/pause` or `.../sla/resume`.
  - *Split* calls `POST /sd/tickets/{id}/split`.
  - On a resolved ticket, *Close* sets `closed`.
- **Edit** is a modal with title, type, priority, urgency, impact, status, resolution, tags and the JSON of dynamic fields. It is sent with `PATCH /sd/tickets/{id}`.
- **SLA / OLA / UC block.** It shows the response and resolution due dates and their status (`ok`, `at_risk`, `breached`, `paused`), *OLA · queue* with its due date, and *UC · vendor contract*:
  - The contract is chosen from `GET /alm/contracts` and saved with `PATCH {uc_contract_id}`.
  - *Vendor has responded* sends `PATCH {uc_vendor_responded: true}`.
- **Comments.** `POST /sd/tickets/{id}/comments` with `{body, is_public}`. Tick **Internal note** under the comment box to write a note only agents see: it is shown in the panel with an *Internal note* label, it is not emailed to the requester and the client portal does not return it (`ticket_out(..., include_internal=True)` only in the agent detail). The checkbox stays as you left it between comments. A public comment from an agent stamps the first response; an internal note does not.
- **Suggest reply.** `POST /sd/tickets/{id}/ai-suggest` returns an AI draft with related KB articles and, if contecmind is configured, related documents. If the AI is unavailable, the panel says so and shows no draft.
- **Canned replies.**
- **Time logging.** `POST /sd/tickets/{id}/time-log` takes `{minutes, unit, billable}`, where unit is `minutes`, `hours` or `days`. Days use `DEFAULT_WORKING_HOURS_PER_DAY`.
- **Follow / unfollow (watchers).** `POST` / `DELETE /sd/tickets/{id}/watch`.
- **Merge a duplicate.** `POST /sd/tickets/{id}/merge`.
- **Links.** `/sd/tickets/{id}/links`, with types `relates_to`, `duplicates`, `caused_by`, `blocks` and `child_of`.
- **Documents panel.**
- **Approval box.** Shown when the ticket awaits a decision.
- **Fulfilment tasks** of a catalogue request.

**Configuration.** `SLA_*` and `SD_*` runtime settings (see *Settings* below).

**Technical notes.**

- Tables: `sd_tickets`, `sd_ticket_comments`, `sd_ticket_history`, `sd_ticket_time_logs`, `sd_ticket_links`, `sd_ticket_watchers`, `sd_ticket_merges`, `sd_ticket_events`, `sd_ticket_approvals`.
- Numbering (`INC-0042` etc.) is per organisation since migration 100. On PostgreSQL that migration only changes constraints.

**Limitations (code reading).**

- ~~Internal notes cannot be written from the ticket panel.~~ Fixed 2026-11-03 (see *Comments* above; test `tests/test_ticket_nota_interna.py`). Before the fix the panel sent `is_internal`, which the API ignores, and the agent detail returned only public comments. The separate `/internal-comments` page still writes to a different table (`ticket_internal_comments`, legacy `cmdb_service`); it is not in the sidebar and does not generate ticket events.
- ~~Changing priority does not recalculate SLA due dates.~~ Fixed 2026-11-03: every priority change recalculates response and resolution due dates from the opening time (not from now), unless the ticket is resolved, closed or cancelled. This covers the edit modal, the escalation action `elevate_priority`, linking to a major incident (P1), accepting an AI triage, Jira sync and *Back to previous*; all go through `ticket_update_service.cambiar_prioridad`. Test: `tests/test_sla_prioridad_manual_y_pausa.py`.
- ~~*Back to previous* loses the paused time.~~ Fixed 2026-11-03: it adds the paused minutes to `sla_pause_minutes` like every other resume path.
- ~~Kanban put closed and cancelled tickets in *Open*, and dropping on *Open* sent `status: "open"`.~~ Fixed 2026-11-03: the board asks only for `new,assigned,in_progress,pending_client,pending_third,resolved` (the `status` filter now accepts several values separated by commas); *Open* holds `new` and `assigned`; dropping on *Open* sets `assigned` if the ticket has an assignee, otherwise `new`. It loads at most 200 tickets and says so when there are more. Tests: `frontend/src/__tests__/KanbanTicketsTab.test.tsx`, `tests/test_tickets_filtro_varios_estados.py`.
- ~~My queue shows at most 25 tickets.~~ Fixed 2026-11-03: *My queue* and *All* are paged on the server (`frontend/src/__tests__/TicketListPaginada.test.tsx`).
- A code comment in `ServiceDeskPage.tsx` says the queue "only shows unassigned tickets". It is the opposite: it shows the tickets assigned to the current user.

---

### Notifications (event outbox and templates)

*Roles:* admin configures (`Service Desk → Config → Notifications`). Everyone receives them.

**Purpose.** Every ticket change, whatever its origin (UI, portal, email, SMS, workflow, escalation or monitoring), notifies the right people.

**How it works.** Changes write a row to `sd_ticket_events` in the same transaction (migration 098). An `after_commit` listener enqueues the Celery task `sd_procesar_eventos_de_ticket`. A beat entry also runs it every minute as a safety net. The processor (`ticket_event_processor.py`) turns each event into:

- an in-app notification (the bell),
- an email using the template for the recipient's role and language,
- a system event `ticket.*` for subscribed webhooks.

**Personal preferences (2026-11).** Each user chooses, in *Profile → 🔔 Avisos*, which notice types they want and by which channel. Every type has «App» (the bell); `approval_requested` also has «Correo». Everything is on by default. They are stored in `user_preferences.extra["notifications"]` (`app/services/preferencias_de_aviso.py`; `GET/PUT /api/v1/users/me/notification-preferences`). The in-app filter is a single `before_flush` listener that drops new `Notification` rows the user does not want, so it covers every code path that creates notices, including future ones. The approval email checks the «Correo» choice before sending.

**Daily digest (2026-11).** In the same tab, *Recibir cada día un resumen por correo* sends one email a day with the user's unread notices of the last 24 hours (`app/services/resumen_de_avisos.py`, hourly job `resumen_diario_de_avisos`).
- It goes out from `NOTIFICATIONS_DIGEST_HOUR` (8) in the user's time zone, and lists at most `NOTIFICATIONS_DIGEST_MAX_ITEMS` (20) notices with a link to the inbox. Both are in *Admin → Automations*.
- Nothing is sent when nothing is pending. The date of the last digest is stored in the user's preferences, so it never goes out twice in a day.
- It is off by default.

Recipients, as implemented in `destinatarios()`:

| Event | Recipients |
|---|---|
| `created` | Requester (`sd.created.requester`, if `SD_NOTIFY_REQUESTER_ON_CREATE`); the assignee or, if none, the queue members; plus on-call |
| `assigned` | The new agent |
| `group_assigned` (no agent) | Members of the new queue |
| `commented` by the requester | The assignee (or the whole queue) and the watchers |
| `commented` by an agent | The requester, only if public and `SD_NOTIFY_REQUESTER_ON_REPLY`; the assignee and the watchers |
| `status_changed` | To `resolved`: the requester (`SD_NOTIFY_REQUESTER_ON_RESOLVE`). Always: the watchers |
| `priority_changed` | Assignee and watchers, bell only (`SOLO_CAMPANA`) |
| `sla_warning`, `sla_breached` | Assignee (or queue) and the queue leads (`is_lead`); a breach also goes to on-call |
| `ola_breached` | Assignee (or queue) and the leads of the queue that held the ticket (`data.group_id`) |
| `uc_breached` | Assignee (or queue) and the leads of the current queue |
| `escalated` | The users chosen by the rule, plus on-call |
| `approval_requested` / `approval_decided` | The approver / the requester |

**Recipient rules.**

- Nobody is notified of their own change, and nobody gets the same event twice. The exception is the creation acknowledgement for an external requester.
- The bell is always sent. Email to agents can be turned off with `SD_NOTIFY_AGENTS_BY_EMAIL`.
- On-call recipients also get an SMS when `SD_ONCALL_SMS` is on and the user has a phone number.
- The subject always carries `[INC-0042]`, which is how replies are threaded back to the ticket.

**Templates.** There are 15 codes:

| Recipient | Codes |
|---|---|
| Requester | `sd.created.requester`, `sd.commented.requester`, `sd.resolved.requester`, `sd.approval_decided.requester` |
| Agent | `sd.created.agent`, `sd.assigned.agent`, `sd.group_assigned.agent`, `sd.commented.agent`, `sd.updated.agent`, `sd.sla_warning.agent`, `sd.sla_breached.agent`, `sd.ola_breached.agent`, `sd.uc_breached.agent`, `sd.escalated.agent` |
| Approver | `sd.approval_requested.approver` |

- Languages: Spanish and English (`ETIQUETAS`).
- The default text lives in code (`plantillas_aviso.py`). A row in `email_templates` (columns `code`, `language`, `is_active`, migration 098) exists only when an organisation customises or switches off a template.
- Endpoints: `GET /sd/notification-templates`, `PUT/DELETE /sd/notification-templates/{code}/{language}` and `POST /sd/notification-templates/preview`.

**Configuration.** `SD_NOTIFY_*`, `SD_INBOUND_ADDRESS` (used as Reply-To), `SD_EVENT_MAX_ATTEMPTS` (5) and `SD_EVENT_BATCH_SIZE` (200). Outgoing mail uses the organisation's SMTP credential.

**Limitations.** A failed event is retried up to `SD_EVENT_MAX_ATTEMPTS` times. It then stays in the table with `last_error`; there is no screen for it.

---

### SLA, OLA and UC

*Roles:* admin/pm configure policies (`Config → SLAs`) and calendars (`/sla-calendars`).

**Which policy applies.** The contract's policy, then the client's, then the active default policy (`scoping.resolve_sla_policy_for_ticket`). Assign with:

- `PATCH /sd/sla-policies/assign/client/{client_id}`
- `PATCH /sd/sla-policies/assign/contract/{contract_id}`

**When the clock runs** (`sla_service.calendario_sla`):

- **24x7:** when `business_hours_only` is false.
- **The service calendar** the policy points to (`calendar_id`, migration 099).
- **The policy's own hours:** `business_start`, `business_end`, `business_days` and `timezone` (migration 098).

Without any policy, the clock follows `SLA_BUSINESS_HOURS_ONLY` / `_START_HOUR` / `_END_HOUR` / `_DAYS` in `DEFAULT_TIMEZONE`. Holidays are the calendar's (`sla_calendar_holidays`) plus `sd_sla_holidays` (per policy, or organisation-wide when `sla_policy_id` is NULL).

**Status.** The `sla_breach_scan` job runs every 5 minutes (`sla_monitor_service.escanear`):

- It computes the response status (only while there is no first response) and the resolution status of every open ticket, and stores them.
- `at_risk` means `SLA_PREDICTION_WARNING_PCT` of the target is used, measured in calendar hours. The default is 0.70. The `SLAEventType`/`EscalationTrigger` code comments still say 75 %; the setting rules.
- Each worsening transition (ok → at_risk → breached) writes an `SLAEvent` and a ticket event exactly once. Going back to ok does not notify.
- The same pass then runs the escalation rules.

**OLA** (migration 108). Set one target per queue in `Config → Groups → OLA (hours)` (`sd_agent_groups.ola_hours`). Empty means the queue has no OLA.

- The clock starts when the ticket enters the queue. `group_assigned_at` is set in a session hook on every queue change, whatever the path.
- It runs on the ticket's SLA calendar and excludes pause time accrued inside that queue (`ola_pause_base`).
- When it expires, `ola_breached` is set once, an `SLAEvent(sla_type="ola")` is written and the leads of that queue are notified.
- A change to the queue's hours is applied on the next pass.
- Tickets already open and queued when migration 108 ran count from that moment.

**UC** (migrations 113 and 115).

- **The contract.** It is the one chosen on the ticket. If none is chosen, it is the contract of the vendor of the ALM asset linked to the ticket's CI, but only if exactly one active `alm_contracts` row with hours matches. With two candidates, none is picked.
- **When it runs.** Only while the status is `pending_third`. `uc_started_at` is reset on every entry, and both clocks restart. It is not paused by the customer SLA pause.
- **Targets.** `resolution_hours` drives `uc_due` / `uc_breached`. `response_hours` drives `uc_response_due` / `uc_response_breached`. The response clock stops when the agent clicks *Vendor has responded* (`uc_vendor_responded_at`).
- **On breach.** A breach writes `SLAEvent` with `sla_type` `uc` or `uc_response` and the event `uc_breached`. It can also start a workflow.
- **Validation.** `uc_contract_id` must point to an active contract of the same organisation with hours; otherwise the API returns 422.

**Technical notes.**

- Endpoints:
  - `GET/POST /sd/sla-policies`, `PATCH/DELETE /sd/sla-policies/{id}`
  - `GET/POST /sd/sla-holidays`, `DELETE /sd/sla-holidays/{id}`
  - `GET /sd/tickets/{id}/sla/events`
- Tables: `sd_sla_policies`, `sd_sla_events`, `sd_sla_holidays`, `sla_calendars`, `sla_calendar_holidays`.

**Limitations.**

- OLA has one target per queue, the same for every priority.
- Priority changes from the UI do not move due dates (see *Ticket lifecycle*).

---

### SLA calendars — `/sla-calendars`

*Roles:* admin and pm can write (`require_admin_or_pm`). Any authenticated user can read.

**How to use it.**

- Create a calendar with name, timezone, `work_start` and `work_end` (HH:MM) and `work_days` (CSV, 1 = Monday).
- Add holidays to it.
- Check whether a date is a business day.
- A policy then selects the calendar. Several clients can share one.

**Technical notes.**

- The endpoints sit under `/cmdb/sla-calendars` in the legacy file `app/api/v1/endpoints/cmdb.py`, not under `/sd`:
  - `GET/POST /cmdb/sla-calendars`, `PATCH/DELETE /cmdb/sla-calendars/{id}`
  - `GET/POST /cmdb/sla-calendars/{id}/holidays`, `PATCH/DELETE .../holidays/{hid}`
  - `GET /cmdb/sla-calendars/{id}/check-date`
- Tables: `sla_calendars`, `sla_calendar_holidays`. Organisation scoping comes from the global tenant filter and the stamp on insert.
- Deleting a calendar is refused with 400 while it has active holidays. The service then also checks whether an active SLA policy still uses it; the outcome of that check was **not verified**.

---

### Escalation

*Roles:* admin configures in `Config → Escalation`.

**How to use it.** Each rule has a *when* (`EscalationTrigger`) and a *then* (`EscalationAction`). It can be restricted to some priorities and to one queue.

- *When:* `sla_at_risk`, `sla_breached`, `idle_hours` (N hours without movement), `priority` (still without an agent), `reopened`.
- *Then:* `notify_manager`, `notify_group_lead`, `notify_custom`, `reassign_group`, `elevate_priority`.

**Rules.**

- A rule fires once per ticket.
- `idle_hours` fires again only if the ticket stays idle another `idle_hours_threshold` hours since the last firing.
- Idle time is wall-clock hours (`now - since`), not calendar hours **(code reading)**.
- The latest firings are listed below the rules.

**Technical notes.**

- Endpoints: `GET/POST /sd/escalation-rules`, `PATCH/DELETE /sd/escalation-rules/{id}`, `GET /sd/escalation-rules/logs`, `POST /sd/escalation-rules/run`.
- Tables: `sd_escalation_rules`, `sd_escalation_logs`.
- Runs inside `sla_breach_scan`.

---

### Inbound email (IMAP, Microsoft 365, webhook)

*Roles:* admin (`Config → Inbound email`, `require_admin`).

**How to use it.** The screen has *Test connection* (`POST /sd/inbound/test`, read-only), *Read now* (`POST /sd/inbound/run`) and the latest messages with what was done with each (`GET /sd/inbound/messages`).

**Processing** (`inbound_mail.procesar`):

1. A message already in `sd_inbound_messages` is ignored (migration 101, unique key).
2. Automatic mail is discarded: `Auto-Submitted` other than `no`, `Precedence` bulk/junk/list/auto_reply, `X-Autoreply`, `X-Autorespond`, and messages without a sender.
3. The sender is matched as a portal contact or an internal user.
4. If the subject cites `[PREFIX-n]` and the sender may comment on that ticket, the quoted history is stripped and the text is added as a public comment:
   - Who may comment: any internal user, the requesting contact, a contact of the ticket's client, or the original requester email.
   - A ticket in `pending_client` or `pending_third` returns to `in_progress`.
   - A `resolved` ticket returns to `in_progress` if `SD_REOPEN_ON_REPLY`.
   - A `closed` or `cancelled` ticket gets a **new** ticket linked with `relates_to`.
5. An outsider citing a number gets a new ticket.
6. Attachments are saved as ticket documents up to `SD_MAIL_MAX_ATTACHMENT_MB`. Those that don't fit are listed in an internal comment.
7. New tickets go through the normal path: numbering, SLA policy, routing and auto-assignment. The type is `SD_CHANNEL_TICKET_TYPE`.

**Configuration.**

- **Mailbox.** Credentials → *Service Desk mailbox*. Set `protocol=imap` (host, port, user, password, folder; default `INBOX`; reads `UNSEEN`, marks `\Seen`) or `protocol=graph`.
- **Microsoft 365.** Graph needs the *Microsoft 365 / Graph* credential: an Azure app with the **Mail.ReadWrite** application permission. It reads `isRead eq false` and sets `isRead=true`. A failing message is stored as `failed` and still marked read.
- **Webhooks.** There are two webhook entry points, both using `inbound_email_service.process_inbound_email`:
  - `POST /sd/inbound-email`, header `X-Contecflow-Email-Secret`.
  - `POST /sd/multichannel/inbound/email`, header `X-Inbound-Secret` or body `token`/`signature`.
  - The organisation is resolved from the recipient address (`SD_INBOUND_ADDRESS`), and the secret is the `webhooks.inbound_email_secret` credential. With no secret configured the answer is 403.
- **Limits.** `SD_MAIL_MAX_PER_RUN` (50).
- **Job.** `sd_leer_buzones`, every 2 minutes, per organisation.

**Limitations.** Not verified against a real IMAP server or Microsoft 365 tenant. The tests use fakes, according to `docs/SERVICE_DESK.md`; this was not run here.

---

### SMS

`POST /sd/multichannel/inbound/sms` is the Twilio form webhook.

- The `X-Twilio-Signature` header is **mandatory**: 403 if missing or invalid. Without the Twilio `auth_token` no SMS is accepted.
- The organisation comes from the receiving number (`To`).
- Outbound SMS is used for on-call paging (`sms_service.send_sms`).
- `GET/PUT /sd/multichannel/config` and `GET /sd/multichannel/channels` hold channel configuration.

**Not verified** against real Twilio.

---

### Monitoring alerts → incidents

*Roles:* admin (`Config → Monitoring`). Ingestion has no session: it authenticates with a token.

**How it works.**

- **Endpoint.** `POST /sd/events/{source}` with header `X-Contecflow-Event-Token`. The token is the *Monitoring alerts* `ingest_token` credential, and it also identifies the organisation.
- **Alertmanager format** (`{"alerts":[...]}`). The key is `fingerprint`, or the sorted labels if it is missing. The CI comes from `instance`, `host` or `service`.
- **Generic format.** An object or a list with mandatory `key` and `title`, plus `status` (`firing`/`resolved`), `severity`, `description` and `ci`.
- **New alert.** It opens an incident.
  - Priority comes from `SD_EVENT_SEVERITY_MAP`. Default: critical→P1, high/error→P2, warning→P3, info→P4, anything else P3.
  - It is linked to the CI whose code or name equals the reference, with any `:port` stripped.
- **Same alert while still firing.** No new incident: `occurrences` and `last_seen_at` are updated.
- **Recovery.**
  - An internal comment is added to the incident.
  - The incident is resolved automatically if `SD_EVENT_AUTO_RESOLVE` is on, the ticket is still open and not pending approval, and **no internal user has commented on it**.
- **Response.** The API returns counts: `created`, `repeated`, `resolved`, `ignored`.
- **History.** `GET /sd/events/alerts` lists the latest alerts.
- Table: `sd_monitoring_alerts` (migration 104).

**Limitations.** Not verified against a real Alertmanager. "Alert correlation" (Tools tab, `alert_correlation_scan` every 30 min) is a different feature: it clusters already-open tickets and can create Problems.

---

### On-call

*Roles:* admin (`Config → On-call`).

**How to use it.**

- Create a schedule per queue: `POST /sd/oncall/schedules`.
- Add shifts with start and end: `POST /sd/oncall/schedules/{id}/entries`.
- `GET /sd/oncall/current` shows who is on call now.
- Whoever is on call for the ticket's queue is notified for `created`, `sla_breached` and `escalated`, but only when the ticket priority is in `SD_ONCALL_PRIORITIES` (default `p1_critical,p2_high`). They also get an SMS if `SD_ONCALL_SMS` is on and the user has a phone.

**Limitations (code reading).** `OnCallSchedule.rotation` (`weekly`, `daily`, `custom`) is stored and returned, but nothing generates shifts from it. Shifts are entered by hand.

---

### Service catalogue, approvals and fulfilment tasks

*Roles:* admin configures (`Config → Catalogue`). Requesters are internal users or portal clients. Approvers are the user named on the service, or an admin.

**How to use it.**

- A service (`sd_service_items`) can set `requires_approval` plus `approval_user_id`. Saving without an active approver returns 422.
- The ticket of such a service is created with `approval_status = pending` and a row in `sd_ticket_approvals` (migration 102).
- The approver is notified and sees the ticket under *To approve*.
- The decision is sent with `POST /sd/tickets/{id}/approval` and `{decision: approved|rejected, comment}`:
  - Only the approver, an `admin` or a superadmin can decide (403 otherwise).
  - Rejecting requires a reason (422 without one), stores it as the resolution and sets the ticket to `cancelled`.
  - The requester is notified.
- **Fulfilment tasks** (migration 107, `sd_service_items.fulfillment_tasks`, a JSON list of `{title, group_id}`):
  - When the request is created, or when it is approved if approval is required, each task becomes a child ticket (`source="fulfillment"`) in its queue.
  - When every child is `resolved`, `closed` or `cancelled`, the parent is resolved automatically with "Petición completada: …".

**Technical notes.**

- Catalogue endpoints: `GET /sd/catalog`, plus `POST`/`PATCH`/`DELETE` on `/sd/catalog/categories` and `/sd/catalog/services`.
- `GET /sd/catalog` requires a portal client or an internal user.
- The "smart catalogue" endpoints (`/sd/catalog/smart/*`) and the `catalog_popularity_update` job (every 6 h) also exist. Their UI was not reviewed (**Not verified**).

---

### Changes — `Service Desk → Changes`

*Roles:* internal users with access to the change. Votes come from CAB members.

**Statuses** (`ChangeStatus`): `draft`, `submitted`, `cab_review`, `approved`, `scheduled`, `in_progress`, `implemented`, `post_review`, `closed_success`, `closed_failed`, `cancelled`. Types: `standard`, `normal`, `emergency`.

**Rules** (`change_service._aplicar_estado`):

- Setting `submitted` or `cab_review` scores the risk (`change_impact_service`).
  - A `standard` change with `auto_risk_score ≤ SD_CHANGE_AUTO_APPROVE_MAX_RISK` (default 30) is approved automatically.
  - Any other change starts the CAB workflow. Without `SD_CAB_GROUP_ID` the API returns 409.
- `approved` cannot be set by editing (409). Only CAB voting approves.
- **CAB.**
  - Members are the members of the CAB queue. For `emergency` changes, only its leads vote.
  - The quorum follows `SD_CAB_APPROVAL_RULE`: `majority` = floor(n/2)+1 (the default), `all` or `any`.
  - Votes go to `POST /sd/changes/{id}/cab/vote`. A vote against requires a note.
  - The change is approved when the quorum is reached. It is cancelled, with `rejected_reason`, as soon as the quorum becomes unreachable.
- `scheduled` requires the change to be `approved`, with `planned_start` and `planned_end`, the end after the start, and no overlap with an active blackout. Emergency changes are exempt from the blackout check.
- `DELETE /sd/changes/{id}` cancels the change instead of deleting it. An implemented change is not cancelled (409).
- **Calendar.** `GET /sd/change-calendar` returns changes, releases and blackouts for the period, with clashes (same CI, overlapping) flagged. Clashes warn but do not block.
- **Releases** (`sd_releases`). Statuses: `planned`, `in_progress`, `released`, `cancelled`. A release cannot move to `released` while it contains changes that are not yet implemented.

**Technical notes.**

- Endpoints: `/sd/changes*` (about 40 routes, including impact analysis, risk matrix, rollback plan, testing plan, comms plan, what-if and rollout plans), `/sd/change-blackouts`, `/sd/releases`.
- Tables: `sd_change_requests`, `sd_change_approvals`, `sd_change_blackouts`, `sd_releases` (migration 103).
- Job: `change_impact_batch_score`, every 10 min.
- Route order matters: `change_rollout` and `change_impact` are included before `misc`, so that `/changes/rollout-plans` and `/changes/cab-dashboard` are not captured by `/changes/{change_id}`.

---

### Problems and KEDB

*Roles:* internal users.

**Statuses.** Problem: `open`, `investigating`, `known_error`, `resolved`, `closed`.

**Features.**

- Linking incidents.
- An RCA wizard (`/sd/problems/{id}/rca-wizard/*`, including `ai-assist`) and RCA templates (`/sd/rca/templates`).
- Promotion to the KEDB.
- Creating a change from a problem.
- KEDB endpoints: `/sd/known-errors*`.

**Jobs.**

| Job | Schedule | What it does |
|---|---|---|
| `problem_auto_detect` | hourly at :05 | Clusters recurring incidents and creates Problems |
| `kedb_expiry_scan` | daily 06:30 | Demotes expired KEDB entries to investigating |
| `kedb_effectiveness_scan` | daily 07:00 | Recomputes effectiveness scores |

**Tables.** `sd_problems`, `sd_known_errors`, `sd_known_error_tickets`, `sd_problem_rca_templates`, `sd_incident_to_problem`.

Not reviewed screen by screen (**Not verified** beyond the endpoints and jobs).

---

### Knowledge base

*Roles:* internal users write. Portal clients and internal users read.

**Statuses** (`KBStatus`): `draft`, `in_review`, `published`, `archived`. Migration 105 added `in_review`, `deflection_count`, `embedding` and `review_comment`.

**Review** (when `SD_KB_REQUIRE_REVIEW` is on). The author submits with `POST /sd/kb/{id}/submit`. A reviewer then publishes or returns the article with a comment (`POST /sd/kb/{id}/review`). The reviewer is a member of `SD_KB_REVIEWER_GROUP_ID`, or an admin if that is empty.

**Portal deflection.** While the client types a request, the portal calls `GET /sd/kb/suggest?q=`. *This solved it* calls `POST /sd/kb/{id}/deflected`, which increments `deflection_count`, and no ticket is opened.

**Other.** Versions are listed with `GET /sd/kb/{id}/versions`, and `POST /sd/kb/{id}/rollback/{version}` restores one. `POST /sd/tickets/{id}/to-kb` turns a ticket into an article.

**Semantic search.**

- Stored vectors exist only with `SEMANTIC_EMBEDDINGS_BACKEND=transformer`. The default is `tfidf`, which searches by words, because its vocabulary is per process and its vectors cannot be stored.
- Optional pgvector (migration 116):
  - If PostgreSQL has the `vector` extension, `sd_kb_articles.embedding_vec` is created and backfilled.
  - The database then orders by cosine distance, with an HNSW index created when the first vector is saved.
  - Without the extension, the comparison happens in Python.
  - The column is intentionally not in the ORM model.
- To enable it on an existing install, use the `pgvector/pgvector:pg16` image and run `kb_vectores.preparar`. Moving from `postgres:16-alpine` (musl) to that image (glibc) changes collation, so run `REINDEX DATABASE` first.

**Security.** `GET /sd/kb`, `GET /sd/kb/{id}`, `/sd/kb/suggest`, `/deflected` and `/helpful` need a portal client or an internal user (`lector_de_la_kb`).

**Quality loop (revision 2026-11, what contecmind already had).** *Service Desk → KB → Calidad*. One service (`app/services/service_desk/kb_calidad.py`) answers every AI question against the knowledge base: NexusAssist, the portal AI chat and the portal L1 bot.

- **Measured before:**
  - NexusAssist searched `ai_kb_articles`, which was empty (0 rows) while the Service Desk base had the real articles.
  - The portal AI chat did not look at the base at all.
  - The L1 bot looked for the whole question as a literal substring.
- **Citations.** The articles that pass the relevance threshold go to the model with their number, and the model is told to cite them (`[KB-0001]`). The answer returns `sources` (number and title), which the assistant and the portal widget show under the reply. For clients, only public articles are used. Thresholds:
  - `SD_KB_RAG_MIN_SCORE_VECTOR` (0.35): cosine similarity, with the sentence model.
  - `SD_KB_RAG_MIN_SCORE_WORDS` (0.5): share of the question's words found, without the sentence model.
  - `SD_KB_RAG_MAX_SOURCES` (3).
- **Word search without the sentence model.** Accents are ignored, and words longer than five letters compare by their first six letters. «¿Cómo restablezco mi contraseña?» now finds «Como restablecer tu contrasena» (measured: before, it found nothing).
- **Expert corrections.** *Corregir* under any assistant reply, or *Responder* on an unanswered question, saves the right answer (`POST /sd/kb/corrections`; only people who can publish to the base, `puede_publicar`). It applies at once to similar questions (`SD_KB_CORRECTION_MATCH`, 0.8: cosine with the sentence model, word overlap without it) and goes ahead of the articles. The reply shows *Respuesta validada por un experto*. A correction is internal unless *También para los clientes* is ticked. Archive it from the Calidad view.
- **Unanswered questions.** A client question (portal chat or L1 bot) with neither article nor correction is recorded in `sd_kb_gaps`. Repeated questions are grouped (same words in any order) and counted. From the list: *Responder* (creates a correction and closes it), *Crear artículo* (the title comes pre-filled; saving closes it) or *Descartar* (it no longer comes back, but is still counted). Internal assistant questions are not recorded: most are about data, not the base.
- **Alerts** (daily job `kb_pasada_de_calidad`, 03:10; admins can run it with *Revisar ahora*, `POST /sd/kb/quality/run`):
  - Stale: a published article untouched for `SD_KB_STALE_DAYS` (180; 0 = off). Its author is notified once per version.
  - Contradictory: published articles more similar than `SD_KB_CONTRADICTION_SIMILARITY` (0.75) are compared with AI (module `knowledge_base` in the AI Hub), at most `SD_KB_CONTRADICTION_MAX_PAIRS` (10, 0 = off) pairs per run. A pair is not compared again until one of the two articles changes. This needs the sentence model (stored vectors) and an AI provider; without either it is skipped and the run says why.
- **Tables:** `sd_kb_corrections`, `sd_kb_gaps`, `sd_kb_findings` (migration 133). **Endpoints:** `GET /sd/kb/quality`, `PATCH /sd/kb/corrections|gaps|findings/{id}` (status).
- `/service-desk?tab=kb` opens the KB tab directly; alerts and citations link there.

**Limitations.** The pgvector path is **Not verified** here. The local stack uses `postgres:16-alpine`.

---

### Status page

*Roles:* admin/pm manage it (`Config → Status page`). The public page is anonymous.

**How to use it.**

- Components have a status (`operational`, `degraded_performance`, `partial_outage`, `major_outage`, `maintenance`), a group, an order and a public flag.
- Incidents are declared per component, and updates are added to them.
- `GET /sd/status-page/link` returns the public address. `GET /sd/status-page/embed.js` (and `/status/embed.js`) returns an embeddable snippet.

**Public page.** `GET /status?org=<slug>` is HTML; its data comes from `GET /sd/status-page?org=<slug>`.

- Without `org`, the page is served only if there is a single organisation; otherwise the answer is 422.
- An unknown slug returns 404.

**Tables.** `sd_status_components`, `sd_status_incidents`.

---

### CSAT

- When a ticket is **closed**, `csat_requested_at` is set once.
- The client portal then shows the rating prompt, and the score is sent with `POST /sd/tickets/{id}/csat`.
- Only the requesting portal client can rate (404 otherwise).
- Rating is allowed only on `resolved` or `closed` tickets, and it closes a resolved ticket.

**Limitations (code reading).** No survey email is sent: the prompt exists only in the portal. A ticket that stays `resolved` without being closed never gets `csat_requested_at`, so the portal shows no prompt for it.

---

### Time to timesheet

`POST /sd/tickets/{id}/time-log` takes `{minutes, unit, billable}`. With `SD_TIME_TO_TIMESHEET` on and a project on the ticket, the time becomes an imputation through `validate_and_create_imputation`, which applies the normal timesheet rules:

- the user must belong to the project and have a rate;
- the date must not be locked;
- caps apply;
- hours are rounded to the nearest half hour (`round(v*2)/2`).

The resulting imputation id is stored in `sd_ticket_time_logs.imputation_id` (migration 106). If a rule blocks it, the time stays on the ticket and the response explains why (`timesheet: skipped, reason`).

**Limitations (code reading).**

- The imputation date is always today.
- `minutes` is an integer, so 1.5 hours cannot be entered with `unit=hours`.
- Less than about 15 minutes rounds to 0 h and is skipped.

---

### Workflow designer — `/sd/workflow-designer`

*Roles:* admin, pm.

**How to use it.**

1. Build a graph from these node types: `start`, `end`, `state`, `decision`, `approval`, `wait`, `notify`, `http_call`, `create_ticket`.
2. Validate it (`POST /sd/workflow-designer/validate`).
3. Save versions and publish one (`.../blueprints/{id}/publish/{version}`).

**Automatic start.**

- The *Start* node can declare `{"trigger": <event>, "condition": "<expr>"}`.
- Triggers: `created`, `assigned`, `group_assigned`, `status_changed`, `priority_changed`, `commented`, `sla_warning`, `sla_breached`, `ola_breached`, `uc_breached`, `escalated`.
- The condition uses the engine's mini-DSL (no `eval`) over the ticket fields and the event.
- A workflow does not start twice on the same ticket.
- Events generated by a workflow do not trigger workflows.

**Nodes and runs.**

- `state` really changes the ticket.
- `notify` sends to `$assignee`, `$group`, `$requester`, a list of user ids or a role, by bell or bell plus email.
- `wait` sets `wake_at`.
- Run statuses: `running`, `waiting`, `completed`, `cancelled`, `error`. Blueprint statuses: `draft`, `published`, `archived`.

**Technical notes.**

- Endpoints: `/sd/workflow-designer/*` (blueprints, versions, runs, cancel, resume, schema, templates).
- Tables: `sd_workflow_blueprints`, `sd_workflow_blueprint_versions`, `sd_workflow_runs`, `sd_workflow_run_steps`.
- Expired `wait` nodes are woken by the **in-process** collaboration scheduler in the API process, every 30 s by default (`collaboration/_scheduler._tick_workflow_engine`), not by Celery. If the API process is not running, timers do not fire.

---

### Tools tab

What each tool actually does, from the code and the Spanish manual:

- **Recommended assignment.** Weighted rules (load, history, skills, on-call). There is no trained model. `POST /sd/incidents/{id}/assign/recommend`.
- **Auto-resolution.** `/sd/auto-resolution/*`, plus the AI analysis endpoints on a ticket.
- **Alert correlation.** `/sd/alerts/correlate*` and `/sd/alert-clusters*`.
- **Change rollout.** `/sd/changes/rollout-plans*`.
- **Call assistant.** Classifies already-transcribed turns by keyword (`/sd/voice/*`). There is no telephony and no speech recognition, although `/sd/voice/webhook/twilio*` routes exist.
- **Predictive analytics** (`/sd/predictive/*`). Statistics over history plus rules.

**Autonomous agent.**

- **Off by default.** Turn it on per organisation in *Settings → Service Desk*: `SD_AUTONOMOUS_AGENT_ENABLED`. Thresholds: `SD_AUTONOMY_RESOLVE_THRESHOLD` (default 0.80, confidence to resolve on its own) and `SD_AUTONOMY_SUGGEST_THRESHOLD` (default 0.50, confidence to post the playbook comment).
- The `autonomous_agent_scan` beat job runs every 5 minutes over up to 100 `new`/`assigned` tickets **that it has not evaluated yet**, skipping organisations where it is off. Each evaluation writes a row in `sd_autonomous_playbook_executions` (`success` or `skipped`, score, reason, `triggered_by` = `celery` or `api`); that row is what the stats and log endpoints read, and what stops the scan from processing the ticket again. P1 tickets are never handled.
- Playbooks: the organisation's own (`sd_autonomous_playbooks`, created through `POST /sd/autonomous/playbooks`; conditions `trigger_keywords`, `trigger_categories`, `max_priority`, `auto_resolve`) are tried first, then the built-in ones (password reset, VPN, email, printer, slow PC). The score is the auto-resolution score plus 0.20 when a playbook matches.
- An `auto_resolve` playbook above the resolve threshold posts its comment **publicly** and resolves the ticket; below it, but above the suggest threshold, it only posts the comment.
- Before 2026-11-03 there was no switch, the thresholds were constants, an assisted ticket received the same public comment every 5 minutes, custom playbooks were never used, nothing wrote the execution log, and built-in texts linked to example URLs (`company.com`). Test: `tests/test_agente_autonomo_interruptor.py`.
- There is no screen for the agent: playbooks, stats and the log are API-only (`/api/v1/sd/autonomous/*`). How often the score reaches the thresholds on real data is **Not verified**.

---

### Support dashboard — `/support-dashboard`

`SupportDashboardPage` renders `MetricsDashboardTab`: ITIL metrics (`GET /sd/metrics/itil`, with MTTR and FCR among others) and agent performance (`GET /sd/metrics/agent-performance`) for the last N days. The day range is computed in the browser with `toISOString()`, which is UTC.

`analytics_snapshot` (hourly at :50) writes `sd_itsm_metric_snapshots`.

---

### Agent dashboard — `/agent-dashboard`

*Roles:* admin, pm (UI). Backend: `GET` needs any authenticated user; the snapshot needs admin/pm.

**How to use it.** Pick a user and a period (7–90 days). The page shows open tickets now, tickets resolved in the period, average resolution time (hours), SLA compliance (% of resolved tickets without a resolution-SLA breach), average CSAT, and per-day charts of resolved tickets, SLA and CSAT.

**Technical notes.** `GET /cmdb/agent-dashboard/{agent_id}?days=` (legacy `cmdb` router), admin or PM (since 2026-11-03; before, any user). Computed on request from `sd_tickets`: tickets assigned to the user with `resolved_at` in the period (days in the viewer's time zone), `resolution_minutes`, `sla_resolution_breached` and `csat_score`; open = assigned and not resolved, closed or cancelled. Test: `tests/test_panel_de_agente_desde_tickets.py`.

**Limitations.**
- ~~Everything except open tickets was always 0.~~ Fixed 2026-11-03: it used to read `agent_metric_snapshots`, filled only by a manual *Snapshot* button with zeros. The button and its endpoint were removed; the table `agent_metric_snapshots` remains in the schema, unused.
- Credit goes to the **current** assignee: if a ticket was reassigned after being resolved, it counts for the new one.
---

### CMDB — `/cmdb`

*Roles:* admin, pm (UI). Writing CIs and relations requires admin or pm. Class fields, discovery, agents and SNMP require **admin only**.

**Tabs.** Inventory, Topology, 3D, Agents, and Classes (shown to admins only).

**Inventory.**

- Each CI has a code (`CI-0001`) and a class (`CIType`): `application`, `server`, `database`, `network`, `service`, `module`, `integration`, `virtual_machine`, `container`, `cloud`, `endpoint`, `storage`, `other`.
- Statuses: `operational`, `degraded`, `maintenance`, `retired`. A CI also has environment, criticality, host, IP and version.
- Class-specific data (for example OS and RAM for a server) is stored too. Changing the class keeps only the new class's data.
- Search covers name, code, host and IP: `GET /sd/cmdb?q=&ci_type=&status=`.
- `DELETE /sd/cmdb/{id}` is a logical delete. Tickets, problems and changes that cite the CI keep it.

**Classes.** `GET /sd/cmdb/class-fields`, `PUT /sd/cmdb/class-fields/{ci_type}` (table `sd_ci_class_fields`, migration 114).

- Fields can be added, removed, reordered, labelled and typed (text, number, date).
- Until the organisation saves one class, factory defaults apply. Saving the first class makes all of them the organisation's own.
- Removing a field does not delete stored values.
- The classes themselves are fixed by the `CIType` enum.

**Relations.** `POST /sd/cmdb/relations`, `DELETE /sd/cmdb/relations/{id}`.

- Types: `depends_on`, `hosts`, `connects_to`, `backed_up_by`, `monitored_by`, `part_of`.
- Relations feed the impact analysis (`GET /sd/cmdb/{id}/impact`, `/blast-radius`, `/deprecation-impact`), the topology (`/sd/cmdb/{id}/topology`), the 3D graph (`GET /sd/cmdb/3d-graph`) and alert correlation.

**History.** `GET /sd/cmdb/{id}/changelog` (table `cmdb_changelog`). Changes made by discovery are labelled as such.

**Linked assets.** `GET /alm/assets/by-ci/{ci}`.

**Agents.**

- An admin registers an agent with `POST /sd/cmdb/agents/register`. The token is shown once.
- The agent calls `POST /sd/cmdb/agents/checkin` with a bearer token, which updates its CI.
- Revoke with `DELETE /sd/cmdb/agents/{id}`. Rotate with `POST /sd/cmdb/agents/{id}/rotate-token`; this one is API only.
- Table: `cmdb_agent_registrations`.

**Discovery.**

- Providers: AWS, Azure, GCP, Kubernetes, vSphere, SNMP (`/sd/cmdb/discovery/*`, `POST /sd/cmdb/snmp-scan`).
- Discovered CIs are created in the provider's organisation.
- A full scan retires what the provider no longer finds. A one-off SNMP scan retires nothing.
- Drift, baseline approval, reconciliation health and duplicate merge are also available.
- Job: `cmdb_discovery_run`, every 15 min, respecting each provider's `next_run_at`.

**Single CMDB (migration 110).**

- `cmdb_items`, `cmdb_relations` and `cmdb_categories` were merged into `sd_configuration_items` / `sd_ci_relations`, keeping ids.
- Same-name CIs in the same organisation were merged.
- `runs_on` A→B became `hosts` B→A.
- Missing organisations were back-filled from the owner, the project, the citing tickets, or the single organisation of the install.
- The old `/cmdb/items|relations|categories` API is gone.

**Limitations.**

- Discovery providers, drift and baseline, reconciliation, SNMP scan and token rotation have **no UI**: no frontend call to those endpoints was found. They are API only.
- The *Agents* tab is visible to `pm`, but its endpoints are admin-only, so a pm gets 403.
- In a multi-organisation install, a CI with no organisation, owner or project is visible only to the superadmin.
- **Not verified** against real cloud providers.

---

### Licences & Assets (ALM) — `/alm`

*Roles:* admin, pm (UI). Writes require `require_any_manager`.

**Tabs.** Dashboard, Vendors, Contracts, Licences, Assets, Cost centres, Compliance.

**Vendors and contracts.**

- Contract types: `purchase`, `subscription`, `maintenance`, `support`, `lease`, `enterprise`.
- Contract statuses: `active`, `expired`, `cancelled`, `pending`, `draft`.
- *Vendor resolution (UC, hours)* (`resolution_hours`) and *Vendor response (UC, hours)* (`response_hours`) turn a contract into a support contract (UC). The form validates them as positive or empty. An empty number is stored as NULL.

**Licences.**

- Types: `perpetual`, `subscription`, `concurrent`, `named`, `device`, `trial`, `free`, `oem`, `volume`.
- Statuses: `active`, `expired`, `unassigned`, `overallocated`, `cancelled`.
- Assignments are made per licence. Compliance (`GET /alm/compliance`) is computed from licences and software installs.

**Assets** (`alm_assets`).

- Types: `laptop`, `desktop`, `server`, `mobile`, `tablet`, `network`, `printer`, `monitor`, `peripheral`, `vm`, `other`.
- Statuses: `in_use`, `available`, `in_repair`, `retired`, `lost`, `stolen`.
- The *Lifecycle & CMDB* section holds the CI link (`ci_id`), warranty, `eol_date`, `lease_expiry`, `next_maintenance_date` and `maintenance_contract`.
- 📋 opens the history (`GET /alm/assets/{id}/history`, table `alm_asset_history`).
- *Expiring soon* sits at the top of the Assets tab (`GET /alm/assets/expiring?days=`, 30/60/90/180).
- 🔁 *Open renewal ticket* calls `POST /alm/assets/{id}/refresh-ticket`. It creates a `service_request` in the asset's organisation, with the asset's CI and normal numbering. If `refresh_ticket_id` is still open, that ticket is returned instead.
- The `asset_expiry_scan` job (daily 07:05) does the same for dates within `SD_ASSET_REFRESH_DAYS` (default 7; 0 switches it off).

**Single inventory (migration 111).**

- `sd_assets` / `sd_asset_history` were merged into `alm_assets` / `alm_asset_history`, keeping ids. Assets with the same serial number were merged.
- Fields ALM has no column for (code, order, vendor text, licence, tags) went into the notes.
- Types: `cloud`→`vm`, everything else→`other`. Statuses: `deployed`/`loaned`→`in_use`, `in_stock`/`pending_order`→`available`, `disposed`→`retired`.
- `/sd/assets` is gone.

**Limitations.** The old inventory's fixed 5-year depreciation and its manual seat audits were not carried over. ALM computes book value from each asset's own useful life.

---

### Settings

They are editable in *Settings → Dynamic config* (`RUNTIME_FLAG_GROUPS` in `app/services/settings_service.py`). Defaults come from `app/core/config_groups/service_desk_config.py` and `sla_config.py`, and values are resolved per organisation at runtime.

**`sla` group (selection).**

| Setting | Default | Meaning |
|---|---|---|
| `SLA_P1..P4_RESPONSE_HOURS` / `_RESOLUTION_HOURS` | P1 response 1.0 (others **Not verified**) | Targets when no policy applies |
| `SLA_BUSINESS_HOURS_ONLY` | true | Without a policy, count business hours only |
| `SLA_BUSINESS_START_HOUR` / `_END_HOUR` | 8 / 18 | Working day without a policy |
| `SLA_BUSINESS_DAYS` | `1,2,3,4,5` | ISO weekdays, 1 = Monday |
| `SLA_PREDICTION_WARNING_PCT` | 0.70 | `at_risk` threshold (share of the target used) |

The `sla` group also has `SLA_PREDICTION_HOURS_*` and `SLA_PREDICTION_SEVERITY_*`, used by predictive analytics.

**`service_desk` group.**

| Setting | Default | Meaning |
|---|---|---|
| `SD_NOTIFY_REQUESTER_ON_CREATE` / `_ON_REPLY` / `_ON_RESOLVE` | true | Emails to the requester |
| `SD_NOTIFY_AGENTS_BY_EMAIL` | true | Email to agents (the bell is always sent) |
| `SD_INBOUND_ADDRESS` | "" | Support address: identifies the organisation for webhooks; Reply-To |
| `SD_REOPEN_ON_REPLY` | true | A reply reopens a resolved ticket |
| `SD_CHANNEL_TICKET_TYPE` | `incident` | Type of tickets opened by email or SMS |
| `SD_MAIL_MAX_PER_RUN` / `SD_MAIL_MAX_ATTACHMENT_MB` | 50 / 15 | Mailbox batch size and attachment limit |
| `SD_CAB_GROUP_ID` | "" | Queue acting as the CAB; required for normal and emergency changes |
| `SD_CAB_APPROVAL_RULE` | `majority` | `majority`, `all` or `any` |
| `SD_CHANGE_AUTO_APPROVE_MAX_RISK` | 30 | Standard changes up to this risk score approve themselves |
| `SD_AUTONOMOUS_AGENT_ENABLED` | false | Autonomous agent scans new tickets every 5 min (comments publicly and may resolve) |
| `SD_AUTONOMY_RESOLVE_THRESHOLD` / `SD_AUTONOMY_SUGGEST_THRESHOLD` | 0.80 / 0.50 | Confidence to resolve on its own / to post the playbook comment |
| `SD_EVENT_SEVERITY_MAP` | JSON (see Monitoring) | Alert severity → priority |
| `SD_EVENT_AUTO_RESOLVE` | true | Resolve the incident on recovery if untouched |
| `SD_ONCALL_PRIORITIES` / `SD_ONCALL_SMS` | `p1_critical,p2_high` / true | Which priorities page on-call, and whether by SMS |
| `SD_KB_REQUIRE_REVIEW` / `SD_KB_REVIEWER_GROUP_ID` | false / "" | KB review, and who reviews (empty: admins) |
| `SD_KB_RAG_MIN_SCORE_VECTOR` / `SD_KB_RAG_MIN_SCORE_WORDS` / `SD_KB_RAG_MAX_SOURCES` | 0.35 / 0.5 / 3 | Relevance to cite an article (with / without sentence model), and articles per answer |
| `SD_KB_CORRECTION_MATCH` | 0.8 | Similarity for an expert correction to apply |
| `SD_KB_STALE_DAYS` | 180 | Days untouched before a published article is flagged (0: off) |
| `SD_KB_CONTRADICTION_SIMILARITY` / `SD_KB_CONTRADICTION_MAX_PAIRS` | 0.75 / 10 | Which article pairs are compared with AI, and how many per daily run (0: off) |
| `SD_TIME_TO_TIMESHEET` | true | Ticket time goes to the timesheet |
| `SD_ASSET_REFRESH_DAYS` | 7 (≥0) | Renewal ticket lead time; 0 = off |
| `SD_EVENT_MAX_ATTEMPTS` / `SD_EVENT_BATCH_SIZE` | 5 / 200 | Outbox retries and batch size |

**Other.** `SEMANTIC_EMBEDDINGS_BACKEND` (default `tfidf`), in the `ai` group. `DEFAULT_TIMEZONE` (default `Europe/Madrid`), which is also the Celery beat timezone.

**Credentials** (*Settings → Credentials*):

| Credential | Purpose |
|---|---|
| SMTP | Outgoing mail |
| *Service Desk mailbox* | The support mailbox (`protocol`, `host`, `port`, `user`, `password`, `folder`) |
| *Microsoft 365 / Graph* | Graph mailbox (`ms_graph`) |
| *Inbound webhooks* | `inbound_email_secret` |
| *Monitoring alerts* | `ingest_token` |
| Twilio | `auth_token`, `from_number` |
| contecmind | `base_url`, `client_id`, `client_secret` |

---

### Background jobs (Celery beat, `app/worker.py`)

Times are in `DEFAULT_TIMEZONE`.

| Task | Schedule | What it does |
|---|---|---|
| `sd_procesar_eventos_de_ticket` | every minute, plus on every commit | Outbox: bell, email, webhooks, workflows |
| `sla_breach_scan` | every 5 min | SLA/OLA/UC status and notifications, then escalation rules |
| `sd_leer_buzones` | every 2 min | Reads each organisation's mailbox |
| `asset_expiry_scan` | daily 07:05 | Renewal tickets for ALM assets |
| `problem_auto_detect` | hourly :05 | Problems from recurring incidents |
| `cmdb_discovery_run` | every 15 min | Discovery providers that are due |
| `change_impact_batch_score` | every 10 min | Risk scoring of pending changes |
| `routing_outcome_scan` | hourly :20 | ML routing outcome backfill |
| `predictive_scan` / `predictive_model_eval_retrain` | every 30 min / every 6 h at :10 | Predictive analytics |
| `analytics_snapshot` | hourly :50 | `sd_itsm_metric_snapshots` |
| `catalog_popularity_update` | every 6 h | Catalogue popularity |
| `compliance_check` | Monday 06:00 | Compliance report |
| `autonomous_agent_scan` | every 5 min | Autonomous playbooks (see *Tools*) |
| `kedb_expiry_scan` / `kedb_effectiveness_scan` | daily 06:30 / 07:00 | KEDB maintenance |
| `alert_correlation_scan` | every 30 min | Clusters open alerts and tickets into Problems |

Workflow `wait` timers do **not** run in Celery: they run in the API process's scheduler.

---

### Migrations relevant to the Service Desk

| # | Change |
|---|---|
| 098 | `sd_ticket_events` (outbox); `email_templates.code/language/is_active`; `sd_sla_policies.timezone`; six new notification types |
| 099 | `sd_sla_policies.calendar_id` |
| 100 | Numbering unique per organisation (PostgreSQL constraints only) |
| 101 | `sd_inbound_messages` |
| 102 | `sd_tickets.approval_status`; `sd_ticket_approvals` |
| 103 | `sd_change_approvals`, `sd_change_blackouts`, `sd_releases`; quorum, meeting and implementer on `sd_change_requests` |
| 104 | `sd_monitoring_alerts` |
| 105 | `kbstatus.in_review`; `sd_kb_articles.deflection_count`, `embedding`, `review_comment` |
| 106 | `sd_ticket_time_logs.imputation_id` |
| 107 | `sd_service_items.fulfillment_tasks` |
| 108 | `sd_agent_groups.ola_hours`; `sd_tickets.group_assigned_at`, `ola_due`, `ola_pause_base`, `ola_breached` |
| 110 | Single CMDB (drops `cmdb_items`, `cmdb_relations`, `cmdb_categories`) |
| 111 | Single asset inventory (drops `sd_assets`, `sd_asset_history`; creates `alm_asset_history`) |
| 113 | `alm_contracts.resolution_hours`; `sd_tickets.uc_contract_id`, `uc_started_at`, `uc_due`, `uc_breached` |
| 114 | `sd_ci_class_fields` |
| 115 | `alm_contracts.response_hours`; `sd_tickets.uc_vendor_responded_at`, `uc_response_due`, `uc_response_breached` |
| 116 | Optional `sd_kb_articles.embedding_vec` (pgvector) |
| 117 | Data only: encrypts the e-sign credentials stored in plain text in `app_settings` (`esign.*` keys matched by `settings_service.es_sensible`) |
| 118 | Automations that fire: trigger stored as text, event outbox |
| 119 | SHA-256 fingerprint of API keys, so they authenticate |
| 120 | Custom roles that apply: assignable and unique per organisation |
| 121 | BPMN engine: process instances and their steps |
| 122 | SSO: provider display name and groups claim |
| 123 | Rows without organisation assigned to theirs (and the client decision on an invoice) |
| 124 | Integrations: deletes data invented by simulated syncs |
| 125 | Uniqueness per organisation for business codes and names |
| 126 | Each company's own domain (`subdomain` entry mode) |
| 127 | Reason for suspending a company |
| 128 | Company deletion: quarantine before purging its data |
| 129 | Approvals: step delegate and last reminder |
| 130 | AI providers: fallback order (`priority`) |
| 131 | Out of office: approval delegate between two dates |
| 132 | Scheduled automations: `schedule_cron` and `next_run_at` |
| 133 | Knowledge-base quality: `sd_kb_corrections`, `sd_kb_gaps`, `sd_kb_findings` |
| 134 | MCP: `mcp_pending_actions` (writes waiting for human approval) |
| 135 | Data only: rows without a company re-homed from their own record; mixed ITSM snapshots deleted |

---

### Known limitations (summary)

**Never verified against real systems.** IMAP, Microsoft 365, Alertmanager, Twilio, contecmind, cloud discovery providers and pgvector were not tested against the real thing.

**Ticket handling.**

- ~~The ticket panel cannot write internal notes.~~ Fixed 2026-11-03.
- ~~Priority changes do not recalculate SLA due dates.~~ Fixed 2026-11-03.
- ~~*Back to previous* drops the paused time.~~ Fixed 2026-11-03.
- The Kanban board puts closed and cancelled tickets in *Open*, and dropping a card on *Open* sends an invalid status.
- ~~*My queue* shows at most 25 tickets.~~ Fixed 2026-11-03.

**Other modules.**

- The Agent dashboard KPIs (resolved, resolution time, SLA %, CSAT) are always zero or empty.
- On-call rotations do not generate shifts.
- OLA is one target per queue for every priority.
- CMDB discovery, drift, reconciliation and SNMP are API only. The *Agents* tab returns 403 for a pm.
- CI classes are fixed (`CIType`); only their fields are configurable.
- ~~The autonomous agent runs on every organisation with no on/off setting and hard-coded thresholds.~~ Fixed 2026-11-03: off by default, per-organisation switch and thresholds.
- CSAT is only requested when a ticket is closed and only in the portal; no email is sent.

**Access.** `team_lead` sees *Service Desk* in the menu but gets 403.

---

## Analytics, BI, AI & Automation

This section describes what each Analytics, BI, AI and Automation screen does as of this revision. Every statement comes from reading the code, unless it is marked "Not verified".

- Paths are relative to the repository root.
- Role lists come from `frontend/src/App.tsx` (the route guard) and `frontend/src/components/layout/Layout.tsx` (the menu).
- The backend role dependencies are in `app/core/deps.py`:
  - `require_admin_or_pm` = admin, pm
  - `require_any_manager` = admin, pm, team_lead, hr
  - `require_internal_user` = the four manager roles plus employee
- Where the frontend and backend roles differ, the module says so. The backend check is the one that actually protects the data.

### Review of 2026-11-04: what was broken and what changed

Measured against a copy of the database with a local Ollama model. Tests: `tests/test_ia_revision_2026_11.py` (28 tests) and `tests/test_portal_revision_2026_11.py`; each fix was reverted once to check that a test turns red.

| Area | Before | Now |
|---|---|---|
| Voice commands (`/voice/command`, `/voice/transcribe`) | Always HTTP 500 (`confirm` argument) | Work; without `confirm` they return the pending action |
| Accepting an AI ticket triage | 500 (`critical` is not a ticket priority) | Mapped to `p1_critical`…`p4_low` |
| Meetings → "Create tasks" | 500 (task without `code`) | Tasks get a `TSK-…` code and a reporter |
| Smart Schedule | The model returned 1, 2, 3 as task ids; applying gave 500 | Tasks are numbered in the prompt and mapped back to their ids |
| RCA wizard AI hint | Always failed; wrong step shown | Reads the text; steps are 1-based |
| NexusAgent | Streamed runs were not saved; history read wrong fields; writes auto-approved | Streamed runs saved; history shows result and steps; "Allow write actions" is off by default |
| KB embeddings | Failed under TF-IDF (`.tolist()` on a list); "rebuilt" counted failures | Stored; rebuild reports `rebuilt` and `failed` |
| Ask the Data | Any JOIN failed (ambiguous `organization_id`) | Tenant filter qualified per table; `dim_date` is not filtered |
| "No AI provider" warning | Returned and stored as if it were the answer | `es_aviso_de_ia()` detects it; Ask the Data, SD suggestions and `call_ai_unified` treat it as an error |
| Revenue in BI / ML / KPIs | Always 0 (hours × `billing_rate`, which is empty) | Adds invoiced subtotals (not draft or cancelled) of projects without a rate |
| Average margin KPI | Its own formula | `profitability_service.calc_project_profitability` |
| Earned value (ML features) | Budget × elapsed time | Budget × task progress |
| ML / OLAP jobs | Celery beat only: never ran under APScheduler | Also in APScheduler, same cadence (`app/main.py`) |
| Anomaly detection | 3 of 5 metric buttons sent unknown keys (all-zero series) | `revenue`, `tickets_created`, `utilization`, `hours_logged`, `first_response_time_avg` |
| Churn form | Sent field names the model does not use | Sends the model's `CHURN_FEATURES` |
| NexusOracle | Acknowledging did not stick; enum shown in text; SLA limit always "medium"; header showed the AI provider | List returns `is_acknowledged` and `entity_name`; limit by the ticket's level; no provider shown (rules only) |
| Scenarios | `%W` weeks (off by one); all active users, admin and HR included; existing bookings ignored | ISO weeks; roles from `SCENARIO_CAPACITY_ROLES` (Admin → Settings → locale) with each person's weekly hours; firm bookings added as `committed_hours` |
| NexusAssist | The page context never reached the prompt; the inline editor opened a new conversation per call | Project or ticket on screen goes into the prompt; one inline-editor conversation per user, without history |
| Voice agent (Service Desk) | Ticket without organization; "urgente" stayed medium | Organization set; urgency words make it `p1_critical` |
| Data Platform presets | Empty dropdown | Filled |
| Data Governance lists | DSR, consents, masks, comments and shared views always empty | Filled (`unwrapList` reads both response shapes) |
| Portal AI chat | Fed other clients' projects to the model when the client had no company; showed an internal instruction when there was no provider | Assigned projects only; a project summary when there is no provider |
| Prediction history, at-risk projects, anomalies | Project id instead of name; no CPI/SPI; no month per anomaly | Name, CPI/SPI and `period` (`YYYY-MM`) |
| Risk (signal score and ML) | Budget at 80 €/h; team load fixed at 85 %; overloaded members always 0; training label in hours; no-data projects counted as low risk | Real internal cost; measured team load and overloaded members; label in euros; `without_data` count |
| AI timeouts | Hardcoded 60/120/90/30 s | Admin settings (group `timeouts`) |
| Forecast chart | Bands never drawn (`lower_bound`/`upper_bound` were not read); a MAPE label nobody filled | Bands drawn; MAPE label removed (the backend does not compute it) |
| Semantic engine offline | Only `ImportError` fell back | Any load error falls back to TF-IDF with a warning |

**Still open (not fixed in this review):**
- LightGBM needs OpenMP. On macOS `setup.sh` now installs `libomp` with Homebrew when the ML requirements are installed (it was missing and churn fell back to the 5 rules).
- Similar-task suggestions need `imputations.task_id`; time logged without a task does not count.
- 8 old `ai_usage_logs` rows from before the fix are marked `success=true` although they were warnings.
- `/bi/kpi` WebSocket pushes need Redis; without it `bi_kpi_push` computes and drops the snapshot.
- Meeting actions have no priority: the model does not extract it and there is no column for it; the screen shows it only when present.
- Backend with no screen: `ai-planning/*`, `/sd/tickets/{id}/ai-analyze|ai-auto-resolve|ai-explain|smart-assign`, `/sd/predictive/*`, `/bi/intelligence/ml/*`, `/revenue-forecast`, `/overrun-prediction`, `/ai-modules/kb/search|generate`, `/semantic/prioritize`.

**Not verified:** tool-calling NexusAgent (Ollama has no tools; no paid API was called), Azure and o-series providers, Whisper transcription with real audio, the Celery worker path, Ask the Data on ETL-filled DuckDB data, and LLM output quality beyond a 7B local model.

### What is real AI here, and what works offline

**LLM calls.** All LLM calls go through `app/services/ai_provider_service.py` (`call_ai` / `call_provider`). The only exception is a legacy direct-to-Anthropic path, covered at the end of this subsection.

**Supported providers.** There are 8, all called over plain HTTP:

| Provider | API used |
|---|---|
| anthropic | native `/messages` |
| openai, groq, mistral, deepseek, azure | OpenAI-compatible `/chat/completions` |
| gemini | `generateContent` |
| ollama | `/api/chat` |

**How the provider is chosen:**
1. An explicit `provider_id`.
2. Otherwise the organization's default row in `ai_providers`, which you configure in **AI Hub**.
3. Otherwise a global row.
4. Otherwise the `.env` provider: `AI_PROVIDER` + `AI_API_KEY` + `AI_MODEL` + `AI_BASE_URL` (`app/core/config_groups/ai_config.py`). `ANTHROPIC_API_KEY` is accepted as a legacy alias.

If the chosen provider fails, every other active provider is tried once. If none answers, the call returns HTTP 200 with the text "⚠️ No hay ningún proveedor de IA configurado…", or "⚠️ AI provider error: …" if a provider failed. **This text is returned as if it were the answer.** Several features display it, store it, or cache it (see each module).

| Capability | Mechanism | Needs an LLM provider? | Behaviour without one |
|---|---|---|---|
| NexusAssist chat (floating panel, Cmd+I) and `AIInlineEditor` | LLM (`call_ai`, module `nexusassist`) | Yes | The warning text is stored as the assistant's reply. In the inline editor it **overwrites or appends to the field**. |
| NexusAgent (`/nexus-agent`) | LLM with real tool/function calling (37 tools, 7 of them write) | Yes, and the provider must support tools (Ollama does not) | Text-only "degraded mode" through `call_ai`, which also needs a provider |
| BI narrative (`NarrativeCard`) | LLM (module `bi_storytelling`) | Optional | Template text built from KPIs |
| Ask the Data (`AskDataWidget`) | LLM writes SQL, which then runs on DuckDB | Yes, in practice | 3 keyword-matched SQL fallbacks. All 3 fail on DuckDB (see Data Explorer). |
| AI Assignment tie-break (`/semantic-engine`, hybrid/LLM modes) | LLM (module `semantic_assign`) | Only for the tie-break | Ranking by embeddings plus workload only |
| AI Hub "Test" / "Sync models" / "Diagnóstico" | Real HTTP calls to the provider | Yes | Error shown |
| AI Assignment ranking | Cosine similarity on embeddings stored as JSON text. Backend is sentence-transformers if installed, otherwise a pure-Python TF-IDF. **No pgvector.** | No | Works offline |
| Risk ML tab (`/risk-scores`) | Real scikit-learn `GradientBoostingClassifier`, trained per organization on its completed projects | No | Rule table if there is no model or fewer than 5 samples |
| BI anomaly detection | scikit-learn `IsolationForest`; z-score if sklearn is missing | No | Works offline |
| BI forecasting | Hand-written OLS / Holt; Prophet and ARIMA only if `requirements-ml.txt` is installed | No | Works offline |
| Churn "prediction" | LightGBM trained on **1,400 synthetic rows** if LightGBM loads, otherwise 5 additive rules | No | Rules |
| NexusOracle, rule-based risk score, alerts engine, smart alerts, governance checks | Rules and thresholds | No | Works offline. None of them is ML or LLM. |
| Automations, BPM | No AI at all | No | — |

**ML libraries in the image.** `deploy/Dockerfile.backend` installs only `requirements.txt` (duckdb, scikit-learn, pandas, numpy). The `requirements-ml.txt` line is commented out. So the Docker image has **no** Prophet, statsmodels, LightGBM or sentence-transformers. The features that use them fall back silently, as described per module.

**Runtime settings group `ai`** (`app/services/settings_service.py`). It contains:
- `CONTECFLOW_AI_MODEL`
- `SEMANTIC_EMBEDDINGS_BACKEND`
- `OPENAI_STT_MODEL`
- `AI_COST_ALERT_USD_PER_DAY`
- STT keys

**None of these selects the chat provider or model used by `call_ai`.** That comes from AI Hub or `.env`.

**Cross-cutting LLM limitations (measured):**
- **`AI_MODEL` is effectively required for the `.env` provider.** Without it, the literal model name `"default"` is sent.
- **Temperature 0.0 is honoured** since 2026-11-04 (it used to become 0.7). 0.7 is used only when the provider has no temperature set. Ollama now receives the temperature and records its token counts (`prompt_eval_count`/`eval_count`).
- **Timeouts are settings** (since 2026-11-04, Admin → Settings → **Timeouts**): `OUTBOUND_AI_TIMEOUT_SECONDS` 60 (cloud providers and the legacy Anthropic paths; it was 30 and only used by the latter), `AI_LOCAL_HTTP_TIMEOUT_SECONDS` 120 (Ollama), `AI_AGENT_TURN_TIMEOUT_SECONDS` 90, `AI_MODELS_LIST_TIMEOUT_SECONDS` 30. The `ai_providers.timeout_seconds` column is still never read: no API or screen sets it, and its default of 30 s would cut local models short.
- **No retries.** Any exception marks the provider `status="error"`, and it is excluded from selection until an admin edits, tests or syncs it.
- **Usage and cost go to `ai_usage_logs`,** using catalog prices. Models that "Sync models" discovers but that are not in the catalog cost $0, and Ollama is always $0. `AI_COST_ALERT_USD_PER_DAY` only writes a log warning.
- **PII redaction is regex-based** (`app/services/ai_governance.py`). It applies only if the organization has active `AIGuardrailPolicy` rows. None are seeded and there is no UI to create them, so by default nothing is redacted. It checks only the last user message, not the system prompt, which carries the tenant data context.
- **Azure is probably broken.** It is called with a `Bearer` header on the generic path, with no deployment or `api-version`. Not verified.
- **o1/o3/o4-mini may be rejected.** They are offered, but `max_tokens`/`temperature` are always sent. Not verified.
- **A legacy path skips provider selection and logging.** `ai_client.call_claude`, `ai_modules/_base.call_claude`, `POST /ai/chat/stream` and `ai_planning_service` POST to `ANTHROPIC_API_URL` directly. `/ai/chat/stream` sends the stored key without decrypting it. The streaming endpoint has no frontend caller. Not runtime-verified.
- **Some callers can use another tenant's provider.** `call_ai` defaults `is_superadmin=True`, so a caller that does not pass it can pick another organization's provider and key. Affected callers: `POST /ai-providers/chat`, the AI Assignment tie-break, and the NexusAgent worker path.

**Data layer for BI.** Several BI widgets read a DuckDB OLAP file, not Postgres:
- Location: `DUCKDB_PATH`, otherwise `/var/contecflow/olap.duckdb`, otherwise `/tmp/contecflow/olap.duckdb`.
- It is filled by the job `olap_nightly_etl` (01:00 daily, `olap/etl.run_full_etl`). Since 2026-11-04 it runs under APScheduler too (the default mode of `setup.sh`), not only under Celery beat.
- Until that job has run, DuckDB-only features (Ask the Data) return errors. KPIs fall back to Postgres.

**Response unwrapping.** The axios interceptor (`frontend/src/services/api/_core.ts:50-74`) turns `{items, meta}` into a bare array. Components that then read `.items` get `undefined`. Data Platform and Data Governance were fixed on 2026-11-04 by reading lists with `unwrapList` (`_core.ts`), which accepts both shapes.

---

### Executive Dashboard — `/executive`
*Roles:* admin, pm (route and menu). Backend: KPIs use `get_current_user`; project health uses `require_any_manager`.

**Purpose.** A one-page executive view with KPI cards, an AI narrative, natural-language questions and a project health table.

**How to use it.**
1. There is no period selector: cost and hours are month to date; margin, pipeline and projects are current.
2. Read the KPI cards (since 2026-11-03, what the server computes): **Cost · month to date**, **Hours · month to date** (with billable %), **Average margin** of active projects, **Weighted pipeline** (with open opportunities and won revenue) and **Active projects** (with high-risk count).
3. Expand the narrative card. The refresh icon ("Regenerar narrativa") forces a new narrative.
4. Type a question in the Ask the Data box, or open "Ver preguntas de ejemplo". The result table has a show-SQL toggle.
5. Scroll to the project status table (Project / Status / Risk / Budget used / Progress, first 12 rows). If the fetch fails, the page falls back to an offline Dexie cache.

**Configuration.**
- An LLM provider is optional for the narrative and required for Ask the Data (see the intro).
- The DuckDB path is set by `DUCKDB_PATH`.
- The narrative cache uses Redis (`REDIS_URL`) if present, otherwise in-process memory, with a 3600 s TTL.

**Technical notes.**
- `GET /api/v1/analytics/olap/kpis` → `olap/query_engine.get_kpi_summary`. It reads DuckDB `fact_imputations`, `dim_date`, `fact_pipeline` and `fact_projects`. Without the DuckDB file it uses `_pg_kpi_summary` over `projects`, `opportunities` and `imputations`.
- `GET /api/v1/dashboard/projects-health` → `dashboard_service.get_projects_health`.
- `GET /api/v1/analytics/narrative?lang&force_refresh` → `services/bi_storytelling.generate_narrative`. This is a real LLM call (`call_ai(module="bi_storytelling", max_tokens=800)`), logged to `ai_usage_logs`.
- `POST /api/v1/analytics/ask` → `services/ask_the_data.ask`, described under Data Explorer.

**Limitations (measured).**
- ~~The KPI cards show €0 regardless of the data; the period buttons filter nothing; Cliente and Budget are always "—".~~ Fixed 2026-11-03: the page reads the keys `get_kpi_summary` returns (`cost_mtd`, `hours_mtd`, `billability_pct`, `avg_margin_pct`, `pipeline_weighted`, `open_opps`, `won_revenue`, `active_projects`, `high_risk_projects`); the period buttons were removed; the table shows `risk_level`, `budget_used_pct` and `progress_pct`. Test: `frontend/src/__tests__/BIPage.test.tsx`.
- There is no revenue KPI: `get_kpi_summary` does not compute revenue. Revenue is on the Finance dashboard.
- Narrative issues:
  - A provider *error* ("⚠️ AI provider error…") does not match the fallback check, so the error text is displayed and cached for 1 h.
  - The cache key ignores the language.
  - ~~Any authenticated user can force a paid LLM call with `force_refresh`.~~ Fixed 2026-11-03 (test `tests/test_api_con_los_roles_de_sus_pantallas.py`): `/analytics/narrative` is admin or PM, like its screens.
  - The fallback template is Spanish only for `lang=es`; every other language gets English.

### Data Explorer — `/data-explorer`
*Roles:* admin, pm (route). Backend (since 2026-11-03): admin or PM for schema, templates, presets and previews (before, any user, or `require_internal_user` for previews); `/bi/intelligence/reports/*` is admin-only, like `/data-platform`.

**Purpose.** Ad-hoc exploration: the AI narrative, Ask the Data, and two query builders.

**How to use it.**
- **Ask the Data:** type a question, then submit. Open the SQL toggle to see the generated query.
- **Constructor visual de consultas** (`VisualQueryBuilderWidget`):
  1. "Selecciona entidad..."
  2. Tick the **Columnas** you want.
  3. Add filters with **+ Filtro** (Campo / operator / Valor).
  4. Set the order: Sin orden / Asc / Desc.
  5. Press **Previsualizar**.
  6. To keep the query, type "Nombre de plantilla..." and press **Guardar**. Saved queries appear under **Plantillas guardadas**, where you can load or delete them (**Eliminar**).
- **Query builder** (`BiQueryBuilderPanel`, tabs 🔧 Constructor / 📁 Guardadas / 📊 Resultados):
  1. Choose a Dataset.
  2. Toggle fields and add filters.
  3. Optionally set group-by and aggregations (count/sum/avg/min/max, with an alias).
  4. Set the Dirección and Límite.
  5. Press **▶ Ejecutar**, or type a name and press **💾 Guardar**.

**Configuration.** An LLM provider is needed for Ask the Data, and DuckDB must have been filled by `olap_nightly_etl`. The query builders need no configuration.

**Technical notes.**
- **Ask the Data:** `POST /api/v1/analytics/ask` → `ask_the_data.ask`.
  1. `_generate_sql` asks the LLM for SQL (`max_tokens=400`).
  2. `validate_sql` checks it: SELECT only, a keyword blacklist, a whitelist of 9 OLAP tables, and LIMIT capped at 200.
  3. It injects an `organization_id = <org>` filter.
  4. The query runs on DuckDB only. It retries once with the error as feedback.
  5. **Verification (revision 2026-11, what contecintelligence had).** `ask_verificacion.verificar` checks that the query answers *this* question and not a similar one. It reads the tree of the LLM's query (DuckDB `json_serialize_sql`, no new dependency), before our tenant filter and LIMIT are added. Checks:
     - `time_window`: the question limits a period and the query does not filter by a date column.
     - `breakdown`: «por proyecto», «by month» and so on, with an ungrouped total.
     - `ranking`: «top», «los que más», «highest», with no ORDER BY. «mayor que» counts as a filter, not a ranking.
     - `units`: a percentage without a division or a `*_pct` column, or an average without `avg`.
     - `distinct`: «distintos» without `COUNT(DISTINCT)` or `SELECT DISTINCT`.

     The answer carries `verification: {verdict, checks}`. The widget shows *Responde a lo preguntado (N comprobaciones)*, the warnings, or *Sin comprobar* when nothing applied. A verdict is `verified` only if at least one check ran; when nothing could be checked it says `not_checked`, never `verified`. Intent patterns cover Spanish, English and Chinese. The Chinese ones have no word boundaries (`\b` does not separate Chinese characters), so they are separate patterns: 三月 / 本月 / 去年, 按项目 / 每个月, 前5 / 最多, 占比 / 平均, 不同 / 去重.
- **Visual builder:**
  - `GET /api/v1/bi/intelligence/query-builder/schema`
  - `POST /api/v1/bi/intelligence/query-builder/preview` (500 rows)
  - `GET/POST/DELETE /api/v1/bi/intelligence/query-builder/templates[/{id}]`
  - Templates are stored in `app_settings` under the key `bi.intelligence.query_builder.templates.{user_id}`.
- **Query builder:**
  - `GET /api/v1/bi/query-builder/schema`
  - `GET/POST /api/v1/bi/query-builder/queries`
  - `POST /api/v1/bi/query-builder/preview`
  - `POST /api/v1/bi/query-builder/queries/{id}/execute`
  - `DELETE /api/v1/bi/query-builder/queries/{id}`
  - Saved queries go in `app_settings` under `bi.query_builder.saved`, per organization.
- Both builders run on `report_builder_service.execute_report`: ORM queries over 20 whitelisted entities, scoped by tenant only.

**Limitations (measured).**
- **Ask the Data fails on most joins.** The tenant filter is injected without a table qualifier. A join between two tables that both have `organization_id` (for example a fact table and `dim_project`) raises DuckDB "Ambiguous reference to column name organization_id". This was reproduced with DuckDB 1.3.0. It breaks all three hardcoded fallback queries and any LLM-written fact/dim join. Only single-table queries, or joins with `dim_date`, work.
- **Without a provider, Ask the Data returns an error.** The result is "SQL no permitido: Only SELECT queries are allowed", unless the question matches one of the 3 fallback keyword patterns, which then fail as above.
- **Grouped totals are wrong above 5,000 rows, without warning.** Group-by and aggregation run in Python over at most 5,000 base rows.
- **Two builders on the same engine.** Both appear on the page, with separate storage.
- ~~Employees can read cost data the route hides.~~ Fixed 2026-11-03 (test `tests/test_api_con_los_roles_de_sus_pantallas.py`).

### Reports — `/reports`
*Roles:* the route has **no role restriction** (any authenticated user); the menu shows it to admin, pm, hr and employee. Backend: catalogue and query use any authenticated user; scheduled-report writes use `require_any_manager`.

**Purpose.** A metric catalogue and chart explorer, hardcoded report templates, and scheduled email reports.

**How to use it.** Pick a mode in the header:
- **Métricas:** browse the catalogue by category. Clicking a metric opens it in the Explorador.
- **Explorador:**
  1. Pick a metric, a colour and a date preset (7d/30d/3m/6m/1a).
  2. Pick one of 10 chart types (recharts).
  3. Filter by project, user, department or top-N.
  4. Use **💾 Guardar** to save, **⬇ CSV** to export, or **📷 PNG** to capture (html2canvas). The current period is compared with the previous one.
- **Plantillas:** about 107 presets, hardcoded in the frontend.
- **Visualizaciones:** advanced chart gallery (`BiAdvancedViz`).
- **Guardados:** reports saved with 💾.
- **Programados:**
  1. Fill in Nombre, Métrica (8 fixed choices), Frecuencia (daily/weekly/monthly), Destinatarios (comma-separated) and "adjuntar PDF".
  2. Each row has **⏸ Pausar / ▶ Activar**, **▶ Enviar ahora**, **📄 PDF** and delete.

**Configuration.**
- Email uses `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASS` and `SMTP_FROM` (`app/core/config.py`). These come from the environment only; they are not runtime settings.
- An optional Slack webhook can be set per scheduled report.

**Technical notes.**
- `GET /api/v1/analytics/catalogue`: the static `CATALOGUE`, 110 metrics.
- `GET /api/v1/analytics/filters/options`
- `GET /api/v1/analytics/query/{metric_id}`: dispatches through `METRICS_REGISTRY` (109 handlers), with project scope from `get_filtered_project_ids` and a cache TTL per metric.
- Scheduled reports (`app/api/v1/endpoints/billing_reports.py`, `app/services/billing_reports_service.py`, table `scheduled_reports`):
  - `GET/POST /api/v1/billing-reports/scheduled-reports`
  - `PATCH/DELETE .../{id}`
  - `POST .../{id}/run`
- Worker `run_scheduled_reports` runs hourly at :00 and calls `scheduled_reports.run_due_reports`. PDFs use reportlab; email uses smtplib with STARTTLS.

**Limitations (measured).**
- **Saved reports disappear on reload.** "Guardar" stores them in a module-level JS variable; nothing is persisted.
- **Visualizaciones shows sample data, not yours.** Every chart there draws hardcoded sample data, and the heatmap uses `Math.random()`.
- **`projects_by_client` is always empty.** It is in the catalogue with no handler, and handler exceptions are swallowed into empty rows.
- **The CSV export breaks on commas.** Values are joined without quoting.
- Scheduled reports:
  - **The emailed PDF has no data.** It is built with `data=[]`, because `report_type` is never set and falls back to "custom". The chosen metric is never queried, and `include_pdf` is never read.
  - **📄 PDF opens a wrong path** (`/api/v1/scheduled-reports/...` instead of `/api/v1/billing-reports/...`). The correct endpoint renders placeholder rows anyway.
  - **Without SMTP, nothing is sent but the run reports success.** The run is marked `success`, and "Enviar ahora" shows "Informe enviado a: …".
  - **The schedule ignores send hour and day.** `send_hour`, `day_of_week` and `day_of_month` are ignored; the next run is simply now + 1 day/week, or the 1st of the month at 08:00.
  - ~~Any user sees the scheduled reports and PATCH copies any field.~~ Fixed 2026-11-03 (`tests/test_informes_programados_roles_y_campos.py`): the list is for admin, pm, team_lead and hr (the *Programados* tab is hidden for the rest), and PATCH accepts only the editable fields (422 otherwise) and runs the ABAC check. Measured: the list was already limited to the user's organization by the tenant filter.
- Worker `send_weekly_report` (Monday 09:00) is a stub that only collects admin emails.

### Report Builder — `/report-builder`
*Roles:* admin, pm (route). Backend: `/reports/preview` and `/reports/export` use `require_internal_user`; `/reports/schema` and `/reports/templates` use any authenticated user.

**Purpose.** A tabular report designer over whitelisted entities, with CSV export and per-user templates.

**How to use it.** Tab **🔧 Constructor**:
1. Pick an entity.
2. Tick columns. If you tick none, all columns are used.
3. Add filters.
4. Choose the sort column and direction.
5. Press **▶ Previsualizar**, then **⬇ Exportar CSV**.
6. To reuse the report, name it and press **💾 Guardar plantilla**. Saved templates are in **📁 Plantillas (n)**.

There is also a **⚡ Presets BI** tab; see Limitations.

**Configuration.** None.

**Technical notes.**
- Endpoints:
  - `GET /api/v1/reports/schema`
  - `POST /api/v1/reports/preview` (limit up to 500, hard cap 2,000)
  - `POST /api/v1/reports/export` (CSV via `csv.DictWriter`)
  - `GET/POST/DELETE /api/v1/reports/templates`
- Service: `app/services/report_builder_service.py`.
- **20 entities:** projects, tasks, imputations, users, expenses, sprints, tickets, opportunities, contracts, risks, absences, timesheets, milestones, deliverables, clients, subcontractors, subcontractor_workers, subcontractor_assignments, problems, kb_articles.
- **Query safety:**
  - Columns are whitelisted per entity, with 12 operators.
  - Queries are built with the SQLAlchemy ORM; there is no raw SQL.
  - An invalid column or operator returns 400. An unknown sort column is ignored.
  - `%` and `_` in `contains`/`starts_with` values are not escaped. That allows wildcard injection only, not SQL injection.
- Templates are stored as JSON in `app_settings`, key `report_templates:{user_id}`.

**Limitations (measured).**
- **The CSV is silently capped at 2,000 rows.** The frontend sends no paging, and the `X-Total-Count` header is ignored.
- **Builder reports cannot be scheduled.**
- **⚡ Presets BI never returns data.** `bi_report_builder_v2_service.execute_preset_with_controls` calls `execute_report` with arguments that do not match its signature (checked with `inspect.signature.bind`: TypeError). The error is caught, so every preset preview and export returns `rows=[]` with `degraded=true`. Export with `format=csv|xlsx` still returns JSON. The existing tests only check the response shape.
- ~~No row-level filter by role: an employee can read `hourly_rate` and imputation costs.~~ Fixed 2026-11-03: the endpoints are admin or PM. Within those roles there is still no row-level filter (a PM reads the whole organization).

### Predictions — `/predictions`
*Roles:* admin, pm (route). Backend: `require_internal_user` for writes and calculations.

**Purpose.** Statistical forecasting, anomaly detection, a churn what-if calculator and conditional report-delivery rules. **There is no LLM on this page.**

**How to use it.**
- **Forecasting BI:**
  1. Pick a Métrica.
  2. Pick a Método: linear / holt / prophet.
  3. Set Períodos (1-24).
  4. Press **Calcular forecast**.
- **Anomalies:** pick a metric button (revenue / tickets / utilization / hours / response_time), then press **Detectar**. The info bar shows "IsolationForest ✅/⚠️ fallback | LightGBM ✅/⚠️ fallback".
- **Predicción de Churn:**
  1. Enter a client id (default `demo-client`).
  2. Enter the 6 numbers: monthly_revenue, support_tickets_last_90d, nps_score, contract_months_remaining, logins_last_30d, open_invoices.
  3. Press **Predecir churn**.
- **Entrega Condicional de Reportes:**
  1. Enter a rule name, a report ID (free text), a Threshold % and recipients.
  2. Press **Crear regla**.
  3. Each rule has evaluate and enable/disable buttons.
- A hint points to `/alerts`, tab "Inteligentes", for smart alerts.

**Configuration.** No settings. Installing `requirements-ml.txt` enables Prophet, statsmodels ARIMA and LightGBM; it is not installed in the Docker image.

**Technical notes.**
- **Forecasting:**
  - `GET /api/v1/bi/forecast/metrics`, `POST /api/v1/bi/forecast` → `bi_forecasting_service.forecast`.
  - History is a 24-month Postgres series from `bi_smart_alerts/metrics._fetch_metric_series`.
  - Methods: hand-written OLS, Holt (α=0.3, β=0.1, the default), ARIMA(1,1,1) and Prophet. ARIMA and Prophet fall back to Holt.
  - Bands are ±1.96 × the RMS of the Holt residuals.
- **Anomalies:**
  - `GET /api/v1/bi/anomaly/info`, `POST /api/v1/bi/anomaly/detect` → `bi_anomaly_service.detect_anomalies`.
  - Uses sklearn `IsolationForest(contamination=0.1, n_estimators=100, random_state=42)` on a single series, or z-score > 2.5 without sklearn.
- **Churn:** `POST /api/v1/bi/churn/predict`.
- **Conditional delivery:**
  - `GET/POST /api/v1/bi/delivery/rules`, `PATCH .../{id}`, `POST .../{id}/evaluate`.
  - Stored in `app_settings` keys `bi.cond_delivery.rules` and `bi.cond_delivery.snapshots`.
- **Related worker jobs** (neither feeds this page):
  - `bi_ml_retrain` (Sunday 03:30) runs multivariate anomaly detection and discards the result.
  - `bi_kpi_push` (every 5 min) pushes a least-squares revenue forecast and z-score anomalies over the realtime channel.

**Limitations (measured).**
- **Prophet silently becomes Holt** without the ML requirements; the response then says `method: "holt"`. ARIMA cannot be selected from the UI. The "hours" metric is aliased to `utilization`.
- **The chart never draws the confidence bands or shows MAPE.** The backend returns `lower_bound`/`upper_bound` arrays, but the frontend expects `.lower`/`.upper` objects and a `mape` field.
- **IsolationForest flags anomalies by construction.** With contamination 0.1 it always flags about 10 % of points: it flagged 3 points on a perfectly linear 24-point series. The `tickets`, `hours` and `response_time` buttons resolve to an all-zero series, so they always report 0 anomalies. The UI's period column is empty, because the backend returns index/value/score only.
- **Churn reads no database data.** `monthly_revenue` and `open_invoices` are ignored. With LightGBM it is trained on **synthetic** data. Without it (Docker image and local venv), it is a 5-rule additive score: NPS < 5 adds +0.3, and so on. High ≥ 0.6, medium ≥ 0.3.
- **Conditional delivery never sends anything.** No worker reads the rules. "Evaluate" always posts `{}`: the first call reports a 100 % change, later calls report no change.

### Alerts — `/alerts`
*Roles:* admin, pm, hr (route and menu). Backend:
- list: any user (employee and subcontractor see only their own)
- run engine: `require_admin`
- mark read: internal user + ABAC
- resolve: `require_any_manager` + ABAC

**Purpose.** Operational alerts produced by a rules engine, plus statistical "smart alerts" on BI metrics. **No LLM.**

**How to use it.**
- **Operativas:**
  - Each alert has **Ver origen**, mark-as-read and **Resolver**.
  - Admins can run the engine on demand with **⚡**.
  - "📊 Exportar Excel" exports the list.
- **Inteligentes** (`SmartAlertsPanel`):
  - Create rules on a metric, then press **Evaluar ahora**.
  - Review the history and acknowledge entries.
  - Default rules can be seeded.

**Configuration.**
- `DEFAULT_WEEKLY_CAPACITY_HOURS` (runtime setting, default 40) is used when a user has no `weekly_capacity_hours`.
- `budget_alert_threshold` and `overload_threshold` appear in Settings, but the engine **never reads them** (see Limitations).

**Technical notes.**
- **Operational alerts** (`app/api/v1/endpoints/alerts.py`, `app/services/alert_service.py`, table `alerts`):
  - `GET /api/v1/alerts?resolved=false`
  - `POST /api/v1/alerts/run`
  - `PATCH /api/v1/alerts/{id}/read`
  - `PATCH /api/v1/alerts/{id}/resolve`
- **Engine `AlertEngine.run_all`**, hardcoded rules:

  | Rule | Fires when | Severity |
  |---|---|---|
  | overload | > 100 % of weekly capacity | warning; critical at ≥ 120 % |
  | budget | ≥ 85 % of budget | warning; critical at ≥ 100 % |
  | task_blocked | blocked > 2 days | — |
  | no_imputation | no hours logged for > 2 days (employee/subcontractor only) | — |
  | deadline_risk | due within 7 days | — |

- Worker `run_alert_engine` runs daily at 08:00. The engine only inserts rows; no email or notification is sent.
- **Smart alerts** (`bi_smart_alerts_service`):
  - `GET /api/v1/bi/alerts/supported-metrics`
  - `GET/POST/DELETE /api/v1/bi/alerts/rules`
  - `POST /api/v1/bi/alerts/evaluate`
  - `GET /api/v1/bi/alerts/history`
  - `POST /api/v1/bi/alerts/history/{id}/acknowledge`
  - `POST /api/v1/bi/alerts/seed-defaults`
  - Rules and log are stored in `app_settings` (log capped at 500).
  - Conditions: threshold above/below; strict monotonic trend up/down; anomaly when |z| ≥ 2.0, or robust MAD z ≥ 3.5, or deviation from the mean ≥ 35 %.

**Limitations (measured).**
- **Thresholds are hardcoded; the Settings values are inert.** `burnout_risk` and `hours_deviation` exist as alert types, but nothing generates them.
- ~~"Run" alerts every tenant.~~ Wrong: measured on 2026-11-03 with two organizations, ⚡ pressed by an org admin only created alerts for that organization (the request's tenant filter scopes the engine's queries). The daily job runs without a tenant and covers all organizations; each alert takes the organization of its user or project.
- **Units are mislabelled.** Budget percentages are shown as "€", and deadline days as "%". The user name never appears: the page reads `display_name`, but the API returns `full_name`.
- Smart alerts:
  - **Evaluated only when you press "Evaluar ahora".** No worker evaluates them.
  - **Threshold rules created in the UI never fire.** The form sends no threshold.
  - `notification_channels` is stored but never used.
  - UI errors are swallowed.

### EVM — Earned Value — `/evm`
*Roles:* admin, pm (route). Backend: the portfolio list uses `require_admin_or_pm`; per-project detail uses `get_current_user` only.

**Purpose.** Earned Value Management for active and on-hold projects.

**How to use it.**
1. Read the four cards: Proyectos activos (N en riesgo), CPI medio cartera, SPI medio cartera, and Presupuesto total / Gastado.
2. Scan the table: Estado, Proyecto, % Hecho, BAC, EV, AC, CPI, SPI, EAC.
3. Click a row to open the modal: BAC, PV, EV, AC; CPI, SPI, TCPI; CV, SV; EAC, ETC, VAC; progress bars. Close it with **Cerrar**.

There are no filters.

**Configuration.** `DEFAULT_CURRENCY` only. The health thresholds are hardcoded.

**Technical notes.**
- `GET /api/v1/projects/evm/portfolio` → `ProjectService.evm_portfolio`.
- `GET /api/v1/projects/{id}/evm` → `ProjectService.evm` (`app/services/project_service.py`).
- Tables: `projects`, `tasks`, `imputations`.
- **Formulas (detail endpoint):**

  | Value | Calculation |
  |---|---|
  | BAC | `projects.budget_amount`; if 0, Σ`tasks.estimated_hours` × avg `imputations.hourly_rate_snapshot` |
  | AC | Σ`imputations.cost_amount`; if 0, Σhours × rate snapshot |
  | % complete | estimated hours of `done` tasks ÷ all estimated hours |
  | EV | BAC × % complete |
  | PV | BAC × elapsed fraction of start → planned end (straight line; no baseline) |
  | CPI | EV ÷ AC |
  | SPI | EV ÷ PV |
  | CV | EV − AC |
  | SV | EV − PV |
  | EAC | BAC ÷ CPI |
  | ETC | EAC − AC |
  | VAC | BAC − EAC |
  | TCPI | (BAC − EV) ÷ (BAC − AC) |

- **Health:** grey if CPI or SPI is missing; green if both are ≥ 0.9; red if either is < 0.85; otherwise yellow.
- There is no worker job.

**Limitations (measured).**
- **The list and the detail can disagree for the same project.**
  - The list has no AC fallback: a project with hours logged but no `cost_amount` shows CPI "—" in the list and a real CPI in the modal.
  - Without dates, the list shows SPI 1.0 while the detail shows "—".
- The list runs about 5 queries per project.
- **The page colours contradict the definitions:**
  - TCPI is coloured green at ≥ 1.1. That is inverted: TCPI > 1 is bad.
  - CPI/SPI cells have no yellow band.
  - "Bajo presupuesto ✓" appears at CPI ≥ 0.9, which is over budget.
- **CPI/SPI are computed differently on other screens** (Portfolio, the ML features, Profitability), so the same project can show different values.

### Project Portfolio — `/portfolio`
*Roles:* admin, pm (route). Backend: list and dashboard use `get_current_user`; writes use `require_admin_or_pm` (delete operations also ABAC).

**Purpose.** Group projects into portfolios and view an aggregated RAG/budget dashboard.

**How to use it.**
1. Use the header button to create a portfolio. Fill in Nombre*, Descripción, Estado (planning/active/archived), Presupuesto total (€), Fecha inicio and Fecha fin, then **Crear cartera**.
2. Cards offer **Editar**, **Eliminar** and **Ver dashboard**.
3. The dashboard shows:
   - KPIs: Presupuesto total / Gastado, % Gastado, En riesgo, En control.
   - A table: RAG, Proyecto, % Hecho, CPI, SPI, Presupuesto, Gasto real, Próximo hito.
   - Click a row to see the next 5 milestones.
   - **Añadir proyecto** adds a project (search box); **X** removes one.
   - The dashboard refreshes every 60 s.

**Configuration.** None.

**Technical notes.**
- Endpoints (`app/api/v1/endpoints/portfolio.py`, `app/services/portfolio_service.py`):
  - `GET/POST /api/v1/portfolios`
  - `PATCH/DELETE /api/v1/portfolios/{id}` (delete is soft and returns 400 while active projects remain)
  - `POST /api/v1/portfolios/{id}/projects`
  - `DELETE /api/v1/portfolios/{id}/projects/{pid}`
  - `GET /api/v1/portfolios/{id}/dashboard`
- Tables: `portfolios`, `portfolio_projects`, `projects`, `tasks`, `imputations`, `project_milestones`.
- RAG = `portfolio_projects.rag_override`, otherwise the `get_evm_quick` health (same 0.9/0.85 rule).
- Budget % = ΣAC ÷ (portfolio budget, or ΣBAC).

**Limitations (measured).**
- **There is no scoring or prioritisation.** Rows are sorted by RAG only; `display_order` and `rag_override` have no UI.
- **Projects without `budget_amount` show grey.** `get_evm_quick` has no BAC or AC fallbacks, so these projects get BAC 0 and grey.
- **Creating a portfolio with empty dates likely fails silently.** The form sends `''` for empty dates, and pydantic rejects `''` for `Optional[date]` (checked with a snippet), so this should return 422. The mutations have no error handler. Not verified end to end.
- `portfolios.budget_spent` is never written.

### Burnup & Velocity — `/sprint-charts`
*Roles:* admin, pm (route). Backend: `get_current_user` only.

**Purpose.** Sprint burnup and team velocity in story points.

**How to use it.**
1. Select **PROYECTO**. The velocity chart appears: bars Planificados/Completados, a Velocidad line, an Avg reference line and "Velocidad media".
2. Select a sprint. The burnup chart appears: Scope (total), Completado, Objetivo, and KPIs (Completado, Scope total, Progreso %).

**Configuration.** None.

**Technical notes.**
- `GET /api/v1/sprints/{project_id}/sprints`
- `GET /api/v1/sprints/{project_id}/sprints/{sprint_id}/burnup`
- `GET /api/v1/sprints/{project_id}/velocity` (`app/services/sprint_service.py`)
- Tables: `sprints`, `sprint_tasks`, `tasks.story_points`.
- **Burnup:** one point per day. "Completed" = story points of `done` tasks with `completed_at` ≤ that day.
- **Velocity:** completed sprints only. Velocity = completed_points ÷ max(duration_days ÷ 7, 0.5), stored when the sprint is closed, so it is **points per week**.

**Limitations (measured).**
- **Scope is constant.** The code has no scope history, so scope creep is not shown.
- **Removed tasks still count in the burnup.** It does not filter `sprint_tasks.is_active`; the burndown does.
- **The velocity chart mixes units.** It plots points/week on the same axis as the points bars and labels the average "pts".

### Cumulative Flow — `/cumulative-flow`
*Roles:* the route has **no role restriction**; the menu shows it to admin and pm. Backend: GET uses `get_current_user`; snapshot uses `require_admin_or_pm`.

**Purpose.** A cumulative flow diagram of task counts by status over time.

**How to use it.**
1. Select a project and a period (7/14/30/60/90 days).
2. Press **📸 snapshot today** to record today's counts. With no history, a "create first snapshot" button appears instead.
3. Read the stacked area chart, the KPIs and the table of the last 14 rows.

**Configuration.** None.

**Technical notes.**
- `GET /api/v1/epics/cfd?project_id=&days=`
- `POST /api/v1/epics/cfd/snapshot?project_id=` (`epics_service.get_cfd_data` / `take_cfd_snapshot`)
- Table `task_state_snapshots`. A snapshot replaces today's rows with `COUNT(tasks) GROUP BY status`.

**Limitations (measured).**
- **No job takes snapshots.** The chart only contains the days on which someone pressed the button, and there is no status history to backfill from.
- **The "completed today" KPI is a cumulative count.** It is actually the total done count.
- Employees who reach the page by URL can view it but get 403 on the snapshot button.

### Project Risk — `/risk-scores`
*Roles:* admin, pm (route). Backend: `require_any_manager`; prediction logs use any user.

**Purpose.** Two risk views: a rule-based signal score, and a per-organization scikit-learn model.

**How to use it.**
- Tab **🛡️ Riesgo basado en señales:**
  - Click a level card (Crítico/Alto/Medio/Bajo) to filter; **× Quitar filtro** clears it.
  - **↻ Recalcular todo** recomputes all scores.
  - Each project shows an overall score /100 and Cronograma/Presupuesto/Alcance/Recursos bars.
  - Click a project for a radar chart, the recommendation and the delay estimate.
- Tab **🤖 Predicciones ML:** KPIs, at-risk projects, **Entrenar ahora**, Versiones del modelo and Historial de predicciones.

**Configuration.** Admin → Settings → **Riesgo del proyecto** (group `risk`, since 2026-11-04): the four weights, the level thresholds, the schedule, budget, scope and resource factors, the delay probability, the cache minutes (`RISK_CACHE_MINUTES`, 60) and the history points (`RISK_HISTORY_POINTS`, 12). `AI_REVENUE_HOURLY_RATE_FALLBACK` (85) is the last-resort hourly cost.

**Technical notes.**
- **Signal score** (`app/api/v1/endpoints/cab.py`, `cab_service.compute_risk_score`). This is **a weighted heuristic, not ML or LLM**.
  - Endpoints: `GET /api/v1/risk-scores[?refresh=true]`, `GET /api/v1/risk-scores/{project_id}`.

  | Component | Calculation | Weight |
  |---|---|---|
  | schedule | min((time % − completion %) × 1.5, 100) | 0.40 |
  | budget | real internal cost (each time entry's `cost_amount`, else hours × the person's cost profile, else `AI_REVENUE_HOURLY_RATE_FALLBACK`); above 85 % → (pct − 85) × 3; above 100 % → (pct − 100) × 2. Until 2026-11-04 it was hours × a hardcoded 80 €/h. | 0.30 |
  | scope | open change requests × 20 | 0.15 |
  | resource | open high-probability risks × 25 | 0.15 |

  - Levels: critical ≥ 75, high ≥ 50, medium ≥ 25.
  - "Delay probability" = min(score × 0.8, 95).
  - Results are cached in `project_risk_scores` for 60 min.
- **ML tab** (`app/api/v1/endpoints/predictions.py`, `app/services/ml_trainer.py`, `ml_features.py`):
  - Endpoints:
    - `GET /api/v1/predictions/portfolio-risk`
    - `POST /api/v1/predictions/train`
    - `GET /api/v1/predictions/models`
    - `GET /api/v1/predictions/logs`
  - Model: `StandardScaler` + `GradientBoostingClassifier(n_estimators=100, max_depth=3)`, needing at least 5 completed projects, with cross-validated ROC-AUC. It is pickled with an HMAC into `ml_models`.
  - Features: cpi, spi, budget_used_pct, elapsed_pct, task_completion_pct, overdue_ratio, team_size, budget_log, duration_days.
  - Label: cost > 1.10 × budget, or a late finish.
  - Without a model, a 13-rule table is used (`ai_modules/predictions.py`).
  - Predictions are logged to `ml_prediction_logs`.
  - Worker `ml-model-retrain` runs on day 1 of each month at 03:00.

**Limitations (measured).**
- **Thresholds and weights are settings** (see Configuration). The detail shows the score history (one point per change). `overloaded_members` is measured since 2026-11-04: people who logged time on the project in the last 4 weeks and whose total hours (all projects) exceed their capacity.
- **The detail writes a row only when the score changes** or the last one is older than the cache (it used to insert one per click). The table is never pruned.
- **Training label and cost feature in euros** (fixed 2026-11-04). Both used to fall back to summing **hours** against a budget in euros when `cost_amount` was empty; they now use the same internal cost as NexusOracle and profitability.
- **Team load is measured** (fixed 2026-11-04; it was a fixed 85, so "team overloaded" could never fire). It is the total hours of the people who logged time on the project in the last 4 weeks against their weekly capacity. With nobody logging time, no load rule applies.
- **Projects without data are not "low risk"** (fixed 2026-11-04). A project with no tasks, or a prediction error, is reported in `without_data` and shown under the KPIs.
- **The ML prediction history records changes only** (since 2026-11-04; each portfolio view used to write one row per project).

### Data Export — `/exports`
*Roles:* admin, pm, hr (route). Backend: imputations use `get_current_user`; projects use `require_any_manager`.

**Purpose.** Download imputations and projects as XLSX or CSV, plus a Jira sync shortcut.

**How to use it.**
- **Imputaciones:** set Desde/Hasta, choose XLSX|CSV, then press **Descargar**.
- **Proyectos:** choose XLSX|CSV, optionally tick "include costs" (admin), then download.
- **Jira:** pick a project, then press **Sincronizar**.

**Configuration.** None.

**Technical notes.**
- `GET /api/v1/analytics/exports/imputations-csv?date_from&date_to&formato`
- `GET /api/v1/analytics/exports/projects-csv?include_costs&formato` (`app/api/v1/endpoints/analytics_extended.py`)
- Files are written by `app/services/exportador_tabular`: CSV in utf-8-sig, XLSX with openpyxl (bold frozen header, typed cells).
- `/analytics/exports/resources-csv` exists, but no page calls it.

**Limitations (measured).**
- **Everyone exports only their own hours.** The frontend never sends `user_id`, so admin, PM and HR all get only their own imputations.
- **Imputation cost columns are always included.** The "include costs" checkbox has no effect on imputations.
- **The admin-only restriction on project costs is frontend-only.** Any manager can request them from the API.
- **Jira sync always returns 404.** It sends a project id where the backend expects a Jira config id, so the result is "Jira config not found".

### Data Platform — `/data-platform`
*Roles:* admin (route). Backend: most GETs use any authenticated user; writes use internal user or admin.

**Purpose.** Manage ETL connectors, Microsoft 365 usage reports, report presets, realtime streaming, the embed SDK and custom connectors.

**How to use it.**
- **Conectores ETL:** press **Refrescar** to reload, **Sincronizar** per connector, and toggle the log. The list polls every 30 s.
- **Microsoft 365:**
  - Tabs Reportes / Adopción / Configuración.
  - Enter Tenant ID, Client ID and Client secret, then press **Guardar**.
  - Press **Sincronizar** to pull reports.
- **Conectores de datos activos:** activate, deactivate or sync each connector.
- Also on the page: a report presets preview, a realtime stream, and Plataforma BI (Embed SDK, connector catalogue, custom connectors, lineage and versions).

**Configuration.**
- Connector credentials have **no UI**.
- M365 needs an Azure app with Graph report permissions. Not verified which permissions.
- The page uses `REDIS_URL` and `ENVIRONMENT`.
- Storage is `app_settings` JSON only.

**Technical notes.**
- ETL:
  - `GET /api/v1/bi/etl/connectors`, `GET .../{id}/log`, `POST .../{id}/sync`.
  - 20 connectors are listed; the clients are in `app/integrations/bi_etl_connectors.py` (real httpx/SDK calls).
  - Worker `sync_connector_data` has 21 hourly beat entries.
- `/api/v1/bi/o365/*` → `bi_o365_service` makes real Microsoft Graph calls (client credentials, getXUserDetail reports).
- `/api/v1/bi/intelligence/connectors/{c}/sync`

**Limitations (measured). Much of this page does not work.**
- **ETL:**
  - Only 5 of the 20 connectors can be enabled. Their SDKs did not import in the local venv.
  - Manual "Sincronizar" sends a Celery task to queue `etl_{id}`, which no worker in the repo consumes.
  - The hourly job passes entity `"default"`, so HubSpot, Stripe and Xero return nothing and still report OK.
  - The log is always empty: it returns `{entries}` and the UI expects a list.
- **"Sync" under Conectores de datos activos is fake.** It generates a random record count (`random.randint(25, 450)`) and marks the connector "connected" without connecting.
- **M365:**
  - Graph errors are swallowed and the sync is recorded as OK with 0 records.
  - The "enabled" flag and the secret are not saved.
  - The Adopción tab shows "[object Object]".
- **Three lists are always empty** (presets, custom connectors, snapshots) because of the `.items` unwrapping issue. Custom connector "Test" only checks that the URL starts with http(s).
- **Streaming:**
  - In production and staging the socket is closed with code 4003 (token in the URL), and the client reconnects every 2 s indefinitely.
  - With Redis, the frame type sent (`bi_kpi_snapshot`) differs from the one the UI accepts (`bi_intelligence_snapshot`).
- ~~Embed and realtime tokens are ordinary full-access JWTs.~~ Fixed 2026-11-03 (test `tests/test_api_con_los_roles_de_sus_pantallas.py`): `get_current_user` rejects tokens carrying `bi_embed`, `bi_intelligence_stream`, `ws` or `document_file_access`; each is accepted only by its own receiver (the realtime stream and the WebSocket check their claim; nothing consumes `bi_embed` yet, so that token currently opens nothing). `POST /bi/embed/token` was already separate (type `embed`, its own secret). The `window.ContecflowBIEmbed` SDK is not implemented, and `allowed_origins` defaults to `["*"]`.
- ~~M365 activity and raw ETL data are open to every role.~~ Fixed 2026-11-03 (test `tests/test_api_con_los_roles_de_sus_pantallas.py`): `/bi/o365/*` and `/bi/etl/*` reads are admin-only, like `/data-platform`.

### Data Governance — `/data-governance`
*Roles:* admin (route). Backend: GDPR and governance writes and (since 2026-11-03) reads use `require_admin`.

**Purpose.** GDPR requests, consent records, field masks, data policies, access audit, lineage, field classification, dashboard collaboration and governance checks.

**How to use it.**
- **GDPR panel:** tabs DSR / Consentimiento / Máscaras / Estadísticas.
- **Governance panel:** tabs Políticas / Auditoría / Overview.
- **Auditoría y linaje:** Auditoría de accesos, Linaje de datos, Clasificación de campos.
- **Compartir y colaborar**, Bookmarks.
- **Resumen de gobernanza:** press **Ejecutar checks**.
- **Collaboration panel:** Comentarios / Vistas compartidas / Accesos / Versiones / Notificaciones.

**Configuration.** None. These values are hardcoded: a 30-day DSR deadline, 3,000 audit events per day, and a 90-day audit window.

**Technical notes.**
- Services: `bi_gdpr_service`, `bi_collaboration_service`.
- Storage:
  - `app_settings` JSON (GDPR, sensitivity, lineage, audit, rules, views, bookmarks)
  - tables `dashboard_comments`, `dashboard_versions`, `dashboard_shares`, `dashboard_notifications`
- **Erasure** (`execute_erasure`) anonymises `users` PII fields and the requester fields on `sd_tickets`. The portability export is real: profile, tickets and consent.
- **Governance checks are plain rules:**
  - DuckDB file missing
  - DuckDB file older than 26 h
  - scheduled-report errors
  - no active schedules

**Limitations (measured).**
- **Lists (fixed 2026-11-04).** Some routes return the list already unwrapped by the interceptor and others return `{items}` inside `data`; the screen now reads both with `unwrapList`. Checked in the browser on a database copy: the DSR, consent, mask and shared-view lists show their rows (with the previous code, the shared view, the consent and the mask were missing). The 5 collaboration tabs use the same reader; they were not checked with data.
- **Some forms always fail with 422, silently:** "Registrar acceso", lineage "Añadir", "Clasificar" (field and enum mismatch), and mask type "partial".
- **The policy editor saves nothing.** The backend accepts only 3 fields, yet the UI says "Política creada". "Anomalías detectadas" and "Checks ejecutados" are always 0.
- **Erasure is narrow.** It does not touch other tables, consent history or DuckDB `dim_user`. Resolving the DSR afterwards re-records the subject id.
- **Masks and classifications are stored but never enforced.** Consent is keyed by user only, so a new purpose overwrites the previous one.
- ~~Personal data is readable by any role.~~ Fixed 2026-11-03 (test `tests/test_api_con_los_roles_de_sus_pantallas.py`): DSRs, consents, masks, stats, the access audit, lineage, sensitivity and governance reads are admin-only.

### NexusAgent — `/nexus-agent`
*Roles:* admin, pm (route). Backend: `require_any_manager`.

**Purpose.** An LLM agent that answers instructions by calling application tools: it reads and **writes** data.

**How to use it.**
1. Type an instruction, or pick one from **Ejemplos**.
2. Keep or change **Streaming en vivo** (on by default).
3. Press **▶ Ejecutar agente** (or Cmd/Ctrl+Enter).

The **Herramientas** sidebar shows 15 of the 37 tools; **Ver todas** lists the rest. History lists past non-streamed runs.

**Configuration.** You need a tool-capable provider (Anthropic, the OpenAI family or Gemini) in AI Hub or `.env`. Ollama runs only in text-only degraded mode.

**Technical notes.**
- **Streaming:** `POST /api/v1/ai/agent/stream` (SSE) → `ai_chat.run_agent_stream` → `ai_tools.pedir_turno` + `tool_execution/executor.execute_tool`.
- **Non-streaming:**
  - `POST /api/v1/ai/agent` creates an `ai_agent_executions` row.
  - The worker task `run_agent_task` then runs `agent_loop.run_tool_use_loop` and stores `ai_agent_steps`.
- Also called: `GET /api/v1/ai/agent/history`, `GET /api/v1/ai-providers`.
- Tool schemas: 37 in `app/services/ai_chat/tool_execution/schema.py`, all with handlers. At most 20 steps.
- **Write tools:** create_task, update_task, create_risk, update_project_status, update_ticket_status, reassign_tickets, send_notification.

**Limitations (measured).**
- **There is no human confirmation for writes.** The backend defaults `auto_approve=False`, but both frontend paths hardcode `auto_approve: true` (`NexusAgentPage.tsx:167`, `_core.ts:1911`). No approve endpoint exists.
- **With streaming on (the default), writes are probably not saved.** The tool handlers only `flush()`; the SSE generator opens its own `SessionLocal()` and only `close()`s it, with no commit. So created tasks and risks are probably rolled back, even though the agent reports success. This was verified by code reading only; no test covers `/ai/agent/stream`. The worker path does commit.
- **The worker path does not scope to the organization.** It selects the provider with the default `is_superadmin=True`, and its session publishes no tenant context, so tools can read and write across organizations.
- **The agent loop is not logged or governed.** It bypasses `call_ai`, so there are no `ai_usage_logs`, no cost accounting and no guardrails; the only input check is a keyword blocklist.
- **Streamed runs never reach History.** History items show only a status, and the non-streamed status is never polled.

### External agents (MCP) — `POST /api/v1/mcp`
*Roles:* any internal user, with their own permissions. The company switches it on in *AI Governance → Modules → Agentes externos (MCP)*.

**Purpose.** Claude, a company copilot or another product use Contecflow's data as tools, through the Model Context Protocol (revision 2026-11, what contecintelligence already had). The tools are NexusAgent's 37 (`AGENT_TOOLS`); nothing is duplicated.

**How to connect.**
1. *AI Governance → Modules*: switch on *Agentes externos (MCP)*. Unlike the other modules, it is **off** until someone switches it on, because it opens a door to the outside.
2. Create an API key (*Reservas → API keys*, `POST /bookings/api-keys`) with scope `read`, or `write` if the agent must write.
3. In the agent: server URL `https://<host>/api/v1/mcp`, header `Authorization: Bearer nxpm_…` (or `X-API-Key`). Transport: Streamable HTTP, one JSON-RPC message per POST.

**Governance.**
- The key acts **as its owner**: role, organisation, financial tools only for admin/hr, as in NexusAgent.
- **Tools that write** (create/update task, create risk, project and ticket status, reassign tickets, send notification) follow `MCP_WRITE_MODE` (*Admin → AI*). A `read` key never sees them; `write` or `admin` is needed. An area-scoped key (`projects`, `tasks`…) cannot open MCP. Any unknown value counts as `off`.
  - `off` (default): they are not listed.
  - `approval`: they are listed with «REQUIERE APROBACIÓN HUMANA». A call does not run. It stores the action (`mcp_pending_actions`, migration 134) and opens an approval of type **«Acción de agente externo (MCP)»** (`mcp_action`). It returns `pending_approval` with an `action_id`.
    - When someone approves, the approval engine runs the tool as the key's owner (`_apply_entity_final_decision` → `mcp_service.aplicar_decision`), stores the result and logs it. When someone rejects, nothing runs.
    - The agent follows it with the extra tool `mcp_action_status`, and only sees its own actions.
    - The approver cannot be the requester (segregation of duties), and the email approval link works as for any other approval.
    - Without a workflow for that type, the call fails with a clear message and nothing is stored. Create the workflow in *Settings → Approval workflows*.
  - `direct`: they run at once.
  - Measured end to end on a copy with PostgreSQL, RLS and the application role: a PM's agent asked for a task (0 tasks), the admin approved it (1 task), and the status went to `executed` with the result.
- The daily limit is the module's `max_actions_per_day` in AI Governance.
- Every call is logged in the AI action log (module `mcp`), allowed, failed or blocked.
- A new NexusAgent tool that is neither `get_`/`search_` nor listed as a write tool breaks the import of `app/services/mcp_service.py` on purpose, so a write is never exposed as a read.

**Protocol.** `initialize` (versions 2025-06-18 and 2025-03-26), `ping`, `tools/list`, `tools/call`; `resources/list` and `prompts/list` return empty lists. Notifications get 202, batches 400, `GET /mcp` 405. A tool failure comes back as a result with `isError: true` so the model can correct itself. Measured on a copy with a `read` key: 30 tools listed, `search_projects` answered, the call logged.

### NexusAssist (in-app AI assistant) — floating panel (Cmd+I) and inline editor
*Roles:* any authenticated user (`POST /ai/chat` uses `get_current_user`).

**Purpose.** A chat assistant with the tenant's data as context, plus "improve this text" buttons in task and ticket fields (`AIInlineEditor`, used in TasksPage, CreateTicketModal and TicketDetail).

**How to use it.** Open the panel with Cmd+I, or with the assistant button in the layout. Type a question; earlier conversations can be reopened or deleted.

**Configuration.** You need a provider (AI Hub or `.env`). Admins can switch the module on or off or limit it in AI Governance (`nexusassist` toggle, enforced by `check_rate_limit`).

**Technical notes.**
- Endpoints: `POST /api/v1/ai/chat`, `GET/DELETE /api/v1/ai/conversations`, `GET /api/v1/ai/conversations/{id}`.
- **Flow:**
  1. Keyword injection blocklist.
  2. Rate limit.
  3. The message is stored in `ai_messages`.
  4. Context is built: the full tenant context (`context_service.build_tenant_context`), knowledge-base retrieval, and the last 10 messages.
  5. `call_ai(module="nexusassist", max_tokens=4000)`.
  6. An action log row is written.

**Limitations (measured).**
- **Without a provider the warning becomes a reply.** It is stored as the assistant's answer. In the inline editor, the warning or error text **replaces or is appended to the user's field**, and every inline call creates a new conversation.
- **The current record is not given to the model.** The panel sends `context_type`/`context_id`, but they are only stored, not used to build the context.
- **The original text is stored even when a policy redacts it.** The message is persisted before redaction.
- **Knowledge-base retrieval is keyword-only under TF-IDF.** With the default TF-IDF backend no KB vector is stored, so retrieval works by words (accent-insensitive, by stem). Since 2026-11 it searches the Service Desk base (before: `ai_kb_articles`, empty), cites the articles it uses and applies expert corrections. See *Knowledge base → Quality loop*.
- **Token counts are not recorded.** `tokens_used` is stored as 0 on messages; real token counts are only in `ai_usage_logs`.

### NexusOracle — `/oracle`
*Roles:* admin, pm (route). Backend: list uses any user; run uses `require_any_manager`.

**Purpose.** Risk warnings for project delay, SLA breach, burnout and budget overrun. **This is rules only: no LLM and no ML.** The backend itself returns `"methodology": "rules_based"`.

**How to use it.**
1. Press **🔮 Ejecutar análisis**.
2. Review the KPIs and the pie and bar charts, and filter by severity.
3. Mark items with **✓ Reconocer**.

**Configuration.** SLA hours come from runtime settings. All other thresholds are hardcoded. The header shows the default AI provider's name even though it is not used.

**Technical notes.**
- Endpoints:
  - `GET /api/v1/oracle/predictions?only_unacked=false`
  - `POST /api/v1/oracle/run` → `ai_modules/oracle.run_oracle_analysis`
  - `POST /api/v1/oracle/predictions/{id}/acknowledge`
- Table `ai_predictions`. There is no worker job.
- **Rules:**
  - project_delay: overdue ratio, up to 40 points; + 35 if < 30 % done within 14 days of the end; + 25 if budget consumption is > 90 %. Shown at ≥ 0.25.
  - sla_breach: ticket age against SLA hours.
  - burnout: 4 weeks of logged hours (> 42 h, and so on).
  - budget_overrun: cost ratio ≥ 0.85.

**Limitations (measured).**
- **The "probability" is a capped score,** not a calibrated probability. `POST /overrun-prediction` (`predict_overrun_ml`) is also a heuristic, despite its name.
- **Acknowledging does not stick on screen.** The list does not return `is_acknowledged` or `entity_name`, so "Reconocidas" is always 0 and acknowledged items still show **Reconocer**.
- Existing budget_overrun predictions are never updated.

### AI Assignment (Semantic Engine) — `/semantic-engine`
*Roles:* admin, pm (route). Backend: config, profile writes and rebuilds use `admin_or_hr`; suggestions use internal user; stats and profile reads use any user.

**Purpose.** Suggest the best assignee for tasks and tickets by comparing the item text with people's profiles and assignment history. It is also used for auto-assignment when tasks and tickets are created (`task_service`, `ticket_creation_service`).

**How to use it.**
- **⚙️ Configuración:**
  1. Pick a mode: Híbrido / Solo semántico / Solo LLM / Solo reglas.
  2. Choose the embeddings backend and the Hugging Face model, then press **Guardar**.
  3. Set the thresholds and the auto-assign toggles.
- **👥 Perfiles:** edit people's profiles.
- **🧪 Probar:** test a suggestion.
- **📊 Estadísticas:** view acceptance statistics.
- Header buttons: **🔄 Reconstruir embeddings** and **✨ Auto-generar perfiles**.

**Configuration.**
- Table `sem_config` (per organization).
- Runtime group `semantic` / `ai`: `SEMANTIC_EMBEDDINGS_BACKEND`, `SEM_THRESHOLD_*`, `SEM_TOP_K_HISTORY`, `SEM_MULTI_ROLE_FACTOR`.
- A provider is needed only for the LLM tie-break.

**Technical notes.**
- Endpoints (`app/api/v1/endpoints/semantic_engine.py` → `semantic_engine_service.py` → `semantic_classifier.SemanticAssigner`):
  - `GET/PATCH /api/v1/semantic/config`
  - `GET/POST /api/v1/semantic/profiles`
  - `POST .../profiles/auto-generate`
  - `POST .../profiles/rebuild-embeddings`
  - `GET /api/v1/semantic/stats`
  - `POST /api/v1/semantic/suggest/task|ticket`
  - `POST /api/v1/semantic/estimate/effort`
  - `POST /api/v1/semantic/record-assignment`
- Tables: `sem_config`, `sem_profiles`, `sem_embedding_cache`, `sem_assignments`, `sem_feedback`. Embeddings are stored as JSON text, and cosine similarity is computed in Python.
- **Scoring:**
  1. Expert cache: an exact hash match, or cosine ≥ 0.92.
  2. Per person: 0.4 × cosine(profile) + 0.6 × time-decayed mean of history cosines (half-life 90 days).
  3. Blend with workload: score × 0.8 + (1 − load) × 0.2, minus a diversity penalty.
  4. In hybrid mode, an LLM tie-break is used below the threshold.
- Skills only enter as text inside the profile; there is no weighted skill matching.
- Effort estimation is a keyword and word-count heuristic.

**Limitations (measured).**
- **PMs get 403 on every write button.** The route allows PMs, but writes need admin or hr.
- **"Precisión" is meaningless.** Rejections are never recorded (only `was_accepted: true`), so it is 100 % or "—".
- **The real embeddings backend may differ from what the UI shows.** The default model name `all-MiniLM-L6-v2` selects the "transformer" backend, which overrides `SEMANTIC_EMBEDDINGS_BACKEND=tfidf`. In the Docker image sentence-transformers is not installed, so the engine silently uses TF-IDF while the UI reports the transformer model.
- **Similarity scores may collapse to zero under TF-IDF.** The vocabulary is refitted per request, so stored and new vectors can differ in length, and cosine returns 0 when lengths differ. Ranking would then depend on workload only. Likely from the code; not runtime-verified.
- **The LLM tie-break is unscoped and its answer is stored as expert knowledge:**
  - It runs without the user, so it uses cross-tenant provider selection and skips guardrails.
  - The returned user id is not checked against the candidates.
  - The answer is stored as feedback with confidence 0.75 and later reused from the cache as "expert" with confidence 1.0.
- **Some settings have no effect.** `SEM_TOP_K_HISTORY` and `SEM_MULTI_ROLE_FACTOR` are read but unused. The runtime `SEM_THRESHOLD_*` values are shadowed by the `sem_config` column defaults.

### Automations — `/automations`
*Roles:* admin, pm (route). Backend: `require_any_manager`; `/run-scheduled` uses `require_admin` and only scans the caller's organization (all of them for a superadmin).

**Purpose.** IF-trigger-THEN-actions rules that run on their own inside one organization. **No AI is involved.**

**How to use it.**
1. Press **+ Nueva regla**.
2. Fill in name, description and project (empty = all projects of the organization).
3. Pick a trigger. The list comes from the engine (`GET /automations/catalog`): only triggers that something actually emits are offered.
4. Optionally tick "Añadir condición" and add one or more field/operator/value rows. With two or more, choose **Se cumplen todas** (AND) or **Basta con una** (OR). The fields offered are the ones the trigger's event carries. Operators: equals, not_equals, greater_than, less_than, contains. A condition that cannot be evaluated (missing field, non-numeric value for a numeric operator, an empty group) is **false**.
   - Stored as one condition `{field, operator, value}` or a group `{"match": "all"|"any", "conditions": [...]}`. Groups can be nested through the API (the screen edits one level and keeps nested groups untouched). Revision 2026-11; before, a rule had at most one condition.
   - With the **Programada (calendario)** trigger, a **Cuándo (cron)** field appears: five fields (minute hour day month weekday) in the organisation's time zone, with presets (every day 9:00, weekdays 9:00, Mondays 8:00, 1st of the month, every hour). The card shows the next run.
5. Add one or more actions. Required parameters are marked `*`; saving a rule with an unknown trigger, an unknown action or a missing required parameter returns 422 with the reason.
6. Press **Crear regla**.

On each rule card:
- **Pausar / Activar** toggles the rule. A paused rule stays in the list and can be reactivated.
- **Probar** is a **simulation**: it says what each action would do (for example "would notify 3 user(s) with role pm", or "no webhook configured") and executes nothing. It warns when automations are off for the organization and when the trigger comes from the periodic scan.
- **Historial** lists the real executions with the result of every action.
- 🗑 deletes the rule and its history.

**Ver plantillas** offers 7 templates, all made of triggers and actions the engine runs.

**Triggers (36).**

| Category | Triggers | Source |
|---|---|---|
| Tasks | task_created, task_status_changed, task_assigned, task_completed, task_blocked | on save |
| Tasks | task_overdue, task_deadline_approaching | periodic scan |
| Projects | project_created, project_status_changed, risk_score_high (new risk or score change) | on save |
| Projects | budget_threshold (`budget_pct` = imputed cost / budget amount, active projects) | periodic scan |
| Sprints | sprint_started (status → active), sprint_ended (status → completed) | on save |
| Time & team | timesheet_submitted, timesheet_rejected, absence_requested, absence_approved, absence_rejected | on save |
| Time & team | timesheet_not_submitted (from `AUTOMATIONS_TIMESHEET_WEEKDAY`, current week still draft or missing) | periodic scan |
| Service Desk | ticket_created, ticket_resolved, ticket_reopened | on save |
| Service Desk | ticket_escalated, ticket_sla_at_risk, ticket_sla_breached (from the ticket event outbox) | on save |
| Finance & CRM | expense_submitted, expense_approved, expense_rejected, opportunity_stage_changed | on save |
| Finance | invoice_sent, invoice_paid (status change) | on save |
| Finance | invoice_overdue (status sent/overdue and due date passed; nothing else marks invoices overdue) | periodic scan |
| Approvals | approval_requested, approval_approved, approval_rejected (from the screen, the email link or a rule) | on save |
| Schedule | scheduled: runs on its cron, without any change. Context: `project_id` (the rule's), `weekday`, `hour` | periodic scan |

"On save" means the event is recorded in the same transaction as the change, whatever path made it (screen, API, Jira sync, AI, another rule). Scan triggers act **once per rule and item** (`dedupe_key`): an overdue task notifies once per due date, a project crosses the budget condition once.

**Actions (16).**

| Action | What it does |
|---|---|
| create_alert | Alert of type `automation` in the organization (message, severity) |
| notify_user | In-app notification to the event's user (task assignee, ticket assignee, requester of the expense/absence/timesheet, opportunity owner). Fails if the event carries no user |
| notify_role | In-app notification to active users of that role **in the rule's organization** |
| send_email | To `to` (comma-separated) and/or users of `to_role` in the organization; marked failed when SMTP does not send |
| call_webhook | HTTPS only, SSRF check; body = `payload` (JSON) or the event context. Use it for RPA (Power Automate, Zapier, Make, n8n, UiPath) |
| send_slack_message / send_teams_message | URL typed in the rule, else the active Slack/Teams integration **of the organization** |
| change_task_status / change_task_priority | On the event's task |
| create_task | In the event's project, assigned to the event's user, optional due in N days |
| change_project_status | On the event's project |
| escalate_ticket | Raises the support level (never lowers it) and records an `escalated` ticket event |
| change_ticket_status | On the event's ticket |
| assign | The event's ticket or task to a person (`to_user`, email in the organisation) or to the member of `to_role` with the fewest open items |
| update_field | One of an allow-list of fields without their own action: task due/start date, estimated hours, story points; ticket priority, support level. Dates accept `+N` / `-N` days from today |
| create_approval | Opens an approval on the event's record (expense, invoice, timesheet, leave, ticket, task, opportunity or project; `entity_type` overrides it). The workflow is chosen by its conditions as when a person asks. Requester: the event's user, else the rule's author. Skips if one is already pending |

An action that fails is recorded and the next ones still run. A rule's action can trigger another rule; the chain stops at `AUTOMATIONS_MAX_CHAIN_DEPTH`.

**Configuration** (Settings → Advanced → Automatizaciones, per organization):
- `AUTOMATIONS_ENABLED` (default true). Off: rules do not run; Probar still simulates.
- `AUTOMATIONS_MAX_CHAIN_DEPTH` (3), `AUTOMATIONS_EVENT_BATCH_SIZE` (200), `AUTOMATIONS_EVENT_MAX_ATTEMPTS` (3).
- `AUTOMATIONS_DEADLINE_DAYS` (2), `AUTOMATIONS_TIMESHEET_WEEKDAY` (5 = Friday), `AUTOMATIONS_WEBHOOK_TIMEOUT_SECONDS` (10).
- `AUTOMATIONS_SCAN_MINUTES` (15, environment only: read when the beat/scheduler starts). It is also the precision of scheduled rules: a rule due at 8:00 runs in the first sweep after 8:00. If several instants were missed (worker down), it runs once and jumps to the next future one (`automation_rules.schedule_cron/next_run_at`, migration 132).
- `send_email` uses `SMTP_*`; Slack/Teams use incoming webhooks in Enterprise → Integraciones.

**Technical notes.**
- Endpoints (`app/api/v1/endpoints/automations.py`, `app/services/automations_service.py`): `GET/POST /api/v1/automations`, `PATCH/DELETE /api/v1/automations/{id}`, `POST /api/v1/automations/{id}/test` (simulation), `GET /api/v1/automations/catalog`, `GET /api/v1/automations/templates/list`, `GET /api/v1/automations/{id}/executions`, `POST /api/v1/automations/run-scheduled`. Every by-id call returns 404 for a rule of another organization.
- Event capture: `app/services/automation_events.py`, a `before_flush` listener on the session (same pattern as the ticket outbox). It writes `automation_events` only when the organization has an active rule for that trigger.
  - On a new record the listener assigns the primary key before reading the event (revision 2026-11). Before, `id` was still `None` in `before_flush`, so a `task_created` event had no `task_id` and every action on "the event's task" failed with "El evento no trae tarea".
- Processing: Celery `automations_procesar_eventos` (queued on commit; beat every minute as a safety net) and `automations_escanear` (every `AUTOMATIONS_SCAN_MINUTES`). The same two jobs exist in APScheduler (`app/services/automation_jobs.py`).
- Tables: `automation_rules` (`trigger_type` is VARCHAR(64) since migration 118; it was a 14-value Postgres enum), `automation_executions` (+ `dedupe_key`), `automation_events`.
- Migration 118 also fills `organization_id` of existing rules from their project or creator, and adds `automation` to the `alerttype` enum.

**Limitations (measured).**
- Actions run after the change is committed, in the worker: a rule never blocks or undoes the change that triggered it, and its effect appears within about a minute (immediately when the broker is up).
- Webhook, e-mail, Slack and Teams calls cannot be rolled back if a later action fails.
- The "Flujos de trabajo" tab was removed: it listed rules under another name, and creating or editing there always failed. The `automation_workflows` API (Enterprise) is unchanged and still has no scheduled runner.
- Rules created before migration 118 with actions that were never implemented (`rpa_*`, `assign_task`, `assign_ticket`, `approve_expense`, `create_jira_issue`) keep their record and fail at run time with "tipo desconocido"; editing them asks for a valid action.

### BPM Procesos — `/bpm`
*Roles:* admin, pm, team_lead (route). Backend: reads use any user; all writes use `require_admin_or_pm`, so a team_lead sees "Editar" and "Nuevo proceso" but gets 403 on save.

**Purpose.** A BPMN 2.0 process catalogue and diagram editor, and (since 2026-11-04) an engine that runs the saved diagrams.

**Coverage (measured 2026-11-05).** The catalogue has **61** processes. To check that every business process is there, two lists were crossed with the catalogue:
- the 97 menu options;
- the 94 tables with a `status` column, which are the state machines the backend really runs.

21 processes were missing and were added, with their steps taken from the real statuses:

| Area | Added |
|---|---|
| Projects | Control de cambios de alcance (`change_requests`), Integración y despliegue (`git_pull_requests`/`git_deployments`), Reunión y seguimiento de acuerdos (`ai_meetings`), Simulación de escenarios (`scenario_models`) |
| Finance | Factura de subcontratista (`subcontractor_invoices`), Orden de trabajo (`work_orders`) |
| HR | Ciclo de OKR (`okr_objectives`), Plan de desarrollo individual (`development_plans`/`dev_goals`), Campaña 360 (`review_360_campaigns`/`review_cycles`) |
| Service Desk | Releases (`sd_releases`), Ciclo de vida de artículo de conocimiento (`sd_kb_articles` + quality loop), Eventos de monitorización (`sd_monitoring_alerts`), Página de estado (`sd_status_incidents`), Resolución autónoma (`sd_autonomous_playbook_executions`) |
| CRM | Solicitud de funcionalidad (`feature_requests`), Conversación gobernada (`portal_conversations`), Formulario público (`/public-forms` → ticket) |
| Administration | Incidente de seguridad (`security_incidents`), Derechos RGPD (`gdpr_requests`), Activos y licencias (`alm_assets`/`alm_licenses`/`alm_contracts`), Alta y baja de empresa (tenant) |

- **Left out on purpose, as not business processes:**
  - Technical logs and queues: `ai_action_logs`, `email_logs`, `automation_events`, `webhook_trigger_logs`, `slack_notification_logs`, `workflow_queue`.
  - Export and import jobs.
  - Presence, calls and recordings in chat.
  - AI provider state, drift snapshots and evaluation runs.
  - The engines themselves (`bpmn_*`, `automation_workflows`, `sd_workflow_*`).
- **Already covered by an existing process:** `client_surveys` (NPS), `sd_ticket_approvals` (service request) and `training_enrollments` (training).
- **Buttons in dark theme (same measurement, 97 routes).** Catalogue titles were unreadable because a `<button>` does not inherit the text colour. 79 buttons on 9 screens were affected; after `button { color: inherit }` in `index.css`, 0.

**How to use it.**
1. Search ("Buscar proceso...") or pick one of the 7 categories.
2. Open a card ("Ver diagrama BPMN →") to view the diagram.
3. Use **Exportar BPMN** to download the `.bpmn` file.
4. To change it, press **Editar**, then **💾 Guardar diseño**.
5. To add a process, press **Nuevo proceso**, fill in name, category, Responsable, SLA and description, then press **Crear y diseñar**.

**Running a process** (admin, pm).
1. Open a **saved** process (a catalogue card that was never saved shows "Guarda el diseño para poder iniciarlo") and press **▶ Iniciar**. The engine uses the published version, or the latest saved one if none is published.
2. The view switches to **Ejecución**: *Mi bandeja* lists the human steps waiting for you; *Instancias* lists every instance of your organization with its status and pending steps (**Ver** shows the full history and lets admin/pm cancel).
3. **Completar** a step; optionally type variables, one per line (`aprobada=true`, `importe=900`). They feed the gateway conditions.

What the engine runs (`app/services/bpmn_engine.py`):
| Element | Behaviour |
|---|---|
| startEvent | Start (the one without an event definition if there are several) |
| task, userTask, manualTask | Waits for a person. If the task is in a **lane** named after a base role (admin, pm, team_lead, hr, employee, or Dirección, Project Manager, Team Lead, RRHH, Empleado), only that role (or an admin) sees and completes it; otherwise anyone in the organization |
| serviceTask, scriptTask, sendTask, businessRuleTask | Recorded as done; **they execute nothing** |
| exclusiveGateway | First outgoing flow whose condition holds, else the default flow, else the instance fails with the reason. Conditions: `variable op value` (`== != > < >= <=`) joined by `and`/`or` (`&&`/`||`), optional `${…}`; a condition that cannot be evaluated is false |
| parallelGateway | Splits to all outgoing flows; with several incoming flows it waits for all of them |
| intermediateCatchEvent + timer | `timeDuration` (ISO 8601: `PT2H`, `P1D`) or `timeDate`; woken by a job every minute |
| intermediateThrowEvent (none) | Passes |
| endEvent | Consumes the token; `terminateEventDefinition` ends the whole instance |

Anything else (sub-processes, call activities, boundary events, inclusive/event-based gateways, messages, signals, several pools with a start) makes **Iniciar** return 422 with the list of unsupported elements. A loop of automatic steps without a wait fails the instance after `BPMN_MAX_AUTOMATIC_STEPS` (500, Settings → Automatizaciones).

**Configuration.** None. No external services.

**Technical notes.**
- The diagram uses the `bpmn-js` 18 library: Modeler in edit mode, Viewer otherwise.
- **The 61 catalogue processes are hardcoded in the frontend** (`PROCESS_CATALOG`), and their XML is generated client-side.
- Saved designs go to `bpmn_processes` and `bpmn_process_versions` (full XML per version; status draft/published/archived).
- Endpoints:
  - `GET /api/v1/bpmn-processes?include_inactive=false`
  - `GET /api/v1/bpmn-processes/{id}`
  - `POST /api/v1/bpmn-processes`
  - `POST /api/v1/bpmn-processes/{id}/versions`

- Engine endpoints: `POST /api/v1/bpmn-processes/{id}/instances` (admin, pm), `GET /api/v1/bpmn-instances[?status=&process_id=]`, `GET /bpmn-instances/inbox`, `GET /bpmn-instances/{id}`, `POST /bpmn-instances/{id}/steps/{step}/complete` (internal users, role of the lane), `POST /bpmn-instances/{id}/cancel` (admin, pm). Tables `bpmn_instances`, `bpmn_instance_steps` (each element crossed is a row: that is the history). Timer job: Celery `bpmn_vencer_temporizadores` and APScheduler `bpmn_timers`, every minute.

**Limitations (measured).**
- **Service and script tasks do nothing**: there is nothing to bind them to yet. Use the Automations module for actions.
- No process mining, no SLA per step, no reassignment of a human step, and no variables form defined by the diagram (variables are typed free-form).
- The catalogue processes cannot be started until they are saved once. The Service Desk workflow engine is separate and not connected to `/bpm`.
- **Owner and SLA from "Nuevo proceso" are lost on reload.** They are never sent to the backend.
- **Some operations exist in the API with no UI:** version history, publish, delete, duplicate and seed. The backend has a second, different catalogue (55 linear processes) behind `POST /seed`.
- ~~Read and write by id have no organization check.~~ Measured 2026-11-04 (`tests/test_motor_bpmn.py`): GET, PATCH and saving a version of another organization's process return 404; the tenant filter scopes them.
- The page loads each process with a separate GET (N+1).

### AI Hub / Connectors — `/ai-hub`
*Roles:* admin, pm (route; Settings menu group). Backend: create, update, delete, set-default, test, sync and diagnostics all use `require_admin`, so a PM can view but not change.

**Purpose.** Configure the LLM providers used by every `call_ai` feature, test them, and see usage. "Connectors" here means **only the 8 LLM providers**.

**How to use it.**
1. Press **Add provider**.
2. Choose the type (anthropic/openai/gemini/deepseek/groq/mistral/ollama/azure), API key, base URL, default model and temperature.
3. Save, then press **Test**. Test sends a real "Di solo 'OK'" request.
4. Use **Sync models** to read the provider's `/models` list, and mark one provider as the default.

Other tabs:
- **Usage:** calls, tokens and cost per module.
- **🛡 Governance:** a read-only view of guardrail policies and audit. The page itself says policy management is pending.
- **Observabilidad:** BI model health and retrain (admin; unrelated to LLMs).
- **Guide:** static help.

Header buttons: **Diagnóstico**, **Sync all models**.

**Configuration.**
- Table `ai_providers`. API keys are encrypted with `encrypt_value` (Fernet `v2:` with a per-record salt, or KMS) and never returned (`has_api_key` only).
- Alternative: `.env` `AI_PROVIDER` / `AI_API_KEY` / `AI_MODEL` / `AI_BASE_URL`.

**Since 2026-11-05 (what contecmind had, added to this hub without a second screen):**
- **The `.env` provider is shown** as a card marked «Desde .env» (it worked but appeared nowhere, so the hub and AI Governance said «no provider» while Gemini answered). It can be tested (`POST /ai-providers/env/test`) and imported (`POST /ai-providers/env/import`): it becomes a normal, editable provider of the company with the key encrypted. The other screens that show «active provider» (AI Governance, NexusAgent) read the same list.
- **«Por función» tab:** provider and model per function (assistant, agent, planning, service desk drafts, auto-resolution, changes, KB, documents, contracts, meetings, BI narrative, Ask the Data, semantic tie-break, client portal, voice, AI modules). Empty means the default provider. Stored per company (`app_settings.ai_routing`); `call_ai(module=…)` applies it when the call does not ask for a specific provider, and falls back to the default if the chosen one is set aside.
- **Test and discover before saving:** in the provider form, «Probar sin guardar» (`POST /ai-providers/test-config`) and «Descubrir modelos con esta clave» (`POST /ai-providers/discover-models`) use what is typed; nothing is stored.
- **Fallback order:** each provider has «Orden de respaldo» (`priority`, migration 130); if the chosen one fails, the others are tried from lowest to highest.
- **A failure no longer disables a provider for good:** it is set aside for `AI_PROVIDER_ERROR_COOLDOWN_SECONDS` (300) and then retried; a successful answer puts it back to active. Before, it stayed in «error», out of selection and fallback, until someone edited it.
- **Reasoning models:** Gemini 2.5 (and o-series) spend tokens thinking. With the 10-token test cap the test always failed (measured with the real API: 7 of 10 tokens on reasoning, answer without text, `KeyError 'parts'`). The test now uses `AI_TEST_MAX_TOKENS` (256), short classification calls use `AI_SHORT_ANSWER_MAX_TOKENS` (256), an answer without text raises a clear error, and reasoning tokens count as output (they are billed).

**Technical notes.**
- Endpoints (`app/api/v1/endpoints/ai_providers.py`):
  - `GET/POST /api/v1/ai-providers`
  - `PATCH/DELETE /api/v1/ai-providers/{id}`
  - set-default
  - test
  - `POST /api/v1/ai-providers/sync-models/all`
  - `GET /api/v1/ai-providers/diagnostics`
  - `GET /api/v1/ai-providers/stats` (from `ai_usage_logs`)
  - `POST /api/v1/ai-providers/chat`
- The governance tab reads `/api/v1/ai-governance/policies`, `/audit-log` and `/audit-log/stats`.

**Limitations (measured).**
- **PATCH accepts any model attribute** (mass assignment), including `organization_id`, `total_cost_usd` and `created_by`.
- **`POST /ai-providers/chat` can use another tenant's provider.** It calls `call_ai` without organization scoping, and a caller-supplied `provider_id` is not org-checked, so any internal user can use another tenant's provider and key.
- **Usage stats include deleted providers.**
- **A provider can drop out of rotation after one failure.** A single timeout or 429 marks it `error`, and it stays out until an admin acts (see the intro).

### AI Governance — `/governance`

**Fixed 2026-11-05:** «Proveedor activo» showed «No configurado» while the `.env` provider was answering (it now reads the same provider list as the hub). «Tokens» showed «0K» (read as «OK»): each module was rounded to thousands before adding; it now shows the exact total.
*Roles:* admin (route and backend, `require_admin`).

**Purpose.** Per-module AI on/off switches and limits, usage stats and an action log.

**How to use it.**
- Tab **Modules:** toggle each of the 9 AI modules and set its limits.
- Tab **Stats:** usage statistics.
- Tab **Audit:** the last 100 actions.

**Configuration.** Table `ai_governance_configs`.

**Technical notes.**
- Endpoints (`app/api/v1/endpoints/governance.py`, `governance_service.py`):
  - `GET /api/v1/governance/config`
  - `PATCH /api/v1/governance/config/{module}`
  - `GET /api/v1/governance/stats`
  - `GET /api/v1/governance/logs?limit=100`
- Data comes from `ai_action_logs`, not from `ai_usage_logs`, which holds the real token and cost data.
- Guardrail policies (PII redaction and blocking) are a separate API, `/api/v1/ai-governance/*`. It has no editing UI, and no policies are seeded.

**Limitations (measured).**
- **Only 2 of the 9 toggles do anything.** `nexusassist` and `nexusagent` are enforced through `check_rate_limit`. The Oracle, meetings, sprint, contracts, KB, portal and voice toggles have no effect.
- **Daily caps and per-module usage never trigger.** They count action-log rows named `nexusassist`/`nexusagent`, but those rows are written as `contecflowassist`, `contecflowagent` and `contecfloworacle`. The per-module usage shown is empty for the same reason.
- **Token counts are mostly 0** in this screen's data source.
- **A second tenant's config may collide.** `module` is unique globally while the rows are per organization, so a second tenant's config insert could fail. Not verified.

### Global "📊 Exportar Excel" button
*Roles:* every role, on any page whose header shows it.

**Purpose.** Export the list currently on screen.

**How it works.**
- `exportVisibleListToExcel` (`frontend/src/components/layout/PageHeader.tsx`) reads the visible DOM under `.page-content`.
- It uses, in order of preference:
  1. a `[data-export-table]` element or the `exportTargetSelector` prop
  2. the largest visible `<table>`
  3. a CSS-grid list
  4. a fallback that puts each card's text into one "Detalle" column
- It downloads `<title>_<date>.xls`.
- No server call and no library are involved.

**Where it appears.**
- It is on by default in every `PageHeader`, and always on pages built with `ui/Page`.
- 34 pages turn it off; about 16 show it conditionally.
- In this area:
  - Reports: always shown.
  - Alerts: Operativas tab only.
  - Report Builder and Data Export: hidden.

**Limitations (measured).**
- **The file is not a real XLSX.** It is an HTML table with an `.xls` extension and the `application/vnd.ms-excel` MIME type, so Excel shows a format warning.
- **It exports only what is rendered.** Pagination and virtualisation limit it to the visible rows, and the card fallback gives one unstructured column.
- **The label is not translated.** It is hardcoded Spanish; the i18n key `reports.export_excel` ("Export to Excel") is not used.

### Worker jobs in this area (`app/worker.py`)

| Job | Schedule | Effect |
|---|---|---|
| `run_alert_engine` | daily 08:00 | Rules-based alerts (all tenants) |
| `run_scheduled_reports` | hourly :00 | Scheduled report emails (PDF without data; silent "success" without SMTP) |
| `send_weekly_report` | Monday 09:00 | Stub: collects emails, sends nothing |
| `check_missing_imputations` | weekdays 18:00 | Computes missing hours, sends nothing |
| `olap_nightly_etl` | daily 01:00 | Fills the DuckDB OLAP file |
| `bi_scheduled_delivery_run` | hourly :45 | Separate BI delivery service (not used by these pages) |
| `bi_kpi_push` | every 5 min | Realtime KPI snapshot (frame type ignored by the UI) |
| `bi_ml_retrain` | Sunday 03:30 | Runs multivariate anomaly detection, persists nothing |
| `ml-model-retrain` | day 1 monthly, 03:00 | Retrains the per-organization risk GradientBoosting model |
| `sync_connector_data` | hourly (21 entries) | ETL connector sync (entity "default") |
| `run_agent_task` | on demand | NexusAgent non-streamed runs |

No job evaluates smart alerts, takes CFD snapshots, computes EVM, runs the Oracle or evaluates conditional delivery rules.

**Not verified in this section.** None of the following was run against a live server:
- live LLM responses from any provider, and Azure / o-series compatibility
- real SMTP delivery and the rendered PDFs
- the rollback of NexusAgent streaming writes (inferred from code)
- the TF-IDF vector-length collapse in AI Assignment (inferred)
- the Portfolio empty-date 422 end to end
- whether `olap_nightly_etl` fills DuckDB in a real deployment
- any `etl_*` queue consumer outside the repository
- the Graph permissions M365 needs

---

## Administration, Configuration & Integrations

This section covers every screen an administrator uses to configure contecflow-PSA, and every integration with an external system. It is written for two readers: the **administrator** (what each screen does, step by step) and the **technical user** (endpoints, tables, settings keys).

**How it was measured.** Routes and roles come from `frontend/src/App.tsx` and `frontend/src/components/layout/Layout.tsx`. Endpoints come from the live FastAPI route table (`app.main.app.routes`, 2,055 routes, dumped with the project venv). Settings defaults come from `Settings.model_fields` in `app/core/config.py` and `app/core/config_groups/*`. Each "wired / not wired" statement comes from grepping the readers of a table or key in `app/` and `frontend/src/`. **No endpoint was called against a running server**, so nothing here is verified at runtime. Behaviour that depends on an external provider (DocuSign, Adobe Sign, Microsoft Graph, Slack, Teams, Jira, Twilio, Stripe, OIDC IdPs) is **Not verified** unless stated otherwise.

**Roles used below.** `admin`, `pm`, `team_lead`, `hr`, `employee` are `User.role` values. *Superadmin* is a separate flag (`User.is_superadmin`) that bypasses the tenant filter. The backend guards are `require_admin`, `require_admin_or_pm`, `require_any_manager`, `require_admin_or_hr`, `require_superadmin`, `require_internal_user` and `get_current_user` (any authenticated user). On almost every screen, the **front-end route role** and the **backend guard** differ. Both are listed, because what you see in the menu is not always what you can save.

**Three request-wide guards** run on every `/api/v1` route (`app/main.py`, `_ROUTER_GUARDS`):
- `bind_request_timezone`: request timezone.
- `apply_abac_for_route`: ABAC.
- `enforce_grc_matrix`: the GRC permission matrix. It can only deny, never grant; see [GRC](#grc--sod-matrix--grc).

---

### Multi-tenant model (how organizations isolate data)

*Code:* `app/db/session.py`, `app/core/tenancy.py`, `app/core/deps.py::get_current_user`

- **Tenant context.** `get_current_user` writes `db.info["organization_id"] = user.organization_id` and `db.info["is_superadmin"]`. Superadmins get `organization_id=None` and `is_superadmin=True`, which bypasses the filter.
- **Automatic read filter.** A `do_orm_execute` listener on `SessionLocal` adds a `with_loader_criteria` to every ORM **SELECT**, for every mapped model that has an `organization_id` column: `organization_id == <org>`.
  - Models flagged `_tenant_filter_include_global = True` (for example `AppSetting`, `CustomProjectType`) use `organization_id == <org> OR organization_id IS NULL`. The NULL rows are global defaults shared by all tenants.
  - A regular user with **no** organization gets a `false` criterion and sees zero rows.
  - The filter is skipped for:
    - relationship loads;
    - sessions with `bypass_tenant_filter=True` (the context manager `sin_filtro_de_tenant`);
    - uninitialised sessions, i.e. background jobs and tests (`is_superadmin is None`).
- **Query/execute layers.** `TenantSession.query()` and `.execute()` resolve models without `organization_id` through, in order: `org_id`, `project_id` (subquery on `projects`), `user_id` / `actor_id` (subquery on `users`). A model with none of these that is not declared `_tenant_exempt = True` raises `TenantIsolationError` (fail-closed). `Organization` is the only declared exempt model.
- **Automatic stamping on insert.** A flush listener copies the session's `organization_id` into new rows whose `organization_id` is None.
- **Kill switches (env, read at import):** `TENANT_AUTO_FILTER_GLOBAL` (default `1`) and `TENANT_AUTO_STAMP_ON_INSERT` (default `1`). Setting either to `0` disables that protection for the whole process.
- **Explicit helpers** (`app/core/tenancy.py`):
  - `org_scoped_or_404`: fetch by id, 404 on cross-tenant. NULL-org rows count as global and stay accessible.
  - `assert_same_org`.
  - `assert_org_id_is_own`: strict check for a client-supplied org id; 404 unless it matches or the caller is a superadmin.
  - `organizacion_existe`.
- **Measured on 2026-11-04 with two companies** (copy of the database, a second organization with its own admin, scripts in the session scratchpad):
  - **Reads:** the second company's admin called the 578 GET routes without parameters (streaming excluded) looking for any id, email or project name of the first. One route showed them: `/settings/general` listed per-ticket settings (dynamic fields, on-hold snapshot) stored as **global** rows. Fixed: they are stored under the ticket's organization, and migration 125 moves the existing ones.
  - **Reads by id:** 278 one-parameter GET routes; 145 could be fed ids of the first company (371 requests). None returned its data; 12 echo the requested id with empty content.
  - **Writes by id:** 296 one-parameter PATCH/PUT/DELETE routes; 118 could be fed ids of the first company (174 requests). None changed or deleted its rows. 178 write routes and 133 read routes have no table deducible from the parameter name and were not probed.
  - **Unique values were global:** 19 business uniques (project code, invoice number, contract, opportunity, work order and change numbers, task types, statuses, departments, skills, wiki space slug, asset tag and serial, AI governance module, alert type, embedding cache) were unique across all companies. The second company could not use "PRJ-0001", and its task types screen returned 500 when seeding "bug". Migration 125 makes them unique per organization; `tests/test_unicos_por_organizacion.py` fails if a new global unique appears without a written reason (48 deliberate ones listed: login identity, tokens, public URLs, rows unique inside their parent).
  - **Deactivating an organization** stopped only SSO and passkey sign-in. Password login, already issued tokens, API keys, the client portal and WebSockets kept working. Now `exigir_organizacion_activa` (`app/db/session.py`) runs on every request (403 "La organización está desactivada") and at password login.
  - **`deps.get_current_client`** (portal collaboration and conversations) did not publish the tenant, and an uninitialised `TenantSession` does not filter. It does now.
  - **Hand-written SQL:** the scheduled-reports summary counted every company's reports; it is now scoped.
  - **No database-level isolation:** there is no Postgres RLS (0 tables) and the application connects as a superuser role. Isolation relies entirely on `TenantSession`.
- **What a superadmin creates stays in their company (since 2026-11-05).** A superadmin's session has no company filter, so rows they created through the screens were stored without a company. Their own company's users never saw them. Measured on a copy: an approval workflow created by `admin@company.com` was invisible to the company's PMs. Now the auto-stamp falls back to the superadmin's own company when the record itself (its project or user) does not say. Rows created in another company on purpose, and global models, are unchanged. In the same way, the AI module switches (*AI Governance → Modules*) now read and write the row of the company explicitly. Before, a superadmin could change another company's row.
- **Rows without a company (measured 2026-11-05, 390 tables).** Rows without `organization_id` in a strict table are invisible to their company's users. In a deployment's database:
  - **Exchange rates (12):** global on purpose, but the strict filter hid them, so *Rentabilidad* converted 1 to 1 without warning. `ExchangeRate` is now global plus per-company. A manual rate belongs to the session's company and wins at the same date, without touching the global rate. The ECB job writes the global rates.
  - **ITSM metric snapshots:** the hourly job computed one row with every company's tickets and no company. It now computes one row per company, and the BI alert reads its own company's.
  - **Oracle predictions:** the job did not set a company. All four types now take it from their project, ticket or user.
  - **Assistant messages and SSO config:** created by a superadmin, now covered by the superadmin stamp.
  - **Migration 135** re-homes the existing rows from their own record (conversation, ticket, creator) and deletes the old mixed snapshots.
  - **Result on a copy:** only deliberate global rows remain without a company (settings, exchange rates, GRC defaults).

- **Database isolation (RLS, since 2026-11-05).** A second barrier under the ORM filter, in PostgreSQL itself (`app/db/rls.py`).
  - **Measured before:** the application connected as `contecflow`, a superuser with BYPASSRLS, and there were 0 policies. Anything that did not go through the ORM filter (hand-written SQL, bulk operations) had nothing underneath.
  - **Policies:** one per table with `organization_id` or `org_id` (400 tables), generated from the models with the same meaning as the ORM filter: strict; global rows (`NULL`) for `_tenant_filter_include_global`; home company or membership for users. Every `alembic upgrade` rebuilds them (`alembic/env.py`), so a new table never stays without one. Inserting a row of another company is rejected; a row without company is allowed.
  - **Context:** before each statement and each flush, the session sets `app.tenant` (transaction-local) to its company, or to empty where the ORM does not filter either (superadmin, background jobs, `sin_filtro_de_tenant`).
  - **Application role:** policies only act if the application does not connect as the schema owner.
    - `setup.sh` creates `APP_DB_USER` (default `contecflow_app`, no superuser, no BYPASSRLS), generates `APP_DB_PASSWORD` in `.env` and points `DATABASE_URL` at it. Migrations keep the owner in `DATABASE_MIGRATIONS_URL`. `CONTECFLOW_DB_APP_ROLE=0` skips this.
    - In docker compose, the `migrate` service runs `python -m app.db.rls`, and the app uses `APP_DB_USER` when it is defined (otherwise the owner, as before).
  - **Checking it:**
    - *Admin → Estado sistema* (`GET /api/v1/settings/db-isolation`, admin) shows whether it is armed: connection role, and tables with RLS out of those expected.
    - The API logs a warning at startup when it is not armed.
  - **Measured on a copy with the application role:**
    - 97 menu routes and 2268 API calls with 0 errors.
    - The 179 GET endpoints the screens call return the same counts as with the owner, so RLS hides nothing the application shows.
    - `tests/test_rls_postgres.py` (runs with `RLS_TEST_OWNER_URL` and `RLS_TEST_APP_URL`) proves that hand-written SQL in company A does not see company B, and that it cannot insert into B.
  - **Coverage (measured):** all 400 mapped tables have a company column, so all have a policy. The only exception is `organizations`, which is exempt on purpose (`_tenant_exempt`). No table depends on the ORM's `project_id`/`user_id` fallback.
  - **pgvector index:** the HNSW index can only be created by the schema owner. With the application role, saving the first vector logs a warning and goes on (savepoint), and KB search keeps working by scanning the table. `kb_vectores.asegurar_indices` creates one index per vector dimension found in the column. It runs as the owner when pgvector is enabled (`preparar`) and on every start or deploy (`python -m app.db.rls`). Measured on a disposable `pgvector/pgvector:pg16` (`KB_PGVECTOR_URL`):
    - a role without privileges saves the vector without failing;
    - the owner then creates `ix_sd_kb_embedding_vec_8`, idempotently;
    - `python -m app.db.rls` recreates it after it is dropped.

- **Entering a company (since 2026-11-05).** Each deployment chooses one mode in `.env` (`TENANT_ENTRY_MODE`; code in `app/services/entrada_service.py`):
  - `email_selector` (default): email and password. With one active company the user enters it directly. With several, the login answers `organization_selection_required` with the list and a 5-minute `selection_token` that is only valid for `POST /auth/select-organization`; the login screen shows a picker. The header shows a company switcher (`POST /auth/switch-organization`) for users in more than one.
  - `subdomain`: the host decides: `<slug>.TENANT_ROOT_DOMAIN` or the company's own `domain` (migration 126). The login shows that company's name. A user who is not a member of that company cannot enter, and a session of another company is refused on that host (403). `X-Forwarded-Host` is honoured only from trusted proxies (`TRUST_PROXY_HEADERS`, `TRUSTED_PROXY_CIDRS`).
  - `org_field`: the login asks for the company code (slug). A wrong code answers like a wrong password.
  - The chosen company travels as the `org` claim of the access and refresh tokens (and the MFA challenge, so the second factor keeps it). On every request it is re-checked: the user must still belong to it (its own record or a membership) and it must be active; if the membership was removed, the session falls back to the company of the user's own record. Passkey and SSO go through the same decision (SSO uses its provider's company). Superadmins enter no company and see all, as before.
  - Users are visible in a company if their own record is there **or** they have a membership in it (`_tenant_filter_members` on `User`).
  - Not verified: a real wildcard DNS and certificate for subdomains; it was tested with `Host` headers.
- **Limitations (measured):**
  - Writes (UPDATE/DELETE) are **not** narrowed by the listener; each endpoint's own WHERE clause has to be correct.
  - Public, unauthenticated endpoints have no tenant context. Examples: `/forms/public/*`, `/webhooks/fire/{slug}`, the Slack and Teams inbound command receivers. Their queries run unfiltered.

---

### Settings — `/settings`
*Roles:* front-end route `admin`, `hr`, `pm`. The sidebar entry shows only for `admin`. Tabs are filtered per role:

| Group | Tab (UI label) | Tab id | Visible to |
|---|---|---|---|
| Personal | General | `general` | admin |
| | Sesión | `session` | admin |
| | Usuarios | `users` | admin, hr |
| | Vacaciones | `vacations` | admin, hr |
| | Departamentos | `depts` | admin, hr |
| | Sedes | `offices` | admin |
| | Idiomas | `idiomas` | admin |
| Workspace | Tipos tarea | `task-types` | admin, pm |
| | Tarifas | `rates` | admin |
| | Numeración | `numbering` | admin |
| | Campos extra | `fields` | admin |
| | Alertas | `alert-config` | admin |
| | Métricas | `metrics` | admin |
| Sistema | Roles | `roles` | admin |
| | Config. dinámica | `runtime-flags` | admin |
| | Credenciales | `integrations` | admin |
| | Email-to-ticket | `email-inbound` | admin |
| | E-firma | `esign` | admin |
| | Nivel de log | `log-level` | admin |
| | Estado sistema | `system-state` | admin |

`?tab=<id>` opens a tab directly; the Service Desk links to `?tab=integrations`.

**Purpose.** This is the central configuration page. Some tabs edit the generic key/value store, some edit typed catalogues, and two edit the runtime-settings and credential stores.

**How to use it (per tab).**
1. **General.** Edit the user-facing keys of `app_settings`. Missing global rows are seeded on the first GET (`DEFAULT_SETTINGS`): `company_name`, `company_logo_url`, `currency`, `timezone`, `language`, `work_hours_per_day`, `work_days_per_week`, `budget_alert_threshold`, `overload_threshold`, `idle_timeout_enabled`, `idle_timeout_minutes`. Change a value and save; each field is one `PATCH`.
2. **Sesión.** Turn on **idle logout** (`idle_timeout_enabled`) and set its minutes (`idle_timeout_minutes`, default 30). These are read by `frontend/src/context/AuthContext.tsx` (staff app) and by `client_portal_service` (portal).
3. **Usuarios.** User CRUD (`/users`): role, department, organization.
4. **Vacaciones.** Edit vacation policies and per-user yearly balances (`vacation_policies`, `user_vacation_balances`). `absence_service` reads the balances.
5. **Departamentos.** CRUD on `departments`. Delete is blocked while dependencies exist (`_check_department_dependencies`).
6. **Sedes.** CRUD on `offices`.
7. **Idiomas.** Three tabs (reviewed 2026-11; before that nothing here reached anyone else):
   - **Idioma del operador.** Your own back-office language. It is saved on the server (`PATCH /users/me/preferences`), so it follows you to any browser. Changing it no longer reloads the whole app. A language chosen on the login screen wins over the stored one and is saved on entry.
   - **Traducciones del back-office.** Override any back-office text for **your whole company**. Saved per organisation in `app_settings` (key `app_translations`, `{lang: {module: {key: text}}}`) via `GET/PUT /api/v1/settings/app-translations` (PUT: admin). Everyone in the company gets them on their next page load. Leaving a field empty removes the override.
   - **Portal cliente.** Override portal texts. Stored in `org_brandings.portal_translations` and delivered to clients inside `GET /portal/branding` (`translations`). Saving merges key by key, so saving one text no longer wipes the rest of that language.
   - The client portal applies the language stored on the client's profile when they sign in, and its menu group titles are translated in its eight languages.
   - **Importar JSON / Exportar JSON** sit side by side at the top of both translation tabs. Export downloads the language being edited, every key with its current text, in exactly the format import accepts (`{lang: {module: {key: text}}}` for the back-office, `{lang: {key: text}}` for the portal): export, translate, import, save. Before, the back-office export wrote `{module: …}` and re-importing it failed, and the portal export ignored the saved overrides.
8. **Tipos tarea.** CRUD on `task_types`.
9. **Tarifas.** Rate tables and entries (`rate_tables`, `rate_entries`). `rate_card_service` reads them.
10. **Numeración.** Code sequences (`numbering_sequences`): prefix, format, reset. `app/services/numbering.py::next_numbered_code` reads them for tasks, risks, milestones, pipeline and the worker.
11. **Campos extra.** Global custom fields (`custom_fields`). This is a different system from the per-project [Custom fields](#custom-fields--custom-fields).
12. **Alertas.** Two parts: enable/disable and thresholds per alert type (`alert_configs`), and toggling BI smart-alert rules (`/bi/alerts/rules`).
13. **Métricas.** BI custom metrics (`/bi/alerts/custom-metrics`).
14. **Roles.** Custom roles with a `module_access` JSON (`custom_roles`).
15. **Config. dinámica.** See [Runtime settings](#runtime-settings-config-dinámica).
16. **Credenciales.** See [Integration credentials](#integration-credentials-credenciales).
17. **Email-to-ticket.** The same component as Service Desk → Configuración → Correo entrante (`ConfigCorreoEntrante`). It configures the inbound mailbox through the `sd_mailbox` credential provider.
18. **E-firma.** The DocuSign and Adobe Sign keys. See [E-signature](#e-signature-docusign--adobe-sign--esign).
19. **Nivel de log.** Read and set the Python log level of the loggers `root`, `contecflow`, `uvicorn`, `uvicorn.error` and `uvicorn.access`, or of one named logger.
20. **Estado sistema.** Read-only view of internal `app_settings` keys (prefixes `bi.*` and others), grouped.

**Technical notes.**

| Area | Endpoints | Guard / tables |
|---|---|---|
| General | `GET /api/v1/settings/general`, `PATCH /api/v1/settings/general/{key}` | GET: `get_current_user`; PATCH: `require_admin`. Table `app_settings` (`key`, `value`, `organization_id`; unique `(key, organization_id)`) |
| Org defaults | `GET /api/v1/settings/org-defaults` | Any user. Reads runtime keys `DEFAULT_CURRENCY`, `_TIMEZONE`, `_LANGUAGE`, `_WORKING_HOURS_PER_DAY`, `_WEEKLY_CAPACITY_HOURS`, `_VACATION_DAYS_PER_YEAR`, `_TAX_RATE` |
| Catalogues | `GET/POST/PATCH/DELETE /api/v1/settings/{project-types,project-statuses,task-statuses,departments,holidays}` | Tables `custom_project_types`, `custom_project_statuses`, `custom_task_statuses`, `departments`, `holidays` |
| Advanced config | `/api/v1/advanced-config/{roles,modules,task-types,alert-configs,rate-tables[/entries],vacation-policies,vacation-balances,offices,numbering[/reset],custom-fields[/values],templates[/apply]}` | Mostly `require_admin`; rate tables and vacations use `require_admin_or_hr` |
| Log level | `GET/POST /api/v1/settings/log-level` | `require_admin` |
| Audit | `GET /api/v1/settings/audit-log?scope=&key=&provider=&actor_id=` | `require_admin`. Table `settings_audit_log`. **There is no UI for it** (the client `settingsApi.auditLog` exists, but no page calls it) |

**Limitations (measured).**
- **Fixed 2026-11-03 — `GET /settings/general` leaked secrets.** It is read by every signed-in user (the idle timeout) and returned every `app_settings` row in plaintext, including e-sign tokens and secrets (`esign.*`), the JWT keyring and `METRICS_AUTH_TOKEN`. Now non-admins get only the general settings (factory keys and plain names, no dotted/internal keys), and nobody gets the value of a sensitive key (`token`, `secret`, `password`, `keyring`, `credential`, `*_key`, `client_id`): it comes back as `••••••••`. Admins still see the internal keys (read-only *System status* view), masked. Tests: `tests/test_ajustes_generales_sin_fugas.py`. Since 2026-11-03 the e-sign credentials (`esign.*` keys matched by `es_sensible`) are also stored encrypted (`esign_service.cifrar_si_es_secreto`; migration 117 for existing rows; test `tests/test_esign_secretos_cifrados.py`). Other internal keys that are not e-sign are not encrypted by this change.
- **Fixed 2026-11-03 — `PATCH /settings/general/{key}` accepted any key and overwrote global rows.** Non-superadmins can now write only general settings (403 otherwise), and the write goes to the organization's own row, created on first change; before, when the organization had no row, the **global** row shared by every tenant was overwritten.
- **`budget_alert_threshold`, `overload_threshold`, `work_days_per_week` and `company_logo_url` have no reader** in `app/` or `frontend/src` other than the seed and the label map. Editing them changes nothing.
- **Alertas (`alert_configs`) is not read by the alert engine.** `alert_service.py` uses hard-coded thresholds (100 %, 85 %, 7 days). Only the CRUD service touches `alert_configs`.
- Roles: see *Custom roles and module access* above. Editing the modules of an existing role used to be dropped silently (`module_access` was missing from the update schema); fixed.
- **Tipos tarea (`task_types`) and Campos extra (`custom_fields`) have no reader** outside their own CRUD and settings tab.
- **Nivel de log changes only the worker process that handled the request.** It is not persisted and not broadcast. With several Uvicorn workers or a Celery worker, other processes keep their level until restart.
- `TemplatesSection` (`/advanced-config/templates`) is defined in `SettingsPageSections.tsx` but **no tab renders it** (dead code).
- In the Users form, a non-superadmin admin's organization dropdown calls `GET /organizations` (`require_superadmin`), which fails for them.

#### Runtime settings ("Config. dinámica")

**Purpose.** Typed operational settings that can be changed without a redeploy.

**How to use it.**
1. Open **Settings → Sistema → Config. dinámica**.
2. Pick one of the 15 group pills: SLA, Service Desk, Health scoring, Semantic, Política contraseñas, Locale y jornada, Tokens, Rotación de claves, IA, Feature flags, Almacenamiento, Red / Proxy, Branding / UI, Observabilidad, Timeouts.
3. Change a value. The row becomes "dirty".
4. Save that row. Each save is one `PUT`.

**Configuration / resolution order.** `get_runtime_*` resolves a key in this order:
1. the `app_settings` row for `(key, caller's org)`;
2. the global row `(key, NULL)`;
3. the env-backed `settings.<KEY>`;
4. the call-site default.

Values are cached in-process for **60 s** (`_CACHE_TTL_SECONDS`). A write invalidates the local cache and publishes on Redis pub/sub (`app/core/settings_pubsub.py`). Without `REDIS_URL`, other workers see the change only after the TTL.

**Technical notes.**
- `GET /api/v1/settings/runtime/{group}` and `PUT /api/v1/settings/runtime/{group}/{key}` with body `{"value": "..."}`. Both are `require_admin`.
- Unknown group → 404. A key outside the group, or a value that does not parse to the declared type → 400.
- The PUT writes **exactly** the `(key, admin's organization_id)` row (`_upsert_setting_at_scope`). It writes the global row only if the admin has no organization.
- Every write appends to `settings_audit_log` with scope `runtime`. **The old and new values are stored in plaintext**, because runtime keys are treated as non-secret; that includes `METRICS_AUTH_TOKEN`.

**Limitations (measured).**
- **Some call sites read only the global row.** They call `get_runtime_*(db, "KEY")` without an org, so an org-scoped write by an admin who belongs to an organization is ignored there:

  | Keys | Where they are read |
  |---|---|
  | `KEY_ROTATION_ENABLED`, `JWT_KEY_ROTATION_DAYS`, `JWT_KEY_RETENTION_COUNT`, `INTEGRATION_SECRET_ROTATION_DAYS` | `key_management.py` |
  | `TRUST_PROXY_HEADERS`, `TRUSTED_PROXY_CIDRS` | not listed here |
  | `METRICS_AUTH_TOKEN` | not listed here |
  | `OUTBOUND_HTTP_TIMEOUT_SECONDS`, `OUTBOUND_AI_TIMEOUT_SECONDS` | not listed here |
  | `SEMANTIC_EMBEDDINGS_BACKEND`, `AI_COST_ALERT_USD_PER_DAY`, `SEM_WEIGHT_*`, `SEM_TOP_K_HISTORY`, `SEM_MULTI_ROLE_FACTOR` | not listed here |
  | `SD_EVENT_MAX_ATTEMPTS`, `SD_EVENT_BATCH_SIZE` | not listed here |
  | `DEFAULT_PROJECT_TYPE`, `DEFAULT_BILLING_TYPE`, `DEFAULT_CURRENCY` | at least one call site |
  | `PROJECT_NAME` | PDF branding in `billing_reports.py` |
  | `REFRESH_TOKEN_EXPIRE_DAYS` | at least one call site |

- **Many call sites use `get_runtime_int(...) or settings.X`,** so a value of `0` falls back to the env value.
- **Seven keys are exposed in the UI but no runtime read uses them, so editing them has no effect.** The "Consumer" column of the reference table marks them.

#### Integration credentials ("Credenciales")

**Purpose.** Store provider credentials per organization, encrypted, instead of in `.env`.

**How to use it.**
1. Open **Settings → Sistema → Credenciales**.
2. Pick a provider pill.
3. Fill in a field and save. Saving an **empty** value deletes the DB row, and the value falls back to `.env`.
4. Secret fields are never echoed back. The UI shows only `configured` and `source` (`db`, `env` or `unset`).
5. Press **Test** to run the provider probe.

**Technical notes.**

| Endpoint | Guard | What it does |
|---|---|---|
| `GET /api/v1/settings/integrations` | `require_admin` | List providers |
| `GET /api/v1/settings/integrations/{provider}` | `require_admin` | Field state |
| `PUT /api/v1/settings/integrations/{provider}/{key}` | `require_admin` | Set or clear a field |
| `POST /api/v1/settings/integrations/{provider}/test` | `require_admin` | Run the probe |

- Table `integration_credentials` (`provider`, `key`, `value`, `value_encrypted`, `is_secret`, `organization_id`).
- Secrets are encrypted with `app/core/encryption.py`. The key is derived from `SECRET_KEY` (HKDF, v2), or AWS KMS when `KMS_PROVIDER=aws`.
- Reads resolve org row → global row → env. The cache is 60 s, with Redis invalidation.
- The audit log (`settings_audit_log`, scope `integration`) stores **hashes** of secrets, not the values.

**Providers (14) and whether the product reads them from this store (measured with `get_credential` / `get_provider_config`):**

| Provider | Fields | Read from this store by | Test probe |
|---|---|---|---|
| `smtp` | host, port, user, password\*, from | `auth_service` (password mail), service desk mail | SMTP connect |
| `sd_mailbox` | protocol (imap/graph), host, port, user, password\*, folder, mailbox | `service_desk/buzones.py` | **none** |
| `contecmind` | base_url, client_id, client_secret\* | `service_desk/contecmind.py` | **none** |
| `monitoring` | ingest_token\* | `service_desk/monitoring_ingest.py` | **none** |
| `aws_s3` | bucket, region, access_key\*, secret_key\* | `s3_service.py` | yes |
| `ms_graph` | tenant_id, client_id, client_secret\*, teams_webhook\*, teams_bot_app_id, sharepoint_site_id | **only** `service_desk/buzones.py` (Graph mailbox). **The `/m365` endpoints read `settings.AZURE_*` / `TEAMS_WEBHOOK_URL` from env and ignore this store.** | token request |
| `slack` | webhook_url\*, signing_secret\* | **nothing but the probe.** Slack consumers read `settings.SLACK_WEBHOOK_URL` / `SLACK_SIGNING_SECRET`, `slack_configs` or `integration_configs` | POST to the webhook |
| `twilio` | account_sid, auth_token\*, from_number | **nothing but the probe.** `sms_service.py` reads env `TWILIO_*` only, and these fields have no env fallback | account fetch |
| `stripe` | publishable_key, secret_key\*, webhook_secret\* | `payments_service.py` (secret_key, webhook_secret) | `GET /v1/balance` |
| `docusign` | integration_key\*, secret_key\*, account_id, base_url | **nothing but the probe.** E-sign reads `app_settings` `esign.*` keys and then env | passive: only checks `account_id` is set |
| `adobe_sign` | client_id, client_secret\*, base_url | **nothing but the probe** (same as DocuSign) | GET `{base}/baseUris` |
| `ai_providers` | anthropic_api_key\*, openai_api_key\*, azure_speech_key\*, google_stt_api_key\* | `ai_client.py`, `ai_modules/_base.py`, `stt/*` | Anthropic `count_tokens`, else OpenAI `/v1/models` |
| `webhooks` | webhook_secret\*, inbound_email_secret\*, github_secret\*, gitlab_secret\*, scim_bearer_token\* | **only** `inbound_email_secret` (`inbound_email_service`). The others are read from env by their consumers | passive: lists which secrets are set |
| `open_exchange_rates` | app_id\* | `currency_sync.py` | `latest.json` |

\* secret, stored encrypted.

**Limitations.**
- For `slack`, `twilio`, `docusign` and `adobe_sign`, and for part of `ms_graph` and `webhooks`, **a green Test does not mean the product uses the value.** Configure those through `.env` or the dedicated screen (E-firma, Jira).
- A real send through any provider is **Not verified**.
- Because the encryption key is derived from `SECRET_KEY`, changing `SECRET_KEY` without re-encrypting leaves stored secrets undecryptable. This follows from the derivation and was not tested.

---

### Runtime settings reference

The source is `RUNTIME_FLAG_GROUPS` in `app/services/settings_service.py`: **18 groups, 172 keys**. "Default" is the code default in `Settings` (`app/core/config.py` plus `config_groups/*`); a `.env` value overrides it. Measured example: the local `.env` sets `ACCESS_TOKEN_EXPIRE_MINUTES=60`.

"Consumer" is what a grep of `app/` found:
- **rt**: read at runtime through `get_runtime_*`, so a UI change takes effect within 60 s.
- **static**: only `settings.<KEY>` is read, so a UI change has **no effect**.
- **none**: no reader at all.

| Group | Key | Type | Default | Meaning | Consumer |
|---|---|---|---|---|---|
| sla | SLA_P1_RESPONSE_HOURS | float | 1.0 | P1 Critical, response hours | rt (`sla_service`); also column default of SLA policies at import |
| sla | SLA_P1_RESOLUTION_HOURS | float | 4.0 | P1 resolution hours | rt (same) |
| sla | SLA_P2_RESPONSE_HOURS | float | 4.0 | P2 High, response hours | rt |
| sla | SLA_P2_RESOLUTION_HOURS | float | 8.0 | P2 resolution hours | rt |
| sla | SLA_P3_RESPONSE_HOURS | float | 8.0 | P3 Medium, response hours | rt |
| sla | SLA_P3_RESOLUTION_HOURS | float | 24.0 | P3 resolution hours | rt |
| sla | SLA_P4_RESPONSE_HOURS | float | 24.0 | P4 Low, response hours | rt |
| sla | SLA_P4_RESOLUTION_HOURS | float | 72.0 | P4 resolution hours | rt |
| sla | SLA_BUSINESS_HOURS_ONLY | bool | true | Without an SLA policy: count business hours only | rt |
| sla | SLA_BUSINESS_START_HOUR | int | 8 | Without policy: workday start (0-23) | rt |
| sla | SLA_BUSINESS_END_HOUR | int | 18 | Without policy: workday end (1-24) | rt |
| sla | SLA_BUSINESS_DAYS | str | `1,2,3,4,5` | Without policy: ISO workdays (1=Mon … 7=Sun) | rt |
| sla | SLA_PREDICTION_WARNING_PCT | float | 0.7 | "At risk" once this share of the SLA is used (0-1) | rt |
| sla | SLA_PREDICTION_HOURS_CRITICAL | int | 4 | Prediction hours window, critical | rt |
| sla | SLA_PREDICTION_HOURS_HIGH | int | 8 | Prediction hours window, high | rt |
| sla | SLA_PREDICTION_HOURS_MEDIUM | int | 24 | Prediction hours window, medium | rt |
| sla | SLA_PREDICTION_HOURS_LOW | int | 72 | Prediction hours window, low | rt |
| sla | SLA_PREDICTION_SEVERITY_CRITICAL_H | float | 1.0 | Severity threshold, critical (h) | rt |
| sla | SLA_PREDICTION_SEVERITY_HIGH_H | float | 4.0 | Severity threshold, high (h) | rt |
| service_desk | SD_NOTIFY_REQUESTER_ON_CREATE | bool | true | Email the requester when a ticket is created | rt (`ticket_event_processor`) |
| service_desk | SD_NOTIFY_REQUESTER_ON_REPLY | bool | true | Email the requester on public agent replies | rt |
| service_desk | SD_NOTIFY_REQUESTER_ON_RESOLVE | bool | true | Email the requester on resolution | rt |
| service_desk | SD_NOTIFY_AGENTS_BY_EMAIL | bool | true | Also email agents (in-app alerts always happen) | rt |
| service_desk | SD_INBOUND_ADDRESS | str | `''` | Support address; identifies the org and is the Reply-To | rt |
| service_desk | SD_REOPEN_ON_REPLY | bool | true | Inbound reply reopens a resolved ticket | rt |
| service_desk | SD_CHANNEL_TICKET_TYPE | str | `incident` | Ticket type for new inbound emails (incident, service_request, question) | rt |
| service_desk | SD_MAIL_MAX_PER_RUN | int | 50 | Inbound emails read per run | rt |
| service_desk | SD_MAIL_MAX_ATTACHMENT_MB | int | 15 | Max inbound attachment size (MB) | rt |
| service_desk | SD_CAB_GROUP_ID | str | `''` | Queue (group id) acting as CAB | rt |
| service_desk | SD_CAB_APPROVAL_RULE | str | `majority` | CAB rule: majority, all, any | rt |
| service_desk | SD_CHANGE_AUTO_APPROVE_MAX_RISK | int | 30 | Standard changes up to this risk score self-approve | rt |
| service_desk | SD_EVENT_SEVERITY_MAP | str (JSON) | `{"critical":"p1_critical","high":"p2_high","error":"p2_high","warning":"p3_medium","info":"p4_low"}` | Monitoring alert severity → ticket priority | rt |
| service_desk | SD_EVENT_AUTO_RESOLVE | bool | true | Resolve the incident when the alert recovers, if untouched | rt |
| service_desk | SD_ONCALL_PRIORITIES | str | `p1_critical,p2_high` | Priorities that page the on-call agent | rt |
| service_desk | SD_ONCALL_SMS | bool | true | Also page by SMS (needs env `TWILIO_*`) | rt |
| service_desk | SD_KB_REQUIRE_REVIEW | bool | false | KB articles need a reviewer before publishing | rt |
| service_desk | SD_KB_REVIEWER_GROUP_ID | str | `''` | Reviewer queue (empty: admins) | rt |
| service_desk | SD_KB_RAG_MIN_SCORE_VECTOR | float | 0.35 | Minimum cosine to cite an article | rt |
| service_desk | SD_KB_RAG_MIN_SCORE_WORDS | float | 0.5 | Without sentence model: share of words to cite an article | rt |
| service_desk | SD_KB_RAG_MAX_SOURCES | int | 3 | Articles given to the AI and cited per answer | rt |
| service_desk | SD_KB_CORRECTION_MATCH | float | 0.8 | Similarity for an expert correction to apply | rt |
| service_desk | SD_KB_STALE_DAYS | int | 180 | Days untouched before an article is flagged (0: off) | rt |
| service_desk | SD_KB_CONTRADICTION_SIMILARITY | float | 0.75 | Similarity for two articles to be compared with AI | rt |
| service_desk | SD_KB_CONTRADICTION_MAX_PAIRS | int | 10 | Pairs compared with AI per daily run (0: off) | rt |
| service_desk | SD_TIME_TO_TIMESHEET | bool | true | Ticket time on tickets with a project goes to the agent's timesheet | rt |
| service_desk | SD_ASSET_REFRESH_DAYS | int | 7 | Days before an asset expiry that open a renewal ticket (0 = off) | rt |
| service_desk | SD_EVENT_MAX_ATTEMPTS | int | 5 | Event delivery, max attempts | rt (global only) |
| service_desk | SD_EVENT_BATCH_SIZE | int | 200 | Event delivery, events per run | rt (global only) |
| health | HEALTH_NPS_LOOKBACK_DAYS | int | 90 | Client health: NPS lookback (days) | rt |
| health | HEALTH_TICKET_LOOKBACK_DAYS | int | 30 | Client health: ticket lookback (days) | rt |
| health | HEALTH_DEFAULT_NO_DATA | float | 70.0 | Score when there is no data (0-100) | rt |
| health | HEALTH_PORTAL_BASE_SCORE | float | 30.0 | Portal component base score | rt |
| health | HEALTH_PORTAL_SCORE_PER_SESSION | float | 7.0 | Score added per portal session | rt |
| health | HEALTH_WEIGHT_NPS | float | 0.4 | Weight, NPS | rt |
| health | HEALTH_WEIGHT_DELIVERY | float | 0.2 | Weight, delivery | rt |
| health | HEALTH_WEIGHT_BUDGET | float | 0.15 | Weight, budget | rt |
| health | HEALTH_WEIGHT_TICKETS | float | 0.15 | Weight, tickets | rt |
| health | HEALTH_WEIGHT_PORTAL | float | 0.1 | Weight, portal | rt |
| health | HEALTH_THRESHOLD_EXCELLENT | float | 80.0 | Band threshold, Excellent | rt |
| health | HEALTH_THRESHOLD_GOOD | float | 60.0 | Band threshold, Good | rt |
| health | HEALTH_THRESHOLD_AT_RISK | float | 40.0 | Band threshold, At risk | rt |
| health | PROJECT_HEALTH_WEIGHT_SCHEDULE | float | 0.3 | Project health: schedule weight | rt |
| health | PROJECT_HEALTH_WEIGHT_BUDGET | float | 0.25 | Project health: budget weight | rt |
| health | PROJECT_HEALTH_WEIGHT_QUALITY | float | 0.2 | Project health: quality weight | rt |
| health | PROJECT_HEALTH_WEIGHT_VELOCITY | float | 0.15 | Project health: velocity weight | rt |
| health | PROJECT_HEALTH_WEIGHT_CLIENT | float | 0.1 | Project health: client weight | rt |
| health | PROJECT_HEALTH_TRAFFIC_GREEN | float | 70.0 | Green when score ≥ | rt |
| health | PROJECT_HEALTH_TRAFFIC_YELLOW | float | 45.0 | Yellow when score ≥ | rt |
| health | PROJECT_HEALTH_BUDGET_RATIO_GOOD | float | 0.8 | Budget ratio "good" when ≤ | rt |
| health | PROJECT_HEALTH_BUDGET_RATIO_OK | float | 1.0 | Budget ratio "ok" when ≤ | rt |
| health | PROJECT_HEALTH_BUDGET_RATIO_WARN | float | 1.2 | Budget ratio "warn" when ≤ | rt |
| semantic | SEM_THRESHOLD_EXPERT_CACHE | float | 0.92 | Semantic classifier: expert-cache hit threshold | rt |
| semantic | SEM_THRESHOLD_CRITICAL | float | 0.9 | Similarity band, critical | rt (key built as `SEM_THRESHOLD_{x}`) |
| semantic | SEM_THRESHOLD_HIGH | float | 0.72 | Similarity band, high | rt |
| semantic | SEM_THRESHOLD_MEDIUM | float | 0.58 | Similarity band, medium | rt |
| semantic | SEM_THRESHOLD_LOW | float | 0.45 | Similarity band, low | rt |
| semantic | SEM_WEIGHT_PROFILE | float | 0.4 | Assignment: profile-match weight | rt (global only) |
| semantic | SEM_WEIGHT_HISTORY | float | 0.6 | Assignment: history-match weight | rt (global only) |
| semantic | SEM_TOP_K_HISTORY | int | 3 | Assignment: top-K history items | rt (global only) |
| semantic | SEM_MULTI_ROLE_FACTOR | float | 0.7 | Assignment: multi-role factor | rt (global only) |
| password_policy | MIN_PASSWORD_LENGTH | int | 8 | Minimum password length | rt (`core/security.py`) |
| password_policy | PASSWORD_REQUIRE_UPPERCASE | bool | true | Require uppercase | rt |
| password_policy | PASSWORD_REQUIRE_LOWERCASE | bool | true | Require lowercase | rt |
| password_policy | PASSWORD_REQUIRE_DIGIT | bool | true | Require a digit | rt |
| password_policy | PASSWORD_REQUIRE_SPECIAL | bool | true | Require a special character | rt |
| password_policy | LOGIN_MAX_ATTEMPTS | int | 5 | Failed logins before lockout | **static**: `auth_service` reads `settings.LOGIN_MAX_ATTEMPTS`, so UI edits are ignored |
| password_policy | LOGIN_ATTEMPT_WINDOW_SECONDS | int | 900 | Counting window (s) | **static** (ignored) |
| password_policy | LOGIN_LOCKOUT_SECONDS | int | 900 | Lockout duration (s) | **static** (ignored) |
| locale | DEFAULT_TIMEZONE | str | `Europe/Madrid` | Default timezone | rt (`/org-defaults`, SLA, SD); many static reads too |
| locale | DEFAULT_LANGUAGE | str | `es` | Default language | rt (`/org-defaults`, SD mail); static elsewhere |
| locale | DEFAULT_CURRENCY | str | `EUR` | Default currency | rt in `/org-defaults` plus 1 site; static `settings.DEFAULT_CURRENCY` in ~44 files |
| locale | DEFAULT_TAX_RATE | float | 21.0 | Default tax rate (%) | rt **only** in `/org-defaults`; invoice/booking column defaults use the value loaded at process start |
| locale | DEFAULT_WORKING_HOURS_PER_DAY | float | 8.0 | Working hours per day | rt (`/org-defaults`, SD ticket ops); static elsewhere |
| locale | DEFAULT_WEEKLY_CAPACITY_HOURS | float | 40.0 | Weekly capacity (h) | rt only in `/org-defaults`; static in ~25 files (e.g. `alert_service`) |
| locale | DEFAULT_VACATION_DAYS_PER_YEAR | int | 23 | Vacation days per year | rt only in `/org-defaults`; policy/balance column defaults are static |
| locale | DEFAULT_IMPUTATION_LOCKOUT_DAYS | int | 14 | Days before time entries lock | **static**: `imputation_service` uses `organizations.imputation_lockout_days`, else `settings.*`, so UI edits are ignored |
| locale | DEFAULT_PROJECT_TYPE | str | `consulting` | Default project type | rt |
| locale | DEFAULT_BILLING_TYPE | str | `time_material` | Default billing type | rt |
| tokens | ACCESS_TOKEN_EXPIRE_MINUTES | int | 15 | Access-token TTL (min) | rt. Effective TTL = `min(EXPIRE, MAX)` |
| tokens | ACCESS_TOKEN_MAX_MINUTES | int | 30 | Upper cap for the access-token TTL | rt |
| tokens | REFRESH_TOKEN_EXPIRE_DAYS | int | 30 | Refresh-token TTL (days) | rt |
| key_rotation | KEY_ROTATION_ENABLED | bool | true | Automatic JWT and integration key rotation | rt (global only) |
| key_rotation | JWT_KEY_ROTATION_DAYS | int | 30 | JWT signing-key rotation period | rt (global only) |
| key_rotation | JWT_KEY_RETENTION_COUNT | int | 3 | Old JWT keys kept for verification | rt (global only) |
| key_rotation | INTEGRATION_SECRET_ROTATION_DAYS | int | 60 | Integration secret rotation period | rt (global only) |
| ai | CONTECFLOW_AI_MODEL | str | `claude-haiku-4-5` | Default LLM model | rt (`ai_client`, `ai_modules`) |
| ai | SEMANTIC_EMBEDDINGS_BACKEND | str | `tfidf` | Embeddings backend | rt (global only) |
| ai | OPENAI_STT_MODEL | str | `gpt-4o-mini-transcribe` | OpenAI speech-to-text model | rt |
| ai | AI_COST_ALERT_USD_PER_DAY | float | 10.0 | Daily AI cost alert (USD) | rt (global only) |
| ai | STT_PROVIDER | str | `openai` | Primary STT provider (openai, azure, google, whisper_local) | rt (via `stt/__init__._setting`) |
| ai | STT_FALLBACK_PROVIDERS | str | `''` | CSV of fallback STT providers | rt (same helper) |
| ai | AZURE_SPEECH_REGION | str | `westeurope` | Azure Speech region | rt |
| ai | AZURE_STT_LANGUAGE | str | `es-ES` | Azure STT language | rt |
| ai | GOOGLE_STT_LANGUAGE | str | `es-ES` | Google STT language | rt |
| feature_flags | M365_CALENDAR_SYNC_ENABLED | bool | false | "M365 calendar sync" | **display only**: read only by `GET /m365/status`; no endpoint is gated by it |
| feature_flags | M365_TEAMS_NOTIFICATIONS_ENABLED | bool | false | "M365 Teams notifications" | **display only** (same) |
| feature_flags | EXCHANGE_RATES_AUTO_UPDATE | bool | false | "Auto-update exchange rates" | **none**: no reader in `app/` |
| storage | S3_URL_EXPIRATION_HOURS | int | 24 | Presigned URL TTL (h) | rt (`s3_service`, collaboration files) |
| storage | MAX_FILE_SIZE_MB | int | 100 | Max document upload size (MB) | rt in `documents.py`; `core/uploads.py` reads `settings` (static) |
| security_network | TRUST_PROXY_HEADERS | bool | false | Trust `X-Forwarded-*` for the client IP | rt (global only) |
| security_network | TRUSTED_PROXY_CIDRS | str | `127.0.0.1/32,::1/128` | Proxies whose `X-Forwarded-*` are trusted | rt (global only) |
| ui_branding | WEBAUTHN_RP_NAME | str | `Contecflow PSA` | WebAuthn relying-party display name | rt (`auth_mfa`) |
| ui_branding | FRONTEND_EMBED_BASE_URL | str | `''` | Base URL for M365/BI embeds | rt (`m365_bi_embed_service`) |
| ui_branding | PROJECT_NAME | str | `Contecflow` | Product display name (TOTP issuer, PDFs) | rt |
| observability | METRICS_AUTH_TOKEN | str | None | Bearer token for `/metrics`; empty disables auth | rt (global only). **Stored and audited in plaintext** |
| timeouts | OUTBOUND_HTTP_TIMEOUT_SECONDS | float | 10.0 | Default timeout for outbound HTTP | rt via `outbound_http_timeout()` (24 call sites) |
| timeouts | OUTBOUND_AI_TIMEOUT_SECONDS | float | 30.0 | Default timeout for outbound AI calls | rt via `outbound_ai_timeout()` |
| ai | AI_PROVIDER_ERROR_COOLDOWN_SECONDS | int | 300 | A failing provider is set aside for (s), then retried | rt |
| ai | MCP_WRITE_MODE | str | `off` | MCP — tools that write: off (hidden), approval (a human approves each call) or direct | rt |
| automations | APPROVAL_EMAIL_LINK_HOURS | int | 72 | Approvals — hours the approve/reject link of the email is valid | rt |
| automations | AUTOMATIONS_DEADLINE_DAYS | int | 2 | "Task due soon": days before the due date | rt |
| automations | AUTOMATIONS_ENABLED | bool | true | Rules run on events and on the periodic scan (off: only the simulation) | rt |
| automations | AUTOMATIONS_EVENT_BATCH_SIZE | int | 200 | Events processed per run | rt |
| automations | AUTOMATIONS_EVENT_MAX_ATTEMPTS | int | 3 | Attempts per event before it is left as failed | rt |
| automations | AUTOMATIONS_MAX_CHAIN_DEPTH | int | 3 | A rule may trigger another one up to this depth | rt |
| automations | AUTOMATIONS_TIMESHEET_WEEKDAY | int | 5 | "Timesheet not submitted": from this weekday (ISO, 1=Mon … 7=Sun) | rt |
| automations | AUTOMATIONS_WEBHOOK_TIMEOUT_SECONDS | int | 10 | Webhook action — timeout (s) | rt |
| automations | BPMN_MAX_AUTOMATIC_STEPS | int | 500 | BPM — automatic steps in a row before an instance fails (loop guard) | rt |
| automations | NOTIFICATIONS_DIGEST_HOUR | int | 8 | Daily notice digest — local hour (0-23) from which it is emailed | rt |
| automations | NOTIFICATIONS_DIGEST_MAX_ITEMS | int | 20 | Daily notice digest — notices listed at most | rt |
| locale | SCENARIO_CAPACITY_ROLES | str | `pm,team_lead,employee,subcontractor` | Scenarios — roles whose capacity counts (comma separated) | rt |
| risk | RISK_BUDGET_OVER_FACTOR | float | 2.0 | Budget — points per % above 100 % | rt |
| risk | RISK_BUDGET_WARN_FACTOR | float | 3.0 | Budget — points per % above the warning | rt |
| risk | RISK_BUDGET_WARN_PCT | float | 85.0 | Budget — % spent where risk starts | rt |
| risk | RISK_CACHE_MINUTES | int | 60 | Scores are reused for (minutes) | rt |
| risk | RISK_DELAY_FACTOR | float | 0.8 | Delay probability — % per score point | rt |
| risk | RISK_DELAY_MAX_PCT | float | 95.0 | Delay probability — maximum (%) | rt |
| risk | RISK_DELAY_PCT_PER_WEEK | float | 20.0 | Predicted delay — probability % per week | rt |
| risk | RISK_HISTORY_POINTS | int | 12 | Detail — history points shown | rt |
| risk | RISK_LEVEL_CRITICAL | float | 75.0 | Risk score — critical from (0-100) | rt |
| risk | RISK_LEVEL_HIGH | float | 50.0 | Risk score — high from (0-100) | rt |
| risk | RISK_LEVEL_MEDIUM | float | 25.0 | Risk score — medium from (0-100) | rt |
| risk | RISK_POINTS_PER_HIGH_RISK | float | 25.0 | Resources — points per open high-probability risk | rt |
| risk | RISK_POINTS_PER_OPEN_CR | float | 20.0 | Scope — points per open change request | rt |
| risk | RISK_SCHEDULE_FACTOR | float | 1.5 | Schedule — points per % behind plan | rt |
| risk | RISK_WEIGHT_BUDGET | float | 0.3 | Risk score — weight of budget (0-1) | rt |
| risk | RISK_WEIGHT_RESOURCE | float | 0.15 | Risk score — weight of resources (0-1) | rt |
| risk | RISK_WEIGHT_SCHEDULE | float | 0.4 | Risk score — weight of schedule (0-1) | rt |
| risk | RISK_WEIGHT_SCOPE | float | 0.15 | Risk score — weight of scope (0-1) | rt |
| service_desk | SD_AUTONOMOUS_AGENT_ENABLED | bool | false | Autonomous agent — scan new tickets every 5 min (comments and may resolve) | rt |
| service_desk | SD_AUTONOMY_RESOLVE_THRESHOLD | float | 0.8 | Autonomous agent — confidence to resolve on its own (0-1) | rt |
| service_desk | SD_AUTONOMY_SUGGEST_THRESHOLD | float | 0.5 | Autonomous agent — confidence to comment a playbook (0-1) | rt |
| tenants | IMPERSONATION_ENABLED | bool | true | Platform support may sign in as a company user (with a reason, audited) | rt |
| tenants | IMPERSONATION_MAX_MINUTES | int | 30 | Sign in as — maximum session length (minutes) | rt |
| tenants | TENANT_DELETION_QUARANTINE_DAYS | int | 30 | Company deletion — quarantine before its data is erased (days) | rt |
| timeouts | AI_AGENT_TURN_TIMEOUT_SECONDS | int | 90 | NexusAgent — timeout per model turn (s) | rt |
| timeouts | AI_LOCAL_HTTP_TIMEOUT_SECONDS | int | 120 | Ollama (local model) call — timeout (s) | rt |
| timeouts | AI_MODELS_LIST_TIMEOUT_SECONDS | int | 30 | AI "Sync models" — timeout (s) | rt |
| timeouts | SSO_CLOCK_SKEW_SECONDS | int | 60 | SSO — clock skew tolerated when validating the id_token (seconds) | rt |
| timeouts | SSO_HTTP_TIMEOUT_SECONDS | float | 10.0 | SSO — timeout calling the identity provider (seconds) | rt |
| tokens | DEVELOPER_TOKEN_TTL_MINUTES | int | 60 | Developer-portal app token TTL (minutes) | rt |
| tokens | PASSKEY_PASSWORDLESS_ENABLED | bool | true | Allow signing in with a passkey alone (no password) | rt |

---

### Project templates — `/project-templates`
*Roles:* route `admin`, `pm`. Backend `require_any_manager`.

**Purpose.** Reusable project blueprints (phases → tasks, risks, deliverables) used to create new projects.

**How to use it.**
1. Open **Project Templates**.
2. **Create**: give a name, description, project type, estimated weeks and hours, then add phases with their tasks (title, hours, skill) and risks.
3. **Instantiate**: pick a template, then set the project name, start date and client. One project is created, with one phase per template phase and its tasks; phase dates are offset from the start date.

**Technical notes.**
- `GET /api/v1/billing-reports/templates`, `POST /api/v1/billing-reports/templates`, `POST /api/v1/billing-reports/templates/{id}/instantiate`.
- Tables `project_templates`, `template_phases`, `template_tasks`, `template_risks`, `template_deliverables`.
- Instantiation writes an audit entry `CREATE_FROM_TEMPLATE`.

**Limitations (measured).**
- There is **no update or delete endpoint** under `/billing-reports/templates`. The admin-only `DELETE /api/v1/advanced-config/templates/{id}` exists, but this page does not call it.
- Two other template APIs exist over overlapping tables, and this page uses neither:
  - `/advanced-config/templates` (same `project_templates` table);
  - `/templates/{id}/full|roles|documents` and `/templates/export` ("Templates Enhanced").

---

### Approval workflows (config) — `/settings/approval-workflows`
*Roles:* route `admin`, `pm`, `team_lead` (`ApprovalsPage mode="config"`). Every write is `require_admin`. Reads and analytics are any user or `require_any_manager`.

**Purpose.** Define multi-step approval flows per entity type, with approver groups, quorum, conditions, auto-approval rules, timeouts, chaining and versions.

**How to use it.** The config mode has seven tabs: Workflows, Templates, Simulator, Bottlenecks, Grupos, Carga, Matriz.
1. **Grupos**: create approver groups (members from `/users`, departments from `/settings/departments`).
2. **Workflows**: create a flow by choosing the entity type, a document category (for documents), the default flag, a chained workflow, SLA block-on-breach and auto-approval rules (JSON). Add steps (approver, group or manager, quorum, conditions), then **Validate** and **Publish**. Use **Clone version** to change a published flow.
3. **Templates**: create a flow from a predefined template.
4. **Simulator**: dry-run which flow and route a payload would take.
5. **Bottlenecks / Carga**: per-step delays and approver load.

**Technical notes.**
- `/api/v1/approvals/workflows[/{id}[/validate|/publish|/clone-version|/steps[/{step_id}]]]`
- `/api/v1/approvals/workflow-templates`, `/approvals/workflows/from-template`, `/approvals/simulate`
- `/api/v1/approvals/groups[/{id}]`
- `/api/v1/approvals/requests[/pending-my-action|/{id}/decide|/{id}/cancel|/{id}/financial-audit]`
- `/api/v1/approvals/stats`, `/approvals/analytics/{bottlenecks,approver-load}`, `/approvals/process-timeouts`
- Tables `approval_workflows`, `approval_steps`, `approval_groups`, `approval_requests`, `approval_decisions`, `financial_approval_audit_logs`.
- Timeouts are processed by the worker (`app/worker.py` → `process_approval_timeouts`).
- `/approval-workflows/builder/schema|validate` exist but no front-end code calls them.

**Limitations (measured).**
- **The final decision is propagated to the source entity only for `entity_type == "document"`** (`_apply_entity_final_decision`). The UI offers `timesheet` (form default), `expense`, `change_request`, `milestone`, `purchase`, `invoice`, `contract`, `budget`, `leave` and `deliverable`. For those types a request reaches "approved" but **nothing on the entity changes**. An event is emitted (`_emit_decision_event`); whether any module reacts to it is **Not verified**.
- Requests are created automatically only for documents (by category: `documents_service`) and in client-portal flows. Every other request has to be created explicitly with `POST /approvals/requests`.
- **Self-approval is always blocked** (403 "SoD"), whatever the SoD rules say; see [GRC](#grc--sod-matrix--grc).

---

### Project workflows — `/settings/project-workflows`
*Roles:* route `admin`, `pm`. Writes need `require_admin_or_pm`. The task transition needs `require_internal_user`. `/settings/workflows` and `/workflows` redirect here.

**Purpose.** A per-project status workflow: states, plus allowed transitions with an optional required role and a mandatory comment.

**How to use it.**
1. Select a project.
2. **Init** creates the default states. **Reset** soft-deletes everything and recreates the "standard Scrum" set.
3. Add or edit states (name, value, color, initial/final, order).
4. Add transitions (from → to, label, `required_role`, `requires_comment`).

**Technical notes.** `GET /api/v1/project-workflows/{project_id}`; `POST …/init`; `DELETE …/reset`; `POST|PATCH|DELETE …/states[/{id}]`; `POST|DELETE …/transitions[/{id}]`; `POST …/tasks/{task_id}/transition`. Tables `workflow_states`, `workflow_transitions`.

**Limitations (measured).**
- **Transitions are enforced only by `POST /project-workflows/{pid}/tasks/{tid}/transition`, and no front-end code calls it** (grep for `transitionTask`: only the API client). Tasks change status through the normal task update, which does not consult `workflow_transitions`. As shipped, the workflow is a definition, not a constraint.

---

### Issue types — `/issue-types`
*Roles:* route `admin`, `pm`. Writes need `require_admin_or_pm`.

**Purpose.** A per-project catalogue of issue types.

**How to use it.**
1. Select a project.
2. **Init** creates the 7 system types: `story`, `task`, `bug`, `improvement`, `epic`, `subtask`, `spike`.
3. Add or edit types (name, value, icon, color, subtask flag, order) and their fields. The page also lists the project's custom fields.

**Technical notes.** `GET|POST /api/v1/issue-types/{project_id}`, `POST …/init`, `PATCH|DELETE …/{type_id}`. Tables `issue_types`, `issue_type_fields`. The same router also serves `/task-dependencies`, `/epic-dependencies` and `/fts/*`.

**Using it in tasks (since 2026-11-03).** The task detail (Tasks → open a task → edit) has a *Tipo de incidencia* select fed by the project's catalogue. `POST /tasks` and `PATCH /tasks/{id}` accept and return `issue_type`. A value outside the project's active catalogue is rejected with 422; a project without its own catalogue accepts the 7 system values.

**Limitations (measured).** The per-type fields (`issue_type_fields`) are not shown in the task form.

---

### Custom fields — `/custom-fields`
*Roles:* route `admin`, `pm`. Writes need `require_admin_or_pm`. Saving values needs `require_internal_user`.

**Purpose.** Per-project extra fields on tasks.

**How to use it.**
1. Select a project.
2. Add a field: name, `field_key`, type (`text`, `number`, `date`, `select`, `url`, `user`, `boolean`), options for `select`, required, show-in-list, order.
3. The values are edited in the task detail on the Tasks page (`customFieldsApi.getValues` / `setValues`).

**Technical notes.** `GET|POST /api/v1/custom-fields/{project_id}`, `PATCH|DELETE …/{field_id}`, `GET|POST …/values/{task_id}`. Tables `project_custom_fields`, `project_custom_field_values`.

**Limitations (measured).**
- The server does **not** validate `is_required` or `field_type` when values are saved; `custom_fields_service` has no check.
- This is separate from Settings → **Campos extra** (`custom_fields` / `custom_field_values` under `/advanced-config/custom-fields`), which has no consumer.

---

### Project permissions — `/project-permissions`
*Roles:* route `admin`, `pm`. Writes need `require_admin_or_pm`.

**Purpose.** Grant users a per-project level (`none`, `viewer`, `member`, `manager`, `owner`) and the flags `can_see_financials`, `can_see_rates`, `can_export`.

**How to use it.** Select a project, add a user with a level and flags, then edit or revoke.

**Technical notes.**
- `GET|POST /api/v1/permissions/{project_id}`, `PATCH|DELETE …/{permission_id}`.
- The duplicate API `/api/v1/enterprise/project-permissions/{project_id}[/{id}]` works on the same table, `project_permissions`.

**How it is enforced (since 2026-11-03, `app/core/permisos_de_proyecto.py`).** On every request with `{project_id}` in its route, an active, non-expired row for that person and project applies:
- `none`: 403, and the project disappears from their project list;
- `viewer`: read only (GET/HEAD/OPTIONS);
- `member`, `manager`, `owner`: whatever the base role already allows;
- `can_see_financials = false`: EVM, profitability, revenue and budget routes of the project → 403;
- `can_export = false`: export routes of the project → 403.
A `viewer` (or higher) row also makes the project appear in the list of a PM or employee who would not see it by role. Admins are never restricted.

**Limitations (measured).**
- A level never grants more than the base role: an employee who is `manager` of a project still cannot do PM-only actions.
- `can_see_rates` has no project route to apply to; it is still not enforced.
- Routes that identify the project only through another record (for example a task id) are not checked against this table; the task's own rules apply.

---

### E-signature (DocuSign / Adobe Sign) — `/esign`
*Roles:* route `admin`, `pm`.
- Create, provider OAuth and config: `require_admin`.
- List, stats, detail, status and signer updates, void: authenticated users, with creator-or-manager checks.

**Purpose.** Signature requests ("envelopes") on stored documents, through DocuSign, Adobe Sign, or **manual** mode (state is tracked in the app only).

**How to use it.**
1. **Configure.** Go to Settings → E-firma, or `PATCH /esign/config`. Enter the DocuSign integration key, secret, account id and base URL, and/or the Adobe Sign client id, secret and base URL.
2. **Get a token.** Run the OAuth flow (`/esign/auth/{docusign|adobe}/authorize` → `callback`), or paste a token (`POST /esign/auth/{provider}/store-token`).
3. **Register webhooks** in the provider:
   - DocuSign Connect → `POST /api/v1/esign/webhooks/docusign`, HMAC verified with env `DOCUSIGN_CONNECT_HMAC_KEY`.
   - Adobe → `GET|POST /api/v1/esign/webhooks/adobe`, verified with the `X-AdobeSign-ClientId` header.
4. On `/esign`, create a request: pick a document, add signers (name, email, routing order), choose the provider, and set subject, message and expiry.
5. Track status. In manual mode, mark signers as signed by hand.

**Technical notes.**
- Envelope endpoints: `GET|POST /api/v1/esign`, `GET /esign/summary/stats`, `GET|DELETE /esign/{id}`, `PATCH /esign/{id}/status`, `PATCH /esign/{id}/signers/{sid}/signed`.
- Config: `GET|PATCH /esign/config` (secrets returned as `***`).
- Tables `esign_envelopes`, `esign_signers`.
- Provider config and tokens are stored in `app_settings` under keys `esign.*`, with env `DOCUSIGN_*` / `ADOBE_SIGN_*` as fallback (`app/core/config.py`).
- The provider calls live in `app/services/esign_providers.py`. Without configuration, envelopes fall back to manual mode.

**Limitations (measured).**
- ~~The `esign.*` secrets are stored in plaintext in `app_settings`.~~ Fixed 2026-11-03: integration key, secret, client id and client secret are stored encrypted (`v2:`) and decrypted on read; values saved before are encrypted by migration 117, and an old plain value is still readable. Account id and base URLs stay in clear.
- **The Credenciales → DocuSign / Adobe Sign providers are not read by e-sign.**
- A PM can open the page but cannot create a request (`require_admin`).
- A real round trip with DocuSign or Adobe is **Not verified**.

---

### Microsoft 365 — `/m365`
*Roles:* route `admin`.
- `GET /m365/status`: any user.
- Calendar, Teams and Planner actions: `require_admin`.
- Presence: any user.

**Purpose.** Microsoft Graph (app-only, client credentials) for calendar events and milestones, Teams notifications by incoming webhook, Planner task sync, and user presence.

**How to use it.**
1. **Set env vars:** `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` and optionally `TEAMS_WEBHOOK_URL`, then restart. The status card shows which of them are present.
2. **Pull calendar:** enter a user UPN and a number of days. This calls `GET /users/{upn}/calendarView`.
3. **Sync milestones** to a calendar.
4. **Teams notify:** title, text and color, posted to the webhook given in the body or to `TEAMS_WEBHOOK_URL`.

**Technical notes.**
- Calendar: `POST /api/v1/m365/calendar/sync?user_upn=&days=`, `POST|DELETE /m365/calendar/events[/{id}]`, `POST /m365/calendar/sync-milestones`.
- Teams: `POST /m365/teams/notify`, `POST /m365/teams/notify-project`, `POST /m365/teams/webhooks/incoming`.
- Other: `GET /m365/users/presence?upns=`, `POST /m365/planner/tasks/sync` (needs `plan_id`).
- The service is `app/services/m365_service.py`. No tables of its own.

**Limitations (measured).**
- **The credentials come from env only.** `m365_service.m365_configured()` and the token requests read `settings.AZURE_*`; Settings → Credenciales → Microsoft 365 / Graph is ignored here (it is used only by the Service Desk Graph mailbox).
- The feature flags `M365_CALENDAR_SYNC_ENABLED` and `M365_TEAMS_NOTIFICATIONS_ENABLED` are **only echoed by `/m365/status`**; nothing checks them.
- The page uses status, calendar sync, milestone sync and Teams notify. Presence, Planner and event create/delete are **API-only**.
- Graph calls need tenant consent for the required application permissions. **Not verified.**

---

### Data import — `/import`
*Roles:* route `admin`, `pm`. Backend `require_any_manager`.

**Purpose.** Bulk CSV import of projects, tasks, users, imputations (time entries) and expenses.

**How to use it.**
1. Choose the entity type.
2. Download the template. Its columns:
   - **projects**: `code, name, client_name, project_type, status, start_date, end_date_planned, budget_amount, billing_type, pm_email`
   - **tasks**: `project_code, title, description, status, priority, assignee_email, due_date, estimated_hours, story_points`
   - **users**: `username, email, full_name, first_name, last_name, role, department, job_title, weekly_capacity_hours, hourly_rate`
   - **imputations**: `user_email, project_code, date, hours, description, is_billable, work_type`
   - **expenses**: `user_email, project_code, category, description, amount, currency, expense_date, is_billable`
3. Upload the CSV (UTF-8, header row, at most 5 MB) and click **Validate**.
4. Click **Execute**. Rows import individually: valid rows are created and failed rows are reported, with the job keeping the first 50 errors.
5. Review the history.

**Technical notes.** `GET /api/v1/billing-reports/import/template/{entity_type}`, `POST /billing-reports/import/validate?entity_type=` (multipart), `POST /billing-reports/import/execute?entity_type=`, `GET /billing-reports/import/jobs`. Table `import_jobs`. Uploads are checked by `read_and_validate_upload_sync(…, UploadProfile.CSV_IMPORT)`.

**Limitations.**
- **Imported users get a random password** (`secrets.token_urlsafe(24)`) and need a password reset.
- Execution is synchronous within the request.
- Behaviour on very large files is **Not verified**.

---

### MFA — `/mfa`
*Roles:* route: any authenticated user (sidebar: admin, pm, hr, employee, team_lead). Backend `get_current_user`.

**Purpose.** Self-service TOTP enrollment with backup codes.

**How to use it.** Click **Setup** (QR and secret appear), scan it with an authenticator app, enter a code to **Verify**, and store the backup codes. **Disable** requires a valid code.

**What happens at sign-in.** Once verified, every sign-in with the password asks for a 6-digit code. A backup code can be typed instead of the code; each backup code works once. **Disable** removes the factor and sign-in no longer asks for it (unless the user has passkeys).

**Technical notes.** `GET /api/v1/mfa/status`, `POST /mfa/setup`, `POST /mfa/verify`, `POST /mfa/validate`, `DELETE /mfa/disable`. Tables `mfa_configs` (`totp_secret` encrypted) and `mfa_backup_codes`. Requires `pyotp` and `qrcode`. The QR is a local `data:image/png` (nothing is sent to a third party).
- Sign-in (`routers/auth_core.py`) checks `users.mfa_enabled AND users.mfa_secret`, or passkeys. Since 2026-11-03 `mfa_service.verify_and_activate_mfa` copies the encrypted secret to `users.mfa_secret` and sets `users.mfa_enabled`; `disable_mfa` clears it (keeping `mfa_enabled` if passkeys exist). `/auth/mfa/validate` also accepts unused `mfa_backup_codes`. `/auth/mfa/disable` also turns `mfa_configs.is_enabled` off. Test: `tests/test_mfa_pantalla_protege_login.py`.

**Limitations (measured).**
- Two endpoint families still exist (`/mfa/*` for this page and `/auth/mfa/*`); they now write the same fields, but enrolling through `/auth/mfa/setup` creates no backup codes and leaves this page showing "not enabled".
- **Passkeys (since 2026-11-04).** Profile → Seguridad → *Passkeys*: add one (browser prompt: fingerprint, Face ID, security key), rename ✏ or remove 🗑. Registration asks for a discoverable credential when the authenticator can (`residentKey: preferred`) and always requires user verification.
  - **Sign in with a passkey alone:** *Entrar con passkey* on the login page (`POST /auth/passkey/login/start|finish`) needs no user name or password; the passkey identifies the user. Because user verification is required it counts as two factors, so no TOTP follows. It can be switched off with `PASSKEY_PASSWORDLESS_ENABLED` (Settings → Tokens). Before, the button sent the user name with an **empty password** to `/auth/login`: always 401, and a failed attempt counted towards lockout.
  - **Passkey as second factor:** after the password or SSO, the second-factor step shows *Usar mi passkey* when the user has one. Backup codes (8 characters) can now be typed there; the field used to accept only 6 digits, so they could not be used from the screen.
  - Endpoints: `/auth/mfa/webauthn/register/start|finish`, `GET /auth/mfa/webauthn/credentials`, `PATCH|DELETE /auth/mfa/webauthn/credentials/{id}`.
  - Not verified with a physical authenticator: the browser ceremony was checked with mocks (`frontend/src/__tests__/LoginSsoPasskey.test.tsx`); the server checks with a simulated credential.
- The front end still has no screen for `/auth/mfa/setup` / `/auth/mfa/verify-setup` (the `/mfa` page uses the older `/mfa/*` endpoints).
- If an organization sets `require_mfa=true`, **which is API-only** (`PATCH /organizations/{id}`), users without a TOTP factor or passkey are refused at login with 403.

---

### GRC / SoD matrix — `/grc`
*Roles:* route `admin`.
- Reads (`permissions`, `sod-rules`, `sod-check`, `violations`): `require_any_manager`.
- Writes and `audit-log`: `require_admin`.

**Purpose.** Two controls: a role × module × action permission matrix that is enforced on every request, and segregation-of-duties (SoD) rules with violation tracking.

**Per company (revision 2026-11).**
- **Measured before:** the 2364 cells of the matrix were stored without a company, and were read and written trusting the session filter.
  - A company administrator saw an empty matrix.
  - Each visit seeded it again, because the count was 0.
  - Changes went to rows that the request check might not read, or that applied to other companies.
- **Now:**
  - The rows without a company are the **global defaults**, seeded once and extended with new modules.
  - A company stores only its **exceptions**, and they win over the defaults.
  - Read, change, reset and the per-request check (`grc_enforce`, with the session's company from the token) all name the company explicitly.
  - *Restablecer* removes the company's exceptions, and the defaults apply again.
  - SoD rules are seeded per company (`ensure_sod_seeded(…, organization_id)`), so editing one never touches another company.
- **Measured on a copy with the application role:** a PM sees the 2364 cells and a second visit adds none. The admin's exception is stored for the company only and the global row is unchanged.

**How to use it.**
1. **Matrix.** The first load seeds a default matrix and fills in a row for every API module derived from the router. Toggle `allowed` per role, module and action. The actions are `ver`, `crear`, `editar`, `eliminar`, `aprobar`, `exportar`; the action of a request is derived from its HTTP method and path. **Seed** resets the matrix to the defaults.
2. **SoD rules.** Edit or create pairs `(module_a, action_a)` ⟂ `(module_b, action_b)` with a risk level, the conflicting roles, and an optional mitigating workflow. 8 defaults are seeded (invoices, expenses, contracts, resources/timesheets, hr, settings/approvals, timesheets, grc/approvals).
3. **SoD check.** Lists the roles whose matrix allows both sides of an active rule.
4. **Violations.** Review violations and resolve them with a note.
5. **Audit log.** GRC events.

**Technical notes.**
- `GET /api/v1/grc/permissions`, `PATCH /grc/permissions/{role}/{module}/{action}`, `POST /grc/permissions/seed`
- `GET|POST /grc/sod-rules`, `PATCH|DELETE /grc/sod-rules/{id}`
- `GET /grc/sod-check`, `GET /grc/violations`, `PATCH /grc/violations/{id}/resolve`, `GET /grc/audit-log`
- Tables `grc_role_permissions`, `grc_sod_rules`, `grc_sod_violations`, `grc_audit_log`.
- Enforcement is in `app/core/grc_enforce.py::enforce_grc_matrix`, a router-level dependency:
  - `allowed=false` → 403.
  - `allowed=true` or no row → the other checks continue.
  - Superadmins are never blocked.
  - `admin` cannot lose read access to `grc`.
  - Unauthenticated, portal, signed-webhook, SCIM and WebSocket prefixes are exempt.

**Limitations (measured).**
- The matrix can **only deny**. Allowing a cell never grants more than RBAC already does.
- **SoD rules do not block anything.** They are detective:
  - `sod-check` is a report over the matrix.
  - Violations are recorded only when a requester tries to approve their own approval request, and that case is blocked by a hard-coded check in the approval engine whatever the rules say.
  - No other code path consults `grc_sod_rules`.

---

### Organizations — `/organizations`

**Since 2026-11-05 (multitenant review):**
- **Creating a company creates its first administrator** when an admin email is given (optional name). The initial password is shown once in a dialog; there was no way to enter a new company before.
- **Suspending asks for a reason**, stored in `suspension_reason` (migration 127) and shown in the list; reactivating clears it. Suspension cuts every session of that company on its next request.
- **Plan limits are enforced**: creating a user or a project answers 409 when the company has reached `max_users` / `max_projects` (they were only checked when assigning an existing user). Users count by their own record or membership. The list shows usage against each limit, in red when reached.
- **Own domain** (`domain`) for the `subdomain` entry mode, unique across companies.
- **Permanent deletion** (`app/services/baja_de_empresa_service.py`): «Dar de baja» asks for a reason, suspends the company at once and opens a quarantine of `TENANT_DELETION_QUARANTINE_DAYS` (30). During it the deletion can be undone and all its data downloaded as a ZIP (one JSON per table, without password hashes or MFA secrets). A daily job (02:40, APScheduler and Celery beat) then erases everything in one transaction: its rows in every table, rows outside it that point to its data (emptied when the column allows NULL, deleted otherwise), and the company. Users who also belong to another company keep their account and move there; a superadmin living in it moves to another company (refused if none is left). Measured on a copy of the real database: 777 rows in 99 tables in 2.2 s, nothing left with that organization, superadmin kept.
- **«Entrar como»** (sign in as a company user, for support): superadmin only, with a reason, switchable off (`IMPERSONATION_ENABLED`) and limited to `IMPERSONATION_MAX_MINUTES` (30). It is written to the company's own audit log (`IMPERSONATION_START`). During it, password, MFA, passkey, API key, SSO, company and developer-app routes answer 403, and a banner shows who is inside; «Salir» uses the superadmin's refresh cookie to return to their own session.
- Not built: a platform-wide audit view of these actions (they are in each company's audit log).
*Roles:* route `admin`. **Backend `require_superadmin` on every endpoint**, so a non-superadmin `admin` sees the menu entry but gets an error from the API.

**Purpose.** Tenant CRUD and user assignment. For the isolation model, see [Multi-tenant model](#multi-tenant-model-how-organizations-isolate-data).

**How to use it.**
1. **Create.** Enter name, slug (`[a-z0-9-]`, 2–60 chars), plan (`starter`, `pro`, `enterprise`), max users, max projects, admin email, timezone, locale and color.
2. **Edit.** The same fields, plus `is_active`, `logo_url` and `require_mfa`. `require_mfa` is **API-only**; the form does not show it.
3. **Assign or remove users.**

**Technical notes.** `GET|POST /api/v1/organizations`, `GET|PATCH /organizations/{id}`, `POST /organizations/{id}/assign-user`, `DELETE /organizations/{id}/remove-user/{user_id}`. Tables `organizations` (`_tenant_exempt`) and `user_organization_memberships`. Changes to `require_mfa` are audited.

**Limitations (measured).**
- `max_users` is checked in `assign-user` (`check_org_user_limit`) and, since 2026-11-04, when SSO creates a user. It is not checked when users are created through `/users` or SCIM.
- **`max_projects` and `plan` have no enforcement anywhere** (grep).
- **`organizations.is_active=false` does not block password login.** It is checked only by SSO auto-provisioning, SCIM, the worker and ML training.
- `assign-user` sets `users.organization_id` only if it was empty. A second membership does not change the user's tenant (see the multi-tenant model).

---

### Enterprise — `/enterprise`
*Roles:* route `admin`. The tabs are Webhooks, GDPR, Email, Integraciones, SSO, Auditoría and API Keys.

**Purpose.** Grab-bag of enterprise administration.

**How to use it / technical notes per tab.**

**Webhooks.** These are **incoming** webhook triggers, the same data as [Webhook log](#webhook-log--webhook-log).

**GDPR.**
- Create erasure or portability requests and process them.
- Endpoints: `GET|POST /api/v1/gdpr/requests`, `POST /gdpr/requests/{id}/process`.
- Erasure calls `_gdpr_erase_user`; portability exports the user's data as JSON.

**Email.**
- Send an email, manage templates, view logs.
- Endpoints: `GET|POST /api/v1/email/templates`, `POST /email/send`, `GET /email/logs`.
- Uses SMTP (`smtp` credentials / env).

**Integraciones.**
- Generic integration records: `GET|POST /api/v1/oauth-integrations`, `DELETE /oauth-integrations/{id}`, `POST /oauth-integrations/{id}/sync`.
- Table `integration_configs`, with secrets in the config JSON encrypted (`decrypt_config_secrets`).
- Catalogue: slack, teams, jira, github, google_calendar, xero, quickbooks.
- Test buttons call `POST /api/v1/integrations-hub/{slack|teams|jira}/test`.

**SSO (OpenID Connect; reviewed and fixed 2026-11-04).**
- Providers: Azure AD / Entra ID, Okta, Google Workspace, generic OIDC. **SAML is not offered**: it was listed but never implemented (every SAML callback returned 503), and contecintelligence, the reference, has no SAML either. Creating a SAML provider returns 422.
- **Configure it** (Enterprise → SSO → *Añadir proveedor*):
  1. Register Contecflow in the IdP with redirect URI **`<app origin>/login`** (the tab shows the exact value; before, it showed a `/auth/sso/callback` path that does not exist).
  2. Fill in provider, button name, client id and secret, discovery URL, scopes, allowed e-mail domains (empty = any), role for new users, groups claim (default `groups`) and the *IdP group = role* mapping, one per line. Tick *Crear el usuario en su primer acceso* to provision on first sign-in, and *Activo* to show the button.
  3. Each card has *Activar/Desactivar*, ✏ (edit; leave the secret empty to keep it), *Verificar config* and 🗑.
- **Sign-in:** the login page lists active providers (`GET /auth/sso/providers`; it returned an empty list before because it read a column that did not exist). The button calls `/auth/sso/{id}/authorize`; the IdP returns to `/login?code=…&state=…`, and the page now exchanges the code (`POST /auth/sso/{id}/callback`). Before, nothing exchanged it, so no SSO sign-in could complete. If the user has TOTP or passkeys, the second-factor step follows.
- **Checks on the id_token:** JWKS signature (RS/ES/PS 256-512; the JWKS client is reused), audience, expiry, **issuer** (from the discovery document; Azure multi-tenant issuers with `{tenantid}` are not compared literally), `nonce`, PKCE S256, one-time HMAC `state`, `email_verified`, and clock skew `SSO_CLOCK_SKEW_SECONDS` (60). Timeouts: `SSO_HTTP_TIMEOUT_SECONDS` (10). Both in Settings → Timeouts. The callback and authorize are rate-limited (`SSO_RATE_LIMIT`, `20/minute`, environment).
- **Users:** looked up by e-mail **within the provider's organization**; an e-mail that belongs to another organization is refused (409). The e-mail domain must be in *allowed domains* if set (403). New users are created in the provider's organization (the organization's user limit applies) with the mapped role or the default role. **The role is re-synchronized from the groups on every sign-in** when a mapping exists (the most privileged match wins; a superadmin is never changed). Existing users of an inactive organization are refused. `/auth/me` returns `sso_provider`, so the profile shows "your account uses SSO" instead of the password form.
- Admin endpoints: `GET|POST /api/v1/enterprise/sso`, `PATCH|DELETE /enterprise/sso/{id}` (PATCH is partial; before, it required `provider` and nothing could be switched on), `POST /enterprise/sso/{id}/test`. Table `sso_configs` (+ `name`, `groups_claim`, migration 122).
- The second, broken SSO under `/bookings/sso/*` (unauthenticated, read columns that do not exist) was removed.
- Compared with contecintelligence (2026-11-04): it has OIDC by id_token POST only, no authorize/redirect flow, no SAML and no passkeys. Contecflow now covers everything it has (issuer check, algorithm set, clock skew, group → role mapping with re-sync, tenant-scoped JIT with seat limit, inactive-organization check, rate limit) and more.
- Not verified against a real IdP: only with a simulated IdP that signs real RS256 tokens (`tests/test_sso_oidc_y_passkeys.py`). The Okta token URL is built as `{issuer}/v1/token`, which fits custom authorization servers; org-level Okta issuers may need the generic OIDC type.

**Auditoría.** `GET /api/v1/enterprise/audit-log`. The UI shows the general log and password-reset events.

**API Keys.**
- Endpoints: `GET|POST /api/v1/bookings/api-keys` (create: `require_any_manager`), `DELETE /bookings/api-keys/{id}`. Table `api_keys`: bcrypt hash, SHA-256 `key_digest` (migration 119) and the visible prefix. The key (`nxpm_…`) is shown once.
- **Using a key:** send `X-API-Key: nxpm_…` (or `Authorization: Bearer nxpm_…`) to any endpoint. The key acts **as its owner** (role and organization) and its scopes cut it down:
  - `read`: GET/HEAD/OPTIONS only; `write` or `admin`: also writes;
  - area scopes `projects`, `tasks`, `timesheets`, `billing`, `expenses`: read and write inside `/api/v1/<area>` (timesheets also `/imputations`; billing `/invoices` and `/billing-reports`) and nothing else.
  - Unknown scopes are rejected with 422.
- **Never valid for managing credentials:** `/auth/*` (except `GET /auth/me`), `/mfa`, `/bookings/api-keys`, `/developer/apps`, `/enterprise/sso`, `/bookings/sso` → 403.
- Per-key limits `rate_limit_per_hour` / `rate_limit_per_day` return 429; the counters reset each hour and each day (before, they never reset). Expired or revoked keys → 401.
- Keys created before migration 119 get their digest the first time they are used (one bcrypt check by prefix).
- `POST /bookings/api-keys/verify` (unauthenticated) uses the same check and counts as a use.

**Limitations (measured).**
- **`/oauth-integrations/{id}/sync` calls the real services** (since 2026-11-04, `cab_service.sync_*`; it used to be simulated and invent data):
  - **github**: reads the repository's last 50 pull requests (`GET /repos/{repo}/pulls`) and processes each one like the webhook does (`git_service.handle_github_pr`): it records the PR, links it to the task named in the branch or title, and a merged PR closes its task. **gitlab** has no pull sync: it works through the Git webhook.
  - **google_calendar**: publishes every sprint with dates as an all-day event in the configured calendar; later syncs update the same event (by Google's id) instead of duplicating it. **outlook** goes through Microsoft 365.
  - **quickbooks/xero**: sends the sent invoices not yet synced, with the same code as Accounting → bulk push.
  - **jira**: brings each linked issue's status into its task (Done, In Progress, To Do, In Review).
  - **slack/teams**: there is nothing to sync; the button answers 400 and points to "Probar".
  - If the provider fails and nothing was synced, the call answers 400 with the provider's error (it used to say "Sincronización completada").
  - Migration `124_integraciones_reales` deletes the commit links and calendar events the old simulation had invented.
  - Not verified against the real GitHub, Google, Xero, QuickBooks or Jira: the tests replace them with doubles (`tests/test_integraciones_reales.py`).
- **Secrets were read encrypted** (fixed 2026-11-04). Integration secrets (`access_token`, `api_token`, `webhook_url`) are stored encrypted, and three readers used them without decrypting: Slack/Teams event notices, the automations' Slack/Teams actions, and Accounting's Xero/QuickBooks calls. They now decrypt.
- SAML is not implemented and no longer offered (see SSO above).
- **Outbound webhooks** (`/api/v1/enterprise/webhooks[/{id}[/test|/deliveries]]`, `/enterprise/webhooks/events`; tables `webhooks`, `webhook_deliveries`) are **API-only**: no screen calls them. Delivery happens in `app/worker.py`, signed with HMAC (`services/webhooks._sign_payload`) and re-checked against SSRF at send time. It requires the worker to be running.

---

### Webhook log — `/webhook-log`
*Roles:* route `admin`.
- List and logs: `require_any_manager`.
- Create, rotate, delete: `require_admin`.

**Purpose.** Incoming webhook triggers. An external system POSTs to a per-trigger URL to start an automation workflow, and every call is logged.

**How to use it.**
1. Create a trigger (in Enterprise → Webhooks, or via the API) with a name, slug, **secret** and `workflow_id` (an automation workflow).
2. Give the caller the URL `POST /api/v1/webhooks/fire/{slug}` and the secret. The caller must send the header `X-Contecflow-Signature: sha256=<hex HMAC-SHA256(secret, raw body)>`.
3. On `/webhook-log`, select a trigger to see its calls.

**Technical notes.**
- `GET|POST /api/v1/webhooks`, `GET /webhooks/{id}/logs`, `POST /webhooks/{id}/rotate`, `DELETE /webhooks/{id}`.
- Public `POST /webhooks/fire/{slug}`, rate-limited to 20/min.
- Tables `webhook_triggers`, `webhook_trigger_logs`.

**Limitations (measured).**
- A trigger **without a secret is never callable** (401).
- Only `workflow_id` is executed. It runs as a background task after the response; `rule_id` and `field_mapping` are stored but not used by the fire handler.
- **All request headers are written to the log** (`json.dumps(dict(request.headers))`).

---

### Jira integration — `/jira-integration`
*Roles:* route `admin`, `pm`.
- Config read and write: `require_admin`.
- Test, issues, sync, push, linked: `require_any_manager`.

**Purpose.** Jira Cloud (REST v3, email + API token over HTTP Basic). It pulls issues into tasks and pushes tasks to Jira.

**How to use it.**
1. Enter the Jira URL, email, API token and project key, then save.
2. Click **Test**.
3. **Browse issues.**
4. Run **Sync** (Jira → tasks: create or update by `jira_issue_key`).
5. Run **Push** for a project (creates missing issues).
6. Optionally register the Jira webhook → `POST /api/v1/jira/webhook`. It is verified with env `JIRA_WEBHOOK_SECRET`.

**Technical notes.**
- `GET|POST /api/v1/jira/config`, `GET /jira/test`, `GET /jira/issues`, `POST /jira/sync`, `POST /jira/push?project_id=`, `GET /jira/linked`, `POST /jira/webhook`.
- Config is stored in `app_settings` (`jira_url`, `jira_email`, `jira_api_token` (encrypted), `jira_project_key`), per organization with a global fallback.

**Limitations (measured).**
- **Three separate Jira integrations exist, with separate configuration:**
  1. this page (`/jira/*`, `app_settings`);
  2. Service Desk `/api/v1/integrations/jira/configs[/{id}[/test|/sync-log]]`, `/integrations/jira/sync/{config_id}`, `/integrations/jira/tickets/{id}/push`, with tables `sd_jira_configs`, `sd_jira_field_map`, `sd_jira_sync_map` and `sd_jira_sync_log`;
  3. `/api/v1/integrations-hub/jira/{test,issues,search,transition}`, which uses `integration_configs`.
- The Exports page calls `POST /integrations/jira/sync/{projectId}`, but that route expects a **config id**.
- The module docstring mentions `GET /jira/sync-log`, but that route does not exist.
- A real Jira round trip is **Not verified**.

---

### Public forms — `/public-forms`
*Roles:* route `admin`, `pm`. Create, update and delete need `require_admin_or_pm`. The public endpoints are anonymous.

**Purpose.** Anonymous intake forms that create Service Desk tickets.

**How to use it.**
1. Create a form: name, description, type, active, target project, target group, default priority and category, success message, notify emails.
2. Copy its public link. The front end renders it at `/intake/:token` (`IntakeFormPage`, no login).
3. Review submissions per form.

**Technical notes.** `GET|POST /api/v1/forms`, `GET|PATCH|DELETE /forms/{id}`, `GET /forms/{id}/submissions`. The public endpoints are `GET /forms/public/{token}` and `POST /forms/public/{token}/submit` (rate limit 10/min per client). Tables `public_forms`, `public_form_submissions`. A submission creates a `Ticket` of type `incident` with `source="public_form"`, numbered within the form's organization.

**Limitations (measured).**
- **`form_type="task"` creates no entity.** Only `"ticket"` is handled; any other type saves just the submission.
- **`notify_emails` is stored but never used to send email** (no reader).
- If ticket creation fails, the submission is still saved and returns `ticket_id: null`; the failure only goes to a log warning.

---

### Developer portal — `/developer`
*Roles:* route `admin`, `pm`. Writes need `require_admin_or_pm`. Each user sees their own apps.

**Purpose.** Register OAuth2 client applications and obtain tokens.

**How to use it.**
1. Create an app: name, description, homepage, redirect URIs (one per line), and scopes from `read`, `write`, `projects`, `tasks`, `timesheets`, `billing`, `admin`.
2. **Copy the client secret now.** It is shown once.
3. **Rotate the secret** if needed.
4. Request a token with `POST /api/v1/developer/token`, body `{grant_type:"client_credentials", client_id, client_secret, scope:"read …"}`. The response carries `access_token` and `expires_in` (`DEVELOPER_TOKEN_TTL_MINUTES`, default 60, Settings → Tokens).
5. Call the API with `Authorization: Bearer <access_token>`. The token acts as the app owner, with the same scope rules and forbidden paths as API keys (see Enterprise → API Keys). `GET /developer/userinfo` returns the owner; `POST /developer/token/revoke` revokes it.

**Technical notes.** `GET|POST /api/v1/developer/apps`, `GET|PATCH|DELETE /developer/apps/{id}`, `POST /developer/apps/{id}/rotate-secret`, `POST /developer/token`, `POST /developer/token/revoke`, `GET /developer/userinfo`. Tables `oauth_apps` (`client_secret_hash`) and `oauth_tokens` (`access_token_hash`).

**Limitations (measured).**
- **Only `client_credentials` is supported.** `authorization_code` returns 400, so the redirect URIs are unused.
- Tokens issued before this revision were stored with a salted PBKDF2 hash and looked up by that hash, so they never matched (not even in `/userinfo`). They expire on their own; tokens are now stored as a SHA-256 digest.
- There is no refresh token; request a new one when it expires.

---

### White-label / branding (no dedicated screen)
*Roles:* `GET /api/v1/orgs/{org_id}/branding`: any user of that org. `PUT|DELETE`: `require_admin` plus `assert_org_id_is_own`.

**Purpose.** Per-organization branding:
- app name, tagline, logo, favicon;
- 5 colors (hex), validated;
- custom domain, support email, privacy and terms URLs;
- welcome message, login background, footer, help URL;
- `hide_powered_by`, `enable_portal`, `enable_ai`, `custom_css_vars` (sanitised).

**How to use it.** API only: `PUT /api/v1/orgs/{org_id}/branding` with a JSON body; `DELETE` resets it. Portal translations live in the same row and are edited from Settings → Idiomas.

**Technical notes.** Table `org_brandings`, service `app/services/branding_service.py`.

**Limitations (measured).**
- **No staff-app screen calls `/orgs/{id}/branding`.**
- The PDF generator (`services/_pdf_marca.py`) uses only the colors, deliberately not the logo.
- The **client portal's branding comes from a different table**, `ClientPortalConfig` (`logo_url`, `accent_color`), configured per client.
- **`custom_domain` has no reader** (no routing by domain).
- Runtime `PROJECT_NAME` (group `ui_branding`) is separate from `org_brandings.app_name`.

---

### Notifications configuration
*Routes:* `/notifications` (any user) is the **inbox**, not a configuration screen.

**What exists (measured).**
- **Inbox.** `GET /api/v1/alerts`, `PATCH /alerts/{id}/read|resolve`, `GET /enterprise/notifications`, `POST /enterprise/notifications/{id}/read`, `POST /enterprise/notifications/read-all`, `DELETE /enterprise/notifications/clear-old`. Real-time delivery uses a WebSocket ticket from `GET /api/v1/ws/ticket`.
- **Service Desk email notifications.** The runtime group `service_desk` (`SD_NOTIFY_*`), sent over SMTP.
- **BI smart-alert rules.** Settings → Alertas (lower part) and Métricas. `/api/v1/bi/alerts/{rules,custom-metrics,evaluate,history,seed-defaults}`.
- **Collaboration notification rules.** `GET|PUT /api/v1/collaboration/notification-rules`.
- **Settings → Alertas (`alert_configs`).** **Not used by the alert engine**; see the Settings limitations.

**Limitations.** No per-user notification-preferences endpoint was found in the route table, apart from the collaboration rules.

---

### Slack & Teams integration hub
**There is no dedicated screen.** Slack and Teams appear in Enterprise → Integraciones (records and test buttons) and as actions in Automations.

**What exists (measured): five configuration sources.**

| Source | Endpoints / table | Used by |
|---|---|---|
| env `SLACK_WEBHOOK_URL` | — | `NotificationService.send_slack_message` (event notifications, change management) |
| env `SLACK_SIGNING_SECRET` | — | Verifies the inbound Slack commands |
| `/api/v1/slack/{config,test,notify,logs}` (`require_admin`, notify `require_any_manager`) | tables `slack_configs`, `slack_notification_logs` | Only these `/slack` endpoints. **No front-end code calls them** |
| `integration_configs` (Enterprise → Integraciones) | — | `/integrations-hub/slack/notify`, `/integrations-hub/notify-event` (manual) and the Automations actions `send_slack_message` / `send_teams_message` |
| Credenciales → Slack | `integration_credentials` | **Only the test probe** |

Other endpoints:
- **Teams:** `POST /api/v1/integrations-hub/teams/test`, posting to an incoming-webhook URL. `/m365/teams/notify` uses env `TEAMS_WEBHOOK_URL`.
- **Block Kit:** `GET /api/v1/notifications/slack/block-kit/preview`, `POST /notifications/slack/block-kit`.

**Inbound bot commands.** The endpoints are `POST /api/v1/integrations-hub/slack/commands` (slash command) and `POST /integrations-hub/teams/commands`. The verbs are:

| Verb | Synonyms | What it does |
|---|---|---|
| `tarea` | `task` | Create a task |
| `tiempo` | `time`, `horas` | Log time for today |
| `ticket` | — | Create an incident |
| `estado` | `status` | Status of a code |
| anything else | — | Show help |

- Slack: without `SLACK_SIGNING_SECRET` the receiver returns 503. With it, `X-Slack-Signature` (HMAC-SHA256) is verified.
- Teams: requires `TEAMS_BOT_APP_ID` and validates the Bot Framework JWT (`TEAMS_BOT_OPENID_METADATA_URL`, `TEAMS_BOT_ISSUER`).

**Limitations (measured).**
- **User mapping (since 2026-11-03).** Slack: an active user whose `username`, or the part of the email before `@`, equals the Slack `user_name` (case-insensitive). Teams: an active user whose full name equals the Teams display name (case-insensitive, spaces collapsed). If none or more than one match (across all organizations), the bot answers "No encuentro un único usuario…" and does nothing; only the help works without a user. The command then runs with that user's organization as tenant context, so project and task codes resolve only inside it, and new tasks, tickets and time entries are stamped with it. Before, the lookup was a partial match (`%name%`) taking the first user of any organization, commands without a user created anonymous rows, and codes were looked up in every organization. Test: `tests/test_bot_slack_teams_usuario_exacto.py`.
- There is no workspace-to-organization mapping: one Slack app (one `SLACK_SIGNING_SECRET`) and one Teams bot serve the whole installation; a name that exists in two organizations is refused.
- Saving a Slack webhook in Credenciales does not route product notifications there.
- **No automatic Slack or Teams dispatch from `integration_configs`.** `notify_event` is called only from the manual `/integrations-hub/notify-event` endpoint.

---

# Part 2 — Technical guide

## Technical Guide

This section is for developers and operators who install, run, configure, extend and operate contecflow-PSA. Every figure below was measured against the repository on 03-11-2026 (last commit `Tue Nov 3 13:46 2026`, 549 commits) by reading the code or running a read-only command. When something could not be checked it says **Not verified**. Where the Spanish `DOCS.md` disagrees with the code, the code wins, and the differences are listed in [13.3](#133-docsmd-statements-that-do-not-match-the-code).

---

### 1. Architecture and stack

#### 1.1 Components

```
                       browser (SPA, React 18)
                               │  same origin: cookies httpOnly + CSRF Origin check
             ┌─────────────────┴──────────────────┐
   dev:  Vite dev server :3000            prod: nginx "web" container (127.0.0.1:8080)
         proxy /api → :8000 (ws: true)          /api/ → api:8000   /api/v1/ws/ → api:8000 (Upgrade)
             └─────────────────┬──────────────────┘     /health → api   everything else → index.html
                               ▼
   ┌──────────────────────── FastAPI app (app/main.py) ─────────────────────────┐
   │ middlewares: ExceptionHandler · CORS · CSRF · security headers · req logger │
   │ router guards (every /api/v1 and /api/v2 route, HTTP and WebSocket):        │
   │   bind_request_timezone → apply_abac_for_route → enforce_grc_matrix         │
   │ /api/v1 (2,043 routes) · /api/v2 (3) · /health · /ready · /status · /metrics│
   │ endpoints (app/api) ──► services (app/services) ──► ORM models (app/models) │
   │ TenantSession + do_orm_execute tenant filter + before_flush org stamping    │
   │ APScheduler in-process when ENABLE_APSCHEDULER=1 (default): mirrors beat     │
   └───────┬──────────────┬───────────────────┬──────────────────┬───────────────┘
           ▼              ▼                   ▼                  ▼
   PostgreSQL 16     Redis 7              S3-compatible       external APIs
   (SQLite in dev    broker+results,      (versitygw v1.8.0,  (8 AI providers, M365,
    fallback)        rate limits, WS      profile s3/app)     Jira, Slack, Stripe,
           ▲         tickets, pub/sub     or local uploads/   DocuSign, Twilio…)
           │              ▲
   ┌───────┴──────────────┴──────────┐      DuckDB file (OLAP, nightly ETL)
   │ Celery worker  (app.worker)     │      OpenSearch / NATS / LiveKit / ClamAV
   │ Celery beat    (52 schedules)   │      (collaboration, opt-in via env)
   └─────────────────────────────────┘
```

#### 1.2 Backend (measured from `requirements.txt` and `venv`)

| Piece | Version / fact |
|---|---|
| Python | `deploy/Dockerfile.backend`: `python:3.12-slim`; local venv: 3.12.7. `setup.sh` accepts ≥ 3.10 (`find_python`). |
| FastAPI / Pydantic / pydantic-settings | 0.135.3 / 2.12.5 / 2.14.2 |
| Uvicorn | 0.29.0 (`[standard]` on non-Windows) |
| SQLAlchemy / Alembic | 2.0.36 / 1.13.0 |
| PostgreSQL driver | psycopg2-binary 2.9.11 (image `postgres:16-alpine`) |
| Celery / redis-py | 5.6.3 / 6.4.0 (image `redis:7-alpine`) |
| APScheduler | 3.11.2 (in-process alternative to beat) |
| Auth libs | python-jose 3.5.0, PyJWT 2.13.0, bcrypt 4.0.1, passlib 1.7.4, pyotp 2.9.0, webauthn 2.7.0 |
| Rate limiting | slowapi 0.1.9 |
| Observability | prometheus-client 0.21.1, prometheus-fastapi-instrumentator 8.1.0, sentry-sdk 2.57.0, OpenTelemetry (optional import) |
| Storage | boto3 1.42.83 |
| Analytics | duckdb 1.3.0, scikit-learn 1.5.0, reportlab 4.4.10 |
| Optional ML (`requirements-ml.txt`) | torch 2.11.0, sentence-transformers 5.3.0, transformers 5.5.0, prophet 1.3.0, lightgbm 4.6.0, statsmodels 0.14.6. Installed by `setup.sh` if the file exists; **commented out** in the backend Dockerfile. |

Python code size: `app/` ≈ 191,900 lines.

#### 1.3 Frontend (measured from `frontend/package.json` and installed `node_modules`)

| Piece | Declared | Installed |
|---|---|---|
| React / react-dom | ^18.3.1 | 18.3.1 |
| TypeScript | ^6.0.3 | 6.0.3 |
| Vite / @vitejs/plugin-react | ^7.1.12 / ^5.0.4 | 7.3.6 |
| @tanstack/react-query | ^5.45.0 | 5.99.0 |
| react-router-dom | ^7.18.3 | 7.18.3 |
| axios | ^1.15.2 | 1.19.0 |
| Tailwind CSS | ^3.4.4 | 3.4.19 |
| Vitest (jsdom) | ^4.1.5 | 4.1.11 |
| Charts / diagrams | echarts 6, recharts 2, plotly.js 2, d3 7, @xyflow/react 12, bpmn-js 18 | — |
| Realtime / offline | yjs + y-websocket, livekit-client, dexie (IndexedDB), workbox-window | — |

24 runtime and 29 dev dependencies. `frontend/src` has 359 files: 258 `.tsx`, 92 `.ts`, 0 `.js/.jsx`; 123 entries under `src/pages`; `App.tsx` declares 129 `<Route>` elements and 119 `lazy()` imports. TypeScript strictness is partial: `strict: false`, `noImplicitAny: false`; `tsconfig.json` records `strictNullChecks` (226 errors) and `noImplicitAny` (387 errors) as pending. Node in the frontend image: `node:20-alpine`. Vite 7 needs Node ≥ 20.19 (upstream requirement — **not verified** here); `setup.sh` only warns below Node 18.

The axios client (`src/services/api/_core.ts`) uses `baseURL = VITE_API_URL || '/api/v1'`, `withCredentials: true`, a 30 s timeout, echoes the `csrf_token` cookie as `X-CSRF-Token` on unsafe methods, and refreshes through `POST /auth/refresh` on 401.

#### 1.4 Storage

- **Relational:** PostgreSQL in Docker (`contecflow-postgres`, published on `127.0.0.1:5434`), or SQLite (`sqlite:///./contecflow.db`) when Docker is unavailable — `setup.sh` silently falls back to SQLite (`revert_env_to_sqlite`). `setup.bat` (Windows) uses SQLite only and never touches Docker.
- **Objects:** S3-compatible. The compose service `s3` runs **versitygw v1.8.0** pinned by digest (`ghcr.io/versity/versitygw@sha256:3029…2499`), POSIX backend, bucket created with `mkdir`, health at `/health`, published on `127.0.0.1:9003`. It is behind the profiles `s3` and `app`; MinIO is gone (its public images stopped being downloadable in 09-2026). Variables are still called `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_BUCKET`, `MINIO_PORT`. `S3Service` only uses S3 when `AWS_ACCESS_KEY` and `AWS_SECRET_KEY` are set; otherwise documents go to `UPLOAD_DIR` (`uploads/`). Presigned URLs are SigV4 and versitygw enforces the region, so `AWS_REGION` must equal the gateway's `VGW_REGION` (the compose file wires both from `AWS_REGION`).
- **OLAP:** DuckDB file (`DUCKDB_PATH`), loaded by the nightly `olap_nightly_etl` task.

#### 1.5 Search

There is no dedicated search engine for the core domain. Measured:

- Substring search is `LIKE/ILIKE '%term%'` in services (inventory in `docs/SEARCH_PERFORMANCE.md`, ~140 call sites). On PostgreSQL, revision `083_pg_trgm_search_indexes` adds `pg_trgm` GIN indexes; on SQLite nothing changes.
- Knowledge-base vectors: revision `116_kb_vectores_pgvector` creates `sd_kb_articles.embedding_vec` **only if** the `vector` extension exists. `postgres:16-alpine` does not ship it, so in the default stack similarity is computed in Python against every article.
- Collaboration search: `COLLAB_SEARCH_BACKEND = auto|simple|pg|opensearch` (`app/services/collaboration/_search.py`), OpenSearch via `OPENSEARCH_URL`.
- Semantic classifier: `SEMANTIC_EMBEDDINGS_BACKEND=tfidf` by default; transformer embeddings need `requirements-ml.txt`.

#### 1.6 AI providers

`app/services/ai_provider_service.py::PROVIDER_CATALOG` lists 8 providers: `anthropic`, `openai`, `gemini`, `deepseek`, `groq`, `mistral`, `ollama`, `azure`. Resolution order is organisation provider (DB) → global provider (DB) → `.env` (`AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL`, `AI_BASE_URL`), with `ANTHROPIC_API_KEY` as a legacy alias. **Caveat (measured):** some code paths are Anthropic-only and skip that chain. `ai_client.py` and `ai_modules/_base.py` read a UI credential `ai_providers/anthropic_api_key`, then `settings.ANTHROPIC_API_KEY`. `ai_planning_service.py` (lines 136, 322) and the receipt-OCR path in `expense_service.py` (lines 207/242) read `settings.ANTHROPIC_API_KEY` directly. A deployment configured only with `AI_PROVIDER=gemini` will not get those features. Speech-to-text has its own chain (`STT_PROVIDER`, default `openai`; Azure, Google, local Whisper via `WHISPER_LOCAL=1`).

---

### 2. Repository layout (measured)

| Path | Content | Count |
|---|---|---|
| `app/main.py` | App factory, middlewares, router guards, `/health`, `/ready`, `/status`, widgets, lifespan (schema preflight, key management, schedulers) | 1,089 lines |
| `app/worker.py` | Celery app, 34 tasks, 52 beat entries | 1,767 lines |
| `app/api/v1/endpoints/` | Endpoint modules (128 top-level + 41 in 7 sub-packages: `admin`, `ai`, `collaboration`, `integrations`, `projects`, `service_desk`, `v239`) | 169 `.py` |
| `app/api/v1/routers/` | 5 domain aggregators (`core`, `delivery`, `ai_domain`, `platform`, `framework`) + auth routers (`auth_core`, `auth_mfa`, `auth_saml`, `auth_sessions`, `auth_sso`) | 10 modules |
| `app/api/v2/` | `meta.py`, `profitability.py` | 3 routes |
| `app/services/` | Business logic (158 top-level modules + 12 sub-packages, e.g. `service_desk`, `collaboration`, `approval_engine`, `cmdb`, `olap`, `stt`) | 357 `.py` |
| `app/models/` | SQLAlchemy models | 72 files, 395 mapped classes, 396 tables |
| `app/schemas/` | Pydantic schemas | 48 files |
| `app/core/` | Config, security, CSRF, ABAC/GRC enforcement, tenancy, encryption, metrics, rate limiter, uploads, timezone context | 30 files + `config_groups/` (5 mixins) |
| `app/db/` | `session.py` (engine, `TenantSession`, tenant hooks), `seed.py` + `seed_parts/` (9 modules, 1,969 lines), `migrate.py` (legacy, unused by setup flows) | — |
| `alembic/versions/` | Migrations, single linear chain, head `117_esign_secretos_cifrados` | 71 revisions |
| `tests/` | Backend pytest suite | 304 `test_*.py`, **4,021 tests collected** |
| `tests_e2e/` | Python Playwright E2E | 13 files |
| `frontend/` | Vite + React SPA, `nginx.frontend.conf`, i18n checkers in `scripts/` | see §1.3 |
| `deploy/` | `Dockerfile.backend`, `Dockerfile.frontend` | 2 |
| `docker-compose.yml` | Single compose with profiles `s3`, `app`, `observability` | 11 services |
| `ops/prometheus/` | `prometheus.yml` (jobs: api, postgres, redis, prometheus) | 1 |
| `scripts/` | Audits, `ci_local.sh`, `reset_to_admin_only.py`, `seed_full_data.py`, `rotate_keys.sh`, `deploy.sh`, smoke scripts | 32 entries |
| `docs/` | Design guide, audits, observability, config maps, service desk | 19 `.md` |
| `setup.sh` / `setup.bat` | macOS/Linux and Windows installers | 1,309 / 861 lines |

Ignored local artefacts present in the working tree: `venv/`, `uploads/**`, `*.db`, `*.db-shm/-wal` (e.g. `clarive.db*`, `contecflow.db-*`). Note: `.env` **is tracked** (see §7.5).

---

### 3. Requirements and installation

#### 3.1 Requirements

- Python ≥ 3.10 for `setup.sh`; 3.12 is what the image and the local venv use (3.12 recommended).
- Node.js + npm (see §1.3 for the Node version).
- Docker with Compose v2 (or v1 `docker-compose`) — optional for development, required for the production stack. `setup.sh` tries to start the daemon (Docker Desktop, OrbStack, Colima or systemd) and waits up to 180 s.
- `lsof` (used to free ports 8000/3000), `curl`, optionally `sqlite3` (SQLite self-check).

#### 3.2 `setup.sh` modes (macOS/Linux)

Ports: backend **8000**, frontend **3000** (hard-coded in the script), Postgres **127.0.0.1:5434**, Redis **127.0.0.1:6381**, S3 **127.0.0.1:9003**. Logs: `/tmp/contecflow-backend.log`, `/tmp/contecflow-frontend.log`; PIDs in `/tmp/contecflow-*.pid`.

| Mode | Steps (in order) |
|---|---|
| `demo` | `setup_backend` → `setup_frontend` → `python -m app.db.seed` → `start_services` |
| `clean` | `setup_backend` → `setup_frontend` → `scripts/reset_to_admin_only.py` (**wipes every table**, recreates the default org and the `admin` superadmin from `SUPERADMIN_EMAIL`/`SUPERADMIN_PASSWORD`) → `start_services`. **There is no ENVIRONMENT gate on this path.** |
| `start` | `start_services` only. Does **not** run migrations. |
| `stop` | Kills the PIDs and anything on 8000/3000; Docker keeps running. |
| `update` | `setup_backend` + `setup_frontend`, no start. |
| `docker-stop` | `docker compose down` (data kept). |
| `docker-clean` | `docker compose down -v`. The message says "borra todos los datos", but `postgres_data` and `s3_data` are `external: true`, so only `redis_data`/`prometheus_data` are removed. |
| *(no argument)* | Prints usage and exits 1. |

What `setup_backend` does, step by step:

1. Finds Python ≥ 3.10 (installs it via Homebrew/apt etc. if missing), creates `venv/` (or reuses `.venv/`).
2. `pip install -r requirements.txt` only when its hash changed (`venv/.req_hash`); same for `requirements-ml.txt` (`.req_ml_hash`). Installs `boto3`/`kubernetes` if AWS/K8s variables are present in `.env`.
3. `setup_docker_infra`: if Docker works, it fills the compose-required variables in `.env` (`POSTGRES_USER/DB`, `MINIO_ROOT_USER` default `contecflow`; `POSTGRES_PASSWORD`/`MINIO_ROOT_PASSWORD` generated once, or `contecflow_dev` if the volume already exists), creates the external volumes `contecflow_postgres_data` and `contecflow_s3_data`, runs `docker compose up -d --remove-orphans` (postgres + redis only), waits 30 s for `pg_isready`, and rewrites `DATABASE_URL`/`REDIS_URL` to 5434/6381 **only if** `.env` still points at SQLite. On any failure it reverts to SQLite and continues.
4. Creates `.env` from `.env.example` if missing; then fills or replaces placeholders/weak values: `SUPERADMIN_EMAIL`, `SUPERADMIN_PASSWORD` and `DEFAULT_USER_PASSWORD` (random `token_urlsafe(18)+'Aa1!'` when weak), `ENVIRONMENT=development` if absent, `CLIENT_PORTAL_SECRET`, `WEBHOOK_SECRET`, and regenerates `SECRET_KEY` if it is shorter than 32 characters or a placeholder.
5. `python -m alembic upgrade head`; aborts on failure.
6. Checks that at least one user with a password exists; with SQLite and no users it deletes `contecflow.db` and migrates again.
7. `sync_demo_passwords`: **only if** `ENVIRONMENT ∈ {development, dev, local, test, testing, demo}`, it rehashes `admin`, `ana.torres`, `luis.vega`, `rrhh` with `DEFAULT_USER_PASSWORD`, guarded by a hash sentinel in `venv/.pwd_hash`.

`start_services`: SQLite `PRAGMA quick_check` (and WAL/SHM cleanup), installs the frontend if `node_modules` is missing, runs `sync_demo_passwords` again, kills ports 8000/3000, starts `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`, waits up to 60 s for `/health`, validates JSX with Babel when sources changed (`frontend/validate.cjs`), starts `npm run dev -- --port 3000`, prints the demo users **with the password in clear text**, and opens the browser.

**APScheduler mirrors the whole Celery beat schedule** (since 2026-11-05, `app.main._replicar_celery_beat`): with `ENABLE_APSCHEDULER=1` (the code default) only 11 of the 58 scheduled jobs used to run (approval timeouts, the SLA scan, ticket events, mailboxes, revenue recognition, connectors, ML… did not). Now every beat entry is registered in APScheduler with the same cadence and arguments and runs in-process; the entries APScheduler already schedules with its own function are listed in `_BEAT_YA_EN_APSCHEDULER`. A test fails if a beat entry is not mirrored.

**Both `setup.sh` and `setup.bat` start a Celery worker and Celery beat** next to the API (since 2026-11-03; before, none was started and only the 4 APScheduler jobs ran locally). The API is launched with `ENABLE_APSCHEDULER=0 ENABLE_CELERY_BEAT=1`. `setup.sh stop` and Ctrl+C stop the worker and beat too. On Windows the worker uses `--pool=solo` (**not verified on Windows**).

#### 3.3 `setup.bat` (Windows), measured differences

- Modes: `demo` (aliases `seed`), `clean` (aliases `zero`, `cero`, `admin-only`, `admin_only`), `start [demo|clean]`, `stop`, `update`; no argument = full install plus an interactive data-mode prompt (default demo). `SETUP_INIT_MODE=demo|clean` skips the prompt.
- **`setup.bat start` re-applies a data mode on every start** (`resolve_init_mode` → `apply_selected_data_mode`): demo re-seeds, clean wipes. Unlike `setup.sh start`, it does not just preserve the DB.
- Always runs `alembic upgrade head`; sets `PYTHONUTF8=1`; SQLite only; expects `.venv\Scripts\python.exe`.
- Cosmetic bug: the banner prints `contecflow2024! - Plataforma PSA Enterprise` (the historic default password used as the product name).

#### 3.4 Manual installation

```bash
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt            # + requirements-ml.txt for ML features
cp -n .env.example .env                    # .env is tracked, so a clone already has one; then review SECRET_KEY, SUPERADMIN_*, DEFAULT_USER_PASSWORD,
                                           # CLIENT_PORTAL_SECRET, DATABASE_URL, REDIS_URL, ALLOWED_ORIGINS
docker volume create contecflow_postgres_data contecflow_s3_data
docker compose up -d                       # postgres + redis (needs POSTGRES_*, MINIO_ROOT_* in .env)
python -m alembic upgrade head
python -m app.db.seed                      # demo data   | or: python scripts/reset_to_admin_only.py
uvicorn app.main:app --reload --port 8000
celery -A app.worker.celery_app worker --loglevel=info
celery -A app.worker.celery_app beat --loglevel=info   # and run uvicorn with ENABLE_APSCHEDULER=0 ENABLE_CELERY_BEAT=1 (see §8.1)
cd frontend && npm install --legacy-peer-deps && npm run dev -- --port 3000
```

`make dev` runs uvicorn (`--reload`, 127.0.0.1:8000) and Vite (127.0.0.1:3000) together. Do not copy `frontend/.env.example` as-is: it sets `VITE_API_URL=http://localhost:8000` (no `/api/v1`), and the axios client uses that value **as the API base**. Calls would go to `http://localhost:8000/auth/login` and fail. Either leave `VITE_API_URL` unset (the Vite proxy forwards `/api` to `http://localhost:8000`) or set it to `…/api/v1`. **Not verified at runtime.**

#### 3.5 Docker stack (`docker-compose.yml`, project name `contecflow`)

| Service | Image | Profile | Port (host) | Notes |
|---|---|---|---|---|
| `postgres` | postgres:16-alpine | default | `127.0.0.1:5434` (`POSTGRES_PORT`) | UTF-8 `en_US.utf8` collation; volume `contecflow_postgres_data` (external) |
| `redis` | redis:7-alpine | default | `127.0.0.1:6381` (`REDIS_PORT`) | AOF on, `maxmemory ${REDIS_MAXMEMORY:-256mb}`, `allkeys-lru`; volume `contecflow_redis_data` |
| `s3` | versitygw v1.8.0 (digest) | `s3`, `app` | `127.0.0.1:9003` (`MINIO_PORT`) | volume `contecflow_s3_data` (external) |
| `migrate` | `contecflow-api:local` | `app` | — | one-shot `alembic upgrade head`; api/worker/beat wait for `service_completed_successfully` |
| `api` | `contecflow-api:local` | `app` | none (expose 8000) | `uvicorn --workers ${API_WORKERS:-4}`; healthcheck `/health` |
| `worker` | `contecflow-api:local` | `app` | — | `celery worker --concurrency=${WORKER_CONCURRENCY:-4}` |
| `beat` | `contecflow-api:local` | `app` | — | singleton `celery beat` |
| `web` | `contecflow-web:local` (nginx 1.27 + built SPA) | `app` | `127.0.0.1:8080` (`WEB_PORT`) | reverse proxy, `client_max_body_size 110m` |
| `prometheus` | prom/prometheus:v2.54.1 | `observability` | `127.0.0.1:9090` | volume `contecflow_prometheus_data` |
| `postgres-exporter` | v0.15.0 | `observability` | — | |
| `redis-exporter` | v1.61.0 | `observability` | — | |

The `x-app` anchor overrides `DATABASE_URL`, `REDIS_URL`, the `AWS_*` S3 variables and `ENVIRONMENT` (default `production`) for api/worker/beat. It also sets `CELERY_BROKER_URL` (db 1) and `CELERY_RESULT_BACKEND` (db 2), but **no code reads them**: `app/worker.py` uses `REDIS_URL` (db 0) for broker and backend. The compose header mentions an `alertmanager` that is not defined. `deploy/Dockerfile.backend` says it "has not been docker-build verified"; `DOCS.md` adds that `tests/test_docker_stack.py` checks only the definition. A full `docker compose --profile app up` is **not verified** here.

Commands: `docker compose up -d` (infra only) · `docker compose --profile s3 up -d` · `docker compose --profile app up -d` (production) · `docker compose --profile observability up -d` · `docker compose down` (keeps data) · `docker compose down -v` (removes only redis/prometheus volumes).

#### 3.6 First login

- `/api/v1/auth/login` accepts **username or email** (`lookup_user_by_credentials`) and is limited to 5/min per IP, plus a lockout of `LOGIN_MAX_ATTEMPTS` (5) within 900 s for 900 s.
- **Superadmin:** username `admin`, password `SUPERADMIN_PASSWORD` from `.env`. The seed re-applies it on every run and reactivates the account (`seed_parts/core.py`), and so does `reset_to_admin_only.py`. Changing the superadmin password in the UI does not survive a re-seed.
- **Email of `admin`:** with `seed_users_data.json` present in the repo root (it is: 9 users), the seed takes users from that file, which hard-codes `admin@company.com`. **`SUPERADMIN_EMAIL` is ignored by `demo`** and used only by `default_seed_users()` (when the JSON is absent) and by `clean`. Log in with the username `admin` to be safe.
- **Other demo users** (`ana.torres` pm, `luis.vega` employee, `rrhh` hr, plus `marta.gil`, `carlos.ruiz`, `sara.lope`, `diego.mora`, `elena.pardo`): password `DEFAULT_USER_PASSWORD`.
- **Conflict to know about:** `sync_demo_passwords` (dev environments only) rewrites `admin` to `DEFAULT_USER_PASSWORD` whenever that value changes, and the `setup.sh` banner always prints `admin / DEFAULT_USER_PASSWORD`. After a fresh `demo` the sentinel usually prevents the overwrite, so admin keeps `SUPERADMIN_PASSWORD`; after you change `DEFAULT_USER_PASSWORD`, admin's password becomes that value. If one fails, try the other. **Not verified at runtime.**
- `ENABLE_SUPERADMIN_BYPASS=1` exists for emergencies. The app refuses to boot with it unless `ENVIRONMENT=development` **and** SQLite.

---

### 4. Configuration

#### 4.1 Two layers

1. **Environment (`.env` → `app.core.config.Settings`, pydantic-settings, `extra="ignore"`).** 248 fields: 149 in `config.py` and 99 in five mixins (`ai_config` 25, `sla_config` 19, `health_config` 23, `semantic_config` 9, `service_desk_config` 22). Read once at import, so a change needs a restart. Validators stop the boot on: weak or placeholder `SECRET_KEY`; an `ENVIRONMENT` outside `{development, test, staging, production}`; placeholder `DEFAULT_USER_PASSWORD`, `CLIENT_PORTAL_SECRET` or `SUPERADMIN_PASSWORD`. In staging/production they also require `WEBHOOK_SECRET`/`INBOUND_EMAIL_SECRET` (≥ 24 characters) and reject localhost in `ALLOWED_ORIGINS`, `FRONTEND_URL`, `BACKEND_URL`, `BASE_URL`, `WEBAUTHN_ORIGIN` and `WEBAUTHN_RP_ID`.
2. **Runtime settings (DB table `app_settings`, edited in Settings).** `app/services/settings_service.py::RUNTIME_FLAG_GROUPS` declares **123 keys in 15 groups**: `sla`, `service_desk`, `health`, `semantic`, `password_policy`, `locale`, `tokens`, `key_rotation`, `ai`, `feature_flags`, `storage`, `security_network`, `ui_branding`, `observability`, `timeouts`. Resolution is **organisation row → global row (`organization_id IS NULL`) → `settings.<KEY>` from env**. Reads are cached in-process for 60 s; writes invalidate locally and across workers via Redis pub/sub (`app/core/settings_pubsub.py`, a no-op without `REDIS_URL`). Not every env variable has a runtime override: only the 123 keys listed there are editable.

#### 4.2 Settings fields (`Settings`, 248)

Defaults are the code defaults, never values from `.env`. Meanings are taken from the field name, its inline comment and the code that reads it; behaviour described in bold was checked in the code that consumes the variable.

**Core (`app/core/config.py`) — 149 variables**

| Name | Default | Meaning |
|---|---|---|
| `PROJECT_NAME` | `'Contecflow'` | App title (OpenAPI, /health). |
| `VERSION` | `'23.9.3'` | Version string reported by /health and OpenAPI. |
| `API_V1_STR` | `'/api/v1'` | Mount prefix of API v1 (also docs URLs). |
| `API_V2_STR` | `'/api/v2'` | Mount prefix of API v2. |
| `ENVIRONMENT` | `'development'` | `development`/`test`/`staging`/`production` (validator rejects anything else). Drives secret hardening, Secure cookies, HSTS, docs exposure, schema-drift enforcement. |
| `LOG_LEVEL` | `'INFO'` | Root/uvicorn log level. |
| `SECRET_KEY` | *(required)* | **Required.** JWT legacy key and the root of field-level encryption (PBKDF2/HKDF). ≥32 chars, ≥10 distinct chars, no placeholder. |
| `SECRET_KEY_PREVIOUS` | `''` | Comma-separated previous keys, used only to **decrypt** after a rotation; filled by `scripts/rotate_keys.sh` (§7.5). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access-token TTL; effective TTL is `min(this, ACCESS_TOKEN_MAX_MINUTES)`. Runtime-overridable. |
| `ACCESS_TOKEN_MAX_MINUTES` | `30` | Upper clamp for access-token TTL. Runtime-overridable. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh-token/cookie TTL. Runtime-overridable. |
| `KEY_ROTATION_ENABLED` | `True` | Enable JWT keyring + integration-secret rotation. |
| `JWT_KEY_ROTATION_DAYS` | `30` | Rotate JWT signing key every N days. |
| `JWT_KEY_RETENTION_COUNT` | `3` | Old JWT keys kept for verification. |
| `INTEGRATION_SECRET_ROTATION_DAYS` | `60` | Re-encrypt integration secrets every N days. |
| `KEY_ROTATION_RUN_HOUR_UTC` | `2` | Hour of the rotation job. **Interpreted in `DEFAULT_TIMEZONE`, not UTC** (both schedulers use that zone). |
| `KMS_PROVIDER` | `''` | `aws` enables AWS KMS envelope encryption. |
| `AWS_KMS_KEY_ID` | `''` | KMS key id. |
| `AWS_KMS_REGION` | `''` | KMS region. |
| `DATABASE_URL` | *(required)* | **Required.** SQLAlchemy URL (SQLite or `postgresql+psycopg2://`). |
| `DEFAULT_PROJECT_TYPE` | `'consulting'` | Default project type for new projects. |
| `DEFAULT_BILLING_TYPE` | `'time_material'` | Default billing type. |
| `ALLOWED_ORIGINS` | `localhost:3000/5173/8000, 127.0.0.1:8000` | CORS allow-list **and** CSRF Origin allow-list (JSON list). Must be explicit, no `*`, no localhost in staging/production. |
| `SUPERADMIN_EMAIL` | *(required)* | **Required.** Email of the bootstrap superadmin (used by `default_seed_users()` and `reset_to_admin_only.py`). |
| `SUPERADMIN_PASSWORD` | *(required)* | **Required.** Bootstrap superadmin password; re-applied on every seed. ≥16 chars outside local envs. |
| `CLIENT_PORTAL_SECRET` | *(required)* | **Required.** Signing secret for client-portal tokens; ≥32 chars in staging/production. |
| `SCIM_BEARER_TOKEN` | `''` | Static bearer for SCIM provisioning. |
| `SCIM_ALLOWED_ORG_ID` | `''` | Org that SCIM token may provision. |
| `WEBHOOK_SECRET` | `''` | HMAC secret for inbound webhooks; mandatory (≥24 chars) in staging/production. |
| `INBOUND_EMAIL_SECRET` | `''` | Secret for inbound-email channel; same rules as WEBHOOK_SECRET. |
| `TRUST_PROXY_HEADERS` | `False` | Trust `X-Forwarded-For` from TRUSTED_PROXY_CIDRS (app/core/network.py). |
| `TRUSTED_PROXY_CIDRS` | `'127.0.0.1/32,::1/128'` | Proxies whose forwarded headers are trusted. |
| `GITHUB_WEBHOOK_SECRET` | `''` | GitHub webhook HMAC. |
| `GITLAB_WEBHOOK_SECRET` | `''` | GitLab webhook token. |
| `JIRA_WEBHOOK_SECRET` | `''` | Jira webhook secret. |
| `DOCUSIGN_INTEGRATION_KEY` | `''` | DocuSign env fallback (DB config wins). |
| `DOCUSIGN_SECRET_KEY` | `''` | DocuSign secret. |
| `DOCUSIGN_ACCOUNT_ID` | `''` | DocuSign account. |
| `DOCUSIGN_BASE_URL` | `''` | DocuSign API base. |
| `DOCUSIGN_CONNECT_HMAC_KEY` | `''` | DocuSign Connect HMAC. |
| `ADOBE_SIGN_CLIENT_ID` | `''` | Adobe Sign OAuth client. |
| `ADOBE_SIGN_CLIENT_SECRET` | `''` | Adobe Sign secret. |
| `ADOBE_SIGN_BASE_URL` | `'https://api.na1.adobesign.com/api/rest/v6'` | Adobe Sign API base. |
| `PROVISIONING_ENABLED` | `False` | Enable Terraform/Ansible runners. |
| `PROVISIONING_ROOT_DIR` | `''` | Working dir for provisioning runners. |
| `MICROSOFT_OAUTH_BASE` | `'https://login.microsoftonline.com'` | Microsoft identity endpoint (SSO). |
| `GOOGLE_OAUTH_BASE` | `'https://accounts.google.com'` | Google OAuth endpoint. |
| `GOOGLE_TOKEN_URL` | `'https://oauth2.googleapis.com/token'` | Google token endpoint. |
| `WEBAUTHN_RP_ID` | `'localhost'` | Passkey relying-party id; real domain required in staging/production. |
| `WEBAUTHN_RP_NAME` | `'Contecflow PSA'` | Passkey RP display name. |
| `WEBAUTHN_ORIGIN` | `'http://localhost:5173'` | Expected WebAuthn origin (no localhost in prod). |
| `XERO_API_BASE` | `'https://api.xero.com/api.xro/2.0'` | Xero API base. |
| `QB_API_BASE` | `'https://quickbooks.api.intuit.com/v3/company'` | QuickBooks API base. |
| `BASE_URL` | `'http://localhost:8000'` | Public backend URL (links); no localhost in prod. |
| `OTEL_ENABLED` | `False` | Enable OpenTelemetry tracing (needs endpoint too). |
| `OTEL_SERVICE_NAME` | `'contecflow-api'` | OTel service.name. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `''` | OTLP/HTTP endpoint. |
| `OTEL_EXPORTER_OTLP_HEADERS` | `''` | OTLP headers. |
| `METRICS_ENABLED` | `False` | Register `/metrics` + HTTP instrumentation. |
| `METRICS_AUTH_TOKEN` | `None` | Bearer for `/metrics` (runtime key with same name takes precedence). |
| `METRICS_MULTIPROC_DIR` | `None` | Prometheus multiprocess dir (sets PROMETHEUS_MULTIPROC_DIR). |
| `FRONTEND_URL` | `'http://localhost:5173'` | Public SPA URL (emails, redirects). |
| `BACKEND_URL` | `'http://localhost:8000'` | Public API URL (logged docs link). |
| `PDF_STORAGE_PATH` | `'./storage/pdfs'` | Local dir for generated PDFs. |
| `AWS_S3_BUCKET` | `'contecflow-documents'` | Document bucket. S3 is used only when AWS_ACCESS_KEY + AWS_SECRET_KEY are set (app/services/s3_service.py); otherwise files go to UPLOAD_DIR. |
| `AWS_REGION` | `'eu-west-1'` | S3 region (must match versitygw `VGW_REGION`). |
| `AWS_ACCESS_KEY` | `None` | S3 access key. |
| `AWS_SECRET_KEY` | `None` | S3 secret key. |
| `AWS_S3_ENDPOINT_URL` | `None` | S3-compatible endpoint (versitygw/MinIO). |
| `AWS_S3_FORCE_PATH_STYLE` | `None` | Force path-style addressing (None = auto). |
| `S3_URL_EXPIRATION_HOURS` | `24` | Presigned URL lifetime. |
| `MAX_FILE_SIZE_MB` | `100` | Upload size cap. |
| `SLACK_WEBHOOK_URL` | `None` | Slack incoming webhook for notifications. |
| `NOTIFICATION_EMAIL_FROM` | `'alerts@contecflow.local'` | From address for alert mail. |
| `DEFAULT_IMPUTATION_LOCKOUT_DAYS` | `14` | Days after which time entries lock. |
| `DEFAULT_TIMEZONE` | `'Europe/Madrid'` | Fallback tz; also **Celery beat and APScheduler timezone**. |
| `DEFAULT_LANGUAGE` | `'es'` | Fallback UI language. |
| `DEFAULT_CURRENCY` | `'EUR'` | Fallback currency. |
| `DEFAULT_TAX_RATE` | `21.0` | Fallback VAT %. |
| `MIN_PASSWORD_LENGTH` | `8` | Password policy. |
| `BCRYPT_ROUNDS` | `12` | bcrypt cost. |
| `PASSWORD_REQUIRE_UPPERCASE` | `True` | Password policy. |
| `PASSWORD_REQUIRE_LOWERCASE` | `True` | Password policy. |
| `PASSWORD_REQUIRE_DIGIT` | `True` | Password policy. |
| `PASSWORD_REQUIRE_SPECIAL` | `True` | Password policy. |
| `LOGIN_MAX_ATTEMPTS` | `5` | Failed logins before lockout. |
| `LOGIN_ATTEMPT_WINDOW_SECONDS` | `900` | Window for counting failures. |
| `LOGIN_LOCKOUT_SECONDS` | `900` | Lockout duration. |
| `DEFAULT_USER_PASSWORD` | *(required)* | **Required.** Password given to non-superadmin seed users; rejected if `CHANGE_ME*` or (outside local envs) the historic default. |
| `DEFAULT_WORKING_HOURS_PER_DAY` | `8.0` | Capacity default. |
| `DEFAULT_WEEKLY_CAPACITY_HOURS` | `40.0` | Capacity default. |
| `DEFAULT_SIMULATION_HOURLY_RATE` | `80.0` | Rate used in what-if simulations. |
| `DEFAULT_VACATION_DAYS_PER_YEAR` | `23` | Absence default. |
| `REDIS_URL` | `None` | Celery broker **and** result backend, rate-limit storage, WS tickets, settings pub/sub. Unset = in-process fallbacks. |
| `RATE_LIMIT_REQUIRE_REDIS_IN_PRODUCTION` | `True` | Refuse to boot in production if Redis is unreachable for the limiter. |
| `SENTRY_DSN` | `None` | Enable Sentry. |
| `SENTRY_ENVIRONMENT` | `'development'` | Sentry environment tag. |
| `AZURE_TENANT_ID` | `None` | M365/Azure AD app (Graph). |
| `AZURE_CLIENT_ID` | `None` | M365 app id. |
| `AZURE_CLIENT_SECRET` | `None` | M365 app secret. |
| `M365_CALENDAR_SYNC_ENABLED` | `False` | Enable calendar sync. |
| `M365_TEAMS_NOTIFICATIONS_ENABLED` | `False` | Enable Teams notifications. |
| `TEAMS_WEBHOOK_URL` | `None` | Teams incoming webhook. |
| `SHAREPOINT_SITE_ID` | `None` | SharePoint site for documents. |
| `FRONTEND_EMBED_BASE_URL` | `''` | Base URL for BI embeds in Teams/SharePoint. |
| `SMTP_HOST` | `''` | Outbound SMTP host. |
| `SMTP_USER` | `''` | SMTP user. |
| `SMTP_PORT` | `587` | SMTP port. |
| `SMTP_PASS` | `''` | SMTP password. |
| `SMTP_FROM` | `''` | SMTP From. |
| `TWILIO_ACCOUNT_SID` | `None` | Twilio (SMS/voice). |
| `TWILIO_AUTH_TOKEN` | `None` | Twilio token. |
| `TWILIO_FROM_NUMBER` | `None` | Twilio sender. |
| `CLIENT_TOKEN_EXPIRE_HOURS` | `72` | Client-portal token TTL. |
| `PORTAL_SHARE_LINK_EXPIRE_HOURS` | `72` | Portal share-link TTL. |
| `JWT_ALGORITHM` | `'HS256'` | Algorithm for **client-portal** tokens only (staff JWTs hard-code HS256 in app/core/security.py). |
| `PBKDF2_ITERATIONS` | `260000` | Iterations for legacy v1 key derivation. |
| `MAX_APPS_PER_USER` | `10` | Developer-portal OAuth apps per user. |
| `WEBHOOK_CB_THRESHOLD` | `5` | Consecutive failures before an outbound webhook is suspended. |
| `AI_REVENUE_HOURLY_RATE_FALLBACK` | `85.0` | Hourly rate used by AI revenue estimates when none is known. |
| `UPLOAD_DIR` | `'uploads'` | Local upload directory. |
| `COLLAB_CALL_START_PER_MIN` | `8` | Collaboration rate limit. |
| `COLLAB_CALL_JOIN_PER_MIN` | `20` | Collaboration rate limit. |
| `COLLAB_CALL_HISTORY_LIMIT` | `50` | Call history page size. |
| `COLLAB_WEBHOOK_INCOMING_PER_MIN` | `120` | Incoming collab webhook rate limit. |
| `COLLAB_CALENDAR_MAX_EVENTS` | `20` | Calendar events returned. |
| `COLLAB_PORTAL_MESSAGE_PER_MIN` | `25` | Portal message rate limit. |
| `STT_PROVIDER` | `'openai'` | Speech-to-text provider. |
| `STT_FALLBACK_PROVIDERS` | `''` | Comma list of fallbacks. |
| `AZURE_SPEECH_KEY` | `''` | Azure STT key. |
| `AZURE_SPEECH_REGION` | `'westeurope'` | Azure STT region. |
| `AZURE_STT_LANGUAGE` | `'es-ES'` | Azure STT language. |
| `GOOGLE_STT_API_KEY` | `''` | Google STT key. |
| `GOOGLE_STT_LANGUAGE` | `'es-ES'` | Google STT language. |
| `SLACK_API_BASE` | `'https://slack.com/api'` | Slack API base. |
| `SLACK_SIGNING_SECRET` | `''` | Slack request signature secret. |
| `TEAMS_BOT_APP_ID` | `''` | Teams bot app id. |
| `TEAMS_BOT_OPENID_METADATA_URL` | `'https://login.botframework.com/v1/.well-known/openidconfiguration'` | Bot Framework OpenID metadata. |
| `TEAMS_BOT_ISSUER` | `'https://api.botframework.com'` | Bot Framework issuer. |
| `STRIPE_SECRET_KEY` | `None` | Stripe. |
| `STRIPE_PUBLISHABLE_KEY` | `None` | Stripe. |
| `STRIPE_WEBHOOK_SECRET` | `None` | Stripe webhook signature. |
| `OPEN_EXCHANGE_RATES_APP_ID` | `None` | FX rates provider. |
| `EXCHANGE_RATES_AUTO_UPDATE` | `False` | Auto-refresh FX rates. |
| `RATE_LIMIT_DEFAULT` | `'200/minute'` | Passed as slowapi `default_limits` (see API → rate limits: likely inert). |
| `CELERY_AGENT_TASK_TIME_LIMIT` | `300` | Hard limit for agent tasks (s). |
| `CELERY_AGENT_TASK_SOFT_TIME_LIMIT` | `280` | Soft limit (s). |
| `OUTBOUND_HTTP_TIMEOUT_SECONDS` | `10.0` | Default outbound HTTP timeout (runtime-overridable). |
| `OUTBOUND_AI_TIMEOUT_SECONDS` | `30.0` | Outbound AI call timeout (runtime-overridable). |

**AI (`config_groups/ai_config.py`) — 26 variables**

| Name | Default | Meaning |
|---|---|---|
| `AI_PROVIDER` | `''` | Deployment-level AI provider (last step of org→global→env chain). |
| `AI_API_KEY` | `''` | Key for AI_PROVIDER. |
| `AI_MODEL` | `''` | Model for AI_PROVIDER. |
| `AI_BASE_URL` | `''` | Base URL (Ollama/Azure). |
| `ANTHROPIC_API_KEY` | `''` | Legacy alias; also read **directly** by several Anthropic-only code paths. |
| `ANTHROPIC_API_URL` | `'https://api.anthropic.com/v1'` | Provider API base URL. |
| `ANTHROPIC_DOCS_URL` | `'https://www.anthropic.com/docs'` | Provider docs link shown in UI. |
| `OPENAI_API_URL` | `'https://api.openai.com/v1'` | Provider API base URL. |
| `OPENAI_DOCS_URL` | `'https://platform.openai.com/docs'` | Provider docs link shown in UI. |
| `GEMINI_API_URL` | `'https://generativelanguage.googleapis.com/v1beta'` | Provider API base URL. |
| `GEMINI_DOCS_URL` | `'https://developers.google.com/ai'` | Provider docs link shown in UI. |
| `DEEPSEEK_API_URL` | `'https://api.deepseek.com/v1'` | Provider API base URL. |
| `DEEPSEEK_DOCS_URL` | `'https://docs.deepseek.ai'` | Provider docs link shown in UI. |
| `GROQ_API_URL` | `'https://api.groq.com/openai/v1'` | Provider API base URL. |
| `GROQ_DOCS_URL` | `'https://docs.groq.com'` | Provider docs link shown in UI. |
| `MISTRAL_API_URL` | `'https://api.mistral.ai/v1'` | Provider API base URL. |
| `MISTRAL_DOCS_URL` | `'https://docs.mistral.ai'` | Provider docs link shown in UI. |
| `OLLAMA_BASE_URL` | `'http://localhost:11434'` | Provider API base URL. |
| `OLLAMA_DOCS_URL` | `'https://ollama.com/docs'` | Provider docs link shown in UI. |
| `AZURE_OPENAI_API_URL` | `''` | Provider API base URL. |
| `AZURE_OPENAI_DOCS_URL` | `'https://oai.azure.com'` | Provider docs link shown in UI. |
| `CONTECFLOW_AI_MODEL` | `'claude-haiku-4-5'` | Default Anthropic model id. |
| `SEMANTIC_EMBEDDINGS_BACKEND` | `'tfidf'` | `tfidf` (default) or transformer backend (needs requirements-ml.txt). |
| `OPENAI_API_KEY` | `''` | OpenAI key (STT and fallback). |
| `OPENAI_STT_MODEL` | `'gpt-4o-mini-transcribe'` | OpenAI transcription model. |
| `AI_COST_ALERT_USD_PER_DAY` | `10.0` | Daily AI spend alert threshold. |

**SLA (`config_groups/sla_config.py`) — 19 variables**

| Name | Default | Meaning |
|---|---|---|
| `SLA_P1_RESPONSE_HOURS` | `1.0` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_P1_RESOLUTION_HOURS` | `4.0` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_P2_RESPONSE_HOURS` | `4.0` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_P2_RESOLUTION_HOURS` | `8.0` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_P3_RESPONSE_HOURS` | `8.0` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_P3_RESOLUTION_HOURS` | `24.0` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_P4_RESPONSE_HOURS` | `24.0` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_P4_RESOLUTION_HOURS` | `72.0` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_BUSINESS_HOURS_ONLY` | `True` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_BUSINESS_START_HOUR` | `8` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_BUSINESS_END_HOUR` | `18` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_BUSINESS_DAYS` | `'1,2,3,4,5'` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_PREDICTION_HOURS_CRITICAL` | `4` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_PREDICTION_HOURS_HIGH` | `8` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_PREDICTION_HOURS_MEDIUM` | `24` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_PREDICTION_HOURS_LOW` | `72` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_PREDICTION_WARNING_PCT` | `0.7` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_PREDICTION_SEVERITY_CRITICAL_H` | `1.0` | SLA targets / business hours / breach prediction (hours, %). |
| `SLA_PREDICTION_SEVERITY_HIGH_H` | `4.0` | SLA targets / business hours / breach prediction (hours, %). |

**Health scores (`config_groups/health_config.py`) — 23 variables**

| Name | Default | Meaning |
|---|---|---|
| `HEALTH_NPS_LOOKBACK_DAYS` | `90` | Customer-health scoring weights/thresholds. |
| `HEALTH_TICKET_LOOKBACK_DAYS` | `30` | Customer-health scoring weights/thresholds. |
| `HEALTH_DEFAULT_NO_DATA` | `70.0` | Customer-health scoring weights/thresholds. |
| `HEALTH_PORTAL_BASE_SCORE` | `30.0` | Customer-health scoring weights/thresholds. |
| `HEALTH_PORTAL_SCORE_PER_SESSION` | `7.0` | Customer-health scoring weights/thresholds. |
| `HEALTH_WEIGHT_NPS` | `0.4` | Customer-health scoring weights/thresholds. |
| `HEALTH_WEIGHT_DELIVERY` | `0.2` | Customer-health scoring weights/thresholds. |
| `HEALTH_WEIGHT_BUDGET` | `0.15` | Customer-health scoring weights/thresholds. |
| `HEALTH_WEIGHT_TICKETS` | `0.15` | Customer-health scoring weights/thresholds. |
| `HEALTH_WEIGHT_PORTAL` | `0.1` | Customer-health scoring weights/thresholds. |
| `HEALTH_THRESHOLD_EXCELLENT` | `80.0` | Customer-health scoring weights/thresholds. |
| `HEALTH_THRESHOLD_GOOD` | `60.0` | Customer-health scoring weights/thresholds. |
| `HEALTH_THRESHOLD_AT_RISK` | `40.0` | Customer-health scoring weights/thresholds. |
| `PROJECT_HEALTH_WEIGHT_SCHEDULE` | `0.3` | Project-health scoring weights/thresholds. |
| `PROJECT_HEALTH_WEIGHT_BUDGET` | `0.25` | Project-health scoring weights/thresholds. |
| `PROJECT_HEALTH_WEIGHT_QUALITY` | `0.2` | Project-health scoring weights/thresholds. |
| `PROJECT_HEALTH_WEIGHT_VELOCITY` | `0.15` | Project-health scoring weights/thresholds. |
| `PROJECT_HEALTH_WEIGHT_CLIENT` | `0.1` | Project-health scoring weights/thresholds. |
| `PROJECT_HEALTH_TRAFFIC_GREEN` | `70.0` | Project-health scoring weights/thresholds. |
| `PROJECT_HEALTH_TRAFFIC_YELLOW` | `45.0` | Project-health scoring weights/thresholds. |
| `PROJECT_HEALTH_BUDGET_RATIO_GOOD` | `0.8` | Project-health scoring weights/thresholds. |
| `PROJECT_HEALTH_BUDGET_RATIO_OK` | `1.0` | Project-health scoring weights/thresholds. |
| `PROJECT_HEALTH_BUDGET_RATIO_WARN` | `1.2` | Project-health scoring weights/thresholds. |

**Semantic engine (`config_groups/semantic_config.py`) — 9 variables**

| Name | Default | Meaning |
|---|---|---|
| `SEM_THRESHOLD_EXPERT_CACHE` | `0.92` | Semantic classifier thresholds/weights. |
| `SEM_THRESHOLD_CRITICAL` | `0.9` | Semantic classifier thresholds/weights. |
| `SEM_THRESHOLD_HIGH` | `0.72` | Semantic classifier thresholds/weights. |
| `SEM_THRESHOLD_MEDIUM` | `0.58` | Semantic classifier thresholds/weights. |
| `SEM_THRESHOLD_LOW` | `0.45` | Semantic classifier thresholds/weights. |
| `SEM_WEIGHT_PROFILE` | `0.4` | Semantic classifier thresholds/weights. |
| `SEM_WEIGHT_HISTORY` | `0.6` | Semantic classifier thresholds/weights. |
| `SEM_TOP_K_HISTORY` | `3` | Semantic classifier thresholds/weights. |
| `SEM_MULTI_ROLE_FACTOR` | `0.7` | Semantic classifier thresholds/weights. |

**Service desk (`config_groups/service_desk_config.py`) — 22 variables**

| Name | Default | Meaning |
|---|---|---|
| `SD_NOTIFY_REQUESTER_ON_CREATE` | `True` | Service desk mail toggle. |
| `SD_NOTIFY_REQUESTER_ON_REPLY` | `True` | Service desk mail toggle. |
| `SD_NOTIFY_REQUESTER_ON_RESOLVE` | `True` | Service desk mail toggle. |
| `SD_NOTIFY_AGENTS_BY_EMAIL` | `True` | Service desk mail toggle. |
| `SD_INBOUND_ADDRESS` | `''` | Support mailbox address. |
| `SD_REOPEN_ON_REPLY` | `True` | Reopen resolved ticket on reply. |
| `SD_CHANNEL_TICKET_TYPE` | `'incident'` | Ticket type for channel-created tickets. |
| `SD_MAIL_MAX_PER_RUN` | `50` | Mails read per mailbox run. |
| `SD_MAIL_MAX_ATTACHMENT_MB` | `15` | Attachment cap. |
| `SD_CAB_GROUP_ID` | `''` | CAB approver group. |
| `SD_CAB_APPROVAL_RULE` | `'majority'` | `majority`/… CAB rule. |
| `SD_CHANGE_AUTO_APPROVE_MAX_RISK` | `30` | Auto-approve changes at/below this risk. |
| `SD_EVENT_SEVERITY_MAP` | `JSON map (see code)` | JSON map monitoring severity → priority. |
| `SD_EVENT_AUTO_RESOLVE` | `True` | Auto-resolve on recovery event. |
| `SD_ONCALL_PRIORITIES` | `'p1_critical,p2_high'` | Priorities that page on-call. |
| `SD_ONCALL_SMS` | `True` | Send SMS to on-call. |
| `SD_KB_REQUIRE_REVIEW` | `False` | KB articles need review. |
| `SD_KB_REVIEWER_GROUP_ID` | `''` | KB reviewer group. |
| `SD_KB_RAG_MIN_SCORE_VECTOR` | `0.35` | Minimum cosine to cite a KB article. |
| `SD_KB_RAG_MIN_SCORE_WORDS` | `0.5` | Without sentence model: share of words to cite an article. |
| `SD_KB_RAG_MAX_SOURCES` | `3` | KB articles per AI answer. |
| `SD_KB_CORRECTION_MATCH` | `0.8` | Similarity for an expert correction to apply. |
| `SD_KB_STALE_DAYS` | `180` | Days before a published article is flagged as stale (0: off). |
| `SD_KB_CONTRADICTION_SIMILARITY` | `0.75` | Similarity for two articles to be compared with AI. |
| `SD_KB_CONTRADICTION_MAX_PAIRS` | `10` | Article pairs compared with AI per daily run (0: off). |
| `SD_TIME_TO_TIMESHEET` | `True` | Ticket time posts to timesheets. |
| `SD_ASSET_REFRESH_DAYS` | `7` | Asset refresh cadence. |
| `SD_EVENT_MAX_ATTEMPTS` | `5` | Ticket-event retry cap. |
| `SD_EVENT_BATCH_SIZE` | `200` | Ticket-event batch size. |

#### 4.3 Variables read directly with `os.getenv` (not in `Settings`)

| Name | Default | Where / meaning |
|---|---|---|
| `TESTING` | `0` | `1` disables CSRF, uses a per-request rate-limit key, skips the schema preflight and the collab scheduler. Set by `tests/conftest.py`. |
| `ENABLE_APSCHEDULER` | `1` | Run the in-process APScheduler (4 jobs). `setup.sh`/`setup.bat`/Docker set it to `0` and run Celery beat instead. |
| `ENABLE_CELERY_BEAT` / `CELERY_BEAT` | `0` | Declares that Celery beat runs; with APScheduler also on, boot fails. |
| `FAIL_ON_DUAL_SCHEDULER` | `1` | `0` lets the app boot with both schedulers (every job would run twice). |
| `FAIL_ON_SCHEMA_DRIFT` | `1` in staging/production, else `0` | Abort boot if the DB's Alembic revisions ≠ script heads. |
| `EXPECTED_ALEMBIC_REVISION` | — | Additional pinned revision to check at boot. |
| `EXPOSE_API_DOCS` | `0` | `1` exposes Swagger/ReDoc/OpenAPI in production. |
| `CSRF_DOUBLE_SUBMIT` | `0` | `1` also requires `X-CSRF-Token` = `csrf_token` cookie. |
| `DISABLE_CSRF_MIDDLEWARE` | `0` | `1` disables CSRF entirely. |
| `ENABLE_SUPERADMIN_BYPASS` | `0` | Dev-only login bypass (development + SQLite enforced at boot). |
| `TENANT_AUTO_FILTER_GLOBAL` | `1` | Global `do_orm_execute` tenant filter (`app/db/session.py:380`). |
| `TENANT_AUTO_STAMP_ON_INSERT` | `1` | `before_flush` stamping of `organization_id` on new rows. |
| `REDIS_RECONNECT_BACKOFF_SECONDS` | — | Redis reconnect backoff. |
| `PREDICTIVE_STATS_MAX_TICKETS`, `CHANGE_BATCH_SCORE_MAX` | — | Service-desk batch caps. |
| `DUCKDB_PATH` | — | OLAP DuckDB file. |
| `COLLAB_STORAGE_BACKEND` | `local` | Collaboration file store (`local`/S3 via `COLLAB_S3_BUCKET`, `COLLAB_S3_ENDPOINT`, `COLLAB_S3_REGION`, `COLLAB_S3_PREFIX`). |
| `COLLAB_SEARCH_BACKEND` | `auto` | `auto|simple|pg|opensearch`; `OPENSEARCH_URL` (`http://localhost:9200`), `OPENSEARCH_USER`, `OPENSEARCH_PASSWORD`. |
| `COLLAB_BUS_BACKEND`, `NATS_URL` | —, `nats://localhost:4222` | Collaboration event bus. |
| `COLLAB_QUEUE_WORKERS`, `COLLAB_SIGNED_MAX_ENTRIES` | — | Collaboration internals. |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | `wss://livekit.local` | Video calls. |
| `CLAMAV_ENABLED`, `CLAMAV_HOST`, `CLAMAV_PORT`, `CLAMAV_SOCKET`, `CLAMAV_TIMEOUT` | `0` | Antivirus scan of collaboration uploads. |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_CONTACT` | — | Web push. |
| `WHISPER_LOCAL`, `WHISPER_LOCAL_BIN`, `WHISPER_BIN`, `WHISPER_LOCAL_MODEL`, `WHISPER_MODEL`, `WHISPER_LOCAL_LANGUAGE` | — | Local Whisper STT. |
| `OPENAI_MODEL` | — | OpenAI model override in one path. |
| `MS365_TENANT_ID` | — | M365 tenant (read directly in one module). |
| `APP_PUBLIC_URL`, `UPLOADS_DIR` | — | Read in single modules. |
| `SEED_USERS_DATA_PATH`, `SEED_CLIENTS_DATA_PATH`, `SEED_EMAIL_TEMPLATES_PATH`, `SEED_API_KEY_DEMO` | `seed_users_data.json`, … | Seed inputs. |
| `PROMETHEUS_MULTIPROC_DIR` | — | Set from `METRICS_MULTIPROC_DIR`. |

Compose-only variables (consumed by `docker-compose.yml`, not by Python): `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`, `REDIS_PORT`, `REDIS_MAXMEMORY`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_BUCKET`, `MINIO_PORT`, `API_WORKERS`, `WORKER_CONCURRENCY`, `WEB_PORT`, `PROMETHEUS_PORT`, `CONTECFLOW_APP_IMAGE`, `CONTECFLOW_WEB_IMAGE`. Frontend (Vite): `VITE_API_URL`, `VITE_WS_URL`, `VITE_PORT`, `API_URL` (proxy target fallback).

`.env.example` (101 keys) contains keys that **no code reads**: `ALLOW_LOCAL_LOGIN`, `HTTP_PORT`, `HTTPS_PORT`, `DEBUG`, `ALGORITHM` (staff JWTs hard-code HS256; `JWT_ALGORITHM` only affects portal tokens). It also sets `ACCESS_TOKEN_EXPIRE_MINUTES=60`, which is clamped to `ACCESS_TOKEN_MAX_MINUTES` (30) for the token while the cookie `max_age` uses the unclamped 60 min.

---

### 5. Database and migrations

- **Alembic is the only schema path.** `setup.sh`, `setup.bat`, the compose `migrate` service and `make migrate` all run `alembic upgrade head`. The app never migrates at startup. Its lifespan only compares `alembic_version` with the script heads and logs, or with `FAIL_ON_SCHEMA_DRIFT=1` aborts. `alembic/env.py` takes the URL from `settings.DATABASE_URL`.
- **Chain:** 71 revision files, linear (`alembic history` = 71 steps from `<base>`), **single head `117_esign_secretos_cifrados`** (measured with `alembic heads`). There are two naming styles: legacy `NNN_name` and Alembic UUID ids (`alembic/NAMING_CONVENTION.md`; history is frozen and never renamed).
- **Commands:**
  ```bash
  python -m alembic upgrade head        # idempotent
  python -m alembic current
  python -m alembic heads               # must print exactly one head
  python -m alembic downgrade -1        # rollback one step
  python -m alembic revision -m "msg"   # or: make migrate-create MSG="msg" (uses --autogenerate)
  ```
- **Rollback caveat (measured):** 6 of the 70 `downgrade()` functions are no-ops or raise: `082_multitenancy_fix_unregistered_models`, `092_performance_backfill_organization`, `093_tickets_backfill_organization`, `097_paridad_postgres_con_los_modelos`, `100_numeracion_por_organizacion`, `112_acento_del_tema`. Downgrading through them does not restore the previous state, so back up first.
- **Parity guard:** `tests/test_alembic_schema_parity.py` builds an empty SQLite with `upgrade head` and compares it with the models. Its PostgreSQL variant **skips** unless `PARITY_POSTGRES_URL` or a `postgresql` `DATABASE_URL` is available.
- **Seeding:**
  - `python -m app.db.seed` (used by `setup.sh demo`) runs `seed()` → `seed_service_desk` → `seed_v10` → `seed_itsm_v2` → `seed_alm` → `seed_enterprise` → `seed_v12` → `seed_v13` → `seed_v14/15/16`. The core part creates the organisation **"Consultora Contecflow SL"** (slug `contecflow-demo`, plan enterprise), app settings, 8 departments, Spanish national holidays for 2025–2026, the 9 users of `seed_users_data.json`, and the clients of `seed_clients_data.json` (2 entries), followed by projects, service-desk, ITSM, ALM, enterprise and configuration data. The seed is idempotent per record (lookups before insert). It has **no ENVIRONMENT gate**.
  - `python scripts/seed_full_data.py` (what `make seed` and `DOCS.md` call) is a different, heavier generator: 15 extra users, 8 clients, 15 projects, ~2,500 time entries Jan 2025–Mar 2027, ~150 tickets, ~35 invoices, sprints, UAT, and so on.
  - `python scripts/reset_to_admin_only.py` (`setup.sh clean`) truncates all data and keeps or creates only `admin` and the default organisation. **No ENVIRONMENT gate.**
- **Backups:** there is no backup tooling for the current stack. `scripts/deploy.sh` has a `pg_dump` step, but it targets compose services named `db`/`backend`/`nginx` and `/api/v1/health`, none of which exist in today's `docker-compose.yml` (`postgres`/`api`/`web`, `/health`). It also calls `app.main._read_alembic_revision`, which is now `_read_alembic_revisions`. **The script cannot work as written.** Use it manually, for example `docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup.sql`, and copy the `contecflow_s3_data` volume or `uploads/`.

---

### 6. API

#### 6.1 Surface (measured by importing `app.main:app`)

2,051 HTTP routes: 2,043 under `/api/v1`, 3 under `/api/v2` (`/version`, 2× `/profitability`), 5 outside (`/health`, `/ready`, `/status`, `/status/embed.js`, `/widget/ticket.js`). By method: GET 874 · POST 757 · DELETE 201 · PATCH 177 · PUT 39. 6 WebSockets: `/api/v1/ws/notifications`, `/api/v1/ws/portal-notifications`, `/api/v1/ws/doc/{doc_id}`, `/api/v1/collaboration/ws`, `/api/v1/bi/collaboration/dashboards/{dashboard_key}/updates`, `/api/v1/bi/intelligence/realtime/stream`. `/metrics` is added only with `METRICS_ENABLED=1`.

Routes per first path segment under `/api/v1` (122 segments; top 30):

| Segment | Routes | Segment | Routes | Segment | Routes |
|---|---|---|---|---|---|
| `sd` (service desk) | 357 | `alm` | 35 | `abac` | 21 |
| `bi` | 195 | `performance` | 34 | `esign` | 18 |
| `collaboration` | 100 | `settings` | 32 | `raci` | 17 |
| `portal` | 90 | `cmdb` | 31 | `m365` | 17 |
| `enterprise` | 47 | `bookings` | 30 | `security-observability` | 17 |
| `advanced-config` | 40 | `approvals` | 29 | `users`, `tasks`, `imputations`, `revenue-recognition`, `ai-chat` | 16 each |
| `epics` | 40 | `clients` | 28 | `expenses` | 15 |
| `projects` | 36 | `auth` | 25 | `semantic`, `governance` | 14 each |
| `billing-reports` | 35 | `documents` | 25 | `sprints`, `ai`, `integrations`, `scim` | 13 each |
| | | `pipeline` | 24 | `analytics`, `activity`, `ai-modules` | 22 each |

The remaining 92 segments have ≤ 12 routes each. `/api/v1` responses carry `x-api-version: 1`, `x-api-deprecated: true` and `deprecation: true`; `/api/v2` carries `x-api-version: 2`. v2 is a 3-route stub, not a replacement.

#### 6.2 OpenAPI

`/api/v1/docs` (Swagger), `/api/v1/redoc`, `/api/v1/openapi.json`. These are disabled when `ENVIRONMENT=production` unless `EXPOSE_API_DOCS=1`. The docs routes get a relaxed CSP that allows cdn.jsdelivr.net (`make docs` checks it).

#### 6.3 Authentication

- **Staff:** `get_current_user` (`app/core/deps.py`) accepts `Authorization: Bearer <JWT>` **or** the `access_token` cookie. It requires `type=access` and an active user. JWTs are HS256 with a `kid` header from a DB keyring (`app/services/key_management.py`: active key plus grace keys, rotated every `JWT_KEY_ROTATION_DAYS`, `JWT_KEY_RETENTION_COUNT` kept).
- **Cookies** (set by `auth_service.set_auth_cookies`): `access_token` (httpOnly, SameSite=Lax, `max_age` = `ACCESS_TOKEN_EXPIRE_MINUTES`); `refresh_token` (httpOnly, SameSite=**Strict**, `path=/api/v1/auth/refresh`); `csrf_token` (JS-readable). `Secure` is set in staging/production.
- **CSRF** (`app/core/csrf.py`): for POST/PUT/PATCH/DELETE **that use cookie auth and no `Authorization` header**, `Origin` (or `Referer`) must be in `ALLOWED_ORIGINS`, otherwise 403. A missing Origin is also rejected. `CSRF_DOUBLE_SUBMIT=1` adds a header/cookie match (constant-time). Exempt prefixes: webhooks, SCIM, `/health`, `/status`, `/metrics`. API clients that send a Bearer token are unaffected. Three of those prefixes do not match real routes (`/api/v1/integrations_hub/…`, while the real path is `integrations-hub`; `/api/v1/esign/docusign/webhook`, while the real path is `/api/v1/esign/webhooks/docusign`; `/api/v1/service-desk/…`, while the real path is `/api/v1/sd/…`). Webhook callers do not send cookies, so the practical effect is nil.
- **Login endpoints:** `POST /api/v1/auth/login` (5/min), `/auth/refresh`, `/auth/logout`, `/auth/me`; SSO (`auth_sso`: OIDC with JWKS, PKCE S256, one-time HMAC `state`, `nonce`, issuer and clock skew — see Enterprise → SSO); passkey sign-in without password (`/auth/passkey/login/*`); `auth_saml` only serves a metadata stub, SAML sign-in is not implemented; session management (`auth_sessions`).
- **MFA:** TOTP and WebAuthn under `/api/v1/auth/mfa/*` (QR returned as a `data:` PNG), plus a second, older set at `/api/v1/mfa/*` that the SPA's MFA page uses (see §7.6). Per-org enforcement exists (`074_org_require_mfa`).
- **Roles:** `UserRole` = `admin` (tenant admin), `pm`, `team_lead`, `hr`, `employee`, `subcontractor`; `is_superadmin` is a separate platform flag. Shortcuts: `require_admin`, `require_admin_or_hr`, `require_admin_or_pm`, `require_any_manager`, `require_internal_user`, `require_superadmin`.
- **Client portal:** separate JWTs (`CLIENT_PORTAL_SECRET`, `JWT_ALGORITHM`, cookie `portal_access_token`, `get_current_client`).
- **API keys:** `X-API-Key` (keys from `/api/v1/bookings/api-keys`) and developer-portal bearer tokens authenticate on the whole API as their owner, cut down by scope (see Enterprise → API Keys). Other domain-specific tokens: BI embed tokens, the SCIM bearer (`SCIM_BEARER_TOKEN`, `/api/v1/scim/v2/{org_id}/…`), OAuth apps in the developer portal (`MAX_APPS_PER_USER`), and the client-portal widget token (`/widget/ticket.js`).

#### 6.4 Response envelope

`app/core/responses.py` defines `APIResponse[T] = {data, meta?}` and `APIListResponse[T] = {items, meta:{total, page, page_size, has_more}}`. Adoption is not total: there are 1,860 `APIResponse/APIListResponse.ok(` calls under `app/api` for 2,051 routes, and `docs/RESPONSE_WRAPPER_MIGRATION.md` describes an incremental migration. No test enforces the envelope. Errors are `{"detail": …}` (sanitised by `sanitize_http_detail`); unhandled exceptions return `{"detail": "Internal Server Error", "request_id": …}`.

#### 6.5 Rate limits

slowapi `Limiter` with Redis storage when `REDIS_URL` is reachable (in-memory otherwise; boot fails in production without Redis unless `RATE_LIMIT_REQUIRE_REDIS_IN_PRODUCTION=0`). There are **117 explicit `@limiter.limit` decorators** (login 5/min, etc.). `RATE_LIMIT_DEFAULT` (`200/minute`) is passed as `default_limits`, but **`SlowAPIMiddleware` is not registered** (0 occurrences). In slowapi, default limits apply through that middleware, so undecorated routes are most likely **unlimited**. **Not verified at runtime.** The key is `get_remote_address` (the socket peer). Behind the compose nginx that peer is the nginx container, and uvicorn is started without `--forwarded-allow-ips`, so per-IP limits are probably shared by all clients. **Not verified.**

#### 6.6 WebSockets

1. `GET /api/v1/ws/ticket` (authenticated) returns a **one-time ticket**: `secrets.token_urlsafe(24)`, TTL **60 s** (hard-coded in `app/services/ws_service.py`), stored in Redis under `contecflow:ws:ticket:user:` or in process memory without Redis. Portal equivalent: `/api/v1/ws/portal-ticket`.
2. Connect with `?ticket=…`; the ticket is consumed on use. `/api/v1/ws/token` also issues a 5-minute JWT with `ws: true`.
3. Without Redis and with more than 1 uvicorn worker, tickets issued by one worker are unknown to the others.
4. WebSockets go through the same router guards (`tests/test_websockets_pasan_las_guardas.py`).
5. The compose nginx adds `Upgrade` headers **only** for `/api/v1/ws/`. `/api/v1/collaboration/ws` and the two `/api/v1/bi/…` sockets go through `location /api/` without them, so they will probably fail behind that proxy. **Not verified at runtime.**

#### 6.7 Webhooks

- **Outbound** (`/api/v1/enterprise/webhooks`): delivery is always a Celery task (`deliver_webhook`, `max_retries=3`, backoff 60 s / 300 s / 1,800 s). Requests carry the headers `X-Contecflow-Event` and `X-Contecflow-Signature: sha256=<HMAC>`. A circuit breaker suspends the hook after `WEBHOOK_CB_THRESHOLD` (5) consecutive failures and notifies admins; reactivate it from the panel. **Needs a running Celery worker.**
- **Inbound:** GitHub/GitLab (`/api/v1/git/webhooks/*`), Jira (`/api/v1/jira/webhook`, `/api/v1/integrations/jira/webhook`), DocuSign/Adobe (`/api/v1/esign/webhooks/*`), Slack/Teams commands (`/api/v1/integrations-hub/*`), M365 Teams, collaboration incoming (`/api/v1/collaboration/webhooks/incoming/{token}`), SCIM. Each verifies its own secret or HMAC (variables in §4.2).

---

### 7. Security model

#### 7.1 Multi-tenancy (`app/db/session.py`)

- 395 mapped classes: 383 have `organization_id`, 11 only `org_id`, 1 declared exempt (`Organization`, `_tenant_exempt = True`), 0 with neither (measured).
- **`TenantSession`** overrides `query()` and `execute()` and adds the tenant filter. It is **fail-closed**: a model it cannot scope raises `TenantIsolationError`.
- **Global `do_orm_execute` listener** (`TENANT_AUTO_FILTER_GLOBAL=1`) adds `with_loader_criteria(model, cls.organization_id == org_id)` to every ORM **SELECT** for the 383 `organization_id` models. Models with `_tenant_filter_include_global` also see `organization_id IS NULL` rows. A user without an organisation gets `WHERE false`. The org id is a **closure** variable, not a default argument: the default-argument version baked the first tenant's id into SQLAlchemy's statement cache and leaked rows between tenants (comment in the code).
- **Skipped when:** the statement is not a SELECT, it is a relationship load, `session.info["bypass_tenant_filter"]` is set (helper `sin_filtro_de_tenant(session)`), the user is superadmin, or `session.info["is_superadmin"]` is unset. That last case covers **Celery/background sessions** (`worker_db_session`), which run unfiltered by design and must scope by organisation themselves.
- **Insert stamping** (`before_flush`, `TENANT_AUTO_STAMP_ON_INSERT=1`) fills a missing `organization_id` from the session.
- The session context is set by `get_current_user` (`db.info["organization_id"]`, `is_superadmin`, `current_user`); portal requests use `publicar_contexto_de_tenant`.
- Guards: `test_tenant_filter_coverage.py`, `test_tenant_filter_fail_closed.py`, `test_tenant_isolation.py`, and 13 `*_por_tenant.py` / `*_tenant_isolation.py` files.

#### 7.2 Global route guards (`app/main.py::_ROUTER_GUARDS`)

Applied as router dependencies to **all** `/api/v1` and `/api/v2` routes, HTTP and WebSocket, in this order:

1. `bind_request_timezone` (`app/core/timezone_context.py`, `async` on purpose): publishes user → organisation → UTC timezone in a `ContextVar` so `timeutil.today()` is the caller's day.
2. `apply_abac_for_route` (`app/core/abac_dependency.py`): route-prefix ABAC as a dependency. It replaces an `ABACMiddleware` that never ran because `request.state.user` was never set. ABAC is **fail-open**: without active policies it restricts nothing. There are also explicit `enforce_abac(...)` calls in endpoints (`tests/test_abac_coverage.py`).
3. `enforce_grc_matrix` (`app/core/grc_enforce.py`): the admin-editable GRC matrix, **additive deny only**. Module and action are derived from the path and method (`grc_catalog.py`); a row with `allowed=False` returns 403.

On top of these: per-endpoint role dependencies (§6.3). `tests/test_guardas_de_rol.py` requires every write route to carry a role guard or a written exemption, and `tests/test_route_auth_coverage.py` requires every `/api` route to declare authentication as a dependency or be explicitly public. Segregation of duties: requesters cannot approve their own request (`approval_engine/requests.py`). Admin-defined SoD rules are only partially evaluated (`tests/test_grc_coverage.py`).

#### 7.3 HTTP hardening (measured in `security_headers_middleware`)

`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` (`SAMEORIGIN` for document file/preview), `Referrer-Policy: strict-origin-when-cross-origin`, HSTS (production only), `Permissions-Policy: camera=(), microphone=(self), geolocation=()`, COOP/CORP `same-origin`, `X-Permitted-Cross-Domain-Policies: none`, and a strict CSP (`script-src 'self'`). CORS: `ALLOWED_ORIGINS`, credentials on, methods GET/POST/PUT/PATCH/DELETE/OPTIONS, headers `Content-Type, Authorization, X-Request-ID, X-Requested-With`. Note that `X-CSRF-Token` is **not** in the allowed headers, so cross-origin double-submit would fail preflight. Same-origin, the normal deployment, is unaffected. The request logger redacts `token`, `access_token`, `refresh_token`, `code`, `state` and `id_token` query parameters.

#### 7.4 Audit logging

`app/services/audit.py::audit_log()` writes `AuditLog` rows (user, action, resource, old/new values, IP, UA). It is **opt-in per call site**: 51 call sites, not a global hook. Settings changes have their own audit (`settings_audit_service.py`).

#### 7.5 Secrets and key rotation

- **Field encryption** (`app/core/encryption.py`): `v2:<salt>.<fernet>` with HKDF from **`SECRET_KEY`** plus a per-record salt; legacy v1 uses PBKDF2 from `SECRET_KEY`; `kmsv1:` when `KMS_PROVIDER=aws`. `decrypt_value` returns `None` on failure (and treats undecryptable non-prefixed values as plaintext).
- **Rotation:** the app rotates the JWT keyring and re-encrypts integration secrets (new salt, same `SECRET_KEY`) on schedule (APScheduler or beat, §8).
- **Rotating `SECRET_KEY`** (since 2026-11-03): run `bash scripts/rotate_keys.sh` from the repository root with the database reachable. It copies `.env` to `.env.bak.<timestamp>` (mode 600; it holds the old key), writes a new random `SECRET_KEY`, prepends the old one to `SECRET_KEY_PREVIOUS`, and runs `scripts/reencrypt_secrets.py`. That script walks every text column of every table with a single-column primary key, finds values encrypted with a previous key (`v2:…` of `app.core.encryption`, and bare Fernet tokens of the v1 format or of the collaboration integrations), re-encrypts them with the current key and prints, per column, how many encrypted values it looked at. No key is printed. Then restart API, worker and beat; open sessions end. `venv/bin/python scripts/reencrypt_secrets.py --check` counts without writing and exits 1 while anything still needs the old key; when it reports 0, `SECRET_KEY_PREVIOUS` can be emptied. Until then the application decrypts with both (`encryption.claves_secretas()`); ML model signatures and collaboration tokens also accept the previous keys. Values under `kmsv1:` do not depend on `SECRET_KEY`. If the key also lives in a secrets manager or server variables, update it there by hand. Test: `tests/test_rotacion_de_secret_key.py` (the shell script was exercised on a scratch copy, not on a real deployment). `make rotate-keys` only prints a reminder.
- **`.env` is versioned on purpose** (`.gitignore` header: private repository, so a fresh clone boots with the same configuration); `.env.*` files (`.env.local`, `.env.produccion`) are ignored. Anyone with read access to the repo therefore has the development secrets — treat repository access as secret access and never commit production values to `.env`. `.gitleaks.toml` is present; `setup.sh` generates missing secrets per installation.

#### 7.6 Known security issues found while measuring

- ~~**MFA QR via a third party.**~~ Fixed 2026-11-03: `/api/v1/mfa/setup` now returns a local `data:` PNG, like `/api/v1/auth/mfa/setup`; the `GOOGLE_CHART_URL` setting was removed.
- `/health` and `/ready` are unauthenticated and include the raw database or Redis exception text when a check fails.
- The CSRF exemption list contains stale paths (§6.3).

---

### 8. Background jobs

#### 8.1 Scheduler modes

- **APScheduler** (in the API process, `ENABLE_APSCHEDULER=1` default, `SQLAlchemyJobStore` on the main DB) runs 4 jobs: `scheduled_reports` (every hour at :00), `scheduled_key_rotation` (`KEY_ROTATION_RUN_HOUR_UTC`:17), `scheduled_alert_engine` (08:00), `scheduled_perf_reminders` (09:00).
- **Celery beat** (`ENABLE_CELERY_BEAT=1`, separate `beat` container) runs the 52 entries below. The app refuses to boot when both are enabled (`FAIL_ON_DUAL_SCHEDULER=1`), but that check only sees the API process's own env. The compose stack now sets `ENABLE_APSCHEDULER=0` and `ENABLE_CELERY_BEAT=1` for every app container (before 2026-11-03 it set neither, so the API ran APScheduler **and** the `beat` container ran beat, and the 3 jobs present in both (reports, key rotation, alert engine) run twice. With 4 API workers, APScheduler itself starts 4 times; the code says the shared job store reduces but does not guarantee single execution. **Set `ENABLE_APSCHEDULER=0` and `ENABLE_CELERY_BEAT=1` in `.env` for the Docker stack.** The effect is **not verified at runtime.**
- **Timezone:** `celery_app.conf.timezone = DEFAULT_TIMEZONE` (Europe/Madrid by default) and `BackgroundScheduler(timezone=DEFAULT_TIMEZONE)`. All hours below are **in `DEFAULT_TIMEZONE`**, despite comments and names saying UTC (`revenue-monthly-recognition` "02:00 UTC", `KEY_ROTATION_RUN_HOUR_UTC`).
- Broker and result backend: `REDIS_URL`. Without it Celery cannot enqueue. `run_agent_task` uses `CELERY_AGENT_TASK_TIME_LIMIT`/`SOFT`.

#### 8.2 Celery beat schedule (`app/worker.py`, 52 entries, 34 tasks; `deliver_webhook` and `run_agent_task` are on-demand only)

| Entry | Task | Cadence | Purpose |
|---|---|---|---|
| run-alert-engine-daily | run_alert_engine | daily 08:00 | Alert engine |
| weekly-load-report | send_weekly_report | Mon 09:00 | Weekly load summary to managers |
| check-missing-imputations | check_missing_imputations | Mon–Fri 18:00 | Remind users who did not log today's time |
| generate-retainer-invoices | generate_retainer_invoices | daily 07:00 | Recurring retainer invoices (by `retainer_day`) |
| run-scheduled-reports | run_scheduled_reports | hourly :00 | Due scheduled reports |
| run-key-rotation | run_scheduled_rotation | daily `KEY_ROTATION_RUN_HOUR_UTC`:17 | JWT keyring and integration-secret rotation |
| jira-periodic-sync | jira_periodic_sync | every 30 min | Pull updated Jira issues |
| process-approval-timeouts | process_approval_timeouts | hourly :00 | Escalate approval steps past timeout |
| revenue-monthly-recognition | revenue_monthly_recognition | daily 02:00 | ASC 606 close for orgs on their day 1 (idempotent) |
| ml-model-retrain | ml_model_retrain | day 1, 03:00 | Monthly ML retrain |
| olap-nightly-etl | olap_nightly_etl | daily 01:00 | Incremental load to DuckDB |
| sla-breach-scan | sla_breach_scan | every 5 min | SLA state, risk/breach notices, escalation |
| sd-leer-buzones | sd_leer_buzones | every 2 min | Read each org's support mailbox (IMAP/M365) |
| sd-ticket-events | sd_procesar_eventos_de_ticket | every minute | Ticket-event outbox safety net (notices, mail, webhooks) |
| problem-auto-detect | problem_auto_detect | hourly :05 | Cluster recurring incidents into Problems |
| cmdb-discovery | cmdb_discovery_run | every 15 min | CMDB discovery (per-provider `next_run_at`) |
| change-impact-batch-score | change_impact_batch_score | every 10 min | Score pending change requests |
| routing-outcome-scan | routing_outcome_scan | hourly :20 | Backfill ML routing outcomes |
| predictive-scan | predictive_scan | every 30 min | Predictive scan of open tickets |
| predictive-model-eval-retrain | predictive_model_eval_retrain | every 6 h at :10 | Evaluate/retrain predictive models |
| asset-expiry-scan | asset_expiry_scan | daily 07:05 | Renewal ticket per expiring ALM asset |
| analytics-snapshot | analytics_snapshot | hourly :50 | ITSM KPI snapshot |
| catalog-popularity | catalog_popularity_update | every 6 h at :00 | Service catalog popularity |
| compliance-check | compliance_check | Mon 06:00 | ITIL/ISO 20000 compliance report |
| bi-scheduled-delivery | bi_scheduled_delivery_run | hourly :45 | BI report delivery (Slack/Teams/email) |
| bi-kpi-push | bi_kpi_push | every 5 min | KPI snapshot per org to the Redis BI channel |
| bi-ml-retrain | bi_ml_retrain | Sun 03:30 | Refresh BI ML training data |
| autonomous-agent-scan | autonomous_agent_scan | every 5 min | Autonomous agent on new open tickets |
| kedb-expiry-scan | kedb_expiry_scan | daily 06:30 | Demote expired KEDB entries |
| kedb-effectiveness-scan | kedb_effectiveness_scan | daily 07:00 | Recompute KEDB effectiveness |
| alert-correlation-scan | alert_correlation_scan | every 30 min | Correlate alerts into Problems |
| bi-connector-sync-* (21 entries) | sync_connector_data | hourly at minutes :01…:21 | One per connector: salesforce, hubspot, jira, stripe, xero, zendesk, freshdesk, servicenow, pipedrive, zoho_crm, quickbooks, github, gitlab, datadog, monday, asana, trello, shopify, intercom, clickup, google_analytics |

The collaboration module also has its own in-process scheduler (`app/services/collaboration/_scheduler.py`, started in the lifespan, skipped when `TESTING=1`).

---

### 9. Observability

- **Logging:** stdlib `logging`, plain-text format `%(asctime)s [%(levelname)s] %(name)s: %(message)s` (time only, no date, no JSON). Level from `LOG_LEVEL`; the SPA can change it at runtime through `/api/v1/settings/log-level`. Each request is logged with method, path, status, duration and the first 8 characters of the token subject. 4xx responses also log the URL with secret query parameters redacted. `/health`, `/ready`, `/metrics` and `/favicon.ico` are not logged.
- **Prometheus** (`app/core/metrics.py`, `docs/OBSERVABILITY_PROMETHEUS.md`): `METRICS_ENABLED=1` registers `/metrics` and the instrumentator (`http_requests_total`, `http_request_duration_seconds`, `contecflow_http_requests_inprogress`) plus domain metrics: `contecflow_app_info`, `contecflow_tickets_created_total`, `contecflow_invoices_created_total`, `contecflow_business_event_total`, `contecflow_abac_denials_total`, `contecflow_scheduled_job_duration_seconds` (APScheduler hook), `contecflow_external_api_calls_total`, `contecflow_external_api_latency_seconds`. Optional Bearer: `METRICS_AUTH_TOKEN` (the runtime key wins). Multi-worker: `METRICS_MULTIPROC_DIR`. The bundled `ops/prometheus/prometheus.yml` scrapes `api:8000/metrics` **without credentials**, so setting a token makes that target fail until you add `authorization` to the job. Postgres and Redis exporters run under the `observability` profile. There is no S3 metrics job and no Alertmanager service.
- **Tracing / errors:** OpenTelemetry (FastAPI + SQLAlchemy instrumentation) when `OTEL_ENABLED` and `OTEL_EXPORTER_OTLP_ENDPOINT` are set; Sentry when `SENTRY_DSN` is set (traces 0.1, profiles 0.05, no PII).
- **Health:** `GET /health` returns `{status:"ok", version, project, db}` and **is always 200**, even when the DB fails (only the `db` field shows the error). `GET /ready` returns 503 if the DB fails, if Redis is configured and unreachable, or on dual scheduler in staging/production, with `checks.db`, `checks.redis`, `checks.celery_broker` (a Redis ping only, not the worker) and `checks.scheduler.mode`. `GET /status` is a public HTML status page (`?org=<slug>`) backed by `/api/v1/sd/status-page`, with an embeddable widget at `/status/embed.js`. The compose nginx proxies only `/api/` and `/health`, so `/status`, `/ready`, `/metrics` and the `.js` widgets are **not reachable through `web`** (`/status` falls through to the SPA's `index.html`; `/widget/ticket.js` and `/status/embed.js` hit the static-asset rule and return 404). Derived from `nginx.frontend.conf`; **not verified at runtime.**

---

### 10. Testing

| Suite | How to run | Measured |
|---|---|---|
| Backend (pytest 9.0.3) | `make test` (= `pytest tests/ -n auto`, xdist 3.8.0) · `make test-serial` · `make test-module M=test_okrs` · `pytest tests/test_auth.py -q` | 304 files, **4,021 tests collected** (`pytest --collect-only`, 3 s). Each test uses an in-memory SQLite (`TEST_DB_URL = "sqlite://"`); `TESTING=1` is forced by `conftest.py`. Full-suite run time **not measured** here. |
| Contract | `tests/test_api_contract_schemathesis.py` (schemathesis 4.25.2, hypothesis) | in the main suite |
| Frontend unit (Vitest 4, jsdom) | `cd frontend && npm test` | 32 `*.test.*` files (`src/**/*.test.{js,jsx,ts,tsx}`) |
| Frontend static | `npm run typecheck`, `npm run lint`, `npm run check:i18n*` (8 scripts), `npm run lint:a11y`, `npm run check:chunks`, `npm run validate:jsx` | — |
| E2E (Python Playwright) | backend + frontend running, then `BASE_URL=http://localhost:3000 ADMIN_PASS=… pytest -c tests_e2e/pytest.ini tests_e2e/` · `make test-e2e` (headed) · `scripts/run-ui-tests-*.sh` | 13 files; Chromium (`playwright install chromium`) |
| Local gates | `./scripts/ci_local.sh` (`--fast`, `--info`) or `make audit` | blocking vs informative gates; no CI/CD by design |

Things that do not work as written (measured):

- `npm run test:e2e` runs `playwright test` but the frontend has no `playwright.config.*` and no `*.spec.ts`. The working E2E suite is the Python `tests_e2e/`.
- `make test-fast` passes `--timeout=10`, but `pytest-timeout` is not installed in the venv (`ModuleNotFoundError`).
- `ruff` is not installed in the venv, so the first blocking gate of `scripts/ci_local.sh` (`python -m ruff check`) fails until you `pip install ruff`.
- `make init-admin` calls `init_admin.sh`, which does not exist. Use `python scripts/reset_to_admin_only.py` (destructive).

Structural guard tests worth knowing (all in `tests/`):

| Test | Guards |
|---|---|
| `test_capa_api_sin_acceso_a_base.py` | AST scan: `app/api/` performs **zero** DB access (only transaction boundaries `commit`/`rollback`/`close`/`refresh` are allowed) |
| `test_route_auth_coverage.py` | Every `/api` route declares auth as a dependency or is intentionally public |
| `test_guardas_de_rol.py`, `test_guardas_deniegan.py` | Every write route has a role guard or a written exemption; guards really deny |
| `test_abac_coverage.py`, `test_abac_dependency_effective.py` | ABAC coverage against the real mechanism |
| `test_grc_enforcement.py`, `test_grc_coverage.py` | GRC matrix enforced over HTTP; SoD limits |
| `test_tenant_filter_coverage.py`, `test_tenant_filter_fail_closed.py`, `test_tenant_isolation.py` | Every model reachable by the tenant filter; fail-closed |
| `test_websockets_pasan_las_guardas.py` | WS handshakes pass the global guards |
| `test_alembic_schema_parity.py` | `upgrade head` from empty = models (PostgreSQL variant skips without a server) |
| `test_rutas_del_frontend.py`, `test_rutas_tapadas.py`, `test_router_conflicts.py` | Frontend calls hit existing routes; no shadowed or duplicate routes |
| `test_i18n_complete.py` | es/en/zh files share namespaces and critical keys |
| `test_seed_fixture_parity.py` | Security properties of default seed users |
| `test_docker_stack.py` | Compose/nginx invariants (definition only, not a live `up`) |

---

### 11. Extending

- **Endpoint:** add it to an existing module in `app/api/v1/endpoints/` or create one and include its `router` in the right aggregator in `app/api/v1/routers/` (`core`, `delivery`, `ai_domain`, `platform`, `framework`). Do not touch `app/api/v1/router.py`. Declare auth and role as `Depends(...)` (`get_current_user` plus a `require_*` guard on writes), or the guard tests fail. Return `APIResponse.ok(...)` / `APIListResponse.ok(...)`. Add `@limiter.limit(...)` if it must be rate-limited (§6.5). The global timezone, ABAC and GRC guards attach automatically, and the GRC module is derived from the first path segment.
- **No DB access in `app/api/`:** call a service. `tests/test_capa_api_sin_acceso_a_base.py` fails on any `db.query`/`db.add`/`execute`… in the API layer (`scripts/audit_db_access_in_api.py` gives the same count).
- **Service:** `app/services/<domain>_service.py` (or a sub-package), taking `db: Session` and ids. Use `db.info["organization_id"]` or the tenant session rather than trusting a client-supplied `org_id` (`app/core/tenancy.py` has guards). Background code runs **unfiltered** and must scope itself.
- **Model:** add it under `app/models/`, import it so it registers on `Base`, give it `organization_id` (or `org_id`). An unscoped model raises `TenantIsolationError` at query time and fails `test_tenant_filter_coverage.py`. Only a truly global model may set `_tenant_exempt = True`, with a reason.
- **Migration:** `python -m alembic revision -m "NNN_description"` (follow `alembic/NAMING_CONVENTION.md`). Write both `upgrade` and `downgrade`, keep a single head, run `alembic upgrade head` on an empty DB and `pytest tests/test_alembic_schema_parity.py`. Never `create_all`. Guard Postgres-only DDL by dialect (see revision 116).
- **Configuration knob:** add a field to `Settings` (or the right mixin). If admins should edit it, register it in `RUNTIME_FLAG_GROUPS` and read it with `get_runtime_int/str/bool/float(db, KEY, org_id)`. Avoid `get_runtime_*` inside loops or under locks: each uncached read is a query.
- **Celery job:** define `@celery_app.task(name="app.worker.<name>")` in `app/worker.py` (`include=["app.worker"]` only discovers that module) and add a `beat_schedule` entry. Remember the cadence is in `DEFAULT_TIMEZONE`. Open DB sessions with `worker_db_session()`.
- **Frontend page:** create `src/pages/<Name>Page.tsx`, register it as a `lazy()` `<Route>` in `src/App.tsx`, call the API through `src/services/api` (axios) and TanStack Query. Add strings to **all three** `src/i18n/langs/{es,en,zh}.mjs` (≈ 272–288 KB each) and run `npm run check:i18n` and the `check:i18n:*` scripts. Follow `docs/GUIA_DE_DISENO.md` (tokens in `src/index.css`, components in `src/components/ui/`, short guide in `components/ui/DESIGN_SYSTEM.md`). `tests/test_rutas_del_frontend.py` flags calls to backend routes that do not exist.

---

### 12. Troubleshooting

| Symptom | Cause (measured) | Fix |
|---|---|---|
| Backend exits at boot with `SECRET_KEY …`, `… placeholder`, `ALLOWED_ORIGINS …` | `Settings` validators (§4.1) | Fix `.env`; `./setup.sh update` regenerates weak or placeholder values |
| `Dual scheduler mode detected` | `ENABLE_APSCHEDULER=1` and `ENABLE_CELERY_BEAT=1` in the same process | Disable one |
| `ENABLE_SUPERADMIN_BYPASS=1 is only allowed …` | Bypass outside development+SQLite | Remove the flag |
| `Schema drift detectado` / `No existe tabla alembic_version` | DB behind the Alembic heads (fatal in staging/production) | `python -m alembic upgrade head` |
| A page with a Plotly chart (CMDB topology, box, violin, 3D) breaks in dev with `ReferenceError: global is not defined` | `plotly.js/lib/*` is CommonJS that reads Node's `global`; Vite's dev pre-bundle does not translate it (the production build does). Fixed 2026-11-04 with `src/charts/globalShim.ts`, imported before plotly | Reload the page |
| `./setup.sh start` served an old schema after `git pull` | `start` did not migrate (fixed 2026-11-04: it now runs `alembic upgrade head` and refuses to start if it fails) | Restart with `./setup.sh stop && ./setup.sh start` |
| Backend not ready after 60 s | Port 8000 busy, import error | `tail -20 /tmp/contecflow-backend.log`, `lsof -i :8000` |
| `SQLite quick_check` fails | WAL/SHM leftovers | `setup.sh` removes `contecflow.db-wal/-shm` itself. Its fallback message suggests `python -m app.db.migrate`, which is the legacy `create_all` path the project abandoned; use `rm -f contecflow.db* && python -m alembic upgrade head` instead |
| `setup.sh` silently ends up on SQLite | Docker daemon not ready, `up` failed, or Postgres not ready in 30 s | Check `docker compose ps`, re-run |
| `external volume "contecflow_postgres_data" not found` | Volumes are `external: true` | `docker volume create contecflow_postgres_data contecflow_s3_data` |
| S3 download 400/403, "region … is wrong" | SigV4 and region mismatch | Keep `AWS_REGION` equal for app and gateway |
| Webhooks, mailbox, SLA scans never run locally | Celery worker or beat not running (e.g. Redis down when `setup.sh` started) | See `/tmp/contecflow-worker.log` and `/tmp/contecflow-beat.log`; restart with `./setup.sh start` |
| Rate-limit or WS-ticket problems with several workers | No Redis (`/ready` shows `redis: disabled`) | Set `REDIS_URL` |
| 401 on every call from a custom `frontend/.env` | `VITE_API_URL` without `/api/v1` | Unset it or append `/api/v1` |
| Seed dies with `UnicodeEncodeError` on Windows | Console code page | `setup.bat` sets `PYTHONUTF8=1`; the seed reconfigures stdout |
| 403 "CSRF protection: missing Origin/Referer" | Cookie-auth unsafe request without Origin (curl, scripts) | Use `Authorization: Bearer`, or send `Origin` from `ALLOWED_ORIGINS` |

DOCS.md §16 lists generic steps (activate the venv, check `DATABASE_URL`, `alembic current`, check `REDIS_URL`, `npm install`/`npm run build`). They are correct but shallow. Its "Seed falla → `scripts/seed_full_data.py`" points at the heavy generator, not the seed `setup.sh` uses (`python -m app.db.seed`).

---

### 13. Known technical limitations

#### 13.1 Measured limitations

1. ~~Local setup has no Celery.~~ Fixed 2026-11-03: the setup scripts start worker and beat (§3.2).
2. ~~Docker stack runs scheduled jobs twice by default.~~ Fixed 2026-11-03: compose sets the scheduler flags (§8.1).
3. **Schedules are in `DEFAULT_TIMEZONE`**, not UTC, contrary to names and comments (§8.1).
4. **`RATE_LIMIT_DEFAULT` is probably inert** (no `SlowAPIMiddleware`); only 117 decorated routes are limited, and behind nginx the key is the proxy IP (§6.5).
5. **nginx forwards WebSocket upgrades only for `/api/v1/ws/`**; 3 other WS endpoints and `/status`, `/ready` and the widgets are not routed (§6.6, §9).
6. ~~Rotating `SECRET_KEY` breaks stored ciphertexts.~~ Fixed 2026-11-03: `SECRET_KEY_PREVIOUS` and `scripts/reencrypt_secrets.py` (§7.5).
7. ~~MFA setup on the SPA leaks the TOTP secret to `chart.googleapis.com`.~~ Fixed 2026-11-03: the QR is generated locally (§7.6).
8. **`setup.sh clean`, `setup.bat start clean` and the seed have no ENVIRONMENT gate.** Only `sync_demo_passwords` is gated (§3.2, §5).
9. **`scripts/deploy.sh` targets a compose layout that no longer exists**, and there is no working backup procedure in the repo (§5).
10. **Several AI features are Anthropic-only** despite the 8-provider catalogue (§1.5).
11. **Unit tests run only on SQLite.** PostgreSQL-specific behaviour (pg_trgm, pgvector, collation, PostgreSQL parity) is skipped without a server.
12. **TypeScript is not strict** (`strictNullChecks` and `noImplicitAny` off, with 226/387 known errors).
13. **The response envelope is not universal** (1,860 `.ok(` for 2,051 routes, no guard test).
14. **`/api/v2` is a 3-route stub** while every `/api/v1` response is flagged deprecated.
15. **6 non-reversible downgrades** (§5).
16. **Hard-coded values that contradict the "everything in Settings" rule:** WS ticket TTL 60 s, staff JWT algorithm HS256, `setup.sh` ports 8000/3000.
17. **Compose sets unused `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`**, and `.env.example` documents 5 keys nothing reads (§4.3).
18. **`DOCS.md` states 116 rate-limited endpoints and "390 of 391 models"; measured today: 117 decorators and 394 of 395 mapped classes scoped (+1 exempt).**

#### 13.2 Not verified

- A full `docker compose --profile app up` (images were not built or started; the user's running stack was not touched).
- Full backend suite run time and pass rate; frontend `npm test`/`build` results.
- Runtime behaviour of: slowapi default limits without middleware, nginx WS routing, rate-limit IP behind nginx, the frontend `.env.example` breakage, the admin password conflict after `sync_demo_passwords`, and whether Google's chart API still answers.
- SSO/SAML flow internals, the OAuth developer-portal token flow, and the GRC "109 non-exempt domains" figure.
- The exact Node version Vite 7 requires (upstream fact, not measured).

#### 13.3 DOCS.md statements that do not match the code

| DOCS.md says | Code says |
|---|---|
| §2: frontend entries `src/main.jsx`, `src/App.jsx`, `src/services/api.js` | `main.tsx`, `App.tsx`, `services/api.ts` + `services/api/_core.ts`; zero `.js/.jsx` in `src` |
| §4: Node.js 20+ | `setup.sh` only requires 18 (warns); the frontend image uses Node 20 |
| §6: variable `CORS_ORIGINS` | It is `ALLOWED_ORIGINS` (`config.py` says so explicitly) |
| §7: mode `./setup.sh admin-only-start` | No such mode. `setup.sh` has demo, clean, start, stop, update, docker-stop, docker-clean; `admin-only` exists only in `setup.bat` as an alias of `clean` |
| §7: Docker stack "versioned in `deploy/docker-compose.yml`" | `docker-compose.yml` is in the repo root; `deploy/` holds only the Dockerfiles |
| §8: Seed = `python scripts/seed_full_data.py` | `setup.sh demo` uses `python -m app.db.seed`; `seed_full_data.py` is a separate, heavier generator |
| §8: "default users live in `default_seed_users()`" | Used only if `seed_users_data.json` is missing; the JSON is in the repo and wins (it ignores `SUPERADMIN_EMAIL`) |
| §8: "`app/db/migrate.py` is no longer used in any flow" | Still recommended by `setup.sh`'s SQLite recovery message |
| §8bis (and the compose header): `./setup.sh` with no argument "creates .env, volumes and starts infra" | No argument prints usage and exits 1 |
| §10: hook `frontend/src/hooks/useOrgSettings.js` | `useOrgSettings.ts` |
| §12: "Rate limiting: 116 endpoints" | 117 `@limiter.limit` decorators |
| §12: tenant filter "covers 390 of 391 models" | 395 mapped classes: 383 `organization_id` + 11 `org_id` + 1 exempt |
| §12 Rotación de claves: `scripts/rotate_keys.sh` | Was only rewriting `SECRET_KEY`; fixed 2026-11-03, see §7.5 |
| §14 Observability: "logs, Sentry and OpenTelemetry" | Also Prometheus `/metrics` and an observability compose profile |
| §15 E-sign: `frontend/src/services/api.js` | `api.ts`; there is no `api.js` |

---

## About this document

Written for functional users and technicians of Contecflow. Measured on 2026-11-03 against commit `HEAD` of `main` by reading pages, API clients, routers, services, models, migrations and `app/worker.py`, plus read-only introspection (route table, settings defaults, `alembic heads`, `pytest --collect-only`). Statements that could not be confirmed are marked *Not verified*. When the code changes, the section of the affected area must be updated in the same commit.
