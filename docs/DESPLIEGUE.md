# Despliegue de Contecflow PSA

Guía para quien despliega: **A**, un entorno nuevo desde cero; **B**, la
actualización de uno existente hasta la cabeza actual de migraciones; **C**,
pruebas de humo. Todo sale del código (`app/core/config.py`,
`app/core/config_groups/*`, `.env.example`, `docker-compose.yml`, `setup.sh`,
`scripts/deploy.sh`, `scripts/backup.sh`, `alembic/versions/`). Rutas de la API
con el prefijo `/api/v1`. Lo que no se ha podido comprobar en ejecución lo dice.

Cabeza de migraciones al revisar esta guía (2026-11-23):
`205_portal_usuarios` (157 revisiones, una sola cadena; `scripts/migrar.py` se
para si hay dos cabezas). La fuente de verdad es siempre `python -m alembic heads`.

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
5. Aislamiento en la base (RLS): `APP_DB_USER` y `APP_DB_PASSWORD` (los genera
   `setup docker`, `scripts/docker_stack.py`). El servicio `migrate` ejecuta
   `python -m app.db.rls`, que crea ese rol sin superusuario ni `BYPASSRLS` y
   aplica las políticas. `api`, `worker` y `beat` conectan con ese rol; las
   migraciones, con el dueño (`POSTGRES_USER`). Auditoría 22-11-2026: el compose
   ya no cae al superusuario (sin `APP_DB_PASSWORD` la API no conecta) y en
   `staging`/`production` la API no arranca si RLS no está armado
   (`RLS_REQUIRED`, sin fijar = exigido ahí). En local, `setup.sh` y `setup.bat`
   preparan el rol igual (`scripts/rol_de_aplicacion.py`) cuando `DATABASE_URL`
   es Postgres.
6. Sesiones sin empresa (`TENANT_SESION_SIN_CONTEXTO`): `cerrar` por defecto
   desde el 23-11-2026: una sesión sin empresa, sin superadmin y sin contexto de
   sistema declarado falla (`TenantIsolationError`) y RLS no devuelve filas. Las
   93 rutas anónimas y las `SessionLocal()` a mano declaran su contexto
   (`docs/seguridad/rutas_anonimas.md`). `avisar` solo sirve para localizar un
   sitio sin declarar (un WARNING «sesión sin contexto de empresa» por sitio);
   no lo uses en producción. Un script propio que abra `SessionLocal()` debe
   declarar su contexto: `declarar_sistema(db, "motivo")`.

7. Las variables de integraciones (correo entrante, métricas, Stripe, GeoIP,
   passkeys…) y los ajustes por organización están en B.1. La lista completa,
   con su valor por defecto, está en docs/REFERENCIA_DE_AJUSTES.md.
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
configura cada empresa: docs/APPROVAL_ENGINE.md (anexo, §22 bis a §22 quater) y, en el README,
§22 Ausencias, §32 Finanzas (gastos) y §36 Aprobaciones.

## B. Actualizar un entorno existente

### B.0 Antes de empezar

1. **Copia de seguridad** de la base y de los ficheros: `./scripts/backup.sh`
   (`pg_dump -Fc` comprobado con `pg_restore --list`, el volumen S3 en tar y un
   manifiesto con SHA-256 y la revisión de Alembic). Se restaura con
   `./scripts/restore.sh <copia> --borra-lo-que-hay`. `scripts/deploy.sh` ya
   hace la copia. Las migraciones 159, 160, 161, 166 y 167 mueven datos (y, de la 170 en adelante, la 170, 177, 178, 179, 182, 183, 185, 186 y 188; la 186 además reescribe tablas). La 160
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

  - Viene **activada** en cada empresa: con el proveedor `ai` traduce en cuanto hay un proveedor de IA configurado.
  - Para apagarla o cambiar el proveedor: Ajustes → Sistema → Traducción (ajustes en vivo del grupo `traduccion`; los valores por defecto están en `.env.example`, `TRANSLATION_*`).
  - Con el proveedor `ai` usa el proveedor de IA ya configurado y su tope diario (`AI_DAILY_BUDGET_USD`).
  - Para DeepL o Azure AI Translator:
    - Cada empresa pone su clave en esa misma pantalla, como credenciales cifradas `deepl` (`api_key`; una clave `:fx` va al plan Free) o `azure_translator` (`api_key`, `region` y, si hace falta, `endpoint`). Nunca se usan las de otra empresa ni las del entorno.
    - El servidor necesita salida https a `api.deepl.com`/`api-free.deepl.com` o a `api.cognitive.microsofttranslator.com` (o al endpoint propio).
    - Si se quiere que su gasto cuente para el tope, hay que fijar `TRANSLATION_COST_PER_MILLION_CHARS_USD` con el precio contratado.
  - Hay una tarea nueva de beat, `purgar-cache-de-traducciones` (diaria a las 03:25).
