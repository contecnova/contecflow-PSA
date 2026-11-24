# Rutas anónimas: credencial propia y contexto de empresa

Arreglo del 23-11-2026 sobre la auditoría del 22-11-2026, informe 01, **M8**
(`docs/auditoria/2026-11-22/01_backend_nucleo_api_seguridad.md`).

Prueba: `tests/test_rutas_anonimas_contexto_2026_11.py` (recuento exacto, contexto
declarado en cada ruta, sesiones a mano de `app/` y comportamiento con `cerrar`).

## 1. El problema

Una ruta sin `get_current_user`, `get_current_client`, `get_current_portal_client`
ni `get_portal_client_or_user` no tiene empresa en su sesión. Hasta el 22-11-2026
esa sesión pasaba **sin filtro** por el ORM y por RLS, y todo dependía de que cada
servicio acotara a mano.

Desde el 23-11-2026 `TENANT_SESION_SIN_CONTEXTO=cerrar` es el defecto. Una sesión
sin empresa, sin superadmin y sin contexto de sistema declarado lanza
`TenantIsolationError`, y RLS no devuelve filas. Cada ruta anónima, por tanto:

1. **Verifica su credencial propia**: firma del webhook, token del formulario,
   token SCIM, ticket del WebSocket, contraseña, etc.
2. **Declara su contexto mientras busca la empresa**. Su sesión es
   `db: Session = Depends(sesion_de_sistema("<motivo>"))` (`app/db/session.py`).
   Es la misma sesión de `get_db`, con `contexto_de_sistema(db, motivo)` puesto.
   La búsqueda de la credencial corre entre empresas, pero con nombre.
3. **Publica la empresa en cuanto la conoce**. Lo hace con
   `publicar_empresa(db, org)` (empresa sin sujeto: webhook, enlace) o con
   `publicar_contexto_de_tenant(db, sujeto)` (usuario o cliente). Desde ese
   momento la sesión filtra y sella, y corta si la empresa está desactivada.
   Cuando el servicio acota él mismo con `como_organizacion`/`con_empresa`, eso
   también vale.

Una ruta que no abre sesión ORM queda exenta, con su motivo escrito en
`SIN_BASE` del test.

## 2. Recuento (medido el 23-11-2026)

Medido importando `app.main` y recorriendo `app.routes` y su grafo
`dependant.dependencies`: **2 757 rutas, 93 anónimas** (97 desde el 23-11-2026: +4 del restablecimiento de contraseña; 101 con las 4 de SAML).

| Tipo de credencial | Rutas | Sin sesión ORM |
|---|---:|---:|
| Entrada e identidad (login, MFA, SSO, SAML, refresco, contraseña, portal, OAuth) | 29 | 2 |
| Webhooks y canales con firma o secreto | 28 | 1 |
| SCIM (token de la empresa) | 13 | 0 |
| Enlaces y tokens propios (formularios, enlaces firmados, BI, aprobaciones, agente CMDB, auditor de Certificaciones) | 15 | 0 |
| WebSocket (ticket de un uso; JWT solo fuera de producción) | 6 | 0 |
| Públicas por slug (status page) | 2 | 0 |
| Sin credencial: JS estáticos, health, ayudas | 10 | 10 |
| **Total** | **103** | **13** |

Ninguna ruta se encontró sin verificar su credencial. Las de firma ya se habían
revisado en auditorías anteriores (2026-08, 2026-11 y 2026-11b), y esta pasada
solo añade el contexto. En la tabla, «sistema» es el motivo declarado; «publica»
es la empresa que se fija después de verificar.

## 3. Tabla ruta → credencial → empresa

Prefijo `/api/v1` salvo las de la raíz.

### Entrada e identidad (25)

