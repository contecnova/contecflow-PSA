# Configuration — Full Alphabetical Location Table

Tabla completa de los 191 settings de `app/core/config.py` + `config_groups/*.py`.
Cada fila indica el destino exacto y el estado del consumer.

## Leyenda

- 🎛 `Settings → Sistema → Config. dinámica` → ✅ consumer migrado, ⚠️ UI registrada pero consumer aún env
- 🔐 `Settings → Sistema → Credenciales` (🔒 = secret cifrado, sin 🔒 = plaintext en BD)
- 📋 Otra página existente de Settings
- 🔴 `.env` bootstrap (redeploy obligatorio)
- ⚪ `.env` keep-env (defaults estables, no aporta moverlo)
- 🟡 No portable o pendiente sin destino (timeouts, orfanatos)

---

## Tabla completa (alphabetical, A → Z)

| Setting | Destino |
|---|---|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 🎛 Tokens ✅ |
| `ACCESS_TOKEN_MAX_MINUTES` | 🎛 Tokens ✅ |
| `ADOBE_SIGN_BASE_URL` | 🔐 Adobe Sign |
| `ADOBE_SIGN_CLIENT_ID` | 🔐 Adobe Sign |
| `ADOBE_SIGN_CLIENT_SECRET` | 🔐 Adobe Sign 🔒 |
| `AI_COST_ALERT_USD_PER_DAY` | 🎛 IA ⚠️ |
| `ALLOWED_ORIGINS` | 🔴 bootstrap (CORS middleware bind) |
| `ANTHROPIC_API_KEY` | 🔐 AI providers 🔒 (migrado en `ai_client` + `ai_modules_service`) |
| `ANTHROPIC_API_URL` | ⚪ keep-env |
| `ANTHROPIC_DOCS_URL` | ⚪ keep-env |
| `API_V1_STR` | 🔴 bootstrap (router prefix) |
| `API_V2_STR` | 🔴 bootstrap (router prefix) |
| `AWS_ACCESS_KEY` | 🔐 AWS S3 🔒 |
| `AWS_KMS_KEY_ID` | 🔴 bootstrap (envelope encryption) |
| `AWS_KMS_REGION` | 🔴 bootstrap |
| `AWS_REGION` | 🔐 AWS S3 |
| `AWS_S3_BUCKET` | 🔐 AWS S3 |
| `AWS_SECRET_KEY` | 🔐 AWS S3 🔒 |
| `AZURE_CLIENT_ID` | 🔐 MS Graph |
| `AZURE_CLIENT_SECRET` | 🔐 MS Graph 🔒 |
| `AZURE_OPENAI_API_URL` | ⚪ keep-env |
| `AZURE_OPENAI_DOCS_URL` | ⚪ keep-env |
| `AZURE_SPEECH_KEY` | 🔐 AI providers 🔒 |
| `AZURE_SPEECH_REGION` | 🎛 IA ⚠️ |
| `AZURE_STT_LANGUAGE` | 🎛 IA ⚠️ |
| `AZURE_TENANT_ID` | 🔐 MS Graph |
| `BACKEND_URL` | 🔴 bootstrap |
| `BASE_URL` | 🔴 bootstrap |
| `BCRYPT_ROUNDS` | 🔴 bootstrap (afecta validación de hashes existentes) |
| `CELERY_AGENT_TASK_SOFT_TIME_LIMIT` | 🔴 bootstrap (decorator binding) |
| `CELERY_AGENT_TASK_TIME_LIMIT` | 🔴 bootstrap (decorator binding) |
| `CLIENT_PORTAL_SECRET` | 🔴 bootstrap (HMAC magic-link) |
| `CONTECFLOW_AI_MODEL` | 🎛 IA ✅ |
| `DATABASE_URL` | 🔴 bootstrap (paradox) |
| `DEEPSEEK_API_URL` | ⚪ keep-env |
| `DEEPSEEK_DOCS_URL` | ⚪ keep-env |
| `DEFAULT_BILLING_TYPE` | 🟡 env orphan (default para nuevos proyectos; podría ir a Locale) |
| `DEFAULT_CURRENCY` | 🎛 Locale ✅ |
| `DEFAULT_IMPUTATION_LOCKOUT_DAYS` | 🎛 Locale ✅ |
| `DEFAULT_LANGUAGE` | 🎛 Locale ✅ |
| `DEFAULT_PROJECT_TYPE` | 🟡 env orphan |
| `DEFAULT_TAX_RATE` | 🎛 Locale ✅ |
| `DEFAULT_TIMEZONE` | 🎛 Locale ✅ |
| `DEFAULT_USER_PASSWORD` | 🔴 bootstrap (seed) |
| `DEFAULT_VACATION_DAYS_PER_YEAR` | 🎛 Locale ✅ |
| `DEFAULT_WEEKLY_CAPACITY_HOURS` | 🎛 Locale ✅ |
| `DEFAULT_WORKING_HOURS_PER_DAY` | 🎛 Locale ✅ |
| `DOCUSIGN_ACCOUNT_ID` | 🔐 DocuSign |
| `DOCUSIGN_BASE_URL` | 🔐 DocuSign |
| `DOCUSIGN_INTEGRATION_KEY` | 🔐 DocuSign 🔒 |
| `DOCUSIGN_SECRET_KEY` | 🔐 DocuSign 🔒 |
| `ENVIRONMENT` | 🔴 bootstrap (validators, scheduler, headers) |
| `EXCHANGE_RATES_AUTO_UPDATE` | 🎛 Feature flags ✅ |
| `FRONTEND_EMBED_BASE_URL` | 🎛 UI Branding ⚠️ |
| `FRONTEND_URL` | 🔴 bootstrap |
| `GEMINI_API_URL` | ⚪ keep-env |
| `GEMINI_DOCS_URL` | ⚪ keep-env |
| `GITHUB_WEBHOOK_SECRET` | 🔐 Webhooks 🔒 |
| `GITLAB_WEBHOOK_SECRET` | 🔐 Webhooks 🔒 |
| `GOOGLE_CHART_URL` | ⚪ keep-env |
| `GOOGLE_OAUTH_BASE` | ⚪ keep-env |
| `GOOGLE_STT_API_KEY` | 🔐 AI providers 🔒 |
| `GOOGLE_STT_LANGUAGE` | 🎛 IA ⚠️ |
| `GOOGLE_TOKEN_URL` | ⚪ keep-env |
| `GROQ_API_URL` | ⚪ keep-env |
| `GROQ_DOCS_URL` | ⚪ keep-env |
| `HEALTH_DEFAULT_NO_DATA` | 🎛 Health ✅ |
| `HEALTH_NPS_LOOKBACK_DAYS` | 🎛 Health ✅ |
| `HEALTH_PORTAL_BASE_SCORE` | 🎛 Health ✅ |
| `HEALTH_PORTAL_SCORE_PER_SESSION` | 🎛 Health ✅ |
| `HEALTH_THRESHOLD_AT_RISK` | 🎛 Health ✅ |
| `HEALTH_THRESHOLD_EXCELLENT` | 🎛 Health ✅ |
| `HEALTH_THRESHOLD_GOOD` | 🎛 Health ✅ |
| `HEALTH_TICKET_LOOKBACK_DAYS` | 🎛 Health ✅ |
| `HEALTH_WEIGHT_BUDGET` | 🎛 Health ✅ |
| `HEALTH_WEIGHT_DELIVERY` | 🎛 Health ✅ |
| `HEALTH_WEIGHT_NPS` | 🎛 Health ✅ |
| `HEALTH_WEIGHT_PORTAL` | 🎛 Health ✅ |
| `HEALTH_WEIGHT_TICKETS` | 🎛 Health ✅ |
| `INBOUND_EMAIL_SECRET` | 🔐 Webhooks 🔒 |
| `INTEGRATION_SECRET_ROTATION_DAYS` | 🎛 Key rotation ✅ |
| `JWT_KEY_RETENTION_COUNT` | 🎛 Key rotation ✅ |
| `JWT_KEY_ROTATION_DAYS` | 🎛 Key rotation ✅ |
| `KEY_ROTATION_ENABLED` | 🎛 Key rotation ✅ |
| `KEY_ROTATION_RUN_HOUR_UTC` | 🔴 bootstrap (cron bind) |
| `KMS_PROVIDER` | 🔴 bootstrap |
| `LOG_LEVEL` | 📋 Settings → Sistema → Nivel de log |
| `LOGIN_ATTEMPT_WINDOW_SECONDS` | 🎛 Password policy ✅ |
| `LOGIN_LOCKOUT_SECONDS` | 🎛 Password policy ✅ |
| `LOGIN_MAX_ATTEMPTS` | 🎛 Password policy ✅ |
| `M365_CALENDAR_SYNC_ENABLED` | 🎛 Feature flags ✅ |
| `M365_TEAMS_NOTIFICATIONS_ENABLED` | 🎛 Feature flags ✅ |
| `MAX_FILE_SIZE_MB` | 🎛 Storage ✅ |
| `METRICS_AUTH_TOKEN` | 🎛 Observability ✅ |
| `METRICS_ENABLED` | 🔴 bootstrap (module load) |
| `MICROSOFT_OAUTH_BASE` | ⚪ keep-env |
| `MIN_PASSWORD_LENGTH` | 🎛 Password policy ✅ |
| `MISTRAL_API_URL` | ⚪ keep-env |
| `MISTRAL_DOCS_URL` | ⚪ keep-env |
| `NOTIFICATION_EMAIL_FROM` | 📋 Settings → Personal → General (legacy) |
| `OLLAMA_BASE_URL` | ⚪ keep-env |
| `OLLAMA_DOCS_URL` | ⚪ keep-env |
| `OPEN_EXCHANGE_RATES_APP_ID` | 🔐 OpenExchangeRates 🔒 ✅ |
| `OPENAI_API_KEY` | 🔐 AI providers 🔒 |
| `OPENAI_API_URL` | ⚪ keep-env |
| `OPENAI_DOCS_URL` | ⚪ keep-env |
| `OPENAI_STT_MODEL` | 🎛 IA ⚠️ |
| `OTEL_ENABLED` | 🔴 bootstrap (TracerProvider init) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | 🔴 bootstrap |
| `OTEL_EXPORTER_OTLP_HEADERS` | 🔴 bootstrap |
| `OTEL_SERVICE_NAME` | 🔴 bootstrap |
| `OUTBOUND_AI_TIMEOUT_SECONDS` | 🟡 no portable (26 literales hardcoded) |
| `OUTBOUND_HTTP_TIMEOUT_SECONDS` | 🟡 no portable |
| `PASSWORD_REQUIRE_DIGIT` | 🎛 Password policy ✅ |
| `PASSWORD_REQUIRE_LOWERCASE` | 🎛 Password policy ✅ |
| `PASSWORD_REQUIRE_SPECIAL` | 🎛 Password policy ✅ |
| `PASSWORD_REQUIRE_UPPERCASE` | 🎛 Password policy ✅ |
| `PDF_STORAGE_PATH` | 🔴 bootstrap (filesystem) |
| `PROJECT_HEALTH_BUDGET_RATIO_GOOD` | 🎛 Health ✅ |
| `PROJECT_HEALTH_BUDGET_RATIO_OK` | 🎛 Health ✅ |
| `PROJECT_HEALTH_BUDGET_RATIO_WARN` | 🎛 Health ✅ |
| `PROJECT_HEALTH_TRAFFIC_GREEN` | 🎛 Health ✅ |
| `PROJECT_HEALTH_TRAFFIC_YELLOW` | 🎛 Health ✅ |
| `PROJECT_HEALTH_WEIGHT_BUDGET` | 🎛 Health ✅ |
| `PROJECT_HEALTH_WEIGHT_CLIENT` | 🎛 Health ✅ |
| `PROJECT_HEALTH_WEIGHT_QUALITY` | 🎛 Health ✅ |
| `PROJECT_HEALTH_WEIGHT_SCHEDULE` | 🎛 Health ✅ |
| `PROJECT_HEALTH_WEIGHT_VELOCITY` | 🎛 Health ✅ |
| `PROJECT_NAME` | 🎛 UI Branding ⚠️ |
| `PROMETHEUS_MULTIPROC_DIR` | 🔴 bootstrap |
| `QB_API_BASE` | ⚪ keep-env |
| `RATE_LIMIT_DEFAULT` | 🔴 bootstrap (decorator binding) |
| `RATE_LIMIT_REQUIRE_REDIS_IN_PRODUCTION` | 🔴 bootstrap |
| `REDIS_URL` | 🔴 bootstrap |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 🎛 Tokens ✅ |
| `S3_URL_EXPIRATION_HOURS` | 🎛 Storage ✅ |
| `SCIM_BEARER_TOKEN` | 🔐 Webhooks 🔒 |
| `SECRET_KEY` | 🔴 bootstrap 🔒 (master key) |
| `SEM_MULTI_ROLE_FACTOR` | 🎛 Semantic ⚠️ (class-level constant) |
| `SEM_THRESHOLD_CRITICAL` | 🎛 Semantic ✅ |
| `SEM_THRESHOLD_EXPERT_CACHE` | 🎛 Semantic ✅ |
| `SEM_THRESHOLD_HIGH` | 🎛 Semantic ✅ |
| `SEM_THRESHOLD_LOW` | 🎛 Semantic ✅ |
| `SEM_THRESHOLD_MEDIUM` | 🎛 Semantic ✅ |
| `SEM_TOP_K_HISTORY` | 🎛 Semantic ⚠️ (class-level) |
| `SEM_WEIGHT_HISTORY` | 🎛 Semantic ⚠️ (class-level) |
| `SEM_WEIGHT_PROFILE` | 🎛 Semantic ⚠️ (class-level) |
| `SEMANTIC_EMBEDDINGS_BACKEND` | 🎛 IA ⚠️ |
| `SENTRY_DSN` | 🔴 bootstrap (sentry_sdk.init) |
| `SENTRY_ENVIRONMENT` | 🔴 bootstrap |
| `SHAREPOINT_SITE_ID` | 🔐 MS Graph |
| `SLA_P1_RESOLUTION_HOURS` | 🎛 SLA ✅ |
| `SLA_P1_RESPONSE_HOURS` | 🎛 SLA ✅ |
| `SLA_P2_RESOLUTION_HOURS` | 🎛 SLA ✅ |
| `SLA_P2_RESPONSE_HOURS` | 🎛 SLA ✅ |
| `SLA_P3_RESOLUTION_HOURS` | 🎛 SLA ✅ |
| `SLA_P3_RESPONSE_HOURS` | 🎛 SLA ✅ |
| `SLA_P4_RESOLUTION_HOURS` | 🎛 SLA ✅ |
| `SLA_P4_RESPONSE_HOURS` | 🎛 SLA ✅ |
| `SLA_PREDICTION_HOURS_CRITICAL` | 🟡 env orphan (no tab) |
| `SLA_PREDICTION_HOURS_HIGH` | 🟡 env orphan |
| `SLA_PREDICTION_HOURS_LOW` | 🟡 env orphan |
| `SLA_PREDICTION_HOURS_MEDIUM` | 🟡 env orphan |
| `SLA_PREDICTION_SEVERITY_CRITICAL_H` | 🟡 env orphan |
| `SLA_PREDICTION_SEVERITY_HIGH_H` | 🟡 env orphan |
| `SLA_PREDICTION_WARNING_PCT` | 🎛 SLA ✅ |
| `SLACK_API_BASE` | ⚪ keep-env |
| `SLACK_SIGNING_SECRET` | 🔐 Slack 🔒 |
| `SLACK_WEBHOOK_URL` | 🔐 Slack 🔒 |
| `SMTP_FROM` | 🔐 SMTP ✅ |
| `SMTP_HOST` | 🔐 SMTP ✅ |
| `SMTP_PASS` | 🔐 SMTP 🔒 ✅ |
| `SMTP_PORT` | 🔐 SMTP ✅ |
| `SMTP_USER` | 🔐 SMTP ✅ |
| `STRIPE_PUBLISHABLE_KEY` | 🔐 Stripe |
| `STRIPE_SECRET_KEY` | 🔐 Stripe 🔒 ✅ |
| `STRIPE_WEBHOOK_SECRET` | 🔐 Stripe 🔒 ✅ |
| `STT_FALLBACK_PROVIDERS` | 🎛 IA ⚠️ |
| `STT_PROVIDER` | 🎛 IA ⚠️ |
| `SUPERADMIN_EMAIL` | 🔴 bootstrap (seed) |
| `SUPERADMIN_PASSWORD` | 🔴 bootstrap (seed) |
| `TEAMS_BOT_APP_ID` | 🔐 MS Graph |
| `TEAMS_WEBHOOK_URL` | 🔐 MS Graph 🔒 |
| `TRUST_PROXY_HEADERS` | 🎛 Red / Proxy ✅ (cache TTL 5min) |
| `TRUSTED_PROXY_CIDRS` | 🎛 Red / Proxy ✅ |
| `VERSION` | 🔴 bootstrap |
| `WEBAUTHN_ORIGIN` | 🔴 bootstrap (validado vs origin) |
| `WEBAUTHN_RP_ID` | 🔴 bootstrap (passkey identity) |
| `WEBAUTHN_RP_NAME` | 🎛 UI Branding ✅ |
| `WEBHOOK_SECRET` | 🔐 Webhooks 🔒 |
| `XERO_API_BASE` | ⚪ keep-env |

