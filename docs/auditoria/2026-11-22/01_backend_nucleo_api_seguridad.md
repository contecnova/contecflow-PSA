# Auditoría 2026-11-22 · 01 · Backend: núcleo, API y seguridad

Zona: `app/core`, `app/db`, `app/api` (210 ficheros), `app/main.py`, `app/worker.py`, `alembic/`, `setup.bat`, `setup.sh`, `docker-compose.yml`, `deploy/Dockerfile.*`, `ops/`, `scripts/`, `.env.example`, `requirements*.txt`.

Auditoría de solo lectura: no se ha cambiado código ni se ha ejecutado la suite de tests. Las cifras de rutas salen de importar `app.main` y recorrer `app.routes` con su grafo de dependencias (script en el scratchpad, sin escribir en la base). Lo que no se ha comprobado lleva la marca **«sin verificar»**.

---

## 1. Resumen: qué es y cómo funciona

API FastAPI síncrona (SQLAlchemy ORM, `def` en el threadpool) con multiempresa en la misma base. La seguridad se monta en capas:

1. **Autenticación** (`app/core/deps.py::get_current_user`). Acepta un JWT de acceso por `Authorization: Bearer` o por la cookie `access_token` (httpOnly, SameSite=Lax, Secure en staging y producción), y también credenciales delegadas (`app/core/credenciales_delegadas.py`): claves de API `nxpm_…` / `X-API-Key` y tokens OAuth del portal de desarrolladores. Estas últimas se buscan por SHA-256 y se recortan por alcance (`read`/`write`/`admin` o por área). Los JWT van firmados con un llavero rotado que vive en la base (`services/key_management`, `kid` en la cabecera). El refresh rota el JTI por sesión, va en una cookie SameSite=Strict con `path=/api/v1/auth` y detecta la reutilización. Los tokens de uso concreto (BI embed, WS…) se rechazan como sesión (`TOKENS_DE_USO_CONCRETO`). Hay MFA (TOTP/WebAuthn), passkeys, SSO OIDC/SAML y SCIM por empresa con su token.
2. **Empresa activa**. `entrada_service.organizacion_de_la_peticion` valida el claim `org` del token frente a las pertenencias (`UserOrganizationMembership`), lo fija en memoria en `user.organization_id` y lo publica en `db.info["organization_id"]`. El superadmin publica `organization_id=None` e `is_superadmin=True`.
3. **Aislamiento entre empresas, con tres capas en el ORM** (`app/db/session.py`): `TenantSession.query()`, `TenantSession.execute(Select)` y el escuchador `do_orm_execute`, que usa `with_loader_criteria`. Las tres fallan en cerrado (`TenantIsolationError`) si un modelo no tiene columna de empresa. Al hacer flush se sella `organization_id` en las filas nuevas. Hay una cuarta capa en Postgres con **RLS** (`app/db/rls.py`): política por tabla y GUC `app.tenant` por transacción.
4. **Autorización**:
   - por rol: `RequireRole` y los atajos `require_admin`, `require_any_manager`…;
   - por **capacidad**: `requiere_capacidad("x")`, contra la matriz de `app/core/capacidades.py`;
   - por **módulo del rol personalizado** (`app/core/modulos.py`, que solo restringe);
   - por **permisos por proyecto** (`app/core/permisos_de_proyecto.py`);
   - **ABAC** en modo fail-open: dependencia global del router (`abac_dependency.py`) más 260 llamadas `enforce_abac(...)` en los endpoints;
   - **matriz GRC** de denegación aditiva (`grc_enforce.py`), que también es dependencia global.
5. **Transversales** (`app/main.py`):
   - CSRF por Origin/Referer, con doble envío opcional;
   - CORS con lista y CORS abierto solo para `/forms/public/`;
   - cabeceras de seguridad (CSP, HSTS en producción, COOP/CORP);
   - SlowAPI con límite por defecto `200/minute` por usuario o IP y 136 `@limiter.limit` propios;
   - saneado de errores y códigos estables (`codigos_de_error.py`, `validacion.py`);
   - métricas Prometheus con Bearer (`metrics.py`, `metricas_empresa.py`);
   - Sentry/OTel opcionales;
   - comprobaciones de arranque: deriva de esquema, planificador dual, bypass de superadmin, CSRF y RLS.
6. **GRC de datos**:
   - bloqueo legal en `before_flush` (`app/db/bloqueo_legal.py`);
   - cadena de auditoría HMAC encadenada por empresa con exportación firmada Ed25519 (`app/db/cadena_auditoria.py`);
   - cifrado de credenciales Fernet/HKDF derivado de `SECRET_KEY` (`app/core/encryption.py`).
7. **Trabajos de fondo**. Celery en `app/worker.py` (58 tareas, `beat_schedule` con ~50 entradas, Redis como broker y backend). Las mismas entradas se replican en APScheduler si `ENABLE_APSCHEDULER=1`, y el arranque se niega al modo dual.
8. **Despliegue**. Un solo `docker-compose.yml` con perfiles `app`, `s3`, `observability` y `host-metrics`: puertos en 127.0.0.1, volúmenes de datos `external`, migración one-shot (`alembic upgrade head && python -m app.db.rls`) y nginx delante. `setup.sh`/`setup.bat` son la entrada local; el modo `docker` de los dos delega en `scripts/docker_stack.py`.

---

## 2. Inventario medido

| Elemento | Medida |
|---|---|
| `app/api` | 210 ficheros `.py`, 52 154 líneas (146 en `endpoints/`, 35 en `service_desk/`, 10 en `collaboration/`, 11 en `routers/`) |
| Rutas registradas (`app.routes`) | **2 751**: GET 1 146 · POST 1 046 · DELETE 254 · PATCH 224 · PUT 72 · WS 6 · HEAD 2 · OPTIONS 1 · 195 módulos con rutas · 0 rutas duplicadas (método+ruta) |
| Rutas con guarda de **capacidad** | 492 |
| Rutas con guarda **solo de rol** (sin capacidad) | 1 421 (`admin,pm,team_lead,hr` 475 · `admin` 404 · internos 285 · `admin,pm` 223 · con externos 34 · `admin,hr` 5) |
| Rutas solo con usuario autenticado (o una guarda local) | 734, de ellas 142 mutables |
| Rutas `require_superadmin` | 11 |
| Rutas sin ninguna dependencia de autenticación | **93** (50 mutables): webhooks firmados, login/MFA/SSO, formularios públicos, SCIM (token propio), WS (ticket propio), health/status |
| Módulos de `app/api/v1` sin rutas propias | 12, todos agregadores (`router.py`, `routers/{core,delivery,ai_domain,platform,framework}.py`, `endpoints/auth.py` y los `__init__`). **Ningún módulo de endpoints huérfano** |
| `enforce_abac(` en `app/api` | 260 |
| `@limiter.limit` en `app/api` | 136 |
| `raise HTTPException(` directos en `app/api` (sin código de catálogo) | 70 en 20 ficheros (19 en `enterprise.py`) |
| `except Exception` en la zona | 203 |
| TODO/FIXME/XXX/HACK en la zona | 10 |
| `app/core` | 53 módulos, 10 986 líneas, más `config_groups/` (17 ficheros, 968 líneas) |
| `app/db` | 21 ficheros (con `seed_parts`), 3 932 líneas |
| Modelos ORM | 537: 525 con `organization_id`, 11 con `org_id`, 1 exento (`Organization`) y **0 sin columna de empresa** |
| Alembic | 147 revisiones, 22 046 líneas, **una sola cabeza** (`195_flujo_de_demanda`), una raíz (`001_initial_tables`), 0 merges, 0 bifurcaciones, 0 `down_revision` colgantes. Numeración con huecos (147 ficheros para el número 195) |
| Migraciones con `drop_table`/`DELETE`, o con downgrade vacío | 18 (110, 111, 144, 146, 156, 160, 166 y 173 con `drop_table`; 124, 135, 149, 150, 159 y 185 con `DELETE`; 112, 135, 153, 155 y 185 con downgrade `pass`) |
| Subidas `UploadFile` | 17 ficheros: 6 usan el validador central (`read_and_validate_upload`/`validate_upload`) y 11 no lo usan en el endpoint |
| HTTP saliente | 33 ficheros de `app/` con `httpx`/`requests`/`urlopen`; 30 no referencian `app/core/outbound_url.py` (ver M7) |
| `requirements.txt` / `-ml` | 112 y 18 dependencias, todas con `==`, sin `--require-hashes` |
| `scripts/` | 53 ficheros, 7 365 líneas |
| `ops/` | 13 ficheros (Prometheus + 2 reglas, Alertmanager, Grafana con 6 dashboards) |
| `setup.sh` / `setup.bat` | 1 469 / 1 028 líneas |

