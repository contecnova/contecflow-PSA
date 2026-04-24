# Auditoría exhaustiva por archivo

- Archivos auditados: **829**
- Cobertura inventario: **829/829**
- Exclusiones aplicadas: node_modules, .git, venv, dist, build

## Top 20 archivos con mayor riesgo combinado

| # | path | seguridad | arquitectura | motivo principal |
|---:|---|---|---|---|
| 1 | AUDIT_FILE_BY_FILE.md | high | high | Uso de eval(); Uso de exec(); Uso de subprocess; revisar sanitización |
| 2 | app/api/v1/endpoints/ws.py | high | medium | Uso de eval() |
| 3 | app/main.py | high | medium | Uso de exec(); Uso de subprocess; revisar sanitización |
| 4 | frontend/eslint.config.js | high | none | Uso de eval() |
| 5 | tests/test_ws_ticket_store.py | high | none | Uso de eval() |
| 6 | frontend/scripts/check_portal_i18n_missing.js | high | none | Uso de eval() |
| 7 | frontend/package-lock.json | none | high | tamaño excesivo (8795 líneas); posible duplicación de bloques |
| 8 | alembic/versions/02be3a225710_autogen_all_models.py | none | high | tamaño excesivo (6347 líneas) |
| 9 | frontend/npm-ls.json | none | high | tamaño excesivo (4254 líneas); posible duplicación de bloques |
| 10 | frontend/src/i18n/portalTranslations.js | none | high | tamaño excesivo (3118 líneas) |
| 11 | DOCS.md | none | high | tamaño excesivo (3032 líneas) |
| 12 | uploads/documents/pending/v1/d6bd16e0.md | none | high | tamaño excesivo (3032 líneas) |
| 13 | frontend/src/pages/ServiceDeskPage.jsx | none | high | tamaño excesivo (2771 líneas) |
| 14 | frontend/src/pages/PortalClientePage.jsx | none | high | tamaño excesivo (2320 líneas) |
| 15 | app/services/ai_chat_service.py | none | high | tamaño excesivo (1978 líneas); acoplamiento medio (26 imports) |
| 16 | frontend/src/pages/ClientsPage.jsx | none | high | tamaño excesivo (1737 líneas) |
| 17 | app/db/seed.py | none | high | tamaño excesivo (1724 líneas) |
| 18 | app/api/v1/endpoints/service_desk.py | none | high | tamaño excesivo (1701 líneas); acoplamiento alto (49 imports) |
| 19 | app/services/cab_service.py | none | high | tamaño excesivo (1589 líneas); acoplamiento alto (45 imports) |
| 20 | frontend/src/pages/SettingsPage.jsx | none | high | tamaño excesivo (1507 líneas) |

## Detalle completo por archivo