---

## Conteo final

| Destino | Cantidad | Estado consumer |
|---|---|---|
| 🎛 Config. dinámica — consumer migrado ✅ | 70 | leen runtime con cache |
| 🎛 Config. dinámica — consumer aún env ⚠️ | 14 | UI guarda, consumer no aplica todavía |
| 🔐 Credenciales — campos cifrables | 42 | SMTP/Stripe/OER consumer migrado; resto leen del registro al pasar `db` |
| 📋 Otras pantallas Settings (general/log-level) | 2 (`LOG_LEVEL`, `NOTIFICATION_EMAIL_FROM`) | + ~30 settings legacy en `app_settings` |
| 🔴 .env bootstrap (no portable) | 35 | requieren redeploy |
| ⚪ .env keep-env (URLs estables) | 22 | no aporta moverlas |
| 🟡 Sin destino: `OUTBOUND_*_TIMEOUT` + `SLA_PREDICTION_*` + `DEFAULT_PROJECT/BILLING_TYPE` | 9 | requieren tab nueva o refactor |
| **TOTAL** | **191 únicos** | (algunos aparecen 2 veces: cred + env fallback) |

## Pendientes (resumen accionable)

| Acción | Impacto | Esfuerzo |
|---|---|---|
| Migrar consumer IA STT (`OPENAI_STT_MODEL`, `STT_PROVIDER`, `STT_FALLBACK_PROVIDERS`, `AZURE_SPEECH_REGION`, `AZURE_STT_LANGUAGE`, `GOOGLE_STT_LANGUAGE`) | 6 settings 🎛 IA → ✅ | 5 archivos en `services/stt/*` |
| Migrar consumer `AI_COST_ALERT_USD_PER_DAY`, `SEMANTIC_EMBEDDINGS_BACKEND` | 2 settings 🎛 IA → ✅ | 1-2 lugares |
| Migrar consumer `PROJECT_NAME`, `FRONTEND_EMBED_BASE_URL` | 2 settings 🎛 UI Branding → ✅ | bajo impacto |
| Refactor `OUTBOUND_*_TIMEOUT_SECONDS` | 2 settings 🟡 → 🎛 nueva tab "Timeouts" | mayor: helper centralizado + 26 callsites |
| Añadir tab "SLA breach prediction" | 6 `SLA_PREDICTION_*` 🟡 → 🎛 SLA tab extendida | añadir 6 entradas al registry + consumer en `breach_prediction_service` |
| Añadir tab "Project defaults" | `DEFAULT_PROJECT_TYPE`, `DEFAULT_BILLING_TYPE` 🟡 → 🎛 | 1 entrada registry + consumer en project creation |
| Migrar `SEM_TOP_K_HISTORY`, `SEM_WEIGHT_*`, `SEM_MULTI_ROLE_FACTOR` de class-level a instance | 4 settings 🎛 Semantic ⚠️ → ✅ | refactor de class constants en SemanticAssigner |
