# Auditoría integral — 2ª pasada (2026-08-02)

Alcance: calidad de código, seguridad, arquitectura, usabilidad y funcionalidad.

Esta pasada **no repite** la anterior (`AUDIT_2026_07_FULL.md`). Hace dos cosas:
verifica que lo corregido aguanta, y ataca deliberadamente lo que aquella dejó
declarado como no cubierto — CVEs de dependencias, N+1, índices, E2E y, sobre todo,
la predicción de que quedaban **más instancias de la misma clase de IDOR**.

Esa predicción se ha confirmado.

---

## 0. Verificación de la pasada anterior

| Corrección | Estado hoy |
|---|---|
| IDOR CSAT y comentarios de portal | ✅ PoC en verde |
| `require_portal_client` → dependencia | ✅ 1.983 rutas con authz declarativa |
| Guard-test de cobertura de authz | ✅ 2/2 |
| Registro ABAC completo (131 prefijos) | ✅ 6/6 |
| Inyección SQL en filtro OLAP | ✅ `_safe_org_id` |
| Linters de seguridad `S`/`B` | ✅ `ruff check app tests` limpio |
| Suite backend | ✅ **1.814 passed, 0 failed** |

Todo lo corregido aguanta. Los hallazgos de abajo son **nuevos**.

---

## 1. 🔴 ALTA — Fuga cross-tenant total del wiki de portal

**Ficheros:** `app/services/client_portal_service.py:1590` y `:1600`

Los endpoints autentican **bien** (`Depends(get_current_client)`), pero las funciones
de servicio detrás **ni siquiera reciben el cliente**:

```python
def portal_wiki_pages(db: Session) -> list:            # <- sin current_client
    pages = db.query(WikiPage).filter(
        WikiPage.visibility == "portal",
        WikiPage.is_published == True,
    ).order_by(WikiPage.title).all()

def portal_wiki_page_detail(page_id: str, db: Session) -> dict:   # <- sin current_client
    page = db.query(WikiPage).filter(
        WikiPage.id == page_id, WikiPage.visibility == "portal",
    ).first()
```

`WikiPage` y `WikiSpace` tienen `organization_id` y `project_id`
(`app/models/epics.py:22,38`), así que el wiki **sí es un recurso con tenencia**.

**Impacto — peor que los dos IDOR de la pasada anterior.** Aquellos exigían conocer
el id de un ticket ajeno; este no exige nada:

1. `GET /api/v1/portal/wiki/pages` devuelve **todas** las páginas visibles en portal
   de **todas las organizaciones**, con sus ids y títulos. Es la enumeración servida.
2. `GET /api/v1/portal/wiki/pages/{page_id}` devuelve el **contenido completo** de
   cualquiera de ellas.

Cualquier cliente de portal de cualquier cliente comercial puede leer la
documentación de portal de todos los demás.

**Confirmado empíricamente.** El cliente atacante recuperó el contenido literal de
la página sembrada para la víctima:

```
GET /api/v1/portal/wiki/pages          -> 200, incluye la página del cliente A
GET /api/v1/portal/wiki/pages/{id}     -> 200
   {"data": {"title": "Runbook confidencial del cliente A",
             "content": "Credenciales y procedimientos internos del cliente A"}}
```

PoC: `tests/test_portal_wiki_tenant_isolation.py` (2 tests, **ambos fallan hoy** a
propósito; pasarán cuando se corrija).

**Corrección:** pasar `current_client` a ambas funciones y acotar por los proyectos
accesibles del cliente, igual que hace `get_project_info`
(`client_portal_service.py:1400-1405`), que sí lo hace bien.

**Lección de método:** la pasada anterior arregló el patrón de *autenticación*
(`Depends`), y eso fue correcto y necesario. Pero autenticar bien no acota nada: aquí
la dependencia está puesta y el fallo persiste porque el **servicio** ignora al
principal. El invariante que falta es «toda función de servicio del portal recibe y
usa la identidad del cliente», y ningún test lo vigila.

---

## 2. 🔴 ALTA — CI no ejecuta la suite de tests

`.github/workflows/` contiene **un solo workflow**, y ejecuta exactamente 5 ficheros
de test de los 193 que hay:

```
test_abac_registry_completeness.py
test_route_auth_coverage.py
test_invoice_tenant_isolation.py
test_portal_ticket_tenant_isolation.py
test_jira_secret_encryption.py
```

