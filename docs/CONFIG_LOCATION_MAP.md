# Configuration Location Map

Inventario completo y autoritativo de **dónde vive cada setting** tras las 3
fases de migración env → UI. 191 settings totales.

Convención de iconos:
- 🎛 = editable en `Settings → Sistema → Config. dinámica` (5 tabs)
- 🔐 = editable en `Settings → Sistema → Credenciales` (10 proveedores)
- 📋 = editable en otra página existente de Settings
- 🔴 = solo `.env` — cambio requiere redeploy (`[bootstrap]`)
- ⚪ = solo `.env` por pragmatismo — defaults estables (`[keep-env]`)
- 🟡 = setting registrado pero el consumer aún lee de env (migración consumer-by-consumer pendiente)

Precedencia siempre: **org override → global override → valor del .env**.

---

## 1. 🎛 Settings → Sistema → Config. dinámica (~83 settings, 13 tabs)

### Tab "SLA" (9)
Consumer migrado: `app/services/sla_service.py::calculate_sla_due` (vía `get_sla_hours(db)`).

| Key | Tipo | Default env |
|---|---|---|
| `SLA_P1_RESPONSE_HOURS` | float | 1.0 |
| `SLA_P1_RESOLUTION_HOURS` | float | 4.0 |
| `SLA_P2_RESPONSE_HOURS` | float | 4.0 |
| `SLA_P2_RESOLUTION_HOURS` | float | 8.0 |
| `SLA_P3_RESPONSE_HOURS` | float | 8.0 |
| `SLA_P3_RESOLUTION_HOURS` | float | 24.0 |
| `SLA_P4_RESPONSE_HOURS` | float | 24.0 |
| `SLA_P4_RESOLUTION_HOURS` | float | 72.0 |
| `SLA_PREDICTION_WARNING_PCT` | float | 0.70 |

### Tab "Health scoring" (23)
Consumers migrados: `customer_health_service.compute_composite_health` + `activity_service.compute_health`.

| Key | Tipo |
|---|---|
| `HEALTH_NPS_LOOKBACK_DAYS` | int |
| `HEALTH_TICKET_LOOKBACK_DAYS` | int |
| `HEALTH_DEFAULT_NO_DATA` | float |
| `HEALTH_PORTAL_BASE_SCORE` | float |
| `HEALTH_PORTAL_SCORE_PER_SESSION` | float |
| `HEALTH_WEIGHT_NPS` | float |
| `HEALTH_WEIGHT_DELIVERY` | float |
| `HEALTH_WEIGHT_BUDGET` | float |
| `HEALTH_WEIGHT_TICKETS` | float |
| `HEALTH_WEIGHT_PORTAL` | float |
| `HEALTH_THRESHOLD_EXCELLENT` | float |
| `HEALTH_THRESHOLD_GOOD` | float |
| `HEALTH_THRESHOLD_AT_RISK` | float |
| `PROJECT_HEALTH_WEIGHT_SCHEDULE` | float |
| `PROJECT_HEALTH_WEIGHT_BUDGET` | float |
| `PROJECT_HEALTH_WEIGHT_QUALITY` | float |
| `PROJECT_HEALTH_WEIGHT_VELOCITY` | float |
| `PROJECT_HEALTH_WEIGHT_CLIENT` | float |
| `PROJECT_HEALTH_TRAFFIC_GREEN` | float |
| `PROJECT_HEALTH_TRAFFIC_YELLOW` | float |
| `PROJECT_HEALTH_BUDGET_RATIO_GOOD` | float |
| `PROJECT_HEALTH_BUDGET_RATIO_OK` | float |
| `PROJECT_HEALTH_BUDGET_RATIO_WARN` | float |

### Tab "Semantic" (9)
Consumer migrado: `semantic_classifier.SemanticAssigner._suggest` (5 threshold fallbacks).

