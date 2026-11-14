# Despliegue de esta versión — lista de comprobación

Guía para quien despliega. Todo sale del código (`app/core/config.py`,
`app/core/config_groups/*`, `.env.example`, `docker-compose.yml`, `setup.sh`,
`alembic/versions/`). Rutas de la API con el prefijo `/api/v1`.

## 0. Antes de empezar

1. **Copia de seguridad de la base de datos.** Las migraciones 159, 160 y 161
   mueven datos y no tienen vuelta atrás completa. La 160 borra `mfa_configs` y
   su `downgrade` no hace nada.
2. Comprueba que la cabeza es la que esperas: `python -m alembic heads`. Cuando
   se escribió esta guía era `164_paridad_postgres_e_indices_de_claves_ajenas`.
   Si sale otra, revisa las revisiones nuevas con el mismo criterio que la
   tabla de abajo.

## 1. Variables de entorno (en `.env` o en el entorno del contenedor)

Con `ENVIRONMENT=staging` o `production`, el arranque **falla** si falta algo
obligatorio o si se queda en el valor de desarrollo. Las variables marcadas
*obligatoria* tumban el arranque. El resto solo apaga su función.

| Variable | ¿Obligatoria? | De dónde sale el valor y qué hacer |
|---|---|---|
| `INBOUND_EMAIL_SECRET` | **Sí** en staging/producción (vacía o de menos de 24 caracteres → no arranca). Lo mismo vale para `WEBHOOK_SECRET`. | Genérala: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Configura la pasarela de correo (Mailgun, SendGrid o Postmark) para que haga `POST /api/v1/sd/inbound-email` con la cabecera `X-Contecflow-Email-Secret: <valor>`. Una organización puede tener su propio secreto con la credencial `webhooks.inbound_email_secret` (Configuración → Integraciones, o `PUT /api/v1/settings/integrations/webhooks/inbound_email_secret`). La organización se reconoce por su `SD_INBOUND_ADDRESS`. Si no hay secreto, la respuesta es 403. |
| `METRICS_AUTH_TOKEN` | Solo si `METRICS_ENABLED=1`. | Genera un valor aleatorio y ponlo como `bearer_token` en el scrape de Prometheus. Si no hay token y el entorno no es `development`/`test`/`testing`, `/metrics` devuelve 401. Es un ajuste de plataforma: el superadmin también puede cambiarlo en caliente (grupo `observability`), y ese valor tiene prioridad sobre el del entorno. |
| `STRIPE_WEBHOOK_SECRET` | Solo si se cobra con Stripe. | En Stripe, ve a Developers → Webhooks → *Add endpoint*. Pon la URL `https://<dominio>/api/v1/invoices/stripe/webhook` y elige los eventos `checkout.session.completed` y `checkout.session.async_payment_succeeded` (son los únicos que aplica `payments_service`). Copia el *Signing secret* (`whsec_…`). También se puede guardar como credencial `stripe.webhook_secret`. Sin secreto, el webhook responde 503. Si la firma no cuadra o tiene más de 300 s, responde 400. Para crear los enlaces de pago hace falta `STRIPE_SECRET_KEY`. |
| `SLACK_TEAM_ID` | No es variable de entorno: es un **ajuste en vivo por organización** (grupo `ai`). | Es el ID del workspace (`T…`), el mismo que Slack manda como `team_id` en cada slash command. Se pone en Configuración → Configuración dinámica → IA, o con `PUT /api/v1/settings/runtime/ai/SLACK_TEAM_ID`, con la sesión de un admin de esa organización. Si dos organizaciones tienen el mismo valor, Slack recibe 403. Si ninguna lo tiene, el usuario se busca en todas y queda un aviso en el log. La firma se comprueba con `SLACK_SIGNING_SECRET` (global) o con la credencial `slack.signing_secret` de la organización. |
| `TEAMS_TENANT_ID` | Igual que el anterior: ajuste en vivo por organización (grupo `ai`). | Es el *Tenant ID* (GUID) de Microsoft Entra ID (Entra admin center → Overview). Es el `tenant.id` que pone el Bot Framework. Se configura igual que `SLACK_TEAM_ID`. El bot necesita además `TEAMS_BOT_APP_ID`. |
| Secreto del webhook de Jira | Por organización. **No** es `JIRA_WEBHOOK_SECRET`: el global ya no autentica nada, así que déjalo vacío. | Un admin entra en la pantalla *Jira* (`/jira-integration`) y pulsa *rotar secreto*, o llama a `POST /api/v1/jira/webhook-secret`. El secreto se ve **una sola vez**. Al rotarlo, el anterior deja de valer y queda en la auditoría. En Jira, apunta el webhook a `https://<dominio>/api/v1/jira/webhook?org=<organization_id>` (o a `/api/v1/integrations/jira/webhook?org=…`). Jira debe mandar el secreto en `X-Atlassian-Webhook-Token` o firmar el cuerpo en `X-Hub-Signature-256: sha256=…`. |
| Twilio por organización | Solo si se usa SMS o voz. | Cada organización declara sus números en el ajuste en vivo **`TWILIO_PHONE_NUMBERS`** (grupo `service_desk`, E.164 separados por comas, p. ej. `+34600000001,+34600000002`). Se pone desde Configuración dinámica → Service Desk, o con `PUT /api/v1/settings/runtime/service_desk/TWILIO_PHONE_NUMBERS`. La credencial `twilio.from_number` también vale. Cada organización puede tener su token: credencial `twilio.auth_token` (`PUT /api/v1/settings/integrations/twilio/auth_token`). Si no tiene, se usa el global `TWILIO_AUTH_TOKEN` (Twilio Console → Account → API keys & tokens → *Auth Token*). En Twilio Console → Phone Numbers → Active numbers: en *A call comes in*, `POST https://<dominio>/api/v1/sd/voice/webhook/twilio`; en *A message comes in*, `POST https://<dominio>/api/v1/sd/multichannel/inbound/sms`. **Cambio de comportamiento:** una llamada a un número que no declara ninguna organización, o que declaran dos, se rechaza (`<Reject/>`). Antes la atendía la instalación sin organización. Hay que declarar los números **antes** de desplegar. |
| `GEOIP_LOOKUP_ENABLED` | No. **Por defecto `true`.** Pon `false` para que ninguna IP salga a un tercero. | Activada, la IP pública de **cada inicio de sesión y cada refresco** se manda a `GEOIP_LOOKUP_URL` (por defecto `https://ipapi.co/{ip}/json/`), un tercero. Es una transferencia de datos personales, así que necesita base legal y aviso de privacidad, y el servidor necesita salida a Internet hacia ese servicio. La respuesta (país, región, ciudad, ASN) alimenta el riesgo de sesión: un cambio de país pesa 20 y uno de ASN pesa 25. Se guarda en caché por IP `GEOIP_CACHE_TTL_SECONDS` (86400), o 300 s si falla. Nunca se consultan IPs privadas ni reservadas. Revisa la cuota del proveedor. Si la apagas, solo se usan las cabeceras `cf-ipcountry`/`x-asn` del proxy. |
| `PROMETHEUS_MULTIPROC_DIR` | Si la API corre con más de un worker y `METRICS_ENABLED=1`. | Un directorio en el que se pueda escribir, **vaciado en cada arranque**. `docker-compose.yml` ya lo hace en el servicio `api` (`/tmp/prometheus-multiproc`, `rm -rf` + `mkdir` antes de uvicorn). Fuera de compose tienes que hacerlo tú. Sin él, cada worker tiene su propio registro y `/metrics` solo devuelve el del worker que atiende. El nombre tiene que ser exactamente `PROMETHEUS_MULTIPROC_DIR` y tiene que estar en el entorno del proceso, porque `prometheus_client` y `/metrics` la leen de ahí. El alias `METRICS_MULTIPROC_DIR` de `Settings` solo crea el directorio. Cada worker se da de baja al apagarse, y los que mueren sin apagarse bien (SIGKILL, OOM) se detectan en el siguiente scrape (solo en POSIX). |
| `WEBAUTHN_RP_ID` / `WEBAUTHN_ORIGIN` | **Sí** en staging/producción (con `localhost` no arranca). | `WEBAUTHN_RP_ID` es el dominio del frontend, sin esquema ni puerto (p. ej. `app.ejemplo.com`). `WEBAUTHN_ORIGIN` es el origen exacto que ve el navegador (p. ej. `https://app.ejemplo.com`). Las passkeys quedan atadas al RP ID: si lo cambias después, las ya registradas dejan de valer. |

