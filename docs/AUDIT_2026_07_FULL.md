# Auditoría integral — Contecflow PSA (2026-07-31)

Alcance: código, seguridad, arquitectura, funcionalidad y usabilidad.
Método: evidencia directa sobre el repo (inspección en runtime del grafo de
dependencias de FastAPI, linters, suite de tests, PoC ejecutables). Cada hallazgo
cita fichero y línea. No se incluyen recomendaciones genéricas sin evidencia.

## 0. Dimensión del sistema

| Área | Ficheros | LOC |
|---|---:|---:|
| Backend (`app/`) | 683 | 170.351 |
| Frontend (`frontend/src/`) | 352 | 132.963 |
| Tests (`tests/`) | 193 | 31.068 |
| Migraciones (`alembic/versions/`) | 43 | — |

- **2.048 rutas** `/api` registradas; 78 prefijos de router.
- Reparto backend: `services/` 323 ficheros, `api/` 188, `models/` 75, `schemas/` 49, `core/` 27.
- Fichero mayor: 1.701 LOC (`client_portal_service.py`). No hay ficheros monstruo.
- Frontend 100% TypeScript (338 `.ts/.tsx`, 0 `.jsx/.js`).

Valoración: base sólida y bien dimensionada. La proporción servicios/endpoints
(323/188) indica que la lógica vive en la capa de servicio, no en los handlers.

---

## 1. Seguridad

### 1.1 🔴 ALTA — IDOR cross-tenant en CSAT de tickets de portal

**Fichero:** `app/api/v1/endpoints/service_desk/tickets.py:259-268`
y `app/services/service_desk/csat_service.py:12-25`

El endpoint autentica al cliente pero **descarta el principal**:

```python
require_portal_client(authorization, portal_access_token, db, detail="...")  # valor no asignado
result = submit_ticket_csat(db, ticket_id, payload.score, payload.comment)
```

Y el servicio resuelve el ticket **solo por id**, sin acotar por cliente:

```python
ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()   # csat_service.py:13
```

**Impacto:** cualquier cliente del portal autenticado puede puntuar el CSAT de un
ticket de **otro cliente** y, como efecto colateral, **forzar su cierre**
(`ticket.status = TicketStatus.closed`, `csat_service.py:22`). Corrupción de datos
cross-tenant y falseo de métricas de calidad de servicio.

**Confirmado empíricamente**, no inferido:

```
POST /api/v1/sd/tickets/{ticket_de_otro_cliente}/csat
-> 200 {"data":{"ok":true},"meta":null}
```

PoC: `tests/test_portal_ticket_tenant_isolation.py::test_portal_client_cannot_submit_csat_on_other_clients_ticket`

**Contraste correcto en el mismo módulo:** `client_ticket_detail_payload`
(`app/services/service_desk/ticket_read_service.py:185-188`) sí filtra por
`Ticket.requester_client_id == client_id`.

**Corrección:** pasar `client.id` a `submit_ticket_csat` y añadir el filtro
`Ticket.requester_client_id == client_id` a la query.

### 1.2 🔴 ALTA — IDOR cross-tenant en comentarios de portal

**Fichero:** `app/api/v1/endpoints/service_desk/tickets.py:214-224`
y `app/services/service_desk/comment_service.py:46-50`

```python
client = require_portal_client(...)
ticket = get_ticket_for_client_comment_or_404(db, ticket_id)   # alias de get_ticket_or_404
comment = add_client_comment_svc(db, ticket, ticket_id, payload.body, client.id)
```

`get_ticket_or_404` filtra solo por `Ticket.id`. La identidad del cliente se usa
únicamente como `author_client_id`, **nunca para acotar el ticket**.

**Impacto:** cualquier cliente del portal puede publicar un comentario
**`is_public=True`** (`comment_service.py:57`) en el ticket de otro cliente. El
comentario queda visible para el propietario legítimo y para los agentes: vector
de inyección de contenido cross-tenant y de phishing interno.