| Key | Tipo |
|---|---|
| `SEM_THRESHOLD_EXPERT_CACHE` | float |
| `SEM_THRESHOLD_CRITICAL` | float |
| `SEM_THRESHOLD_HIGH` | float |
| `SEM_THRESHOLD_MEDIUM` | float |
| `SEM_THRESHOLD_LOW` | float |
| `SEM_WEIGHT_PROFILE` | float |
| `SEM_WEIGHT_HISTORY` | float |
| `SEM_TOP_K_HISTORY` | int |
| `SEM_MULTI_ROLE_FACTOR` | float |

### Tab "Política contraseñas" (8)
Consumer migrado: `core/security.py::validate_password_policy(db=db)`.

| Key | Tipo |
|---|---|
| `MIN_PASSWORD_LENGTH` | int |
| `PASSWORD_REQUIRE_UPPERCASE` | bool |
| `PASSWORD_REQUIRE_LOWERCASE` | bool |
| `PASSWORD_REQUIRE_DIGIT` | bool |
| `PASSWORD_REQUIRE_SPECIAL` | bool |
| `LOGIN_MAX_ATTEMPTS` | int |
| `LOGIN_ATTEMPT_WINDOW_SECONDS` | int |
| `LOGIN_LOCKOUT_SECONDS` | int |

### Tab "Locale y jornada" (8)
Consumer migrado: `GET /api/v1/settings/org-defaults`.

| Key | Tipo |
|---|---|
| `DEFAULT_TIMEZONE` | str |
| `DEFAULT_LANGUAGE` | str |
| `DEFAULT_CURRENCY` | str |
| `DEFAULT_TAX_RATE` | float |
| `DEFAULT_WORKING_HOURS_PER_DAY` | float |
| `DEFAULT_WEEKLY_CAPACITY_HOURS` | float |
| `DEFAULT_VACATION_DAYS_PER_YEAR` | int |
| `DEFAULT_IMPUTATION_LOCKOUT_DAYS` | int |

### Tab "Tokens" (3)
Consumer migrado: `core/security.py::create_access_token / create_refresh_token` aceptan `db`, `session_security.register_or_rotate_user_session` lee TTL del runtime, `auth_service.set_auth_cookies(db=...)` aplica TTL en cookie.

| Key | Tipo |
|---|---|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | int |
| `ACCESS_TOKEN_MAX_MINUTES` | int |
| `REFRESH_TOKEN_EXPIRE_DAYS` | int |

### Tab "Rotación de claves" (4)
Consumer migrado: `key_management._rotate_jwt_keyring` y `rotate_due_materials` leen vía runtime.

| Key | Tipo |
|---|---|
| `KEY_ROTATION_ENABLED` | bool |
| `JWT_KEY_ROTATION_DAYS` | int |
| `JWT_KEY_RETENTION_COUNT` | int |
| `INTEGRATION_SECRET_ROTATION_DAYS` | int |

### Tab "IA" (9)
Consumer migrado: `ai_client.get_api_key / get_default_model / call_claude(db=...)` y mirror en `ai_modules_service.api_key / call_claude(db=...)`.

| Key | Tipo |
|---|---|
| `CONTECFLOW_AI_MODEL` | str |
| `SEMANTIC_EMBEDDINGS_BACKEND` | str |
| `OPENAI_STT_MODEL` | str |
| `AI_COST_ALERT_USD_PER_DAY` | float |
| `STT_PROVIDER` | str |
| `STT_FALLBACK_PROVIDERS` | str |
| `AZURE_SPEECH_REGION` | str |
| `AZURE_STT_LANGUAGE` | str |
| `GOOGLE_STT_LANGUAGE` | str |

### Tab "Feature flags" (3)
Consumer migrado: `/api/v1/m365/status` lee runtime.

| Key | Tipo |
|---|---|
| `M365_CALENDAR_SYNC_ENABLED` | bool |
| `M365_TEAMS_NOTIFICATIONS_ENABLED` | bool |
| `EXCHANGE_RATES_AUTO_UPDATE` | bool |