**No se ejecutan en CI:** los **1.814 tests** de backend, los **86** de frontend,
`tsc --noEmit`, el build del frontend, ni los 14 ficheros E2E de Playwright.

Combinado con que se commitea directo a `main` sin ramas ni PR, **nada impide que
`main` se rompa**. La suite existe, es buena y tarda 11 minutos con `-n auto`: el
coste de ejecutarla es bajísimo comparado con el riesgo que cubre.

**Corrección propuesta:** añadir un job con `pytest -n auto`, `tsc --noEmit`,
`vitest run` y el build.

> **Estado final: no aplica — CI/CD eliminado por decisión del propietario
> (2026-08-02).** Se llegó a añadir `.github/workflows/ci.yml` con esos cuatro
> pasos, y después se eliminó todo `.github/workflows/` a petición expresa.
>
> Consecuencia, para que quede escrito: **ninguna verificación es automática**. Los
> guard-tests que esta auditoría y la anterior añadieron siguen existiendo y siguen
> siendo válidos, pero solo corren si alguien los lanza a mano:
>
> ```
> make test                  # suite backend completa (-n auto, ~11 min)
> cd frontend && npm run typecheck && npm run test && npm run build
> python -m pytest tests/test_route_auth_coverage.py \
>                  tests/test_portal_principal_is_used.py \
>                  tests/test_portal_wiki_tenant_isolation.py \
>                  tests/test_portal_ticket_tenant_isolation.py \
>                  tests/test_abac_registry_completeness.py -q
> ```
>
> El riesgo descrito arriba (nada impide romper `main`) sigue vigente y pasa a ser
> un riesgo asumido conscientemente, no un descuido.

---

## 3. 🟠 MEDIA — El guardrail de aislamiento multi-tenant está en rojo en CI

`scripts/audit_tenant_isolation.py --strict --baseline …` es un paso del workflow.
Ejecutado hoy:

```
[tenant-audit] STRICT FAIL: new unreviewed tenant findings detected.
EXIT = 1
```

Cifras reales:

```
total queries scanned: 2781
candidates to review:  2329
baseline entries:      1902
new entries:           1913   <- fuera del baseline
```

- El baseline (`scripts/tenant_audit_baseline.txt`) es del **2026-05-17**, mientras
  el código siguió creciendo.
- Ninguno de los hallazgos corresponde a ficheros tocados en la pasada anterior:
  es deuda previa, no una regresión introducida ahora.

> **Corrección a una versión anterior de este documento**, que decía «≥200 hallazgos,
> el número real se desconoce porque el script trunca en 200». Era inexacto: lo que
> se trunca es el *listado*, pero el script **sí imprime el total**
> (`new entries: 1913`). El error fue mío al filtrar la salida. El truncado ahora
> avisa de cuántas entradas omite.

Con 1.913 de 2.329 candidatos fuera del baseline, el baseline no está «algo
desfasado»: ha dejado de describir el código. Regenerarlo sin revisar sería
sellar 2.329 hallazgos sin mirarlos, que es peor que no tenerlo. El triaje real es
trabajo de días, no una regeneración.

El hallazgo §1 es exactamente el tipo de fallo que este script existe para detectar.

---

## 4. 🟠 MEDIA — 40 CVEs en dependencias Python; 27 en un parser de entrada no confiable

`pip-audit` (instalado en esta sesión; antes no existía en el entorno):

| Paquete | CVEs | Versión | Corregido en |
|---|---:|---|---|
| **pypdf** | **27** | 6.1.3 | 6.14.2 |
| pyasn1 | 4 | 0.6.3 | 0.6.4 |
| setuptools | 2 | 81.0.0 | 83.0.0 |
| scikit-learn | 2 | 1.4.2 | 1.5.0 |
| idna | 2 | 3.11 | 3.15 |
| pyarrow | 1 | 17.0.0 | 23.0.1 |
| ecdsa | 1 | 0.19.2 | **sin arreglo** |
| pytest | 1 | 8.4.2 | 9.0.3 (dev) |

Lo que eleva la severidad: **pypdf procesa PDFs subidos por usuarios**
(`app/services/documents_service.py:478` → `PdfReader(io.BytesIO(raw))`). Un parser
de formato complejo con 27 vulnerabilidades conocidas, sobre entrada no confiable, es
la combinación clásica.

`ecdsa` **no tiene versión con arreglo**: hay que decidir si se sustituye la
librería o se acepta el riesgo por escrito.