| Ruta | Credencial | Cómo resuelve la empresa |
|---|---|---|
| `POST /auth/login` | usuario + contraseña; 5/min y bloqueo por cuenta e IP | sistema «login»; `entrada_service.decidir` (host, código, única o elección) |
| `POST /auth/select-organization` | token de elección firmado | sistema; la elegida, con la pertenencia revalidada |
| `GET /auth/entry-config` | ninguna (solo marca) | sistema; la del host en modo subdominio |
| `POST /auth/refresh` | refresh token (JWT + `jti` de una sesión activa) | sistema; claim `org` revalidado |
| `POST /auth/password/forgot` | ninguna (anti-enumeración, 5/min) | sistema; la del usuario, para su SMTP (`encolar`) |
| `POST /auth/password/reset` | token efímero de un uso | sistema; la del usuario (su política de contraseñas) |
| `POST /auth/password/reset/policy` | token efímero vigente (no lo consume, 20/min) | sistema; la del usuario (solo las reglas) |
| `POST /auth/mfa/validate` | reto MFA firmado + TOTP | sistema; la del usuario |
| `POST /auth/mfa/webauthn/authenticate/start` y `/finish` | reto MFA + firma WebAuthn | sistema; la del usuario |
| `POST /auth/passkey/login/start` y `/finish` | firma WebAuthn (passkey) | sistema; la del usuario |
| `GET /auth/sso/providers` | ninguna; se filtra por email o dominio | sistema; las del dominio |
| `GET /auth/sso/{config_id}/authorize` | configuración SSO + `state` | sistema; la de la configuración |
| `POST /auth/sso/{config_id}/callback` | `state` firmado + `code` OIDC | sistema; la de la configuración |
| `GET /auth/saml/metadata` | ninguna | sin base (XML con `BASE_URL`) |
| `GET /auth/saml/{config_id}/login` | configuración SAML activa; registra la AuthnRequest pendiente (un solo uso) | sistema; la de la configuración |
| `POST /auth/saml/callback` (ACS) | firma XML del IdP + audiencia, destino, caducidad e `InResponseTo` de un solo uso | sistema; la de la configuración de la petición pendiente |
| `POST /auth/saml/canjear` | ticket de un solo uso que emite el ACS | sistema; la de la configuración (`entrada_service.confirmar`) |
| `GET /auth/saml/logout` | LogoutRequest del IdP con firma de query (RSA-SHA256/512) obligatoria | sistema; la de la configuración del emisor |
| `POST /portal/auth/login` | email + contraseña del cliente | sistema; la del cliente |
| `POST /portal/auth/logout` | token del cliente (se revoca su `jti`) | sin base |
| `POST /portal/auth/password/forgot` | ninguna (anti-enumeración, tiempo igualado, 5/min + cubo hash(correo)\|IP) | sistema; la del cliente, para su SMTP (`encolar`) |
| `POST /portal/auth/password/policy` | token efímero del portal vigente (no lo consume, 20/min) | sistema; **publica** la del cliente |
| `POST /portal/auth/password/reset` | token efímero del portal de un uso (10/min) | sistema; **publica** la del cliente (su política) |
| `POST /developer/token` | `client_id` + `client_secret` | sistema; `con_empresa` en la de la app |
| `POST /developer/token/revoke` | el propio token (por huella) | sistema; por huella |
| `GET /developer/userinfo` | bearer OAuth (huella y caducidad) | sistema; el usuario del token |
| `GET /ws/portal-ticket` | token del cliente del portal | `declarar_sistema` y después `publicar_contexto_de_tenant(cliente)` |

### Webhooks y canales (28)