**Confirmado empíricamente:**

```
POST /api/v1/sd/tickets/{ticket_de_otro_cliente}/comments/client
-> 200 {"data":{"id":"e9974b48-...","created_at":"..."},"meta":null}
```

PoC: `tests/test_portal_ticket_tenant_isolation.py::test_portal_client_cannot_comment_on_other_clients_ticket`

**Corrección:** acotar el ticket por `requester_client_id == client.id` antes de
insertar el comentario.

### 1.3 🟠 MEDIA — Authz imperativa en el cuerpo, no declarativa (causa raíz de 1.1 y 1.2)

La superficie de portal no usa `Depends(...)` para autenticar, sino una llamada a
`require_portal_client(...)` **dentro del handler**. Consecuencias medidas:

- Una inspección del grafo de dependencias en runtime clasifica **69 rutas** como
  «sin autenticación» cuando en realidad la mayoría sí autentican en el cuerpo.
  Es decir: **ninguna herramienta puede auditar authz automáticamente**.
- OpenAPI no marca esas rutas como protegidas.
- No hay red de seguridad en tiempo de colección: olvidar la llamada, o descartar
  su valor de retorno (exactamente lo ocurrido en 1.1), no rompe nada.

**Corrección:** convertir `require_portal_client` en dependencia
(`client = Depends(get_current_portal_client)`) y añadir un guard-test que recorra
`app.routes` exigiendo que toda ruta `/api` tenga una dependencia de auth o figure
en una allowlist explícita de rutas públicas.

### 1.4 🟠 MEDIA — Sin linter de seguridad; 472 `noqa` inertes

`ruff.toml` activa solo `select = ["E", "F", "W"]` (pycodestyle + pyflakes). **No**
hay `S` (bandit/seguridad) ni `B` (bugbear).

Al mismo tiempo el código contiene 472 `noqa` de reglas **que no están
activadas**, luego no suprimen nada y dan falsa sensación de rigor:

| Regla silenciada | Veces | ¿Activa? |
|---|---:|---|
| `PLC0415` (import dentro de función) | 200 | No |
| `F401` | 126 | Sí |
| `BLE001` (blind except) | 61 | No |
| `E712`/`E711` | 53 | No (ignoradas globalmente) |
| `E402` | 13 | No |

Nota: ignorar `E711`/`E712` globalmente es **defendible** aquí, porque con
SQLAlchemy `Column == None` es idiomático (genera `IS NULL`).

**Corrección:** añadir `S` y `B` al `select`, revisar el resultado y eliminar los
`noqa` inertes (o activar sus reglas).

### 1.5 🟡 BAJA — El guard-test de ABAC cubre 12 prefijos de 78

`tests/test_abac_registry_completeness.py` exige cobertura ABAC solo para
`CRITICAL_PREFIXES` (12 prefijos: projects, tasks, users, sd, invoices…), y
`ABAC_ROUTE_REGISTRY` tiene 13 entradas. Dominios enteros quedan fuera del
guardrail: BI, ai-governance, collaboration, integrations, marketplace…

No es un fallo per se (esos dominios usan RBAC vía `get_current_user`/`require_admin`),
pero el guardrail no escala con la API y su nombre sugiere más cobertura de la que da.

**RESUELTO en esta sesión.** El registro pasa de 13 a **131 prefijos** y cubre los
127 prefijos de primer nivel de la API: cada uno está en `ABAC_ROUTE_REGISTRY` con su
`resource_type`, o en el nuevo `ABAC_EXEMPT_PREFIXES` con el motivo escrito
(autenticación, principal `ClientUser` del portal, membresía de colaboración,
webhooks sin usuario, metadatos de UI, stubs 501, docs). Cuatro tests nuevos en
`tests/test_abac_registry_completeness.py` impiden que se degrade: sin decisión, sin
solapes, sin prefijos obsoletos y sin exenciones sin motivo.