### Tab "Almacenamiento" (2)
Consumer migrado: `S3Service.reload_from_db(db, org_id)` actualiza el cliente; endpoints `/documents/*` leen `MAX_FILE_SIZE_MB` por request.

| Key | Tipo |
|---|---|
| `S3_URL_EXPIRATION_HOURS` | int |
| `MAX_FILE_SIZE_MB` | int |

### Tab "Red / Proxy" (2)
Consumer migrado: `core/network.py::_effective_proxy_config()` con cache TTL 5 min para evitar abrir sesión DB en hot path.

| Key | Tipo |
|---|---|
| `TRUST_PROXY_HEADERS` | bool |
| `TRUSTED_PROXY_CIDRS` | str |

### Tab "Branding / UI" (3)
Consumer migrado: `auth_mfa.py` lee `WEBAUTHN_RP_NAME` para el registration. `FRONTEND_EMBED_BASE_URL` y `PROJECT_NAME` se exponen pero hoy se leen de env en sus consumers; aplicar override al ciclo de vida del request requiere pasar db (pendiente menor).

| Key | Tipo |
|---|---|
| `WEBAUTHN_RP_NAME` | str |
| `FRONTEND_EMBED_BASE_URL` | str |
| `PROJECT_NAME` | str |

### Tab "Observabilidad" (1)
Consumer migrado: `/metrics` resuelve el token por scrape vía DB → env, soporta rotación sin redeploy.

| Key | Tipo |
|---|---|
| `METRICS_AUTH_TOKEN` | str |

---

## 2. 🔐 Settings → Sistema → Credenciales (42 fields, 11 proveedores)

Secretos cifrados con Fernet/HKDF (o AWS KMS si `KMS_PROVIDER=aws`). Nunca echo-back en GET. Consumer-by-consumer adopt: hoy migrado **SMTP** vía `auth_service.send_password_reset_email(db, org_id)`; el resto leen del registry cuando le pases `db`.

### SMTP — outbound email (5)
| Field | Tipo | Secreto | Env fallback |
|---|---|---|---|
| `host` | str | | `SMTP_HOST` |
| `port` | int | | `SMTP_PORT` |
| `user` | str | | `SMTP_USER` |
| `password` | str | ✓ | `SMTP_PASS` |
| `from` | str | | `SMTP_FROM` |

### AWS S3 — documents (4) 🟡
| Field | Tipo | Secreto | Env fallback |
|---|---|---|---|
| `bucket` | str | | `AWS_S3_BUCKET` |
| `region` | str | | `AWS_REGION` |
| `access_key` | str | ✓ | `AWS_ACCESS_KEY` |
| `secret_key` | str | ✓ | `AWS_SECRET_KEY` |

### Microsoft 365 / Graph (6) 🟡
| Field | Tipo | Secreto | Env fallback |
|---|---|---|---|
| `tenant_id` | str | | `AZURE_TENANT_ID` |
| `client_id` | str | | `AZURE_CLIENT_ID` |
| `client_secret` | str | ✓ | `AZURE_CLIENT_SECRET` |
| `teams_webhook` | str | ✓ | `TEAMS_WEBHOOK_URL` |
| `teams_bot_app_id` | str | | `TEAMS_BOT_APP_ID` |
| `sharepoint_site_id` | str | | `SHAREPOINT_SITE_ID` |

### Slack (2) 🟡
| Field | Tipo | Secreto | Env fallback |
|---|---|---|---|
| `webhook_url` | str | ✓ | `SLACK_WEBHOOK_URL` |
| `signing_secret` | str | ✓ | `SLACK_SIGNING_SECRET` |

### Twilio — SMS/WhatsApp (3) 🟡
No tiene env vars en `config.py` — totalmente UI.

| Field | Tipo | Secreto |
|---|---|---|
| `account_sid` | str | |
| `auth_token` | str | ✓ |
| `from_number` | str | |

