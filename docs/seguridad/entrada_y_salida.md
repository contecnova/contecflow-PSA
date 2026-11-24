# Seguridad transversal de entrada y salida

Arreglos del 23-11-2026 sobre la auditoría del 22-11-2026 (`docs/auditoria/2026-11-22/`):
01 M4, M5, M6, M7, M10 y B8; 02 C4, A18–A21, A27, A28, A37–A39, M59, M67, M80 y M94;
03 A-RZ2, A-RZ4, A-SD8 y «marketplace en claro».

Pruebas: `tests/test_seguridad_entrada_salida_2026_11_23.py` y `tests/test_subidas_validador_central.py`.

## 1. Llamadas salientes (SSRF)

### Un solo guardia

`app/core/outbound_url.py` es el **único** validador SSRF. Antes había cuatro más:

- `enterprise_service/webhooks._BLOCKED_NETWORKS`;
- `automations_service/acciones._motivo_de_rechazo_ssrf`, que dejaba pasar si fallaba el DNS;
- `bookings_service._validate_provision_url`, que no resolvía el nombre;
- `auth_service/sso.validate_https_discovery_url` y `core/network.assert_safe_outbound_url`.

Hoy todos delegan en el central y conservan su nombre para no romper a quien los llama.

El guardia:

- **Rechaza** todo lo que no sea una IP global: privadas, loopback, link-local (metadatos de nube), CGN 100.64/10, reservadas, multicast, NAT64 o IPv4-mapeadas con IP interna. También `localhost`, `*.local`, `*.internal`, los nombres de metadatos y las URL con usuario y contraseña.
- **Permite** los hosts internos legítimos (un Jira on-premise, un SMTP o un IMAP de la casa) solo si están declarados en `OUTBOUND_PRIVATE_HOSTS_ALLOWED`.
- **Cierra el DNS rebinding.** `cliente_httpx()`, `cliente_httpx_async()`, `peticion()` y `abrir()` validan la URL de cada petición y de cada redirección. Además comprueban la IP a la que el socket se ha conectado de verdad (`comprobar_conexion`) antes de enviar un byte. Si es interna lanzan `ConexionBloqueada` (no es un `OSError`, para que no se confunda con un destino caído).
- **Fija el origen al paginar.** Con `mismo_origen(base, siguiente)`, un `next` o un `@odata.nextLink` de la respuesta no puede llevarse el token a otro host.
- **Valida hosts sin URL** (SMTP, IMAP) con `validar_host_saliente(host)`.

### Dónde se aplica