---

## 3. Hallazgos por severidad

### CRÍTICA

#### C1. `.env` con secretos reales versionado en git
- ⏸ pendiente (decisión del usuario) 23-11-2026: `.env` sigue en git (`git ls-files .env`). La regla de esta ronda es no tocar `.env` ni hacer commits: sacarlo del índice (`git rm --cached .env`, `.env` en `.gitignore`), rotar `SECRET_KEY`/`CLIENT_PORTAL_SECRET`/`SUPERADMIN_PASSWORD`/`DEFAULT_USER_PASSWORD` y decidir si se purga el historial son pasos del dueño del repositorio. RLS (A1), Redis (M5) y Docker ya generan sus secretos locales.
- **Dónde.** `.env`, seguido desde el commit `834b6d5a` («El .env se versiona») y modificado en `9850be66`. `git ls-files` lo lista.
- **Evidencia.** `git show HEAD:.env` contiene (valores no copiados aquí) `DATABASE_URL`, `SECRET_KEY`, `CLIENT_PORTAL_SECRET`, `SUPERADMIN_EMAIL`, `SUPERADMIN_PASSWORD`, `DEFAULT_USER_PASSWORD`, `AI_API_KEY` y `ANTHROPIC_API_KEY` (estas dos vacías en HEAD). La copia de trabajo está modificada (`git status`: ` M .env`), porque `setup.sh` la reescribe (en `preparar_rol_de_aplicacion`, `setup.sh:888-896`, pone `APP_DB_PASSWORD` y `DATABASE_URL` con contraseña).
- **Impacto.** Quien tenga el repositorio (o una copia: OneDrive, un clon, un backup) tiene:
  - la clave de firma derivada y el cifrado de credenciales de integraciones (`app/core/encryption.py:12-87` deriva de `SECRET_KEY`);
  - la clave HMAC de la cadena de auditoría y la Ed25519 de las exportaciones firmadas (`app/db/cadena_auditoria.py:9-12, 25-27`), con lo que puede falsificar el registro «a prueba de manipulación»;
  - el secreto del portal de clientes (falsifica tokens de cliente, `security.py::verify_client_token`);
  - la contraseña del superadmin.

  `docker-compose.yml` monta ese mismo `.env` (`env_file: [.env]`) en api/worker/beat, así que el stack de producción Docker usaría esos secretos. Además contradice la norma del usuario («no subir .env») y la propia cabecera de `.dockerignore`. El siguiente `git commit -a` subiría también las credenciales locales que `setup.sh` escribe.
- **Arreglo.** `git rm --cached .env` y `.env` en `.gitignore`. Rotar `SECRET_KEY` (con `SECRET_KEY_PREVIOUS` y `scripts/reencrypt_secrets.py`), `CLIENT_PORTAL_SECRET`, `SUPERADMIN_PASSWORD` y `DEFAULT_USER_PASSWORD`. Decidir si se purga el historial. Separar la clave de la cadena de auditoría y la de cifrado de `SECRET_KEY` (claves propias o KMS).

### ALTA

#### A1. RLS desarmado en el stack Docker y en Windows; solo `setup.sh` lo arma
- ✅ arreglado 23-11-2026: lógica única `scripts/rol_de_aplicacion.py` (la llaman `setup.sh` y `setup.bat` → `:prepare_app_role`, tras migrar y en `update`); `docker_stack.py` genera `APP_DB_USER`/`APP_DB_PASSWORD`; el compose ya no cae al superusuario (`${APP_DB_USER:-contecflow_app}:${APP_DB_PASSWORD:-}`); el arranque se niega con RLS desarmado en staging/production (`RLS_REQUIRED`, `main._avisar_si_rls_desarmada`). Sin probar en un Docker real (no se tocaron los volúmenes).
- **Dónde.**
  - `docker-compose.yml:69`: `DATABASE_URL: postgresql+psycopg2://${APP_DB_USER:-${POSTGRES_USER}}:${APP_DB_PASSWORD:-${POSTGRES_PASSWORD}}@…`.
  - `scripts/docker_stack.py` (sin ninguna aparición de `APP_DB_USER`).
  - `setup.bat` (ninguna aparición).
  - `setup.sh:860-905` (`preparar_rol_de_aplicacion`, la única que crea el rol).
- **Evidencia.** Sin `APP_DB_USER` en el `.env`, la API, el worker y el beat conectan como `POSTGRES_USER`, el superusuario que crea la imagen `postgres`. `rls.estado()` (`app/db/rls.py`) lo detecta («se salta RLS (superusuario o BYPASSRLS)»), pero solo lo avisa en el log (`main.py::_avisar_si_rls_desarmada`).
- **Impacto.** La red de aislamiento en la base, documentada como cuarta capa, no actúa precisamente en el despliegue de producción (`setup docker` / `--profile app`) ni en Windows. Cualquier SQL a mano o fallo del filtro ORM queda sin respaldo. Los dos lanzadores no hacen lo mismo, contra la regla «setup siempre al día».
- **Arreglo.** Que `docker_stack.py` (y por tanto `setup.bat docker`) genere `APP_DB_USER`/`APP_DB_PASSWORD` al completar el `.env`, como `setup.sh`. En `production`/`staging`, que el arranque falle si `rls.estado()["armed"]` es `False` (hoy solo avisa).

