# Pruebas de conexión de los conectores: qué verifican de verdad

23-11-2026. Segunda ronda de la auditoría 2026-11-22: los informes 02 (A56, A57) y 03 (§5, «Stubs o integraciones sin probar de verdad»). Cada conector tiene una prueba de conexión **real**, es decir, una llamada al servicio con las credenciales de la empresa, y la prueba dice lo que ha comprobado (`verificado`):

Las rutas son relativas a `/api/v1`; `…/x/test` es `POST /settings/integrations/x/test` (capacidad `org.administrar`).

| `verificado` | Significa |
|---|---|
| `nada` | No se ha llamado al servicio: falta configuración o el fallo es previo. |
| `configuracion` | Los campos están completos y el servidor responde, pero la credencial necesita un flujo con usuario (OAuth con consentimiento) que una prueba no puede hacer. |
| `alcance` | El servicio responde en esa dirección; la credencial no se ha validado. |
| `credencial` | El servicio ha aceptado la credencial. |
| `credencial_y_uso` | Además, la operación que usa el producto funciona con esos permisos. |
| `pasivo` | Solo secretos de entrada (firmas de webhooks): se verifican al llegar el primer evento. |

Todas son de **solo lectura** salvo Slack y Teams por webhook, cuya prueba es enviar un mensaje (esa es la única operación del webhook). Ninguna devuelve el cuerpo de la respuesta remota: solo el estado HTTP o la clase del error.

## Lo que NO se ha podido verificar aquí

En este entorno no hay credenciales reales de ningún proveedor. El código de las pruebas está cubierto por tests con dobles (`tests/test_ronda2_transversal_2026_11_23.py` y `tests/test_auditoria_2026_11_arquitectura_c3.py`), pero **que cada servicio acepte la llamada tal como se hace solo se sabe cuando el usuario pulsa «Probar conexión» con sus credenciales reales.** Si una prueba falla, `verificado` y el estado HTTP dicen en qué paso.

Lo que más importa confirmar con un servicio real:

- **Jira Cloud:** `POST /rest/api/3/search/jql` con `nextPageToken`, que es la ruta de búsqueda actual (A56), y que `/rest/api/3/status` traiga `statusCategory` (A57). La prueba lo comprueba por separado en `comprobaciones`.
- **Microsoft Graph:** que la aplicación de Azure de la empresa tenga `Organization.Read.All`, y para cada función su permiso: `Calendars.ReadWrite`, `Presence.Read.All`, `Tasks.ReadWrite.All`, `TeamsTab.ReadWriteForTeam.All`, `ChannelMessage.Send`, `Sites.ReadWrite.All` y `Files.ReadWrite.All`. La prueba solo verifica el token y la lectura del tenant; un permiso que falte se ve al usar esa función (403 de Graph).
- **Salesforce:** la versión de API configurada (`SALESFORCE_API_VERSION`, `v57.0` por defecto) y la lectura de `Opportunity`.

## Por conector