Esto valida el aviso de la pasada anterior: pinear las 117 dependencias es bueno para
reproducibilidad y malo para parcheo. El paso `pip-audit` ya está añadido al
workflow, así que **este job fallará hasta que se actualicen** — es el
comportamiento deseado, pero conviene saberlo antes de mirar CI.

---

## 5. 🟠 MEDIA — 7 vulnerabilidades high en npm; una en dependencia de producción

`npm audit`: 12 en total (0 críticas, 7 high, 3 moderate, 2 low).

De las 7 high, **6 son transitivas de build** (vite, postcss, js-yaml,
brace-expansion, undici, form-data) — impacto limitado a la cadena de compilación.

La que importa: **`axios` es dependencia de producción** y tiene un ReDoS vía
inyección en nombre de cookie. Es el cliente HTTP de toda la aplicación.

---

## 6. 🟠 MEDIA — Endpoint de LLM sin rate limit, y autenticado por el body

`POST /api/v1/portal-ai/chat` (`app/api/v1/endpoints/ai_modules.py:395`).

Dos cosas, y conviene separarlas para no exagerar:

- **Sí autentica.** El servicio valida `client_token` con `verify_client_token`
  (`ai_modules/client_portal.py:87`) y la sesión se acota por `client_user_id`
  (`:115`). El aislamiento aquí es correcto.
- **Pero el token viaja en el body**, no como dependencia. Es el mismo antipatrón que
  causó los IDOR: invisible al guard-test de authz, que lo clasifica como ruta
  pública y lo tiene en la allowlist con un «PENDIENTE».
- **Y no tiene rate limit.** Es un endpoint que llama a un LLM de pago. El resto de
  la superficie sensible sí está limitada (login 5/min, reset 10/min, portal login
  5/min, webhooks 20/min), así que aquí falta por descuido, no por criterio.

**Impacto:** un cliente legítimo —o un token filtrado— puede quemar presupuesto de
proveedor de IA sin tope.

---

## 7. 🟡 BAJA — Otros

- **115 bucles con `db.query()` dentro** en `app/services` (candidatos a N+1). Hay
  389 usos de eager loading, así que el patrón correcto se conoce y se aplica; no
  están todos cubiertos. No perfilado bajo carga.
- **`update_uat_issue(issue_id, status, db)`** (`client_portal_service.py:1277`) no
  acota por organización. El endpoint exige `require_any_manager`, así que es riesgo
  **cross-organización entre staff interno**, no de portal. Requiere credenciales de
  manager y conocer el id.
- **Email del solicitante en logs** (`service_desk/templates.py:97`): PII en logs,
  relevante para GDPR. Discutible por utilidad de soporte, pero conviene decidirlo.

---

## 7.b 🟠 MEDIA — Peso del bundle: 1,95 MB gzip en un solo chunk

Medido al ejecutar `npm run build` por primera vez en CI (build correcto, 3m45s):

| Chunk | Tamaño | Gzip |
|---|---:|---:|
| `vendor-core` | 6.466 kB | **1.947 kB** |
| `route-misc` | 2.798 kB | 666 kB |
| `vendor-echarts` | 832 kB | 273 kB |
| `vendor-recharts` | 312 kB | 70 kB |
| `route-delivery` | 290 kB | 68 kB |
| `vendor-react` | 217 kB | 68 kB |

Vite avisa de chunks >900 kB. El troceado **existe y funciona** (react, recharts y
echarts ya están separados, y hay 166 usos de `lazy`/`Suspense`), pero `vendor-core`
con 1,95 MB comprimido indica que algo grande sigue sin separarse, y `route-misc`
con 666 kB parece un cajón de sastre de rutas.

**Impacto de usabilidad:** ~2,6 MB comprimidos antes de pintar en la ruta peor. En
una conexión móvil mediocre son varios segundos de pantalla en blanco. Es el tipo de
coste que no aparece en ningún test y que sí se nota en producción.

**RESUELTO en parte.** La causa era que cinco librerías pesadas no tenían regla de
`manualChunks` y caían todas en el cajón por defecto: `plotly.js` (99 MB en
`node_modules`), `livekit-client` (10 MB), `bpmn-js` (6 MB), `@xyflow/react` (3 MB) y
`d3`. Añadidas sus reglas en `vite.config.js`:

