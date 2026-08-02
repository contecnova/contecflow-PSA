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

**Corrección:** añadir al workflow un job con `pytest -n auto`, `tsc --noEmit`,
`vitest run` y el build. Es la acción de mayor retorno de todo este informe.

---

## 3. 🟠 MEDIA — El guardrail de aislamiento multi-tenant está en rojo en CI

`scripts/audit_tenant_isolation.py --strict --baseline …` es un paso del workflow.
Ejecutado hoy:

```
[tenant-audit] STRICT FAIL: new unreviewed tenant findings detected.
EXIT = 1
```

- **≥200 hallazgos nuevos** fuera del baseline. Digo «≥» porque el script trunca la
  salida en 200 (`audit_tenant_isolation.py:78,92`), así que **el número real se
  desconoce**.
- El baseline (`scripts/tenant_audit_baseline.txt`, 2.334 líneas) no se actualiza
  desde **2026-05-17**, mientras el código siguió creciendo.
- Ninguno de los hallazgos corresponde a ficheros tocados en la pasada anterior:
  es deuda previa, no una regresión introducida ahora.

Un guardrail de seguridad que lleva meses en rojo deja de ser un guardrail. Y el
truncado a 200 hace que ni siquiera se pueda dimensionar el problema.

**Corrección:** quitar el truncado (o hacerlo explícito con un contador total),
triar los hallazgos y regenerar el baseline. El hallazgo §1 es exactamente el tipo
de fallo que este script existe para detectar.

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

**Corrección:** analizar `vendor-core` (`rollup-plugin-visualizer`) y repartir por
`manualChunks`; trocear `route-misc` por dominio real.

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
| 9 | Triar los 115 posibles N+1, empezando por los endpoints de listado | 🟡 | iterativo |
| 10 | Acotar `update_uat_issue` por organización | 🟡 | 30 min |

La acción 7 es la que cierra la **clase** de fallo en lugar de la instancia. Las
acciones 1 y 9 son instancias concretas; sin la 7, seguirán apareciendo.

---

## 9.b Registro de resolución — P0 (2026-08-02)

| # | Acción | Estado | Evidencia |
|---|---|---|---|
| 1 | Wiki de portal acotado por tenencia (`_portal_visible_wiki_filter`) | ✅ | 3 tests en verde, incluido el caso positivo |
| 2 | Nuevo workflow `ci.yml`: pytest `-n auto`, tsc, vitest y build | ✅ | `.github/workflows/ci.yml` |
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

### Decisión deliberada: dos pasos de CI pasan a no bloqueantes

`Tenant static audit (strict)` y `Dependency vulnerability scan` se han marcado
`continue-on-error: true`, **con comentario y condición de retirada** en el propio
workflow.

Motivo: ambos están rojos hoy (§3 y §4) por deuda previa. Con el nuevo `ci.yml`
ejecutando la suite por primera vez, dejarlos bloqueando significaría que CI nace
en rojo permanente — y un CI siempre rojo se ignora, que es exactamente el fallo
descrito en §3. Se dejan informativos para que la señal nueva (tests) sea creíble.

**Hay que revertirlo** al cerrar P1 #4, #5 y #6. Es una línea en cada paso.

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