#### A2. Las credenciales delegadas (clave de API y token OAuth) se saltan la matriz GRC y la capa ABAC global
- ✅ arreglado 23-11-2026: GRC (`grc_enforce.aplicar_a_principal`) y ABAC (`abac_dependency.aplicar_abac_a_principal`) se aplican dentro de `get_current_user` (`deps._aplicar_politicas`), en las dos ramas (JWT y credencial delegada), tras publicar la empresa. Las guardas globales solo deciden en rutas que no resuelven el usuario con `get_current_user` (`credenciales_opcionales.ruta_resuelve_usuario`). Verificado: `test_EL_HALLAZGO_una_clave_de_api_respeta_la_matriz_grc` (403 `grc_politica_deniega` con `X-API-Key`).
- **Dónde.** `app/core/grc_enforce.py::_resolve_user` (solo decodifica JWT: `decode_token(token)`, `payload.get("type") != "access"` → `None`) y `app/core/abac_dependency.py:118-133` (igual).
- **Evidencia.** Con `X-API-Key: nxpm_…`, o `Bearer nxpm_…` / un token OAuth opaco, `decode_token` devuelve `None`, las dos dependencias globales hacen `return` («sin usuario: la guarda del endpoint decide») y luego `get_current_user` acepta la credencial (`deps.py:34-36`). `grc_enforce.decidir` nunca se evalúa.
- **Impacto.** Si un administrador de empresa deniega un módulo a un rol en la matriz GRC, ese mismo usuario puede llegar a él con una clave de API o una app OAuth. La garantía declarada («lo que un administrador prohíbe, queda prohibido», `grc_enforce.py`) no se cumple con credenciales delegadas. Lo mismo vale para las políticas ABAC de prefijo sin `enforce_abac` explícito.
- **Arreglo.** Resolver el principal una sola vez (dependencia que reutilice `credenciales_delegadas.resolver`) y aplicar GRC/ABAC sobre ese principal. Lo más sencillo es mover GRC y ABAC dentro de `get_current_user`, después de fijar la empresa, como ya hacen `modulos.comprobar` y `permisos_de_proyecto.comprobar`.

### MEDIA

#### M1. La capa ABAC global evalúa con la empresa de ficha, no con la activa
- ✅ arreglado 23-11-2026: en `get_current_user` ABAC corre con la empresa activa ya fijada; en la guarda global residual, `fijar_organizacion_activa(db, user, payload['org'])` (validada) antes de `enforce_abac`.
- **Dónde.** `abac_dependency.py:133`: `user = db.query(User)…first()`, seguido de `enforce_abac(db, user, …)`. `abac_enforce.py` usa `user.organization_id`.
- **Evidencia.** Las dependencias del router (`_ROUTER_GUARDS`, `main.py`) se resuelven antes que las del endpoint, así que `organizacion_de_la_peticion` todavía no ha fijado la empresa del token en memoria. La GRC sí lo corrige (`request.state.grc_org = payload.get("org")`) y la ABAC no.
- **Impacto.** Para usuarios con varias empresas se aplican las políticas ABAC de otra empresa: deniegan de más o no aplican las de la empresa activa.
- **Arreglo.** Igual que en A2: evaluar después de `get_current_user`, o usar el `org` del payload validado.

#### M2. El token OAuth de una app no hereda la empresa de la app
- ✅ arreglado 23-11-2026: `create_token(..., organization_id=app.organization_id)` dentro de `con_empresa`; se exige que el dueño pertenezca a la empresa de la app (401 `credencial_dueno_fuera_de_empresa`) y una app sin empresa no emite tokens (400 `oauth_app_sin_empresa`, nuevo, es/en/zh). Verificado con dos tests.
- **Dónde.** `app/api/v1/endpoints/developer_portal.py:206` (`svc.create_token(...)` sin organización) y `app/services/developer_portal_service.py:107-114` (`OAuthToken(...)` sin `organization_id`).
- **Evidencia.** La petición es anónima, así que `_sellar_organizacion` (`session.py:799-821`) deriva la empresa del `user_id`, que es la empresa de ficha del dueño. Después `deps._usuario_de_credencial_delegada` trabaja en `token.organization_id`.
- **Impacto.** Si el dueño creó la app en la empresa B pero su ficha es A, la app de terceros lee y escribe en A. Es el mismo defecto que la «revisión multitenant 2026-11b» ya corrigió para las claves de API.
- **Arreglo.** `create_token(..., organization_id=app.organization_id)` y comprobar la pertenencia del dueño a esa empresa.

#### M3. CSRF no cubre la cookie del portal de clientes, que además no es `Secure` en staging
- ✅ arreglado 23-11-2026: `csrf.COOKIES_DE_SESION` incluye `portal_access_token`; el portal pone y borra su cookie con `COOKIE_OPTS` (Secure en staging y producción) y emite `csrf_token` al entrar; el refresco del frontend (`_core.ts::refrescarSesion`, axios directo) manda `X-CSRF-Token`.
- **Dónde.** `app/core/csrf.py:106-112` (`has_cookie = bool(request.cookies.get("access_token") or request.cookies.get("refresh_token"))`) y `app/api/v1/endpoints/client_portal.py:255-260` (`secure=settings.ENVIRONMENT == "production"`).
- **Impacto.** Las rutas del portal autenticadas por la cookie `portal_access_token` no pasan la comprobación de Origin. SameSite=Lax lo mitiga desde sitios ajenos, pero no desde subdominios hermanos. En staging la cookie viaja por HTTP. Es incoherente con `COOKIE_OPTS` (`secure` en `{"production","staging"}`).
- **Arreglo.** Incluir `portal_access_token` en `_uses_cookie_auth` y usar `COOKIE_OPTS` en el portal.

#### M4. Subidas leídas enteras en memoria antes de validar; 11 de 17 endpoints no usan el validador central
- **Dónde.**
  - `ausencias.py:340` y `demanda.py:356` (`file.file.read()`);
  - `portal_demanda.py:146` y `proveedores_portal.py:81` (**usuarios externos**);
  - `proveedores.py:320`, `collaboration/calls.py:110` y `conectores.py:143` (`await file.read()`, que reenvía a contecmind sin validar el tipo);
  - `cmdb_riesgo.py:212-228` y `cmdb_software.py:460/636` (importaciones);
  - `politicas.py:148` y `reuniones.py:207` (estos dos sí acotan la lectura).
- **Evidencia.** Los servicios de ausencias, demanda y proveedores validan después (`validate_upload`), con el fichero ya entero en memoria. En la app no hay límite global de cuerpo: solo nginx en Docker (`client_max_body_size 110m`, `frontend/nginx.frontend.conf:54`). En local, uvicorn se expone en `0.0.0.0` sin límite (ver B2).
- **Impacto.** Agotamiento de memoria con subidas concurrentes, incluido el que pueden provocar usuarios del portal o de proveedores. La validación de tipo es desigual entre puntos de subida (`app/core/uploads.py` lo documentaba como problema resuelto).
- **Arreglo.** `read_and_validate_upload(file, perfil)` en los 11 endpoints y un límite de cuerpo en la app (middleware ASGI por `Content-Length` y conteo de bytes).
- ✅ arreglado 23-11-2026: límite global de cuerpo (`app/core/limite_de_cuerpo.py`, ASGI puro, `MAX_REQUEST_BODY_MB`=110: 413 por Content-Length y por bytes contados); los 17+ endpoints con `UploadFile` leen con tope y validan con `app/core/uploads.py` antes de procesar (portal de demanda y de proveedores con DOCUMENT; conectores antes de reenviar; CMDB con perfil nuevo `DATA_IMPORT`; audio con `validate_audio_upload`); adjuntos del correo entrante con `validate_upload(CHANNEL)`. Verificado: `tests/test_subidas_validador_central.py` (ast: ningún `.read()` sin tope) y `test_el_cuerpo_grande_da_413_por_cabecera_y_por_bytes`.