Esto **no cierra rutas por sorpresa**: `enforce_abac()` es fail-open, así que
registrar un prefijo solo significa «si un admin define una política para este
resource_type, también se aplicará aquí».

Aviso de rendimiento que la ampliación destapó y hubo que arreglar antes: la versión
anterior de `enforce_abac()` escribía una fila en `PolicyAudit` **y hacía commit en
cada request** a una ruta registrada, incluso cuando no matcheaba ninguna política.
Con 13 prefijos era tolerable; con cobertura total habría sido un INSERT+COMMIT por
request en toda la API. Ahora hay un early-out si la organización no tiene políticas
activas, y la auditoría solo se escribe cuando alguna política ha aplicado de verdad
(las denegaciones siempre se auditan, porque implican política que matcheó).

### 1.6 🟡 BAJA — Secreto HMAC embebido en datos de demo

`app/db/seed_parts/enterprise.py:53` → `secret="s3cr3t-hmac-key-example"` en un
webhook de seed. Está `is_active=False`, pero si el seed se ejecuta en un entorno
real y alguien activa el webhook, el secreto de firma es público en el repo.

**Corrección:** generar el secreto con `secrets.token_urlsafe()` en el seed.

### 1.7 🟡 BAJA — Verificación TLS desactivable en discovery de CMDB

`app/services/cmdb/discovery.py:229-232`: con `disable_ssl_verification` el
contexto pasa a `check_hostname = False` + `CERT_NONE`. Es **opt-in del operador**
y responde a una necesidad real (vCenter con certificado autofirmado), pero no se
ofrece la alternativa correcta (CA/fingerprint propio), así que la única salida es
desactivar la verificación por completo.

### 1.8 🟠 MEDIA — Inyección SQL en el filtro de aislamiento multi-tenant de OLAP

**Fichero:** `app/services/olap/query_engine.py:36-40` y `:181`

El motor OLAP construye SQL para DuckDB por interpolación de cadena, y el `org_id`
—que es precisamente el filtro de aislamiento entre organizaciones— se insertaba como
literal sin validar:

```python
return f"AND {prefix}organization_id = '{org_id}'"
```

Los demás valores interpolados (`months`, `since_key`, `until_key`) son `int` tipados
y FastAPI los coacciona, así que están a salvo. El `org_id` es el único `str`.

**Explotabilidad:** no demostrada hoy, porque el `org_id` proviene de
`current_user.organization_id` (registro del servidor, no entrada directa del
usuario). Pero es un filtro de tenancy construido por concatenación: a una comilla
de distancia de una fuga cross-organización en el almacén analítico. No hace falta
esperar a que sea explotable para arreglarlo.

**Detectado por** `S608` de bandit, que no estaba activado (ver §1.4).

### 1.9 🟡 BAJA — 45 usos de apertura de URL sin restricción de esquema

`S310` (suspicious-url-open-usage) aparece 45 veces. `urllib.urlopen` acepta
`file://` y otros esquemas, así que si alguna de esas URL es influenciable por el
usuario habría lectura de ficheros locales o SSRF. **No verificado caso a caso** en
esta auditoría; queda como pendiente de triaje.

### 1.10 ✅ Aspectos sólidos verificados

- **CORS:** `app/main.py:495-498` usa `settings.ALLOWED_ORIGINS` y
  `app/core/config.py:447` **rechaza `*` con `allow_credentials=True`**. Correcto.
- **Inyección SQL:** sin f-strings en SQL en la ruta de petición. Los únicos casos
  (`app/db/migrate.py:284`, `migrate_to_pg.py:62-95`) son utilidades de migración
  con identificadores saneados / procedentes del metadata, no de entrada de usuario.
- **Ejecución de código:** 0 `eval`/`exec`/`os.system`/`shell=True`/`pickle.loads`
  de Python. Los `r.eval(` de `ws.py:111,155` son scripts Lua de Redis, no `eval`.