### Stripe — payments (3) 🟡
| Field | Tipo | Secreto | Env fallback |
|---|---|---|---|
| `publishable_key` | str | | `STRIPE_PUBLISHABLE_KEY` |
| `secret_key` | str | ✓ | `STRIPE_SECRET_KEY` |
| `webhook_secret` | str | ✓ | `STRIPE_WEBHOOK_SECRET` |

### DocuSign — e-signature (4) 🟡
| Field | Tipo | Secreto | Env fallback |
|---|---|---|---|
| `integration_key` | str | ✓ | `DOCUSIGN_INTEGRATION_KEY` |
| `secret_key` | str | ✓ | `DOCUSIGN_SECRET_KEY` |
| `account_id` | str | | `DOCUSIGN_ACCOUNT_ID` |
| `base_url` | str | | `DOCUSIGN_BASE_URL` |

### Adobe Sign — e-signature (3) 🟡
| Field | Tipo | Secreto | Env fallback |
|---|---|---|---|
| `client_id` | str | | `ADOBE_SIGN_CLIENT_ID` |
| `client_secret` | str | ✓ | `ADOBE_SIGN_CLIENT_SECRET` |
| `base_url` | str | | `ADOBE_SIGN_BASE_URL` |

### AI provider keys (4) 🟡
| Field | Tipo | Secreto | Env fallback |
|---|---|---|---|
| `anthropic_api_key` | str | ✓ | `ANTHROPIC_API_KEY` |
| `openai_api_key` | str | ✓ | `OPENAI_API_KEY` |
| `azure_speech_key` | str | ✓ | `AZURE_SPEECH_KEY` |
| `google_stt_api_key` | str | ✓ | `GOOGLE_STT_API_KEY` |

### Inbound webhooks (signing secrets, 5) 🟡
| Field | Tipo | Secreto | Env fallback |
|---|---|---|---|
| `webhook_secret` | str | ✓ | `WEBHOOK_SECRET` |
| `inbound_email_secret` | str | ✓ | `INBOUND_EMAIL_SECRET` |
| `github_secret` | str | ✓ | `GITHUB_WEBHOOK_SECRET` |
| `gitlab_secret` | str | ✓ | `GITLAB_WEBHOOK_SECRET` |
| `scim_bearer_token` | str | ✓ | `SCIM_BEARER_TOKEN` |

### OpenExchangeRates — currency (1) ✅
Consumer migrado: `/currency/sync-openexchangerates` lee del registry.

| Field | Tipo | Secreto | Env fallback |
|---|---|---|---|
| `app_id` | str | ✓ | `OPEN_EXCHANGE_RATES_APP_ID` |

---

## 3. 📋 Otras páginas existentes en Settings

| Setting / función | Página | Notas |
|---|---|---|
| Empresa, logo, currency, timezone, language, work hours, budget threshold, overload threshold, idle timeout | **Settings → Personal → General** | Tabla `app_settings` (sin tipado). Reemplazo legacy del que parte el modelo. |
| `LOG_LEVEL` runtime | **Settings → Sistema → Nivel de log** | Endpoint propio existente |
| Tipos/estados de proyecto y tarea, departamentos, sedes, festivos, vacaciones | **Settings → Workspace** | Tablas `custom_*_*`, `departments`, `holidays` |
| Roles + permisos por módulo | **Settings → Sistema → Roles** | `advanced-config/roles` |
| Tarifas, plantillas, alertas, campos extra, numeración | **Settings → Workspace** | `advanced-config/*` |
| Email-to-ticket, e-firma | **Settings → Sistema** | Endpoints dedicados |

---

## 4. 🔴 Solo `.env` — bootstrap (~35)

Cambios requieren redeploy. Movilos a BD **no** tendría efecto sin reinicio o falla silenciosamente.