| Chunk | Antes (gzip) | Después (gzip) |
|---|---:|---:|
| `vendor-core` | **1.947 kB** | **177 kB** (−91%) |
| `vendor-plotly` | — | 1.430 kB |
| `vendor-livekit` | — | 134 kB |
| `vendor-bpmn` | — | 137 kB |
| `vendor-d3` | — | 44 kB |

El peso total no baja —el código es el que es—, pero deja de pagarse en la carga
inicial: cada una de esas librerías ahora solo se descarga en las rutas que la usan.

De paso, `@testing-library/dom`, `/jest-dom` y `/react` estaban declaradas en
`dependencies` en vez de `devDependencies` (verificado: solo se importan desde
tests). Movidas — 27 → 24 dependencias de producción.

**Pendiente:** `route-misc` sigue en 666 kB gzip. Es el cajón de sastre de páginas
del `manualChunks` por ruta; trocearlo exige decidir agrupaciones por dominio real,
que es criterio de producto más que técnico.

## 8. ✅ Verificado como sólido en esta pasada

- **Validación de subidas** (`documents_service.py:133-156`): allowlist de extensión
  **y** de MIME **y** verificación de magic bytes contra el `Content-Type` declarado,
  con 415 si no coinciden. Por encima de la media.
- **Rate limiting donde importa**: login, cambio y reseteo de contraseña, login de
  portal, webhooks. Correcto salvo la excepción de §6.
- **Índices**: 959 columnas con `index=True` y 44 índices compuestos.
- **E2E**: 14 ficheros de Playwright, incluidos WCAG, regresión de todas las páginas
  y regresión público/protegido. (No ejecutados en esta auditoría ni en CI — §2.)
- **UX de estados**: 1.138 usos de `isLoading`/`isPending`, 541 de `isError`/`onError`,
  166 de `lazy`/`Suspense`. La app no se queda muda mientras carga ni cuando falla.
- **Sin secretos en logs**: la búsqueda de contraseñas/tokens en llamadas a logger no
  encontró ninguno; se registran ids de usuario, no credenciales.

---

## 9. Plan de acción

| # | Acción | Sev. | Esfuerzo |
|---|---|---|---|
| 1 | Acotar `portal_wiki_pages` y `portal_wiki_page_detail` por cliente | 🔴 | 1 h |
| 2 | CI: ejecutar `pytest -n auto`, `tsc`, `vitest` y build | 🔴 | 2 h |
| 3 | Actualizar pypdf a 6.14.2+ (parsea entrada no confiable) | 🟠 | 1 h + regresión |
| 4 | Quitar el truncado a 200 del auditor de tenancy, triar y regenerar baseline | 🟠 | 1 d |
| 5 | Actualizar axios; decidir sobre `ecdsa` (sin arreglo) por escrito | 🟠 | 2 h |
| 6 | Rate limit en `/portal-ai/chat` + moverlo a `Depends(get_current_portal_client)` | 🟠 | 1 h |
| 7 | Guard-test: toda función de servicio del portal recibe la identidad del cliente | 🟠 | 0,5 d |
| 8 | Repartir `vendor-core` (1,95 MB gzip) y trocear `route-misc` | 🟠 | 0,5 d |
| 9 | Resolver los **7 `Circular chunk`** que el build ya emite hoy (prerrequisito para trocear `route-misc`) | 🟠 | 0,5 d |
| 10 | Revisar las columnas `organization_id` del audit #7 que ningún código rellena | 🟠 | 0,5 d |
| 11 | Triar los 115 posibles N+1 (límite superior: hay falsos positivos) | 🟡 | iterativo |
| 12 | Acotar `update_uat_issue` por organización | 🟡 | 30 min |

La acción 7 es la que cierra la **clase** de fallo en lugar de la instancia. Las
acciones 1 y 9 son instancias concretas; sin la 7, seguirán apareciendo.

---

## 9.b Registro de resolución — P0 (2026-08-02)

| # | Acción | Estado | Evidencia |
|---|---|---|---|
| 1 | Wiki de portal acotado por tenencia (`_portal_visible_wiki_filter`) | ✅ | 3 tests en verde, incluido el caso positivo |
| 2 | Workflow `ci.yml` con pytest `-n auto`, tsc, vitest y build | ⛔ revertido | CI/CD eliminado por decisión del propietario — ver §2 |
| 3 | Guard-test de clase: el principal del portal declarado debe usarse | ✅ | `tests/test_portal_principal_is_used.py` |

### Cómo se acotó el wiki