- **Inyección SQL en la ruta de petición:** de los 13 avisos `S608`, 12 son
  utilidades de migración o identificadores de metadata (no entrada de usuario). El
  13.º era real y está descrito en §1.8.
- **XSS frontend:** 0 usos de `dangerouslySetInnerHTML`.
- **Cadena de suministro:** **117/117** dependencias pineadas con `==`.
- **Cobertura authz declarativa:** 1.976 de 2.048 rutas con dependencia de auth
  (96,5%); `get_current_user` en 1.927.
- **Sin `except:` desnudos** (0 en todo el backend).

---

## 2. Arquitectura

### 2.1 🟠 MEDIA — ~200 imports internos diferidos (presión de ciclos)

200 imports dentro de funciones marcados `# noqa: PLC0415`. Los símbolos más
diferidos son **módulos internos**, no dependencias opcionales:
`AppSetting` (18), `HTTPException` (12), `settings` (11), `ITSMChangeRequest` (6),
`CMDBAgentRegistration` (5), `User` (4), `Project` (3).

Diferir `app.models.*` y `app.core.config.settings` dentro de funciones es el
patrón clásico para romper ciclos de importación.

Esto **contradice la política declarada** en `docs/CIRCULAR_IMPORTS.md`:

> «There are **no remaining lazy imports in the audited services for the sole
> purpose of breaking import cycles.** Any future deferred imports should be
> documented inline with the full cycle path and a refactor plan.»