### Identidad / arranque
| Key | Por qué |
|---|---|
| `VERSION` | Identidad del build, expuesta en `/health` y métricas |
| `API_V1_STR` / `API_V2_STR` | Routing montado a app-construction time |
| `ENVIRONMENT` | Drives validators, scheduler safety, security headers |
| `DEBUG` | FastAPI debug flag, lifecycle |
| `ALLOWED_ORIGINS` | `CORSMiddleware.__init__` |

### Conectividad obligatoria
| Key | Por qué |
|---|---|
| `DATABASE_URL` | Bootstrap paradox — necesario para leer cualquier setting de BD |
| `REDIS_URL` | Bootstrap del rate limiter + Celery broker |
| `RATE_LIMIT_REQUIRE_REDIS_IN_PRODUCTION` | Decisión de arranque |

### Crypto / KMS
| Key | Por qué |
|---|---|
| `SECRET_KEY` | Master key — rotación vía `key_management`, no por cambiar valor |
| `ALGORITHM` | JWT algorithm |
| `KMS_PROVIDER` / `AWS_KMS_KEY_ID` / `AWS_KMS_REGION` | Backend de envelope encryption |
| `BCRYPT_ROUNDS` | Cambiarlo afecta validación de hashes existentes |

### Seed / bootstrap creds
| Key | Por qué |
|---|---|
| `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD` | **El `.env` manda, en cada arranque** — no solo el primero. Ver abajo. |
| `DEFAULT_USER_PASSWORD` | Solo seed demo |
| `CLIENT_PORTAL_SECRET` | HMAC key para magic-links |

**El `.env` manda sobre el superadmin (2026-09-17).** La siembra sólo creaba la
cuenta si no existía, así que cambiar `SUPERADMIN_PASSWORD` en el fichero no
cambiaba nada en cuanto existía. Ahora `_sembrar_usuarios` (en
`app/db/seed_parts/core.py`) reaplica esa contraseña en cada siembra, reactiva la
cuenta y le asegura su organización.

Es la vía de recuperación de un administrador bloqueado, y una vía que sólo
funciona el primer día no es una vía. **El precio:** cambiar esa contraseña desde
la aplicación no sobrevive a un reinicio; sólo afecta a esta cuenta. Lo fija
`tests/test_superadmin_env_manda.py`, que inspecciona la función por nombre —no
por posición— para que reordenar el fichero no lo rompa en falso.

El mismo criterio se aplica en contecmind, contecweb, contecintelligence y
contecpos.

### Observabilidad — módulo load
| Key | Por qué |
|---|---|
| `SENTRY_DSN` / `SENTRY_ENVIRONMENT` | `sentry_sdk.init()` al import |
| `OTEL_ENABLED` / `OTEL_SERVICE_NAME` / `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_EXPORTER_OTLP_HEADERS` | TracerProvider en module load |
| `METRICS_ENABLED` / `PROMETHEUS_MULTIPROC_DIR` | `setup_metrics()` al startup |

### Scheduler bind-time
| Key | Por qué |
|---|---|
| `KEY_ROTATION_RUN_HOUR_UTC` | `CronTrigger(hour=...)` al startup |
| `ENABLE_APSCHEDULER` / `ENABLE_CELERY_BEAT` / `FAIL_ON_DUAL_SCHEDULER` | Decisión de modo en lifespan |
| `CELERY_AGENT_TASK_TIME_LIMIT` / `_SOFT_TIME_LIMIT` | Decorator binding en Celery |

### Routing / WebAuthn / network
| Key | Por qué |
|---|---|
| `BASE_URL` / `FRONTEND_URL` / `BACKEND_URL` | Construido al startup, raramente cambia |
| `PDF_STORAGE_PATH` | Path de filesystem leído al boot |
| `WEBAUTHN_RP_ID` | Validado contra origin del navegador (mover rompe passkeys) |
| `WEBAUTHN_ORIGIN` | Mismo |
| `RATE_LIMIT_DEFAULT` | Decorator binding en slowapi |
| `MICROSOFT_OAUTH_BASE` / `GOOGLE_OAUTH_BASE` / `GOOGLE_TOKEN_URL` | URLs de proveedor SSO (técnicamente keep-env, pero rara vez cambian) |