Un espacio wiki es de proyecto **o** de organización (ver `WikiSpace`), así que el
filtro admite los dos casos y deniega por defecto:

- espacios cuyo `project_id` está entre los proyectos accesibles del cliente, o
- espacios sin proyecto cuya `organization_id` coincide con la del cliente.

Cliente sin proyectos ni organización: no ve nada (`false()`).

Se añadió además un **test de contrapeso**
(`test_portal_client_still_sees_own_wiki_page`): sin él, «arreglar» la fuga
devolviendo siempre una lista vacía también habría pasado los tests de aislamiento.

### El guard-test se verificó reintroduciendo el bug

Un guardrail que nunca ha demostrado atrapar su fallo no sirve. Se revirtió
temporalmente la llamada a la forma vulnerable
(`_svc.portal_wiki_pages(db)`, sin el cliente) y el test **falló**; restaurado el
fix, pasa. La invariante que vigila es la firma exacta de los tres IDOR
encontrados: *el principal se declara pero no se usa*.

Opt-out explícito: nombrar el parámetro `_client` cuando el endpoint solo necesita
autenticar y no autorizar por ese principal (p. ej. `get_dynamic_forms_public`,
que devuelve configuración global idéntica para todos). Queda visible en el diff.

### Sobre los pasos no bloqueantes

Se marcaron temporalmente `Tenant static audit (strict)` y
`Dependency vulnerability scan` como `continue-on-error`, para que la entrada de la
suite en CI diera señal creíble en lugar de nacer en rojo permanente.

Quedó sin efecto al eliminarse CI/CD por completo (§2). Ambas comprobaciones siguen
disponibles como scripts manuales:

```
python scripts/audit_tenant_isolation.py --strict --baseline scripts/tenant_audit_baseline.txt
pip-audit --requirement requirements.txt --strict
```

## 9.c Registro de resolución — P1 (2026-08-02)

| # | Acción | Estado | Resultado |
|---|---|---|---|
| 4 | pypdf 6.1.3 → **6.14.2** | ✅ | 27 CVEs cerrados en el parser de PDFs subidos |
| 4 | pyasn1 → 0.6.4, idna → 3.15, scikit-learn → 1.5.0, pyarrow → 23.0.1 | ✅ | suite verde, sin regresiones |
| 4 | setuptools 81 → 83 | ⛔ bloqueado | **torch 2.11 exige `setuptools<82`**. Revertido para no romper el grafo (`pip check` limpio) y anotado en `requirements.txt` |
| 5 | axios → **1.19.0** | ✅ | npm audit: 12 → **3** vulnerabilidades, **0 high, 0 critical** |
| 5 | ecdsa 0.19.2 | ⚠️ sin arreglo | No existe versión corregida. Decisión pendiente: sustituir la librería o aceptar el riesgo por escrito |
| 6 | Auditor de tenancy: truncado explícito + cifras reales | ✅ | 1.913 hallazgos nuevos de 2.329 candidatos (ver §3) |
| 7 | `/portal-ai/chat`: `Depends(get_current_portal_client)` + `20/minute` | ✅ | Sale del allowlist de rutas públicas; **cambia el contrato** (ver abajo) |
| 8 | `manualChunks` para plotly/livekit/bpmn/xyflow/d3 | ✅ | `vendor-core` 1.947 → **177 kB gzip** (−91%) |
| 8 | `@testing-library/*` → devDependencies | ✅ | 27 → 24 dependencias de producción |
| 8 | Trocear `route-misc` (666 kB gzip) | ⏸ | Requiere decidir agrupación por dominio |

### Cambio de contrato en `/portal-ai/chat`

Antes el token de cliente viajaba en el body como `client_token`; ahora se autentica
por cookie de portal o cabecera `Authorization`, como el resto del portal.

El frontend **no se ve afectado**: ya usaba la variante por cookie
(`POST /portal/ai-chat`). Sí afectaría a integraciones externas que siguieran
enviando `client_token` en el body — no consta ninguna en el repo.

## 9.d Registro de resolución — P2 (2026-08-02)