| Salida | Origen de la URL | Cambio |
|---|---|---|
| Proveedor de IA (`ai_provider_service/clientes.py`, `gestion.py`, `ai_tools.py`) | `api_base_url` del admin de empresa | Se valida al guardar y al «probar sin guardar». La llamada pasa por `_http`: si el destino es el de plataforma (`settings.*_API_URL`, `OLLAMA_BASE_URL`), directo; si no, por el guardia con IP conectada. El cuerpo remoto ya no vuelve en el error salvo que el destino sea de plataforma (era un oráculo). |
| Webhooks salientes (`entrega_de_webhooks.py`, `enterprise_service/webhooks.py`) | Empresa | `cliente_httpx`, de modo que se comprueba la IP conectada (antes, `httpx.Client` tras validar: TOCTOU). La prueba ya no devuelve el cuerpo remoto. |
| Automatizaciones y flujos de reservas | Regla o flujo de empresa | Guardia central con HTTPS obligatorio y `abrir`/`cliente_httpx`. |
| Probar conexión (`integration_test_service.py`) | Empresa | Todas las sondas con `cliente_httpx`; el host SMTP con `validar_host_saliente`. |
| Credenciales de integración (`integration_credentials_service.set_credential`) | Empresa | Todo campo `*url*` o `host` se valida al guardar (02 M94). |
| Conectores contecmind y contecintelligence (`conectores/anfitrion.py`) | Empresa | `base_url` validada. Todas las llamadas, que llevan `client_secret` y tokens delegados, salen por `_SalidaSegura` (`cliente_httpx`). |
| Salesforce | `instance_url` de empresa | HTTPS, guardia e IP conectada. |
| CMDB de software: escaneos, fuentes, riesgo de terceros, escáneres | Empresa | `peticion`/`cliente_httpx`, paginación con el mismo origen y redirecciones solo sin credenciales. Las credenciales SSH/WinRM solo se usan contra los hosts que configuró el admin: un `hosts` de la petición fuera de esa lista se rechaza (`cmdb_host_no_configurado`, 02 A21). Esos hosts sí pueden ser privados, porque escanear la red propia es la función del módulo. |
| CMDB discovery (`cmdb/discovery.py`) | Empresa | Sin credenciales propias no se usan las del servidor: cadena por defecto de boto3, kubeconfig local o in-cluster, `DefaultAzureCredential`, ADC de GCP o un fichero de cuenta de servicio (02 A18). Se admite `kubeconfig` (YAML) y `service_account_json` dentro de la configuración cifrada. Se reactiva con `CMDB_DISCOVERY_ALLOW_PLATFORM_CREDENTIALS=1`. SNMP y vSphere apuntan a los hosts que configuró el admin con su propia credencial. |
| GitHub/GitLab de colaboración y del CAB | `api_base`/`base_url` de integración | `cliente_httpx_async`; en el CAB (GitHub Enterprise Server), desde el 23-11-2026 `cliente_httpx` en `cab_service.integraciones._pedir_github` (URL, redirecciones e **IP conectada**). Antes era `httpx.get` tras validar la URL, y el nombre se resolvía dos veces. El error ya no repite el cuerpo remoto ni el texto de la excepción. `tests/test_integraciones_reales.py` sustituye ahora `_pedir_github` en vez de `httpx.get` global, y comprueba además que la petición sale por `cliente_httpx` y que una conexión bloqueada no filtra la IP. |
| Buzón IMAP del service desk, SMTP de empresa | Empresa | Desde el 23-11-2026, **IP fijada** (§10): se valida el host, se conecta a esa IP sin volver a resolver y TLS verifica el nombre. El SMTP de plataforma (`SMTP_HOST`) no se toca. |
| Webhook de Teams (`m365.py`) | Empresa | `cliente_httpx_async`. |
| Región de Recall.ai y de Azure Speech | Ajuste de empresa | Solo una etiqueta DNS (`[a-z0-9-]`): la región iba dentro del host. |
| Metadatos de Bot Framework (`integrations_hub.py`) | Configuración | `abrir()` en vez de `urlopen`. |

### Salidas que quedan con `httpx` directo, y por qué son seguras

Medido el 23-11-2026 con `rg "httpx\.(get|post|…)\(|urlopen\("`: quedan 19 ficheros. Todos están en la lista `_SALIDAS_REVISADAS` del test, y cualquier fichero nuevo hace fallar el test.

- **Hosts fijos de plataforma** (`settings.*`, constantes del proveedor):
  - `bi_o365_service`, `m365_bi_embed_service` y `m365_service`: Microsoft OAuth y Graph; el tenant va en la ruta, no en el host;
  - `collaboration/_integrations` (token URL de `settings`) y `_integrations_clients` (Atlassian, Google y Graph);
  - `_transcription` (`OPENAI_API_URL`);
  - `exchange_rate_service` (BCE y OpenExchangeRates);
  - `stripe_service`;
  - `stt/google_stt` y `stt/openai_stt`;
  - `reuniones/conectores` (Zoom y Google Meet);
  - `buzones` (Graph; el IMAP sale por `Imap4SslFijado`, §10).