| Ruta | Credencial | Cómo resuelve la empresa |
|---|---|---|
| `POST /sd/inbound-email` | secreto de la empresa del destinatario | sistema; por la dirección `To`, y `inbound_mail.procesar` con `como_organizacion` |
| `POST /sd/multichannel/inbound/email` | `X-Inbound-Secret` de la empresa del destinatario | igual que la anterior |
| `POST /sd/multichannel/inbound/sms` | firma de Twilio con el token de la empresa del número `To` | sistema; por el número receptor |
| `POST /sd/voice/webhook/twilio` y `/gather` | firma de Twilio (empresa del número llamado) | sistema; **publica** la empresa tras verificar (`_llamada_verificada`) |
| `POST /sd/events/{source}` | token de eventos de la empresa | sistema; **publica** la empresa del token |
| `POST /sd/channels/slack/interactions` | firma de Slack del workspace | sistema; la del workspace (`leer_interaccion`) |
| `POST /sd/channels/slack/events` | firma de Slack del workspace | sistema; publica la del workspace antes de encolar |
| `GET /sd/channels/whatsapp/webhook` | verify token | sistema; por el verify token |
| `POST /sd/channels/whatsapp/webhook` | `X-Hub-Signature-256` de Meta | sistema; por el número |
| `POST /collaboration/webhooks/incoming/{token}` | token del webhook entrante | sistema; la del webhook |
| `GET /collaboration/integrations/oauth/callback` | `state` OAuth firmado + cookie de vínculo | sistema; la del `state` |
| `POST /webhooks/fire/{slug}` | slug + HMAC `X-Contecflow-Signature` | sistema; **publica** la del disparador tras la firma; la tarea de fondo usa `fijar_contexto` |
| `POST /invoices/stripe/webhook` | `Stripe-Signature` | sistema; la de la factura |
| `POST /git/webhooks/github[/{slug}]` | `X-Hub-Signature-256` | sistema; la de la instalación o el slug |
| `POST /git/webhooks/gitlab[/{slug}]` | `X-Gitlab-Token` | sistema; la de la instalación o el slug |
| `POST /esign/webhooks/docusign` | HMAC de DocuSign Connect | sistema; la del sobre |
| `GET /esign/webhooks/adobe` | client id de Adobe Sign | sin base (eco) |
| `POST /esign/webhooks/adobe` | client id de Adobe Sign | sistema; la del acuerdo |
| `POST /webhooks/meetings/recall/{org_id}` | firma Svix de la empresa | sistema; `{org_id}` verificada con su secreto |
| `POST /webhooks/meetings/zoom/{org_id}` | `x-zm-signature` | igual |
| `POST /webhooks/meetings/teams/{org_id}` | `clientState` de Graph | igual |
| `POST /integrations-hub/slack/commands` | firma de Slack (secreto del workspace o global) | sistema; publica la del usuario de Slack (`_ejecutar_comando_del_bot`) |
| `POST /integrations-hub/teams/commands` | JWT de Bot Framework (firma, emisor, audiencia) | sistema; publica la del usuario de Teams |
| `POST /jira/webhook` | secreto de webhook de la empresa | sistema; **publica** la empresa del secreto |
| `POST /integrations/jira/webhook` | secreto de webhook de la empresa | igual |

### SCIM (13)

`/scim/v2/{org_id}/…`: `ServiceProviderConfig`, `ResourceTypes`, `Schemas`,
`Users` (GET, POST), `Users/{id}` (GET, PUT, PATCH, DELETE), `Groups`,
`Groups/{id}` (GET, PATCH) y `Bulk`.

La credencial es el token SCIM de la empresa, que debe coincidir con `{org_id}`
(si no, 403). `_require_scim_token` busca el token en `contexto_de_sistema("scim:
token de la empresa")` y después **publica** `{org_id}`. Como la sesión es la
misma en todo el grafo, el endpoint ya filtra por esa empresa.

### Enlaces y tokens propios (13)

| Ruta | Credencial | Cómo resuelve la empresa |
|---|---|---|
| `GET /forms/public/{token}` y `POST …/submit` | token del formulario activo (envío: 10/min) | sistema; **publica** la del formulario (sella el ticket o lead) |
| `GET /portal/view/{token}` | token firmado del proyecto | sistema; **publica** la del proyecto |
| `GET /certificaciones/auditor/{token}` | token del acceso temporal del auditor (solo su huella SHA-256 en `cert_accesos`; vigente, sin revocar, auditor activo) | sistema; **publica** la del acceso (migración 212; cada consulta en `cert_accesos_registro` y en auditoría) |
| `GET /certificaciones/auditor/{token}/paquete` | ídem | sistema; **publica** la del acceso; deja traza en `cert_paquetes` |
| `GET /collaboration/files/by-token/{token}` | token firmado de descarga | sistema; la del adjunto |
| `GET /bi/bookmarks/shared/{share_token}` | token de enlace compartido | sistema; la del marcador |
| `GET /bi/embed/sdk-config` y `GET /bi/embed/view` | token de embebido de la empresa `org` | sistema; `org` verificada con su token |
| `GET /bi/data/projects`, `/timesheets`, `/kpis` | token BI (`get_bi_token`) | sistema; la del token |
| `GET` y `POST /approvals/email-decision` | token firmado del correo (POST: 20/min) | sistema; la de la solicitud |
| `POST /sd/cmdb/agents/checkin` | bearer del agente (SHA-256 en base) | sistema; la del agente |

### WebSocket (6)

`/collaboration/ws`, `/bi/collaboration/dashboards/{key}/updates`,
`/bi/intelligence/realtime/stream`, `/ws/notifications`,
`/ws/portal-notifications` y `/ws/doc/{doc_id}`.