#### M5. Redis: el broker usa `allkeys-lru`, no tiene contraseña y existe una tarea que ejecuta cualquier función `app.*`
- **Dónde.**
  - `docker-compose.yml:126-135` (`--maxmemory-policy allkeys-lru`, sin `requirepass`);
  - `app/worker.py:405-409` (`ejecutar_en_segundo_plano(ruta, args, kwargs)` → `resolver(ruta)(*args, **kwargs)`);
  - `app/core/segundo_plano.py:61` (solo exige `modulo.startswith("app.")`).
- **Impacto.**
  - Con memoria llena, Redis evicta mensajes encolados de Celery, tickets de WebSocket y contadores de rate limit, sin error.
  - Cualquier proceso del host (puerto en 127.0.0.1:6381) o de la red de compose puede encolar la ejecución de cualquier función importable de `app.*` con argumentos arbitrarios: borrados masivos, `app.db.rls.main`, etc.
- **Arreglo.**
  - `noeviction` para la base del broker, o un Redis aparte para la caché.
  - `requirepass`/ACL en Redis.
  - Lista blanca explícita de rutas en `segundo_plano.resolver`, por ejemplo con un decorador `@encolable`.
- ✅ arreglado 23-11-2026: `noeviction` en el compose; `REDIS_PASSWORD` → `--requirepass` (y exportador), inyectada en `REDIS_URL` (`app/core/redis_url.py`), generada por `docker_stack.py`/`setup.sh`; `ejecutar_en_segundo_plano` solo resuelve `FUNCIONES_ENCOLABLES` (18 rutas explícitas). Verificado: `test_el_worker_solo_ejecuta_la_lista_blanca`, `test_compose_redis_noeviction_y_contrasena`, `test_la_contrasena_de_redis_entra_en_la_url`.

#### M6. La geolocalización de IP está activada por defecto y envía la IP de cada login a un tercero; el código dice lo contrario
- **Dónde.** `app/core/config_groups/proceso_config.py:114-116` (`GEOIP_LOOKUP_ENABLED … default=True` con `https://ipapi.co/{ip}/json/`) frente a `app/services/session_security.py:98` («Apagado por defecto (`GEOIP_LOOKUP_ENABLED=0`)»).
- **Impacto.** Transferencia de datos personales (IP) a un encargado externo fuera del EEE sin que el comentario ni el operador lo sepan. Riesgo RGPD: hace falta base legal, registro de actividades y contrato de encargo.
- **Arreglo.** Poner `False` por defecto (o documentarlo de verdad en `.env.example`/DOCS y en el registro de tratamientos) y corregir el comentario.
- ✅ arreglado 23-11-2026: `GEOIP_LOOKUP_ENABLED=False` por defecto (config, `.env.example`, README, DOCS) y requisitos RGPD documentados en `docs/seguridad/entrada_y_salida.md`.

#### M7. Tres validadores SSRF distintos y 30 ficheros con HTTP saliente que no usan el central
- **Dónde.**
  - `app/core/outbound_url.py` (el completo: valida resolución, redirecciones e IP final);
  - `app/services/enterprise_service/webhooks.py:34-44` (lista de redes propia);
  - `app/services/auth_service.validate_https_discovery_url`, que usa `integrations_hub.py:385-397` con `urllib.request.urlopen` sin fijar la IP.

  Los 30 ficheros sin referencia al guardia central se listan con `rg` (p. ej. `entrega_de_webhooks.py`, `cab_service/integraciones.py`, `conectores/anfitrion.py`, `integration_test_service.py`, `m365_service.py`).
- **Evidencia.** `entrega_de_webhooks.py:84-118` revalida la URL con su propio validador y conecta con un `httpx.Client` normal: queda abierta una ventana TOCTOU/DNS rebinding que `outbound_url.cliente_httpx` sí cierra.
- **Impacto.** SSRF residual hacia redes internas o metadatos de nube según el destino. La mayoría son URLs de configuración de administrador; caso a caso, **sin verificar** (los servicios están fuera de mi zona).
- **Arreglo.** Un solo validador (`outbound_url`) y `cliente_httpx()`/`abrir()` obligatorios. Un test que prohíba `httpx.(get|post|Client)` fuera de `outbound_url`.
- ✅ arreglado 23-11-2026: un solo guardia (`app/core/outbound_url.py`): los validadores de webhooks, automatizaciones, reservas, OIDC y `network.assert_safe_outbound_url` delegan; bloquea todo lo no global (CGN, NAT64, mapeadas, metadatos, credenciales en URL); `cliente_httpx`/`cliente_httpx_async`/`peticion`/`abrir` comprueban la IP conectada (rebinding) y cada redirección. Aplicado en IA, webhooks, sondas, credenciales al guardar, conectores, Salesforce, CMDB, GitHub/GitLab, IMAP/SMTP de empresa, Teams. Quedan 19 ficheros con `httpx` directo, todos de host fijo o acotado, listados con su motivo en el doc y en el test. Verificado: `test_no_hay_otro_validador_ssrf`, `test_nadie_nuevo_llama_a_httpx_sin_el_guardia`, `test_la_ip_conectada_se_comprueba_aunque_la_url_haya_pasado`.
- ✅ Segunda ronda, 23-11-2026: el riesgo residual del correo queda cerrado (`app/core/conexion_fijada.py`).
  - El SMTP de empresa y el IMAP conectan a la IP ya validada sin volver a resolver. TLS verifica el nombre.
  - Un host que no resuelve se rechaza.
  - El GitHub Enterprise del CAB sale por `cliente_httpx` (`_pedir_github`), con la IP conectada comprobada. `tests/test_integraciones_reales.py` sustituye esa costura en vez de `httpx.get`.
  - Verificado: los tests de IP fijada y GHES de `tests/test_ronda2_transversal_2026_11_23.py` y `tests/test_integraciones_reales.py`.

#### M8. Las rutas anónimas no tienen ninguna red de aislamiento
- ✅ arreglado 23-11-2026: las 93 rutas anónimas (medidas recorriendo `app.routes` y su grafo de dependencias) verifican su credencial propia y declaran su contexto. Mientras buscan la credencial, su sesión es `Depends(sesion_de_sistema("<motivo>"))`. En cuanto la firma, el token o el slug dan la empresa, la **publican** (`publicar_empresa`/`publicar_contexto_de_tenant`): SCIM, formularios públicos, vista de proyecto, CAB, Jira ×2, Twilio, monitorización, Slack, WebSockets y portal. 13 no abren sesión ORM y figuran en una lista con su motivo. Ninguna se encontró sin verificar su credencial.
  - Las `SessionLocal()` a mano de `app/` declaran su contexto con `declarar_sistema` o `fijar_contexto`: de 48 sitios con código, 42 no declaraban nada; hoy declaran todos salvo `get_db`/`worker_db_session` (los declara quien los usa).
 También lo hacen `segundo_plano`, la siembra, los scripts y `setup.bat`/`setup.sh`.
  - **El defecto de `TENANT_SESION_SIN_CONTEXTO` pasa a `cerrar`** (config, `.env.example`, README y DESPLIEGUE): una sesión sin contexto lanza `TenantIsolationError` y RLS no devuelve filas. `avisar` queda solo para localizar un sitio.
  - Tabla ruta → credencial → empresa: `docs/seguridad/rutas_anonimas.md`.
  - Verificado: `tests/test_rutas_anonimas_contexto_2026_11.py` (recuento exacto, contexto por ruta, sesiones a mano, comportamiento con `cerrar`).

