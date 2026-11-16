# Despliegue de Contecflow PSA

Guía para quien despliega: **A**, un entorno nuevo desde cero; **B**, la
actualización de uno existente hasta la cabeza actual de migraciones; **C**,
pruebas de humo. Todo sale del código (`app/core/config.py`,
`app/core/config_groups/*`, `.env.example`, `docker-compose.yml`, `setup.sh`,
`scripts/deploy.sh`, `scripts/backup.sh`, `alembic/versions/`). Rutas de la API
con el prefijo `/api/v1`. Lo que no se ha podido comprobar en ejecución lo dice.

Cabeza de migraciones al revisar esta guía (2026-11-16):
`169_bpmn_decisiones_y_codigos_de_error` (123 revisiones, una sola cadena). La
fuente de verdad es siempre `python -m alembic heads`.

Desarrollo en local (`./setup.sh demo|clean|start`, SQLite o Postgres en
Docker): README, «3. Requirements and installation». Esta guía trata el stack
de `docker-compose.yml` con el perfil `app`.

## A. Entorno nuevo

### A.1 Qué levanta el compose

`docker compose --profile app up -d` levanta `postgres` (16), `redis` (7), `s3`
(versitygw), `migrate`, `api` (uvicorn con `API_WORKERS` procesos, 4 por
defecto), `worker` (Celery), `beat` (Celery beat, único planificador: el
compose fija `ENABLE_APSCHEDULER=0` y `ENABLE_CELERY_BEAT=1`) y `web` (nginx con
el frontend construido, que hace de proxy de `/api`). Los puertos se publican
solo en `127.0.0.1`: `WEB_PORT` (por defecto `127.0.0.1:8080`), Postgres
`127.0.0.1:5434`, Redis `127.0.0.1:6381` y S3 `127.0.0.1:9003`. La API no
publica puerto: solo la alcanza nginx. El TLS y el dominio público los pone un
proxy por delante de `WEB_PORT`, que no está en el compose. Con
`--profile observability` se añaden Prometheus y los exportadores.

### A.2 Volúmenes externos

`contecflow_postgres_data` y `contecflow_s3_data` son `external: true`: compose
no los crea ni los borra (un `down -v` no los toca). En una máquina nueva hay
que crearlos antes del primer `up`; si no, `up` falla con «external volume not
found»:

```bash
docker volume create contecflow_postgres_data
docker volume create contecflow_s3_data
```

`setup.sh` (modos `demo`, `clean` y `update`) los crea si faltan.
`contecflow_redis_data` y `contecflow_prometheus_data` son regenerables y los
crea compose.

### A.3 El fichero `.env`

1. Copia `.env.example` a `.env`. Ojo: con Docker disponible, `setup.sh` crea
   un `.env` mínimo (solo las variables del compose) antes del paso que copia
   el ejemplo, y entonces ya no lo copia. Si no tienes `.env`, cópialo tú antes.
2. `ENVIRONMENT`: el compose pone `production` si no la defines (también es el
   valor por defecto del código). Valores admitidos: `development`, `test`,
   `staging` y `production`.