Todas estas variables están en `.env.example`, con su comentario
(`PROMETHEUS_MULTIPROC_DIR` comentada a propósito: basta con que exista, aunque
vacía, para que `prometheus_client` entre en modo multiproceso).
`tests/test_env_example_sincronizado.py` vigila que no vuelvan a faltar. Un
`.env` creado antes no las tiene: añádelas a mano.

## 2. Migraciones: `alembic upgrade head`

Con compose, el servicio `migrate` ejecuta `python -m alembic upgrade head && python -m app.db.rls`,
y `api`, `worker` y `beat` esperan a que termine bien. Fuera de compose, lanza
esos mismos dos comandos. `setup.sh` también llama a `alembic upgrade head`.

| Revisión | Qué hace | ¿Lenta o con bloqueos en PostgreSQL? |
|---|---|---|
| 158 `obligaciones_asc606_precio_y_metodo` | Añade a `rev_obligations` tres columnas que admiten nulos: `method`, `standalone_price` y `notes`. | Rápida: solo cambia el catálogo. |
| 159 `jira_una_sola_configuracion` | Añade `sd_jira_configs.usar_para_tareas` (`NOT NULL DEFAULT false`). Pasa la conexión Jira de tareas de `app_settings` (`jira_url`, …) a una fila de `sd_jira_configs` y borra esos `app_settings`. Las filas globales solo se asignan si hay una única organización. | Rápida. El default constante no reescribe la tabla (PG ≥ 11). Recorre pocas filas. |
| 160 `mfa_un_solo_sistema` | Añade `users.mfa_verified_at`. Copia el TOTP de `mfa_configs` a `users` y rehace `mfa_backup_codes` por `user_id`. **Borra `mfa_configs`**. Es irreversible. | Rápida (tablas pequeñas). `DROP TABLE` y la recreación de `mfa_backup_codes` toman un bloqueo exclusivo breve. |
| 161 `jira_hub_a_jira_config` | Pasa las credenciales Jira de `integration_configs` (tipo `jira`) a `sd_jira_configs`. Desactiva la fila antigua y borra su token. | Rápida (pocas filas). |
| 162 `perfil_semantico_por_organizacion` | Rellena `sem_profiles.organization_id` con la organización del usuario. Quita el único de `user_id` y crea el único `(user_id, organization_id)`. | `UPDATE` de toda la tabla. El índice y el único se crean **sin** `CONCURRENTLY`, así que bloquean las escrituras en `sem_profiles` mientras se construyen. Es una fila por usuario: en la práctica, segundos. |
| 163 `indices_de_claves_ajenas_calientes` | Crea 12 índices en claves ajenas muy filtradas (`sd_tickets.requester_client_id`, `tasks.parent_task_id`, …). | `CREATE INDEX CONCURRENTLY IF NOT EXISTS` dentro de `autocommit_block`. **No bloquea** lecturas ni escrituras, pero lee la tabla dos veces y espera a que acaben las transacciones abiertas. En tablas grandes, minutos. |
| 164 `paridad_postgres_e_indices_de_claves_ajenas` | (1) Pone a NULL los `budgets.cliente_id` huérfanos y crea la clave ajena `fk_budgets_cliente_id_clients` (`ON DELETE SET NULL`). (2) Crea hasta 319 índices: 2 de paridad en `budgets` y 317 en claves ajenas. | (1) `ALTER TABLE … ADD CONSTRAINT` sin `NOT VALID`: mientras valida, bloquea las escrituras en `budgets` (y en `clients`), lo que dura proporcional a `budgets`. (2) Igual que la 163, `CONCURRENTLY`, sin bloquear, uno tras otro. **Es la más lenta**: el tiempo total es la suma de leer cada tabla afectada. |

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