- **Dónde.** `app/db/session.py:276-279` y `:476-478` (`is_superadmin is None` → sin filtro) y `app/db/rls.py:142` (`tenant_de` devuelve `""`, es decir, sin restricción, si `is_superadmin is not False`).
- **Evidencia.** Las 93 rutas sin autenticación (50 mutables: webhooks, formularios públicos, login del portal, SCIM, eventos de monitorización, correo entrante) trabajan con una sesión sin contexto. Ni el ORM ni RLS filtran, y todo depende de que cada servicio acote a mano. Ejemplo de que se puede hacer bien: `status_page_service.organizacion_de_la_pagina`.
- **Impacto.** Un fallo de acotado en cualquiera de esas rutas es una fuga entre empresas sin red debajo.
- **Arreglo.** Que cada ruta pública publique su empresa con `publicar_contexto_de_tenant` en cuanto la resuelve (token, slug o firma). Un test que recorra las 93 rutas y exija esa llamada o una exención razonada.

#### M9. La autorización sigue siendo mayoritariamente por rol; hay guardas locales que duplican y divergen
- ✅ arreglado 23-11-2026 (ronda 2): **ninguna ruta de `app/api` se guarda ya por rol**. Codemod revisado `scripts/codemods/guardas_a_capacidades.py`: cada fichero de endpoints tiene un área y cada `require_*` un conjunto de roles; (área, guarda) → capacidad con EXACTAMENTE esos roles (`ADMIN`→`<área>.administrar`, `ADMIN_PM`→`gestionar`/`dirigir`, `ADMIN_RRHH`→`rrhh`, `GESTORES`→`gestionar`/`responsables`, `INTERNOS`→`usar`, `TODOS`→`trabajar`). Se reutiliza la del catálogo cuando ya existe con los mismos roles y sin módulo (`sd.administrar`, `sd.gestionar`, `sd.completo`, `alm.gestionar`, `cartera.gestionar`, `software.gestionar`, `org.administrar`); las demás se crean sin `modulo` (bloque generado de `app/core/capacidades.py`: 99, más `tareas.usar` y `clientes.dirigir`), así que no cierran más que la guarda de rol: el superadmin pasa igual y el rol personalizado sigue cerrando por módulo en `get_current_user`. 147 ficheros. Guardas a mano incluidas: `predictive_observability._require_admin` → `observabilidad.administrar` (ahora pasa también el superadmin), `verify_admin_or_governance_role` (ABAC, ABAC admin, gobierno de IA, SOC; 28 llamadas) y `_permiso_de_gobierno` → `gobierno.administrar`/`ia.administrar`/`soc.administrar` en la firma (la función se retira), `alm_integracion.require_gestor_de_personas` → `alm.personas`, el `require_internal_user` del cuerpo de `traduccion.editor_de_contenido` → `traduccion.usar`, y 24 `if current_user.role not in …: 403` al principio del cuerpo (entregables, NPS, rentabilidad, riesgos, auto-resolución, correlación, problemas) → la capacidad con el conjunto EFECTIVO (guarda de la firma ∩ comprobación del cuerpo). Las comprobaciones mixtas (propietario o admin) se quedan: son control de objeto. Herramientas del asistente (`tool_execution/politica.py`) con la capacidad de su ruta. Frontend: `permisos/capacidades.ts` sincronizado (bloque generado). Medida de audiencia antes/después por (método, ruta) en `docs/seguridad/guardas_por_capacidad.md`. Tests: `tests/test_auditoria_2026_11_22_ronda2_nucleo.py` y recuentos comentados en `test_guardas_deniegan.py`/`test_guardas_de_rol.py`.
- **Evidencia.**
  - 1 421 rutas con `RequireRole` frente a 492 con `requiere_capacidad`: la matriz de capacidades, que es lo que la pantalla enseña, decide en menos de una cuarta parte de la API.
  - `app/api/v1/endpoints/settings.py:39-42` redefine `require_admin_or_pm` a mano: no deja pasar al superadmin, a diferencia de `RequireRole.__call__`, y tapa el nombre del núcleo.
  - `predictive_observability.py:37` tiene su propio `_require_admin`.
- **Impacto.** Un rol personalizado o un cambio en la matriz no se refleja en 1 421 rutas, y la pantalla y la API pueden discrepar.
- **Arreglo.** Migrar por dominio de `RequireRole` a `requiere_capacidad` y borrar las guardas locales.

#### M10. Migraciones destructivas e irreversibles sin copia previa automática
- **Dónde.**
  - `alembic/versions/135_filas_sin_empresa.py:47` (`DELETE FROM sd_itsm_metric_snapshots WHERE organization_id IS NULL`, `downgrade: pass`);
  - `185_ajustes_generales_una_fuente.py:61`;
  - 110, 111, 146, 156, 160, 166 y 173 (`drop_table` tras copiar datos);
  - `scripts/migrar.py`, `setup.sh update`, `setup.bat` y la migración del compose: ninguno hace `pg_dump` antes.
- **Impacto.** Un `update` sobre una base real borra datos sin vuelta atrás.
- **Arreglo.** Hacer copia (`scripts/backup.sh`) antes de `alembic upgrade` cuando haya revisiones pendientes y el entorno no sea de desarrollo, y marcar las revisiones destructivas en `NAMING_CONVENTION.md`.
- ✅ arreglado 23-11-2026: `scripts/migrar.py` (setup.bat/setup.sh) llama a `scripts/copia_antes_de_migrar.py`: con revisiones destructivas pendientes (14 de 147 en la cadena) copia SQLite con la API de backup o PostgreSQL con `pg_dump -Fc` (si no hay `pg_dump`, avisa); si la copia falla no migra. `MIGRATION_BACKUP_MODE`/`MIGRATION_BACKUP_DIR`. Verificado: `test_la_copia_previa_detecta_las_destructivas_y_copia_sqlite`. Ronda 2 (23-11-2026): las 15 revisiones destructivas (⚠ irreversibles: 135 y 185) están marcadas en `alembic/NAMING_CONVENTION.md` y un test compara la tabla con el detector.

### BAJA