3. Con `staging` o `production` el arranque **falla** (validadores de
   `app/core/config.py` y comprobaciones de `app/main.py`) si:
   - `SECRET_KEY` tiene menos de 32 caracteres o es un marcador (`CHANGE_ME…`);
   - `CLIENT_PORTAL_SECRET` tiene menos de 32 caracteres, poca entropía o es un marcador;
   - `SUPERADMIN_PASSWORD` es un marcador o una contraseña conocida, o tiene menos de 16 caracteres o menos de 8 distintos;
   - `DEFAULT_USER_PASSWORD` es un marcador o el valor por defecto conocido;
   - `WEBHOOK_SECRET` o `INBOUND_EMAIL_SECRET` están vacías o tienen menos de 24 caracteres;
   - `ALLOWED_ORIGINS` está vacía, contiene `*` o contiene `localhost`;
   - `FRONTEND_URL`, `BACKEND_URL`, `BASE_URL` o `WEBAUTHN_ORIGIN` apuntan a `localhost`, o `WEBAUTHN_RP_ID` es `localhost` o `127.0.0.1`;
   - en `production`, Redis no responde y `RATE_LIMIT_REQUIRE_REDIS_IN_PRODUCTION` sigue activa (por defecto);
   - la base no está en la revisión que espera el código: con `FAIL_ON_SCHEMA_DRIFT` sin definir, el control de deriva aborta en `staging` y `production`.

   Genera cada secreto con `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
4. El compose exige además (`${VAR:?}`): `POSTGRES_USER`, `POSTGRES_PASSWORD`,
   `POSTGRES_DB`, `MINIO_ROOT_USER` y `MINIO_ROOT_PASSWORD`.
5. Aislamiento en la base (RLS): define `APP_DB_USER` y `APP_DB_PASSWORD`. El
   servicio `migrate` ejecuta `python -m app.db.rls`, que crea ese rol sin
   superusuario ni `BYPASSRLS` y aplica las políticas. `api`, `worker` y `beat`
   conectan con ese rol; las migraciones, con el dueño (`POSTGRES_USER`). Sin
   ellas todo conecta como dueño: las políticas existen pero no actúan, y
   Admin → Estado del sistema lo avisa.
6. Las variables de integraciones (correo entrante, métricas, Stripe, GeoIP,
   passkeys…) y los ajustes por organización están en B.1. La lista completa,
   con su valor por defecto, está en el README («4.2 Settings fields»).
   `.env.example` recoge las que necesita un operador y explica al final qué
   familias de ajustes finos se quedan fuera a propósito.

### A.4 Arranque

Opción recomendada: `./scripts/deploy.sh`. Hace, en orden: imágenes (las
descarga si `CONTECFLOW_APP_IMAGE`/`CONTECFLOW_WEB_IMAGE` apuntan a un
registro; si no, las construye), copia de seguridad (`scripts/backup.sh`; si la
base ya está en marcha y la copia falla, se para), `docker compose --profile app
up -d` comprobando que `migrate` sale con 0, y `GET /health` a través de nginx.

A mano: `docker compose --profile app up -d`. El servicio `migrate` ejecuta
`python -m alembic upgrade head && python -m app.db.rls`, y `api`, `worker` y
`beat` esperan a que termine bien.

### A.5 Primer administrador

No hay ningún paso que se ejecute en producción y cree el primer usuario: el
seed (`python -m app.db.seed`) y `scripts/reset_to_admin_only.py` se niegan si
`ENVIRONMENT` no es de desarrollo o pruebas (`app/core/entorno.py`).
`reset_to_admin_only.py` **borra todos los datos** y crea la organización
`default` y el usuario `admin` (superadmin) con `SUPERADMIN_EMAIL` y
`SUPERADMIN_PASSWORD`. En una base recién migrada y vacía no hay nada que
perder, así que se puede lanzar una vez con `ENVIRONMENT=development` solo para
ese proceso, por ejemplo:

```bash
docker compose --profile app run --rm -e ENVIRONMENT=development api python scripts/reset_to_admin_only.py
```

**No verificado en ejecución**, y **nunca** sobre una base con datos. Después,
entra con el usuario `admin` y crea las organizaciones y los usuarios desde la
aplicación (README, «Organizations»).

### A.6 Detrás del proxy

- `BACKEND_URL` tiene que ser la URL pública (`https://<dominio>`): con ella se
  construyen las vueltas de OAuth y se comprueba la firma de Twilio (contra
  `BACKEND_URL` + ruta y, si no, contra la URL que ve la API).
- Con `docker-compose.yml` la API ya cree las cabeceras `X-Forwarded-*` de
  nginx: el servicio `api` fuerza `TRUST_PROXY_HEADERS=1` y
  `TRUSTED_PROXY_CIDRS` (los tres rangos privados; se acotan con
  `CONTECFLOW_PROXY_CIDRS`), y uvicorn arranca con `--no-proxy-headers`, así
  que `FORWARDED_ALLOW_IPS` no hace falta. El proxy de delante debe conservar
  el `Host` o mandar `X-Forwarded-Host`, y mandar `X-Forwarded-Proto: https`.
- Sin compose: `TRUST_PROXY_HEADERS=true` y en `TRUSTED_PROXY_CIDRS` la red del
  proxy. Si no, la IP del cliente (rate limiting, riesgo de sesión) será la del
  proxy.

### A.7 Después del primer arranque

Haz las pruebas de humo de la sección C. Configura en la aplicación lo que va
por organización (B.1: secreto de Jira, `SLACK_TEAM_ID`, `TEAMS_TENANT_ID`,
`TWILIO_PHONE_NUMBERS`, secreto propio de correo entrante). Las políticas de
gastos y las reglas de ausencias (tipos, cupos, turnos, documentos) las
configura cada empresa: DOCS.md §22 bis a §22 quater y, en el README, «Policies
& rules engine», «Absences» y «Expenses».

## B. Actualizar un entorno existente

### B.0 Antes de empezar