- **Host acotado:**
  - `teams_bot`: el `serviceUrl` debe coincidir con el del token firmado y estar en `TEAMS_BOT_ALLOWED_SERVICE_HOSTS`;
  - `canal_slack`: el `response_url` solo puede ser `hooks.slack.com`;
  - `recall` y `azure_stt`: la región se valida como etiqueta DNS.
- **Ya validado:** `cab_service/integraciones` (GHES por `cliente_httpx`; el `httpx` que queda es Google Calendar, host fijo) y `conectores/anfitrion` (su `httpx` es la salida segura).
- `core/outbound_url`: el propio guardia.

~~Riesgo residual: imaplib y smtplib resuelven el nombre por su cuenta.~~ Resuelto el 23-11-2026 (§10). Además, imaplib usaba por defecto un contexto TLS que **no** verificaba el certificado. Ahora usa `contexto_tls()`, como el SMTP.

## 2. Subidas y tamaño del cuerpo

- **Límite global:** `app/core/limite_de_cuerpo.py` es un middleware ASGI puro y el más externo. Si `Content-Length` supera `MAX_REQUEST_BODY_MB` (110 por defecto), responde 413 sin leer nada. Sin cabecera, o si la cabecera miente, cuenta los bytes según llegan y corta con 413 (`cuerpo_demasiado_grande`). nginx mantiene su `client_max_body_size`.
- **Todos los endpoints con `UploadFile`** leen con tope y validan tipo, bytes mágicos y nombre con `app/core/uploads.py` *antes* de procesar. Esto incluye el portal de demanda, el portal de proveedores (usuarios externos, perfil DOCUMENT), ausencias, demanda, proveedores, conectores (antes de reenviar a contecmind), las importaciones de CMDB (perfil nuevo `DATA_IMPORT`, 25 MB), políticas, documentos y audio (`validate_audio_upload`). Un test estático con `ast` impide un `.read()` sin tope.
- **Adjuntos del correo entrante del SD:** cada adjunto pasa por `safe_filename`, el tope `min(SD_MAIL_MAX_ATTACHMENT_MB, CHANNEL)` y `validate_upload(..., CHANNEL)`. Uno rechazado se anota en la nota de «no guardados» y el correo sigue; en el log solo quedan el id del ticket y el código.

## 3. Secretos en reposo

- **Slack `bot_token`:** se cifra con `encrypt_value` al guardar y se descifra al usar. Sin la clave en el formulario se conserva la guardada. Los valores antiguos en claro se siguen leyendo (`decrypt_value` los devuelve tal cual) y la próxima rotación los cifra (modo «valor»).
- **Comunidad SNMP:** ya no se escribe en los atributos del CI (`snmp_auth: community|usm`). Sigue cifrada en la configuración del proveedor. Los CIs existentes la pierden en el próximo descubrimiento, porque `reconcile` reescribe los atributos.
- **Secreto HMAC de los webhooks entrantes del CAB:** se guarda cifrado. Sin secreto y sin firma se devuelve el mismo 401, así que ya no se pueden enumerar slugs (01 B8).
- **Marketplace:** si el cifrado falla, ya no se guarda la configuración en claro como respaldo.
- **Rotación** (`key_management._secretos_a_recifrar`): ahora cubre todas las columnas cifradas:
  - `IntegrationCredential`, `JiraConfig`, `SoftwareConfig` (NVD y GHSA), `SlackConfig` y `WebhookTrigger`;
  - `ALMLicense`, `User.mfa_secret`, `CMDBDiscoveryProvider.config_json`, `IntegrationInstance`, `GDPRRequest.export_data`;
  - los tokens de colaboración (MultiFernet propio, `rotate`);
  - el JSON de `IntegrationConfig.config` y los ajustes con secretos anidados (BI ETL, BI O365, reuniones).

  Cada columna tiene su modo: `valor`, `prefijo`, `json` o `colab`. La rotación lee las filas de todas las empresas en un contexto de sistema declarado. Lo que no se puede descifrar no se toca y se avisa, sin escribir el valor.
