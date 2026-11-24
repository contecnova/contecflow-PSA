# Referencia de ajustes

Referencia completa de la configuración de contecflow: cada variable de entorno de `Settings` y cada ajuste editable en vivo desde la aplicación. La guía de uso (qué ajustar para implantar, en qué orden y por qué) está en el [README](../README.md#6-configuración-y-variables-de-entorno); aquí está la lista exhaustiva.

Este documento lo comprueba `tests/test_readme_ajustes_completo.py`: cada campo de `Settings` y cada clave de `RUNTIME_FLAG_GROUPS` tiene su fila, y las cifras de los encabezados son las reales. Quien añada un ajuste añade aquí su fila.

- [1. Las dos capas de configuración](#1-las-dos-capas-de-configuración)
- [2. Variables de entorno (`Settings`)](#2-variables-de-entorno-settings)
- [3. Ajustes en vivo (Configuración → Sistema → Config. dinámica)](#3-ajustes-en-vivo-configuración--sistema--config-dinámica)
- [4. Variables leídas fuera de `Settings`](#4-variables-leídas-fuera-de-settings)

## 1. Las dos capas de configuración


1. **Entorno (`.env` → `app.core.config.Settings`, pydantic-settings, `extra="ignore"`).** 724 campos (medidos el 2026-11-23; el desglose que sigue es del 2026-11-16, con 475): 244 en `config.py` y 231 en diez mixins de `app/core/config_groups/` (`ai_config` 41, `sla_config` 20, `health_config` 25, `semantic_config` 10, `service_desk_config` 36, `automations_config` 13, `proceso_config` 74, `escalas_config` 5, `empresa_config` 4, `politicas_config` 3). Se leen una sola vez al importar, así que un cambio requiere reiniciar. Los validadores detienen el arranque ante: un `SECRET_KEY` débil o de marcador de posición; un `JWT_ALGORITHM` distinto de HS256/HS384/HS512; un `ENVIRONMENT` que no sea `development`, `test`, `staging` o `production` ni uno de sus alias (`dev`, `local`, `demo`, `testing`, `stage`, `pre`, `preprod`, `prod`, `prd`, que se normalizan al canónico desde el 23-11-2026); un `DEFAULT_USER_PASSWORD`, `CLIENT_PORTAL_SECRET` o `SUPERADMIN_PASSWORD` de marcador de posición. En staging/production exigen además `WEBHOOK_SECRET`/`INBOUND_EMAIL_SECRET` (≥ 24 caracteres) y rechazan localhost en `ALLOWED_ORIGINS`, `FRONTEND_URL`, `BACKEND_URL`, `BASE_URL`, `WEBAUTHN_ORIGIN` y `WEBAUTHN_RP_ID`.
2. **Ajustes en vivo (tabla de BD `app_settings`, se editan en Configuración).** `app/services/settings_service/`::RUNTIME_FLAG_GROUPS declara **443 claves en 32 grupos** (medido el 2026-11-23 en `_catalogo.py`): `sla`, `service_desk`, `automations`, `tenants`, `audit`, `risk`, `health`, `proyectos`, `semantic`, `password_policy`, `account_security`, `locale`, `tokens`, `key_rotation`, `ai`, `conectores`, `lecciones`, `gastos`, `licencias_uso`, `licencias_integracion`, `politicas`, `presupuestos`, `alm`, `traduccion`, `feature_flags`, `storage`, `security_network`, `ui_branding`, `observability`, `informes`, `timeouts`, `semaforos`. Dos claves existen solo ahí y no tienen campo en `Settings`: `SLACK_TEAM_ID` y `TEAMS_TENANT_ID` (vinculan un espacio de trabajo de Slack o un tenant de Teams a una empresa). La resolución es **fila de la organización → fila global (`organization_id IS NULL`) → `settings.<KEY>` del entorno**. Las lecturas se cachean en proceso durante 60 s; las escrituras invalidan en local y entre workers mediante pub/sub de Redis (`app/core/settings_pubsub.py`, no hace nada sin `REDIS_URL`). No toda variable de entorno tiene un ajuste en vivo: solo son editables las claves listadas ahí.


## 2. Variables de entorno (`Settings`)

Total medido: **728 campos de `Settings`**.

Los valores por defecto son los del código, nunca valores del `.env`. Los significados se toman del nombre del campo, de su comentario en línea y del código que lo lee; el comportamiento descrito en negrita se comprobó en el código que consume la variable.

**Núcleo (`app/core/config.py`) — 159 variables**

| Nombre | Defecto | Significado |
|---|---|---|
| `PROJECT_NAME` | `'Contecflow'` | Título de la aplicación (OpenAPI, /health). |
| `VERSION` | `'23.9.3'` | Cadena de versión que informan /health y OpenAPI. |
| `API_V1_STR` | `'/api/v1'` | Prefijo de montaje de la API v1 (también de las URL de documentación). |
| `ENVIRONMENT` | `'production'` | `development`/`test`/`staging`/`production`. Alias admitidos y normalizados al arrancar (23-11-2026): `dev`, `local` y `demo` → development; `testing` → test; `stage`, `pre`, `preprod` → staging; `prod`, `prd` → production. Cualquier otro valor no arranca. Sin definir equivale a production; `setup.sh` y `setup.bat` escriben `development` cuando falta y rechazan un valor desconocido. Determina el endurecimiento de secretos, las cookies Secure, HSTS, la exposición de la documentación y la exigencia de coherencia del esquema. |
| `LOG_LEVEL` | `'INFO'` | Nivel de log de la raíz/uvicorn. |
| `SECRET_KEY` | *(required)* | **Obligatoria.** Clave heredada de JWT y raíz del cifrado a nivel de campo (PBKDF2/HKDF). ≥32 caracteres, ≥10 caracteres distintos, sin marcadores de posición. |
| `SECRET_KEY_PREVIOUS` | `''` | Claves anteriores separadas por comas, usadas solo para **descifrar** tras una rotación; las rellena `scripts/rotate_keys.sh` (README, «Rotación de claves»). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | TTL del access token; el TTL efectivo es `min(este valor, ACCESS_TOKEN_MAX_MINUTES)`. Sobrescribible en vivo. |
| `ACCESS_TOKEN_MAX_MINUTES` | `30` | Tope superior del TTL del access token. Sobrescribible en vivo. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | TTL del refresh token y de su cookie. Sobrescribible en vivo. |
| `KEY_ROTATION_ENABLED` | `True` | Activa el llavero JWT y la rotación de secretos de integración. |
| `JWT_KEY_ROTATION_DAYS` | `30` | Rota la clave de firma JWT cada N días. |
| `JWT_KEY_RETENTION_COUNT` | `3` | Claves JWT antiguas que se conservan para verificar. |
| `INTEGRATION_SECRET_ROTATION_DAYS` | `60` | Recifra los secretos de integración cada N días. |
| `KEY_ROTATION_RUN_HOUR` | `2` | Hora del trabajo de rotación, en `DEFAULT_TIMEZONE` (ambos planificadores usan esa zona). El nombre antiguo `KEY_ROTATION_RUN_HOUR_UTC` se sigue leyendo de `.env`. |
| `KMS_PROVIDER` | `''` | `aws` activa el cifrado de sobre con AWS KMS. |
| `AWS_KMS_KEY_ID` | `''` | Id de la clave KMS. |
| `AWS_KMS_REGION` | `''` | Región de KMS. |
| `DATABASE_URL` | *(required)* | **Obligatoria.** URL de SQLAlchemy (SQLite o `postgresql+psycopg2://`). |
| `DEFAULT_PROJECT_TYPE` | `'consulting'` | Tipo de proyecto por defecto de los proyectos nuevos. |
| `DEFAULT_BILLING_TYPE` | `'time_material'` | Tipo de facturación por defecto. |
| `ALLOWED_ORIGINS` | `localhost:3000/5173/8000, 127.0.0.1:8000` | Lista de orígenes permitidos de CORS **y** de CSRF (lista JSON). Debe ser explícita, sin `*`, y sin localhost en staging/production. |
| `SUPERADMIN_EMAIL` | *(required)* | **Obligatoria.** Correo del superadmin inicial (lo usan `default_seed_users()` y `reset_to_admin_only.py`). |
| `SUPERADMIN_PASSWORD` | *(required)* | **Obligatoria.** Contraseña del superadmin inicial; se reaplica en cada siembra. ≥16 caracteres fuera de entornos locales. |
| `CLIENT_PORTAL_SECRET` | *(required)* | **Obligatoria.** Secreto de firma de los tokens del portal de clientes; ≥32 caracteres en staging/production. |
| `SCIM_BEARER_TOKEN` | `''` | Bearer estático para el aprovisionamiento SCIM. |
| `SCIM_ALLOWED_ORG_ID` | `''` | Organización que ese token SCIM puede aprovisionar. |
| `WEBHOOK_SECRET` | `''` | Secreto HMAC de los webhooks entrantes; obligatorio (≥24 caracteres) en staging/production. |
| `INBOUND_EMAIL_SECRET` | `''` | Secreto del canal de correo entrante; mismas reglas que WEBHOOK_SECRET (production no arranca sin él; figura en `.env.example` desde el 13-11-2026, igual que `WEBAUTHN_RP_ID`/`WEBAUTHN_ORIGIN`). |
| `TRUST_PROXY_HEADERS` | `False` | Confía en `X-Forwarded-For` procedente de TRUSTED_PROXY_CIDRS (app/core/network.py). |
| `TRUSTED_PROXY_CIDRS` | `'127.0.0.1/32,::1/128'` | Proxies cuyas cabeceras reenviadas son de confianza. |
| `GITHUB_WEBHOOK_SECRET` | `''` | HMAC del webhook de GitHub. |
| `GITLAB_WEBHOOK_SECRET` | `''` | Token del webhook de GitLab. |
| `JIRA_WEBHOOK_SECRET` | `''` | **Ya no autentica nada** (auditoría 2026-11 n.º 14): cada organización genera su propio secreto de webhook de Jira con `POST /api/v1/jira/webhook-secret` (guardado en `app_settings`, clave `jira_webhook_secret`). El código no lee este campo. |
| `DOCUSIGN_INTEGRATION_KEY` | `''` | Alternativa por entorno de DocuSign (la configuración en BD tiene prioridad). |
| `DOCUSIGN_SECRET_KEY` | `''` | Secreto de DocuSign. |
| `DOCUSIGN_ACCOUNT_ID` | `''` | Cuenta de DocuSign. |
| `DOCUSIGN_BASE_URL` | `''` | Base de la API de DocuSign. |
| `DOCUSIGN_DEMO` | `None` | Entorno demo de DocuSign; sin definir = demo fuera de staging/production y real dentro de ellos (19-11-2026). `true` impide arrancar en production. |
| `DOCUSIGN_AUTH_BASE_DEMO` | `'https://account-d.docusign.com'` | Base OAuth de DocuSign (demo). |
| `DOCUSIGN_AUTH_BASE_PROD` | `'https://account.docusign.com'` | Base OAuth de DocuSign (producción). |
| `DOCUSIGN_API_BASE_DEMO` | `'https://demo.docusign.net'` | Base de la API de DocuSign en demo y sin DOCUSIGN_BASE_URL. |
| `DOCUSIGN_API_BASE_PROD` | `'https://na1.docusign.net'` | Base de la API de DocuSign en real y sin DOCUSIGN_BASE_URL (cuentas de la UE: https://eu.docusign.net). |
| `DOCUSIGN_CONNECT_HMAC_KEY` | `''` | HMAC de DocuSign Connect. |
| `ADOBE_SIGN_CLIENT_ID` | `''` | Cliente OAuth de Adobe Sign. |
| `ADOBE_SIGN_CLIENT_SECRET` | `''` | Secreto de Adobe Sign. |
| `ADOBE_SIGN_BASE_URL` | `''` | Base de la API de Adobe Sign de la región de la cuenta (19-11-2026: vacío = ADOBE_SIGN_DEV_BASE_URL fuera de production; con Adobe configurado y vacío, production no arranca). |
| `ADOBE_SIGN_DEV_BASE_URL` | `'https://api.na1.adobesign.com/api/rest/v6'` | Base de Adobe Sign usada solo fuera de staging/production cuando ADOBE_SIGN_BASE_URL está vacía. |
| `PROVISIONING_ENABLED` | `False` | Activa los runners de Terraform/Ansible. |
| `PROVISIONING_ROOT_DIR` | `''` | Directorio de trabajo de los runners de aprovisionamiento. |
| `MICROSOFT_OAUTH_BASE` | `'https://login.microsoftonline.com'` | Endpoint de identidad de Microsoft (SSO, credenciales de cliente de Graph, OAuth de M365). |
| `MICROSOFT_GRAPH_BASE` | `'https://graph.microsoft.com'` | Base de Microsoft Graph (sin `/v1.0`); también el ámbito del token `<base>/.default`. Nubes soberanas: `https://graph.microsoft.us`… |
| `GOOGLE_OAUTH_BASE` | `'https://accounts.google.com'` | Endpoint OAuth de Google. |
| `GOOGLE_TOKEN_URL` | `'https://oauth2.googleapis.com/token'` | Endpoint de tokens de Google. |
| `WEBAUTHN_RP_ID` | `'localhost'` | Id de la parte confiante (relying party) de las passkeys; requiere dominio real en staging/production. |
| `WEBAUTHN_RP_NAME` | `'Contecflow PSA'` | Nombre visible de la RP de las passkeys. |
| `WEBAUTHN_ORIGIN` | `'http://localhost:5173'` | Origen WebAuthn esperado (sin localhost en producción). |
| `XERO_API_BASE` | `'https://api.xero.com/api.xro/2.0'` | Base de la API de Xero. |
| `XERO_TOKEN_URL` | `'https://identity.xero.com/connect/token'` | Endpoint OAuth 2.0 de Xero para renovar el access token. |
| `QB_API_BASE` | `'https://quickbooks.api.intuit.com/v3/company'` | Base de la API de QuickBooks. |
| `BASE_URL` | `'http://localhost:8000'` | URL pública del backend (enlaces); sin localhost en producción. |
| `CONNECTOR_LOGO_BASE_URL` | `'https://cdn.contecflow.app/connectors'` | Base de los logotipos de los conectores del marketplace (19-11-2026); una instalación aislada puede servirlos ella misma. |
| `OTEL_ENABLED` | `False` | Activa la trazabilidad OpenTelemetry (necesita también el endpoint). |
| `OTEL_SERVICE_NAME` | `'contecflow-api'` | `service.name` de OTel. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `''` | Endpoint OTLP/HTTP. |
| `OTEL_EXPORTER_OTLP_HEADERS` | `''` | Cabeceras OTLP. |
| `METRICS_ENABLED` | `False` | Registra `/metrics` y la instrumentación HTTP. |
| `METRICS_AUTH_TOKEN` | `None` | Bearer de `/metrics` (la clave en vivo con el mismo nombre tiene prioridad). |
| `METRICS_MULTIPROC_DIR` | `None` | Directorio multiproceso de Prometheus (fija PROMETHEUS_MULTIPROC_DIR). |
| `METRICS_TENANT_LABEL` | `"slug"` | Valor de la etiqueta `empresa` en las métricas: `slug` o `id` de la organización (nunca datos personales). Véase docs/OBSERVABILIDAD.md. |
| `METRICS_TENANT_MAX` | `50` | Solo las primeras N organizaciones (por fecha de creación) tienen etiqueta `empresa` propia; el resto se agrupa como `otras` (cardinalidad de Prometheus acotada). |
| `METRICS_BUSINESS_ENABLED` | `True` | Métricas de negocio por organización (tickets, SLA, proyectos…) leídas de la base de datos en cada scrape. |
| `METRICS_BUSINESS_CACHE_SECONDS` | `60` | Caché (s) del recolector de métricas de negocio entre scrapes. |
| `CELERY_METRICS_PORT` | `0` | Puerto del servidor de métricas del worker/beat de Celery (0 = desactivado). Solo en la red interna de compose, no se publica en el host. |
| `FRONTEND_URL` | `'http://localhost:5173'` | URL pública de la SPA (correos, redirecciones). |
| `BACKEND_URL` | `'http://localhost:8000'` | URL pública de la API (enlace de documentación en el log). |
| `PDF_STORAGE_PATH` | `'./storage/pdfs'` | Directorio local de los PDF generados. |
| `AWS_S3_BUCKET` | `'contecflow-documents'` | Bucket de documentos. S3 solo se usa si están definidas AWS_ACCESS_KEY y AWS_SECRET_KEY (app/services/s3_service.py); si no, los ficheros van a UPLOAD_DIR. |
| `AWS_REGION` | `'eu-west-1'` | Región de S3 (debe coincidir con `VGW_REGION` de versitygw). |
| `AWS_ACCESS_KEY` | `None` | Clave de acceso de S3. |
| `AWS_SECRET_KEY` | `None` | Clave secreta de S3. |
| `AWS_S3_ENDPOINT_URL` | `None` | Endpoint compatible con S3 (versitygw/MinIO). |
| `AWS_S3_FORCE_PATH_STYLE` | `None` | Fuerza el direccionamiento path-style (None = automático). |
| `S3_URL_EXPIRATION_HOURS` | `24` | Duración de las URL prefirmadas. |
| `MAX_FILE_SIZE_MB` | `100` | Tamaño máximo de subida. |
| `SLACK_WEBHOOK_URL` | `None` | Webhook entrante de Slack para notificaciones. |
| `NOTIFICATION_EMAIL_FROM` | `'alerts@contecflow.local'` | Dirección de remitente del correo de alertas. 19-11-2026: en staging/production, un remitente `.local` o de ejemplo sin SMTP_FROM impide arrancar (`app/core/comprobacion_de_produccion.py`). |
| `DEFAULT_IMPUTATION_LOCKOUT_DAYS` | `14` | Días tras los cuales se bloquean las imputaciones de horas. |
| `EXTERNOS_UMBRAL_CONSUMO_PCT` | `80.0` | Personal externo (rev. 178): avisa al responsable interno y al PM cuando una asignación consume este % de sus horas contratadas o del importe del pedido (y de nuevo al 100 %). En vivo (`proyectos`). |
| `EXTERNOS_AVISO_CADUCIDAD_DIAS` | `14` | Personal externo (rev. 178): días de antelación con que el trabajo diario `externos_caducidad` avisa de que caduca el acceso de un externo. En vivo (`proyectos`). |
| `PROVEEDORES_TOLERANCIA_CONCILIACION_PCT` | `2.0` | Proveedores (rev. 189): diferencia aceptada (%) entre la factura del proveedor y la previsión del periodo; dentro de ella el extracto queda `reconciled`, fuera `disputed`. En vivo (`proyectos`). |
| `PROVEEDORES_AVISO_DOCUMENTO_DIAS` | `30` | Proveedores (rev. 189): días de antelación con que el trabajo diario avisa al responsable interno de que caduca un documento o certificación de un proveedor. En vivo (`proyectos`). |
| `PROVEEDORES_REVISION_RIESGO_MESES` | `12` | Proveedores (rev. 189): meses hasta la siguiente revisión de riesgo tras una evaluación (la mitad si el riesgo es alto o crítico). En vivo (`proyectos`). |
| `DEFAULT_TIMEZONE` | `'Europe/Madrid'` | Zona horaria de reserva; también es la **zona horaria de Celery beat y de APScheduler**. |
| `DEFAULT_LANGUAGE` | `'es'` | Idioma de interfaz de reserva. |
| `DEFAULT_CURRENCY` | `'EUR'` | Moneda de reserva. |
| `DEFAULT_COUNTRY` | `'ES'` | País por defecto (ISO 3166-1 alfa-2) de clientes y proveedores nuevos; clave en vivo por empresa (19-11-2026). |
| `SUPPORTED_CURRENCIES` | `'EUR,USD,GBP,PLN,CHF,SEK,DKK,NOK,JPY,CAD,AUD,MXN,BRL'` | Monedas ofrecidas en las pantallas. |
| `CURRENCY_SYMBOLS` | `'EUR:€,USD:$,GBP:£'` | Símbolos de moneda en los documentos. |
| `DEFAULT_TAX_RATE` | `21.0` | % de IVA de reserva. |
| `TAX_NAME` | `''` | Nombre del impuesto en las facturas (VAT, IVA, GST...); vacío = el habitual del idioma de la factura (18-11-2026). |
| `INVOICE_ISSUER_NAME` | `''` | Emisor de la factura — razón social impresa en las facturas (auditoría 22-11-2026, A54). |
| `INVOICE_ISSUER_TAX_ID` | `''` | Emisor de la factura — identificación fiscal (NIF/VAT) impresa en las facturas (auditoría 22-11-2026, A54). |
| `INVOICE_ISSUER_ADDRESS` | `''` | Emisor de la factura — domicilio social impreso en las facturas (auditoría 22-11-2026, A54). |
| `INVOICE_ISSUER_IBAN` | `''` | Emisor de la factura — IBAN de pago impreso en las facturas (auditoría 22-11-2026, A54). |
| `COMPANY_SECTOR` | `''` | Sector de la empresa para la narrativa de IA del BI; vacío = no se asume ninguno (18-11-2026). |
| `MIN_PASSWORD_LENGTH` | `8` | Política de contraseñas. |
| `BCRYPT_ROUNDS` | `12` | Coste de bcrypt. |
| `PASSWORD_REQUIRE_UPPERCASE` | `True` | Política de contraseñas. |
| `PASSWORD_REQUIRE_LOWERCASE` | `True` | Política de contraseñas. |
| `PASSWORD_REQUIRE_DIGIT` | `True` | Política de contraseñas. |
| `PASSWORD_REQUIRE_SPECIAL` | `True` | Política de contraseñas. |
| `LOGIN_MAX_ATTEMPTS` | `5` | Inicios de sesión fallidos antes del bloqueo. |
| `LOGIN_ATTEMPT_WINDOW_SECONDS` | `900` | Ventana para contar los fallos. |
| `LOGIN_LOCKOUT_SECONDS` | `900` | Duración del bloqueo. |
| `DEFAULT_USER_PASSWORD` | *(required)* | **Obligatoria.** Contraseña de los usuarios semilla que no son superadmin; se rechaza si es `CHANGE_ME*` o (fuera de entornos locales) el valor histórico por defecto. |
| `DEFAULT_WORKING_HOURS_PER_DAY` | `8.0` | Capacidad por defecto. |
| `DEFAULT_WEEKLY_CAPACITY_HOURS` | `40.0` | Capacidad por defecto. |
| `DEFAULT_PRODUCTIVE_HOURS_YEAR` | `1700.0` | Coste de personal: horas productivas al año de reserva (prevalecen el perfil de coste y el preset del país); clave en vivo `locale`. |
| `DEFAULT_EMPLOYER_COST_PCT` | `0.32` | Coste de personal: coste de empresa sobre el salario bruto de reserva; clave en vivo `locale`. |
| `DEFAULT_SIMULATION_HOURLY_RATE` | `80.0` | Tarifa usada en las simulaciones «y si». |
| `DEFAULT_VACATION_DAYS_PER_YEAR` | `23` | Ausencia por defecto. |
| `DEFAULT_WORKDAY_START` | `09:00` | Inicio de la jornada de la empresa para personas sin turno ni horario laboral (rev. 180); clave en vivo `locale`. |
| `ABSENCE_BALANCE_CARRY_PERIODS` | `2` | Periodos de saldo que se miran hacia atrás para arrastrar los sobrantes (rev. 180); clave en vivo `locale`. |
| `HOUR_BANK_RECALC_DAYS` | `35` | Días hacia atrás que el pase diario recalcula la bolsa de horas (rev. 180); clave en vivo `locale`. |
| `PLANNING_SCHEDULE_HORIZON_DAYS` | `400` | Días hacia delante del planificador con el horario efectivo de cada persona (rev. 180); clave en vivo `proyectos`. |
| `REDIS_URL` | `None` | Broker **y** backend de resultados de Celery, almacenamiento del límite de tasa, tickets de WS, pub/sub de ajustes. Sin definir = alternativas en proceso. |
| `RATE_LIMIT_REQUIRE_REDIS_IN_PRODUCTION` | `True` | Impide arrancar en production si Redis no es accesible para el limitador. |
| `SENTRY_DSN` | `None` | Activa Sentry. |
| `SENTRY_ENVIRONMENT` | `'development'` | Etiqueta de entorno de Sentry. |
| `AZURE_TENANT_ID` | `None` | Aplicación M365/Azure AD (Graph). |
| `AZURE_CLIENT_ID` | `None` | Id de la aplicación M365. |
| `AZURE_CLIENT_SECRET` | `None` | Secreto de la aplicación M365. |
| `M365_PLATFORM_CREDENTIALS_ENABLED` | `False` | Permite que una empresa sin credencial propia de *Microsoft 365 / Graph* use los `AZURE_*` de la plataforma (instalaciones de una sola empresa). Desactivado: cada empresa guarda su propia aplicación de Azure (2026-11-23, auditoría 03 A-MP3). |
| `M365_CALENDAR_SYNC_ENABLED` | `False` | Activa la sincronización del calendario. |
| `M365_TEAMS_NOTIFICATIONS_ENABLED` | `False` | Activa las notificaciones de Teams. |
| `TEAMS_WEBHOOK_URL` | `None` | Webhook entrante de Teams. |
| `SHAREPOINT_SITE_ID` | `None` | Sitio de SharePoint para documentos. |
| `FRONTEND_EMBED_BASE_URL` | `''` | URL base de los embeds de BI en Teams/SharePoint. |
| `BI_EMBED_FRAME_ANCESTORS` | `"'self' https://teams.microsoft.com https://*.teams.microsoft.com https://*.cloud.microsoft https://*.sharepoint.com"` | Página de embed de BI — quién puede mostrarla en un iframe (CSP frame-ancestors, separados por espacios) |
| `SMTP_HOST` | `''` | Host SMTP de salida. |
| `SMTP_USER` | `''` | Usuario SMTP. |
| `SMTP_PORT` | `587` | Puerto SMTP. |
| `SMTP_PASS` | `''` | Contraseña SMTP. |
| `SMTP_FROM` | `''` | Remitente (From) SMTP. |
| `TWILIO_ACCOUNT_SID` | `None` | Twilio (SMS/voz). |
| `TWILIO_AUTH_TOKEN` | `None` | Token de Twilio. |
| `OUTBOUND_PRIVATE_HOSTS_ALLOWED` | `""` | Hosts internos (separados por comas) a los que pueden llegar las llamadas salientes aunque resuelvan a una red privada (p. ej. un Jira local). Véase `app/core/outbound_url.py`. |
| `MAX_REQUEST_BODY_MB` | `110` | Tope duro (MB) del cuerpo de cualquier petición: Content-Length y bytes en streaming, 413 por encima (`app/core/limite_de_cuerpo.py`). Mantener >= MAX_FILE_SIZE_MB más la sobrecarga del formulario. 0 lo desactiva. |
| `CMDB_DISCOVERY_ALLOW_PLATFORM_CREDENTIALS` | `False` | Permite que el descubrimiento de la CMDB recurra a las credenciales de nube del propio servidor (cadena de boto3, kubeconfig local o del clúster, DefaultAzureCredential, GCP ADC/fichero). Desactivado: solo credenciales explícitas por empresa. |
| `JWT_KEYRING_CACHE_SECONDS` | `60` | Caché por proceso del llavero de claves JWT; un `kid` desconocido también fuerza la recarga, de modo que una rotación hecha por Celery llega a los workers web. 0 = hasta el reinicio. |
| `MIGRATION_BACKUP_MODE` | `'destructive'` | Copia de seguridad antes de que `scripts/migrar.py` migre: `destructive` (una revisión pendiente borra o elimina datos), `always` u `off`. Copia del fichero en SQLite; pg_dump si está en el PATH, si no, un aviso. |
| `MIGRATION_BACKUP_DIR` | `'backups'` | Carpeta de las copias previas a la migración (datos personales: mismo acceso y retención que la base de datos). |
| `REDIS_PASSWORD` | `None` | `requirepass` de Redis (docker-compose); se inyecta en REDIS_URL cuando esta no lleva credenciales. Lo genera setup. |
| `COUNTRY_EMPLOYER_COSTS_PATH` | `""` | Fichero JSON que sustituye los presets de coste social del empleador por país (`app/core/country_employer_costs.json`). |
| `TWILIO_FROM_NUMBER` | `None` | Remitente de Twilio. |
| `CLIENT_TOKEN_EXPIRE_HOURS` | `72` | TTL del token del portal de clientes. |
| `PORTAL_SHARE_LINK_EXPIRE_HOURS` | `72` | TTL del enlace compartido del portal. |
| `JWT_ALGORITHM` | `'HS256'` | Firma de los tokens del personal y del portal de clientes. Las claves son simétricas, así que solo se aceptan HS256, HS384 o HS512. |
| `WS_TICKET_TTL_SECONDS` | `60` | Vida (s) del ticket de un solo uso que abre un WebSocket. |
| `PBKDF2_ITERATIONS` | `260000` | Iteraciones de la derivación de clave v1 heredada. |
| `MAX_APPS_PER_USER` | `10` | Aplicaciones OAuth del portal de desarrolladores por usuario. |
| `WEBHOOK_CB_THRESHOLD` | `5` | Fallos consecutivos antes de suspender un webhook saliente. |
| `AI_REVENUE_HOURLY_RATE_FALLBACK` | `85.0` | Tarifa horaria que usan las estimaciones de ingresos de IA cuando no se conoce ninguna. |
| `UPLOAD_DIR` | `'uploads'` | Directorio local de subidas. |
| `COLLAB_CALL_START_PER_MIN` | `8` | Límite de tasa de la colaboración. |
| `COLLAB_CALL_JOIN_PER_MIN` | `20` | Límite de tasa de la colaboración. |
| `COLLAB_CALL_HISTORY_LIMIT` | `50` | Tamaño de página del historial de llamadas. |
| `COLLAB_WEBHOOK_INCOMING_PER_MIN` | `120` | Límite de tasa del webhook entrante de colaboración. |
| `COLLAB_CALENDAR_MAX_EVENTS` | `20` | Eventos de calendario devueltos. |
| `COLLAB_PORTAL_MESSAGE_PER_MIN` | `25` | Límite de tasa de mensajes del portal. |
| `STT_PROVIDER` | `'openai'` | Proveedor de voz a texto. |
| `STT_FALLBACK_PROVIDERS` | `''` | Lista separada por comas de alternativas. |
| `AZURE_SPEECH_KEY` | `''` | Clave de STT de Azure. |
| `AZURE_SPEECH_REGION` | `'westeurope'` | Región de STT de Azure. |
| `ML_FACTOR_DE_SOBRECOSTE` | `1.10` | Modelo de sobrecoste (`ml_features`): coste real > presupuesto × factor = sobrecoste (23-11-2026; antes fijo). Cambiarlo cambia las etiquetas: reentrenar. |
| `STT_COSTE_USD_POR_MINUTO` | `0.006` | Coste estimado de la voz por minuto de audio (23-11-2026): cuenta para el tope diario de gasto en IA; sin duración del proveedor se estima por tamaño (16 kB/s). |
| `AZURE_STT_LANGUAGE` | `''` | Idioma de STT de Azure. Vacío (19-11-2026) = idioma del usuario o de la empresa; un valor fija la variante regional. |
| `GOOGLE_STT_API_KEY` | `''` | Clave de STT de Google. |
| `GOOGLE_STT_LANGUAGE` | `''` | Idioma de STT de Google. Vacío (19-11-2026) = idioma del usuario o de la empresa. |
| `SLACK_API_BASE` | `'https://slack.com/api'` | Base de la API de Slack. |
| `SALESFORCE_API_VERSION` | `'v57.0'` | Versión de la API REST de Salesforce (23-11-2026; antes fija en la URL). |
| `WEBHOOK_OUTBOUND_PER_MIN` | `120` | Entregas de webhooks salientes por webhook y minuto (23-11-2026; antes fijo en `webhooks.py`). |
| `SLACK_CANAL_POR_DEFECTO` | `'#contecflow-alerts'` | Canal de Slack si la configuración de la empresa no fija uno (23-11-2026; antes `#general`/`#contecflow-alerts` fijos). Sin token ni webhook, el envío falla (`slack_sin_configurar`), ya no «simula» éxito. |
| `SLACK_SIGNING_SECRET` | `''` | Secreto de firma de las peticiones de Slack. |
| `TEAMS_BOT_APP_ID` | `''` | Id de la aplicación del bot de Teams. |
| `TEAMS_BOT_OPENID_METADATA_URL` | `'https://login.botframework.com/v1/.well-known/openidconfiguration'` | Metadatos OpenID de Bot Framework. |
| `TEAMS_BOT_ISSUER` | `'https://api.botframework.com'` | Emisor (issuer) de Bot Framework. |
| `STRIPE_SECRET_KEY` | `None` | Stripe. |
| `STRIPE_PUBLISHABLE_KEY` | `None` | Stripe. |
| `STRIPE_WEBHOOK_SECRET` | `None` | Firma del webhook de Stripe. |
| `OPEN_EXCHANGE_RATES_APP_ID` | `None` | Proveedor de tipos de cambio. |
| `EXCHANGE_RATES_AUTO_UPDATE` | `False` | Actualiza automáticamente los tipos de cambio. |
| `RATE_LIMIT_DEFAULT` | `'200/minute'` | Límite de toda ruta sin su propio `@limiter.limit`, por ruta y por usuario (o IP). |
| `CELERY_AGENT_TASK_TIME_LIMIT` | `300` | Límite duro de las tareas de agente (s). |
| `CELERY_AGENT_TASK_SOFT_TIME_LIMIT` | `280` | Límite blando (s). |
| `OUTBOUND_HTTP_TIMEOUT_SECONDS` | `10.0` | Timeout HTTP saliente por defecto (sobrescribible en vivo). |
| `OUTBOUND_AI_TIMEOUT_SECONDS` | `60.0` | Timeout de las llamadas salientes de IA (sobrescribible en vivo). |

**Políticas de cuenta (`app/core/config_groups/seguridad_de_cuentas_config.py`, 23-11-2026) — 26 variables**

| Nombre | Defecto | Significado |
|---|---|---|
| `PASSWORD_MAX_LENGTH` | `128` | Política de contraseñas — longitud máxima (NIST: permitir al menos 64). Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `PASSWORD_BLOCK_COMMON` | `True` | Política de contraseñas — rechaza contraseñas comunes o filtradas de la lista LOCAL (no se envía nada a terceros). Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `PASSWORD_BLOCK_PERSONAL` | `True` | Política de contraseñas — rechaza contraseñas que contengan el nombre de usuario, la parte local del correo o el nombre. Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `PASSWORD_HISTORY_COUNT` | `5` | Política de contraseñas — las últimas N contraseñas no se pueden reutilizar (se guardan hashes bcrypt). 0 = sin historial. Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `PASSWORD_MIN_AGE_HOURS` | `0` | Política de contraseñas — horas antes de poder cambiar de nuevo una contraseña (evita recorrer el historial). 0 = desactivado. Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `PASSWORD_EXPIRY_DAYS` | `0` | Política de contraseñas — días hasta que caduca una contraseña y debe cambiarse al iniciar sesión. 0 = nunca (recomendación del NIST). Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `PASSWORD_EXPIRY_WARNING_DAYS` | `14` | Política de contraseñas — avisa tantos días antes de que caduque la contraseña. Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `TEMP_PASSWORD_EXPIRY_HOURS` | `72` | Política de contraseñas — horas de validez de una contraseña temporal fijada por un administrador. Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `LOGIN_LOCKOUT_NOTIFY_USER` | `True` | Bloqueo de cuenta — avisa al usuario cuando se bloquea su cuenta. Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `MFA_REQUIRED_ROLES` | `'admin'` | MFA — roles base que deben usar un segundo factor (CSV). Vacío = ninguno (sigue aplicando el interruptor de toda la empresa). Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `MFA_REQUIRED_FOR_SENSITIVE` | `True` | MFA — obligatorio para quien tenga una capacidad sensible (administración, costes, personas, seguridad). Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `MFA_ALLOWED_METHODS` | `'totp,webauthn'` | MFA — segundos factores permitidos (CSV de totp, webauthn). Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `MFA_GRACE_DAYS` | `7` | MFA — días durante los que un usuario al que se acaba de exigir MFA aún puede iniciar sesión sin él. Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `MFA_REMEMBER_DEVICE_DAYS` | `0` | MFA — días durante los que un dispositivo puede saltarse el desafío de MFA tras superar uno. 0 = desactivado. Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `SESSION_MAX_HOURS` | `0` | Sesiones — duración máxima absoluta desde el inicio de sesión (horas). 0 = sin tope (NIST AAL2: 24). Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `SESSION_MAX_CONCURRENT` | `0` | Sesiones — máximo de sesiones simultáneas por usuario; se cierra la más antigua. 0 = ilimitadas. Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `ACCESS_IP_ALLOWLIST` | `''` | Acceso — IP/CIDR autorizadas a iniciar sesión y usar la API (CSV). Vacío = cualquiera. El superadmin de la plataforma está exento. Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `ACCESS_HOURS` | `''` | Acceso — franja horaria permitida HH:MM-HH:MM en la zona horaria de la empresa (puede cruzar la medianoche). Vacío = a cualquier hora. Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `ACCESS_DAYS` | `'1,2,3,4,5,6,7'` | Acceso — días de la semana ISO permitidos (1 = lunes) cuando ACCESS_HOURS está definido. Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `ACCESS_HOURS_EXEMPT_ROLES` | `'admin'` | Acceso — roles base exentos de la franja horaria (CSV). Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `ACCESS_BLOCKED_COUNTRIES` | `''` | Acceso — países ISO-3166 alfa-2 bloqueados (CSV). Solo actúa cuando se conoce el país (cabecera de proxy de confianza o GEOIP_LOOKUP_ENABLED). Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `ACCOUNT_INACTIVE_DISABLE_DAYS` | `0` | Cuentas — el trabajo diario desactiva las cuentas sin inicio de sesión durante estos días. 0 = desactivado. Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `SECURITY_SOD_TWO_ADMINS` | `False` | Segregación de funciones — los cambios de política de seguridad y los restablecimientos de MFA requieren un segundo administrador. Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `SECURITY_ALERT_FAILED_LOGINS` | `20` | Alertas — inicios de sesión fallidos en 15 minutos en la empresa que alertan a los administradores. 0 = desactivado. Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `SOC_FUERZA_BRUTA_VENTANA_MIN` | `10` | SOC (`security_observability`) — ventana en minutos de fallos de login por IP (23-11-2026: antes constante). |
| `SOC_FUERZA_BRUTA_FALLOS` | `5` | SOC — fallos por IP en la ventana que abren una detección de fuerza bruta. |
| `SOC_CRED_STUFFING_USUARIOS` | `3` | SOC — usuarios distintos atacados por una IP que la convierten en credential stuffing (antes `CRED_STUFFING_THRESHOLD`=20 sin usar y `3` fijo). |
| `SOC_MFA_FALLOS` | `3` | SOC — fallos de MFA de una persona en 15 min que abren una detección. |
| `SECURITY_ALERT_NEW_IP` | `True` | Alertas — avisa a los administradores cuando un usuario inicia sesión desde una IP que nunca se había visto para él. Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |
| `ACCESS_REVIEW_INTERVAL_DAYS` | `90` | Revisión de accesos — una campaña debe cerrarse al menos cada tantos días (informe de cumplimiento). 0 = no se exige. Por empresa (`account_security`/`password_policy`), docs/seguridad/politicas_de_cuenta.md. |

**IA (`config_groups/ai_config.py`) — 26 variables**

| Nombre | Defecto | Significado |
|---|---|---|
| `AI_PROVIDER` | `''` | Proveedor de IA a nivel de despliegue (último paso de la cadena org→global→env). |
| `AI_API_KEY` | `''` | Clave de AI_PROVIDER. |
| `AI_MODEL` | `''` | Modelo de AI_PROVIDER. |
| `AI_BASE_URL` | `''` | URL base (Ollama/Azure). |
| `ANTHROPIC_API_KEY` | `''` | Alias heredado de `AI_PROVIDER=anthropic` + `AI_API_KEY`. |
| `ANTHROPIC_API_URL` | `'https://api.anthropic.com/v1'` | URL base de la API del proveedor. |
| `ANTHROPIC_DOCS_URL` | `'https://www.anthropic.com/docs'` | Enlace a la documentación del proveedor que se muestra en la interfaz. |
| `OPENAI_API_URL` | `'https://api.openai.com/v1'` | URL base de la API del proveedor. |
| `OPENAI_DOCS_URL` | `'https://platform.openai.com/docs'` | Enlace a la documentación del proveedor que se muestra en la interfaz. |
| `GEMINI_API_URL` | `'https://generativelanguage.googleapis.com/v1beta'` | URL base de la API del proveedor. |
| `GEMINI_DOCS_URL` | `'https://developers.google.com/ai'` | Enlace a la documentación del proveedor que se muestra en la interfaz. |
| `DEEPSEEK_API_URL` | `'https://api.deepseek.com/v1'` | URL base de la API del proveedor. |
| `DEEPSEEK_DOCS_URL` | `'https://docs.deepseek.ai'` | Enlace a la documentación del proveedor que se muestra en la interfaz. |
| `GROQ_API_URL` | `'https://api.groq.com/openai/v1'` | URL base de la API del proveedor. |
| `GROQ_DOCS_URL` | `'https://docs.groq.com'` | Enlace a la documentación del proveedor que se muestra en la interfaz. |
| `MISTRAL_API_URL` | `'https://api.mistral.ai/v1'` | URL base de la API del proveedor. |
| `MISTRAL_DOCS_URL` | `'https://docs.mistral.ai'` | Enlace a la documentación del proveedor que se muestra en la interfaz. |
| `OLLAMA_BASE_URL` | `'http://localhost:11434'` | URL base de la API del proveedor. |
| `OLLAMA_DOCS_URL` | `'https://ollama.com/docs'` | Enlace a la documentación del proveedor que se muestra en la interfaz. |
| `AZURE_OPENAI_API_URL` | `''` | URL base de la API del proveedor. |
| `AZURE_OPENAI_DOCS_URL` | `'https://oai.azure.com'` | Enlace a la documentación del proveedor que se muestra en la interfaz. |
| `CONTECFLOW_AI_MODEL` | `'claude-haiku-4-5'` | Id del modelo de Anthropic por defecto. |
| `SEMANTIC_EMBEDDINGS_BACKEND` | `'tfidf'` | `tfidf` (por defecto) o backend transformer (necesita requirements-ml.txt). |
| `SEMANTIC_RETRAIN_INTERVAL_HOURS` | `24` | Asignación por IA — cada cuántas horas se reconstruyen los perfiles de cada empresa (texto desde su historial + embeddings). La tarea `app.worker.semantic_reentrenar` corre cada hora (:23) y actúa cuando la hora UTC es múltiplo del intervalo (24 → 00:23 UTC; 168 → semanal); 0: nunca (23-11-2026). |
| `OPENAI_API_KEY` | `''` | Clave de OpenAI (STT y alternativa). |
| `OPENAI_STT_MODEL` | `'gpt-4o-mini-transcribe'` | Modelo de transcripción de OpenAI. |
| `AI_COST_ALERT_USD_PER_DAY` | `10.0` | Umbral de alerta del gasto diario en IA. |

**SLA (`config_groups/sla_config.py`) — 20 variables**

| Nombre | Defecto | Significado |
|---|---|---|
| `SLA_P1_RESPONSE_HOURS` | `1.0` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_P1_RESOLUTION_HOURS` | `4.0` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_P2_RESPONSE_HOURS` | `4.0` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_P2_RESOLUTION_HOURS` | `8.0` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_P3_RESPONSE_HOURS` | `8.0` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_P3_RESOLUTION_HOURS` | `24.0` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_P4_RESPONSE_HOURS` | `24.0` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_P4_RESOLUTION_HOURS` | `72.0` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_BUSINESS_HOURS_ONLY` | `True` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_BUSINESS_START_HOUR` | `8` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_BUSINESS_END_HOUR` | `18` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_BUSINESS_DAYS` | `'1,2,3,4,5'` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_PREDICTION_HOURS_CRITICAL` | `4` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_PREDICTION_HOURS_HIGH` | `8` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_PREDICTION_HOURS_MEDIUM` | `24` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_PREDICTION_HOURS_LOW` | `72` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_PREDICTION_WARNING_PCT` | `0.7` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_PREDICTION_SEVERITY_CRITICAL_H` | `1.0` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_PREDICTION_SEVERITY_HIGH_H` | `4.0` | Objetivos de SLA / horario laboral / predicción de incumplimiento (horas, %). |
| `SLA_AT_RISK_WINDOW_HOURS` | `2.0` | Ventana de riesgo del wallboard y del panel de SLA (horas); clave en vivo `sla`. |

**Puntuaciones de salud (`config_groups/health_config.py`) — 25 variables**

| Nombre | Defecto | Significado |
|---|---|---|
| `HEALTH_NPS_LOOKBACK_DAYS` | `90` | Pesos y umbrales de la puntuación de salud del cliente. |
| `HEALTH_TICKET_LOOKBACK_DAYS` | `30` | Pesos y umbrales de la puntuación de salud del cliente. |
| `HEALTH_DEFAULT_NO_DATA` | `70.0` | Pesos y umbrales de la puntuación de salud del cliente. |
| `HEALTH_PORTAL_BASE_SCORE` | `30.0` | Pesos y umbrales de la puntuación de salud del cliente. |
| `HEALTH_PORTAL_SCORE_PER_SESSION` | `7.0` | Pesos y umbrales de la puntuación de salud del cliente. |
| `HEALTH_WEIGHT_NPS` | `0.4` | Pesos y umbrales de la puntuación de salud del cliente. |
| `HEALTH_WEIGHT_DELIVERY` | `0.2` | Pesos y umbrales de la puntuación de salud del cliente. |
| `HEALTH_WEIGHT_BUDGET` | `0.15` | Pesos y umbrales de la puntuación de salud del cliente. |
| `HEALTH_WEIGHT_TICKETS` | `0.15` | Pesos y umbrales de la puntuación de salud del cliente. |
| `HEALTH_WEIGHT_PORTAL` | `0.1` | Pesos y umbrales de la puntuación de salud del cliente. |
| `HEALTH_THRESHOLD_EXCELLENT` | `80.0` | Pesos y umbrales de la puntuación de salud del cliente. |
| `HEALTH_THRESHOLD_GOOD` | `60.0` | Pesos y umbrales de la puntuación de salud del cliente. |
| `HEALTH_THRESHOLD_AT_RISK` | `40.0` | Pesos y umbrales de la puntuación de salud del cliente. |
| `PROJECT_HEALTH_WEIGHT_SCHEDULE` | `0.3` | Pesos y umbrales de la puntuación de salud del proyecto. |
| `PROJECT_HEALTH_WEIGHT_BUDGET` | `0.25` | Pesos y umbrales de la puntuación de salud del proyecto. |
| `PROJECT_HEALTH_WEIGHT_QUALITY` | `0.2` | Pesos y umbrales de la puntuación de salud del proyecto. |
| `PROJECT_HEALTH_WEIGHT_VELOCITY` | `0.15` | Pesos y umbrales de la puntuación de salud del proyecto. |
| `PROJECT_HEALTH_WEIGHT_CLIENT` | `0.1` | Pesos y umbrales de la puntuación de salud del proyecto. |
| `PROJECT_HEALTH_TRAFFIC_GREEN` | `70.0` | Pesos y umbrales de la puntuación de salud del proyecto. |
| `PROJECT_HEALTH_TRAFFIC_YELLOW` | `45.0` | Pesos y umbrales de la puntuación de salud del proyecto. |
| `PROJECT_HEALTH_BUDGET_RATIO_GOOD` | `0.8` | Pesos y umbrales de la puntuación de salud del proyecto. |
| `PROJECT_HEALTH_BUDGET_RATIO_OK` | `1.0` | Pesos y umbrales de la puntuación de salud del proyecto. |
| `PROJECT_HEALTH_BUDGET_RATIO_WARN` | `1.2` | Pesos y umbrales de la puntuación de salud del proyecto. |
| `EVM_INDEX_GREEN_MIN` | `0.9` | Semáforo EVM: CPI/SPI en verde desde este valor (TCPI por su inverso). |
| `EVM_INDEX_RED_BELOW` | `0.85` | Semáforo EVM: CPI/SPI en rojo por debajo de este valor (TCPI por su inverso). |
| `PLANNING_WORKDAYS` | `'1,2,3,4,5'` | Planificador de proyectos, nivelación, curva S y cartera (rev. 173): planificador — días laborables de la empresa (ISO, CSV); los festivos vienen de Configuración › Festivos. |
| `PLANNING_CRITICAL_FLOAT_DAYS` | `0.0` | Planificador de proyectos, nivelación, curva S y cartera (rev. 173): planificador — una tarea es crítica con una holgura total de hasta (días laborables). |
| `PLANNING_NEAR_CRITICAL_FLOAT_DAYS` | `3.0` | Planificador de proyectos, nivelación, curva S y cartera (rev. 173): planificador — casi crítica con una holgura total de hasta (días laborables). |
| `PLANNING_AUTO_RECALCULATE` | `True` | Planificador de proyectos, nivelación, curva S y cartera (rev. 173): planificador — recalcula la ruta crítica cuando cambian fechas, dependencias o estimaciones. |
| `LEVELING_OVERALLOCATION_PCT` | `100.0` | Planificador de proyectos, nivelación, curva S y cartera (rev. 173): nivelación — sobreasignado por encima de este % de la jornada de la persona. |
| `LEVELING_HORIZON_DAYS` | `120` | Planificador de proyectos, nivelación, curva S y cartera (rev. 173): nivelación — días hacia delante que mira. |
| `RESOURCE_UNDERUSE_PCT` | `50.0` | Planificador de proyectos, nivelación, curva S y cartera (rev. 173): recursos — infrautilizado por debajo de este % de la capacidad. |
| `RESOURCE_AVAILABILITY_WEEKS` | `8` | Planificador de proyectos, nivelación, curva S y cartera (rev. 173): recursos — semanas que se muestran en la disponibilidad y las alertas. |
| `EVM_SNAPSHOTS_ENABLED` | `True` | Planificador de proyectos, nivelación, curva S y cartera (rev. 173): valor ganado — guarda un punto diario de curva S por proyecto activo. |
| `EVM_CURVE_MAX_POINTS` | `365` | Planificador de proyectos, nivelación, curva S y cartera (rev. 173): valor ganado — puntos de curva S devueltos (los más recientes). |
| `PORTFOLIO_MIN_SCORE_TO_ADVANCE` | `50.0` | Planificador de proyectos, nivelación, curva S y cartera (rev. 173): cartera — puntuación mínima de la propuesta (0-100) para pasar una puerta (gate). |

**Motor semántico (`config_groups/semantic_config.py`) — 10 variables**

| Nombre | Defecto | Significado |
|---|---|---|
| `SEM_THRESHOLD_EXPERT_CACHE` | `0.92` | Pesos y umbrales del clasificador semántico. |
| `SEM_THRESHOLD_CRITICAL` | `0.9` | Pesos y umbrales del clasificador semántico. |
| `SEM_THRESHOLD_HIGH` | `0.72` | Pesos y umbrales del clasificador semántico. |
| `SEM_THRESHOLD_MEDIUM` | `0.58` | Pesos y umbrales del clasificador semántico. |
| `SEM_THRESHOLD_LOW` | `0.45` | Pesos y umbrales del clasificador semántico. |
| `SEM_WEIGHT_PROFILE` | `0.4` | Pesos y umbrales del clasificador semántico. |
| `SEM_WEIGHT_HISTORY` | `0.6` | Pesos y umbrales del clasificador semántico. |
| `SEM_TOP_K_HISTORY` | `3` | Pesos y umbrales del clasificador semántico. |
| `SEM_MULTI_ROLE_FACTOR` | `0.7` | Pesos y umbrales del clasificador semántico. |
| `EMBEDDING_MODEL_NAME` | `'all-MiniLM-L6-v2'` | Modelo sentence-transformers del backend `transformer` cuando la configuración semántica de la organización no fija ninguno. |

**Service desk (`config_groups/service_desk_config.py`) — 33 variables**

| Nombre | Defecto | Significado |
|---|---|---|
| `SD_NOTIFY_REQUESTER_ON_CREATE` | `True` | Interruptor de correo del service desk. |
| `SD_NOTIFY_REQUESTER_ON_REPLY` | `True` | Interruptor de correo del service desk. |
| `SD_NOTIFY_REQUESTER_ON_RESOLVE` | `True` | Interruptor de correo del service desk. |
| `SD_NOTIFY_AGENTS_BY_EMAIL` | `True` | Interruptor de correo del service desk. |
| `SD_INBOUND_ADDRESS` | `''` | Dirección del buzón de soporte. |
| `SD_INBOUND_REQUIRE_SENDER_AUTH` | `True` | Un correo entrante actúa como la persona de su `From` solo si SPF/DKIM/DMARC pasaron en `Authentication-Results`; si no, comenta como remitente externo (auditoría 2026-11-22, A-SD6). En vivo (`service_desk`). |
| `SD_INBOUND_AUTHSERV_ID` | `''` | Servidor de correo (authserv-id) cuya cabecera `Authentication-Results` es de confianza; vacío: la cabecera superior. En vivo (`service_desk`). |
| `TWILIO_PHONE_NUMBERS` | `''` | Números de Twilio de una organización (E.164, CSV), definidos por organización; el valor del entorno no enruta. |
| `SD_REOPEN_ON_REPLY` | `True` | Reabre el ticket resuelto al recibir una respuesta. |
| `SD_CHANNEL_TICKET_TYPE` | `'incident'` | Tipo de ticket de los tickets creados por canal. |
| `SD_MAIL_MAX_PER_RUN` | `50` | Correos leídos en cada ejecución del buzón. |
| `SD_MAIL_MAX_ATTACHMENT_MB` | `15` | Tope de adjuntos. |
| `SD_CAB_GROUP_ID` | `''` | Grupo aprobador del CAB. |
| `SD_CAB_APPROVAL_RULE` | `'majority'` | Regla del CAB `majority`/… |
| `SD_CHANGE_AUTO_APPROVE_MAX_RISK` | `30` | Aprueba automáticamente los cambios con riesgo igual o inferior a este. |
| `SD_STANDARD_CHANGE_MAX_FAILURE_PCT` | `20` | Suspende un modelo de cambio estándar por encima de esta tasa de fallos (%). |
| `SD_STANDARD_CHANGE_MIN_CLOSURES` | `5` | Cierres necesarios para que cuente la tasa de fallos de un modelo estándar. |
| `SD_STANDARD_CHANGE_REVIEW_DAYS` | `365` | Días que un modelo de cambio estándar permanece aprobado (revisión periódica). |
| `SD_EVENT_SEVERITY_MAP` | `JSON map (see code)` | Mapa JSON severidad de monitorización → prioridad. |
| `SD_EVENT_AUTO_RESOLVE` | `True` | Resuelve automáticamente al recibir el evento de recuperación. |
| `SD_ONCALL_PRIORITIES` | `'p1_critical,p2_high'` | Prioridades que avisan a la guardia. |
| `SD_ONCALL_SMS` | `True` | Envía SMS a la guardia. |
| `SD_KB_REQUIRE_REVIEW` | `False` | Los artículos de la KB necesitan revisión. |
| `SD_KB_REVIEWER_GROUP_ID` | `''` | Grupo revisor de la KB. |
| `SD_KB_RAG_MIN_SCORE_VECTOR` | `0.35` | Coseno mínimo para citar un artículo de la KB. |
| `SD_KB_RAG_MIN_SCORE_WORDS` | `0.5` | Sin modelo de frases: proporción de palabras para citar un artículo. |
| `SD_KB_RAG_MAX_SOURCES` | `3` | Artículos de la KB por respuesta de IA. |
| `SD_KB_CORRECTION_MATCH` | `0.8` | Similitud para que se aplique una corrección de un experto. |
| `SD_KB_STALE_DAYS` | `180` | Días antes de que un artículo publicado se marque como obsoleto (0: desactivado). |
| `SD_KB_CONTRADICTION_SIMILARITY` | `0.75` | Similitud para que dos artículos se comparen con IA. |
| `SD_KB_CONTRADICTION_MAX_PAIRS` | `10` | Pares de artículos comparados con IA en cada ejecución diaria (0: desactivado). |
| `SD_TIME_TO_TIMESHEET` | `True` | Las horas de los tickets se imputan a las hojas de horas. |
| `SD_ASSET_REFRESH_DAYS` | `7` | Cadencia de actualización de activos. |
| `SD_AUTO_CLOSE_HOURS_AFTER_RESOLUTION` | `72` (1-720) | Autorresolución con IA: horas por defecto tras la resolución antes del cierre automático; cada empresa lo sobrescribe en su configuración de autorresolución. |
| `SD_VALIDATION_WINDOW_HOURS` | `48` (1-720) | Autorresolución con IA: ventana por defecto (h) para detectar una reapertura; sobrescribible por empresa en la misma configuración. |
| `KEDB_DEFAULT_REVIEW_DAYS` | `90` (7-365) | Errores conocidos: periodo de revisión al publicar o revisar; clave en vivo `service_desk`. |
| `SD_EVENT_MAX_ATTEMPTS` | `5` | Tope de reintentos de eventos de ticket. |
| `SD_EVENT_BATCH_SIZE` | `200` | Tamaño de lote de eventos de ticket. |


**Más ajustes** (generados a partir del código: valor por defecto de `Settings`, texto de la etiqueta del ajuste en vivo, de la descripción del campo o del comentario que lo precede):

| Variable | Defecto | Significado |
|---|---|---|
| `AUTOMATIONS_ENABLED` | `True` | Las reglas se ejecutan con los eventos y en el barrido periódico (desactivado: solo la simulación) |
| `AUTOMATIONS_MAX_CHAIN_DEPTH` | `3` | Una regla puede disparar otra hasta esta profundidad |
| `AUTOMATIONS_EVENT_BATCH_SIZE` | `200` | Eventos procesados por ejecución |
| `AUTOMATIONS_EVENT_MAX_ATTEMPTS` | `3` | Intentos por evento antes de dejarlo como fallido |
| `AUTOMATIONS_SCAN_MINUTES` | `15` | Barrido periódico de automatizaciones (tareas vencidas, presupuesto, hojas de horas sin enviar): cada cuántos minutos se ejecuta. |
| `AUTOMATIONS_DEADLINE_DAYS` | `2` | «Tarea próxima a vencer»: días antes del vencimiento |
| `AUTOMATIONS_TIMESHEET_WEEKDAY` | `5` | «Hoja de horas sin enviar»: a partir de este día de la semana (ISO, 1=lun … 7=dom) |
| `AUTOMATIONS_WEBHOOK_TIMEOUT_SECONDS` | `10` | Acción de webhook — timeout (s) |
| `NOTIFICATIONS_DIGEST_HOUR` | `8` | Resumen diario de avisos — hora local (0-23) a partir de la cual se envía por correo |
| `NOTIFICATIONS_DIGEST_MAX_ITEMS` | `20` | Resumen diario de avisos — máximo de avisos listados |
| `NOTIFICATIONS_ALERTS_TIME` | `08:00` | Motor de alertas — hora local (HH:MM) en la zona horaria de cada empresa (clave en vivo `automations`, 19-11-2026) |
| `NOTIFICATIONS_BUDGET_CAMPAIGN_TIME` | `08:30` | Recordatorio de la campaña de presupuesto — hora local (HH:MM) en la zona horaria de cada empresa |
| `NOTIFICATIONS_MISSING_IMPUTATIONS_TIME` | `18:00` | Recordatorio de imputaciones de horas pendientes — hora local (HH:MM); solo a las personas cuyo horario efectivo tiene trabajo ese día |
| `NOTIFICATIONS_PERF_REMINDERS_TIME` | `09:00` | Recordatorios de evaluaciones de desempeño — hora local (HH:MM) en la zona horaria de cada empresa (19-11-2026; antes 09:00 del worker) |
| `UMBRAL_PRESUPUESTO_AVISO_PCT` | `70.0` | Presupuesto consumido — aviso por encima de este %. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_PRESUPUESTO_CRITICO_PCT` | `90.0` | Presupuesto consumido — crítico por encima de este %. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_CARGA_AVISO_PCT` | `85.0` | Carga de recursos — alta por encima de este % de la capacidad. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_CARGA_CRITICO_PCT` | `100.0` | Carga de recursos — sobrecargado por encima de este % de la capacidad. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_SOBRECARGA_HORAS_SEMANA` | `42.0` | Burnout — una semana con más horas que esta cuenta como semana sobrecargada. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_SLA_AVISO_PCT` | `90.0` | Cumplimiento de SLA — aviso por debajo de este %. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_SLA_CRITICO_PCT` | `75.0` | Cumplimiento de SLA — crítico por debajo de este %. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_OKR_AVISO_PCT` | `60.0` | Progreso de OKR — aviso por debajo de este %. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_OKR_CRITICO_PCT` | `30.0` | Progreso de OKR — crítico por debajo de este %. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_NPS_AVISO` | `50.0` | NPS — aviso por debajo de este valor (-100..100). Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_NPS_CRITICO` | `0.0` | NPS — crítico por debajo de este valor (-100..100). Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_MARGEN_AVISO_PCT` | `50.0` | Margen — aviso por debajo de este %. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_MARGEN_CRITICO_PCT` | `30.0` | Margen — crítico por debajo de este %. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_SPRINT_COMPLETITUD_AVISO_PCT` | `80.0` | Finalización del sprint — aviso por debajo de este %. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_SPRINT_COMPLETITUD_CRITICO_PCT` | `50.0` | Finalización del sprint — crítico por debajo de este %. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_SPRINT_VELOCIDAD_AVISO_PCT` | `85.0` | Ratio de velocidad del sprint — aviso por debajo de este %. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_SPRINT_VELOCIDAD_CRITICO_PCT` | `50.0` | Ratio de velocidad del sprint — crítico por debajo de este %. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_APROBACION_RIESGO_SLA_AVISO_PCT` | `50.0` | Aprobaciones — aviso de riesgo de SLA del paso desde este %. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_APROBACION_RIESGO_SLA_CRITICO_PCT` | `80.0` | Aprobaciones — riesgo de SLA del paso crítico desde este %. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_APROBACION_RECHAZO_AVISO_PCT` | `10.0` | Aprobaciones — aviso de tasa de rechazo desde este %. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_APROBACION_RECHAZO_CRITICO_PCT` | `25.0` | Aprobaciones — tasa de rechazo crítica desde este %. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_APROBACION_PENDIENTES_CRITICO` | `3.0` | Aprobaciones — un paso con tantas solicitudes pendientes es crítico. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_APROBACION_DECISION_HORAS` | `24.0` | Aprobaciones — un paso que tarda en decidir estas horas o más es lento. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_VENCIMIENTO_HORIZONTE_DIAS` | `90` | Vencimientos — muestra lo que vence dentro de estos días. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_VENCIMIENTO_AVISO_DIAS` | `30` | Vencimientos — aviso cuando quedan estos días o menos. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_VENCIMIENTO_CRITICO_DIAS` | `14` | Vencimientos — crítico cuando quedan estos días o menos. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_HITOS_HORIZONTE_DIAS` | `60` | Portal de clientes — próximos hitos dentro de estos días. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `UMBRAL_HITOS_INMINENTE_DIAS` | `7` | Portal de clientes — un hito a menos de estos días es inminente. Umbral por métrica (19-11-2026, `app/core/umbrales.py`). En vivo (`semaforos`). |
| `BPMN_MAX_AUTOMATIC_STEPS` | `500` | BPM — pasos automáticos seguidos antes de que una instancia falle (protección contra bucles) |
| `BPMN_MAX_XML_BYTES` | `2000000` | BPM — tamaño máximo del XML de un diagrama (mayor: 413) |
| `BPMN_MAX_VARIABLES_BYTES` | `65536` | BPM — tamaño máximo de las variables de una instancia en JSON (mayor: 413) |
| `SMTP_TLS_VERIFY` | `True` | Verifica el certificado y el nombre del servidor SMTP (SMTP_SSL en 465 y STARTTLS). Apagarlo solo para un relé interno con certificado autofirmado: sin verificación, un intermediario puede leer el correo y la contraseña (`config_groups/seguridad_salida_config.py`). |
| `BPMN_SERVICE_RETRIES` | `3` | BPM — reintentos de una acción automática antes de abrir un incidente (0-20; docs/BPM.md). Sobrescribible en vivo por empresa. |
| `BPMN_STUCK_HOURS` | `72` | BPM — horas que un paso pendiente espera antes de contar su instancia como atascada (métricas de `/bpm`). Sobrescribible en vivo por empresa. |
| `BPMN_SEGREGACION_DE_FUNCIONES` | `False` | BPM — segregación de funciones: quien diseña o publica una versión no aprueba en sus instancias. Apagado de serie; por empresa en vivo. |
| `BI_TOKEN_DAILY_REQUEST_LIMIT` | `10000` | Tokens BI — peticiones al día por token (0 = sin límite). |
| `BI_BOOKMARK_SHARE_DAYS` | `30` | Marcadores BI — días que vale un enlace compartido (0 = sin caducidad). |
| `RECURRING_TASKS_MAX_CATCHUP` | `10` | Tareas recurrentes — máximo de ocurrencias atrasadas que se crean al ponerse al día. |
| `COLLAB_TUS_TTL_HOURS` | `24` | Subidas del chat — horas antes de purgar una subida reanudable sin terminar. |
| `DOC_COLLAB_HISTORY_MAX` | `200` | Documentos coeditados — instantáneas que se guardan en el historial (0 = sin límite). |
| `AI_CONTRACT_MAX_PAGES` | `200` | Análisis de contratos con IA — máximo de páginas del PDF que se leen (0 = sin límite). |
| `QB_MINOR_VERSION` | `65` | QuickBooks — versión menor de la API cuando la integración no fija una. |
| `BI_DELIVERY_ALLOWED_DOMAINS` | `''` | Informes BI programados — dominios de correo externos admitidos como destinatarios (CSV; vacío = solo personas de la empresa). |
| `BI_DELIVERY_MAX_ROWS` | `5000` | Informes BI programados — filas por informe entregado. |
| `OVERTIME_LEGAL_ANNUAL_CAP_HOURS` | `80.0` | Horas extra — tope legal anual por persona (80 h, art. 35.2 del Estatuto de los Trabajadores; 0 = sin tope). |
| `SD_AUTONOMOUS_AGENT_ENABLED` | `False` | Agente autónomo — revisa los tickets nuevos cada 5 min (comenta y puede resolver) |
| `SD_AUTONOMY_RESOLVE_THRESHOLD` | `0.8` | Agente autónomo — confianza para resolver por sí solo (0-1) |
| `SD_AUTONOMY_SUGGEST_THRESHOLD` | `0.5` | Agente autónomo — confianza para comentar un playbook (0-1) |
| `SD_AUTONOMOUS_AGENT_MODE` | `suggest` | Agente autónomo — modo: suggest (un agente aplica la propuesta) o execute |
| `SD_AUTONOMOUS_DISABLED_PLAYBOOKS` | — | Agente autónomo — playbooks integrados desactivados para la empresa (CSV de ids) |
| `SD_QUEUE_SLA_RISK_WEIGHT` | `0.65` | Cola de riesgo — peso del riesgo de SLA frente al valor de negocio (0-1) |
| `SD_DUPLICATE_WINDOW_DAYS` | `14` | Duplicados — días hacia atrás desde el ticket para buscar similares (0: sin límite) |
| `SD_DUPLICATE_MIN_SIMILARITY` | `0.35` | Duplicados — similitud mínima (0-1) para proponer un ticket |
| `SD_DUPLICATE_MAX_CANDIDATES` | `5` | Duplicados — máximo de candidatos mostrados (0: todos) |
| `SD_PRESENCE_TTL_SECONDS` | `45` | Aviso de colisión — segundos sin latido tras los cuales un visor se da de baja |
| `SD_PORTAL_ASSISTANT_ACTION_TTL_MINUTES` | `15` | Asistente del portal — minutos durante los que se puede confirmar una acción propuesta |
| `SD_PORTAL_ASSISTANT_MIN_MATCH` | `0.2` | Asistente del portal — similitud mínima (0-1) para proponer un servicio del catálogo |
| `SD_PASSWORD_RESET_SERVICE_ID` | — | Asistente del portal — servicio del catálogo que restablece contraseñas (vacío: no se ofrece) |
| `SD_PORTAL_ASSISTANT_AI` | `true` | Asistente del portal — entender con la IA (ruta 'portal_assistant' en el AI Hub); desactivado: coincidencia por palabras clave |
| `SD_PORTAL_ASSISTANT_MAX_TOKENS` | `700` | Asistente del portal — máximo de tokens por respuesta de IA |
| `SD_SLACK_TICKET_CHANNEL` | — | Slack — id del canal donde se publica la tarjeta de cada ticket nuevo (su hilo queda vinculado al ticket; vacío: desactivado) |
| `SD_SLACK_INTAKE_CHANNELS` | — | Slack — ids de los canales de entrada (CSV): cada mensaje de primer nivel abre un ticket vinculado a su hilo |
| `SD_CHANNEL_MAX_ATTACHMENT_MB` | `16` | Canales — tamaño máximo de adjunto recibido o enviado por WhatsApp/Slack (MB) |
| `AI_LOCAL_HTTP_TIMEOUT_SECONDS` | `120` | Llamada a Ollama (modelo local) — timeout (s) |
| `AI_PROVIDER_ERROR_COOLDOWN_SECONDS` | `300` | Un proveedor que falla se aparta durante (s) y luego se reintenta |
| `MCP_WRITE_MODE` | `'off'` | MCP — herramientas que escriben: off (ocultas), approval (una persona aprueba cada llamada) o direct |
| `MCP_RATE_LIMIT_PER_MINUTE` | `60` | MCP — llamadas por minuto de cada credencial (o sesión); por encima, 429 con Retry-After (0: sin límite propio) |
| `MCP_NOTEBOOK_ENABLED` | `False` | MCP — herramientas de «Mi cuaderno» para agentes de programación (cada persona sigue eligiendo qué cuadernos comparte) |
| `AI_DAILY_BUDGET_USD` | `0.0` | IA — tope de gasto diario por empresa en USD; las llamadas se detienen hasta las 00:00 UTC (0: sin tope) |
| `AI_DAILY_BUDGET_WARN_PCT` | `80.0` | IA — % del tope diario desde el que avisa el AI Hub |
| `ASK_DATA_HINT_MAX_VALUES` | `10` | Ask the Data — valores reales mostrados cuando un filtro no encuentra nada |
| `ASK_DATA_HINT_MIN_SIMILARITY` | `0.5` | Ask the Data — similitud mínima (0-1) para que un valor real cuente como cercano |
| `ASK_DATA_RETRY_WITH_REAL_VALUES` | `True` | Ask the Data — con cero filas y un valor real cercano, vuelve a preguntar al modelo una vez con los valores reales |
| `ASK_DATA_REUSE_EXACT_EXAMPLE` | `True` | Ask the Data — la misma pregunta que una validada reutiliza su consulta sin llamar al modelo |
| `ASK_DATA_EXAMPLES_IN_PROMPT` | `3` | Ask the Data — ejemplos validados que se dan al modelo (0: ninguno) |
| `ASK_DATA_EXAMPLE_MIN_SIMILARITY` | `0.3` | Ask the Data — solapamiento mínimo de palabras (0-1) para dar un ejemplo validado |
| `ASK_DATA_CONTEXT_TURNS` | `4` | Ask the Data — preguntas anteriores de la misma conversación (con su consulta) que se dan al modelo para entender las de seguimiento («¿y en octubre?»); 0: sin memoria. Las conversaciones se guardan por persona y empresa (sin filas de resultado), se borran desde el widget, por retención (`ask_data_conversations`) y con la supresión RGPD (23-11-2026). |
| `AI_TEST_MAX_TOKENS` | `256` | Tope de tokens de la llamada «Probar» del proveedor; los modelos de razonamiento (Gemini 2.5, serie o) gastaban un tope de 10 tokens en pensar y no devolvían nada. |
| `AI_SHORT_ANSWER_MAX_TOKENS` | `256` | Tope de tokens de las llamadas de IA de respuesta corta (clasificar, elegir un id); los modelos de razonamiento necesitan margen para pensar antes de responder. |
| `AI_BRIEF_ANSWER_MAX_TOKENS` | `500` | Tope de tokens de las respuestas breves de IA (un JSON, una clasificación con motivo) (19-11-2026). |
| `AI_MEDIUM_ANSWER_MAX_TOKENS` | `800` | Tope de tokens de las respuestas medias de IA (resumen, narrativa). |
| `AI_LONG_ANSWER_MAX_TOKENS` | `1500` | Tope de tokens de las respuestas largas de IA (artículo, respuesta del asistente); valor por defecto de `call_ai_unified`. |
| `AI_CHAT_MAX_TOKENS` | `4000` | Tope de tokens de los turnos de chat con herramientas (NexusAssist, agente en segundo plano). |
| `AI_PROVIDER_DEFAULT_MAX_TOKENS` | `2000` | max_tokens de un proveedor configurado solo por .env. |
| `AI_DEFAULT_TEMPERATURE` | `0.7` | Temperatura de un proveedor configurado solo por .env. |
| `AI_AGENT_TURN_TIMEOUT_SECONDS` | `90` | NexusAgent — timeout por turno del modelo (s) |
| `AI_MODELS_LIST_TIMEOUT_SECONDS` | `30` | IA «Sincronizar modelos» — timeout (s) |
| `DEVELOPER_TOKEN_TTL_MINUTES` | `60` | TTL del token de aplicación del portal de desarrolladores (minutos) |
| `DATABASE_MIGRATIONS_URL` | `''` | Conexión del propietario para las migraciones y la configuración de RLS cuando `DATABASE_URL` usa el rol de aplicación sin privilegios (vacío: `DATABASE_URL`). |
| `TENANT_ENTRY_MODE` | `'email_selector'` | Cómo entran los usuarios en su empresa: `email_selector` (elegir tras la contraseña) o `subdomain`. Un modo por despliegue. |
| `TENANT_ROOT_DOMAIN` | `''` | Modo subdominio: se accede a las empresas en `<slug>.TENANT_ROOT_DOMAIN` (además del dominio propio de cada empresa). |
| `TENANT_SELECTION_TOKEN_MINUTES` | `5` | Vida del token que solo permite elegir empresa tras la contraseña. |
| `TENANT_DELETION_QUARANTINE_DAYS` | `30` | Eliminación de empresa — cuarentena antes de borrar sus datos (días) |
| `AUDIT_EXPORT_MAX_ROWS` | `100000` | Registro de auditoría — máximo de filas de la exportación firmada (las más recientes) |
| `COMPLIANCE_STALE_ACCOUNT_DAYS` | `90` | Informe de cumplimiento — se señala una cuenta activa sin inicio de sesión durante más de estos días |
| `COMPLIANCE_GDPR_MAX_DAYS` | `30` | Plazo de las solicitudes RGPD (DSR) y comprobación del informe de cumplimiento |
| `COMPLIANCE_GDPR_EXPORT_TTL_DAYS` | `30` | Copia de acceso/portabilidad RGPD — días que se conserva (cifrada) tras completarse |
| `COMPLIANCE_MFA_MIN_COVERAGE_PCT` | `100.0` | Informe de cumplimiento — % mínimo de usuarios activos con segundo factor |
| `COMPLIANCE_MIN_PASSWORD_LENGTH` | `12` | Informe de cumplimiento — longitud mínima de contraseña que debe exigir la política |
| `RETENTION_MIN_DAYS` | `30` | Retención — ninguna política puede conservar un tipo de registro menos días que estos |
| `CHANGE_CANARY_RAMP_PCT` | `1,5,25,50,100` | Despliegue canary — % de usuarios por fase (CSV, creciente, termina en 100). En vivo (`service_desk`, 19-11-2026). |
| `CHANGE_CANARY_FIRST_MINUTES` | `30` | Despliegue canary — minutos de la primera fase. En vivo (`service_desk`). |
| `CHANGE_CANARY_STEP_MINUTES` | `45` | Despliegue canary — minutos de cada fase intermedia. En vivo (`service_desk`). |
| `CHANGE_CANARY_LAST_MINUTES` | `60` | Despliegue canary — minutos de la última fase. En vivo (`service_desk`). |
| `CHAT_RETENTION_PROPOSED_MONTHS` | `24` | Chat — meses de retención propuestos para una política nueva. En vivo (`audit`, 19-11-2026). |
| `VACATION_MAX_DAYS_ENTITLED` | `60` | Vacaciones — máximo de días asignados a una persona en un año. En vivo (`locale`, 19-11-2026). |
| `PERF_REMINDER_WINDOW_DAYS` | `7` | Evaluaciones de desempeño — recuerda cuando el ciclo cierra en N días. En vivo (`automations`, 19-11-2026). |
| `PERF_REMINDER_UNDATED_CYCLE_DAYS` | `30` | Evaluaciones de desempeño — ciclo sin fecha recordado tras N días activo. En vivo (`automations`). |
| `PERF_STALLED_CYCLE_DAYS` | `45` | Evaluaciones de desempeño — estancado tras N días activo con baja finalización. En vivo (`automations`). |
| `PERF_STALLED_COMPLETION_PCT` | `50.0` | Evaluaciones de desempeño — estancado por debajo de este % de finalización. En vivo (`automations`). |
| `APPROVAL_EMAIL_LINK_HOURS` | `72` | Aprobaciones — horas de validez del enlace de aprobar/rechazar del correo |
| `IMPERSONATION_ENABLED` | `True` | El soporte de la plataforma puede iniciar sesión como un usuario de una empresa (con motivo, auditado) |
| `IMPERSONATION_MAX_MINUTES` | `30` | Iniciar sesión como — duración máxima de la sesión (minutos) |
| `ORG_DEFAULT_MAX_USERS` | `25` | Empresa nueva: límite de usuarios por defecto; clave en vivo de la plataforma `tenants`. |
| `ORG_DEFAULT_MAX_PROJECTS` | `100` | Empresa nueva: límite de proyectos por defecto; clave en vivo de la plataforma `tenants`. |
| `SSO_HTTP_TIMEOUT_SECONDS` | `10.0` | SSO — timeout de la llamada al proveedor de identidad (segundos) |
| `SSO_CLOCK_SKEW_SECONDS` | `60` | SSO — desfase de reloj tolerado al validar el id_token (segundos) |
| `SSO_RATE_LIMIT` | `'20/minute'` | Límite de tasa de los endpoints de inicio de sesión SSO (sintaxis de slowapi). |
| `PASSKEY_PASSWORDLESS_ENABLED` | `True` | Permite iniciar sesión solo con una passkey (sin contraseña) |
| `DOCUMENT_CHECKOUT_HOURS` | `24` | Check-out de documentos — la reserva caduca por sí sola tras (h) |
| `SCENARIO_CAPACITY_ROLES` | `'pm,team_lead,employee,subcontractor'` | Escenarios — roles cuya capacidad cuenta (separados por comas) |
| `RISK_WEIGHT_SCHEDULE` | `0.4` | Puntuación de riesgo — peso del calendario (0-1) |
| `RISK_WEIGHT_BUDGET` | `0.3` | Puntuación de riesgo — peso del presupuesto (0-1) |
| `RISK_WEIGHT_SCOPE` | `0.15` | Puntuación de riesgo — peso del alcance (0-1) |
| `RISK_WEIGHT_RESOURCE` | `0.15` | Puntuación de riesgo — peso de los recursos (0-1) |
| `RISK_LEVEL_CRITICAL` | `75.0` | Puntuación de riesgo — crítico desde (0-100) |
| `RISK_LEVEL_HIGH` | `50.0` | Puntuación de riesgo — alto desde (0-100) |
| `RISK_LEVEL_MEDIUM` | `25.0` | Puntuación de riesgo — medio desde (0-100) |
| `RISK_SCHEDULE_FACTOR` | `1.5` | Calendario — puntos por cada % de retraso sobre el plan |
| `RISK_BUDGET_WARN_PCT` | `85.0` | Presupuesto — % gastado en el que empieza el riesgo |
| `RISK_BUDGET_WARN_FACTOR` | `3.0` | Presupuesto — puntos por cada % por encima del aviso |
| `RISK_BUDGET_OVER_FACTOR` | `2.0` | Presupuesto — puntos por cada % por encima del 100 % |
| `RISK_POINTS_PER_OPEN_CR` | `20.0` | Alcance — puntos por cada solicitud de cambio abierta |
| `RISK_POINTS_PER_HIGH_RISK` | `25.0` | Recursos — puntos por cada riesgo abierto de alta probabilidad |
| `RISK_DELAY_FACTOR` | `0.8` | Probabilidad de retraso — % por punto de puntuación |
| `RISK_DELAY_MAX_PCT` | `95.0` | Probabilidad de retraso — máximo (%) |
| `RISK_DELAY_PCT_PER_WEEK` | `20.0` | Retraso previsto — % de probabilidad por semana |
| `RISK_CACHE_MINUTES` | `60` | Las puntuaciones se reutilizan durante (minutos) |
| `RISK_HISTORY_POINTS` | `12` | Detalle — puntos de historial mostrados |
| `TEAMS_BOT_APP_PASSWORD` | `''` | Secreto de la aplicación del bot de Teams. Necesario para **responder** en Teams: Bot Framework ignora el cuerpo de la respuesta HTTP de un mensaje, así que las respuestas se publican en el `serviceUrl` de la conversación con un token de aplicación. |
| `TEAMS_BOT_TOKEN_URL` | `'https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token'` | De dónde obtiene el bot su token de aplicación (credenciales de cliente). Configurable para nubes soberanas. |
| `TEAMS_BOT_TOKEN_SCOPE` | `'https://api.botframework.com/.default'` | Ámbito (scope) de ese token. |
| `TEAMS_BOT_ALLOWED_SERVICE_HOSTS` | `'smba.trafficmanager.net,*.botframework.com,*.botframework.azure.us'` | Hosts a los que puede responder el bot (CSV, comodines `*`). El `serviceUrl` también debe coincidir con el del token firmado. |
| `TEAMS_KB_ANSWERS_ENABLED` | `True` | Bot de Teams — un mensaje que no es un comando se responde desde la base de conocimiento |
| `CONECTOR_TIMEOUT_SECONDS` | `15.0` | Conectores — timeout de una llamada a contecmind o contecintelligence (s) |
| `CONECTOR_TOKEN_TTL_SECONDS` | `300` | Conectores — vida solicitada del token delegado de un usuario (s) |
| `CONECTOR_LOG_RETENTION_DAYS` | `30` | Conectores — días que se conserva el registro de llamadas |
| `CONECTOR_STATUS_WINDOW_HOURS` | `24` | Conectores — horas que resume el panel de estado |
| `CONTECMIND_WRITER_ROLES` | `'admin,pm,team_lead'` | contecmind — roles que pueden subir documentos y solicitar aprobaciones (CSV) |
| `CONTECMIND_SUGGEST_LIMIT` | `5` | contecmind — documentos sugeridos en un ticket |
| `CONTECMIND_UPLOAD_MAX_MB` | `50` | contecmind — tamaño máximo de subida (MB) |
| `CONTECMIND_ROOT_FOLDER` | `'contecflow'` | contecmind — carpeta raíz de las carpetas de los registros |
| `CONTECINTELLIGENCE_ANALYST_ROLES` | `'admin,pm'` | contecintelligence — roles que entran como analista (CSV) |
| `CONTECINTELLIGENCE_ASK_TIMEOUT_SECONDS` | `120.0` | contecintelligence — timeout de una pregunta (s) |
| `CONTECINTELLIGENCE_HANDOFF_ENABLED` | `True` | contecintelligence — Ask the Data ofrece pasar una pregunta |
| `CONTECINTELLIGENCE_EMBED_ORIGINS` | `''` | contecintelligence — orígenes (CSV, `https://host[:puerto]`) a los que la pantalla puede llamar directamente con un token acotado (métricas incrustadas en el panel BI). Solo estos se añaden al `connect-src` de la CSP (`app/main.py`; en desarrollo, `vite.config.js` lee la misma variable; con el nginx del frontend hay que añadirlos a mano en `nginx.frontend.conf`). Vacío: sin incrustación (23-11-2026). |
| `LIST_MAX_ROWS` | `5000` | **Tope de filas de un listado de la API (`app/core/paginacion.py`): `limit` máximo aceptado y tope aplicado cuando no se envía `limit`; si se alcanza sin `limit`, se marca `X-Truncated: true` / `meta.has_more` y se registra un aviso.** |
| `BI_ETL_PAGE_SIZE` | `100` | Conectores ETL de BI — registros pedidos por petición |
| `BI_ETL_HTTP_TIMEOUT_S` | `20.0` | Conectores ETL de BI — timeout de una petición a la fuente (s) |
| `BI_ETL_LOG_MAX_ENTRIES` | `100` | Conectores ETL de BI — entradas del registro de sincronización conservadas por conector |
| `BI_EXPLORER_MAX_ROWS` | `100000` | Data Explorer — filas leídas para agrupar y totalizar |
| `REPORT_EXPORT_MAX_ROWS` | `100000` | Generador de informes — filas de una exportación CSV |
| `PERIODO_MAX_DIAS` | `1830` | Informes — periodo más largo que se puede solicitar (días) (`app/core/periodo.py`) |
| `PERIODO_MAX_PUNTOS_HORA` | `744` | Informes — máximo de puntos de una serie horaria (`app/core/periodo.py`) |
| `PERIODO_MAX_PUNTOS_DIA` | `1100` | Informes — máximo de puntos de una serie diaria (`app/core/periodo.py`) |
| `PERIODO_MAX_PUNTOS_SEMANA` | `530` | Informes — máximo de puntos de una serie semanal (`app/core/periodo.py`) |
| `PERIODO_MAX_PUNTOS_MES` | `240` | Informes — máximo de puntos de una serie mensual (`app/core/periodo.py`) |
| `PERIODO_AUTO_MAX_PUNTOS` | `120` | Informes — granularidad automática: la más fina que se mantenga dentro de estos puntos (`app/core/periodo.py`) |
| `LESSONS_CATEGORIES` | `'alcance,planificacion,estimacion,tecnica,calidad,comunicacion,cliente,proveedor,equipo,seguridad,operacion,coste'` | Lecciones — categorías (CSV) |
| `LESSONS_VALIDATOR_ROLES` | `'admin,pm,team_lead'` | Lecciones — roles que validan o archivan una lección (CSV) |
| `LESSONS_ONLY_VALIDATED` | `True` | Lecciones — solo se recomiendan las lecciones validadas |
| `LESSONS_AI_DRAFT_ENABLED` | `True` | Lecciones — la IA redacta la lección a partir de los hechos medidos de su origen |
| `LESSONS_AI_MAX_TOKENS` | `4000` | Lecciones — límite de tokens del borrador de la IA (los modelos de razonamiento gastan parte pensando) |
| `LESSONS_RECOMMENDATIONS_MAX` | `5` | Lecciones — máximo de recomendaciones mostradas |
| `LESSONS_RECOMMENDATIONS_MIN_SCORE` | `0.2` | Lecciones — similitud mínima (0-1) para recomendar una lección |
| `LESSONS_WEIGHT_CLIENT` | `0.3` | Lecciones — peso de «mismo cliente» |
| `LESSONS_WEIGHT_PROJECT_TYPE` | `0.15` | Lecciones — peso de «mismo tipo de proyecto» |
| `LESSONS_WEIGHT_TAGS` | `0.2` | Lecciones — peso de las etiquetas compartidas (por solapamiento) |
| `LESSONS_WEIGHT_CATEGORY` | `0.15` | Lecciones — peso de «mismo servicio del catálogo o CI» (tickets) |
| `LESSONS_WEIGHT_TEXT` | `0.2` | Lecciones — peso de la similitud de texto |
| `LESSONS_PENDING_LOOKBACK_DAYS` | `180` | Lecciones — los proyectos cerrados, problemas, incidentes y sprints de los últimos N días cuentan como pendientes |
| `EXPENSE_MILEAGE_RATE` | `0.26` | Gastos — tarifa de kilometraje por km (el importe de un gasto de kilometraje = km × tarifa) |
| `EXPENSE_ATTACHMENT_MAX_MB` | `10` | Gastos — tamaño máximo de un justificante o documento (MB) |
| `EXPENSE_MANAGER_ROLES` | `'admin,pm'` | Gastos — roles que ven y gestionan los gastos de todos y sus justificantes (CSV) |
| `POLICY_SIMULATION_DEFAULT_LAST_N` | `100` | Políticas — el simulador reproduce las últimas N entidades del dominio salvo que se indique un rango de fechas |
| `POLICY_SIMULATION_MAX_ENTITIES` | `1000` | Políticas — máximo de entidades que reproduce una simulación |
| `POLICY_DOCUMENT_TYPES` | `'receipt,invoice,ticket,attendees,other'` | Políticas — tipos de documento que puede pedir un resultado «exigir adjunto» (CSV) |
| `TRANSLATION_ENABLED` | `True` | Traducción — activada para la empresa: los mensajes de clientes se muestran en el idioma de cada operador y las respuestas salen en el del cliente (desactivada: no se envía nada a un traductor) |
| `TRANSLATION_PROVIDER` | `'ai'` | Traducción — proveedor: ai (el proveedor de IA de la empresa), deepl o azure (credenciales de la empresa) |
| `TRANSLATION_CHANNELS` | `'ticket,email,livechat,whatsapp,slack,teams,portal_assistant,internal_chat,kb,editor'` | Traducción — canales en los que se aplica (CSV): ticket, email, livechat, whatsapp, slack, teams, portal_assistant, internal_chat, kb, editor |
| `TRANSLATION_OUTBOUND_AUTO` | `True` | Traducción — una respuesta pública enviada sin vista previa (Slack, API) sale traducida al idioma del cliente |
| `TRANSLATION_INCLUDE_ORIGINAL` | `False` | Traducción — el cliente recibe también el texto original del operador debajo de la traducción |
| `TRANSLATION_DETECT_MIN_CONFIDENCE` | `0.6` | Traducción — la detección local de idioma decide a partir de esta confianza (0-1); por debajo, detecta el proveedor |
| `TRANSLATION_MAX_BATCH_CHARS` | `12000` | Traducción — caracteres enviados al proveedor por llamada (los lotes más largos se dividen) |
| `TRANSLATION_AI_MAX_TOKENS` | `8192` | Traducción — proveedor de IA: máximo de tokens de la respuesta por llamada |
| `TRANSLATION_COST_PER_MILLION_CHARS_USD` | `0.0` | Traducción — precio de DeepL/Azure por millón de caracteres (USD); cuenta para el tope diario de IA (0: no cuenta) |
| `TRANSLATION_CACHE_RETENTION_DAYS` | `180` | Traducción — las traducciones en caché sin usar durante más de N días se eliminan (0: nunca) |
| `TRANSLATION_KB_LANGUAGES` | `''` | Traducción — idiomas del portal en los que se generan los artículos de conocimiento (CSV; vacío: todos los del portal) |
| `ALM_USAGE_IDLE_DAYS` | `60` | Uso de licencias — sin uso durante más de N días: «sin uso» |
| `ALM_USAGE_UNDERUSED_DAYS` | `30` | Uso de licencias — sin uso durante más de N días (y hasta el límite de «sin uso»): «infrautilizada» |
| `ALM_USAGE_MIN_ACTIVE_DAYS` | `4` | Uso de licencias — cuando la fuente da frecuencia, menos días activos que estos en su periodo: «infrautilizada» |
| `ALM_USAGE_STALE_DATA_DAYS` | `7` | Uso de licencias — la evidencia leída hace más de N días está desactualizada (se muestra, nunca se usa para recuperar) |
| `ALM_USAGE_SYNC_INTERVAL_HOURS` | `24` | Uso de licencias — la sincronización programada lee cada fuente activa cada N horas |
| `ALM_USAGE_MAX_PAGES` | `200` | Uso de licencias — máximo de páginas que lee un conector por llamada (protege contra paginación descontrolada) |
| `ALM_USAGE_REPORT_PERIOD_DAYS` | `30` | Uso de licencias — periodo de los informes de uso y registros leídos (Microsoft 365 acepta 7, 30, 90 o 180) |
| `ALM_USAGE_INTUNE_MAX_APPS` | `500` | Uso de licencias — Intune: aplicaciones detectadas cuyos dispositivos se leen por sincronización |
| `ALM_USAGE_SYNC_LOG_RETENTION_DAYS` | `180` | Uso de licencias — los registros de sincronización de más de N días se eliminan |
| `ALM_USAGE_CREATE_ASSETS` | `True` | Uso de licencias — un dispositivo inventariado que aún no es un activo se crea como activo |
| `ALM_RECLAIM_GRACE_DAYS` | `30` | Recuperación — una asignación de menos de N días nunca se recupera |
| `ALM_RECLAIM_KEEP_DAYS` | `90` | Recuperación — cuando el titular dice que aún la necesita, se le deja en paz durante N días |
| `ALM_RIGHTSIZING_WINDOW_DAYS` | `90` | Dimensionamiento — un servicio cuenta como usado si se usó en los últimos N días |
| `ALM_UNMANAGED_LOOKBACK_DAYS` | `365` | Software no gestionado — se analizan los gastos de software de los últimos N días |
| `ALM_UNMANAGED_MIN_OCCURRENCES` | `2` | Software no gestionado — apariciones necesarias para proponerlo (gastos, usuarios o dispositivos) |
| `GOOGLE_ADMIN_API_BASE` | `'https://admin.googleapis.com'` | Uso de licencias — URL base de Google Admin SDK (Directory y Reports) |
| `GOOGLE_LICENSING_API_BASE` | `'https://licensing.googleapis.com'` | Uso de licencias — URL base de Google Enterprise License Manager |
| `BUDGET_LINE_TYPES` | `'personal,licencias,subcontratacion,material,viajes,otros'` | Presupuestos — tipos de línea (CSV); «personal» se valora a partir de las imputaciones de horas |
| `BUDGET_EXPENSE_TYPE_MAP` | `'travel:viajes,accommodation:viajes,meals:viajes,software:licencias,hardware:material,training:otros,subcontract:subcontratacion,other:otros'` | Presupuestos — en qué tipo de línea cuenta cada categoría de gasto (categoría:tipo, CSV) |
| `BUDGET_APPROVER_ROLES` | `'admin'` | Presupuestos — roles que aprueban o rechazan cuando no se aplica ningún flujo de aprobación (CSV) |
| `BUDGET_MANAGER_ROLES` | `'admin,pm,hr'` | Presupuestos — roles que crean y editan presupuestos (CSV) |
| `BUDGET_REVENUE_TYPES` | `'horas,hitos,cuotas,otros_ingresos'` | Presupuestos — tipos de línea de ingresos (CSV) |
| `BUDGET_CEILING_POLICY` | `'avisar'` | Presupuestos — avisar o bloquear cuando los presupuestos hijos superan el techo del padre |
| `BUDGET_JUSTIFICATION_MIN_AMOUNT` | `5000.0` | Presupuestos — las líneas de este importe o más necesitan una justificación para enviarse |
| `BUDGET_CAMPAIGN_REMINDER_DAYS` | `7` | Presupuestos — días antes del cierre de una campaña para recordar a los responsables los presupuestos sin enviar |
| `BUDGET_CONTROL_POLICY` | `'avisar'` | Presupuestos — aprobar un gasto o introducir un pedido por encima del importe disponible: no, avisar o bloquear |
| `BUDGET_VARIANCE_EXPLAIN_PCT` | `15.0` | Presupuestos — una desviación mensual por tipo de este % o más necesita una explicación antes de cerrar el mes |
| `BUDGET_VARIANCE_EXPLAIN_MIN_AMOUNT` | `1000.0` | Presupuestos — …y de este importe o más (deben cumplirse ambas) |
| `BUDGET_ALM_LINE_TYPE` | `'licencias'` | Presupuestos — tipo de línea donde los contratos y licencias de ALM cuentan como comprometidos |
| `INTERNAL_IT_ERP_ACCOUNT` | `''` | Clientes internos (rev. 193): cuenta del ERP de TI o centro de coste que se abona en los asientos de cargo interno. En vivo (`presupuestos`); se edita en Configuración → Finanzas → Clientes internos. |
| `ALM_HANDOVER_ACT_ENABLED` | `True` | Licencias y hardware — emite un acta de entrega y devolución (firmada) cuando un activo cambia de manos |
| `ALM_HANDOVER_CHECKLIST` | `'charger,case,peripherals,no_visible_damage,data_wiped,accounts_removed'` | Licencias y hardware — elementos de la lista de comprobación de entrega/devolución (CSV de códigos) |
| `ALM_ACT_ESIGN_PROVIDER` | `'manual'` | Licencias y hardware — quién firma las actas: manual (en la aplicación), docusign o adobe_sign |
| `ALM_LOAN_DEFAULT_DAYS` | `14` | Licencias y hardware — duración por defecto de un préstamo (días) |
| `ALM_LOAN_REMINDER_DAYS` | `2` | Licencias y hardware — días antes del vencimiento de un préstamo en que se recuerda al titular |
| `ALM_RENEWAL_LEAD_DAYS` | `30` | Licencias y hardware — días antes del plazo de preaviso en que se anuncia una renovación |
| `ALM_LICENSE_NOTICE_DAYS` | `30` | Licencias y hardware — días de preaviso de una licencia sin contrato |
| `ALM_RENEWAL_NOTIFY_ROLES` | `'admin'` | Licencias y hardware — roles notificados de las renovaciones sin responsable (CSV) |
| `ALM_PERPETUAL_AMORTIZATION_MONTHS` | `36` | Licencias y hardware — meses en que se amortiza una licencia perpetua |
| `ALM_REBILL_MARKUP_PCT` | `0.0` | Licencias y hardware — margen (%) sobre el coste refacturado a clientes |
| `ALM_RECONCILIATION_TOLERANCE_PCT` | `2.0` | Licencias y hardware — tolerancia (%) entre contrato, factura y gasto |
| `ALM_RECONCILIATION_EXPENSE_WINDOW_DAYS` | `45` | Licencias y hardware — días en torno a una factura en que se buscan gastos coincidentes |
| `ALM_EXPENSE_CATEGORIES` | `'software,hardware'` | Licencias y hardware — categorías de gasto que pueden pagar una factura de proveedor (CSV) |
| `ALM_CONCURRENT_PEAK_WINDOW_DAYS` | `90` | Licencias y hardware — ventana (días) del pico concurrente medido |
| `ALM_OFFBOARDING_LICENSE_RELEASE_DAYS` | `0` | Baja de personal — días tras la fecha de salida para liberar las licencias de la persona (0: de inmediato) |
| `ALM_OFFBOARDING_PENDING_ASSETS` | `'avisar'` | Baja de personal — equipos aún no devueltos: avisar (advierte), confirmar (una desactivación manual debe confirmarlo) o bloquear (se rechaza una desactivación manual; SCIM y el fin de contrato nunca se bloquean) |
| `ALM_RETURN_DUE_DAYS` | `7` | Devoluciones — días de que dispone la persona para devolver cada equipo (0: sin plazo) |
| `ALM_RETURN_GROUP_ID` | `''` | Devoluciones — cola del service desk (id de grupo) para los tickets de devolución; vacío: reglas de enrutamiento |
| `ALM_PURCHASE_GROUP_ID` | `''` | Compras — cola (id de grupo) para las solicitudes de compra cuando no hay puesto o unidad libre; vacío: reglas de enrutamiento |
| `ALM_BREAKDOWN_GROUP_ID` | `''` | Averías — cola (id de grupo) para las averías comunicadas desde «Mi equipo»; vacío: reglas de enrutamiento |
| `ALM_KIT_ON_HIRE` | `True` | Alta de personal — propone el kit correspondiente al crear a una persona (manualmente o por SCIM) |
| `ALM_KIT_FALLBACK_ROLES` | `'admin,hr'` | Alta de personal — roles que confirman un kit cuando la persona nueva no tiene responsable (CSV) |
| `ALM_CONTRACT_END_OFFBOARDING` | `True` | Baja de personal — cuando termina el contrato de un subcontratista (disponible hasta), abre la baja automáticamente |

**Proceso, infraestructura y backends opcionales (`config_groups/proceso_config.py`) — 74 variables**

Hasta la segunda auditoría de 2026-11 (hallazgo 16) estas variables se leían con `os.getenv`/`os.environ` en 36 módulos (95 lecturas). Mismos nombres de entorno y valores por defecto; los booleanos ahora aceptan `1/true/yes/on` (antes solo contaba `1`) y un valor vacío significa el valor por defecto. **El arranque rechaza `DISABLE_CSRF_MIDDLEWARE=1` en staging/production** (y `ENABLE_SUPERADMIN_BYPASS=1` fuera de development, como antes); `TENANT_AUTO_*=0` registra ahí un CRITICAL. Los valores del `.env` ahora se aplican aunque el fichero no esté exportado al proceso.

| Nombre | Defecto | Significado |
|---|---|---|
| `ENABLE_APSCHEDULER` | `True` | Ejecuta el APScheduler en proceso. |
| `ENABLE_CELERY_BEAT` | `False` | Declara que Celery beat está en ejecución. |
| `CELERY_BEAT` | `False` | Alias heredado de ENABLE_CELERY_BEAT (cualquiera activado = beat). |
| `FAIL_ON_DUAL_SCHEDULER` | `True` | Impide arrancar con ambos planificadores activados. |
| `FAIL_ON_SCHEMA_DRIFT` | `None` | Aborta el arranque ante una deriva de Alembic; sin definir = activado en staging/production, desactivado en el resto. |
| `EXPECTED_ALEMBIC_REVISION` | `''` | Revisión de Alembic fijada adicionalmente que se comprueba al arrancar. |
| `EXPOSE_API_DOCS` | `False` | Expone Swagger/ReDoc/OpenAPI en producción. |
| `CSRF_DOUBLE_SUBMIT` | `False` | Exige además X-CSRF-Token == cookie csrf_token. |
| `DISABLE_CSRF_MIDDLEWARE` | `False` | Desactiva las comprobaciones CSRF (se rechaza en staging/production). |
| `ENABLE_SUPERADMIN_BYPASS` | `False` | Bypass de login solo para desarrollo (solo development + SQLite). |
| `TENANT_AUTO_FILTER_GLOBAL` | `True` | Filtro de tenant global del ORM (se lee al importar). |
| `TENANT_AUTO_STAMP_ON_INSERT` | `True` | Estampa organization_id en las filas nuevas (se lee al importar). |
| `TENANT_SESION_SIN_CONTEXTO` | `'cerrar'` | Sesión sin tenant, sin superadmin y sin contexto de sistema declarado: `cerrar` (por defecto desde el 23-11-2026: TenantIsolationError + RLS no devuelve filas) \| `avisar` (sin filtro, un WARNING por punto de llamada; solo para localizar un punto sin declarar). Véase docs/seguridad/rutas_anonimas.md. |

| `RLS_REQUIRED` | `None` | Aborta el arranque si el RLS de Postgres no está armado (rol de aplicación sin BYPASSRLS); sin definir = activado en staging/production. |
| `REDIS_RECONNECT_BACKOFF_SECONDS` | `30.0` | Espera antes de reintentar Redis tras un fallo. |
| `PREDICTIVE_STATS_MAX_TICKETS` | `200` | Tickets analizados por petición de estadísticas predictivas. |
| `CHANGE_BATCH_SCORE_MAX` | `100` | Cambios puntuados por pasada de lote del CAB. |
| `DUCKDB_PATH` | `''` | Fichero DuckDB de OLAP; vacío = /var/contecflow/olap.duckdb o un directorio temporal. |
| `AI_MODELS_CATALOG_PATH` | `''` | JSON del catálogo de modelos y precios de IA; vacío = app/core/ai_models.json. |
| `APP_DB_USER` | `''` | Rol de BD que no es propietario, creado por `python -m app.db.rls`. |
| `APP_DB_PASSWORD` | `''` | Contraseña de APP_DB_USER. |
| `SEED_USERS_DATA_PATH` | `'seed_users_data.json'` | Siembra — JSON de usuarios. |
| `SEED_CLIENTS_DATA_PATH` | `'seed_clients_data.json'` | Siembra — JSON de clientes. |
| `SEED_EMAIL_TEMPLATES_PATH` | `'seed_email_templates.json'` | Siembra — JSON de plantillas de correo. |
| `SEED_API_KEY_DEMO` | `'nxpm_demo_integration_key_1234'` | Siembra — clave de API de demo (se guarda con hash al insertar). |
| `UPLOADS_DIR` | `'uploads'` | Raíz de las subidas de colaboración (distinta de UPLOAD_DIR). |
| `COLLAB_SIGNED_MAX_ENTRIES` | `20000` | Máximo de tokens de descarga firmados en memoria. |
| `COLLAB_STORAGE_BACKEND` | `'local'` | local | s3 | minio. |
| `COLLAB_S3_BUCKET` | `None` | Bucket S3 de colaboración. |
| `COLLAB_S3_PREFIX` | `'collaboration/'` | Prefijo de claves S3 de colaboración. |
| `COLLAB_S3_REGION` | `'eu-west-1'` | Región S3 de colaboración. |
| `COLLAB_S3_ENDPOINT` | `None` | Endpoint compatible con S3 (MinIO, versitygw). |
| `CLAMAV_ENABLED` | `False` | Analiza con clamd las subidas de colaboración. |
| `CLAMAV_HOST` | `'localhost'` | Host de clamd. |
| `CLAMAV_PORT` | `3310` | Puerto de clamd. |
| `CLAMAV_SOCKET` | `None` | Socket UNIX de clamd (prevalece sobre host/puerto). |
| `CLAMAV_TIMEOUT` | `30.0` | Timeout de clamd (s). |
| `COLLAB_SEARCH_BACKEND` | `'auto'` | auto | simple | pg | opensearch. |
| `OPENSEARCH_URL` | `'http://localhost:9200'` | URL de OpenSearch. Con COLLAB_SEARCH_BACKEND=opensearch, localhost impide arrancar en production (19-11-2026). |
| `OPENSEARCH_USER` | `None` | Usuario de OpenSearch. |
| `OPENSEARCH_PASSWORD` | `None` | Contraseña de OpenSearch. |
| `COLLAB_BUS_BACKEND` | `'memory'` | memory | redis | nats. |
| `NATS_URL` | `'nats://localhost:4222'` | URL de NATS para el bus nats. |
| `COLLAB_QUEUE_WORKERS` | `4` | Workers de la cola en proceso de colaboración. |
| `LIVEKIT_URL` | `'wss://livekit.local'` | URL de LiveKit. |
| `LIVEKIT_API_KEY` | `None` | Clave de API de LiveKit. |
| `LIVEKIT_API_SECRET` | `None` | Secreto de API de LiveKit. |
| `VAPID_CONTACT` | `'mailto:noreply@contecflow.local'` | Contacto de web push. |
| `VAPID_PUBLIC_KEY` | `None` | Clave pública de web push. |
| `VAPID_PRIVATE_KEY` | `None` | Clave privada de web push. |
| `APP_PUBLIC_URL` | `''` | Base de los enlaces del resumen de chat por correo; vacío = FRONTEND_URL (19-11-2026, antes localhost:3000). localhost impide arrancar en production. |
| `MS365_TENANT_ID` | `'common'` | Tenant de Microsoft 365 para el OAuth de colaboración. |
| `MS365_CLIENT_ID` | `None` | OAuth de colaboración — id de cliente de Microsoft 365. |
| `MS365_CLIENT_SECRET` | `None` | OAuth de colaboración — secreto de Microsoft 365. |
| `MS365_REDIRECT_URI` | `None` | OAuth de colaboración — redirección de Microsoft 365. |
| `JIRA_CLIENT_ID` | `None` | OAuth de colaboración — id de cliente de Jira. |
| `JIRA_CLIENT_SECRET` | `None` | OAuth de colaboración — secreto de Jira. |
| `JIRA_REDIRECT_URI` | `None` | OAuth de colaboración — redirección de Jira. |
| `GITHUB_CLIENT_ID` | `None` | OAuth de colaboración — id de cliente de GitHub. |
| `GITHUB_CLIENT_SECRET` | `None` | OAuth de colaboración — secreto de GitHub. |
| `GITHUB_REDIRECT_URI` | `None` | OAuth de colaboración — redirección de GitHub. |
| `GITLAB_CLIENT_ID` | `None` | OAuth de colaboración — id de cliente de GitLab. |
| `GITLAB_CLIENT_SECRET` | `None` | OAuth de colaboración — secreto de GitLab. |
| `GITLAB_REDIRECT_URI` | `None` | OAuth de colaboración — redirección de GitLab. |
| `GITHUB_WEB_BASE` | `'https://github.com'` | Base web/OAuth de GitHub; GitHub Enterprise Server: https://github.company.com (19-11-2026). |
| `GITHUB_API_BASE` | `'https://api.github.com'` | Base REST de GitHub; GHES: https://github.company.com/api/v3. Por integración: `config.api_base`. |
| `GITLAB_BASE_URL` | `'https://gitlab.com'` | Base de GitLab (autoalojado). Por integración: `config.base_url`. |
| `GOOGLE_CLIENT_ID` | `None` | OAuth de colaboración — id de cliente de Google. |
| `GOOGLE_CLIENT_SECRET` | `None` | OAuth de colaboración — secreto de Google. |
| `GOOGLE_REDIRECT_URI` | `None` | OAuth de colaboración — redirección de Google. |
| `WHISPER_LOCAL` | `False` | Los subtítulos del chat recurren a whisper local. |
| `WHISPER_BIN` | `'whisper'` | Binario de whisper. |
| `WHISPER_MODEL` | `'base'` | Modelo de whisper. |
| `WHISPER_LOCAL_BIN` | `''` | Binario del proveedor de STT (prevalece sobre WHISPER_BIN). |
| `WHISPER_LOCAL_MODEL` | `''` | Modelo del proveedor de STT (prevalece sobre WHISPER_MODEL). |
| `WHISPER_LOCAL_LANGUAGE` | `'es'` | Idioma por defecto del proveedor de STT. |
| `GEOIP_LOOKUP_ENABLED` | `False` | Envía la IP pública de cada inicio de sesión o refresco a GEOIP_LOOKUP_URL (tercero; desactivado por defecto desde el 23-11-2026 por el RGPD: requiere base jurídica, registro de actividades y contrato de encargado). |
| `GEOIP_LOOKUP_URL` | `'https://ipapi.co/{ip}/json/'` | Servicio de geolocalización por IP; se sustituye `{ip}`. |
| `GEOIP_CACHE_TTL_SECONDS` | `86400` | Caché por IP de las respuestas de geolocalización (s). |

**Escalas compartidas (`config_groups/escalas_config.py`, aplicadas por `app/core/escalas.py`) — 5 variables**

Sobrescribibles en vivo (grupos `risk` y `service_desk`).

| Nombre | Defecto | Significado |
|---|---|---|
| `RISK_PROBABILITY_CRITICAL` | `0.75` | Probabilidad prevista (0-1) — crítico desde. |
| `RISK_PROBABILITY_HIGH` | `0.5` | Probabilidad prevista (0-1) — alto desde. |
| `RISK_PROBABILITY_MEDIUM` | `0.25` | Probabilidad prevista (0-1) — medio desde. |
| `ALERT_CORRELATION_PROBLEM_SCORE` | `0.65` | Correlación de alertas — sugiere o crea un problema desde esta puntuación (y ≥3 tickets). |
| `ALERT_CORRELATION_REVIEW_SCORE` | `0.35` | Correlación de alertas — sugiere revisión desde esta puntuación. |

**Mi cuaderno (`app/core/config.py`, migración 202, docs/CUADERNO.md) — 3 variables**

Todo lo demás del cuaderno (etiquetas por defecto, plantillas, política de baja, días de papelera, IA y voz) es por empresa en Configuración › Mi cuaderno.

| Nombre | Defecto | Significado |
|---|---|---|
| `CUADERNO_PAGE_MAX_BYTES` | `2097152` | Tamaño máximo del contenido de una página (JSON del editor, bytes); el estado de colaboración acepta el doble. |
| `CUADERNO_COLLAB_HISTORY_MAX` | `20` | Instantáneas de colaboración (Yjs) conservadas por página (0 = sin límite). |
| `CUADERNO_VOICE_MAX_BYTES` | `26214400` | Tamaño máximo de una nota de voz enviada a transcripción (bytes). |

**Ticket a PR (`app/core/config.py`, migración 203, docs/integraciones/TICKET_A_PR.md) — 17 variables**

Valores por defecto de la plataforma. Cada empresa activa el módulo (desactivado por defecto) y ajusta motor, modelo, límites, ficheros protegidos, pruebas y plantillas en Configuración › Ticket a PR (clave de `app_settings` `ticket_pr.config`); las credenciales de Git viven cifradas en el almacén de integraciones (proveedor `ticket_pr`).

| Nombre | Defecto | Significado |
|---|---|---|
| `TICKET_PR_ENGINE_IMAGE` | `ghcr.io/anomalyco/opencode` | Imagen del motor del agente de programación (OpenCode). |
| `TICKET_PR_ENGINE_VERSION` | — | Versión fijada del motor (etiqueta o digest `sha256:`). Vacía o `latest`: no se ejecuta nada. |
| `TICKET_PR_ENGINE_EGRESS_HOSTS` | `models.dev,registry.npmjs.org` | Hosts que el motor necesita al arrancar (lista de permitidos del proxy de salida, además de la API del modelo). |
| `TICKET_PR_EGRESS_PROXY_IMAGE` | `ubuntu/squid:6.6-24.04_beta` | Proxy de salida (squid) con la lista de permitidos; la única salida del contenedor del agente. |
| `TICKET_PR_HELPER_IMAGE` | `busybox:1.36.1` | Imagen auxiliar (sh + tar) para llenar y vaciar el volumen del espacio de trabajo, sin red. |
| `TICKET_PR_DOCKER_BIN` | `docker` | CLI de Docker. Sin Docker no se ejecuta nada. |
| `TICKET_PR_CPUS` | `2.0` | Límite de CPU por contenedor. |
| `TICKET_PR_MEMORY_MB` | `4096` | Límite de memoria por contenedor (sin swap). |
| `TICKET_PR_PIDS_LIMIT` | `512` | Límite de procesos por contenedor. |
| `TICKET_PR_PLAN_TIMEOUT_MIN` | `15` | Tiempo máximo de la fase de plan (min); después `docker kill`. |
| `TICKET_PR_BUILD_TIMEOUT_MIN` | `45` | Tiempo máximo de la fase de compilación y de las pruebas (min). |
| `TICKET_PR_MAX_RUNS_PER_DAY` | `20` | Ejecuciones del agente por empresa y día (UTC). |
| `TICKET_PR_MAX_COST_PER_DAY_USD` | `20.0` | Coste de IA del agente por empresa y día (USD; 0: sin tope propio, sigue aplicando el tope de IA de la empresa). |
| `TICKET_PR_MAX_CONCURRENT` | `2` | Ejecuciones del agente en curso a la vez por empresa. |
| `TICKET_PR_MAX_REPO_MB` | `200` | Tamaño máximo del repositorio sin comprimir entregado al agente (MB). |
| `TICKET_PR_MAX_CHANGED_FILES` | `50` | Por encima de este número de ficheros modificados se bloquea la PR. |
| `TICKET_PR_MAX_DIFF_KB` | `512` | Por encima de este tamaño de contenido modificado se bloquea la PR (KB). |

## 3. Ajustes en vivo (Configuración → Sistema → Config. dinámica)


La fuente es `RUNTIME_FLAG_GROUPS` en `app/services/settings_service/`: **32 grupos, 445 claves**. «Defecto» es el valor por defecto del código en `Settings` (`app/core/config.py` más `config_groups/*`); un valor del `.env` lo sobrescribe. Ejemplo medido: el `.env` local define `ACCESS_TOKEN_EXPIRE_MINUTES=60`.

«Uso» es lo que encontró un grep de `app/`:
- **en vivo**: se lee en ejecución mediante `get_runtime_*`, de modo que un cambio en la interfaz surte efecto en 60 s.
- **estático**: solo se lee `settings.<KEY>`, de modo que un cambio en la interfaz **no tiene efecto**.
- **ninguno**: no hay ningún lector.

| Grupo | Clave | Tipo | Defecto | Significado | Uso |
|---|---|---|---|---|---|
| sla | SLA_P1_RESPONSE_HOURS | float | 1.0 | P1 Crítica, horas de respuesta | en vivo (`sla_service`); además, valor por defecto de columna de las políticas de SLA al importar |
| sla | SLA_P1_RESOLUTION_HOURS | float | 4.0 | P1, horas de resolución | en vivo (igual) |
| sla | SLA_P2_RESPONSE_HOURS | float | 4.0 | P2 Alta, horas de respuesta | en vivo |
| sla | SLA_P2_RESOLUTION_HOURS | float | 8.0 | P2, horas de resolución | en vivo |
| sla | SLA_P3_RESPONSE_HOURS | float | 8.0 | P3 Media, horas de respuesta | en vivo |
| sla | SLA_P3_RESOLUTION_HOURS | float | 24.0 | P3, horas de resolución | en vivo |
| sla | SLA_P4_RESPONSE_HOURS | float | 24.0 | P4 Baja, horas de respuesta | en vivo |
| sla | SLA_P4_RESOLUTION_HOURS | float | 72.0 | P4, horas de resolución | en vivo |
| sla | SLA_BUSINESS_HOURS_ONLY | bool | true | Sin política de SLA: cuenta solo las horas laborables | en vivo |
| sla | SLA_BUSINESS_START_HOUR | int | 8 | Sin política: inicio de la jornada (0-23) | en vivo |
| sla | SLA_BUSINESS_END_HOUR | int | 18 | Sin política: fin de la jornada (1-24) | en vivo |
| sla | SLA_BUSINESS_DAYS | str | `1,2,3,4,5` | Sin política: días laborables ISO (1=lun … 7=dom) | en vivo |
| sla | SLA_PREDICTION_WARNING_PCT | float | 0.7 | «En riesgo» cuando se ha consumido esta fracción del SLA (0-1) | en vivo |
| sla | SLA_PREDICTION_HOURS_CRITICAL | int | 4 | Ventana de horas de la predicción, crítica | en vivo |
| sla | SLA_PREDICTION_HOURS_HIGH | int | 8 | Ventana de horas de la predicción, alta | en vivo |
| sla | SLA_PREDICTION_HOURS_MEDIUM | int | 24 | Ventana de horas de la predicción, media | en vivo |
| sla | SLA_PREDICTION_HOURS_LOW | int | 72 | Ventana de horas de la predicción, baja | en vivo |
| sla | SLA_PREDICTION_SEVERITY_CRITICAL_H | float | 1.0 | Umbral de severidad, crítica (h) | en vivo |
| sla | SLA_PREDICTION_SEVERITY_HIGH_H | float | 4.0 | Umbral de severidad, alta (h) | en vivo |
| sla | SLA_AT_RISK_WINDOW_HOURS | float | 2.0 | Wallboard y panel de SLA: un ticket abierto que vence dentro de estas horas está en riesgo (el panel de SLA cuenta una segunda banda hasta el doble) | en vivo |
| service_desk | SD_NOTIFY_REQUESTER_ON_CREATE | bool | true | Envía un correo al solicitante al crear un ticket | en vivo (`ticket_event_processor`) |
| service_desk | SD_NOTIFY_REQUESTER_ON_REPLY | bool | true | Envía un correo al solicitante en las respuestas públicas del agente | en vivo |
| service_desk | SD_NOTIFY_REQUESTER_ON_RESOLVE | bool | true | Envía un correo al solicitante al resolverse | en vivo |
| service_desk | SD_NOTIFY_AGENTS_BY_EMAIL | bool | true | Envía también correo a los agentes (las alertas en la aplicación siempre se generan) | en vivo |
| service_desk | SD_INBOUND_ADDRESS | str | `''` | Dirección de soporte; identifica la organización y es el Reply-To | en vivo |
| service_desk | TWILIO_PHONE_NUMBERS | str | `''` | Números de Twilio de la empresa (E.164, CSV); una llamada o SMS entrante a uno de ellos le pertenece, y se rechaza una llamada a un número que ninguna empresa declara | fila por organización (`sms_service.organizacion_del_numero_de_twilio`) |
| service_desk | SD_REOPEN_ON_REPLY | bool | true | Una respuesta entrante reabre un ticket resuelto | en vivo |
| service_desk | SD_INBOUND_REQUIRE_SENDER_AUTH | bool | true | Un correo entrante actúa como su remitente solo si pasan SPF/DKIM/DMARC (`Authentication-Results`) | en vivo (`inbound_mail.remitente_fiable`) |
| service_desk | SD_INBOUND_AUTHSERV_ID | str | `''` | authserv-id del servidor de correo cuyo `Authentication-Results` es de confianza (vacío: la cabecera superior) | en vivo |
| service_desk | SD_CHANNEL_TICKET_TYPE | str | `incident` | Tipo de ticket de los correos entrantes nuevos (incident, service_request, question) | en vivo |
| service_desk | SD_MAIL_MAX_PER_RUN | int | 50 | Correos entrantes leídos por ejecución | en vivo |
| service_desk | SD_MAIL_MAX_ATTACHMENT_MB | int | 15 | Tamaño máximo del adjunto entrante (MB) | en vivo |
| service_desk | SD_CAB_GROUP_ID | str | `''` | Cola (id de grupo) que actúa como CAB | en vivo |
| service_desk | SD_CAB_APPROVAL_RULE | str | `majority` | Regla del CAB: majority, all, any | en vivo |
| service_desk | SD_CHANGE_AUTO_APPROVE_MAX_RISK | int | 30 | Los cambios estándar hasta esta puntuación de riesgo se autoaprueban | en vivo |
| service_desk | SD_STANDARD_CHANGE_MAX_FAILURE_PCT | int | 20 | Modelo de cambio estándar suspendido por encima de esta tasa de fallos (%) | en vivo |
| service_desk | SD_STANDARD_CHANGE_MIN_CLOSURES | int | 5 | Cierres necesarios para que cuente la tasa de fallos de un modelo estándar | en vivo |
| service_desk | SD_STANDARD_CHANGE_REVIEW_DAYS | int | 365 | Días que un modelo estándar permanece aprobado antes de revisarse | en vivo |
| service_desk | CHANGE_CANARY_RAMP_PCT | str | `1,5,25,50,100` | Cambios — despliegue canary: % de usuarios por fase (CSV, creciente, termina en 100; 2-10 fases, 1-100) | en vivo (`/org-defaults` → `propuestas` → ChangeRolloutPanel; `valores_de_negocio`, 19-11-2026) |
| service_desk | CHANGE_CANARY_FIRST_MINUTES | int | 30 | Cambios — despliegue canary: minutos de la primera fase (5-1440) | en vivo (`/org-defaults` → ChangeRolloutPanel) |
| service_desk | CHANGE_CANARY_STEP_MINUTES | int | 45 | Cambios — despliegue canary: minutos de cada fase intermedia (5-1440) | en vivo (`/org-defaults` → ChangeRolloutPanel) |
| service_desk | CHANGE_CANARY_LAST_MINUTES | int | 60 | Cambios — despliegue canary: minutos de la última fase (5-1440) | en vivo (`/org-defaults` → ChangeRolloutPanel) |
| service_desk | SD_EVENT_SEVERITY_MAP | str (JSON) | `{"critical":"p1_critical","high":"p2_high","error":"p2_high","warning":"p3_medium","info":"p4_low"}` | Severidad de la alerta de monitorización → prioridad del ticket | en vivo |
| service_desk | SD_EVENT_AUTO_RESOLVE | bool | true | Resuelve el incidente cuando la alerta se recupera, si nadie lo ha tocado | en vivo |
| service_desk | SD_ONCALL_PRIORITIES | str | `p1_critical,p2_high` | Prioridades que avisan al agente de guardia | en vivo |
| service_desk | SD_ONCALL_SMS | bool | true | Avisa también por SMS (necesita las variables de entorno `TWILIO_*`) | en vivo |
| service_desk | SD_KB_REQUIRE_REVIEW | bool | false | Los artículos de la KB necesitan un revisor antes de publicarse | en vivo |
| service_desk | SD_KB_REVIEWER_GROUP_ID | str | `''` | Cola de revisores (vacío: administradores) | en vivo |
| service_desk | SD_KB_RAG_MIN_SCORE_VECTOR | float | 0.35 | Coseno mínimo para citar un artículo | en vivo |
| service_desk | SD_KB_RAG_MIN_SCORE_WORDS | float | 0.5 | Sin modelo de frases: proporción de palabras para citar un artículo | en vivo |
| service_desk | SD_KB_RAG_MAX_SOURCES | int | 3 | Artículos entregados a la IA y citados por respuesta | en vivo |
| service_desk | SD_KB_CORRECTION_MATCH | float | 0.8 | Similitud para que se aplique una corrección de un experto | en vivo |
| service_desk | SD_KB_STALE_DAYS | int | 180 | Días sin tocar antes de marcar un artículo (0: desactivado) | en vivo |
| service_desk | SD_KB_CONTRADICTION_SIMILARITY | float | 0.75 | Similitud para que dos artículos se comparen con IA | en vivo |
| service_desk | SD_KB_CONTRADICTION_MAX_PAIRS | int | 10 | Pares comparados con IA en cada ejecución diaria (0: desactivado) | en vivo |
| service_desk | SD_TIME_TO_TIMESHEET | bool | true | Las horas de los tickets con proyecto van a la hoja de horas del agente | en vivo |
| service_desk | SD_ASSET_REFRESH_DAYS | int | 7 | Días antes del vencimiento de un activo que abren un ticket de renovación (0 = desactivado) | en vivo |
| service_desk | KEDB_DEFAULT_REVIEW_DAYS | int | 90 | Errores conocidos: días hasta la revisión al publicar o revisar uno, si la petición no indica ninguno (7-365) | en vivo (empresa) |
| service_desk | SD_EVENT_MAX_ATTEMPTS | int | 5 | Entrega de eventos, máximo de intentos | en vivo (solo global) |
| service_desk | SD_EVENT_BATCH_SIZE | int | 200 | Entrega de eventos, eventos por ejecución | en vivo (solo global) |
| health | HEALTH_NPS_LOOKBACK_DAYS | int | 90 | Salud del cliente: retrospectiva de NPS (días) | en vivo |
| health | HEALTH_TICKET_LOOKBACK_DAYS | int | 30 | Salud del cliente: retrospectiva de tickets (días) | en vivo |
| health | HEALTH_DEFAULT_NO_DATA | float | 70.0 | Puntuación cuando no hay datos (0-100) | en vivo |
| health | HEALTH_PORTAL_BASE_SCORE | float | 30.0 | Puntuación base del componente de portal | en vivo |
| health | HEALTH_PORTAL_SCORE_PER_SESSION | float | 7.0 | Puntuación añadida por cada sesión del portal | en vivo |
| health | HEALTH_WEIGHT_NPS | float | 0.4 | Peso, NPS | en vivo |
| health | HEALTH_WEIGHT_DELIVERY | float | 0.2 | Peso, entrega | en vivo |
| health | HEALTH_WEIGHT_BUDGET | float | 0.15 | Peso, presupuesto | en vivo |
| health | HEALTH_WEIGHT_TICKETS | float | 0.15 | Peso, tickets | en vivo |
| health | HEALTH_WEIGHT_PORTAL | float | 0.1 | Peso, portal | en vivo |
| health | HEALTH_THRESHOLD_EXCELLENT | float | 80.0 | Umbral de banda, Excelente | en vivo |
| health | HEALTH_THRESHOLD_GOOD | float | 60.0 | Umbral de banda, Buena | en vivo |
| health | HEALTH_THRESHOLD_AT_RISK | float | 40.0 | Umbral de banda, En riesgo | en vivo |
| health | PROJECT_HEALTH_WEIGHT_SCHEDULE | float | 0.3 | Salud del proyecto: peso del calendario | en vivo |
| health | PROJECT_HEALTH_WEIGHT_BUDGET | float | 0.25 | Salud del proyecto: peso del presupuesto | en vivo |
| health | PROJECT_HEALTH_WEIGHT_QUALITY | float | 0.2 | Salud del proyecto: peso de la calidad | en vivo |
| health | PROJECT_HEALTH_WEIGHT_VELOCITY | float | 0.15 | Salud del proyecto: peso de la velocidad | en vivo |
| health | PROJECT_HEALTH_WEIGHT_CLIENT | float | 0.1 | Salud del proyecto: peso del cliente | en vivo |
| health | PROJECT_HEALTH_TRAFFIC_GREEN | float | 70.0 | Verde cuando la puntuación ≥ | en vivo |
| health | PROJECT_HEALTH_TRAFFIC_YELLOW | float | 45.0 | Amarillo cuando la puntuación ≥ | en vivo |
| health | PROJECT_HEALTH_BUDGET_RATIO_GOOD | float | 0.8 | Ratio de presupuesto «bueno» cuando ≤ | en vivo |
| health | PROJECT_HEALTH_BUDGET_RATIO_OK | float | 1.0 | Ratio de presupuesto «correcto» cuando ≤ | en vivo |
| health | PROJECT_HEALTH_BUDGET_RATIO_WARN | float | 1.2 | Ratio de presupuesto «aviso» cuando ≤ | en vivo |
| health | EVM_INDEX_GREEN_MIN | float | 0.9 | EVM — CPI/SPI en verde desde (TCPI: su inverso) | en vivo (`project_service`) |
| health | EVM_INDEX_RED_BELOW | float | 0.85 | EVM — CPI/SPI en rojo por debajo de (TCPI: su inverso) | en vivo (`project_service`) |
| proyectos | PLANNING_WORKDAYS | str | `1,2,3,4,5` | Planificador — días laborables de la empresa (ISO, CSV); los festivos vienen de Configuración › Festivos | en vivo (`planificador.calendario`) |
| proyectos | PLANNING_SCHEDULE_HORIZON_DAYS | int | 400 | Planificador — días hacia delante calculados con el horario efectivo de cada persona | en vivo (`planificador.calendario`) |
| proyectos | PLANNING_CRITICAL_FLOAT_DAYS | float | 0.0 | Planificador — una tarea es crítica con una holgura total de hasta (días laborables) | en vivo (`planificador.servicio`) |
| proyectos | PLANNING_NEAR_CRITICAL_FLOAT_DAYS | float | 3.0 | Planificador — casi crítica con una holgura total de hasta (días laborables) | en vivo (`planificador.servicio`) |
| proyectos | PLANNING_AUTO_RECALCULATE | bool | true | Planificador — recalcula la ruta crítica cuando cambian fechas, dependencias o estimaciones | en vivo (`planificador.servicio`) |
| proyectos | LEVELING_OVERALLOCATION_PCT | float | 100.0 | Nivelación — sobreasignado por encima de este % de la jornada de la persona | en vivo (`planificador.nivelacion`, `planificador.carga`) |
| proyectos | LEVELING_HORIZON_DAYS | int | 120 | Nivelación — días hacia delante que mira | en vivo (`planificador.nivelacion`) |
| proyectos | RESOURCE_UNDERUSE_PCT | float | 50.0 | Recursos — infrautilizado por debajo de este % de la capacidad | en vivo (`planificador.carga`) |
| proyectos | RESOURCE_AVAILABILITY_WEEKS | int | 8 | Recursos — semanas que se muestran en la disponibilidad y las alertas | en vivo (`planificador.carga`, `cartera_service`) |
| proyectos | EVM_SNAPSHOTS_ENABLED | bool | true | Valor ganado — guarda un punto diario de curva S por proyecto activo | en vivo (`evm_service`, worker) |
| proyectos | EVM_CURVE_MAX_POINTS | int | 365 | Valor ganado — puntos de curva S devueltos (los más recientes) | en vivo (`evm_service`) |
| proyectos | EXTERNOS_UMBRAL_CONSUMO_PCT | float | 80 | Personal externo — avisa cuando una asignación consume este % de las horas contratadas o del importe del pedido | en vivo (`externos.horas`) |
| proyectos | EXTERNOS_AVISO_CADUCIDAD_DIAS | int | 14 | Personal externo — días de antelación para avisar de que caduca su acceso | en vivo (`externos.ciclo`) |
| proyectos | PORTFOLIO_MIN_SCORE_TO_ADVANCE | float | 50.0 | Cartera — puntuación mínima de la propuesta (0-100) para pasar una puerta (gate) | en vivo (`cartera_service`) |
| proyectos | PROVEEDORES_TOLERANCIA_CONCILIACION_PCT | float | 2.0 | Proveedores — diferencia aceptada (%) entre la factura del proveedor y la previsión del periodo | en vivo (`proveedores.facturacion`) |
| proyectos | PROVEEDORES_AVISO_DOCUMENTO_DIAS | int | 30 | Proveedores — días de antelación para avisar de que caduca un documento o certificación | en vivo (`proveedores.grc`) |
| proyectos | PROVEEDORES_REVISION_RIESGO_MESES | int | 12 | Proveedores — meses hasta la siguiente revisión de riesgo (la mitad si el riesgo es alto o crítico) | en vivo (`proveedores.grc`) |
| semaforos | UMBRAL_PRESUPUESTO_AVISO_PCT | float | 70.0 | Presupuesto consumido — aviso por encima de este % | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_PRESUPUESTO_CRITICO_PCT | float | 90.0 | Presupuesto consumido — crítico por encima de este % | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_CARGA_AVISO_PCT | float | 85.0 | Carga de recursos — alta por encima de este % de la capacidad | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_CARGA_CRITICO_PCT | float | 100.0 | Carga de recursos — sobrecargado por encima de este % de la capacidad | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_SOBRECARGA_HORAS_SEMANA | float | 42.0 | Burnout — una semana con más horas que esta cuenta como sobrecargada | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_SLA_AVISO_PCT | float | 90.0 | Cumplimiento de SLA — aviso por debajo de este % | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_SLA_CRITICO_PCT | float | 75.0 | Cumplimiento de SLA — crítico por debajo de este % | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_OKR_AVISO_PCT | float | 60.0 | Progreso de OKR — aviso por debajo de este % | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_OKR_CRITICO_PCT | float | 30.0 | Progreso de OKR — crítico por debajo de este % | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_NPS_AVISO | float | 50.0 | NPS — aviso por debajo de este valor (-100..100) | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_NPS_CRITICO | float | 0.0 | NPS — crítico por debajo de este valor (-100..100) | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_MARGEN_AVISO_PCT | float | 50.0 | Margen — aviso por debajo de este % | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_MARGEN_CRITICO_PCT | float | 30.0 | Margen — crítico por debajo de este % | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_SPRINT_COMPLETITUD_AVISO_PCT | float | 80.0 | Finalización del sprint — aviso por debajo de este % | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_SPRINT_COMPLETITUD_CRITICO_PCT | float | 50.0 | Finalización del sprint — crítico por debajo de este % | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_SPRINT_VELOCIDAD_AVISO_PCT | float | 85.0 | Ratio de velocidad del sprint — aviso por debajo de este % | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_SPRINT_VELOCIDAD_CRITICO_PCT | float | 50.0 | Ratio de velocidad del sprint — crítico por debajo de este % | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_APROBACION_RIESGO_SLA_AVISO_PCT | float | 50.0 | Aprobaciones — aviso de riesgo de SLA del paso desde este % | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_APROBACION_RIESGO_SLA_CRITICO_PCT | float | 80.0 | Aprobaciones — riesgo de SLA del paso crítico desde este % | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_APROBACION_RECHAZO_AVISO_PCT | float | 10.0 | Aprobaciones — aviso de tasa de rechazo desde este % | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_APROBACION_RECHAZO_CRITICO_PCT | float | 25.0 | Aprobaciones — tasa de rechazo crítica desde este % | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_APROBACION_PENDIENTES_CRITICO | float | 3.0 | Aprobaciones — un paso con tantas solicitudes pendientes es crítico | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_APROBACION_DECISION_HORAS | float | 24.0 | Aprobaciones — un paso que tarda en decidir estas horas o más es lento | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_VENCIMIENTO_HORIZONTE_DIAS | int | 90 | Vencimientos (contratos, licencias) — muestra lo que vence dentro de estos días | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_VENCIMIENTO_AVISO_DIAS | int | 30 | Vencimientos — aviso cuando quedan estos días o menos | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_VENCIMIENTO_CRITICO_DIAS | int | 14 | Vencimientos — crítico cuando quedan estos días o menos | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_HITOS_HORIZONTE_DIAS | int | 60 | Portal de clientes — próximos hitos dentro de estos días | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semaforos | UMBRAL_HITOS_INMINENTE_DIAS | int | 7 | Portal de clientes — un hito a menos de estos días es inminente | en vivo (`app/core/umbrales.py`, `useUmbrales()`) |
| semantic | SEM_THRESHOLD_EXPERT_CACHE | float | 0.92 | Clasificador semántico: umbral de acierto de la caché de expertos | en vivo |
| semantic | SEM_THRESHOLD_CRITICAL | float | 0.9 | Banda de similitud, crítica | en vivo (clave construida como `SEM_THRESHOLD_{x}`) |
| semantic | SEM_THRESHOLD_HIGH | float | 0.72 | Banda de similitud, alta | en vivo |
| semantic | SEM_THRESHOLD_MEDIUM | float | 0.58 | Banda de similitud, media | en vivo |
| semantic | SEM_THRESHOLD_LOW | float | 0.45 | Banda de similitud, baja | en vivo |
| semantic | SEM_WEIGHT_PROFILE | float | 0.4 | Asignación: peso de la coincidencia de perfil | en vivo (solo global) |
| semantic | SEM_WEIGHT_HISTORY | float | 0.6 | Asignación: peso de la coincidencia de historial | en vivo (solo global) |
| semantic | SEM_TOP_K_HISTORY | int | 3 | Asignación: los K elementos principales del historial | en vivo (solo global) |
| semantic | SEM_MULTI_ROLE_FACTOR | float | 0.7 | Asignación: factor multirrol | en vivo (solo global) |
| password_policy | MIN_PASSWORD_LENGTH | int | 8 | Longitud mínima de contraseña | en vivo (`core/security.py`) |
| password_policy | PASSWORD_REQUIRE_UPPERCASE | bool | true | Exigir mayúsculas | en vivo |
| password_policy | PASSWORD_REQUIRE_LOWERCASE | bool | true | Exigir minúsculas | en vivo |
| password_policy | PASSWORD_REQUIRE_DIGIT | bool | true | Exigir un dígito | en vivo |
| password_policy | PASSWORD_REQUIRE_SPECIAL | bool | true | Exigir un carácter especial | en vivo |
| password_policy | LOGIN_MAX_ATTEMPTS | int | 5 | Inicios de sesión fallidos antes del bloqueo | en vivo, por empresa desde el 23-11-2026 (`auth_service/estado_efimero._politica_de_bloqueo(org_id)`, caché propia de 60 s; el cubo usuario|IP antes de conocer al usuario usa la fila global) |
| password_policy | LOGIN_ATTEMPT_WINDOW_SECONDS | int | 900 | Ventana de recuento (s) | en vivo, por empresa (igual) |
| password_policy | LOGIN_LOCKOUT_SECONDS | int | 900 | Duración del bloqueo (s) | en vivo, por empresa (igual) |
| password_policy | PASSWORD_MAX_LENGTH | int | 128 | Longitud máxima | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| password_policy | PASSWORD_BLOCK_COMMON | bool | true | Rechazar contraseñas comunes (lista local) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| password_policy | PASSWORD_BLOCK_PERSONAL | bool | true | Rechazar contraseñas que contengan el nombre de usuario, el correo o el nombre | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| password_policy | PASSWORD_HISTORY_COUNT | int | 5 | Las últimas N contraseñas no se pueden reutilizar (0 = desactivado) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| password_policy | PASSWORD_MIN_AGE_HOURS | int | 0 | Horas mínimas entre cambios (0 = desactivado) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| password_policy | PASSWORD_EXPIRY_DAYS | int | 0 | Caducidad de la contraseña (días, 0 = nunca) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| password_policy | PASSWORD_EXPIRY_WARNING_DAYS | int | 14 | Aviso antes de la caducidad (días) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| password_policy | TEMP_PASSWORD_EXPIRY_HOURS | int | 72 | Validez de la contraseña temporal (horas) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| password_policy | LOGIN_LOCKOUT_NOTIFY_USER | bool | true | Avisar al usuario cuando se le bloquea | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| account_security | MFA_REQUIRED_ROLES | str | `admin` | MFA obligatorio para estos roles base (CSV) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| account_security | MFA_REQUIRED_FOR_SENSITIVE | bool | true | MFA obligatorio para capacidades sensibles | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| account_security | MFA_ALLOWED_METHODS | str | `totp,webauthn` | Segundos factores permitidos (CSV: totp, webauthn) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| account_security | MFA_GRACE_DAYS | int | 7 | Periodo de gracia de MFA (días) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| account_security | MFA_REMEMBER_DEVICE_DAYS | int | 0 | Recordar el dispositivo para MFA (días, 0 = desactivado) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| account_security | SESSION_MAX_HOURS | int | 0 | Máximo absoluto de la sesión (horas, 0 = sin tope) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| account_security | SESSION_MAX_CONCURRENT | int | 0 | Sesiones simultáneas por usuario (0 = ilimitadas) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| account_security | ACCESS_IP_ALLOWLIST | str | (empty) | IP/CIDR permitidas (CSV, vacío = cualquiera) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| account_security | ACCESS_HOURS | str | (empty) | Franja horaria permitida HH:MM-HH:MM (vacío = cualquiera) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| account_security | ACCESS_DAYS | str | `1,2,3,4,5,6,7` | Días de la semana ISO permitidos (CSV) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| account_security | ACCESS_HOURS_EXEMPT_ROLES | str | `admin` | Roles exentos de la franja horaria (CSV) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| account_security | ACCESS_BLOCKED_COUNTRIES | str | (empty) | Países bloqueados ISO-3166 alfa-2 (CSV) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| account_security | ACCOUNT_INACTIVE_DISABLE_DAYS | int | 0 | Desactivar las cuentas sin inicio de sesión durante N días (0 = desactivado) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| account_security | SECURITY_SOD_TWO_ADMINS | bool | false | Los cambios de seguridad necesitan un segundo administrador | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| account_security | SECURITY_ALERT_FAILED_LOGINS | int | 20 | Alertar tras N inicios de sesión fallidos en 15 min (0 = desactivado) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| account_security | SECURITY_ALERT_NEW_IP | bool | true | Alertar ante un inicio de sesión desde una IP nueva | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| account_security | ACCESS_REVIEW_INTERVAL_DAYS | int | 90 | Revisión de accesos obligatoria cada N días (0 = desactivado) | en vivo, por empresa (`seguridad_de_cuentas/politica.leer`); solo la escribe `PUT /security/policy` |
| locale | DEFAULT_TIMEZONE | str | `Europe/Madrid` | Zona horaria por defecto | en vivo (`/org-defaults`, SLA, SD); también muchas lecturas estáticas |
| locale | DEFAULT_LANGUAGE | str | `es` | Idioma por defecto | en vivo (`/org-defaults`, correo de SD); estático en el resto |
| locale | DEFAULT_CURRENCY | str | `EUR` | Moneda por defecto | en vivo en `/org-defaults` más 1 punto; `settings.DEFAULT_CURRENCY` estático en ~44 ficheros |
| locale | DEFAULT_COUNTRY | str | `ES` | País por defecto de clientes y proveedores nuevos (ISO 3166-1 alfa-2) | en vivo; se aplica al insertar mediante `por_empresa.rellenar_altas_por_empresa` (19-11-2026) |
| locale | SUPPORTED_CURRENCIES | str | `EUR,USD,GBP,PLN,CHF,SEK,DKK,NOK,JPY,CAD,AUD,MXN,BRL` | Monedas ofrecidas en las pantallas (CSV de códigos ISO 4217) | en vivo (`/org-defaults` → todos los selectores de moneda; lista de tipos de cambio) |
| locale | CURRENCY_SYMBOLS | str | `EUR:€,USD:$,GBP:£` | Símbolos de moneda en los documentos (CÓDIGO:símbolo, CSV); una moneda sin símbolo muestra su código | en vivo (PDF de factura) |
| locale | DEFAULT_TAX_RATE | float | 21.0 | Tipo impositivo por defecto (%) | en vivo **solo** en `/org-defaults`; los valores por defecto de columna de facturas/reservas usan el valor cargado al arrancar el proceso |
| locale | TAX_NAME | str | '' | Nombre del impuesto en las facturas; vacío = el habitual del idioma de la factura | en vivo en `invoice_pdf.nombre_del_impuesto` |
| locale | INVOICE_ISSUER_NAME | str | '' | Emisor de la factura — razón social impresa en las facturas | en vivo en `invoice_pdf.datos_del_emisor` |
| locale | INVOICE_ISSUER_TAX_ID | str | '' | Emisor de la factura — identificación fiscal (NIF/VAT) impresa en las facturas | en vivo en `invoice_pdf.datos_del_emisor` |
| locale | INVOICE_ISSUER_ADDRESS | str | '' | Emisor de la factura — domicilio social impreso en las facturas | en vivo en `invoice_pdf.datos_del_emisor` |
| locale | INVOICE_ISSUER_IBAN | str | '' | Emisor de la factura — IBAN de pago impreso en las facturas | en vivo en `invoice_pdf.datos_del_emisor` |
| locale | COMPANY_SECTOR | str | '' | Sector de la empresa para las narrativas de IA | en vivo en `bi_storytelling` |
| locale | DEFAULT_WORKING_HOURS_PER_DAY | float | 8.0 | Horas de trabajo al día | en vivo (`/org-defaults`, operaciones de tickets de SD); estático en el resto |
| locale | DEFAULT_WEEKLY_CAPACITY_HOURS | float | 40.0 | Capacidad semanal (h) | en vivo solo en `/org-defaults`; estático en ~25 ficheros (p. ej. `alert_service`) |
| locale | DEFAULT_PRODUCTIVE_HOURS_YEAR | float | 1700.0 | Coste de personal: horas productivas al año cuando el perfil de coste y el preset del país no dicen nada | en vivo (empresa; `cost_service.costes_por_defecto`) |
| locale | DEFAULT_EMPLOYER_COST_PCT | float | 0.32 | Coste de personal: coste de empresa sobre el salario bruto (0,32 = 32 %) cuando el perfil y el preset del país no dicen nada | en vivo (empresa; `cost_service.costes_por_defecto`) |
| locale | DEFAULT_WORKDAY_START | str | `09:00` | Inicio de la jornada de la empresa (HH:MM) para personas sin turno ni horario laboral | en vivo (`horario.efectivo`) |
| locale | ABSENCE_BALANCE_CARRY_PERIODS | int | 2 | Ausencias — periodos de saldo anteriores que se miran para arrastrar los sobrantes | en vivo (`ausencias.saldos`) |
| locale | HOUR_BANK_RECALC_DAYS | int | 35 | Ausencias — días hacia atrás que el pase diario recalcula la bolsa de horas | en vivo (`ausencias.bolsa`) |
| locale | DEFAULT_VACATION_DAYS_PER_YEAR | int | 23 | Días de vacaciones al año | en vivo solo en `/org-defaults`; los valores por defecto de columna de políticas/saldos son estáticos |
| locale | VACATION_MAX_DAYS_ENTITLED | int | 60 | Vacaciones — máximo de días asignados a una persona en un año (1-366, ≥ `DEFAULT_VACATION_DAYS_PER_YEAR`) | en vivo (empresa de la persona: `PATCH /advanced-config/vacation-balances` rechaza por encima de él; Configuración › Vacaciones, 19-11-2026) |
| locale | DEFAULT_IMPUTATION_LOCKOUT_DAYS | int | 14 | Días antes de que se bloqueen las imputaciones de horas | en vivo (`imputation_service/_comun._dias_de_bloqueo`, por empresa) |
| locale | DEFAULT_PROJECT_TYPE | str | `consulting` | Tipo de proyecto por defecto | en vivo |
| locale | DEFAULT_BILLING_TYPE | str | `time_material` | Tipo de facturación por defecto | en vivo |
| tokens | ACCESS_TOKEN_EXPIRE_MINUTES | int | 15 | TTL del access token (min) | en vivo. TTL efectivo = `min(EXPIRE, MAX)` |
| tokens | ACCESS_TOKEN_MAX_MINUTES | int | 30 | Tope superior del TTL del access token | en vivo |
| tokens | REFRESH_TOKEN_EXPIRE_DAYS | int | 30 | TTL del refresh token (días) | en vivo |
| key_rotation | KEY_ROTATION_ENABLED | bool | true | Rotación automática de claves JWT y de integración | en vivo (solo global) |
| key_rotation | JWT_KEY_ROTATION_DAYS | int | 30 | Periodo de rotación de la clave de firma JWT | en vivo (solo global) |
| key_rotation | JWT_KEY_RETENTION_COUNT | int | 3 | Claves JWT antiguas conservadas para verificar | en vivo (solo global) |
| key_rotation | INTEGRATION_SECRET_ROTATION_DAYS | int | 60 | Periodo de rotación de los secretos de integración | en vivo (solo global) |
| ai | CONTECFLOW_AI_MODEL | str | `claude-haiku-4-5` | Modelo LLM por defecto | en vivo (`ai_client`, `ai_modules`) |
| ai | SEMANTIC_EMBEDDINGS_BACKEND | str | `tfidf` | Backend de embeddings | en vivo (solo global) |
| ai | OPENAI_STT_MODEL | str | `gpt-4o-mini-transcribe` | Modelo de voz a texto de OpenAI | en vivo |
| ai | AI_COST_ALERT_USD_PER_DAY | float | 10.0 | Alerta de coste diario de IA (USD) | en vivo (solo global) |
| ai | STT_PROVIDER | str | `openai` | Proveedor de STT principal (openai, azure, google, whisper_local) | en vivo (mediante `stt/__init__._setting`) |
| ai | STT_FALLBACK_PROVIDERS | str | `''` | CSV de proveedores de STT alternativos | en vivo (mismo auxiliar) |
| ai | AZURE_SPEECH_REGION | str | `westeurope` | Región de Azure Speech | en vivo |
| ai | AZURE_STT_LANGUAGE | str | `` (vacío) | Idioma de STT de Azure — vacío = idioma del usuario/empresa; rellenar solo para fijar variante (es-MX) | en vivo |
| ai | GOOGLE_STT_LANGUAGE | str | `` (vacío) | Idioma de STT de Google — vacío = idioma del usuario/empresa | en vivo |
| feature_flags | M365_CALENDAR_SYNC_ENABLED | bool | false | «Sincronización del calendario M365» | **solo informativo**: lo lee únicamente `GET /m365/status`; ningún endpoint depende de él |
| feature_flags | M365_TEAMS_NOTIFICATIONS_ENABLED | bool | false | «Notificaciones de Teams de M365» | **solo informativo** (igual) |
| feature_flags | EXCHANGE_RATES_AUTO_UPDATE | bool | false | «Actualizar automáticamente los tipos de cambio» | en vivo, ajuste de plataforma (fila global): el trabajo beat `actualizar-tipos-de-cambio` (16:30) descarga los tipos del BCE solo cuando está activado |
| storage | S3_URL_EXPIRATION_HOURS | int | 24 | TTL de las URL prefirmadas (h) | en vivo (`s3_service`, ficheros de colaboración) |
| storage | DOCUMENT_CHECKOUT_HOURS | int | 24 | Check-out de documentos — la reserva caduca por sí sola tras (h) | en vivo |
| storage | MAX_FILE_SIZE_MB | int | 100 | Tamaño máximo de subida de documentos (MB) | en vivo en `documents.py`; `core/uploads.py` lee `settings` (estático) |
| security_network | TRUST_PROXY_HEADERS | bool | false | Confiar en `X-Forwarded-*` para la IP del cliente | en vivo (solo global) |
| security_network | TRUSTED_PROXY_CIDRS | str | `127.0.0.1/32,::1/128` | Proxies cuyas `X-Forwarded-*` son de confianza | en vivo (solo global) |
| ui_branding | WEBAUTHN_RP_NAME | str | `Contecflow PSA` | Nombre visible de la parte confiante (relying party) de WebAuthn | en vivo (`auth_mfa`) |
| ui_branding | FRONTEND_EMBED_BASE_URL | str | `''` | URL base de los embeds de M365/BI | en vivo (`m365_bi_embed_service`) |
| ui_branding | BI_EMBED_FRAME_ANCESTORS | str | `'self' https://teams.microsoft.com https://*.teams.microsoft.com https://*.cloud.microsoft https://*.sharepoint.com` | Página de embed de BI — quién puede mostrarla en un iframe (CSP frame-ancestors, separados por espacios) | en vivo (`/bi/embed/view`) |
| ui_branding | PROJECT_NAME | str | `Contecflow` | Nombre visible del producto (emisor de TOTP, PDF) | en vivo |
| observability | METRICS_AUTH_TOKEN | str | None | Token bearer de `/metrics`; vacío = cerrado fuera de development (2026-11) | en vivo (solo global). **Se guarda y se audita en texto plano** |
| timeouts | OUTBOUND_HTTP_TIMEOUT_SECONDS | float | 10.0 | Timeout por defecto del HTTP saliente | en vivo mediante `outbound_http_timeout()` (24 puntos de llamada) |
| timeouts | OUTBOUND_AI_TIMEOUT_SECONDS | float | 60.0 | Timeout por defecto de las llamadas de IA salientes | en vivo mediante `outbound_ai_timeout()` |
| ai | AI_PROVIDER_ERROR_COOLDOWN_SECONDS | int | 300 | Un proveedor que falla se aparta durante (s) y luego se reintenta | en vivo |
| ai | AI_DAILY_BUDGET_USD | float | 0.0 | IA — tope de gasto diario por empresa en USD; las llamadas se detienen hasta las 00:00 UTC (0: sin tope) | en vivo |
| ai | AI_DAILY_BUDGET_WARN_PCT | float | 80.0 | IA — % del tope diario desde el que avisa el AI Hub | en vivo |
| ai | ASK_DATA_EXAMPLE_MIN_SIMILARITY | float | 0.3 | Ask the Data — solapamiento mínimo de palabras (0-1) para dar un ejemplo validado | en vivo |
| ai | ASK_DATA_CONTEXT_TURNS | int | 4 | Ask the Data — preguntas anteriores de la conversación dadas al modelo para las de seguimiento (0: sin memoria) | en vivo |
| ai | SEMANTIC_RETRAIN_INTERVAL_HOURS | int | 24 | Asignación por IA — horas entre reconstrucciones automáticas de los perfiles (0: nunca) | en vivo (se aplica en la siguiente pasada horaria) |
| ai | ASK_DATA_EXAMPLES_IN_PROMPT | int | 3 | Ask the Data — ejemplos validados que se dan al modelo (0: ninguno) | en vivo |
| ai | ASK_DATA_HINT_MAX_VALUES | int | 10 | Ask the Data — valores reales mostrados cuando un filtro no encuentra nada | en vivo |
| ai | ASK_DATA_HINT_MIN_SIMILARITY | float | 0.5 | Ask the Data — similitud mínima (0-1) para que un valor real cuente como cercano | en vivo |
| ai | ASK_DATA_RETRY_WITH_REAL_VALUES | bool | true | Ask the Data — con cero filas y un valor real cercano, vuelve a preguntar al modelo una vez con los valores reales | en vivo |
| ai | ASK_DATA_REUSE_EXACT_EXAMPLE | bool | true | Ask the Data — la misma pregunta que una validada reutiliza su consulta sin llamar al modelo | en vivo |
| ai | TEAMS_KB_ANSWERS_ENABLED | bool | true | Bot de Teams — un mensaje que no es un comando se responde desde la base de conocimiento | en vivo |
| ai | SLACK_TEAM_ID | str | — | Bot de Slack — espacio de trabajo (team_id) de esta empresa; el usuario se busca solo aquí | en vivo |
| ai | TEAMS_TENANT_ID | str | — | Bot de Teams — id del tenant de Microsoft de esta empresa; el usuario se busca solo aquí | en vivo |
| ai | MCP_WRITE_MODE | str | `off` | MCP — herramientas que escriben: off (ocultas), approval (una persona aprueba cada llamada) o direct | en vivo |
| ai | MCP_RATE_LIMIT_PER_MINUTE | int | 60 | MCP — llamadas por minuto de cada credencial (o sesión); por encima, 429 con Retry-After (0: sin límite propio) | en vivo (`mcp_service.consumir_limite`) |
| ai | MCP_NOTEBOOK_ENABLED | bool | false | MCP — herramientas de «Mi cuaderno» para agentes de programación (cada persona sigue eligiendo qué cuadernos comparte) | en vivo |
| audit | AUDIT_EXPORT_MAX_ROWS | int | 100000 | Registro de auditoría — máximo de filas de la exportación firmada (las más recientes) | en vivo |
| audit | COMPLIANCE_GDPR_MAX_DAYS | int | 30 | Plazo de las solicitudes RGPD (DSR) y comprobación del informe de cumplimiento | en vivo (`bi_gdpr_service`, `informe_de_cumplimiento`) |
| audit | COMPLIANCE_GDPR_EXPORT_TTL_DAYS | int | 30 | Copia de acceso/portabilidad RGPD — días que se conserva (cifrada) tras completarse; después la ejecución diaria de retención la borra | en vivo (`cab_service/gdpr`) |
| audit | COMPLIANCE_MFA_MIN_COVERAGE_PCT | float | 100.0 | Informe de cumplimiento — % mínimo de usuarios activos con segundo factor | en vivo |
| audit | COMPLIANCE_MIN_PASSWORD_LENGTH | int | 12 | Informe de cumplimiento — longitud mínima de contraseña que debe exigir la política | en vivo |
| audit | COMPLIANCE_STALE_ACCOUNT_DAYS | int | 90 | Informe de cumplimiento — se señala una cuenta activa sin inicio de sesión durante más de estos días | en vivo |
| conectores | CONECTOR_TIMEOUT_SECONDS | float | 15.0 | Conectores — timeout de una llamada a contecmind o contecintelligence (s) | en vivo |
| conectores | CONECTOR_TOKEN_TTL_SECONDS | int | 300 | Conectores — vida solicitada del token delegado de un usuario (s) | en vivo |
| conectores | CONECTOR_LOG_RETENTION_DAYS | int | 30 | Conectores — días que se conserva el registro de llamadas | en vivo |
| conectores | CONECTOR_STATUS_WINDOW_HOURS | int | 24 | Conectores — horas que resume el panel de estado | en vivo |
| conectores | CONTECMIND_WRITER_ROLES | str | `admin,pm,team_lead` | contecmind — roles que pueden subir documentos y solicitar aprobaciones (CSV); el resto lee | en vivo |
| conectores | CONTECMIND_SUGGEST_LIMIT | int | 5 | contecmind — documentos sugeridos en un ticket | en vivo |
| conectores | CONTECMIND_UPLOAD_MAX_MB | int | 50 | contecmind — tamaño máximo de un documento subido desde contecflow (MB) | en vivo |
| conectores | CONTECMIND_ROOT_FOLDER | str | `contecflow` | contecmind — carpeta raíz donde cada registro tiene su propia carpeta | en vivo |
| conectores | CONTECINTELLIGENCE_ANALYST_ROLES | str | `admin,pm` | contecintelligence — roles que entran como analista (CSV); el resto como visor | en vivo |
| conectores | CONTECINTELLIGENCE_ASK_TIMEOUT_SECONDS | float | 120.0 | contecintelligence — timeout de una pregunta (s) | en vivo |
| conectores | BI_ETL_PAGE_SIZE | int | 100 | Conectores ETL de BI — registros pedidos por petición | en vivo (`bi_etl_service`) |
| conectores | BI_ETL_HTTP_TIMEOUT_S | float | 20.0 | Conectores ETL de BI — timeout de una petición a la fuente (s) | en vivo (`bi_etl_service`) |
| conectores | BI_ETL_LOG_MAX_ENTRIES | int | 100 | Conectores ETL de BI — entradas del registro de sincronización conservadas por conector | en vivo (`bi_etl_service`, `bi_o365_service`) |
| conectores | BI_EXPLORER_MAX_ROWS | int | 100000 | Data Explorer — filas leídas para agrupar y totalizar (por encima, el resultado indica que es parcial) | en vivo (`bi_query_builder_service`) |
| conectores | REPORT_EXPORT_MAX_ROWS | int | 100000 | Generador de informes — filas de una exportación CSV (X-Total-Count indica cuántas existen) | en vivo (`report_builder_service`) |
| informes | PERIODO_MAX_DIAS | int | 1830 | Informes — periodo más largo que se puede solicitar (días) | en vivo (`app/core/periodo.py`, todo informe con periodo) |
| informes | PERIODO_MAX_PUNTOS_HORA | int | 744 | Informes — máximo de puntos de una serie horaria | en vivo (`app/core/periodo.py`, todo informe con periodo) |
| informes | PERIODO_MAX_PUNTOS_DIA | int | 1100 | Informes — máximo de puntos de una serie diaria | en vivo (`app/core/periodo.py`, todo informe con periodo) |
| informes | PERIODO_MAX_PUNTOS_SEMANA | int | 530 | Informes — máximo de puntos de una serie semanal | en vivo (`app/core/periodo.py`, todo informe con periodo) |
| informes | PERIODO_MAX_PUNTOS_MES | int | 240 | Informes — máximo de puntos de una serie mensual | en vivo (`app/core/periodo.py`, todo informe con periodo) |
| informes | PERIODO_AUTO_MAX_PUNTOS | int | 120 | Informes — granularidad automática: la más fina que se mantenga dentro de estos puntos | en vivo (`app/core/periodo.py`, todo informe con periodo) |
| informes | BI_DELIVERY_ALLOWED_DOMAINS | str | '' | Informes BI programados — dominios externos admitidos como destinatarios (CSV; vacío = solo la empresa) | en vivo |
| informes | BI_DELIVERY_MAX_ROWS | int | 5000 | Informes BI programados — filas por informe entregado | en vivo |
| conectores | CONTECINTELLIGENCE_HANDOFF_ENABLED | bool | true | contecintelligence — Ask the Data ofrece pasar una pregunta que no sabe responder | en vivo |
| lecciones | LESSONS_CATEGORIES | str | `alcance,planificacion,estimacion,tecnica,calidad,comunicacion,cliente,proveedor,equipo,seguridad,operacion,coste` | Lecciones — categorías (CSV) | en vivo |
| lecciones | LESSONS_VALIDATOR_ROLES | str | `admin,pm,team_lead` | Lecciones — roles que validan o archivan una lección (CSV) | en vivo |
| lecciones | LESSONS_ONLY_VALIDATED | bool | true | Lecciones — solo se recomiendan las lecciones validadas | en vivo |
| lecciones | LESSONS_AI_DRAFT_ENABLED | bool | true | Lecciones — la IA redacta la lección a partir de los hechos medidos de su origen | en vivo |
| lecciones | LESSONS_AI_MAX_TOKENS | int | 4000 | Lecciones — límite de tokens del borrador de la IA (los modelos de razonamiento gastan parte pensando) | en vivo |
| lecciones | LESSONS_RECOMMENDATIONS_MAX | int | 5 | Lecciones — máximo de recomendaciones mostradas | en vivo |
| lecciones | LESSONS_RECOMMENDATIONS_MIN_SCORE | float | 0.2 | Lecciones — similitud mínima (0-1) para recomendar una lección | en vivo |
| lecciones | LESSONS_WEIGHT_CLIENT | float | 0.3 | Lecciones — peso de «mismo cliente» | en vivo |
| lecciones | LESSONS_WEIGHT_PROJECT_TYPE | float | 0.15 | Lecciones — peso de «mismo tipo de proyecto» | en vivo |
| lecciones | LESSONS_WEIGHT_TAGS | float | 0.2 | Lecciones — peso de las etiquetas compartidas (por solapamiento) | en vivo |
| lecciones | LESSONS_WEIGHT_CATEGORY | float | 0.15 | Lecciones — peso de «mismo servicio del catálogo o CI» (tickets) | en vivo |
| lecciones | LESSONS_WEIGHT_TEXT | float | 0.2 | Lecciones — peso de la similitud de texto | en vivo |
| lecciones | LESSONS_PENDING_LOOKBACK_DAYS | int | 180 | Lecciones — los proyectos cerrados, problemas, incidentes y sprints de los últimos N días cuentan como pendientes | en vivo |
| gastos | EXPENSE_MILEAGE_RATE | float | 0.26 | Gastos — tarifa de kilometraje por km (el importe de un gasto de kilometraje = km × tarifa) | en vivo |
| gastos | EXPENSE_ATTACHMENT_MAX_MB | int | 10 | Gastos — tamaño máximo de un justificante o documento (MB) | en vivo |
| gastos | EXPENSE_MANAGER_ROLES | str | `admin,pm` | Gastos — roles que ven y gestionan los gastos de todos y sus justificantes (CSV) | en vivo |
| politicas | POLICY_SIMULATION_DEFAULT_LAST_N | int | `100` | Políticas — el simulador reproduce las últimas N entidades del dominio salvo que se indique un rango de fechas | en vivo |
| politicas | POLICY_SIMULATION_MAX_ENTITIES | int | `1000` | Políticas — máximo de entidades que reproduce una simulación | en vivo |
| politicas | POLICY_DOCUMENT_TYPES | str | `receipt,invoice,ticket,attendees,other` | Políticas — tipos de documento que puede pedir un resultado «exigir adjunto» (CSV) | en vivo |
| traduccion | TRANSLATION_ENABLED | bool | True | Traducción — activada para la empresa: los mensajes de clientes se muestran en el idioma de cada operador y las respuestas salen en el del cliente (desactivada: no se envía nada a un traductor) | en vivo (`traduccion.ajustes`) |
| traduccion | TRANSLATION_PROVIDER | str | 'ai' | Traducción — proveedor: ai (el proveedor de IA de la empresa), deepl o azure (credenciales de la empresa) | en vivo (`traduccion.ajustes`) |
| traduccion | TRANSLATION_CHANNELS | str | 'ticket,email,livechat,whatsapp,slack,teams,portal_assistant,internal_chat,kb,editor' | Traducción — canales en los que se aplica (CSV): ticket, email, livechat, whatsapp, slack, teams, portal_assistant, internal_chat, kb, editor | en vivo (`traduccion.ajustes`) |
| traduccion | TRANSLATION_OUTBOUND_AUTO | bool | True | Traducción — una respuesta pública enviada sin vista previa (Slack, API) sale traducida al idioma del cliente | en vivo (`traduccion.ajustes`) |
| traduccion | TRANSLATION_INCLUDE_ORIGINAL | bool | False | Traducción — el cliente recibe también el texto original del operador debajo de la traducción | en vivo (`traduccion.ajustes`) |
| traduccion | TRANSLATION_DETECT_MIN_CONFIDENCE | float | 0.6 | Traducción — la detección local de idioma decide a partir de esta confianza (0-1); por debajo, detecta el proveedor | en vivo (`traduccion.ajustes`) |
| traduccion | TRANSLATION_MAX_BATCH_CHARS | int | 12000 | Traducción — caracteres enviados al proveedor por llamada (los lotes más largos se dividen) | en vivo (`traduccion.ajustes`) |
| traduccion | TRANSLATION_AI_MAX_TOKENS | int | 8192 | Traducción — proveedor de IA: máximo de tokens de la respuesta por llamada | en vivo (`traduccion.ajustes`) |
| traduccion | TRANSLATION_COST_PER_MILLION_CHARS_USD | float | 0.0 | Traducción — precio de DeepL/Azure por millón de caracteres (USD); cuenta para el tope diario de IA (0: no cuenta) | en vivo (`traduccion.ajustes`) |
| traduccion | TRANSLATION_CACHE_RETENTION_DAYS | int | 180 | Traducción — las traducciones en caché sin usar durante más de N días se eliminan (0: nunca) | en vivo (`traduccion.ajustes`) |
| traduccion | TRANSLATION_KB_LANGUAGES | str | '' | Traducción — idiomas del portal en los que se generan los artículos de conocimiento (CSV; vacío: todos los del portal) | en vivo (`traduccion.ajustes`) |
| licencias_uso | ALM_USAGE_IDLE_DAYS | int | 60 | Uso de licencias — sin uso durante más de N días: «sin uso» | en vivo (`alm_uso`) |
| licencias_uso | ALM_USAGE_UNDERUSED_DAYS | int | 30 | Uso de licencias — sin uso durante más de N días (y hasta el límite de «sin uso»): «infrautilizada» | en vivo (`alm_uso`) |
| licencias_uso | ALM_USAGE_MIN_ACTIVE_DAYS | int | 4 | Uso de licencias — cuando la fuente da frecuencia, menos días activos que estos en su periodo: «infrautilizada» | en vivo (`alm_uso`) |
| licencias_uso | ALM_USAGE_STALE_DATA_DAYS | int | 7 | Uso de licencias — la evidencia leída hace más de N días está desactualizada (se muestra, nunca se usa para recuperar) | en vivo (`alm_uso`) |
| licencias_uso | ALM_USAGE_SYNC_INTERVAL_HOURS | int | 24 | Uso de licencias — la sincronización programada lee cada fuente activa cada N horas | en vivo (`alm_uso`) |
| licencias_uso | ALM_USAGE_MAX_PAGES | int | 200 | Uso de licencias — máximo de páginas que lee un conector por llamada (protege contra paginación descontrolada) | en vivo (`alm_uso`) |
| licencias_uso | ALM_USAGE_REPORT_PERIOD_DAYS | int | 30 | Uso de licencias — periodo de los informes de uso y registros leídos (Microsoft 365 acepta 7, 30, 90 o 180) | en vivo (`alm_uso`) |
| licencias_uso | ALM_USAGE_INTUNE_MAX_APPS | int | 500 | Uso de licencias — Intune: aplicaciones detectadas cuyos dispositivos se leen por sincronización | en vivo (`alm_uso`) |
| licencias_uso | ALM_USAGE_SYNC_LOG_RETENTION_DAYS | int | 180 | Uso de licencias — los registros de sincronización de más de N días se eliminan | en vivo (`alm_uso`) |
| licencias_uso | ALM_USAGE_CREATE_ASSETS | bool | True | Uso de licencias — un dispositivo inventariado que aún no es un activo se crea como activo | en vivo (`alm_uso`) |
| licencias_uso | ALM_RECLAIM_GRACE_DAYS | int | 30 | Recuperación — una asignación de menos de N días nunca se recupera | en vivo (`alm_uso`) |
| licencias_uso | ALM_RECLAIM_KEEP_DAYS | int | 90 | Recuperación — cuando el titular dice que aún la necesita, se le deja en paz durante N días | en vivo (`alm_uso`) |
| licencias_uso | ALM_RIGHTSIZING_WINDOW_DAYS | int | 90 | Dimensionamiento — un servicio cuenta como usado si se usó en los últimos N días | en vivo (`alm_uso`) |
| licencias_uso | ALM_UNMANAGED_LOOKBACK_DAYS | int | 365 | Software no gestionado — se analizan los gastos de software de los últimos N días | en vivo (`alm_uso`) |
| licencias_uso | ALM_UNMANAGED_MIN_OCCURRENCES | int | 2 | Software no gestionado — apariciones necesarias para proponerlo (gastos, usuarios o dispositivos) | en vivo (`alm_uso`) |
| presupuestos | BUDGET_LINE_TYPES | str | `personal,licencias,subcontratacion,material,viajes,otros` | Presupuestos — tipos de línea (CSV); «personal» se valora a partir de las imputaciones de horas | en vivo |
| presupuestos | BUDGET_EXPENSE_TYPE_MAP | str | `travel:viajes,accommodation:viajes,meals:viajes,software:licencias,hardware:material,training:otros,subcontract:subcontratacion,other:otros` | Presupuestos — en qué tipo de línea cuenta cada categoría de gasto (categoría:tipo, CSV) | en vivo |
| presupuestos | BUDGET_APPROVER_ROLES | str | `admin` | Presupuestos — roles que aprueban o rechazan cuando no se aplica ningún flujo de aprobación (CSV) | en vivo |
| presupuestos | BUDGET_MANAGER_ROLES | str | `admin,pm,hr` | Presupuestos — roles que crean y editan presupuestos (CSV) | en vivo |
| presupuestos | BUDGET_REVENUE_TYPES | str | `horas,hitos,cuotas,otros_ingresos` | Presupuestos — tipos de línea de ingresos (CSV) | en vivo (`budgets_service`) |
| presupuestos | BUDGET_CEILING_POLICY | str | `avisar` | Presupuestos — cuando los presupuestos hijos superan el techo del padre: avisar o bloquear | en vivo (`presupuestos_preparar`) |
| presupuestos | BUDGET_JUSTIFICATION_MIN_AMOUNT | float | 5000.0 | Presupuestos — las líneas de este importe o más necesitan una justificación para enviarse (0: ninguna) | en vivo (`presupuestos_preparar`) |
| presupuestos | BUDGET_CAMPAIGN_REMINDER_DAYS | int | 7 | Presupuestos — días antes del cierre de una campaña en que se recuerda a los responsables de presupuestos sin enviar | en vivo (`presupuestos_preparar`) |
| presupuestos | BUDGET_CONTROL_POLICY | str | avisar | Presupuestos — aprobar un gasto o introducir un pedido por encima del importe disponible: no, avisar o bloquear | en vivo (`presupuestos_seguir`) |
| presupuestos | BUDGET_VARIANCE_EXPLAIN_PCT | float | 15.0 | Presupuestos — una desviación mensual por tipo de este % o más necesita una explicación antes de cerrar el mes | en vivo (`presupuestos_seguir`) |
| presupuestos | BUDGET_VARIANCE_EXPLAIN_MIN_AMOUNT | float | 1000.0 | Presupuestos — …y de este importe o más (deben cumplirse ambas) | en vivo (`presupuestos_seguir`) |
| presupuestos | BUDGET_ALM_LINE_TYPE | str | licencias | Presupuestos — tipo de línea donde los contratos y licencias de ALM cuentan como comprometidos | en vivo (`presupuestos_seguir`) |
| presupuestos | INTERNAL_IT_ERP_ACCOUNT | str | (empty) | Clientes internos — cuenta del ERP de TI o centro de coste que se abona en los asientos de cargo interno; vacío o 1-40 letras, dígitos, espacio . _ / -; sin ella se rechaza el CSV de asientos (409 `interno_sin_cuenta_ti`) | en vivo (`clientes_internos.cargos`) |
| alm | ALM_HANDOVER_ACT_ENABLED | bool | True | Licencias y hardware — emite un acta de entrega y devolución (firmada) cuando un activo cambia de manos | en vivo (`alm_*`) |
| alm | ALM_HANDOVER_CHECKLIST | str | charger,case,peripherals,no_visible_damage,data_wiped,accounts_removed | Licencias y hardware — elementos de la lista de comprobación de entrega/devolución (CSV de códigos) | en vivo (`alm_*`) |
| alm | ALM_ACT_ESIGN_PROVIDER | str | manual | Licencias y hardware — quién firma las actas: manual (en la aplicación), docusign o adobe_sign | en vivo (`alm_*`) |
| alm | ALM_LOAN_DEFAULT_DAYS | int | 14 | Licencias y hardware — duración por defecto de un préstamo (días) | en vivo (`alm_*`) |
| alm | ALM_LOAN_REMINDER_DAYS | int | 2 | Licencias y hardware — días antes del vencimiento de un préstamo en que se recuerda al titular | en vivo (`alm_*`) |
| alm | ALM_RENEWAL_LEAD_DAYS | int | 30 | Licencias y hardware — días antes del plazo de preaviso en que se anuncia una renovación | en vivo (`alm_*`) |
| alm | ALM_LICENSE_NOTICE_DAYS | int | 30 | Licencias y hardware — días de preaviso de una licencia sin contrato | en vivo (`alm_*`) |
| alm | ALM_RENEWAL_NOTIFY_ROLES | str | admin | Licencias y hardware — roles notificados de las renovaciones sin responsable (CSV) | en vivo (`alm_*`) |
| alm | ALM_PERPETUAL_AMORTIZATION_MONTHS | int | 36 | Licencias y hardware — meses en que se amortiza una licencia perpetua | en vivo (`alm_*`) |
| alm | ALM_REBILL_MARKUP_PCT | float | 0.0 | Licencias y hardware — margen (%) sobre el coste refacturado a clientes | en vivo (`alm_*`) |
| alm | ALM_RECONCILIATION_TOLERANCE_PCT | float | 2.0 | Licencias y hardware — tolerancia (%) entre contrato, factura y gasto | en vivo (`alm_*`) |
| alm | ALM_RECONCILIATION_EXPENSE_WINDOW_DAYS | int | 45 | Licencias y hardware — días en torno a una factura en que se buscan gastos coincidentes | en vivo (`alm_*`) |
| alm | ALM_EXPENSE_CATEGORIES | str | software,hardware | Licencias y hardware — categorías de gasto que pueden pagar una factura de proveedor (CSV) | en vivo (`alm_*`) |
| alm | ALM_CONCURRENT_PEAK_WINDOW_DAYS | int | 90 | Licencias y hardware — ventana (días) del pico concurrente medido | en vivo (`alm_*`) |
| licencias_integracion | ALM_OFFBOARDING_LICENSE_RELEASE_DAYS | int | 0 | Baja de personal — días tras la fecha de salida para liberar las licencias de la persona (0: de inmediato) | en vivo (`alm_integracion`) |
| licencias_integracion | ALM_OFFBOARDING_PENDING_ASSETS | str | avisar | Baja de personal — equipos aún no devueltos: avisar, confirmar o bloquear (solo desactivación manual) | en vivo (`alm_integracion`) |
| licencias_integracion | ALM_RETURN_DUE_DAYS | int | 7 | Devoluciones — días de que dispone la persona para devolver cada equipo (0: sin plazo) | en vivo (`alm_integracion`) |
| licencias_integracion | ALM_RETURN_GROUP_ID | str | (empty) | Devoluciones — cola (id de grupo) para los tickets de devolución; vacío: reglas de enrutamiento | en vivo (`alm_integracion`) |
| licencias_integracion | ALM_PURCHASE_GROUP_ID | str | (empty) | Compras — cola (id de grupo) para las solicitudes de compra cuando no hay puesto o unidad libre; vacío: reglas de enrutamiento | en vivo (`alm_integracion`) |
| licencias_integracion | ALM_BREAKDOWN_GROUP_ID | str | (empty) | Averías — cola (id de grupo) para las averías comunicadas desde «Mi equipo»; vacío: reglas de enrutamiento | en vivo (`alm_integracion`) |
| licencias_integracion | ALM_KIT_ON_HIRE | bool | True | Alta de personal — propone el kit correspondiente al crear a una persona (manualmente o por SCIM) | en vivo (`alm_integracion`) |
| licencias_integracion | ALM_KIT_FALLBACK_ROLES | str | admin,hr | Alta de personal — roles que confirman un kit cuando la persona nueva no tiene responsable (CSV) | en vivo (`alm_integracion`) |
| licencias_integracion | ALM_CONTRACT_END_OFFBOARDING | bool | True | Baja de personal — abre la baja cuando termina el contrato de un subcontratista | en vivo (`alm_integracion`) |
| audit | RETENTION_MIN_DAYS | int | 30 | Retención — ninguna política puede conservar un tipo de registro menos días que estos | en vivo |
| audit | CHAT_RETENTION_PROPOSED_MONTHS | int | 24 | Chat — retención (meses) propuesta para una política nueva (1-120, ≥ `RETENTION_MIN_DAYS` en meses de 30 días, ≤ el máximo de chat de la empresa) | en vivo (`collaboration.compliance.create_policy` cuando no se envían meses; Configuración › Chat, 19-11-2026) |
| automations | APPROVAL_EMAIL_LINK_HOURS | int | 72 | Aprobaciones — horas de validez del enlace de aprobar/rechazar del correo | en vivo |
| automations | AUTOMATIONS_DEADLINE_DAYS | int | 2 | «Tarea próxima a vencer»: días antes del vencimiento | en vivo |
| automations | AUTOMATIONS_ENABLED | bool | true | Las reglas se ejecutan con los eventos y en el barrido periódico (desactivado: solo la simulación) | en vivo |
| automations | AUTOMATIONS_EVENT_BATCH_SIZE | int | 200 | Eventos procesados por ejecución | en vivo |
| automations | AUTOMATIONS_EVENT_MAX_ATTEMPTS | int | 3 | Intentos por evento antes de dejarlo como fallido | en vivo |
| automations | AUTOMATIONS_MAX_CHAIN_DEPTH | int | 3 | Una regla puede disparar otra hasta esta profundidad | en vivo |
| automations | AUTOMATIONS_TIMESHEET_WEEKDAY | int | 5 | «Hoja de horas sin enviar»: a partir de este día de la semana (ISO, 1=lun … 7=dom) | en vivo |
| automations | AUTOMATIONS_WEBHOOK_TIMEOUT_SECONDS | int | 10 | Acción de webhook — timeout (s) | en vivo |
| automations | BPMN_MAX_AUTOMATIC_STEPS | int | 500 | BPM — pasos automáticos seguidos antes de que una instancia falle (protección contra bucles) | en vivo |
| automations | BPMN_MAX_XML_BYTES | int | 2000000 | BPM — tamaño máximo de un diagrama de proceso (XML BPMN, bytes) | ninguno encontrado el 2026-11-16 (añadido al catálogo ese día) |
| automations | BPMN_MAX_VARIABLES_BYTES | int | 65536 | BPM — tamaño máximo de las variables de una instancia (JSON, bytes) | en vivo (`bpmn_engine`) |
| automations | NOTIFICATIONS_DIGEST_HOUR | int | 8 | Resumen diario de avisos — hora local (0-23) a partir de la cual se envía por correo | en vivo |
| automations | NOTIFICATIONS_DIGEST_MAX_ITEMS | int | 20 | Resumen diario de avisos — máximo de avisos listados | en vivo |
| automations | NOTIFICATIONS_ALERTS_TIME | str | `08:00` | Motor de alertas — hora local (HH:MM, zona horaria de la empresa) a la que se ejecuta cada día | en vivo (`worker`, 19-11-2026) |
| automations | NOTIFICATIONS_BUDGET_CAMPAIGN_TIME | str | `08:30` | Recordatorio de la campaña de presupuesto — hora local (HH:MM) a la que se envía cada día | en vivo (`worker`, 19-11-2026) |
| automations | NOTIFICATIONS_MISSING_IMPUTATIONS_TIME | str | `18:00` | Recordatorio de imputaciones de horas pendientes — hora local (HH:MM); solo a las personas cuyo horario tiene trabajo ese día | en vivo (`worker`, 19-11-2026) |
| automations | NOTIFICATIONS_PERF_REMINDERS_TIME | str | `09:00` | Recordatorios de evaluaciones de desempeño — hora local (HH:MM) a la que se envían cada día | en vivo (`worker`, 19-11-2026) |
| automations | PERF_REMINDER_WINDOW_DAYS | int | 7 | Recordatorios de evaluaciones de desempeño — recuerda cuando el ciclo cierra en N días (1-90) | en vivo (empresa del ciclo, `perf_reminder_service`, 19-11-2026) |
| automations | PERF_REMINDER_UNDATED_CYCLE_DAYS | int | 30 | Recordatorios de evaluaciones de desempeño — un ciclo sin fecha de fin se recuerda tras N días activo (1-365) | en vivo (empresa del ciclo) |
| automations | PERF_STALLED_CYCLE_DAYS | int | 45 | Evaluaciones de desempeño — un ciclo activo más de N días con baja finalización está estancado (1-365) | en vivo (empresa del ciclo, `org_perf_kpis`) |
| automations | PERF_STALLED_COMPLETION_PCT | float | 50.0 | Evaluaciones de desempeño — estancado por debajo de este % de finalización cuando está vencido o es antiguo (0-100) | en vivo (empresa del ciclo, `org_perf_kpis`) |
| automations | BPMN_SERVICE_RETRIES | int | 3 | BPM — reintentos de una acción automática antes de que sea un incidente (0-20) | en vivo (`bpmn_engine`) |
| automations | BPMN_STUCK_HOURS | int | 72 | BPM — horas de un paso pendiente para contar la instancia como atascada | en vivo (`bpmn_gobierno`) |
| automations | BPMN_SEGREGACION_DE_FUNCIONES | bool | false | BPM — quien diseña o publica una versión no aprueba en sus instancias | en vivo (`bpmn_engine`, `approval_engine`) |
| locale | SCENARIO_CAPACITY_ROLES | str | `pm,team_lead,employee,subcontractor` | Escenarios — roles cuya capacidad cuenta (separados por comas) | en vivo |
| locale | OVERTIME_LEGAL_ANNUAL_CAP_HOURS | float | 80.0 | Horas extra — tope legal anual por persona (horas; 80 = art. 35.2 ET; 0 = sin tope) | en vivo |
| risk | RISK_BUDGET_OVER_FACTOR | float | 2.0 | Presupuesto — puntos por cada % por encima del 100 % | en vivo |
| risk | RISK_BUDGET_WARN_FACTOR | float | 3.0 | Presupuesto — puntos por cada % por encima del aviso | en vivo |
| risk | RISK_BUDGET_WARN_PCT | float | 85.0 | Presupuesto — % gastado en el que empieza el riesgo | en vivo |
| risk | RISK_CACHE_MINUTES | int | 60 | Las puntuaciones se reutilizan durante (minutos) | en vivo |
| risk | RISK_DELAY_FACTOR | float | 0.8 | Probabilidad de retraso — % por punto de puntuación | en vivo |
| risk | RISK_DELAY_MAX_PCT | float | 95.0 | Probabilidad de retraso — máximo (%) | en vivo |
| risk | RISK_DELAY_PCT_PER_WEEK | float | 20.0 | Retraso previsto — % de probabilidad por semana | en vivo |
| risk | RISK_HISTORY_POINTS | int | 12 | Detalle — puntos de historial mostrados | en vivo |
| risk | RISK_PROBABILITY_CRITICAL | float | 0.75 | Probabilidad prevista (0-1) — crítico desde (ML, oráculo, severidad del ticket) | en vivo (`app/core/escalas.py`) |
| risk | RISK_PROBABILITY_HIGH | float | 0.5 | Probabilidad prevista (0-1) — alto desde | en vivo (`app/core/escalas.py`) |
| risk | RISK_PROBABILITY_MEDIUM | float | 0.25 | Probabilidad prevista (0-1) — medio desde | en vivo (`app/core/escalas.py`) |
| risk | RISK_LEVEL_CRITICAL | float | 75.0 | Puntuación de riesgo — crítico desde (0-100) | en vivo |
| risk | RISK_LEVEL_HIGH | float | 50.0 | Puntuación de riesgo — alto desde (0-100) | en vivo |
| risk | RISK_LEVEL_MEDIUM | float | 25.0 | Puntuación de riesgo — medio desde (0-100) | en vivo |
| risk | RISK_POINTS_PER_HIGH_RISK | float | 25.0 | Recursos — puntos por cada riesgo abierto de alta probabilidad | en vivo |
| risk | RISK_POINTS_PER_OPEN_CR | float | 20.0 | Alcance — puntos por cada solicitud de cambio abierta | en vivo |
| risk | RISK_SCHEDULE_FACTOR | float | 1.5 | Calendario — puntos por cada % de retraso sobre el plan | en vivo |
| risk | RISK_WEIGHT_BUDGET | float | 0.3 | Puntuación de riesgo — peso del presupuesto (0-1) | en vivo |
| risk | RISK_WEIGHT_RESOURCE | float | 0.15 | Puntuación de riesgo — peso de los recursos (0-1) | en vivo |
| risk | RISK_WEIGHT_SCHEDULE | float | 0.4 | Puntuación de riesgo — peso del calendario (0-1) | en vivo |
| risk | RISK_WEIGHT_SCOPE | float | 0.15 | Puntuación de riesgo — peso del alcance (0-1) | en vivo |
| service_desk | SD_AUTONOMOUS_AGENT_ENABLED | bool | false | Agente autónomo — revisa los tickets nuevos cada 5 min (comenta y puede resolver) | en vivo |
| service_desk | SD_AUTONOMY_RESOLVE_THRESHOLD | float | 0.8 | Agente autónomo — confianza para resolver por sí solo (0-1) | en vivo |
| service_desk | SD_AUTONOMY_SUGGEST_THRESHOLD | float | 0.5 | Agente autónomo — confianza para comentar un playbook (0-1) | en vivo |
| service_desk | SD_AUTONOMOUS_AGENT_MODE | str | `suggest` | Agente autónomo — modo: suggest (un agente aplica la propuesta) o execute | en vivo |
| service_desk | SD_AUTONOMOUS_DISABLED_PLAYBOOKS | str | — | Agente autónomo — playbooks integrados desactivados para la empresa (CSV de ids) | en vivo |
| service_desk | SD_QUEUE_SLA_RISK_WEIGHT | float | `0.65` | Cola de riesgo — peso del riesgo de SLA frente al valor de negocio (0-1) | en vivo |
| service_desk | SD_DUPLICATE_WINDOW_DAYS | int | `14` | Duplicados — días hacia atrás desde el ticket para buscar similares (0: sin límite) | en vivo |
| service_desk | SD_DUPLICATE_MIN_SIMILARITY | float | `0.35` | Duplicados — similitud mínima (0-1) para proponer un ticket | en vivo |
| service_desk | SD_DUPLICATE_MAX_CANDIDATES | int | `5` | Duplicados — máximo de candidatos mostrados (0: todos) | en vivo |
| service_desk | SD_PRESENCE_TTL_SECONDS | int | `45` | Aviso de colisión — segundos sin latido tras los cuales un visor se da de baja | en vivo |
| service_desk | SD_PORTAL_ASSISTANT_ACTION_TTL_MINUTES | int | `15` | Asistente del portal — minutos durante los que se puede confirmar una acción propuesta | en vivo |
| service_desk | SD_PORTAL_ASSISTANT_MIN_MATCH | float | `0.2` | Asistente del portal — similitud mínima (0-1) para proponer un servicio del catálogo | en vivo |
| service_desk | SD_PASSWORD_RESET_SERVICE_ID | str | — | Asistente del portal — servicio del catálogo que restablece contraseñas (vacío: no se ofrece) | en vivo |
| service_desk | SD_PORTAL_ASSISTANT_AI | bool | `true` | Asistente del portal — entender con la IA (ruta 'portal_assistant' en el AI Hub); desactivado: coincidencia por palabras clave | en vivo |
| service_desk | SD_PORTAL_ASSISTANT_MAX_TOKENS | int | `700` | Asistente del portal — máximo de tokens por respuesta de IA | en vivo |
| service_desk | SD_SLACK_TICKET_CHANNEL | str | — | Slack — id del canal donde se publica la tarjeta de cada ticket nuevo (su hilo queda vinculado al ticket; vacío: desactivado) | en vivo |
| service_desk | SD_SLACK_INTAKE_CHANNELS | str | — | Slack — ids de los canales de entrada (CSV): cada mensaje de primer nivel abre un ticket vinculado a su hilo | en vivo |
| service_desk | SD_CHANNEL_MAX_ATTACHMENT_MB | int | `16` | Canales — tamaño máximo de adjunto recibido o enviado por WhatsApp/Slack (MB) | en vivo |
| service_desk | ALERT_CORRELATION_PROBLEM_SCORE | float | 0.65 | Correlación de alertas — puntuación (0-1) para sugerir o crear un problema (con 3 o más tickets) | en vivo (`app/core/escalas.py`) |
| service_desk | ALERT_CORRELATION_REVIEW_SCORE | float | 0.35 | Correlación de alertas — puntuación (0-1) para sugerir una revisión | en vivo (`app/core/escalas.py`) |
| tenants | IMPERSONATION_ENABLED | bool | true | El soporte de la plataforma puede iniciar sesión como un usuario de una empresa (con motivo, auditado) | en vivo |
| tenants | IMPERSONATION_MAX_MINUTES | int | 30 | Iniciar sesión como — duración máxima de la sesión (minutos) | en vivo |
| tenants | ORG_DEFAULT_MAX_USERS | int | 25 | Empresa nueva: límite de usuarios por defecto (cuando la petición de creación no indica ninguno) | en vivo (plataforma) |
| tenants | ORG_DEFAULT_MAX_PROJECTS | int | 100 | Empresa nueva: límite de proyectos por defecto (cuando la petición de creación no indica ninguno) | en vivo (plataforma) |
| tenants | TENANT_DELETION_QUARANTINE_DAYS | int | 30 | Eliminación de empresa — cuarentena antes de borrar sus datos (días) | en vivo |
| timeouts | AI_AGENT_TURN_TIMEOUT_SECONDS | int | 90 | NexusAgent — timeout por turno del modelo (s) | en vivo |
| timeouts | AI_LOCAL_HTTP_TIMEOUT_SECONDS | int | 120 | Llamada a Ollama (modelo local) — timeout (s) | en vivo |
| timeouts | AI_MODELS_LIST_TIMEOUT_SECONDS | int | 30 | IA «Sincronizar modelos» — timeout (s) | en vivo |
| timeouts | SSO_CLOCK_SKEW_SECONDS | int | 60 | SSO — desfase de reloj tolerado al validar el id_token (segundos) | en vivo |
| timeouts | SSO_HTTP_TIMEOUT_SECONDS | float | 10.0 | SSO — timeout de la llamada al proveedor de identidad (segundos) | en vivo |
| tokens | DEVELOPER_TOKEN_TTL_MINUTES | int | 60 | TTL del token de aplicación del portal de desarrolladores (minutos) | en vivo |
| tokens | PASSKEY_PASSWORDLESS_ENABLED | bool | true | Permite iniciar sesión solo con una passkey (sin contraseña) | en vivo |
| tokens | BI_TOKEN_DAILY_REQUEST_LIMIT | int | 10000 | Tokens BI — peticiones al día por token (0 = sin límite) | en vivo |
| tokens | BI_BOOKMARK_SHARE_DAYS | int | 30 | Marcadores BI — días que vale un enlace compartido (0 = sin caducidad) | en vivo |
| tokens | RECURRING_TASKS_MAX_CATCHUP | int | 10 | Tareas recurrentes — máximo de ocurrencias atrasadas creadas al ponerse al día | en vivo |
| tokens | COLLAB_TUS_TTL_HOURS | int | 24 | Subidas del chat — horas antes de purgar una subida reanudable sin terminar | en vivo |
| tokens | DOC_COLLAB_HISTORY_MAX | int | 200 | Documentos coeditados — instantáneas que se guardan en el historial (0 = sin límite) | en vivo |
| tokens | AI_CONTRACT_MAX_PAGES | int | 200 | Análisis de contratos con IA — máximo de páginas del PDF que se leen (0 = sin límite) | en vivo |
| tokens | QB_MINOR_VERSION | int | 65 | QuickBooks — versión menor de la API cuando la integración no fija una | en vivo |

## 4. Variables leídas fuera de `Settings`


Solo quedan estas; `tests/test_auditoria_2026_11_config_2.py` falla ante cualquier otra lectura de `os.environ`/`os.getenv` en `app/`.

| Nombre | Dónde | Por qué está fuera de `Settings` |
|---|---|---|
| `TESTING` | `app/core/entorno.py` (`en_pruebas()`) | Señal del arnés de pruebas fijada por `tests/conftest.py`; los tests la cambian con `monkeypatch.setenv` después de construir `Settings`, por lo que se lee en cada llamada. `1` desactiva CSRF, usa una clave de límite de tasa por petición y omite la comprobación previa del esquema y el planificador de colaboración. |
| `PYTEST_CURRENT_TEST` | `app/core/entorno.py` (`ejecutando_pytest()`) | La fija el propio pytest, en cada test. |
| `PROMETHEUS_MULTIPROC_DIR` | `app/core/metrics.py` | Lo consume `prometheus_client` desde el entorno del proceso; se fija a partir de `METRICS_MULTIPROC_DIR` (`setdefault`) o por el gestor de procesos. |
| `DATABASE_URL` | `app/db/migrate_to_pg.py` (valor por defecto de `--pg-url`) | CLI independiente que debe ejecutarse sin el resto de `Settings` (sin `SECRET_KEY`, etc.). |

Variables solo de compose (las consume `docker-compose.yml`, no Python): `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`, `REDIS_PORT`, `REDIS_MAXMEMORY`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_BUCKET`, `MINIO_PORT`, `API_WORKERS`, `WORKER_CONCURRENCY`, `WEB_PORT`, `PROMETHEUS_PORT`, `CONTECFLOW_APP_IMAGE`, `CONTECFLOW_WEB_IMAGE`, `APP_DB_USER`/`APP_DB_PASSWORD` (rol de base de datos de los contenedores de la aplicación; por defecto el propietario `POSTGRES_*`), `CONTECFLOW_PROXY_CIDRS` (pasa a ser `TRUSTED_PROXY_CIDRS` del contenedor `api`). Frontend (Vite): `VITE_API_URL`, `VITE_WS_URL`, `VITE_PORT`, `API_URL` (alternativa del destino del proxy).

`.env.example` define `ACCESS_TOKEN_EXPIRE_MINUTES=60`, que se limita a `ACCESS_TOKEN_MAX_MINUTES` (30) para el token, mientras que el `max_age` de la cookie usa los 60 min sin limitar.