1. **Copia de seguridad** de la base y de los ficheros: `./scripts/backup.sh`
   (`pg_dump -Fc` comprobado con `pg_restore --list`, el volumen S3 en tar y un
   manifiesto con SHA-256 y la revisión de Alembic). Se restaura con
   `./scripts/restore.sh <copia> --borra-lo-que-hay`. `scripts/deploy.sh` ya
   hace la copia. Las migraciones 159, 160, 161, 166 y 167 mueven datos. La 160
   borra `mfa_configs` y su `downgrade` no la recupera.
2. Mira en qué revisión está la base (`python -m alembic current`) y cuál es la
   cabeza del código (`python -m alembic heads`). La tabla de B.2 cubre desde la
   158; si vienes de antes, revisa también las intermedias con el mismo
   criterio.
3. Añade al `.env` las variables nuevas de B.1: un `.env` creado antes no las
   tiene.

### B.1 Variables y ajustes nuevos

Con `ENVIRONMENT=staging` o `production`, las marcadas *obligatoria* tumban el
arranque si faltan. El resto solo apaga su función.


Con `ENVIRONMENT=staging` o `production`, el arranque **falla** si falta algo
obligatorio o si se queda en el valor de desarrollo. Las variables marcadas
*obligatoria* tumban el arranque. El resto solo apaga su función.