- **Caché del llavero JWT:** dura `JWT_KEYRING_CACHE_SECONDS` (60 s) y un `kid` desconocido fuerza la recarga. Así, una rotación hecha en Celery llega a los procesos web sin reiniciar.

## 4. Redis y Celery

- **Contraseña:** `REDIS_PASSWORD` se pasa como `--requirepass` en docker-compose (también al exportador de métricas). La aplicación la inyecta en `REDIS_URL` si la URL no lleva credenciales (`app/core/redis_url.py`), y eso cubre Celery, rate limit, WebSocket y pub/sub. `setup docker` y `setup.sh` la generan si falta. Vacía, Redis arranca como antes.
- **`maxmemory-policy noeviction`:** Redis es el broker de Celery. Con `allkeys-lru` expulsaba en silencio tareas encoladas; ahora una escritura que no cabe falla y se ve en el log.
- **`ejecutar_en_segundo_plano`:** solo ejecuta `FUNCIONES_ENCOLABLES`, una lista blanca explícita de 18 funciones en `app/core/segundo_plano.py`. Antes valía cualquier `app.*`. `encolar` con una función fuera de la lista la ejecuta en línea, para no perderla, y lo avisa.

## 5. RGPD

- **Geo-IP (ipapi.co) apagado por defecto** (`GEOIP_LOOKUP_ENABLED=false`). Encenderlo transfiere la IP de cada inicio de sesión a un tercero fuera del EEE. Antes de hacerlo hacen falta:
  - base legal (interés legítimo con evaluación);
  - entrada en el registro de actividades de tratamiento;
  - contrato de encargo;
  - aviso de privacidad.

  Apagado, el riesgo de sesión usa solo las cabeceras `cf-ipcountry`/`x-asn` del proxy.
- **Fuentes (RGPD), resuelto 23-11-2026:** las tipografías (DM Sans y Geist 400-800, Geist Mono 400-500) se sirven desde el propio host con los paquetes `@fontsource/dm-sans`, `@fontsource/geist` y `@fontsource/geist-mono` (importados en `frontend/src/fuentes.ts`, que carga `main.tsx`). El navegador ya no pide nada a `fonts.googleapis.com` ni a `fonts.gstatic.com`, así que **la IP del visitante (operadores y clientes del portal) ya no llega a Google**. La CSP de `app/main.py`, `frontend/nginx.frontend.conf` y `vite.config.js` deja `font-src 'self' data:` y `style-src` sin Google. Se retira `VITE_FONTS_CSS_URL`. El chino sigue cayendo a la fuente del sistema, como antes (ninguna de las tres familias trae CJK).

## 6. Exportaciones CSV/XLSX

`app/core/celdas_seguras.py` antepone `'` a los textos que empiezan por `= + - @`, tabulador o salto de línea (también sus formas de ancho completo). Se aplica en:

- el exportador común (`exportador_tabular.py`, CSV y XLSX);
- el Excel de gastos;
- el CSV del constructor de informes.

Los números, también los negativos, siguen siendo números.

**Segunda ronda (23-11-2026).** Medido: los «~30 generadores» eran sobre todo filas JSON de `services/metrics/*` que no se escriben a fichero. Los ficheros de `app/` que escriben CSV/XLSX son 10. Antes neutralizaban 3 y ahora neutralizan los 10:

- `analytics_extended` (CSV de recursos);
- `bi_export_service` y `bi_report_delivery_service` (Excel BI);
- `clientes_internos/cargos` (CSV contable, solo los campos de texto: los importes ya son cadenas con formato y un negativo ganaría la comilla);
- `cmdb_software/analisis` (2 CSV);
- `m365_bi_embed_service`;
- `presupuestos_seguir`.