### Compose / infra
| Key | Por qué |
|---|---|
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | docker-compose, no la app |
| `REDIS_PASSWORD` | docker-compose |
| `HTTP_PORT` / `HTTPS_PORT` | docker-compose |
| `VITE_API_URL` | Build-time del frontend |

---

## 5. ⚪ Solo `.env` — keep-env (~25)

Pragmáticamente env: URLs públicas estables y constantes de presentación. No hay valor en exponerlas en UI.

### URLs de proveedores IA (16)
`ANTHROPIC_API_URL`, `ANTHROPIC_DOCS_URL`, `OPENAI_API_URL`, `OPENAI_DOCS_URL`, `GEMINI_API_URL`, `GEMINI_DOCS_URL`, `DEEPSEEK_API_URL`, `DEEPSEEK_DOCS_URL`, `GROQ_API_URL`, `GROQ_DOCS_URL`, `MISTRAL_API_URL`, `MISTRAL_DOCS_URL`, `OLLAMA_BASE_URL`, `OLLAMA_DOCS_URL`, `AZURE_OPENAI_API_URL`, `AZURE_OPENAI_DOCS_URL`

### Otras URLs base
| Key | Default |
|---|---|
| `SLACK_API_BASE` | `https://slack.com/api` |
| `GOOGLE_CHART_URL` | (URL pública Google Charts) |
| `XERO_API_BASE` | `https://api.xero.com/api.xro/2.0` |
| `QB_API_BASE` | `https://quickbooks.api.intuit.com/v3/company` |
| `WEBAUTHN_RP_NAME` | "Contecflow PSA" (display only) |
| `NOTIFICATION_EMAIL_FROM` | `alerts@contecflow.local` (también en general settings) |

### Constantes del proyecto
| Key | Default |
|---|---|
| `PROJECT_NAME` | "Contecflow" |
| `ALLOW_LOCAL_LOGIN` | `true` |

---

## 6. 🟢 Estado actual de consumers

Lista de los consumers que migré recientemente y los que conscientemente quedan en env.

### ✅ Consumers migrados (leen runtime cuando reciben `db`)

| Setting / grupo | Consumer | Archivo |
|---|---|---|
| `SLA_P*_HOURS` | `calculate_sla_due` via `get_sla_hours(db)` | `services/sla_service.py` |
| `HEALTH_*`, `PROJECT_HEALTH_*` | `compute_composite_health` + `compute_health` | `services/customer_health_service.py`, `services/activity_service.py` |
| `SEM_THRESHOLD_*` | `SemanticAssigner._suggest` (5 thresholds) | `services/semantic_classifier.py` |
| `MIN_PASSWORD_LENGTH`, `PASSWORD_REQUIRE_*`, `LOGIN_*` | `validate_password_policy(db=...)` | `core/security.py` |
| Locale defaults (`DEFAULT_*`) | `GET /settings/org-defaults` | `api/v1/endpoints/settings.py` |
| `ACCESS_TOKEN_EXPIRE_MINUTES`, `_MAX_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS` | `create_access_token / create_refresh_token`, `set_auth_cookies`, `register_or_rotate_user_session` | `core/security.py`, `services/auth_service.py`, `services/session_security.py` |
| `KEY_ROTATION_ENABLED`, `JWT_KEY_ROTATION_DAYS`, `JWT_KEY_RETENTION_COUNT`, `INTEGRATION_SECRET_ROTATION_DAYS` | `_rotate_jwt_keyring`, `rotate_due_materials`, `get_integration_rotation_status` | `services/key_management.py` |
| `CONTECFLOW_AI_MODEL`, `ANTHROPIC_API_KEY` | `ai_client.get_api_key/get_default_model/call_claude(db=...)`, `ai_modules_service.api_key/call_claude(db=...)` | `services/ai_client.py`, `services/ai_modules_service.py` |
| `M365_CALENDAR_SYNC_ENABLED`, `M365_TEAMS_NOTIFICATIONS_ENABLED` | `/api/v1/m365/status` | `api/v1/endpoints/m365.py` |
| `EXCHANGE_RATES_AUTO_UPDATE`, `OPEN_EXCHANGE_RATES_APP_ID` | `sync_openexchangerates` (key vía credentials registry) | `api/v1/endpoints/currency_sync.py` |
| `S3_URL_EXPIRATION_HOURS`, `MAX_FILE_SIZE_MB`, `AWS_*` | `S3Service.reload_from_db(db, org_id)` + endpoints documents | `services/s3_service.py`, `api/v1/endpoints/documents.py` |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | `create_payment_link_record`, `handle_stripe_webhook` | `services/v238_service.py` |
| `SMTP_*` | `send_password_reset_email(db, org_id)` | `services/auth_service.py` |
| `WEBAUTHN_RP_NAME` | MFA registration options | `api/v1/routers/auth_mfa.py` |
| `METRICS_AUTH_TOKEN` | `/metrics` Bearer check per-scrape | `core/metrics.py` |
| `TRUST_PROXY_HEADERS`, `TRUSTED_PROXY_CIDRS` | `_effective_proxy_config()` con cache TTL 5min | `core/network.py` |
| Integraciones (Jira, Twilio, MS Graph) | wrapper `track_external_call` + credenciales registry | múltiples |