- **Migración 175**: tablas nuevas y columnas que admiten nulos; no mueve datos.

**Canales en tiempo real (17-11-2026, migración 179).** Sin variables de
entorno nuevas obligatorias. Ajustes en vivo nuevos (Configuración dinámica →
Service Desk): `SD_SLACK_TICKET_CHANNEL`, `SD_SLACK_INTAKE_CHANNELS`,
`SD_CHANNEL_MAX_ATTACHMENT_MB` (16), `SD_PORTAL_ASSISTANT_AI` (activado) y
`SD_PORTAL_ASSISTANT_MAX_TOKENS` (700). Lo que hay que configurar fuera:

- **Slack: hilos ↔ ticket (Events API).** En api.slack.com → *Your Apps* → la
  app de la empresa:
  - *OAuth & Permissions* → **Bot Token Scopes**: `chat:write` (tarjetas y
    respuestas en hilos), `channels:history`, `groups:history` y
    `mpim:history` (leer los mensajes de los canales públicos, privados y de
    grupo donde esté el bot), `files:read` (bajar adjuntos), `files:write`
    (subir adjuntos del ticket al hilo), `users:read` y `users:read.email`
    (casar el autor por correo). Además de `commands`, que ya tenía. Reinstala
    la app en el workspace y copia el **Bot User OAuth Token** (`xoxb-…`) en
    la credencial cifrada **`slack.bot_token`** de la empresa (Ajustes →
    Credenciales → Slack). No va en `.env`.
  - *Event Subscriptions* → activado, Request URL
    `https://<dominio>/api/v1/sd/channels/slack/events` (Slack la verifica con
    un `url_verification` firmado: tiene que estar guardado antes el signing
    secret). **Subscribe to bot events**: `message.channels`, `message.groups`
    y `message.mpim`.
  - Invita al bot (`/invite @app`) a los canales de avisos y de entrada y pon
    sus ids en `SD_SLACK_TICKET_CHANNEL` / `SD_SLACK_INTAKE_CHANNELS`.
  - Requisitos: `SLACK_TEAM_ID` de la empresa (sin él los eventos dan 403) y
    salida https a `slack.com` y `files.slack.com`. Los eventos se procesan en
    el worker (Celery); sin cola, en la propia petición.
- **WhatsApp: adjuntos y plantilla.** El token ya configurado sirve para
  bajar y subir medios (`whatsapp_business_messaging`). Para escribir pasadas
  24 h del último mensaje del cliente, crea y aprueba en el *WhatsApp Manager*
  una plantilla de categoría *Utility* con **dos variables de cuerpo**
  (`{{1}}` número del ticket, `{{2}}` texto) y pon su nombre e idioma en
  Credenciales → WhatsApp Business (`template_name`, `template_language`). El
  servidor necesita salida https a `graph.facebook.com` y a los hosts de medios
  de Meta (`*.fbsbx.com`, `*.whatsapp.net`, `*.fbcdn.net`). Para el antivirus
  de los adjuntos, `CLAMAV_ENABLED=true` y clamd accesible (`CLAMAV_HOST`/
  `CLAMAV_PORT` o `CLAMAV_SOCKET`).
- **Chat inmediato**: con más de un proceso de API hace falta `REDIS_URL` (los
  avisos del chat van por Redis, como los demás del WebSocket); el proxy tiene
  que dejar pasar WebSocket a `/api/v1/ws/` (ya lo necesitaba).