La credencial es el ticket de un solo uso (`GET /ws/ticket`) o el JWT en la URL,
que solo se admite fuera de producción. Cada WebSocket abre su `SessionLocal()` y
declara `declarar_sistema(db, "ws: identidad por ticket")`. Tras resolver al
usuario o al cliente (y revalidar la empresa activa del ticket), llama a
`publicar_contexto_de_tenant`.

### Públicas por slug (2)

`GET /sd/status-page?org=<slug>` y `GET /status?org=<slug>` (raíz). No llevan
credencial: son públicas a propósito. Son de sistema («status page pública por
slug») y la empresa se resuelve con `status_page_service.organizacion_de_la_pagina`.
Solo sale lo que la empresa marcó como público.

### Sin credencial y sin base (10)

`GET /collaboration/slash/help`, `OPTIONS /collaboration/tus`,
`GET /collaboration/push/public-key`, `GET /ai-governance/pii-types`,
`POST /client-errors` (solo log), `GET /status/page.js`, `GET /status/embed.js`,
`GET /widget/ticket.js`, `GET /health` y `GET /ready`. Las dos últimas hacen
`SELECT 1` por el engine, sin ORM.

## 4. Sesiones creadas a mano (`SessionLocal()`)

Hay dos ayudantes en `app/db/contexto_de_tenant.py`, reexportados en `app/db/session.py`:

- `declarar_sistema(db, motivo)`: contexto de sistema para toda la vida de la
  sesión (WebSocket, hilo, script).
- `fijar_contexto(db, org, motivo)`: la empresa si se conoce; sistema con
  motivo si no (tareas en segundo plano que reciben la empresa).

Medido con `git grep -n "SessionLocal()" -- app`: **antes, 54 líneas en 30
ficheros**, que son 48 sitios con código y 6 comentarios.

- 4 ya tenían contexto desde la primera consulta: `ai_chat`,
  `agent_execution_service`, `metricas_empresa` (`sin_filtro_de_tenant`) y
  `reuniones/llamadas` (`como_organizacion`).
- 2 son `get_db` y `worker_db_session`, que declara quien las usa: la petición,
  la tarea de Celery (`TareaDeSistema`) o `segundo_plano`.
- Los **42 restantes no declaraban nada**. Entre ellos están 9 de WebSocket, que
  publicaban la empresa pero buscaban la identidad sin contexto.

**Ahora** los 42 declaran, y también los 2 que otros cambios añadieron mientras
tanto (`bots.texto_de_sistema` y `aprovisionamiento`): son 50 sitios. Por tipo
de sitio:


- WebSockets: 9 sitios.
- Ajustes globales: métricas, red, IA, SSO y política de login.
- Siembra: 3 sitios.
- Tareas en segundo plano con empresa:
  - `semantic_feedback_service` ×3, con la empresa del ticket;
  - `task_service` ×2, con la de la petición;
  - `cab_service.webhooks_entrantes`;
  - `auto_resolucion_operaciones`;
  - `bots`;
  - `olap` ×5;
  - `bi_storytelling` ×3;
  - `textos_de_salida`;
  - `aprovisionamiento`.
- Planificador de colaboración: 3 sitios.
- `key_management`: 3 sitios.

Fuera de `app/`:

- `setup.bat` y `setup.sh`: comprobar usuarios y contraseñas demo.
- `scripts/docker_stack.py`, `seed_full_data.py`, `reset_to_admin_only.py`,
  `audit_secrets_encryption.py` y `list_tables.py`.

`segundo_plano._publicar` usa `fijar_contexto`. `segundo_plano._llamar` ejecuta en
línea (sin Celery) dentro de `trabajo_de_sistema("segundo plano: <función>")`.

## 5. GRC

- **Auditoría.** No cambia ningún registro. Los motivos declarados aparecen en el
  `TenantIsolationError` cuando falta uno.
- **RGPD y retención.** Sin datos nuevos.
- **Privilegios.** Ninguna ruta gana acceso. Al publicar la empresa tras la
  credencial, las rutas de webhook, formulario, SCIM, Jira, Twilio,
  monitorización y CAB pasan a filtrar por su empresa; antes iban sin filtro.
  Una empresa desactivada corta en `publicar_empresa` (403
  `empresa_desactivada`).
- **Operación.** `TENANT_SESION_SIN_CONTEXTO=avisar` sigue existiendo para
  localizar un sitio sin declarar: deja un WARNING por sitio y lo cuenta en
  `SITIOS_SIN_CONTEXTO`. No es para producción.