| # | Dónde | Evidencia | Impacto | Arreglo |
|---|---|---|---|---|
| B1 | `app/main.py:1030`, `:1089` | `/health` devuelve `version` y `project`; `/ready` devuelve `environment` y el modo del planificador. nginx los publica (`nginx.frontend.conf:185-199`) | Ayuda a identificar el sistema | Responder solo `status` en público | ✅ 23-11-2026: en staging/producción `/health` responde `status` y `db`; `/ready`, `status` y el estado de cada comprobación (sin entorno, modo del planificador ni motivos). En desarrollo, con detalle (`main._health_detallado`).
| B2 | `setup.sh:1177-1178`, `setup.bat:742`, `scripts/start.sh:136-138` | `uvicorn … --host 0.0.0.0` | En local la API (posiblemente con `ENABLE_SUPERADMIN_BYPASS`) queda expuesta a la LAN. El compose usa 127.0.0.1 a propósito | `--host 127.0.0.1` por defecto, con `BACKEND_HOST` para abrirlo | ✅ 23-11-2026: `setup.sh`/`setup.bat` arrancan uvicorn en `127.0.0.1`; `BACKEND_HOST=0.0.0.0` lo abre a la red. Docker no cambia (dentro del contenedor 0.0.0.0, publicado en 127.0.0.1). `scripts/start.sh` retirado.
| B3 | `setup.sh:1437-1447`, `setup.bat:143-157` | `docker-clean` dice «borra todos los datos», pero `docker compose down -v` sin `--profile` no toca los volúmenes `external` (postgres, s3) ni los de perfiles | El operador cree que limpió y no limpió (o al revés) | Mensaje veraz, o `docker volume rm` explícito tras confirmación | ✅ 23-11-2026: `docker-clean` baja todos los perfiles (`--profile app/s3/observability/host-metrics down -v --remove-orphans`) y dice la verdad: borra Redis/Prometheus/Alertmanager/Grafana y CONSERVA PostgreSQL y S3 (externos), con el `docker volume rm` para borrarlos a propósito.
| B4 | `deploy/Dockerfile.backend` | Comentario «no ha sido build-verificada» y `docker compose run … backend` (el servicio se llama `api`); instala `curl` sin uso (el healthcheck es Python); sin `HEALTHCHECK`; `python:3.12-slim` sin digest | Documentación engañosa, superficie innecesaria | Actualizar el comentario, quitar `curl`, fijar el digest | ✅ 23-11-2026: comentario al día (lo construye el compose; migraciones por el servicio `migrate`), sin `curl` ni `apt-get`, imagen base `ARG PYTHON_IMAGE` fijable por digest con `--build-arg` (el digest se fija en CI). Sin `HEALTHCHECK` en la imagen a propósito: la misma imagen corre api/worker/beat/migrate y cada servicio declara el suyo en el compose.
| B5 | `docker-compose.yml:384`, `:550` | Prometheus con `--web.enable-lifecycle` sin autenticación (127.0.0.1:9090); cAdvisor `privileged` (perfil opcional) | Cualquier proceso local puede recargar o parar Prometheus | Quitar `enable-lifecycle` o ponerle autenticación | ✅ 23-11-2026: fuera `--web.enable-lifecycle` (recargar = `docker compose restart prometheus`). cAdvisor `privileged` se queda: lo exige para leer cgroups y solo existe en el perfil opcional `host-metrics`.
| B6 | `requirements*.txt` | 130 pines `==` sin hashes; no se fijan las transitivas (sin verificar si hay lockfile) | Builds no reproducibles, riesgo de cadena de suministro | `pip-compile --generate-hashes` | ⏸ pendiente 23-11-2026: no viable en esta ronda: `pip-compile --generate-hashes` necesita red, pip-tools y decidir plataformas (Windows en local, Linux en Docker). Procedimiento: `pip install pip-tools && pip-compile --generate-hashes -o requirements.lock requirements.txt` en Linux y `pip install --require-hashes -r requirements.lock` en el Dockerfile.
| B7 | `config.py:147` vs `:353` | `COMPLIANCE_MIN_PASSWORD_LENGTH=12` y `MIN_PASSWORD_LENGTH=8` | Dos políticas de contraseña | Una sola fuente. ✅ 23-11-2026: una sola política, la de la empresa (`seguridad_de_cuentas/politica.py`, editada en Seguridad de cuentas); `COMPLIANCE_MIN_PASSWORD_LENGTH` es solo el umbral con el que el informe de cumplimiento la mide, documentado |
| B8 | `cab.py:217-221` | Trigger sin secreto → `webhook_no_autorizado`; sin firma → `cab_firma_requerida` | Permite enumerar slugs de webhook | Mismo 401 genérico <br>✅ arreglado 23-11-2026: mismo 401 `webhook_no_autorizado` sin secreto o sin firma; el secreto HMAC se guarda cifrado. |
| B9 | `app/api` | `request.client.host` en 17 sitios frente a `extract_client_ip` en 10 (p. ej. `cmdb.py:550`, `auth_core.py` en `password_forgot`) | Tras nginx se registra la IP del proxy en auditoría y en los cubos de recuperación de contraseña | Usar siempre `extract_client_ip`. 🟡 23-11-2026: arreglado en `auth_core` (cubos de login y de recuperación, `LOGIN` en auditoría con IP); quedan los demás sitios de `app/api` | ✅ 23-11-2026 (ronda 2): los 16 sitios restantes de `app/api` (ALM, ausencias, RGPD de BI, portal, demanda, documentos, GRC, proveedores y su portal, CMDB) usan `network.ip_del_cliente` (= `extract_client_ip`, None si no hay). 0 `request.client.host` en `app/api`; un test lo impide.
| B10 | `app/core/uploads.py` (`ALLOWED_MIME_TYPES`) | `image/svg+xml` admitido en DOCUMENT/ATTACHMENT | XSS almacenado si se sirve inline (mitigado por la CSP `script-src 'self'`; sin verificar `Content-Disposition` en todas las descargas) | Servir SVG como adjunto o sanearlo | ✅ 23-11-2026: `/documents` ya servía el SVG como adjunto; ahora también la descarga por token de colaboración (`Content-Disposition: attachment`). Los canales ya excluían SVG.
| B11 | `ratelimit.py`, `abac_dependency.py`, `grc_enforce.py`, `deps.py`, `main.py::_pista_de_usuario` | El JWT se decodifica hasta 5 veces por petición y el usuario se carga 3 veces | Coste por petición | Decodificar una vez (`request.state`) | ✅ 23-11-2026: `security.decode_token_de_peticion` memoriza el JWT en `request.state` (una decodificación por petición): límite de peticiones, zona horaria, GRC/ABAC residuales, `get_current_user` y la pista del log. El usuario se carga una vez: GRC y ABAC corren dentro de `get_current_user` desde A2.
| B12 | `.env` (HEAD) | `ACCESS_TOKEN_EXPIRE_MINUTES=60` con `ACCESS_TOKEN_MAX_MINUTES=30`: la vida real es 30 | Configuración engañosa | Alinear | ✅ 23-11-2026: `.env.example` con `ACCESS_TOKEN_EXPIRE_MINUTES=30` y la explicación (vida real = min(EXPIRE, MAX)). El `.env` local no se toca (sigue con 60, que se recorta a 30: alinearlo a mano).
| B13 | `app/api` | 70 `raise HTTPException(...)` sin código de catálogo (p. ej. `enterprise.py:111` `HTTPException(404)`) | La interfaz no puede traducirlos (es/en/zh) | `error_http(…, codigo)`  ✅ 23-11-2026: los 73 `HTTPException` directos de `app/api` (72 con `HTTPException(404)` o `detail` snake_case ajeno al catálogo + 1 con dict en `m365.py`) pasan a `error_http`: 404 → `no_encontrado` con `que=<entidad>`, `campo_obligatorio`, `solo_admin`, `sin_permiso`. Entidades nuevas (`scripts/codemods/errores_con_codigo/http_sin_codigo.json`, sincronizadas a es/en/zh): webhook, marcador, trabajador, escenario, prediccion, reunion, token, configuracion. `scripts/errores_sin_codigo.py` cuenta la categoría `http_crudo` (cualquier `HTTPException(...)` directo en `app/api` y `app/core`, salvo `detail` con código del catálogo o prefijo `alm_`/`almint_`/`trad_`): 73 antes, 0 después; la cuota (`scripts/errores-sin-codigo.json`) sigue en 0 y `tests/test_errores_sin_codigo.py` cubre el patrón. |
| B14 | `app/main.py` (`ExceptionHandlerMiddleware`) | `logger.error(..., exc_info=True)` con la traza completa | Las trazas pueden llevar datos personales al log | Sanear o usar Sentry con `send_default_pii=False` (ya está) | ✅ 23-11-2026: en staging/producción el log guarda la traza sin datos personales (`main._traza_saneada`: marcos de código + mensaje pasado por `redact_pii`); en desarrollo, la traza completa.