- **Asistente del portal con IA**: necesita un proveedor de IA de la empresa;
  opcionalmente, en *Hub de IA → Por función*, la ruta «Asistente del portal»
  (`portal_assistant`). Sin proveedor, el asistente sigue con el
  reconocimiento por palabras y avisa al cliente.
- **Migración 179**: columnas que admiten nulos en `sd_channel_conversations`,
  `sd_channel_messages` y `sd_portal_assistant_actions`; rellena
  `last_inbound_at` de las conversaciones existentes con su último mensaje
  entrante.

**Ronda 2 de la auditoría 22-11-2026 (informe 01), 23-11-2026:**
- **Permisos por capacidad en toda la API (M9)**: ninguna ruta se guarda ya por rol;
  todas por capacidad del catálogo, con los mismos roles que antes (ver
  `docs/seguridad/guardas_por_capacidad.md`). Sin migración ni variable. Cambio visible: el
  superadmin pasa también por las guardas que eran a mano (observabilidad predictiva, ABAC,
  gobierno de IA) y el 403 trae el código `capacidad_requerida` en vez de `roles_requeridos`
  o `solo_admin`. Las 4 rutas OLAP de `/analytics/olap/*` piden `analitica.ver` (admin y PM).
- **Arranque local (`setup.sh`/`setup.bat start`)**: la API escucha en `127.0.0.1`. Para
  abrirla a la red local, `BACKEND_HOST=0.0.0.0`. Docker no cambia.
- **`docker-clean`**: baja todos los perfiles y CONSERVA los volúmenes externos de
  PostgreSQL y S3 (lo dice al terminar, con el `docker volume rm` para borrarlos a propósito).
- **Prometheus**: sin `--web.enable-lifecycle`; para recargar su configuración,
  `docker compose restart prometheus`.
- **Imagen**: sin `curl`; `--build-arg PYTHON_IMAGE=python:3.12-slim@sha256:<digest>` fija la base.
- **`ACCESS_TOKEN_EXPIRE_MINUTES`**: la vida real es min(EXPIRE, `ACCESS_TOKEN_MAX_MINUTES`=30);
  `.env.example` ya dice 30. Un `.env` antiguo con 60 se recorta a 30: alinéalo.
- **Log de errores**: en staging/producción la traza no lleva el texto de la excepción sin
  redactar (correos, teléfonos, IBAN).