Ninguno pasa por el exportador común porque cambiaría su formato (`;`, `QUOTE_ALL`, hojas con estilo). `tests/test_exportaciones_sin_formulas.py` es estático: falla si un fichero de `app/` escribe CSV/XLSX (`csv.writer`, `DictWriter`, `Workbook(`, `ws.append`, `.cell(value=)`, `to_csv`/`to_excel`) sin importar `celdas_seguras` ni usar el exportador común. Su lista blanca solo contiene `celdas_seguras.py`. Límite conocido: una hoja con otro nombre de variable (`hoja.append`) en un fichero sin `Workbook(` ni `csv.writer(` no se detectaría.

## 7. Copia antes de migrar

`scripts/migrar.py`, que usan `setup.bat` y `setup.sh`, llama antes de `alembic upgrade head` a `scripts/copia_antes_de_migrar.py`:

- calcula las revisiones pendientes y detecta las destructivas en su `upgrade()` (`drop_table`, `drop_column`, `DELETE FROM`, `TRUNCATE`, `DROP`). Hay 14 de 147 en la cadena actual;
- **SQLite:** copia consistente con la API de backup de sqlite3, válida con la app arrancada y en modo WAL;
- **PostgreSQL:** `pg_dump -Fc` si está en el PATH, con la contraseña por `PGPASSWORD`. Si no está, avisa y sigue;
- si la copia falla, no migra (salida 1);
- se controla con `MIGRATION_BACKUP_MODE` (`destructive` por defecto, `always` u `off`) y `MIGRATION_BACKUP_DIR` (`backups/`, ignorado por git).

**GRC:** las copias contienen datos personales. Deben tener el mismo control de acceso que la base y retención limitada: borrar las copias de migración cuando la nueva versión esté validada (recomendado ≤ 30 días). Quedan fuera de la supresión RGPD por persona hasta que se borran, así que esa retención debe figurar en el registro de tratamientos.

## 8. Ajustes nuevos

Están en `app/core/config_groups/seguridad_salida_config.py`, docs/REFERENCIA_DE_AJUSTES.md y `.env.example`:

- `MAX_REQUEST_BODY_MB`
- `CMDB_DISCOVERY_ALLOW_PLATFORM_CREDENTIALS`
- `JWT_KEYRING_CACHE_SECONDS`
- `MIGRATION_BACKUP_MODE`
- `MIGRATION_BACKUP_DIR`
- `REDIS_PASSWORD`
- `M365_PLATFORM_CREDENTIALS_ENABLED` (23-11-2026, §11)

Cambia el valor por defecto de `GEOIP_LOOKUP_ENABLED`, que ahora es `false`.

## 9. Auditoría, privilegios y retención

- **Auditoría:** los cambios de credenciales de integración siguen en `record_change`, que guarda el hash del valor cifrado. Las salidas bloqueadas por el guardia quedan en el log con el host y el motivo, nunca con el secreto. En los webhooks también quedan en `WebhookDelivery` como `blocked`.
- **Privilegios:**
  - las credenciales de plataforma de la CMDB pasan a ser opt-in del operador, no del admin de empresa;
  - el relé SSH/WinRM queda limitado a los hosts del admin;
  - el worker ya no ejecuta funciones arbitrarias.
- **Datos personales:** los adjuntos rechazados se registran sin nombre de fichero ni remitente.

## 10. Correo: IP fijada (anti DNS rebinding, 23-11-2026)

`app/core/conexion_fijada.py`:

- `ip_fijada(host)` valida el host con el guardia y devuelve una de sus IPs.
  - Si el host **no resuelve**, se rechaza (`host_no_resuelve`). Antes pasaba, y la resolución de la conexión podía dar una IP interna.
  - Un host de `OUTBOUND_PRIVATE_HOSTS_ALLOWED` devuelve `None` y se conecta por nombre, como antes.