Ninguno de los 200 documenta la ruta del ciclo. El documento describe un
saneamiento de 3 módulos (audit #110) y se ha quedado desfasado respecto al resto.

**Corrección:** o bien mapear el grafo de imports y romper los ciclos de verdad
(extraer un módulo de tipos/contratos), o bien actualizar la política y exigir la
justificación inline que ella misma pide.

### 2.2 🟡 BAJA — Migración del envelope canónico a medias

Trabajo en curso (audit #67). Estado real medido: **149 de 163** ficheros de
endpoints usan `app.core.responses`. De los 14 restantes, **10 están exentos con
motivo** (WebSockets, protocolo TUS, shape RFC de SCIM, Slack Block Kit,
agregadores sin rutas, stubs 501, y `v2/profitability` que desenvuelve v1 a
propósito).

De los 4 que este documento clasificó inicialmente como «pendientes reales», al
revisarlos uno a uno **solo 2 lo eran**:

| Fichero | Veredicto |
|---|---|
| `accounting_hub` (6 rutas) | Interno → migrar |
| `currency_sync` (2 rutas) | Interno → migrar |
| `bi_embed` (6 rutas) | **Exento**: contrato con embebedores externos (iframes de terceros, JS SDK); `/sdk-config` es público |
| `v2/meta` (1 ruta) | **Exento**: descubrimiento de versión público; consumidores externos leen `api_version` en la raíz |

Cobertura efectiva: **97,5%**.

### 2.3 ✅ Aspectos sólidos verificados

- **Un solo head de Alembic** (`088_portal_translations`): sin ramas divergentes.
- **Capas limpias**: la lógica está en `services/`; los handlers delegan.
- **Suite de guard-tests notable** — el proyecto se autoaudita en CI:
  `test_router_conflicts` (rutas duplicadas), `test_abac_registry_completeness`,
  `test_schema_layer_consistency` (prohíbe schemas Pydantic inline),
  `test_db_sync_endpoints` (prohíbe sesión sync en endpoints async),
  `test_soft_delete_pattern`, `test_pydantic_v2_migration`, `test_i18n_complete`,
  `test_accessibility`. Es una práctica madura y poco común.
- **Interceptor de respuesta bien diseñado** (`frontend/src/services/api/_core.ts:50-74`):
  desenvuelve ambos envelopes con guardas estrictas de 2 claves exactas para no
  tocar payloads que casualmente tengan `data`.

---

## 3. Calidad de código

### 3.1 ✅ Lint prácticamente limpio

`ruff check app tests`: **37 avisos** en 201k LOC (25 `F401` import sin usar,
12 `W293` espacios), **todos auto-corregibles** con `--fix`.

### 3.2 🟠 MEDIA — 883 `except Exception`, de los cuales 85 silencian por completo

Uno por cada ~190 LOC de backend. No hay `except:` desnudos (0). Pero **85 son
`try/except/pass`** (`S110`), es decir, tragan el error sin log ni tratamiento.

> Corrección de esta auditoría: una versión anterior de este documento afirmaba
> «0 `except: pass`». Era falso — un `grep` multilínea mal construido. La cifra
> correcta, medida con `ruff --select S110`, es **85**.

Capturar `Exception` de forma tan extendida convierte errores de programación en
degradación silenciosa; los 85 que además hacen `pass` son invisibles en producción.

**Corrección:** activar `BLE001` (ya hay 61 `noqa` esperándola) y estrechar a
excepciones concretas, priorizando los 85 `S110`.

### 3.3 🟡 BAJA — Deuda declarada

32 `TODO` (0 `FIXME`/`HACK`/`XXX`), 63 `type: ignore`, 5 endpoints que devuelven
501 (`labels.py`, `collaborative.py` son stubs completos).

---

## 4. Funcionalidad

### 4.1 🔴 ALTA (transitoria) — 86 tests de backend en rojo

Estado actual de la suite: **86 fallan, 1.720 pasan, 17 skip, 1 xfail** (11 min con
`-n auto`). Es el *fallout* del refactor del envelope en curso, no defectos de
producto: los endpoints ya devuelven `{data,meta}`/`{items,meta}` y estos tests
aún leen la shape antigua. Bajó de 318 a 86 en esta sesión.

Concentración: `test_business_logic_v236` (15), `test_v24_features` (14),
`test_platform_flows` (10), `test_psa_critical_flows` (7), `test_ai_governance` (6).

Bloquea release hasta cerrarse. `remaining_failures.txt` en la raíz del repo está
**desfasado** (refleja 84 fallos de un estado anterior) y debería borrarse.

### 4.2 ✅ Suite de frontend verde

`tsc --noEmit` sin errores; vitest **25 ficheros / 86 tests** en verde.

### 4.3 Nota sobre paralelización

La suite es **xdist-safe**: serial y `-n auto` producen el mismo resultado
(318 = 318 en la medición de control). Pasar de 64 a 11 minutos es una mejora de
CI inmediata y gratuita.

---

## 5. Usabilidad

### 5.1 🟠 MEDIA — Deuda de i18n: 1.419–2.017 claves por idioma

`npm run check:i18n` → `ok: false`. Base en español; faltan claves en los 7 idiomas:

| Idioma | Claves faltantes |
|---|---:|
| fr | 2.017 |
| de | 2.015 |
| pt | 2.015 |
| it | 2.015 |
| en | 1.419 |
| pl | 1.419 |
| zh | 1.419 |

Matiz importante: **es deuda conocida y congelada, no un defecto ignorado**. CI
usa `check:i18n:ci` → `check:i18n:no-new-debt`, que impide *añadir* deuda pero no
exige completitud. Aun así, **el inglés con 1.419 claves sin traducir** es un
riesgo comercial si se vende fuera de mercados hispanohablantes: módulos enteros
(`ai`, `client_portal`, `inbox`, `absences`) caen a español.

### 5.2 🟡 BAJA — 1.753 anotaciones `: any` en TypeScript

El proyecto mide esto (`type:coverage --at-least 75`), así que está gobernado, pero
1.753 `any` erosionan la garantía que justifica el 100% de TS.

### 5.3 ✅ `console.*`: 29 de 33 son legítimos

Desglosado: 17 `console.error` + 12 `console.warn` (reporte de error legítimo en
cliente) y solo ~4 `console.log`/`console.info`, de los cuales 2 son
reasignaciones (`console.log = ...`) usadas para silenciar en tests.

> Corrección: una versión anterior de este documento contaba «33 `console.*` en
> código de producción» como deuda. Al desglosarlo por nivel, no lo es.

### 5.4 ✅ Accesibilidad con proceso real

`docs/A11Y_WCAG_AUDIT.md` define dos capas (automatizada y manual), con
`lint:a11y:report`, `lint:a11y:strict:core` (`--max-warnings 0` sobre ficheros
núcleo) y baseline E2E con Playwright. Existe `tests/test_accessibility.py`.

---

## 6. Plan de acción priorizado

| # | Acción | Sev. | Esfuerzo |
|---|---|---|---|
| 1 | Acotar por `requester_client_id` en CSAT (`csat_service.py:13`) y comentarios (`comment_service.py:47`) | 🔴 | 1 h |
| 2 | Cerrar los 86 tests del refactor del envelope y commitear el Lote 3 | 🔴 | 0,5–1 d |
| 3 | `require_portal_client` → dependencia `Depends` + guard-test global de authz sobre `app.routes` | 🟠 | 0,5 d |
| 4 | Activar `S` (bandit) y `B` (bugbear) en `ruff.toml`; triar resultado; purgar `noqa` inertes | 🟠 | 0,5 d |
| 5 | Traducir al menos el inglés (1.419 claves) | 🟠 | según recurso |
| 6 | Estrechar los `except Exception` de servicios de integración (activar `BLE001`) | 🟠 | iterativo |
| 7 | Resolver los ~200 imports diferidos o actualizar `CIRCULAR_IMPORTS.md` | 🟠 | 1 d |
| 8 | Lote 4 del envelope: 4 ficheros / 15 rutas | 🟡 | 0,5 d |
| 9 | Ampliar `ABAC_ROUTE_REGISTRY` más allá de los 12 prefijos críticos | 🟡 | 1 d |
| 10 | Seed: generar el secreto HMAC aleatoriamente | 🟡 | 15 min |
| 11 | `ruff --fix` (37), borrar `remaining_failures.txt`, quitar 33 `console.*` | 🟡 | 30 min |
| 12 | Adoptar `-n auto` en CI (64 min → 11 min) | ✅ mejora | 15 min |

## 6.b Registro de resolución (misma sesión, 2026-07-31)

| # | Acción | Estado | Evidencia |
|---|---|---|---|
| 1 | IDOR de CSAT acotado por `requester_client_id` | ✅ | `csat_service.py:12-25`; PoC en verde |
| 1 | IDOR de comentarios: `get_ticket_or_404` → `get_client_ticket_or_404` (client_id obligatorio) | ✅ | `comment_service.py:46`; PoC en verde |
| 3 | `require_portal_client` → dependencia `get_current_portal_client`; 9 call sites convertidos | ✅ | rutas con auth declarativa 1.976 → 1.983 |
| 3 | Guard-test global de authz sobre `app.routes` + allowlist razonada | ✅ | `tests/test_route_auth_coverage.py` (2 tests en verde) |
| 4 | `S` (bandit) y `B` (bugbear) activados en `ruff.toml` | ✅ | `ruff check app tests` → All checks passed |
| 1.8 | Validación estricta del `org_id` antes de interpolarlo en SQL de OLAP | ✅ | `query_engine.py:_safe_org_id` |
| 8 | Lote 4 del envelope: `accounting_hub` + `currency_sync` migrados; `bi_embed` y `v2/meta` exentos y documentados en el código | ✅ | — |
| 9 | `ABAC_ROUTE_REGISTRY` 13 → **131 prefijos**; cobertura de los 127 prefijos de la API + `ABAC_EXEMPT_PREFIXES` con motivos | ✅ | 6 tests en `test_abac_registry_completeness.py` |
| 9 | `enforce_abac`: early-out sin políticas + auditoría solo cuando matchea (evita 1 INSERT+COMMIT por request) | ✅ | `abac_enforce.py` |
| 10 | Seed: secreto HMAC → `secrets.token_urlsafe(32)` | ✅ | `seed_parts/enterprise.py:53` |
| 11 | `ruff --fix` (37) y borrado de `remaining_failures.txt` | ✅ | — |
| 12 | `-n auto` en `make test` (64 min → ~11) + `make test-serial` para depurar | ✅ | `Makefile` |
| — | CI: guard-test de authz, aislamiento de portal, `ruff` y **`pip-audit`** añadidos | ✅ | `.github/workflows/abac-guardrails.yml` |
| 2 | Fallout del envelope: 318 → 86 → (pendiente de cierre) | 🔄 | ver §4.1 |

### Cómo se baselinaron los linters nuevos

Activar `S`+`B` produjo 4.561 avisos. Reparto y decisión:

- **3.900 `B008`** — `Depends(...)` en argumentos por defecto: es el idioma de
  FastAPI. Ignorado globalmente, con el motivo escrito en `ruff.toml`.
- **423 `B904`**, **7 `S311`**, **6 `S603`** — deuda de trazabilidad y falsos
  positivos (random de seeds/simulación, subprocess sin shell que ya es la forma
  correcta). Ignorados con motivo.
- **216 restantes** — anotados con `# noqa: <REGLA>` en su sitio mediante
  `ruff check --add-noqa`.

La diferencia con los 472 `noqa` preexistentes que este informe critica en §1.4 es
deliberada: **estos referencian reglas que SÍ están activas**, así que cualquier
violación nueva rompe CI. Los antiguos apuntaban a reglas desactivadas y no
suprimían nada.

Nota honesta: baselinar no arregla los 85 `S110` ni los 45 `S310`. Detiene la
hemorragia; el triaje sigue pendiente (§1.9 y §3.2).

## 7. Qué NO cubre esta auditoría

Para que el alcance quede claro y no se lea como una garantía que no es:

- **CVEs de dependencias: no escaneado en esta sesión.** No hay `pip-audit`, `safety` ni `bandit`
  en el entorno. Las 117 dependencias están pineadas, lo que es bueno para la
  reproducibilidad pero *malo* para el parcheo: un pin nunca recibe arreglos de
  seguridad solo. **Recomendación: añadir `pip-audit` a CI** — es el hueco más
  grande que queda en la parte de seguridad.
- **Frontend `npm audit`:** no ejecutado.
- **Rendimiento y N+1:** no perfilado. Existen `docs/INDEX_TUNING.md` y
  `docs/SEARCH_PERFORMANCE.md` y un test anti-N+1
  (`test_dashboard_extended.py::test_profitability_avoids_n_plus_one_queries`),
  pero no se ha medido nada bajo carga.
- **E2E de Playwright:** no ejecutados (15 ficheros en `tests_e2e/`).
- **Revisión de índices de BD y planes de consulta:** no realizada.
- **Pentest real** (fuzzing de autenticación, escalada de privilegios más allá de
  los dos IDOR encontrados, SSRF en las integraciones salientes): no realizado.
  Los dos IDOR se encontraron auditando el patrón de authz; **es razonable esperar
  más instancias de la misma clase** en la superficie de portal hasta que se
  aplique la acción 3.

## 8. Valoración global

Producto grande (300k+ LOC) con **madurez de ingeniería por encima de la media**:
lint casi limpio, dependencias totalmente pineadas, capas respetadas, un solo head
de migraciones, y una batería de guard-tests que hace cumplir invariantes
arquitectónicas en CI — algo que la mayoría de proyectos de este tamaño no tiene.

Los dos problemas serios son **acotados y de la misma familia**: la superficie del
portal de cliente autentica pero no autoriza por tenant en dos endpoints, porque la
authz se hace a mano en el cuerpo en lugar de por dependencia. Arreglar el patrón
(acción 3) elimina la clase entera de fallo, no solo las dos instancias.

El riesgo mayor a corto plazo no es de seguridad sino de **entrega**: 86 tests en
rojo por un refactor a medio camino.