- **Scripts retirados**: `scripts/start.sh`, `start.bat`, `clean_and_start.sh`,
  `test_and_report.sh`, `update_endpoints_table.sh`, `smoke_test_simple.py`. La entrada es
  `setup.sh`/`setup.bat`.

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
| 170 `alm_titulares_ciclo_y_costes` | Licencias y hardware, fases 1 y 3: `alm_license_assignments` se amplía en el sitio (mismos ids) y pasa a ser la asignación universal (recurso licencia o activo; titular persona, proyecto, departamento, cliente o dispositivo; modo, estado, intervalo, aprobación, coste). **Renombra columnas** (`user_id` → `holder_user_id`, `project_id` → `holder_project_id`, `asset_id` → `holder_asset_id`, `expires_at` → `valid_to`) y convierte `is_active` en `status`. Migra los datos: cada activo con `assigned_to_id` recibe su asignación vigente. | Con datos: renombra y reescribe asignaciones y activos (tablas pequeñas en la práctica); en una hora de poca carga. |
| 171 `alm_uso_real` | Licencias y hardware, fase 2 (uso real). Crea `alm_uso_conexiones`, `alm_uso_sincronizaciones`, `alm_uso_evidencias`, `alm_uso_mapeos`, `alm_uso_derechos`, `alm_uso_niveles`, `alm_uso_ajustes`, `alm_uso_recuperaciones` y `alm_software_no_controlado`. No toca tablas existentes. Depende de la 170 (`alm_titulares_ciclo_y_costes`). | Rápida: solo tablas nuevas. |
| 172 `alm_altas_bajas_y_autoservicio` | Licencias y hardware, fase 4: tablas nuevas `alm_kits`, `alm_kit_elementos`, `alm_propuestas_de_kit`, `alm_bajas`, `alm_devoluciones`, `alm_items_de_catalogo` y `alm_peticiones`. No toca tablas existentes; idempotente. | Rápida: solo tablas nuevas. |
| 173 `proyectos_planificador_y_hub` | Proyectos: columnas nuevas en `tasks` (progreso, restricciones y camino crítico), `task_dependencies` (`link_type`, `note`), `gantt_baselines` (`is_current`; `schedule_snapshot` admite NULL), `saved_filters` y `template_tasks`; tablas nuevas `gantt_baseline_tasks`, `evm_snapshots` (curva S diaria), `portfolio_criteria`, `portfolio_gates`, `portfolio_proposals` y las dependencias de tareas de plantilla. | Rápida en general: columnas que admiten nulos e índices nuevos; algún `UPDATE` pequeño de rellenado. |
| 174 `service_desk_mercado` | Service Desk, mejoras de mercado: tablas nuevas `sd_service_item_tasks` (pasa a ellas el JSON `fulfillment_tasks`, que queda vacío), `sd_sla_rules`, `sd_ola_targets`, `sd_ticket_lifecycles` (+ estados y transiciones), `sd_channel_conversations`, `sd_channel_messages`, `sd_ci_classes` y `sd_portal_assistant_actions`; columnas nuevas como `sd_service_items.approval_mode`. | Rápida: tablas nuevas y columnas que admiten nulos; copia las tareas de ejecución existentes. |
| 175 `traduccion_en_tiempo_real` | Traducción en tiempo real. Crea `translation_cache`, `message_translations`, `translation_glossary_terms` y `sd_kb_article_translations`. Añade columnas que admiten nulos: `sd_tickets.language`, `system_template` y `system_params`, `sd_ticket_comments.language` y `sd_channel_messages.language`. No mueve datos. El downgrade borra las tablas, las columnas, los ajustes `TRANSLATION_*` y las credenciales `deepl`/`azure_translator`. | Rápida: tablas nuevas y columnas que admiten nulos. |
| 177 `portal_idiomas_restos` | Portal en 8 idiomas: `sd_ticket_comments.system_template` y `system_params` (comentarios automáticos con plantilla, pintados en el idioma de cada lector). Datos: añade el canal `portal` a cada valor guardado no vacío de `TRANSLATION_CHANNELS` en `app_settings`. | Rápida: columnas que admiten nulos y un `UPDATE` de pocas filas de `app_settings`. |
| 178 `externos_como_internos` | Externos como internos: columnas nuevas en `subcontractor_workers` (`has_access`, `access_until`, `internal_owner_id`, `access_expiry_notified_at`), `subcontractor_assignments` (`project_member_id`, `is_active`, `ended_at`, `consumption_alert_pct`) y `subcontractor_timelogs` (`worker_id`, `source`). Datos: `access_until` = `available_until` en los trabajadores existentes. | Rápida: tablas pequeñas, columnas que admiten nulos y rellenado de pocas filas. |
| 179 `canales_tiempo_real` | Canales en tiempo real: `sd_channel_conversations` (`client_read_at`, `agent_read_at`, `last_inbound_at`), `sd_channel_messages` (`ticket_comment_id`, `attachment_document_id`, `delivery_status`) y `sd_portal_assistant_actions.engine`. Rellena `last_inbound_at` con el último mensaje entrante. | Rápida: columnas que admiten nulos y un `UPDATE` sobre las conversaciones de canal. |
| 180 `turnos_y_ausencias_por_horas` | Horario efectivo: tablas nuevas `jornadas_laborales`, `asignaciones_de_jornada` y `movimientos_de_saldo`; columnas nuevas en `users` (`office_id`, `hire_date`, `employment_type`), `turnos` (`tramos`, `pausa_minutos`) y `tipos_de_ausencia` (modo por horas). | Rápida: tablas nuevas y columnas que admiten nulos o con valor por defecto. |
| 181 `versiones_avisos_y_catalogo` | Tabla nueva `portal_content_translations`: versión revisable (`draft` → `in_review` → `published` / `rejected`) de un aviso o del nombre y la descripción de una categoría o servicio del catálogo en un idioma del portal. Sin datos. | Rápida: solo una tabla nueva. |
| 182 `comentarios_de_canal_y_festivos_por_empresa` | `sd_ticket_comments.edited_at` y `retracted_at` (mensajes editados o borrados en su canal de origen). Datos: copia cada festivo sin empresa a cada empresa que no lo tenga y borra el original sin empresa. **El `downgrade` no deshace la copia de festivos.** | Rápida: columnas que admiten nulos y copia de pocas filas de `holidays`. |
| 183 `contacto_principal_correlacionado` | Contacto principal de la ficha de cliente correlacionado con `client_contacts`: por cada cliente activo crea el contacto principal que falte, deja un único principal y hace que la ficha (`contact_*`) lo refleje. Solo datos, más un índice. | Proporcional al nº de clientes y contactos; en una hora de poca carga. |
| 184 `horas_extra` | Tablas nuevas `config_horas_extra`, `peticiones_de_horas_extra`, `eventos_de_horas_extra` y `presupuestos_de_horas_extra`. No crea configuración: sin fila el módulo está desactivado y la imputación se comporta como antes. El `downgrade` borra las cuatro tablas con sus datos. | Rápida: solo tablas nuevas. |
| 185 `ajustes_generales_una_fuente` | Solo datos: `/settings/general` pasa a leer y escribir las claves de ejecución `DEFAULT_CURRENCY`, `DEFAULT_TIMEZONE`, `DEFAULT_LANGUAGE` y `DEFAULT_WORKING_HOURS_PER_DAY`; copia el valor que una empresa cambió en las filas `app_settings` antiguas (`currency`, `timezone`, `language`, `work_hours_per_day`) a su clave de ejecución si aún no tenía una. No copia las filas globales. | Rápida: pocas filas de `app_settings`. |
| 186 `catalogos_de_tipo_sector_y_categoria` | `projects.project_type`, `clients.industry` y `expenses.category` dejan de ser enums de BD (`projecttype`, `clientindustry`, `expensecategory`) y guardan la clave (`VARCHAR(50)`) de su catálogo editable por empresa. Tablas nuevas `custom_client_industries` y `custom_expense_categories`, con sus semillas globales; siembra `custom_project_types` si está vacía. | **Lenta en PostgreSQL:** `ALTER COLUMN ... TYPE VARCHAR(50) USING ...::text` reescribe `projects`, `clients` y `expenses` con bloqueo exclusivo: en una hora de poca carga. |
| 188 `asistente_de_reuniones` | Asistente de reuniones: `ai_meetings.status` pasa a 30 caracteres y a los estados nuevos (`processing` → `procesando`, `done` → `lista`, `failed` → `error`), con columnas de origen, plataforma, bot, consentimiento, retención de audio y transcripción, acta y llamada del chat; `ai_meeting_actions.ticket_id`; tablas nuevas `ai_meeting_participants`, `ai_meeting_segments`, `ai_meeting_translations`, `ai_meeting_audio`, `ai_meeting_events` y `ai_meeting_user_prefs`. | Rápida en general: tablas nuevas y un `UPDATE` de los estados de `ai_meetings`. |
| 189 `proveedores_y_externalizacion` | Proveedores y externalización: columnas nuevas en `subcontractors` (tipo, modalidades, ciclo de vida, riesgo, revisión, baja), `tasks` (`supplier_id`, `supplier_work_package_id`) y `subcontractor_invoices` (`created_by`, `contract_id`); tablas nuevas `supplier_contracts`, `supplier_services`, `supplier_work_packages`, `supplier_pricing_lines`, `supplier_reports`, `supplier_statements`, `supplier_usage_records`, `supplier_documents`, `supplier_risk_assessments`, `supplier_access_grants` y catálogos propios. | Rápida: tablas nuevas y columnas que admiten nulos. |
| 190 `cmdb_software_y_vulnerabilidades` | CMDB de software: 15 tablas nuevas (`sw_products`, `sw_versions`, `sw_components`, `sw_sbom_imports`, `sw_product_licenses`, `sw_instances`, `sw_instance_relations`, `sw_config_snapshots`, `sw_baselines`, `sw_vulnerabilities`, `sw_vulnerability_affects`, `sw_findings`, `sw_vuln_exceptions`, `sw_sync_runs`, `sw_config`). No toca tablas existentes; el `downgrade` las borra con sus datos. | Rápida: solo tablas nuevas. |
| 191 `proveedores_portal_y_aprobacion` | Portal del proveedor, aprobación por importe y fuentes de medición: solo columnas nuevas (`subcontractor_workers.supplier_portal`, `supplier_services.metering_*`, `supplier_usage_records.detail` y `source_system`, `supplier_reports.report_type` y `attachments`, entre otras); ninguna tabla nueva. | Rápida: columnas que admiten nulos o con valor por defecto. |
| 192 `textos_por_clave_y_cierre` | Textos guardados por clave: `sd_ticket_history.new_value_key` y `new_value_params`, `sd_autonomous_playbook_executions.resolution_note_key` y `resolution_note_params`. El texto escrito sigue como respaldo. | Rápida: columnas que admiten nulos. |
| 193 `clientes_internos` | Clientes internos (showback/chargeback): `clients.kind` (`externo` por defecto, `NOT NULL`) e `internal_type`, vínculos con la estructura (`department_id`, `area_id`, `cost_center_id`, `group_organization_id`), `business_owner_id` y columnas de finanzas internas (`finance_mode`, `cost_method`, `internal_rate_table_id`, `transfer_markup_pct`…). Las filas existentes quedan como externas. | Rápida: columnas con valor por defecto constante y un índice. |
| 194 `indice_de_riesgo` | Índice de riesgo y vulnerabilidades: tablas nuevas `sw_risk_snapshots`, `sw_compensating_controls`, `sw_exploit_events`, `sw_saved_views` y `sw_risk_alert_log`; columnas nuevas `sw_config.risk_settings`, `sw_findings.detected_by`, `exploit_attempts`, `last_exploit_at`, `risk_points` y `sw_instances.exposure_source`. Idempotente; el `downgrade` borra lo nuevo con sus datos. | Rápida: tablas nuevas y columnas que admiten nulos. |
| 195 `flujo_de_demanda` | Flujo de demanda configurable por empresa: 8 tablas nuevas (`demand_request_types`, `demand_flows`, `demand_requests`, `demand_step_states`, `demand_transitions` con hash encadenado, `demand_field_versions`, `demand_documents`, `demand_comments`), todas con `organization_id`. | Rápida: solo tablas nuevas. |
| 196 `auditoria_2026_11_22` | (1) Columnas: `collaboration_audit_events.hash_version` (`NOT NULL DEFAULT 'v1'`), `client_documents.signed_pdf_sha256`, `collaboration_webhooks.secret_token_hash` (se rellena con el SHA-256 del secreto existente) y `automation_events.idempotency_key` con índice único `uq_automation_events_org_idempotency` (empresa, clave). (2) **Borra** 6 tablas sin modelo ni uso: `ai_anomalies`, `oauth_states`, `subcontractor_worker_skills`, `imputation_snapshots`, `whatif_tasks`, `wiki_export_jobs` (0 filas medidas en local; el `downgrade` las recrea vacías). (3) `ondelete` en las 171 claves ajenas a `users.id` que no lo tenían: 159 `SET NULL`, 8 `RESTRICT` (autorías obligatorias: aprobaciones, evaluaciones, votos del CAB, horas de ticket, planes de desarrollo, 360) y 4 `CASCADE` (datos de la propia persona). **Cambio de comportamiento:** el borrado definitivo de un usuario con historial protegido lo anonimiza (supresión RGPD) en vez de borrarlo. | PostgreSQL: suelta y recrea cada clave con su nombre (valida las filas: segundos con volúmenes normales). SQLite: recrea las ~140 tablas afectadas (`batch_alter_table`); medido sobre la base local: ~1 min, mismas filas en las 533 tablas, mismos índices, `foreign_key_check` vacío. `scripts/migrar.py` copia la base antes (es destructiva). |
| 197 `dinero_numeric` | 79 columnas de dinero de `Float` a `Numeric`: importes `Numeric(18,2)`, tarifas, tipos de cambio, precios unitarios y costes de IA `Numeric(18,6)` (tipos `Money`/`Rate` de `app/models/money.py`). Redondea los valores a esos decimales. Python sigue recibiendo `float`. 10 columnas del plan se descartan por no ser dinero (ver docstring). | PostgreSQL: `ALTER COLUMN ... TYPE NUMERIC USING round(...)` reescribe cada tabla con bloqueo exclusivo (incluidas `users` y `projects`): en una hora de poca carga. SQLite: recrea 46 tablas. |
| 198 `cambios_estandar_y_portal` | (1) Tabla nueva `sd_standard_change_models` (catálogo de cambios estándar por empresa, A-SD19) y `sd_change_requests.standard_model_id` (clave a ella, `ON DELETE SET NULL`, con índice). Los cambios existentes quedan sin modelo: un `standard` aún sin aprobar irá al CAB al enviarse. (2) `client_users.must_change_password` (`NOT NULL DEFAULT false`): el portal obliga a cambiar la contraseña generada por el sistema (alta y «Reenviar acceso»); las filas existentes quedan en `false`. (3) `ai_meeting_user_prefs`: el único `uq_ai_meeting_user_prefs_user` (user_id) pasa a `uq_ai_meeting_user_prefs_org_user` (organization_id, user_id). El `downgrade` lo deshace todo (vuelve al único por persona: falla si alguien tiene preferencias en dos empresas). Medido en una copia de la base local (23-11-2026): 195→198 sin errores, mismas 2 747 filas; bajada a 197 y subida de nuevo, mismos conteos en las 534 tablas; `alembic heads`: una cabeza. | Rápida: tabla nueva, columnas con valor por defecto constante e índices. SQLite recrea `sd_change_requests`, `client_users` y `ai_meeting_user_prefs` (`batch_alter_table`). PostgreSQL: el único nuevo de `ai_meeting_user_prefs` bloquea esa tabla (pequeña) mientras se crea. |
| 200 `esquema_pendiente_auditoria` | Lo que la auditoría 2026-11-22 dejó como «migración necesaria» (informes 01-03). (1) Columnas nuevas, todas NULL: `subcontractor_invoices.approved_by` (FK `users`, `SET NULL`) y `approved_at`; `contracts.currency` (vacía = moneda de la empresa); pares clave/datos de textos (`texto_clave`/`texto_params` en `grc_sod_rules`, `issue_types`, `workflow_states`, `workflow_transitions`, `approval_groups`; `*_key`/`*_params` en `sd_sla_events.note`, `alerts.title`/`description`, `invoices.notes`, `rev_entries.description`, `timesheets.review_notes`; `sprint_plans.ai_reasoning_params`). (2) `notificationtype` + `milestone_approved`/`milestone_rejected` (PostgreSQL: `ALTER TYPE … ADD VALUE` en bloque autocommit, antes de la transacción). (3) Tablas nuevas `sd_voice_sessions`, `sd_ticket_hold_snapshots`, `sd_dynamic_form_rules`, `sd_dynamic_form_rule_history`, y **movimiento de datos** desde `app_settings` (`sd.voice_agent.sessions`, `sd.ticket.pending_snapshot.*`, `sd.dynamic_forms.*`): número y transcripción de voz se **cifran** con `SECRET_KEY` (haz la copia y no cambies la clave a la vez); cada clave se borra solo tras copiarla; lo que no se puede copiar (sin empresa, ticket inexistente) se queda y sale en el log `alembic.200`. (4) `invoices.tax_rate`, `recurring_invoices.tax_rate` → `NUMERIC(18,6)`, `rev_obligations.standalone_price` → `NUMERIC(18,2)`. (5) `org_id` → `organization_id` en 11 tablas (ABAC, guardarraíles de IA, seguridad) con sus índices `ix_*`. (6) `integration_connectors`: únicos de `name`/`slug` sustituidos por `UNIQUE (organization_id, slug)` + único parcial de `slug` con `organization_id IS NULL`. (7) Relleno de `organization_id` NULL desde `project_id`/`ticket_id`. (8) **440 FK** con `ON DELETE` explícito (hacia `organizations` `CASCADE`; columna nullable `SET NULL`; si no, `RESTRICT`). El `downgrade` lo deshace todo y devuelve los datos a `app_settings` (la voz, descifrada); no deshace el relleno (7) ni el redondeo (4). Medido en una copia de la base local (23-11-2026): 195→199 en 22,5 s y 199→200 en 5,3 s (sembrando blobs de prueba, 11,6 s); 540→544 tablas, 2 766 filas antes y después (una clave de `app_settings` pasa a `sd_dynamic_form_rules`); 440 FK cambiadas, `integrity_check` y `foreign_key_check` limpios; bajada a 199 con los mismos conteos en las 540 tablas y los blobs de vuelta; subida otra vez y `scripts/comprobar_esquema.py` en verde; `alembic heads`: una cabeza. | SQLite: las FK se cambian reescribiendo la cláusula en `sqlite_master` (`writable_schema`, sin recrear tablas) y se comprueba con `integrity_check`; recrea solo `integration_connectors`, `invoices`, `recurring_invoices` y `rev_obligations` (`batch_alter_table`). PostgreSQL: cada FK es `DROP CONSTRAINT` + `ADD … NOT VALID` (bloqueo breve `SHARE ROW EXCLUSIVE` en hija y padre) + `VALIDATE` (recorre la hija con `SHARE UPDATE EXCLUSIVE`: no para escrituras); 440 FK sobre ~350 tablas: en bases grandes, lánzala en hora de poca carga. Los `ALTER COLUMN … TYPE` de (4) reescriben `invoices`, `recurring_invoices` y `rev_obligations` con bloqueo exclusivo (tablas medianas). Si una FK no valida (filas huérfanas), queda `NOT VALID` y lo avisa el log; límpialas y lanza `VALIDATE CONSTRAINT`. Tras el upgrade, `python -m app.db.rls` rehace las políticas (las 11 tablas renombradas ya usan `organization_id`). |
| 201 `cadena_colaboracion_y_cronometro` | (1) C5 del informe 02 (auditoría 2026-11-22): `collaboration_audit_events.hmac` y `key_id` (VARCHAR(64), NULL). Las filas nuevas de la cadena de colaboración guardan el HMAC con la clave activa del llavero (`key_management`) y su `kid`; la verificación usa la clave de ese `kid` (si el llavero ya la podó, la fila sale en `unverifiable`, no como rotura). Las filas anteriores se quedan con NULL y se verifican por `integrity_hash` (v1/v2) como antes. (2) M31: índice único parcial `uq_timer_sessions_un_activo_por_usuario` en `timer_sessions(user_id) WHERE ended_at IS NULL` (un cronómetro abierto por persona). Antes de crearlo **cierra los duplicados** (deja abierto el más reciente de cada persona; al resto `ended_at` = ahora, sin imputación) y lo cuenta en el log `alembic.201`. El `downgrade` quita el índice y las columnas (no reabre los cronómetros cerrados). Medido en una copia de la base local (23-11-2026): 195→201 sin errores; 2 filas en `collaboration_audit_events` y 0 en `timer_sessions` (0 duplicados abiertos), mismos conteos tras subir, bajar a 200 y volver a subir; `integrity_check` limpio y `scripts/comprobar_esquema.py` en verde; con 3 cronómetros abiertos sembrados para una persona, cierra 2 y el índice rechaza un cuarto; `alembic heads`: una cabeza. | Rápida. SQLite: `ADD COLUMN` (el `downgrade` recrea `collaboration_audit_events`). PostgreSQL: `ADD COLUMN` NULL sin reescritura; el `CREATE UNIQUE INDEX` bloquea escrituras en `timer_sessions` mientras se crea (tabla pequeña). |

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


1. `GET /health` → 200. `GET /ready` → 200, con `db` y `redis` en `ok`. En staging y producción
   (23-11-2026, auditoría 01 B1) ninguna de las dos dice versión, producto, entorno ni modo del
   planificador: solo `status` de cada comprobación. Para depurar, mira el log o usa desarrollo.
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