| Variable | ¿Obligatoria? | De dónde sale el valor y qué hacer |
|---|---|---|
| `INBOUND_EMAIL_SECRET` | **Sí** en staging/producción (vacía o de menos de 24 caracteres → no arranca). Lo mismo vale para `WEBHOOK_SECRET`. | Genérala: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Configura la pasarela de correo (Mailgun, SendGrid o Postmark) para que haga `POST /api/v1/sd/inbound-email` con la cabecera `X-Contecflow-Email-Secret: <valor>`, o `POST /api/v1/sd/multichannel/inbound/email` con `X-Inbound-Secret: <valor>` (o el campo `token` del cuerpo). Los dos usan el mismo secreto. Una organización puede tener su propio secreto con la credencial `webhooks.inbound_email_secret` (Configuración → Integraciones, o `PUT /api/v1/settings/integrations/webhooks/inbound_email_secret`). La organización se reconoce por su `SD_INBOUND_ADDRESS`. Si no hay secreto, la respuesta es 403. |
| `METRICS_AUTH_TOKEN` | Solo si `METRICS_ENABLED=1`. | Genera un valor aleatorio y ponlo como `bearer_token` en el scrape de Prometheus. Si no hay token y el entorno no es `development`/`test`/`testing`, `/metrics` devuelve 401. Es un ajuste de plataforma: el superadmin también puede cambiarlo en caliente (grupo `observability`), y ese valor tiene prioridad sobre el del entorno. |
| `STRIPE_WEBHOOK_SECRET` | Solo si se cobra con Stripe. | En Stripe, ve a Developers → Webhooks → *Add endpoint*. Pon la URL `https://<dominio>/api/v1/invoices/stripe/webhook` y elige los eventos `checkout.session.completed` y `checkout.session.async_payment_succeeded` (son los únicos que aplica `payments_service`). Copia el *Signing secret* (`whsec_…`). También se puede guardar como credencial `stripe.webhook_secret`. Sin secreto, el webhook responde 503. Si la firma no cuadra o tiene más de 300 s, responde 400. Para crear los enlaces de pago hace falta `STRIPE_SECRET_KEY`. |
| `SLACK_TEAM_ID` | No es variable de entorno: es un **ajuste en vivo por organización** (grupo `ai`). | Es el ID del workspace (`T…`), el mismo que Slack manda como `team_id` en cada slash command. Se pone en Configuración → Configuración dinámica → IA, o con `PUT /api/v1/settings/runtime/ai/SLACK_TEAM_ID`, con la sesión de un admin de esa organización. Si dos organizaciones tienen el mismo valor, Slack recibe 403. Si ninguna lo tiene, el usuario se busca en todas y queda un aviso en el log. La firma se comprueba con `SLACK_SIGNING_SECRET` (global) o con la credencial `slack.signing_secret` de la organización. |
| `TEAMS_TENANT_ID` | Igual que el anterior: ajuste en vivo por organización (grupo `ai`). | Es el *Tenant ID* (GUID) de Microsoft Entra ID (Entra admin center → Overview). Es el `tenant.id` que pone el Bot Framework. Se configura igual que `SLACK_TEAM_ID`. El bot necesita además `TEAMS_BOT_APP_ID`. |
| Secreto del webhook de Jira | Por organización. **No** es `JIRA_WEBHOOK_SECRET`: el global ya no autentica nada, así que déjalo vacío. | Un admin entra en la pantalla *Jira* (`/jira-integration`) y pulsa *rotar secreto*, o llama a `POST /api/v1/jira/webhook-secret`. El secreto se ve **una sola vez**. Al rotarlo, el anterior deja de valer y queda en la auditoría. En Jira, apunta el webhook a `https://<dominio>/api/v1/jira/webhook?org=<organization_id>` (o a `/api/v1/integrations/jira/webhook?org=…`). Jira debe mandar el secreto en `X-Atlassian-Webhook-Token` o firmar el cuerpo en `X-Hub-Signature-256: sha256=…`. |
| Twilio por organización | Solo si se usa SMS o voz. | Cada organización declara sus números en el ajuste en vivo **`TWILIO_PHONE_NUMBERS`** (grupo `service_desk`, E.164 separados por comas, p. ej. `+34600000001,+34600000002`). Se pone desde Configuración dinámica → Service Desk, o con `PUT /api/v1/settings/runtime/service_desk/TWILIO_PHONE_NUMBERS`. La credencial `twilio.from_number` también vale. Cada organización puede tener su token: credencial `twilio.auth_token` (`PUT /api/v1/settings/integrations/twilio/auth_token`). Si no tiene, se usa el global `TWILIO_AUTH_TOKEN` (Twilio Console → Account → API keys & tokens → *Auth Token*). En Twilio Console → Phone Numbers → Active numbers: en *A call comes in*, `POST https://<dominio>/api/v1/sd/voice/webhook/twilio`; en *A message comes in*, `POST https://<dominio>/api/v1/sd/multichannel/inbound/sms`. **Cambio de comportamiento:** una llamada a un número que no declara ninguna organización, o que declaran dos, se rechaza (`<Reject/>`). Antes la atendía la instalación sin organización. Hay que declarar los números **antes** de desplegar. |
| `GEOIP_LOOKUP_ENABLED` | No. **Por defecto `true`.** Pon `false` para que ninguna IP salga a un tercero. | Activada, la IP pública de **cada inicio de sesión y cada refresco** se manda a `GEOIP_LOOKUP_URL` (por defecto `https://ipapi.co/{ip}/json/`), un tercero. Es una transferencia de datos personales, así que necesita base legal y aviso de privacidad, y el servidor necesita salida a Internet hacia ese servicio. La respuesta (país, región, ciudad, ASN) alimenta el riesgo de sesión: un cambio de país pesa 20 y uno de ASN pesa 25. Se guarda en caché por IP `GEOIP_CACHE_TTL_SECONDS` (86400), o 300 s si falla. Nunca se consultan IPs privadas ni reservadas. Revisa la cuota del proveedor. Si la apagas, solo se usan las cabeceras `cf-ipcountry`/`x-asn` del proxy. |
| `PROMETHEUS_MULTIPROC_DIR` | Si la API corre con más de un worker y `METRICS_ENABLED=1`. | Un directorio en el que se pueda escribir, **vaciado en cada arranque**. `docker-compose.yml` ya lo hace en el servicio `api` (`/tmp/prometheus-multiproc`, `rm -rf` + `mkdir` antes de uvicorn). Fuera de compose tienes que hacerlo tú. Sin él, cada worker tiene su propio registro y `/metrics` solo devuelve el del worker que atiende. El nombre tiene que ser exactamente `PROMETHEUS_MULTIPROC_DIR` y tiene que estar en el entorno del proceso, porque `prometheus_client` y `/metrics` la leen de ahí. El alias `METRICS_MULTIPROC_DIR` de `Settings` solo crea el directorio. Cada worker se da de baja al apagarse, y los que mueren sin apagarse bien (SIGKILL, OOM) se detectan en el siguiente scrape (solo en POSIX). |
| `WEBAUTHN_RP_ID` / `WEBAUTHN_ORIGIN` | **Sí** en staging/producción (con `localhost` no arranca). | `WEBAUTHN_RP_ID` es el dominio del frontend, sin esquema ni puerto (p. ej. `app.ejemplo.com`). `WEBAUTHN_ORIGIN` es el origen exacto que ve el navegador (p. ej. `https://app.ejemplo.com`). Las passkeys quedan atadas al RP ID: si lo cambias después, las ya registradas dejan de valer. |