| Conector | Dónde se prueba | Qué llama | `verificado` si sale bien | Necesita del usuario |
|---|---|---|---|---|
| Jira (tareas y service desk) | `GET /jira/test`, `POST /integrations/jira/configs/{id}/test` | `GET /rest/api/3/myself`, y en `comprobaciones`: `GET /project/{clave}`, `POST /search/jql` (`maxResults=1`) y `GET /status` | `ok` más `comprobaciones` (`proyecto`, `busqueda`, `estados`: `true`/`false`/`null`) | URL, correo y token de API de Atlassian |
| Microsoft 365 / Graph | `POST /settings/integrations/ms_graph/test` | Token de aplicación de la empresa y `GET /organization` | `credencial_y_uso` | Tenant, client id y secret de su aplicación de Azure; permisos de aplicación con consentimiento de administrador |
| Buzón del service desk (IMAP / Graph) | `POST /settings/integrations/sd_mailbox/test` y `POST /sd/inbound/test` | IMAP con la IP validada y fijada, login y `UNSEEN`, o Graph con `GET /users/{buzón}/mailFolders/inbox` | `credencial_y_uso` | Host, usuario y contraseña IMAP, o la credencial Graph y el buzón |
| WhatsApp Business | `POST /settings/integrations/whatsapp/test` | `GET graph.facebook.com/{versión}/{phone_number_id}` | `credencial_y_uso` | `phone_number_id` y token de usuario del sistema |
| Salesforce | `POST /salesforce-sync/integrations/salesforce/test?instance_id=` (capacidad `integraciones.responsables`) | `GET /services/data/{v}/limits` y `SELECT Id FROM Opportunity LIMIT 1` | `credencial_y_uso`; `salida: no_implementada` | `instance_url` y `access_token` de la instancia |
| SMTP de empresa | `POST /settings/integrations/smtp/test` | Conexión (IP fijada), TLS, login y `NOOP` | `credencial` | Host, puerto, usuario y contraseña |
| AWS S3 | `…/aws_s3/test` | `head_bucket` | `credencial_y_uso` | Bucket, región y claves |
| Slack (credenciales) | `…/slack/test` | `POST` vacío al webhook (400 de Slack = existe) | `alcance` | Webhook |
| Slack / Teams (hub) | `POST /integrations-hub/slack/test`, `/teams/test` | Envía un mensaje de prueba | (mensaje entregado) | Webhook |
| Twilio | `…/twilio/test` | `GET` de la cuenta | `credencial` | SID y token |
| Stripe | `…/stripe/test` | `GET /v1/balance` | `credencial` | Clave secreta |
| DocuSign | `…/docusign/test` | Descubrimiento OpenID del servidor de autenticación | `configuracion` (antes decía `ok` sin llamar a nada) | Conectar la cuenta (OAuth con consentimiento) |
| Adobe Sign | `…/adobe_sign/test` | `GET {base}/baseUris` | `alcance` | Conectar la cuenta (OAuth) |
| Proveedores de IA | `…/ai_providers/test`, `POST /ai-providers/{id}/test` | `count_tokens` (Anthropic) o `GET /models` (OpenAI) | `credencial` | Clave |
| DeepL, Azure Translator | `…/deepl/test`, `…/azure_translator/test`, `POST /translation/test` | Traduce una palabra | `credencial_y_uso` | Clave (y región) |
| OpenExchangeRates | `…/open_exchange_rates/test` | `latest.json` | `credencial_y_uso` | App id |
| Monitorización, webhooks entrantes | `…/monitoring/test`, `…/webhooks/test` | Nada saliente | `pasivo` | Que el emisor mande un evento firmado |
| Uso de licencias (M365, Google, Okta, Jamf) | `…/alm_*/test`, `POST /alm/uso/conexiones/{clave}/probar` | La llamada más barata de cada fuente con sus permisos | `credencial_y_uso` | Credencial de la fuente |
| Del ticket al PR (agente de código) | `POST /ticket-pr/prueba`, `…/ticket_pr/test` | `docker version`, `docker pull` de las imágenes fijadas (motor, proxy, auxiliar), GitHub App (`GET /app/installations/{id}` y token de instalación para un repositorio permitido) o GitLab (`GET /personal_access_tokens/self` y el proyecto), y la lista de modelos del proveedor de IA | `credencial_y_uso` (todo, con un repositorio probado) o `credencial` (Git y modelo); `comprobaciones` por pieza | Docker en el servidor, GitHub App o token de GitLab, proveedor de IA; ver docs/integraciones/TICKET_A_PR.md §11 |
| contecmind, contecintelligence | `…/{producto}/test`, `POST /conectores/{producto}/probar` | Credencial de la aplicación y salud | `credencial` | Credencial de la aplicación |
| Xero, QuickBooks | `POST /accounting/xero/test`, `/qb/test` | Organización o empresa del token | (ok/error) | Token OAuth |
| Reuniones (Teams, Zoom, Meet, bots) | `POST /meeting-assistant/config/test/{conector}` | La prueba de cada conector | (ok/error) | Credencial de cada plataforma |
| BI ETL, escáneres de la CMDB | `POST /bi/etl/connectors/{id}/test`, `POST /cmdb/software/scanners/{id}/test` | Conexión al origen o al primer equipo | (ok/error) | Credencial del origen o equipo |

`tests/test_ronda2_transversal_2026_11_23.py::test_cada_proveedor_de_credenciales_tiene_prueba` falla si se añade un proveedor al almacén de credenciales sin su prueba.

## Lo que sigue sin conector real (no es una prueba que falte)

Está en el informe 03, §5:

- la sincronización de salida de Salesforce: la prueba lo dice (`salida: no_implementada`);
- los 7 conectores del marketplace que no tienen código;
- 5 proveedores de discovery de la CMDB sin dependencia instalada;
- `slack_service` en modo simulado.

Ninguno se anuncia como probado.