---

## 4. Código muerto

- **`app/db/session.py:105-135` y `:207-235`**: las ramas `project_id`, `user_id` y `actor_id` de `_tenant_filter_for_model` y `_tenant_where_for_model` no se alcanzan nunca. Medido: 0 de 537 modelos llegan ahí (525 tienen `organization_id`, 11 `org_id` y 1 está exento). Son 60 líneas duplicadas que además filtran por `User.organization_id`, la empresa de ficha, que ya no es la semántica vigente. Se pueden borrar y dejar el fallo en cerrado. ✅ 23-11-2026: retiradas de las dos funciones; un modelo sin `organization_id`/`org_id` ni exención falla en cerrado. `test_tenant_filter_coverage.VIAS` al día.
- **`app/api/deps.py`**: reexporta `app.core.deps`. Lo usan 20 ficheros: no está muerto, pero son dos rutas de import para lo mismo. ⏸ se conserva 23-11-2026: reexporta a propósito para 20 ficheros y los tests; unificar el import es mecánico y sin efecto de seguridad.
- **`app/core/deps.py::get_current_active_user`**: alias trivial («is_active is already checked»), usado en 3 ficheros. ⏸ se conserva 23-11-2026: lo reconoce `explicar_acceso` y lo usan 3 ficheros.
- **`verify_admin_or_governance_role`** (`security.py`): se conserva con un nombre que ya no describe lo que hace (el rol `governance` no existe). ✅ 23-11-2026: retirada; sus 28 llamadas pasan a la capacidad en la firma (M9).
- **`scripts/start.sh`/`start.bat`, `clean_and_start.sh`, `test_and_report.sh`, `update_endpoints_table.sh`, `smoke_test_simple.py`**: solo los citan DOCS, README, auditorías antiguas y tests de configuración. Duplican el arranque de `setup.*` con otro comportamiento (`start.sh` fija el puerto 8000 y no pone `ENABLE_APSCHEDULER=0`). Candidatos a retirarse (sin verificar el uso manual). ✅ 23-11-2026: retirados los seis (solo los citaba la documentación; README al día).
- **`app/db/migrate_to_pg.py`**: herramienta de un solo uso (SQLite a Postgres); sin verificar si sigue haciendo falta. ⏸ se conserva 23-11-2026: es la vía documentada (README) para pasar una instalación SQLite a PostgreSQL.
- **`abac_registry.py` (cabecera)**: dice «Nada lo lee en caliente». Es falso desde que `abac_dependency.py` lo importa y lo aplica: es documentación muerta y engañosa. ✅ 23-11-2026: la cabecera dice ya que se lee en caliente (`abac_dependency._resolve_coverage`).
- No hay módulos de endpoints huérfanos ni rutas duplicadas. ✅ comprobado de nuevo 23-11-2026.

## 5. Hardcode

- **URLs.** Están en `config.py`/`config_groups/` como valor por defecto configurable (Docusign, Microsoft, Google, GitHub, proveedores de IA, `ipapi.co`, `cdn.contecflow.app`), lo cual es correcto. Las únicas literales fuera de configuración están en `main.py` (CSP con `cdn.jsdelivr.net` y `fastapi.tiangolo.com` para la documentación) y `m365.py:218,259` (`schema.org`, que es de protocolo). ✅ revisado 23-11-2026: correcto tal cual.
- **Correos.** `NOTIFICATION_EMAIL_FROM="alerts@contecflow.local"` y `VAPID_CONTACT="mailto:noreply@contecflow.local"` vienen por defecto; `ops/alertmanager/generar-config.sh` pone `alertas@contecflow.local`. Las semillas (`app/db/seed_parts/core.py:346-381`, `enterprise.py:91-103`) usan dominios reales (`acme.com`, `freelance.com`, `techpartners.es`, `hospitalx.es`…): si el entorno demo envía correo, saldría a terceros. Mejor usar `example.com`. ✅ 23-11-2026: las semillas usan `*.example.com` (acme, techstart, retailcorp, hospitalx, freelance, techpartners); los remitentes `*.contecflow.local` no son enrutables y se cambian por entorno. Los usuarios demo `@company.com` se conservan: son las credenciales documentadas del modo demo.
- **Rutas.** Hay listas de rutas en código que se mantienen a mano:
  - `main.py::_PETICIONES_CON_401_ESPERADO` (9 rutas);
  - `csrf.py::_DEFAULT_EXEMPT_PREFIXES` (18);
  - `credenciales_delegadas.RUTAS_VEDADAS` y `AREAS`;
  - `modulos.MODULOS`;
  - `cors_publico.RUTAS_PUBLICAS`.

  Son razonables como política, pero se desincronizan: el propio fichero CSRF tiene tres comentarios de «decía X y no casaba con la ruta». ⏸ aceptado 23-11-2026: política escrita, cada lista con su test de coherencia; generarlas de un registro único es refactor sin efecto funcional.
- **Umbrales.**
  - Límites `@limiter.limit("5/minute")`… escritos en 136 sitios;
  - `RATE_LIMIT_DEFAULT=200/minute`;
  - `_PROFILE_MAX_MB` (RECEIPT 10, PDF_ONLY 10, CSV_IMPORT 5) en `uploads.py`;
  - pool de Postgres `pool_size=10`, `max_overflow=20`, `pool_recycle=3600` (`session.py:363-370`);
  - `create_mfa_challenge_token` con 5 minutos fijos (`security.py`);
  - `traces_sample_rate=0.1` en Sentry. ⏸ aceptado 23-11-2026: los límites por ruta son política de cada endpoint (`RATE_LIMIT_DEFAULT` ya es ajuste); pool, reto MFA y muestreo de Sentry quedan como valores por defecto razonables.