**Licencias y hardware — fase 2 (uso real).** No hay variables de entorno nuevas
obligatorias. Cada empresa conecta sus fuentes en Licencias → Uso real → Fuentes
(administrador); las credenciales se guardan cifradas por empresa y **no** se leen
del entorno ni de la fila global. Antes de activar cada fuente:

- **Microsoft 365 / Intune:** registra una aplicación en Entra ID con permisos de
  *aplicación* `Organization.Read.All`, `User.Read.All`, `AuditLog.Read.All`
  (requiere Entra ID P1/P2), `Reports.Read.All` y, para Intune,
  `DeviceManagementManagedDevices.Read.All`; da consentimiento de administrador y
  crea un secreto. En el centro de administración de Microsoft 365 desactiva la
  ocultación de nombres en los informes.
- **Google Workspace:** cuenta de servicio con delegación de todo el dominio y los
  alcances `admin.directory.user.readonly`, `admin.reports.usage.readonly`,
  `admin.reports.audit.readonly` y `apps.licensing`; indica el administrador a
  suplantar y, si el cliente es `my_customer`, la opción `dominio`.
- **Okta:** token de API de un administrador de solo lectura.
- **Jamf Pro:** cliente de API con un rol que tenga «Read Computers».
- **Agente de inventario:** actualiza el agente para que envíe `serial_number`,
  `primary_user` y `software` en el check-in (campos opcionales).
- Salida a Internet del servidor (worker incluido) hacia `graph.microsoft.com`,
  `login.microsoftonline.com`, `admin.googleapis.com`, `licensing.googleapis.com`,
  `oauth2.googleapis.com` y las URL de Okta/Jamf de cada empresa (solo https).
- Beat: `alm-uso-sincronizar` (cada hora, :35) y `alm-uso-pasada-diaria` (07:40).
  Umbrales en Configuración dinámica, grupo `licencias_uso`. Para que la
  recuperación pida aprobación en la bandeja, crea un flujo para el tipo
  `license_reclaim`; sin flujo se aprueba desde la pantalla de Recuperación.

**Service desk — mejoras de mercado (16-11-2026, migración 174).** No hay
variables de entorno nuevas obligatorias. Los ajustes nuevos son en vivo
(Configuración dinámica → Service Desk): `SD_AUTONOMOUS_AGENT_MODE`,
`SD_AUTONOMOUS_DISABLED_PLAYBOOKS`, `SD_QUEUE_SLA_RISK_WEIGHT`,
`SD_DUPLICATE_*`, `SD_PRESENCE_TTL_SECONDS`, `SD_PORTAL_ASSISTANT_*` y
`SD_PASSWORD_RESET_SERVICE_ID`. Lo que hay que configurar fuera:

- **Slack (app interactiva).** En api.slack.com → *Your Apps* → la app de la
  empresa: *Slash Commands* → `/contecflow` con Request URL
  `https://<dominio>/api/v1/integrations-hub/slack/commands`; *Interactivity &
  Shortcuts* → activado, Request URL
  `https://<dominio>/api/v1/sd/channels/slack/interactions`. Copia el *Signing
  Secret* (Basic Information) en la credencial `slack.signing_secret` de la
  empresa (Ajustes → Credenciales) y pon el `SLACK_TEAM_ID` de la empresa
  (ajuste en vivo, grupo `ai`). Sin firma válida, 403. El servidor necesita
  salida a `hooks.slack.com` para actualizar las tarjetas.
- **WhatsApp Business (Meta Cloud API).** En developers.facebook.com → la app
  de WhatsApp: copia el *Phone number ID*, crea un token permanente de un
  usuario del sistema con `whatsapp_business_messaging`, copia el *App
  Secret* (Configuración → Básica) e inventa un *verify token*. Guárdalos en
  Ajustes → Credenciales → **WhatsApp Business** (`phone_number_id`,
  `access_token`, `app_secret`, `verify_token`; `api_version` opcional,
  `v20.0`). Después, en WhatsApp → Configuración → Webhook: Callback URL
  `https://<dominio>/api/v1/sd/channels/whatsapp/webhook`, el mismo verify
  token, y suscribe el campo `messages`. Un número que declaren dos empresas
  no es de ninguna (403). El servidor necesita salida a `graph.facebook.com`.
- **Teams**: lo de siempre (`TEAMS_BOT_APP_ID`, `TEAMS_TENANT_ID`); los
  comandos nuevos del service desk no piden nada más.
- **Aviso de colisión entre procesos**: usa el mismo Redis (`REDIS_URL`) que
  los avisos en tiempo real; sin Redis solo ve a quien está en el mismo
  proceso.