| Acción | Estado | Detalle |
|---|---|---|
| `update_uat_issue` acotado por organización | ✅ | Vía `session → project → organization` |
| Validador de URLs salientes + aplicado en eSign e integraciones | ✅ | `app/core/outbound_url.py`; 17 de los 45 sitios S310 |
| N+1 en la status page **pública** | ✅ | Una consulta en vez de una por componente |
| N+1 en el catálogo de marketplace | ✅ | `in_()` en vez de una consulta por instancia |
| PII: email completo en logs → solo dominio | ✅ | `service_desk/templates.py` |
| Trocear `route-misc` por dominio | ⛔ revertido | Introducía chunks circulares — ver abajo |
| Triaje de los 85 `S110` | ⏸ | No abordado |
| i18n inglés (1.419 claves) | ⏸ | No abordado |
| Triaje de los ~1.900 hallazgos de tenancy | ⏸ | Trabajo de días |

### `update_uat_issue`: por qué no se filtra por `organization_id`

`UATIssue` **tiene** columna `organization_id`, y filtrar por ella habría sido lo
obvio. No sirve: no se rellena al crear la incidencia
(`UATIssue(session_id=..., reported_by=..., **payload)`), así que está a `NULL` en
todas las filas y el filtro las habría excluido todas. El scoping va por
`session → project → organization`, igual que `respond_to_fr`.

Es un aviso más general: **hay columnas `organization_id` añadidas por el audit #7
que ningún código rellena**. Filtrar por ellas «porque existen» rompe cosas de forma
silenciosa. Merece su propia revisión.

### SSRF: 17 de 45, no los 45

`app/core/outbound_url.py` generaliza la comprobación que ya existía solo para la URL
de discovery de OIDC (esquema http/https, sin hosts locales, sin IPs privadas). Se
aplicó en los puntos por donde pasan más llamadas: `esign_providers._http` y sus 5
sitios OAuth, y los 5 de `integrations.py`.

Quedan ~28 sitios (sobre todo `mfa_service.py`, `scheduled_reports.py`,
`bookings_service.py`). No se resuelve DNS a propósito: sería TOCTOU y añadiría un
fallo externo a una validación. Defensa completa frente a DNS rebinding necesita
control de egreso a nivel de red.

### Por qué se revirtió el troceo de `route-misc`

Funcionaba en tamaño: `route-misc` bajaba de 666 a 481 kB gzip y aparecían seis
chunks de dominio (`settings` 19 kB, `itsm` 27, `governance` 28, `process` 38,
`collab` 40, `people` 43).

Pero los avisos de `Circular chunk` de rollup pasan de **7 a 11**.

> **Hallazgo nuevo, medido al comprobar esto:** el build **ya emite hoy 7 avisos de
> `Circular chunk`** con la configuración de `main`, p. ej.
> `route-delivery -> route-misc -> route-service-desk -> route-delivery`.
> No los introduce este cambio; estaban ahí y nadie los veía porque el filtro
> habitual de la salida del build no los muestra. Un grafo de chunks circular puede
> alterar el orden de carga en runtime. **Merece revisión propia.**

Las páginas se importan entre sí a través de componentes compartidos, así que
agruparlas por dominio añade 4 ciclos más. Meter más ciclos en un grafo ya circular
a cambio de 185 kB, sin poder verificar el orden de carga en un navegador, no
compensa.

**Requisito previo para reintentarlo:** extraer a módulos propios lo que las páginas
comparten, resolver los 7 ciclos actuales, y luego volver a agrupar. El troceo de
*vendors*, que es el que dio el −91%, no tiene este problema y se mantiene.

### Sobre el detector de N+1

Los «115 bucles con `db.query`» del §7 son un límite superior, no un recuento de
fallos. Al mirarlos uno a uno aparecen falsos positivos claros: por ejemplo
`client_service.list_contacts()` es una comprehension cuya *fuente* es la consulta,
que se ejecuta una sola vez. De los 22 que caían en funciones de listado, se
corrigieron los dos con impacto real; el resto necesita revisión caso a caso.

## 10. Qué NO cubre esta pasada

- **E2E de Playwright**: no ejecutados (requieren navegadores y app levantada).
- **Perfilado real de rendimiento**: los 115 N+1 son candidatos estáticos, no
  mediciones. No se ha medido latencia ni bajo carga.
- **Planes de consulta de BD** y tuning de índices reales.
- **a11y ejecutado**: no se corrió `lint:a11y` en esta pasada; solo se constató que
  el proceso y los tests existen.
- **Pentest de la superficie interna** (staff): esta pasada se centró en el portal de
  cliente porque ahí está el principal distinto. El registro de `update_uat_issue`
  sugiere que el eje **cross-organización entre usuarios internos** merece su propia
  revisión.