## 3. Arranque

1. `docker compose --profile app up -d`. Si no usas compose, levanta API, worker
   y beat después de que hayan terminado las migraciones.
2. Si el arranque falla, el mensaje dice qué variable falta (sección 1).
3. Detrás de un proxy (TLS terminado antes de la API): `BACKEND_URL` tiene que
   ser la URL pública (`https://<dominio>`). La firma de Twilio se comprueba
   contra `BACKEND_URL` + ruta y, si no, contra la URL que ve la API. Con
   `docker-compose.yml` la API ya cree las cabeceras `X-Forwarded-*` de nginx
   (`TRUSTED_PROXY_CIDRS` forzado en el servicio `api`; se acota con
   `CONTECFLOW_PROXY_CIDRS`). El proxy de delante debe conservar el `Host` o
   mandar `X-Forwarded-Host`, y mandar `X-Forwarded-Proto: https`. Sin compose,
   pon `TRUST_PROXY_HEADERS=true` y en `TRUSTED_PROXY_CIDRS` la red del proxy.
   `FORWARDED_ALLOW_IPS` de uvicorn no hace falta.

## 4. Pruebas de humo después de desplegar

1. `GET /health` → 200. `GET /ready` → 200, con `db` y `redis` en `ok`.
2. `python -m alembic current` → la cabeza de la sección 0. La consulta de
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