- **Aprobación multinivel del catálogo**: crea en Aprobaciones un flujo para
  el tipo «Petición del catálogo» (`catalog_request`) **antes** de pasar un
  servicio a *Flujo de aprobaciones* (sin flujo activo no se puede guardar).
- **Migración 174**: cifra la configuración de los proveedores de descubrimiento
  con la clave de cifrado de la instalación (la misma de las credenciales) y
  convierte los festivos de `sd_sla_holidays` en un calendario «Festivos
  generales» por empresa. Hazla con la clave de cifrado de producción cargada.

- **Traducción en tiempo real (16-11-2026)**:
  - Nada obligatorio: viene **apagada** por empresa.
  - Para activarla: Ajustes → Sistema → Traducción (ajustes en vivo del grupo `traduccion`; los valores por defecto están en `.env.example`, `TRANSLATION_*`).
  - Con el proveedor `ai` usa el proveedor de IA ya configurado y su tope diario (`AI_DAILY_BUDGET_USD`).
  - Para DeepL o Azure AI Translator:
    - Cada empresa pone su clave en esa misma pantalla, como credenciales cifradas `deepl` (`api_key`; una clave `:fx` va al plan Free) o `azure_translator` (`api_key`, `region` y, si hace falta, `endpoint`). Nunca se usan las de otra empresa ni las del entorno.
    - El servidor necesita salida https a `api.deepl.com`/`api-free.deepl.com` o a `api.cognitive.microsofttranslator.com` (o al endpoint propio).
    - Si se quiere que su gasto cuente para el tope, hay que fijar `TRANSLATION_COST_PER_MILLION_CHARS_USD` con el precio contratado.
  - Hay una tarea nueva de beat, `purgar-cache-de-traducciones` (diaria a las 03:25).
- **Migración 175**: tablas nuevas y columnas que admiten nulos; no mueve datos.

Las que son variables de entorno están en `.env.example`, con su comentario
(`PROMETHEUS_MULTIPROC_DIR` comentada a propósito: basta con que exista, aunque
vacía, para que `prometheus_client` entre en modo multiproceso).
`tests/test_env_example_sincronizado.py` vigila que no vuelvan a faltar. Un
`.env` creado antes no las tiene: añádelas a mano.


### B.2 Migraciones

Con compose las aplica el servicio `migrate` (`alembic upgrade head` y después
`python -m app.db.rls`). Fuera de compose, lanza esos mismos dos comandos con el
dueño del esquema (`DATABASE_MIGRATIONS_URL`, o `DATABASE_URL` si no está).
`setup.sh` también llama a `alembic upgrade head`.