- `socket_fijado` abre el socket contra esa IP y comprueba la IP del otro extremo (`comprobar_conexion`).
- `Imap4SslFijado` (buzón del service desk: lectura y «probar») y `SmtpFijado`/`SmtpSslFijado` conectan a la IP. Los dos SMTP viven en `notification_service`, el único módulo que importa `smtplib`.
- La negociación TLS usa el **nombre** configurado: SNI, certificado y STARTTLS siguen siendo los del host, y un servidor que no presente un certificado válido para su nombre se rechaza.
- El IMAP pasa además `contexto_tls()`. Antes imaplib no verificaba el certificado.
- `SMTP_TLS_VERIFY=false` relaja la verificación en los dos protocolos, solo para un relay interno autofirmado.

El SMTP de plataforma (`SMTP_HOST` del entorno) no pasa por aquí: es configuración del operador.

## 11. Microsoft 365 / Graph por empresa (03 A-MP3, 23-11-2026)

Antes, todo Graph salía con los `AZURE_TENANT_ID/CLIENT_ID/CLIENT_SECRET` globales: calendario, presencia, Planner, pestañas y tarjetas de Teams, páginas de SharePoint y OneDrive. Una única aplicación de Azure, con permisos de aplicación sobre **todo** su tenant, servía a todas las empresas. Ahora (`app/services/m365_service.py`):

- **Credencial por empresa:** cada empresa guarda la suya en el almacén cifrado (`ms_graph`: `tenant_id`, `client_id`, `client_secret` cifrado). `credenciales_de_graph(db, empresa)` la lee sin caer al entorno.
- **Credencial a medias:** no se completa con la de plataforma, porque mezclaría tenants. Cuenta como no configurada (503).
- **Token por credencial:** se cachea por (tenant, client id, huella del secreto) hasta 2 minutos antes de caducar. Cambiar el secreto invalida la entrada.
- **Credencial de plataforma:** los `AZURE_*` solo se usan si el operador activa `M365_PLATFORM_CREDENTIALS_ENABLED`, y solo para una empresa sin credencial propia. El estado (`GET /m365/status`, `credential_source`) dice si se usa la de la `empresa` o la de `plataforma`.
- **Empresa activa:** todos los endpoints de `m365.py` y `m365_bi.py` usan la empresa activa del usuario. También la usan el buzón Graph del service desk (`buzones._token_graph`, antes `get_provider_config`, que caía al entorno) y el informe de uso de O365 (`bi_o365_service`).
- **Entradas validadas:**
  - `tenant_id` (va en la ruta del token) solo admite un GUID o un dominio;
  - los identificadores de equipo, canal, sitio y plan pasan por `id_de_graph`, de modo que no pueden cambiar la ruta de Graph (`m365_id_no_valido`).
- **Errores sin texto remoto:** el error de OneDrive y el de registrar una pestaña ya no repiten la respuesta remota.
- **Probar conexión** (`POST /settings/integrations/ms_graph/test`): pide el token con la credencial de la empresa y lee `/organization`, el propio tenant.

Con credencial propia, los equipos, canales y sitios alcanzables son los del tenant de esa empresa, que es justo lo que su aplicación de Azure autoriza. Con la de plataforma, sigue valiendo para todo el tenant del operador. Por eso es opt-in, y en esa configuración el aislamiento depende de la validación de UPN (`buzon_de_la_organizacion`).

**Pendiente (dato, no código):** las empresas que hoy funcionan con los `AZURE_*` globales dejan de tener Graph al actualizar hasta que guarden su credencial o el operador active `M365_PLATFORM_CREDENTIALS_ENABLED`. Es intencionado y hay que avisarlo en la nota de versión.

## 12. Pruebas de conexión: qué verifican de verdad

Cada prueba dice qué ha comprobado contra el servicio real (`verificado`): `nada`, `configuracion`, `alcance`, `credencial`, `credencial_y_uso` o `pasivo`. La tabla por conector, y lo que solo se puede verificar con las credenciales reales del usuario, está en [docs/integraciones/pruebas_de_conexion.md](../integraciones/pruebas_de_conexion.md).