### 🟡 Registrado pero consumer aún env (mejora menor — pasar `db`)

| Setting | Consumer pendiente | Estimación |
|---|---|---|
| `OPENAI_STT_MODEL`, `STT_PROVIDER`, `STT_FALLBACK_PROVIDERS`, `AZURE_SPEECH_REGION`, `AZURE_STT_LANGUAGE`, `GOOGLE_STT_LANGUAGE` | `services/stt/*` | 5 archivos, ~2 líneas cada uno |
| `AI_COST_ALERT_USD_PER_DAY` | telemetría AI / alert engine | 1 lugar |
| `SEMANTIC_EMBEDDINGS_BACKEND` | `semantic_classifier._resolve_embeddings_runtime` | 1 lugar |
| `OPENAI_API_KEY` | `services/stt/openai_stt.py`, `services/expense_service.py` (OCR), `mfa_service.py` | 4 lugares |
| `AZURE_SPEECH_KEY`, `GOOGLE_STT_API_KEY` | `services/stt/*` | 2 lugares |
| `FRONTEND_EMBED_BASE_URL` | BI embed URL builder (sin matches actuales en el código revisado) | recomendado al introducirse |
| `PROJECT_NAME` | branding/UI builders | bajo impacto, no urgente |

### 🔴 No portable (consumer no puede aceptar db sin redeploy)

| Setting | Por qué |
|---|---|
| `OUTBOUND_HTTP_TIMEOUT_SECONDS`, `OUTBOUND_AI_TIMEOUT_SECONDS` | Cero matches en el código vs `settings.X`. 26 callsites usan literales `timeout=N`. Refactor: helper centralizado `outbound_timeout(kind)` + sustituir 26 literales. Aparte. |
| Bootstrap entries (sec 4) | Module-load / decorator-bind / cron-bind |

---

## Conteo final actualizado

| Destino | Cantidad |
|---|---|
| 🎛 Config. dinámica (13 tabs) | **83** |
| 🔐 Credenciales (11 proveedores, 42 fields) | **42** |
| 📋 Otras páginas Settings | ~30 (legacy `app_settings` + roles/tarifas/etc.) |
| 🔴 .env bootstrap (no portable) | ~35 |
| ⚪ .env keep-env (URLs estables) | ~25 |
| 🟡 Registrado, consumer aún env (mejora menor) | ~13 |
| **Total settings únicos en `config.py` + `config_groups/`** | **191** |