| Revisión | Qué hace | ¿Lenta o con bloqueos en PostgreSQL? |
|---|---|---|
| 158 `obligaciones_asc606_precio_y_metodo` | Añade a `rev_obligations` tres columnas que admiten nulos: `method`, `standalone_price` y `notes`. | Rápida: solo cambia el catálogo. |
| 159 `jira_una_sola_configuracion` | Añade `sd_jira_configs.usar_para_tareas` (`NOT NULL DEFAULT false`). Pasa la conexión Jira de tareas de `app_settings` (`jira_url`, …) a una fila de `sd_jira_configs` y borra esos `app_settings`. Las filas globales solo se asignan si hay una única organización. | Rápida. El default constante no reescribe la tabla (PG ≥ 11). Recorre pocas filas. |
| 160 `mfa_un_solo_sistema` | Añade `users.mfa_verified_at`. Copia el TOTP de `mfa_configs` a `users` y rehace `mfa_backup_codes` por `user_id`. **Borra `mfa_configs`**. Es irreversible. | Rápida (tablas pequeñas). `DROP TABLE` y la recreación de `mfa_backup_codes` toman un bloqueo exclusivo breve. |
| 161 `jira_hub_a_jira_config` | Pasa las credenciales Jira de `integration_configs` (tipo `jira`) a `sd_jira_configs`. Desactiva la fila antigua y borra su token. | Rápida (pocas filas). |
| 162 `perfil_semantico_por_organizacion` | Rellena `sem_profiles.organization_id` con la organización del usuario. Quita el único de `user_id` y crea el único `(user_id, organization_id)`. | `UPDATE` de toda la tabla. El índice y el único se crean **sin** `CONCURRENTLY`, así que bloquean las escrituras en `sem_profiles` mientras se construyen. Es una fila por usuario: en la práctica, segundos. |
| 163 `indices_de_claves_ajenas_calientes` | Crea 12 índices en claves ajenas muy filtradas (`sd_tickets.requester_client_id`, `tasks.parent_task_id`, …). | `CREATE INDEX CONCURRENTLY IF NOT EXISTS` dentro de `autocommit_block`. **No bloquea** lecturas ni escrituras, pero lee la tabla dos veces y espera a que acaben las transacciones abiertas. En tablas grandes, minutos. |
| 164 `paridad_postgres_e_indices_de_claves_ajenas` | (1) Pone a NULL los `budgets.cliente_id` huérfanos y crea la clave ajena `fk_budgets_cliente_id_clients` (`ON DELETE SET NULL`). (2) Crea hasta 319 índices: 2 de paridad en `budgets` y 317 en claves ajenas. | (1) `ALTER TABLE … ADD CONSTRAINT` sin `NOT VALID`: mientras valida, bloquea las escrituras en `budgets` (y en `clients`), lo que dura proporcional a `budgets`. (2) Igual que la 163, `CONCURRENTLY`, sin bloquear, uno tras otro. **Es la más lenta**: el tiempo total es la suma de leer cada tabla afectada. |
| 165 `motor_de_politicas_y_flujos` | Motor común de políticas (tarea #26). Crea `politicas`, `politica_reglas`, `tablas_de_referencia`, `tabla_de_referencia_filas`, `politica_evaluaciones` y `approval_request_steps`. Añade `approval_steps.kind` (`approve`/`inform`, por defecto `approve`) y `approver_level`, `approval_workflows.diagrama`, `approval_requests.contexto`, `approval_decisions.step_ref` y `expenses.country`/`city`. | Rápida: tablas nuevas y columnas que admiten nulos o llevan un default constante. |
| 166 `gastos_sobre_el_motor_de_politicas` | Gastos sobre el motor (tarea #27). Añade `expenses.attendees` y `trip`, `expense_attachments.document_type`, `users.grade` y `tablas_de_referencia.uso`. **Datos:** cada fila de `expense_policies` pasa a ser una política publicada del dominio `gastos` con el mismo comportamiento (tope por gasto o diario, justificante, justificación) y después **borra `expense_policies`**. **Cambio de comportamiento:** los importes se comparan en la moneda por defecto de la empresa (`DEFAULT_CURRENCY`), convirtiendo al tipo de cambio de la fecha del gasto; antes se comparaba la cifra sin mirar la moneda. El `downgrade` rehace `expense_policies` desde las políticas migradas. | Rápida (pocas filas). |
| 167 `ausencias_reglas_turnos_y_documentos` | Ausencias gobernadas por reglas (tarea #25). Tablas nuevas de tipos de ausencia y de documento, requisitos, turnos, patrones y cuadrante, huecos y reservas de cupo (lista de espera), documentos, eventos y acceso especial. En `absences`, `type` pasa de enum a `VARCHAR(50)` (se borra el tipo `absencetype`), el estado gana `waitlisted` y entran `absence_type_id`, `shift_id`, `substitute_id`, `unit`, `amount`, los medios días, `hours` y `requested_at`. **Datos:** en cada empresa crea los siete tipos anteriores (mismas claves) y tres tipos de documento, y enlaza cada ausencia con su tipo. **No crea cupos ni requisitos**: los configura cada empresa, o «Cargar ejemplos», que nunca se aplica sola. | `ALTER TYPE … ADD VALUE` va en `autocommit_block`. El cambio de tipo de `absences.type` **reescribe la tabla** con bloqueo exclusivo, y sus tres índices nuevos se crean sin `CONCURRENTLY` (bloquean las escrituras en `absences`). Proporcional al tamaño de `absences`: en la práctica, segundos. |
| 168 `indice_unico_procesos_bpmn` | Índices únicos `uq_bpmn_processes_org_key` sobre (`organization_id`, `key`) y `uq_bpmn_processes_key_global` sobre `key` donde `organization_id IS NULL`. **Antes** renombra las claves duplicadas: conserva la de la fila más antigua y añade `_dup_<n>` a las demás. No borra ni desactiva nada, y el sufijo no se revierte en el `downgrade`. | `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS` en `autocommit_block`: no bloquea (mismas precauciones que la 163 y la 164, abajo). Tabla pequeña. |
| 169 `bpmn_decisiones_y_codigos_de_error` | Añade `bpmn_instance_steps.wait_kind` (lo rellena en los pasos existentes) y `bpmn_instances.error_code`/`error_params`. **Cambio de comportamiento:** una compuerta exclusiva sin condiciones pasa a ser una decisión que toma una persona desde la bandeja; antes la instancia fallaba en ella. | Rápida: columnas que admiten nulos y un `UPDATE` de los pasos. |
| 171 `alm_uso_real` | Licencias y hardware, fase 2 (uso real). Crea `alm_uso_conexiones`, `alm_uso_sincronizaciones`, `alm_uso_evidencias`, `alm_uso_mapeos`, `alm_uso_derechos`, `alm_uso_niveles`, `alm_uso_ajustes`, `alm_uso_recuperaciones` y `alm_software_no_controlado`. No toca tablas existentes. Depende de la 170 (`alm_titulares_ciclo_y_costes`). | Rápida: solo tablas nuevas. |
| 175 `traduccion_en_tiempo_real` | Traducción en tiempo real. Crea `translation_cache`, `message_translations`, `translation_glossary_terms` y `sd_kb_article_translations`. Añade columnas que admiten nulos: `sd_tickets.language`, `system_template` y `system_params`, `sd_ticket_comments.language` y `sd_channel_messages.language`. No mueve datos. El downgrade borra las tablas, las columnas, los ajustes `TRANSLATION_*` y las credenciales `deepl`/`azure_translator`. | Rápida: tablas nuevas y columnas que admiten nulos. |

Sobre los índices `CONCURRENTLY` (163 y 164):

- Lanza la migración en una hora de poca carga. Una transacción larga abierta
  hace esperar a cada índice.
- Si un `CREATE INDEX CONCURRENTLY` se corta (timeout, cancelación), deja un
  índice **INVALID** con el nombre ya ocupado. La migración se salta los
  nombres que ya existen, así que repetirla **no** lo arregla. Compruébalo
  después:
  `SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid;`
  Bórralo con `DROP INDEX CONCURRENTLY <nombre>;` y vuelve a lanzar `alembic upgrade head`.
- En SQLite no hay `CONCURRENTLY` y los índices se crean sin más.


### B.3 Arranque

1. `./scripts/deploy.sh`, o `docker compose --profile app up -d`. Sin compose,
   levanta API, worker y beat después de que hayan terminado las migraciones y
   `python -m app.db.rls`.
2. Si el arranque falla, el mensaje dice qué variable falta (A.3 y B.1).
3. Proxy: igual que en A.6.

### B.4 Volver atrás

Restaura la copia de B.0 con `scripts/restore.sh`. Un `alembic downgrade` no
devuelve el estado anterior en todas las revisiones: la 160 no recupera
`mfa_configs` y la 168 no quita los sufijos `_dup_<n>`. Las revisiones sin
`downgrade` real están en el README («5. Database and migrations»).

## C. Pruebas de humo después de desplegar


1. `GET /health` → 200. `GET /ready` → 200, con `db` y `redis` en `ok`.
2. `python -m alembic current` → la misma revisión que `python -m alembic heads` (B.0). La consulta de
   índices INVALID no devuelve filas.
3. Inicia sesión con un usuario normal y con uno que tenga passkey. La passkey
   tiene que funcionar con el `WEBAUTHN_RP_ID` nuevo.
4. `curl -H "Authorization: Bearer $METRICS_AUTH_TOKEN" https://<dominio>/metrics`
   → 200. Sin la cabecera → 401. Con varios workers, repite el scrape: los
   contadores no deben bajar de una vez a otra.
5. Correo entrante: manda un correo de prueba a la dirección de soporte (o
   haz `POST /api/v1/sd/inbound-email` con el secreto) → se crea un ticket en
   la organización de esa `SD_INBOUND_ADDRESS`. Con un secreto erróneo → 403.
6. Stripe: Dashboard → Webhooks → *Send test event* →
   `checkout.session.completed` → 200 (`applied: false` si no hay factura).
7. Jira: rota el secreto y haz un cambio en una incidencia enlazada. La tarea
   se actualiza. Una petición sin token → 403.
8. Slack/Teams: un slash command o un mensaje al bot desde el workspace o
   tenant vinculado responde como el usuario de esa organización.
9. Twilio: llama a un número declarado. Se oye el saludo de la organización y
   `GET /api/v1/sd/voice/sessions`, con un admin de esa organización, muestra la sesión. Manda un SMS
   al mismo número → se abre un ticket en esa organización. Una llamada a un
   número que no está en `TWILIO_PHONE_NUMBERS` se rechaza.
10. GeoIP (activada por defecto; sáltalo si pusiste `GEOIP_LOOKUP_ENABLED=false`):
    tras un inicio de sesión desde una IP pública, esa sesión queda con
    `country_code` y `city` rellenos.