- **Idiomas.** `translations.py:15` `SUPPORTED_LANGS = {"es","en","fr","de","it","pt","pl","zh"}` es una lista propia que no sale de un catálogo común. Los operadores es/en/zh y los mensajes de dominio en castellano en `detail` (504 `detail="…"`) dependen del `code` para traducirse; los 70 `HTTPException` sin código no se traducen. ⏸ otro agente (textos e idiomas) 23-11-2026; los `HTTPException` sin código ya son 0 (B13).
- **Estados.** 12 comparaciones `status == "…"` literales en `app/api` (bajo). ⏸ aceptado 23-11-2026 (bajo): comparaciones de presentación; los estados con máquina de estados (cambios, tickets) usan enums.

## 6. Arquitectura: incoherencias

1. **Hay dos sitios donde se decide la autorización con el principal resuelto de dos maneras.**
   - Las dependencias globales (ABAC y GRC) decodifican el JWT por su cuenta, sin credenciales delegadas y sin empresa activa.
   - `get_current_user` resuelve el principal completo.

   Este hallazgo es el origen de A2 y M1. `modulos` y `permisos_de_proyecto` ya se aplican dentro de `get_current_user`: GRC y ABAC deberían ir en el mismo sitio. ✅ 23-11-2026: GRC y ABAC dentro de `get_current_user` (A2/M1); el JWT se decodifica una vez (B11).
2. **Tres validadores SSRF** (M7) y **dos rutas de deps** (`app.core.deps` y `app.api.deps`). ✅ SSRF unificado (M7). ⏸ las dos rutas de deps se conservan (§4).
3. **Los routers de autenticación viven en `app/api/v1/routers/`** (`auth_core.py`, `auth_mfa.py`, `auth_sso.py`…), mezclados con los agregadores de dominio. Lo demás está en `endpoints/`. ⏸ aceptado 23-11-2026: moverlos no cambia comportamiento y rompería imports de tests.
4. **Política de cookies repartida.** `COOKIE_OPTS` está en `services/auth_service/tokens_y_cookies.py`, el portal pone la suya en el endpoint y la cookie CSRF tiene la suya en `core/csrf.py`. 🟡 23-11-2026: el portal ya usa `COOKIE_OPTS` (M3); la cookie CSRF tiene la suya porque NO es httpOnly a propósito (doble envío).
5. **Lanzadores no equivalentes.** `setup.sh` crea el rol RLS y `setup.bat`/`docker_stack.py` no (A1). Los modos coinciden (`demo`, `clean`, `start`, `stop`, `update`, `docker`, `docker-status`, `docker-stop`, `docker-clean`). `clean` exige un entorno no productivo en los dos, a través de `exigir_entorno_no_productivo` en `reset_to_admin_only.py`. ✅ 23-11-2026: los dos crean el rol RLS (A1), arrancan en 127.0.0.1 (B2) y limpian Docker igual (B3).
6. **`.env` versionado frente a `.env` que reescriben los lanzadores.** El fichero que el repositorio trata como configuración compartida es el mismo que `setup` llena con credenciales locales (C1). ⏸ ver C1 (decisión del usuario).
7. **El superadmin trabaja sin filtro de empresa.** `db.info["organization_id"]=None` y `is_superadmin=True` hacen que vea todas las empresas mezcladas en cualquier listado. Es diseño documentado, pero no hay una «empresa de trabajo» para el superadmin fuera de «entrar como». ⏸ diseño documentado; una «empresa de trabajo» del superadmin es decisión de producto.

## 7. Qué hace / qué no hace

**Hace (comprobado):**
- Aislamiento por empresa en el ORM en tres capas, que falla en cerrado; el 100 % de los modelos tiene columna de empresa o exención explícita.
- Sellado de `organization_id` al insertar.
- Políticas RLS generadas desde los modelos en cada `alembic upgrade`.
- JWT con llavero rotado y `kid`, refresh con rotación y detección de reutilización, MFA/passkeys/SSO/SAML/SCIM.
- Login con tiempo constante frente a usuarios inexistentes, bloqueo por IP y por cuenta.
- Restablecimiento de contraseña de un solo uso que revoca las sesiones.
- Bypass de superadmin limitado a desarrollo con SQLite (ocho condiciones, más el arranque que se niega fuera de desarrollo).
- Validación de secretos débiles en la configuración: `SECRET_KEY`, `CLIENT_PORTAL_SECRET` y `SUPERADMIN_PASSWORD` en staging y producción.
- CORS sin `*` con credenciales.
- CSP estricta para la API.
- Documentación de la API cerrada en producción.
- `/metrics` con Bearer y cerrado sin token fuera de desarrollo.
- Webhooks entrantes con firma o secreto por empresa: GitHub, GitLab, Jira, CAB, Slack, WhatsApp, Zoom/Recall/Teams y monitorización.
- Validación central de subidas con bytes mágicos.
- Guardia SSRF completa en `outbound_url`.
- Bloqueo legal en `before_flush`.
- Cadena de auditoría HMAC con exportación firmada.
- Alembic con una sola cabeza y la migración como paso previo obligatorio en Docker.
- Volúmenes de datos protegidos de `down -v`.
- Puertos de Docker en 127.0.0.1.
- `.dockerignore` que excluye `.env`, `*.db`, `uploads/`, `tests/` y `docs/`.

**No hace:**
- No protege los secretos: el `.env` está en git (C1). ⏸ (C1).
- No arma RLS en el despliegue Docker ni en Windows (A1). ✅ (A1).
- No aplica GRC ni ABAC global a las claves de API ni a los tokens OAuth (A2). ✅ (A2).
- No evalúa la ABAC global en la empresa activa (M1). ✅ (M1).
- No asigna la empresa de la app a los tokens OAuth (M2). ✅ (M2).
- No limita el tamaño del cuerpo en la app ni valida igual todas las subidas (M4). ✅ (M4).
- No acota en el ORM ni en RLS las rutas anónimas (M8). ✅ (M8).
- No decide la mayor parte de la API por capacidad (M9). ✅ (M9: toda la API).
- No hace copia de seguridad antes de migraciones destructivas (M10). ✅ (M10).
- No tiene lista blanca de tareas encolables ni autenticación en Redis (M5). ✅ (M5).
- No apaga por defecto la geolocalización externa de IPs (M6). ✅ (M6).
- No aplica ABAC por recurso concreto: el motor recibe `resource_id` pero, según `abac_dependency.py`, las decisiones salen del rol, el tipo y los atributos del usuario. Sin verificar si el motor ya usa atributos del recurso. ⏸ sin verificar: decisión de diseño del motor ABAC.

**Sin verificar** (fuera de alcance o sin ejecutar):
- El comportamiento de `with_loader_criteria` con consultas `select_from` sin entidad. ⏸ sin verificar.
- Que las FK de entrada a otra empresa (`project_id` ajeno en un alta) se validen en todos los servicios: RLS `WITH CHECK` solo mira la columna de empresa de la propia fila. ⏸ sin verificar de forma global (se corrigen caso a caso: portal, enrutado, escalado y fusión en la ronda 2 del informe 03).
- `ipaddress` con direcciones IPv4 mapeadas en IPv6 (`::ffff:127.0.0.1`) en la versión de Python desplegada. ✅ el guardia SSRF bloquea las mapeadas (M7).
- Si un usuario de solo lectura puede emitir ediciones por el WebSocket de documentos (`ws.py::_bucle_de_documento`). ⏸ sin verificar.
- El uso manual de los scripts legados. ✅ retirados (§4).