| path | tipo/rol estimado | propósito | errores/lint (Ruff) | riesgo seguridad | riesgo arquitectura |
|---|---|---|---|---|---|
| .env | config | ══════════════════════════════════════════════════════════════════════════════ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| .env.example | config | ══════════════════════════════════════════════════════════════════════════════ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| .gitleaks.toml | config | title = "Contecflow Gitleaks Config" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| AUDIT_FILE_BY_FILE.md | docs | Auditoría exhaustiva por archivo | none | high — Uso de eval(); Uso de exec(); Uso de subprocess; revisar sanitización | high — tamaño excesivo (863 líneas) |
| DOCS.md | docs | 8. Pruebas automáticas E2E con Playwright | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (3032 líneas) |
| Makefile | code/config | ══════════════════════════════════════════════════════════════════════════════ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic.ini | config | [alembic] | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/env.py | code/config | sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/001_initial_tables.py | migration | """Baseline migration — existing tables created via Base.metadata.create_all. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/002_incremental.py | migration | """Incremental ADD COLUMN migrations (migrated from legacy migrate.py). | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (253 líneas) |
| alembic/versions/003_document_management.py | migration | """Create document management tables | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/004_v24_features.py | migration | """v24 features: timezone per user, recurring billing, public forms, oauth apps | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/005_security_hardening.py | migration | """Security hardening: expand encrypted secret columns, block closed-project imputations | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/006_webauthn_passkeys.py | migration | """Add WebAuthn/FIDO2 passkey credentials table | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/007_user_sessions_panel.py | migration | """Add user sessions table for active devices panel and revocation | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/008_governance_scim_policy_compliance.py | migration | """Add SCIM fields, policy packs and compliance evidence tables | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/009_abac_fine_grained_auth.py | migration | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/010_security_observability.py | migration | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/011_ai_governance_guardrails.py | migration | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/011_multitenancy_org_id.py | migration | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/012_sem_config_priority_thresholds.py | migration | """012 — sem_config priority thresholds + history decay | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/013_sem_config_threshold_calibration.py | migration | """013 — sem_config threshold calibration + schema notes | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/014_ai_providers.py | migration | """014 — ai_providers and ai_usage_logs tables | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/015_multitenant_org_isolation.py | migration | """015 — multi-tenant org isolation: add organization_id to projects | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/016_task_status_in_review.py | migration | """016 — add in_review to TaskStatus enum and migrate existing 'review' rows | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/017_mfa_sso_hardening.py | migration | """017 - MFA replay protection and SSO tenant binding | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/018_drop_user_refresh_token_jti.py | migration | """018 - Drop users.refresh_token_jti (superseded by UserSession.refresh_token_jti) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/019_client_user_multiproject.py | migration | """Add client_user_projects M2M table for multi-project portal access. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/020_tenant_scope_ai_providers_and_rate_tables.py | migration | """Add organization_id to ai_providers and rate_tables for tenant isolation. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/021_imputation_unique_user_task_date.py | migration | """Add unique index to prevent duplicate imputation by user+task+date. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/022_perf_composite_indexes.py | migration | """Add composite indexes for high-volume list and filter endpoints. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/023_api_pagination_and_query_indexes.py | migration | """Add composite indexes for paginated/filter-heavy API endpoints. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/024_imputation_is_invoiced.py | migration | """Add is_invoiced and invoiced_invoice_id to imputations. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/025_merge_multitenancy_heads.py | migration | """Merge multitenancy and main migration branches. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/026_activity_event_tenant_isolation.py | migration | """026 — Add organization_id to activity_events for tenant isolation | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/027_approval_step_started_at.py | migration | """027 — Add step_started_at to approval_requests for timeout tracking | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/028_sd_tickets_sla_metrics.py | migration | """028 — Add SLA metric columns to sd_tickets | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/029_webhook_circuit_breaker.py | migration | """029 — Add circuit-breaker columns to webhooks table | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/02be3a225710_autogen_all_models.py | migration | """autogen all models | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (6347 líneas) |
| alembic/versions/030_webhook_trigger_slug_rotation.py | migration | """030 — Add slug rotation columns to webhook_triggers table | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| alembic/versions/72eb69fe644d_merge_migration_heads.py | migration | """merge_migration_heads | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/__init__.py | backend module | Archivo de backend module para __init__. | none | none — sin patrones de riesgo detectados | medium — archivo vacío |
| app/api/__init__.py | api endpoint | Archivo de api endpoint para __init__. | none | none — sin patrones de riesgo detectados | medium — archivo vacío |
| app/api/deps.py | api endpoint | get_current_user, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/__init__.py | api endpoint | Archivo de api endpoint para __init__. | none | none — sin patrones de riesgo detectados | medium — archivo vacío |
| app/api/v1/endpoints/__init__.py | api endpoint | Exponer v239_features para importación desde router.py | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/abac.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | medium — archivo moderadamente grande (392 líneas); posible duplicación de bloques |
| app/api/v1/endpoints/abac_admin.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/absences.py | api endpoint | TYPE_LABELS, count_working_days as _working_days, serialize_absence as _absence_out, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/accounting_hub.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/activity.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (432 líneas) |
| app/api/v1/endpoints/admin/__init__.py | api endpoint | admin/ subpackage - routers imported directly in app/api/v1/router.py | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/admin/users.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/advanced_config.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (373 líneas) |
| app/api/v1/endpoints/ai/__init__.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/ai/chat.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/ai_chat.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (710 líneas) |
| app/api/v1/endpoints/ai_governance.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (319 líneas) |
| app/api/v1/endpoints/ai_modules.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (400 líneas) |
| app/api/v1/endpoints/ai_providers.py | api endpoint | """AI Providers — CRUD y despacho multi-proveedor""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/ai_suggestions.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/alerts.py | api endpoint | get_alerts_query, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/alm.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/analytics.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (682 líneas) |
| app/api/v1/endpoints/analytics_extended.py | api endpoint | Unificar todos los endpoints bajo un solo router | none | none — sin patrones de riesgo detectados | medium — archivo grande (432 líneas) |
| app/api/v1/endpoints/analytics_legacy_metrics.py | api endpoint | Archivo legacy eliminado. No contiene lógica activa ni endpoints. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/approvals.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (265 líneas) |
| app/api/v1/endpoints/auth.py | api endpoint | verify_password, | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1215 líneas) |
| app/api/v1/endpoints/automations.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/backlog.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/billing/__init__.py | api endpoint | billing/ subpackage - routers imported directly in app/api/v1/router.py | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/billing/reports.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/billing_reports.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (549 líneas) |
| app/api/v1/endpoints/bookings.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (279 líneas) |
| app/api/v1/endpoints/branding.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/cab.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (636 líneas) |
| app/api/v1/endpoints/capacity.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (354 líneas) |
| app/api/v1/endpoints/changes.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/cicd.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/client_portal.py | api endpoint | --- | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (808 líneas) |
| app/api/v1/endpoints/clients.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (268 líneas) |
| app/api/v1/endpoints/cmdb.py | api endpoint | """Clarive v21 — Wiki tags, comentarios internos, CMDB, dashboard agente, | none | none — sin patrones de riesgo detectados | medium — archivo grande (474 líneas) |
| app/api/v1/endpoints/collaborative.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/contracts.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/currency_rates.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/currency_sync.py | api endpoint | router = APIRouter(tags=["Currency"]) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/custom_fields.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/dashboard.py | api endpoint | get_global_kpis, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/deliverables.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/developer_portal.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/documents.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (579 líneas) |
| app/api/v1/endpoints/documents_collab.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/documents_edit.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/enterprise.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (474 líneas) |
| app/api/v1/endpoints/epics.py | api endpoint | """Clarive v19 — Wiki, Épicas, NQL, CFD, Menciones""" | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (307 líneas) |
| app/api/v1/endpoints/esign.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (299 líneas) |
| app/api/v1/endpoints/events.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/expenses.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/export_template.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/gantt_suggestions.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/git_integration.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/governance.py | api endpoint | _org_id = _gsvc.get_org_id | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (283 líneas) |
| app/api/v1/endpoints/grc.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (383 líneas) |
| app/api/v1/endpoints/health_composite.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/imputations.py | api endpoint | validate_and_create_imputation, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/integrations/__init__.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/integrations/erp.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/integrations_hub.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (369 líneas) |
| app/api/v1/endpoints/invoices.py | api endpoint | router = APIRouter(tags=["Invoices"]) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/issue_types.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | medium — archivo moderadamente grande (276 líneas); posible duplicación de bloques |
| app/api/v1/endpoints/jira.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (383 líneas) |
| app/api/v1/endpoints/labels.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/m365.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (372 líneas) |
| app/api/v1/endpoints/marketplace.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/mfa.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (605 líneas); posible duplicación de bloques |
| app/api/v1/endpoints/milestones.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/notifications.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/nps.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/okrs.py | api endpoint | """OKRs — Objectives & Key Results.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/onboarding.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/performance.py | api endpoint | """Performance Reviews — Evaluaciones de rendimiento 360°.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/pipeline.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (253 líneas) |
| app/api/v1/endpoints/portfolio.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/profitability.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/projects/__init__.py | api endpoint | ProjectCreate, ProjectUpdate, ProjectOut, ProjectSummary, ProjectPhaseCreate, ProjectPhaseOut | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/projects/projects.py | api endpoint | Archivo de api endpoint para projects. | none | none — sin patrones de riesgo detectados | medium — archivo vacío |
| app/api/v1/endpoints/projects/tasks.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/public_forms.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/raci.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | medium — archivo moderadamente grande (335 líneas); posible duplicación de bloques |
| app/api/v1/endpoints/rate_cards.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/report_builder.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/resource_demand.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/resource_forecast.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (408 líneas) |
| app/api/v1/endpoints/resources.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (311 líneas) |
| app/api/v1/endpoints/risks.py | api endpoint | serialize_risk as _risk_out, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/salesforce_sync.py | api endpoint | router = APIRouter(tags=["Integrations", "Salesforce"]) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/scim.py | api endpoint | ensure_org as _ensure_org, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/security_observability.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (487 líneas) |
| app/api/v1/endpoints/semantic_engine.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/service_desk.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1701 líneas); acoplamiento alto (49 imports) |
| app/api/v1/endpoints/settings.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/skills.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/slack_block_kit.py | api endpoint | router = APIRouter(tags=["Notifications", "Slack"]) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/sprints.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (310 líneas) |
| app/api/v1/endpoints/tasks.py | api endpoint | logger = logging.getLogger(__name__) | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (306 líneas) |
| app/api/v1/endpoints/template.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/templates.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/timesheets.py | api endpoint | review_timesheet_flow, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/training.py | api endpoint | """Training & Certificaciones.""" | none | none — sin patrones de riesgo detectados | medium — posible duplicación de bloques |
| app/api/v1/endpoints/translations.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/ui.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/users.py | api endpoint | UserCreate, UserUpdate, UserSelfUpdate, UserPublic, UserWithRate, UserLoad | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/v239/__init__.py | api endpoint | Archivo de api endpoint para __init__. | none | none — sin patrones de riesgo detectados | medium — archivo vacío |
| app/api/v1/endpoints/v239/approval_builder.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/v239/baselines.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/v239/branding.py | api endpoint | router = APIRouter() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/v239_features.py | api endpoint | Puedes agregar más routers de v239 aquí si es necesario | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/endpoints/ws.py | api endpoint | """ | none | high — Uso de eval() | medium — archivo grande (714 líneas) |
| app/api/v1/router.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/routers/__init__.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/routers/ai_domain.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/routers/core.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/routers/delivery.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/routers/framework.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v1/routers/platform.py | api endpoint | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v2/__init__.py | api endpoint | API v2 package | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v2/endpoints/__init__.py | api endpoint | API v2 endpoints package | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v2/endpoints/meta.py | api endpoint | """v2 meta endpoints — version information and change-log for API consumers.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v2/endpoints/profitability.py | api endpoint | router = APIRouter(prefix="/profitability", tags=["Rentabilidad v2"]) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/api/v2/router.py | api endpoint | """API v2 router. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/core/__init__.py | backend module | Archivo de backend module para __init__. | none | none — sin patrones de riesgo detectados | medium — archivo vacío |
| app/core/abac.py | backend module | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/core/abac_enforce.py | backend module | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/core/config.py | backend module | PROJECT_NAME: str = Field(default="Contecflow", env="PROJECT_NAME") | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (332 líneas) |
| app/core/deps.py | backend module | security = HTTPBearer(auto_error=False) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/core/encryption.py | backend module | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/core/events.py | backend module | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (253 líneas) |
| app/core/network.py | backend module | raw = (value or "").strip() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/core/ratelimit.py | backend module | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/core/secret_utils.py | backend module | """Utilities to encrypt/decrypt sensitive values in integration config dictionaries.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/core/security.py | backend module | logger = logging.getLogger(__name__) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/db/__init__.py | backend module | Archivo de backend module para __init__. | none | none — sin patrones de riesgo detectados | medium — archivo vacío |
| app/db/base.py | backend module | pass | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/db/migrate.py | backend module | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/db/migrate_to_pg.py | backend module | !/usr/bin/env python3 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/db/seed.py | backend module | """ | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1724 líneas) |
| app/db/session.py | backend module | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (319 líneas) |
| app/integrations/__init__.py | backend module | Archivo de backend module para __init__. | none | none — sin patrones de riesgo detectados | medium — archivo vacío |
| app/main.py | backend module | ── Logging rico ────────────────────────────────────────────────────────────── | none | high — Uso de exec(); Uso de subprocess; revisar sanitización | medium — archivo grande (575 líneas) |
| app/models/__init__.py | model | AuditLog, ProjectPermission, Webhook, WebhookDelivery, SSOConfig, | none | none — sin patrones de riesgo detectados | high — acoplamiento alto (47 imports) |
| app/models/abac.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/activity.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/advanced_config.py | model | ── Custom Roles & Permissions ──────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (308 líneas) |
| app/models/ai_chat.py | model | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (388 líneas) |
| app/models/ai_governance.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/ai_providers.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/alert.py | model | overload = "overload"              # Person >100% capacity | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/alm.py | model | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (339 líneas) |
| app/models/automations.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/billing_reports.py | model | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (491 líneas) |
| app/models/bookings.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/cab.py | model | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (433 líneas) |
| app/models/client_portal.py | model | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (340 líneas) |
| app/models/clients.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/cmdb.py | model | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (254 líneas) |
| app/models/custom_fields.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/document_collab.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/documents.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/enterprise.py | model | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (454 líneas) |
| app/models/epics.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/esign.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/exchange_rates_log.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/expenses.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/financial.py | model | draft = "draft"           # Employee filling in | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/git_integration.py | model | """Git integration models — PR/Deploy events linked to tasks.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/governance.py | model | __tablename__ = "tenant_policy_packs" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/imputation.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/integration.py | model | Integration models disabled in standalone mode | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/issue_types.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/marketplace.py | model | """Gantt baseline and what-if scheduling scenario models. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/mfa.py | model | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (337 líneas) |
| app/models/nps.py | model | """NPS (Net Promoter Score) + Client Health models.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/oauth_apps.py | model | """SQLAlchemy models for the Developer Portal (OAuth2 apps).""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/okrs.py | model | """Módulo OKRs — Objectives and Key Results.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/performance.py | model | """Módulo de evaluaciones de rendimiento 360°.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/pipeline.py | model | ── Pipeline Stage Configuration ────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/portfolio.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/project.py | model | development = "development" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/public_forms.py | model | """SQLAlchemy models for public intake forms.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/raci.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/resources.py | model | ── Skills & Competencies ───────────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (289 líneas) |
| app/models/security_observability.py | model | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (311 líneas) |
| app/models/semantic_engine.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/service_desk.py | model | """ | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1031 líneas) |
| app/models/sessions.py | model | __tablename__ = "user_sessions" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/settings.py | model | """Key-value settings store. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/sprints.py | model | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/task.py | model | backlog = "backlog" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/training.py | model | """Módulo de formación y certificaciones.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/user.py | model | admin = "admin"             # Dirección — ve todo incluyendo costes | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/models/white_label.py | model | """White-label / tenant branding model. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/__init__.py | schema | ruff: noqa: F401 | none | none — sin patrones de riesgo detectados | medium — acoplamiento medio (30 imports) |
| app/schemas/abac.py | schema | id: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/absences.py | schema | type: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/ai_chat.py | schema | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/ai_modules.py | schema | title: Optional[str] = None | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/alerts.py | schema | id: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/approvals.py | schema | name: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/auth.py | schema | username: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/automations.py | schema | name: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/billing_reports.py | schema | ── Invoice output schemas (replaces _invoice_out dict) ─────────────────────── | none | none — sin patrones de riesgo detectados | medium — archivo grande (462 líneas) |
| app/schemas/bookings.py | schema | predecessor_id: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/capacity.py | schema | user_id: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/changes.py | schema | title: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/common_enums.py | schema | admin = "admin" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/contracts.py | schema | name: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/currency_rates.py | schema | from_currency: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/custom_fields.py | schema | name: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/dashboard.py | schema | total_budget: float | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/deliverables.py | schema | name: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/documents.py | schema | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/enterprise.py | schema | user_id: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/epics.py | schema | name: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/expenses.py | schema | user_id: Optional[str] = None | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/governance.py | schema | is_enabled: bool = True | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/grc.py | schema | allowed: bool | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/imputations.py | schema | task_id: Optional[str] = None | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/m365.py | schema | subject:       str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/milestones.py | schema | name: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/misc.py | schema | project_ids: Optional[List[str]] = None | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/nps.py | schema | score: int = Field(..., ge=0, le=10) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/okrs.py | schema | title: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/performance.py | schema | name: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/pipeline.py | schema | name: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/portfolio.py | schema | name: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/projects.py | schema | name: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/raci.py | schema | item_type:  str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/risks.py | schema | title: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/semantic_engine.py | schema | engine_mode: str \| None = None | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/service_desk.py | schema | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (337 líneas) |
| app/schemas/settings.py | schema | key: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/skills.py | schema | name: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/sprints.py | schema | name: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/tasks.py | schema | title: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/time_tracking.py | schema | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/timesheets.py | schema | id: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/training.py | schema | title: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/schemas/users.py | schema | username: str | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/__init__.py | service | Archivo de service para __init__. | none | none — sin patrones de riesgo detectados | medium — archivo vacío |
| app/services/abac.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (799 líneas) |
| app/services/absence_service.py | service | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (334 líneas) |
| app/services/accounting_hub_service.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/activity_service.py | service | """ | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (914 líneas) |
| app/services/advanced_config_service.py | service | """ | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (976 líneas); acoplamiento medio (29 imports) |
| app/services/ai_chat/context_service.py | service | """Build a rich data context for the current tenant for AI assistants.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/ai_chat_service.py | service | """ | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1978 líneas); acoplamiento medio (26 imports) |
| app/services/ai_client.py | service | """AI Client — low-level Claude API wrapper. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/ai_copilot_service.py | service | """AI Copilot contextual suggestions service. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/ai_dispatch.py | service | """Shared AI dispatch functions to avoid endpoint-to-endpoint imports.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/ai_governance.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (534 líneas) |
| app/services/ai_modules_service.py | service | """ | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1412 líneas) |
| app/services/ai_provider_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (520 líneas) |
| app/services/alert_service.py | service | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (292 líneas) |
| app/services/alm_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (722 líneas) |
| app/services/analytics_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (420 líneas) |
| app/services/approval_engine.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (748 líneas) |
| app/services/approval_workflows.py | service | """Shared approval workflow lookup helpers.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/audit.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/auth_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (758 líneas) |
| app/services/automations_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (504 líneas) |
| app/services/billing_reports/data_source_service.py | service | skills_q = db.query(UserSkill).options( | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/billing_reports/history_service.py | service | q = db.query(ImportJob).order_by(ImportJob.started_at.desc()) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/billing_reports/report_catalog_service.py | service | SYSTEM_REPORTS = [ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (259 líneas) |
| app/services/billing_reports_service.py | service | Obtener una factura por ID | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1355 líneas); acoplamiento medio (29 imports) |
| app/services/bookings_service.py | service | """ | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1013 líneas); acoplamiento medio (30 imports) |
| app/services/cab_service.py | service | """ | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1589 líneas); acoplamiento alto (45 imports) |
| app/services/capacity_service.py | service | ── User helpers ───────────────────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/change_service.py | service | return next_numbered_code(db, "change_request", prefix="CR", padding=3) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/client_portal_service.py | service | """ | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1458 líneas); acoplamiento medio (29 imports) |
| app/services/client_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (763 líneas) |
| app/services/cmdb_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (757 líneas) |
| app/services/contract_service.py | service | db: Session, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/currency_rates_service.py | service | db: Session, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/custom_fields_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (442 líneas) |
| app/services/customer_health_service.py | service | """Customer Health Score service. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/dashboard_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (456 líneas) |
| app/services/deliverable_service.py | service | return next_numbered_code(db, "deliverable", prefix="DEL", padding=3) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/developer_portal_service.py | service | """Service layer for Developer Portal — OAuth2 app & token management.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/documents_service.py | service | Devuelve un query filtrable y el total para paginación | none | none — sin patrones de riesgo detectados | medium — archivo grande (536 líneas) |
| app/services/enterprise_service.py | service | """ | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1104 líneas); acoplamiento medio (33 imports) |
| app/services/epics_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (596 líneas) |
| app/services/esign_service.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/exchange_rate_service.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/expense_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (536 líneas) |
| app/services/export_service.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/git_service.py | service | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (336 líneas) |
| app/services/governance_service.py | service | return ( | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/grc_service.py | service | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (304 líneas) |
| app/services/grc_sod.py | service | """Service functions for SoD enforcement and violation logging.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/imputation_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (716 líneas) |
| app/services/integrations.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (749 líneas) |
| app/services/invoice_pdf.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/issue_type_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (429 líneas) |
| app/services/jira_service.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/key_management.py | service | """Key management + automatic rotation for JWT and integration secrets. | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (335 líneas) |
| app/services/m365_service.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/marketplace_service.py | service | """Integration Marketplace service. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/metrics/__init__.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/metrics/advanced.py | service | """Advanced metrics: forecast_revenue, burnout_index.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/metrics/alm.py | service | """ALM metrics: license_cost_by_vendor, license_utilization, license_expiry_timeline, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/metrics/business.py | service | """Business metrics: pipeline_by_stage, pipeline_evolution, contracts_by_status, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/metrics/capacity.py | service | """Capacity & Utilization metrics: load_by_week, productivity_by_person.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/metrics/costs.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo moderadamente grande (388 líneas); posible duplicación de bloques |
| app/services/metrics/hours.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo moderadamente grande (282 líneas); posible duplicación de bloques |
| app/services/metrics/projects.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo moderadamente grande (316 líneas); posible duplicación de bloques |
| app/services/metrics/remaining.py | service | """Remaining metrics: sprints, semantic, load profiles, etc.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/metrics/rrhh.py | service | """RRHH metrics: absences_by_type, absences_by_person, absences_by_month.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/metrics/service_desk.py | service | """Service Desk metrics: tickets_by_status, tickets_by_type, tickets_by_agent, | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (340 líneas) |
| app/services/mfa_service.py | service | coding: utf-8 | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1356 líneas) |
| app/services/milestone_service.py | service | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (368 líneas) |
| app/services/notification_service.py | service | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (260 líneas) |
| app/services/notifications.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/nps_service.py | service | """Service layer for NPS and Client Health Snapshot operations.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/numbering.py | service | return datetime.now(timezone.utc).year | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/okr_service.py | service | """OKR service — business logic for Objectives & Key Results.""" | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (259 líneas) |
| app/services/pagination_service.py | service | """Paginate a SQLAlchemy query and optionally expose pagination headers. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/performance_service.py | service | """Service layer for Performance Reviews.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/pipeline_service.py | service | STAGE_LABELS = { | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (295 líneas) |
| app/services/portfolio_service.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/profitability_service.py | service | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (374 líneas) |
| app/services/project_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (629 líneas) |
| app/services/psa_flows.py | service | imp = db.query(Imputation).filter(Imputation.id == imputation_id).first() | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (314 líneas) |
| app/services/public_forms_service.py | service | """Service layer for public intake forms.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/raci_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (760 líneas) |
| app/services/rate_card_service.py | service | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (281 líneas) |
| app/services/realtime_notifications.py | service | """Realtime notification helpers used by non-WS endpoints.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/report_builder_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (674 líneas) |
| app/services/report_pdf.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/resource_analytics.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (608 líneas) |
| app/services/risk_scoring.py | service | """Shared risk scoring rules used across risk and analytics modules.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/risk_service.py | service | return ( | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/s3_service.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/salesforce_service.py | service | """Service layer for Salesforce sync operations.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/scheduled_reports.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/scim_service.py | service | """SCIM service — provisioning helpers (RFC 7644).""" | none | none — sin patrones de riesgo detectados | medium — archivo grande (406 líneas) |
| app/services/security_observability.py | service | """ | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1016 líneas) |
| app/services/semantic_classifier.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (632 líneas) |
| app/services/semantic_engine_service.py | service | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (302 líneas) |
| app/services/service_desk/agent_group_service.py | service | return { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/ai_suggest_service.py | service | ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/analytics_service.py | service | d_from = ( | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/announcement_service.py | service | db: Session, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/asset_service.py | service | max_code = db.query(func.max(Asset.code)).scalar() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/canned_response_service.py | service | db: Session, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/catalog_service.py | service | categories = ( | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/change_service.py | service | _org_user_ids_subquery, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/cmdb_relation_service.py | service | ci = _scope_ci_query(db.query(ConfigurationItem), db, current_user).filter( | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/cmdb_service.py | service | db: Session, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/comment_service.py | service | ticket = _scope_ticket_query(db.query(Ticket), db, current_user).filter(Ticket.id == ticket_id).first() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/csat_service.py | service | ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/customer_context_service.py | service | recent_tickets = db.query(Ticket).filter( | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/escalation_service.py | service | EscalationAction, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/holiday_service.py | service | q = db.query(SDSLAHoliday) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/inbound_email_service.py | service | SLAPolicy, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/kb_service.py | service | db: Session, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/known_error_service.py | service | return ( | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/link_service.py | service | return db.query(TicketLink).options( | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/major_incident_service.py | service | q = db.query(MajorIncident).options(joinedload(MajorIncident.commander)) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/merge_split_service.py | service | ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/metrics_service.py | service | """Calculate ITIL priority from urgency x impact.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/oncall_service.py | service | q = db.query(OnCallSchedule).options( | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/portal_auth_service.py | service | authorization: Optional[str], | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/problem_service.py | service | scope_problem_query as _scope_problem_query, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/routing_rule_service.py | service | return value.value if hasattr(value, "value") else value | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/scoping.py | service | db: Session, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/semantic_feedback_service.py | service | db = SessionLocal() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/sla_assignment_service.py | service | if not sla_policy_id: | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/sla_event_service.py | service | ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/sla_policy_service.py | service | return { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/stats_service.py | service | PRIORITY_LABELS, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/status_page_service.py | service | StatusPageComponent, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/ticket_creation_service.py | service | PRIORITY_MATRIX, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/ticket_ops_service.py | service | ticket = _scope_ticket_query(db.query(Ticket), db, current_user).filter(Ticket.id == ticket_id).first() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/ticket_query_service.py | service | db: Session, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/ticket_read_service.py | service | db: Session, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/ticket_template_service.py | service | q = db.query(TicketTemplate).filter(TicketTemplate.is_active == True) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/ticket_update_service.py | service | PRIORITY_MATRIX, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/watcher_service.py | service | return ( | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/service_desk/workload_service.py | service | group = db.query(AgentGroup).options( | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/session_security.py | service | logger = logging.getLogger("clarive.session_security") | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (270 líneas) |
| app/services/settings_service.py | service | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (264 líneas) |
| app/services/signature_pdf.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/skill_service.py | service | ── Skill catalog ────────────────────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/sla_service.py | service | """SLA Service — business logic for SLA calculations. | none | none — sin patrones de riesgo detectados | medium — archivo grande (461 líneas) |
| app/services/sprint_service.py | service | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (277 líneas) |
| app/services/task_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (567 líneas) |
| app/services/timesheet_service.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/training_service.py | service | """Service layer for Training & Certifications.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/user_service.py | service | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (424 líneas) |
| app/services/v238_service.py | service | """ | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (867 líneas) |
| app/services/webhooks.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/services/ws_service.py | service | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| app/worker.py | backend module | celery_app = Celery( | none | none — sin patrones de riesgo detectados | medium — archivo grande (708 líneas) |
| frontend/.env.example | frontend module | Variables de entorno para el frontend | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/eslint.config.js | frontend module | js.configs.recommended, | none | high — Uso de eval() | none — sin hallazgos relevantes |
| frontend/index.html | frontend module | <!DOCTYPE html> | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/nginx.frontend.conf | frontend module | server { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/npm-ls.json | frontend module | "version": "1.0.0", | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (4254 líneas); posible duplicación de bloques |
| frontend/package-lock.json | frontend module | "name": "contecflow-frontend", | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (8795 líneas); posible duplicación de bloques |
| frontend/package.json | frontend module | "name": "contecflow-frontend", | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/postcss.config.js | frontend module | plugins: { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/public/manifest.json | frontend module | "name": "Contecflow", | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/public/robots.txt | frontend module | User-agent: | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/public/sw.js | frontend module | Contecflow v22 Service Worker | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/scripts/check_portal_i18n_missing.js | frontend module | Script para detectar claves de traducción faltantes en PORTAL_TRANSLATIONS | none | high — Uso de eval() | none — sin hallazgos relevantes |
| frontend/src/App.jsx | frontend component | SkeletonDashboard, SkeletonTable, SkeletonProjects, | none | none — sin patrones de riesgo detectados | medium — archivo grande (488 líneas) |
| frontend/src/__tests__/AIInlineEditor.test.jsx | frontend component | describe('AIInlineEditor', () => { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/__tests__/BadgeWithTooltip.test.jsx | frontend component | expect.extend({ toHaveStyle }); | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/__tests__/ColVisibility.test.jsx | frontend component | function TestColVisibility({ cols, storageKey }) { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/__tests__/Confirm.test.jsx | frontend component | expect.extend({ toHaveStyle }); | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/__tests__/DocumentViewer.test.jsx | frontend component | describe('DocumentViewer', () => { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/__tests__/DocumentsPanel.test.jsx | frontend component | describe('DocumentsPanel', () => { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/__tests__/EntitySelect.test.jsx | frontend component | No se puede testear EntitySelect sin mock de React Query y API, pero se documenta el patrón: | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/__tests__/GanttChart.test.jsx | frontend component | describe('GanttChart', () => { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/__tests__/LangSelector.test.jsx | frontend component | expect.extend({ toHaveStyle }); | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/__tests__/OfflineIndicator.test.jsx | frontend component | describe('OfflineIndicator', () => { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/__tests__/Pagination.test.jsx | frontend component | describe('Pagination', () => { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/__tests__/ResourceDashboard.test.jsx | frontend component | describe('ResourceDashboard', () => { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/__tests__/ResourceHeatmap.test.jsx | frontend component | describe('ResourceHeatmap', () => { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/__tests__/Skeletons.test.jsx | frontend component | describe('Skeletons', () => { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/__tests__/TableControls.test.jsx | frontend component | function TestTable({ data }) { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/__tests__/TimerWidget.test.jsx | frontend component | describe('TimerWidget', () => { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/__tests__/VirtualList.test.jsx | frontend component | describe('VirtualList', () => { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/__tests__/uiTranslations.test.jsx | frontend component | Mock for i18n context/provider if needed | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/AIInlineEditor.jsx | frontend component | AIInlineEditor — textarea con paleta de comandos IA activada con "/" | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (293 líneas) |
| frontend/src/components/DocumentViewer.jsx | frontend component | DocumentViewer  Visor de documentos rediseV3ado. | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (328 líneas) |
| frontend/src/components/DocumentsPanel.jsx | frontend component | DocumentsPanel  Panel embebible de documentos rediseV3ado | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/GanttChart.jsx | frontend component | GanttChart v2 — Production-quality Interactive Gantt | none | none — sin patrones de riesgo detectados | medium — archivo grande (590 líneas) |
| frontend/src/components/LangSelector.jsx | frontend component | LangSelector — Language picker for login and other screens | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/OfflineIndicator.jsx | frontend component | OfflineIndicator — shows network status + pending offline queue info | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/ResourceDashboard.jsx | frontend component | Resource Dashboard Component | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/ResourceHeatmap.jsx | frontend component | ResourceHeatmap — Visual weekly load heatmap per team member | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (359 líneas) |
| frontend/src/components/TimerWidget.jsx | frontend component | TimerWidget — Cronómetro compacto (para usar en navbar u otros lugares) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/bi/DateRangeFilterBar.jsx | frontend component | const RANGE_PRESETS = { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/dashboard/DashboardGrid.jsx | frontend component | DashboardGrid — Motor compartido para todos los dashboards del sistema | none | none — sin patrones de riesgo detectados | medium — archivo grande (566 líneas) |
| frontend/src/components/layout/Breadcrumbs.jsx | frontend component | if (!items.length) return null | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/layout/GlobalSearch.jsx | frontend component | GlobalSearch — Cmd+K search palette | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/layout/GlobalSearchModal.jsx | frontend component | GlobalSearchModal — Cmd+K search across all modules | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/layout/Layout.jsx | frontend component | LayoutDashboard, CheckSquare, Columns, Clock, Calendar, Umbrella, | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1151 líneas) |
| frontend/src/components/layout/NexusAssistPanel.jsx | frontend component | const SUGGESTIONS = [ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/layout/NotificationCenter.jsx | frontend component | NotificationCenter v23 — Centro de notificaciones en el sidebar | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/layout/NotificationsPanel.jsx | frontend component | NotificationsPanel — Bell icon with dropdown notification list | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/layout/OnboardingTour.jsx | frontend component | OnboardingTour — Tours interactivos por módulo | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/layout/OnboardingWizard.jsx | frontend component | OnboardingWizard — Interactive step-by-step setup guide for new admins | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (327 líneas) |
| frontend/src/components/layout/PageHeader.jsx | frontend component | PageHeader — Cabecera de página consistente con icono, título, breadcrumb, acciones y métricas | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/layout/TopProgressBar.jsx | frontend component | TopProgressBar — Thin top loading bar that fires on every route change. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/layout/UserProfilePanel.jsx | frontend component | UserProfilePanel — Panel lateral de perfil de usuario | none | none — sin patrones de riesgo detectados | medium — archivo grande (521 líneas) |
| frontend/src/components/ui/BadgeWithTooltip.jsx | frontend component | Badge with tooltip (hover for info) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/ui/ColVisibility.jsx | frontend component | ColVisibility — gear button + dropdown to show/hide table columns. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/ui/Confirm.jsx | frontend component | Confirm — Simple confirmation dialog | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/ui/EntitySelect.jsx | frontend component | EntitySelect — Reusable select components for shared catalog entities. | none | none — sin patrones de riesgo detectados | medium — archivo moderadamente grande (370 líneas); posible duplicación de bloques |
| frontend/src/components/ui/FRCRIcons.jsx | frontend component | Icon for Feature Request (FR) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/ui/IconButton.jsx | frontend component | ariaLabel, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/ui/Pagination.jsx | frontend component | Pagination — simple prev/next + page number controls. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/ui/Skeletons.jsx | frontend component | Skeletons — pre-built per-page skeleton screens. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/ui/TableControls.jsx | frontend component | TableControls.jsx | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/ui/VirtualList.jsx | frontend component | VirtualList — renders only visible rows for large datasets. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/components/ui/index.jsx | frontend component | ClientSelect, UserSelect, ProjectSelect, | none | none — sin patrones de riesgo detectados | medium — archivo grande (694 líneas) |
| frontend/src/constants/api.js | frontend module | api.js — Constantes de API y configuración del cliente | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/constants/business_config.json | frontend module | "TIMEOUT": { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/constants/constants.json | frontend module | "ROLES": [ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/constants/sharedStatus.js | frontend module | sharedStatus.js - Estados y configuración centralizados para portal y backoffice | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/constants/theme.js | frontend module | theme.js — Design tokens centralizados de Contecflow | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/context/AuthContext.jsx | frontend component | const AuthContext = createContext(null) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/context/ConfirmContext.jsx | frontend component | ConfirmContext — reemplaza los confirm() nativos del navegador con un | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/context/ToastContext.jsx | frontend component | ToastContext — Sistema global de notificaciones no bloqueantes | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/features/bi/widgets.jsx | frontend component | AreaChart, Area, BarChart, Bar, Line, | none | none — sin patrones de riesgo detectados | medium — archivo grande (624 líneas) |
| frontend/src/hooks/__tests__/useAppT.test.js | frontend module | const mockTranslations = { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useAbsences.js | frontend module | const STALE = 2 * 60 * 1000 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useAppT.js | frontend module | const NOOP = () => {}; | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useAssets.js | frontend module | const STALE = 2 * 60 * 1000 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useChanges.js | frontend module | const STALE = 2 * 60 * 1000 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useClients.js | frontend module | useClients — Centralized hook for client data. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useContracts.js | frontend module | const STALE = 2 * 60 * 1000 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useCountUp.js | frontend module | useCountUp — Animates a number from 0 (or prev value) to `target`. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useDashboard.js | frontend module | return useQuery({ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useDeliverables.js | frontend module | const STALE = 2 * 60 * 1000 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useDocCollab.js | frontend module | useDocCollab — Yjs CRDT collaboration over existing ws/doc backend protocol. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useEpics.js | frontend module | const STALE = 2 * 60 * 1000 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useExpenses.js | frontend module | const STALE = 2 * 60 * 1000 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useFormValidation.js | frontend module | const [errors, setErrors] = useState({}) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useImputations.js | frontend module | return useQuery({ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useInvalidate.js | frontend module | useInvalidate — Estrategia global de invalidación de cache | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useLicenses.js | frontend module | const STALE = 2 * 60 * 1000 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useMilestones.js | frontend module | const STALE = 2 * 60 * 1000 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useNotificationBadges.js | frontend module | Centralises the two badge queries (alert count + pending approvals) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useOKRs.js | frontend module | const STALE = 2 * 60 * 1000 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useOnlineStatus.js | frontend module | Returns `true` when the browser has network connectivity. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/usePipeline.js | frontend module | const STALE = 2 * 60 * 1000 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useProblems.js | frontend module | const STALE = 2 * 60 * 1000 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useProjects.js | frontend module | return useQuery({ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useRisks.js | frontend module | const STALE = 2 * 60 * 1000 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useSprints.js | frontend module | const STALE = 2 * 60 * 1000 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useSubcontractors.js | frontend module | const STALE = 2 * 60 * 1000 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useTasks.js | frontend module | return useQuery({ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useTickets.js | frontend module | const STALE = 60 * 1000  // 1 min — tickets change more frequently | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useTraining.js | frontend module | const STALE = 2 * 60 * 1000 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useUserPreferences.js | frontend module | useUserPreferences — Carga y persiste preferencias de UI del usuario en el backend. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useUsers.js | frontend module | useUsers — Centralized hook for user data. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/hooks/useVendors.js | frontend module | const STALE = 2 * 60 * 1000 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/i18n/AppLangContext.jsx | frontend component | AppLangContext — Context de idioma para el back-office | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/i18n/appTranslations.js | frontend module | Legacy compatibility wrapper. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/i18n/portalTranslations.js | frontend module | Portal Client i18n translations | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (3118 líneas) |
| frontend/src/index.css | frontend module | ══════════════════════════════════════════════════════════════ | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1334 líneas) |
| frontend/src/main.jsx | frontend component | Initialize offline sync — auto-syncs queued imputations when the browser comes back online | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/AIHubPage.jsx | frontend component | const getStatusCfg = (t) => ({ | none | none — sin patrones de riesgo detectados | medium — archivo grande (473 líneas) |
| frontend/src/pages/ALMPage.jsx | frontend component | ── Constantes ──────────────────────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1386 líneas) |
| frontend/src/pages/AbsencesPage.jsx | frontend component | ── Estilos compartidos ─────────────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | medium — archivo grande (538 líneas) |
| frontend/src/pages/AgentDashboardPage.jsx | frontend component | const ps = { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/AlertsPage.jsx | frontend component | const SEVERITY_CONFIG = { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/ApprovalsPage.jsx | frontend component | const inp = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 12... | none | none — sin patrones de riesgo detectados | medium — archivo grande (646 líneas) |
| frontend/src/pages/AutomationsPage.jsx | frontend component | AutomationsPage — Visual no-code rule builder + Workflows multi-paso + RPA | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (862 líneas) |
| frontend/src/pages/BIPage.jsx | frontend component | DEFAULT_LAYOUT, | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (317 líneas) |
| frontend/src/pages/BIProjectDetailPage.jsx | frontend component | ResponsiveContainer, | none | none — sin patrones de riesgo detectados | medium — archivo grande (496 líneas) |
| frontend/src/pages/BudgetsPage.jsx | frontend component | BudgetsPage — Presupuestos multi-período por departamento | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (255 líneas) |
| frontend/src/pages/CMDBPage.jsx | frontend component | const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' } | none | none — sin patrones de riesgo detectados | medium — archivo grande (497 líneas) |
| frontend/src/pages/CalendarPage.jsx | frontend component | CalendarPage v23 — Vista calendario global unificada | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/CapacityPage.jsx | frontend component | CapacityPage — Planificador visual de recursos con drag-and-drop | none | none — sin patrones de riesgo detectados | medium — archivo grande (428 líneas) |
| frontend/src/pages/ChangelogPage.jsx | frontend component | ChangelogPage — Release notes y changelog por proyecto | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (301 líneas) |
| frontend/src/pages/ChangesPage.jsx | frontend component | ── Estilos compartidos ─────────────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | medium — archivo grande (488 líneas) |
| frontend/src/pages/ClientPortalPage.jsx | frontend component | ClientPortalPage – Internal PM view for managing the client portal: | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1054 líneas) |
| frontend/src/pages/ClientsPage.jsx | frontend component | Estilos reutilizables globales (asegurar que siempre estén definidos) | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1737 líneas) |
| frontend/src/pages/ContractsPage.jsx | frontend component | ── Estilos compartidos ─────────────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | medium — archivo grande (528 líneas) |
| frontend/src/pages/CumulativeFlowPage.jsx | frontend component | const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' } | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/CustomFieldsPage.jsx | frontend component | const FIELD_TYPES = [ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (287 líneas) |
| frontend/src/pages/DeliverablesPage.jsx | frontend component | ── Estilos compartidos ─────────────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (301 líneas) |
| frontend/src/pages/DependenciesPage.jsx | frontend component | const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' } | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (370 líneas) |
| frontend/src/pages/DeveloperPortalPage.jsx | frontend component | DeveloperPortalPage — Manage OAuth2 applications | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (280 líneas) |
| frontend/src/pages/DocumentsPage.jsx | frontend component | DocumentsPage — Rediseño completo del hub de gestión documental | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1122 líneas) |
| frontend/src/pages/ESignPage.jsx | frontend component | ESignPage — Electronic signature management dashboard | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (364 líneas) |
| frontend/src/pages/EVMPage.jsx | frontend component | EVMPage — Earned Value Management | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (272 líneas) |
| frontend/src/pages/EnterprisePage.jsx | frontend component | EnterprisePage v14 — Webhooks, GDPR, Email, Integraciones, SSO, Audit, API Keys | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (831 líneas) |
| frontend/src/pages/EpicGanttPage.jsx | frontend component | const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' } | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (337 líneas) |
| frontend/src/pages/EpicsPage.jsx | frontend component | const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' } | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (314 líneas) |
| frontend/src/pages/ExpensesPage.jsx | frontend component | ExpensesPage — gestión completa de gastos con flujo de aprobación | none | none — sin patrones de riesgo detectados | medium — archivo grande (621 líneas) |
| frontend/src/pages/ExportsPage.jsx | frontend component | const t = useAppT() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/ForbiddenPage.jsx | frontend component | const location = useLocation() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/FullTextSearchPage.jsx | frontend component | const _t = useAppT() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/GanttPage.jsx | frontend component | GanttPage — delegated to GanttChart v2 component. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/GitPage.jsx | frontend component | GitPage — bidirectional Git integration dashboard | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (342 líneas) |
| frontend/src/pages/GovernancePage.jsx | frontend component | const card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 } | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/GrcPage.jsx | frontend component | GrcPage — Governance, Risk & Compliance (backbone de seguridad) | none | none — sin patrones de riesgo detectados | medium — archivo grande (666 líneas) |
| frontend/src/pages/ImportPage.jsx | frontend component | ImportPage — Importación masiva de datos desde CSV/Excel | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/ImputarPage.jsx | frontend component | const HOUR_OPTIONS = [0.5, 1, 1.5, 2, 3, 4, 5, 6, 7, 8] | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (376 líneas) |
| frontend/src/pages/IntakeFormPage.jsx | frontend component | IntakeFormPage — Public-facing form, no auth required. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/InternalCommentsPage.jsx | frontend component | const _ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' } | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/InvoicesPage.jsx | frontend component | InvoicesPage — Facturación: crear, gestionar y hacer seguimiento de facturas | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (271 líneas) |
| frontend/src/pages/IssueTypesPage.jsx | frontend component | const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' } | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (279 líneas) |
| frontend/src/pages/JiraIntegrationPage.jsx | frontend component | Settings2, CheckCircle, XCircle, RefreshCw, ArrowDownToLine, | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (377 líneas) |
| frontend/src/pages/KanbanAdvancedPage.jsx | frontend component | KanbanAdvancedPage v2 — Production-quality Kanban | none | none — sin patrones de riesgo detectados | medium — archivo grande (676 líneas) |
| frontend/src/pages/LoginPage.jsx | frontend component | const { login, sessionExpired } = useAuth() | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (339 líneas) |
| frontend/src/pages/M365Page.jsx | frontend component | M365Page — Microsoft 365 deep integration | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (331 líneas) |
| frontend/src/pages/MFAPage.jsx | frontend component | MFAPage — Configuración de autenticación en dos pasos (TOTP) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/MeetingsAIPage.jsx | frontend component | const card = { | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (287 líneas) |
| frontend/src/pages/MentionsPage.jsx | frontend component | const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' } | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (256 líneas) |
| frontend/src/pages/MilestoneBillingPage.jsx | frontend component | const inp = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 12... | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (363 líneas) |
| frontend/src/pages/NPSPage.jsx | frontend component | NPSPage — Customer NPS & Health trend dashboard | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (300 líneas) |
| frontend/src/pages/NexusAgentPage.jsx | frontend component | const card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 } | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (341 líneas) |
| frontend/src/pages/NotFoundPage.jsx | frontend component | const location = useLocation() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/NotificationsPage.jsx | frontend component | NotificationsPage — Bandeja de entrada de notificaciones | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (254 líneas) |
| frontend/src/pages/OKRsPage.jsx | frontend component | OKRsPage — Objectives & Key Results | none | none — sin patrones de riesgo detectados | medium — archivo grande (406 líneas) |
| frontend/src/pages/OraclePage.jsx | frontend component | const card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 } | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/OrgChartPage.jsx | frontend component | OrgChartPage — Organigrama, posiciones y cadenas de aprobación | none | none — sin patrones de riesgo detectados | medium — archivo grande (713 líneas) |
| frontend/src/pages/OrganizationsPage.jsx | frontend component | OrganizationsPage — Gestión multi-tenant de organizaciones | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (274 líneas) |
| frontend/src/pages/PerformanceReviewsPage.jsx | frontend component | PerformanceReviewsPage — Evaluaciones de rendimiento 360° | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (378 líneas) |
| frontend/src/pages/PipelinePage.jsx | frontend component | ﻿import { useMemo, useState } from 'react' | none | none — sin patrones de riesgo detectados | medium — archivo grande (434 líneas) |
| frontend/src/pages/PortalClientePage.jsx | frontend component | PortalClientePage – The external-facing client portal. | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (2320 líneas) |
| frontend/src/pages/PortalPublicViewPage.jsx | frontend component | const API = axios.create({ baseURL: '/api/v1', timeout: 30000 }) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/PortfolioPage.jsx | frontend component | PortfolioPage — Gestión de carteras de proyectos | none | none — sin patrones de riesgo detectados | medium — archivo grande (407 líneas) |
| frontend/src/pages/ProfitabilityPage.jsx | frontend component | ── Estilos compartidos ─────────────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (358 líneas) |
| frontend/src/pages/ProjectPermissionsPage.jsx | frontend component | const LEVELS = [ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (292 líneas) |
| frontend/src/pages/ProjectTemplatesPage.jsx | frontend component | ProjectTemplatesPage — Manage and instantiate project templates. | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (336 líneas) |
| frontend/src/pages/ProjectsPage.jsx | frontend component | const PROJ_COLS = [ | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (986 líneas) |
| frontend/src/pages/PublicFormsPage.jsx | frontend component | PublicFormsPage — Manage public ticket intake forms | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (259 líneas) |
| frontend/src/pages/RACIPage.jsx | frontend component | RACIPage — Matriz de responsabilidades por proyecto (R/A/C/I) | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (268 líneas) |
| frontend/src/pages/RateCardsPage.jsx | frontend component | const inp = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 12... | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (353 líneas) |
| frontend/src/pages/ReportBuilderPage.jsx | frontend component | ReportBuilderPage — No-code parametric report builder | none | none — sin patrones de riesgo detectados | medium — archivo grande (504 líneas) |
| frontend/src/pages/ReportsPage.jsx | frontend component | BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1080 líneas) |
| frontend/src/pages/ResetPasswordPage.jsx | frontend component | function strengthScore(password) { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/ResourceForecastPage.jsx | frontend component | const STATUS_COLOR = { | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (392 líneas) |
| frontend/src/pages/ResourceSchedulerPage.jsx | frontend component | ResourceSchedulerPage — visual resource scheduler (Runn/Parallax-style) | none | none — sin patrones de riesgo detectados | medium — archivo grande (774 líneas) |
| frontend/src/pages/ResourcesPage.jsx | frontend component | const ROLES = Object.entries(ROLE_LABELS).map(([v, l]) => ({ value: v, label: l })) | none | none — sin patrones de riesgo detectados | medium — archivo grande (525 líneas) |
| frontend/src/pages/RevenuePage.jsx | frontend component | RevenuePage — Reconocimiento de ingresos ASC 606 / IFRS 15 | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (280 líneas) |
| frontend/src/pages/RiskScoresPage.jsx | frontend component | RiskScoresPage — Predicción de riesgo por proyecto | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/RisksPage.jsx | frontend component | ── Estilos compartidos ─────────────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | medium — archivo grande (438 líneas) |
| frontend/src/pages/SLACalendarsPage.jsx | frontend component | const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' } | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (306 líneas) |
| frontend/src/pages/ScenariosPage.jsx | frontend component | ScenariosPage — Scenario planning / What-if capacity | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/SearchPage.jsx | frontend component | SearchPage v23 — Búsqueda unificada (NQL + Full-text) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/SemanticEnginePage.jsx | frontend component | const card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 } | none | none — sin patrones de riesgo detectados | medium — archivo grande (543 líneas) |
| frontend/src/pages/ServiceDeskPage.jsx | frontend component | ServiceDeskPage — ITIL/ITSM completo | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (2771 líneas) |
| frontend/src/pages/SettingsPage.jsx | frontend component | const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, pa... | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1507 líneas) |
| frontend/src/pages/SkillsPage.jsx | frontend component | ── Estilos compartidos ─────────────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | medium — archivo grande (531 líneas) |
| frontend/src/pages/SprintChartsPage.jsx | frontend component | SprintChartsPage — Burnup chart + Velocity trend per project | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/SprintPlanningPage.jsx | frontend component | const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' } | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (303 líneas) |
| frontend/src/pages/SprintsPage.jsx | frontend component | SprintsPage — Full Scrum sprint management | none | none — sin patrones de riesgo detectados | medium — archivo grande (660 líneas) |
| frontend/src/pages/SubcontractorsPage.jsx | frontend component | const inp = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 12... | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (926 líneas) |
| frontend/src/pages/TasksPage.jsx | frontend component | ── Estilos compartidos ─────────────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (1247 líneas) |
| frontend/src/pages/TimerPage.jsx | frontend component | Timer Page — Seguimiento de tiempo con cronómetro activo e historial | none | none — sin patrones de riesgo detectados | medium — archivo grande (468 líneas) |
| frontend/src/pages/TimesheetsPage.jsx | frontend component | const STATUS_CFG = { | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (354 líneas) |
| frontend/src/pages/TrainingPage.jsx | frontend component | TrainingPage — Formación y Certificaciones | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (357 líneas) |
| frontend/src/pages/UATPage.jsx | frontend component | UATPage — Gestión de casos UAT (User Acceptance Testing) | none | none — sin patrones de riesgo detectados | medium — archivo grande (402 líneas) |
| frontend/src/pages/WebhookLogPage.jsx | frontend component | WebhookLogPage — Log de eventos webhook salientes | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/WikiPage.jsx | frontend component | const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' } | none | none — sin patrones de riesgo detectados | medium — archivo grande (728 líneas) |
| frontend/src/pages/WikiTagsPage.jsx | frontend component | const _t = useAppT() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/WorkflowsPage.jsx | frontend component | const panelStyle = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding:... | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (375 líneas) |
| frontend/src/pages/service-desk/CMDBTab.jsx | frontend component | function onKeyboardActivate(event, action) { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/service-desk/ChangeManagementTab.jsx | frontend component | const CHANGE_STATUS_COLOR = { | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (262 líneas) |
| frontend/src/pages/service-desk/CreateTicketModal.jsx | frontend component | function getCreateTicketSchema(t) { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/service-desk/ITSMKnowledgeTab.jsx | frontend component | const PRIORITY_COLOR = { | none | none — sin patrones de riesgo detectados | medium — archivo grande (415 líneas) |
| frontend/src/pages/service-desk/KanbanTicketsTab.jsx | frontend component | const PRIO_COLOR = { p1_critical: '#E24B4A', p2_high: '#BA7517', p3_medium: '#378ADD', p4_low: '#1D9E75' } | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/service-desk/MajorIncidentsTab.jsx | frontend component | function DeclareMIModal({ onClose, onSaved }) { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/service-desk/MetricsDashboardTab.jsx | frontend component | ── Helpers ──────────────────────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | medium — archivo grande (659 líneas) |
| frontend/src/pages/service-desk/TicketDetail.jsx | frontend component | ── CannedResponsePicker ────────────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | medium — archivo grande (527 líneas) |
| frontend/src/pages/service-desk/TicketListTab.jsx | frontend component | function TRow({ t: ticket, onClick }) { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/pages/service-desk/sdUtils.jsx | frontend component | Shared constants, styles, and tiny presentational components | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/services/api.js | service | const BASE_URL = import.meta.env.VITE_API_URL \|\| '/api/v1' | none | none — sin patrones de riesgo detectados | medium — archivo grande (426 líneas) |
| frontend/src/services/offlineQueue.js | service | offlineQueue.js — IndexedDB queue for offline time imputations | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/services/settingsApi.js | service | General | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/utils/formValidation.js | frontend module | const fieldErrors = {} | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/utils/helpers.js | frontend module | ── Date helpers ────────────────────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/utils/helpers.test.js | frontend module | describe('helpers', () => { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/utils/logger.js | frontend module | logger.js — Configurable frontend logger for Contecflow PSA | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/src/utils/security.js | frontend module | Frontend security utilities. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/tailwind.config.js | frontend module | @type {import('tailwindcss').Config} | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| frontend/vite.config.js | frontend module | const apiTarget = process.env.VITE_API_URL \|\| process.env.API_URL \|\| 'http://localhost:8000' | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| pytest.ini | config | [pytest] | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| requirements-ml.txt | config | Optional machine learning dependencies for semantic embeddings and advanced models. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| requirements.txt | config | ── Web framework ────────────────────────────────────────────────────────────── | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| ruff.toml | config | [lint] | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| scripts/ci_local.sh | script | !/usr/bin/env bash | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| scripts/clean_and_start.sh | script | !/bin/bash | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| scripts/clean_deploy_artifacts.sh | script | !/usr/bin/env bash | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| scripts/deploy.sh | script | !/usr/bin/env bash | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| scripts/list_tables.py | script | s = SessionLocal() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| scripts/poblar_training_ejemplo.sh | script | !/bin/bash | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| scripts/rotate_keys.sh | script | !/bin/bash | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| scripts/run-ui-tests-linux-mac.sh | script | !/bin/bash | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| scripts/run-ui-tests-windows.bat | script | @echo off | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| scripts/run_regression_suite.sh | script | !/usr/bin/env bash | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| scripts/smoke_check.py | script | base = "http://127.0.0.1:8000/api/v1" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| scripts/smoke_test_i18n.py | script | !/usr/bin/env python3 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| scripts/smoke_test_simple.py | script | !/usr/bin/env python3 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| scripts/start.bat | script | @echo off | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| scripts/start.sh | script | !/bin/bash | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| scripts/test_and_report.sh | script | !/bin/bash | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| scripts/update_endpoints_table.sh | script | !/bin/bash | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| seed_clients_data.json | config | [ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| seed_email_templates.json | config | [ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| seed_users_data.json | config | [ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| setup.bat | code/config | @echo off | none | none — sin patrones de riesgo detectados | medium — archivo grande (522 líneas) |
| setup.sh | code/config | !/bin/bash | none | none — sin patrones de riesgo detectados | medium — archivo grande (746 líneas) |
| tests/__init__.py | test | Archivo de test para __init__. | none | none — sin patrones de riesgo detectados | medium — archivo vacío |
| tests/conftest.py | test | Forzar modo 'plain' para claves JWT en tests (no KMS) | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (318 líneas) |
| tests/test_abac.py | test | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (495 líneas) |
| tests/test_abac_resources.py | test | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (262 líneas) |
| tests/test_absences.py | test | """Tests de Ausencias.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_accessibility.py | test | Verifica etiquetas ARIA | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_accounting.py | test | """Tests de integración contable — sync status, validaciones.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_ai_chat_service_execute_tool.py | test | src = inspect.getsource(execute_tool) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_ai_governance.py | test | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (367 líneas) |
| tests/test_ai_suggest_service.py | test | @pytest.fixture | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_alerts.py | test | """Tests for Alerts — listing, resolving, running alert engine.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_api_versioning.py | test | res = client.get("/api/v2/profitability/summary", headers=auth(admin_token)) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_approvals.py | test | """Tests de aprobaciones multi-nivel.""" | none | none — sin patrones de riesgo detectados | medium — archivo grande (415 líneas) |
| tests/test_auth.py | test | """Tests de autenticación — login, tokens, 2FA.""" | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (346 líneas) |
| tests/test_auth_redirect_uri_validation.py | test | allowed = ["http://localhost:3000", "https://app.example.com"] | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_automations.py | test | """Tests de Automatizaciones — reglas, ejecución, plantillas.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_automations_extended.py | test | """Extended tests for Automations — run-scheduled, test-rule, fire-trigger actions.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_bi_analytics.py | test | """Tests BI/Analytics — nuevas métricas, filtros, utilización avanzada, alertas de margen.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_billing_reports.py | test | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (736 líneas) |
| tests/test_billing_reports_service_unit.py | test | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (385 líneas) |
| tests/test_branding.py | test | payload = { | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_business_logic.py | test | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (494 líneas) |
| tests/test_business_logic_v236.py | test | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (501 líneas) |
| tests/test_business_logic_v238.py | test | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (509 líneas) |
| tests/test_business_logic_v239.py | test | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (774 líneas) |
| tests/test_capacity.py | test | """Tests del planificador de capacidad.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_capacity_extended.py | test | """Tests for Capacity — overview, availability, plans.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_changes.py | test | """Tests de Cambios (Change Requests) — flujo completo de solicitudes de cambio.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_cicd.py | test | Simula fallo en pipeline | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_clients.py | test | """Tests de Clientes (CRM) — CRUD, contactos, 360.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_contracts.py | test | """Tests de Contratos.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_custom_fields.py | test | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (326 líneas) |
| tests/test_customer_context_service.py | test | @pytest.fixture | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_dashboard.py | test | """Tests de Dashboard — KPIs, salud de proyectos, métricas.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_dashboard_extended.py | test | """Tests for Dashboard — KPIs, project health, resource load, profitability.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_dashboard_widgets.py | test | Añadir widget | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_db_sync_endpoints.py | test | Legacy async handlers that still use sync DB access. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_deliverables.py | test | """Tests de Entregables — ciclo de vida completo: crear, entregar, aceptar, rechazar.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_documents.py | test | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (320 líneas) |
| tests/test_documents_collab.py | test | Crear documento | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_exchange_rates.py | test | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_expenses.py | test | """Tests de Gastos — CRUD, aprobación, recibos.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_feature_gaps.py | test | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (413 líneas) |
| tests/test_financial_core.py | test | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (361 líneas) |
| tests/test_governance_enterprise.py | test | org = Organization(name="Acme", slug="acme") | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_grc.py | test | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (268 líneas) |
| tests/test_import_export.py | test | Corrupt file upload — endpoint may not be implemented yet (404 is acceptable) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_imputation_business_guards.py | test | res = client.post( | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_imputations.py | test | """Tests de imputaciones (registro de horas).""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_imputations_enhanced.py | test | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (339 líneas) |
| tests/test_integrations_marketplace.py | test | headers = {"Authorization": f"Bearer {admin_token}"} | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_issues_16_20.py | test | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (587 líneas) |
| tests/test_jira.py | test | """Tests de integración Jira — configuración, mapeos, webhooks.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_merge_split_service.py | test | @pytest.fixture | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_milestone_billing.py | test | """Tests del flujo SOW → Milestone → Aprobación → Factura.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_new_endpoints.py | test | """Tests for new stub endpoints: ai_suggestions, resource_demand, health_composite, ui, templates, ai.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_notifications.py | test | Simula evento | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_nps_customer_health.py | test | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (283 líneas) |
| tests/test_numbering_concurrency.py | test | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_okrs.py | test | """Tests de OKRs — objetivos, key results, check-ins.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_onboarding.py | test | Simula completar paso 1 | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_performance.py | test | """Tests de Performance Reviews — ciclos, evaluaciones, submit.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_pipeline.py | test | """Tests de Pipeline CRM — oportunidades, etapas, forecast.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_platform_flows.py | test | """ | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (831 líneas) |
| tests/test_portal_feature_requests.py | test | """Tests del flujo portal/backoffice de Feature Requests. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_portal_feature_requests_cr_control.py | test | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_portal_translations.py | test | cp._TRANSLATIONS_STORE.clear() | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_portfolio.py | test | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (255 líneas) |
| tests/test_problem_service.py | test | @pytest.fixture | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_profitability.py | test | """Tests de rentabilidad — EAC/ETC/CPI y métricas EVM.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_profitability_extended.py | test | """Extended tests for Profitability — milestones CRUD, summary, by-person/week.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_projects.py | test | """Tests de proyectos — CRUD, estados, permisos, aislamiento multi-tenant.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_psa_critical_flows.py | test | res = client.post( | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_pydantic_v2_migration.py | test | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_raci.py | test | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (283 líneas) |
| tests/test_rate_cards.py | test | """Tests de rate cards — tarifas, márgenes, jerarquía.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_regression_api_get_smoke.py | test | _SKIP_PATH_PREFIXES = ( | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_regression_api_operations_smoke.py | test | _SKIP_PATH_PREFIXES = ( | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_regression_invoices_created_at.py | test | inv = Invoice( | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_report_builder.py | test | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_resource_forecast.py | test | """Tests de resource forecasting.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_resources.py | test | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (344 líneas) |
| tests/test_risks.py | test | """Tests de Gestión de Riesgos — CRUD, portfolio de riesgos.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_router_conflicts.py | test | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_schema_layer_consistency.py | test | """Domain endpoints should import schemas from app.schemas, not define them inline.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_scim_service_security.py | test | monkeypatch.setattr(settings, "SCIM_BEARER_TOKEN", "scim-secret", raising=False) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_security_observability.py | test | """ | none | none — sin patrones de riesgo detectados | low — archivo moderadamente grande (399 líneas) |
| tests/test_semantic_classifier.py | test | """test_semantic_classifier.py — Tests for the 6 bug fixes + 6 refinement improvements. | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (926 líneas) |
| tests/test_semantic_engine_tenant.py | test | client = TestClient(app) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_service_desk.py | test | """Tests de Service Desk — tickets, SLA, categorías.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_settings.py | test | """Tests de Configuración Global — tipos de proyecto, departamentos, festivos, ajustes.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_settings_service.py | test | get_general_settings, update_setting, get_project_types, create_project_type, update_project_type, delete_project_type, | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_simulation.py | test | res = client.get("/api/v1/resource-demand/pipeline", headers={"Authorization": f"Bearer {admin_token}"}) | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_skills.py | test | """Tests de Skills y Catálogo de Habilidades — CRUD, asignación a usuarios, matriz.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_sla_assignment_service.py | test | assign_sla_policy_to_client, assign_sla_policy_to_contract, assign_sla_policy_target, _ensure_sla_policy_exists_if_pr... | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_sprints.py | test | """Tests de Sprints — creación, estados, backlog, velocidad.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_task_service.py | test | @pytest.fixture | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_tasks.py | test | """Tests de tareas — CRUD, estados, asignación.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_tenant_isolation.py | test | Todos los tests usan el fixture seed_multitenant de conftest.py | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_ticket_query_service.py | test | @pytest.fixture | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_ticket_update_service.py | test | @pytest.fixture | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_timesheets.py | test | """Tests de timesheets — registro de horas, aprobación.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_timesheets_extended.py | test | """Tests for Timesheets — submission, review, team views.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_training.py | test | """Tests de Training & Certificaciones.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_translations.py | test | Cambia idioma | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_user_preferences.py | test | payload = {"language": "en", "theme_mode": "dark"} | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_user_service.py | test | get_load_map_payload, get_org_chart_payload, approval_chain_for_user, create_user_record | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_users.py | test | """Tests de usuarios — perfil propio, preferencias, permisos.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_v235_features.py | test | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_v236_features.py | test | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_v24_features.py | test | """ | none | none — sin patrones de riesgo detectados | medium — archivo grande (666 líneas) |
| tests/test_webhook_ssrf.py | test | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_webhooks.py | test | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests/test_ws_ticket_store.py | test | self.store = {} | none | high — Uso de eval() | none — sin hallazgos relevantes |
| tests_e2e/conftest.py | test | """ | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests_e2e/pytest.ini | test | [pytest] | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests_e2e/test_e2e_all_pages_regression.py | test | """Regresion E2E amplia de paginas autenticadas. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests_e2e/test_e2e_auth.py | test | """E2E: Autenticación y sesión de usuario.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests_e2e/test_e2e_dashboard.py | test | """E2E: Dashboard principal y BI.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests_e2e/test_e2e_dashboard_reporting_smoke.py | test | """Smoke E2E for authenticated dashboard and reporting flows. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests_e2e/test_e2e_okrs.py | test | """E2E: OKRs — crear objetivo, añadir KR, hacer check-in.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests_e2e/test_e2e_portal_bi_smoke.py | test | """Smoke E2E: portal multi-proyecto + BI click-to-filter.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests_e2e/test_e2e_projects.py | test | """E2E: Gestión de proyectos — CRUD completo en el navegador.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests_e2e/test_e2e_public_protected_regression.py | test | """Regresion E2E para acceso publico y proteccion de rutas.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests_e2e/test_e2e_service_desk.py | test | """E2E: Service Desk — tickets, comentarios.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests_e2e/test_e2e_sidebar_menu_smoke.py | test | """Smoke E2E: rutas del menú lateral en sesión autenticada. | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| tests_e2e/test_e2e_user_profile.py | test | """E2E: Panel de perfil de usuario — apariencia, idioma, seguridad.""" | none | none — sin patrones de riesgo detectados | none — sin hallazgos relevantes |
| uploads/documents/pending/v1/d6bd16e0.md | docs | 8. Pruebas automáticas E2E con Playwright | none | none — sin patrones de riesgo detectados | high — tamaño excesivo (3032 líneas) |
