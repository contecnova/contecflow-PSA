# Canonical API Response Wrapper — Migration Plan (audit #67)

## Contexto

El audit #67 identificó que los endpoints del backend devuelven shapes de respuesta
inconsistentes:

- Algunos devuelven `{data, meta}` (paginado custom)
- Otros devuelven un array crudo `[...]`
- Otros devuelven `{message}` u `{ok: True, message}`
- Otros devuelven el objeto recurso directamente

Esto fuerza al frontend a usar heurísticos (`unwrapList`, fallbacks múltiples) y rompe
el contrato implícito de la API.

## Objetivo

Unificar todas las respuestas en un wrapper canónico de dos shapes:

- **`APIResponse[T]`** → para respuestas single-object: `{ data: T, meta?: ResponseMeta }`
- **`APIListResponse[T]`** → para respuestas de lista: `{ items: T[], meta: ResponseMeta }`

`ResponseMeta` incluye `total`, `page`, `page_size`, `has_more` (todos opcionales).

## Contrato canónico

Definido en `app/core/responses.py`:

```python
from app.core.responses import APIResponse, APIListResponse, ResponseMeta

@router.get("/items", response_model=APIListResponse[ItemOut])
def list_items(page: int = 1, page_size: int = 50, ...):
    q = svc.get_items_query(...)
    items, total, _ = paginate_query(q, page, page_size)
    return APIListResponse.ok(items=items, total=total, page=page, page_size=page_size)

@router.get("/items/{id}", response_model=APIResponse[ItemOut])
def get_item(id: str, ...):
    item = svc.get_item(id)
    return APIResponse.ok(data=item)
```

## Pilot endpoints (ya migrados)

Estos 3 endpoints sirven de referencia para futuras migraciones:

| Endpoint                           | Archivo                                          | Shape antigua          | Shape nueva                |
|------------------------------------|--------------------------------------------------|------------------------|----------------------------|
| `GET /api/v1/alerts`               | `app/api/v1/endpoints/alerts.py`                 | `List[AlertOut]`       | `APIListResponse[AlertOut]`|
| `GET /api/v1/deliverables/all/overview` | `app/api/v1/endpoints/deliverables.py`     | `List[dict]`           | `APIListResponse[dict]`    |
| `GET /api/v1/sprints`              | `app/api/v1/endpoints/sprints.py`                | `List[dict]`           | `APIListResponse[dict]`    |

### Wave P2 (2026-05-16)

Migración adicional aplicada en dominio collaboration (portal/compliance/bots):

| Endpoint | Archivo | Shape antigua | Shape nueva |
|---|---|---|---|
| `GET /api/v1/portal/collaboration/conversations` | `app/api/v1/endpoints/collaboration_portal.py` | `List[dict]` | `APIListResponse[dict]` |
| `GET /api/v1/portal/collaboration/notifications` | `app/api/v1/endpoints/collaboration_portal.py` | `List[dict]` | `APIListResponse[dict]` |
| `GET /api/v1/collaboration/slash/help` | `app/api/v1/endpoints/collaboration/bots.py` | `{commands:[...]}` | `APIListResponse[dict]` |
| `GET /api/v1/collaboration/decisions` | `app/api/v1/endpoints/collaboration/compliance.py` | `List[dict]` | `APIListResponse[dict]` |

Caller frontend actualizado para transición sin roturas:

- `frontend/src/pages/portal-client/portalClientContext.tsx` ahora unifica `APIListResponse` con interceptor (similar a `frontend/src/services/api.ts`).

Migración adicional aplicada en dominio BI Report Builder v2:

| Endpoint | Archivo | Shape antigua | Shape nueva |
|---|---|---|---|
| `GET /api/v1/bi/reports/v2/presets` | `app/api/v1/endpoints/bi_report_builder_v2.py` | `{items,count}` | `APIListResponse[dict]` |
| `GET /api/v1/bi/reports/v2/categories` | `app/api/v1/endpoints/bi_report_builder_v2.py` | `{items:[str]}` | `APIListResponse[{name}]` |
| `GET /api/v1/bi/reports/v2/components` | `app/api/v1/endpoints/bi_report_builder_v2.py` | `{items:[...]}` | `APIListResponse[dict]` |
| `GET /api/v1/bi/reports/v2/layouts` | `app/api/v1/endpoints/bi_report_builder_v2.py` | `{items:[...]}` | `APIListResponse[dict]` |
| `GET /api/v1/bi/reports/v2/templates` | `app/api/v1/endpoints/bi_report_builder_v2.py` | `{items:[...]}` | `APIListResponse[dict]` |

Single-object responses del mismo dominio se estandarizaron a `APIResponse[T]`.

Wave adicional aplicada en dominios Projects/Tasks/Users:

| Endpoint | Archivo | Shape antigua | Shape nueva |
|---|---|---|---|
| `GET /api/v1/projects/milestones` | `app/api/v1/endpoints/projects/__init__.py` | `List[dict]` | `APIListResponse[dict]` |
| `GET /api/v1/tasks/dependencies` | `app/api/v1/endpoints/tasks.py` | `List[dict]` | `APIListResponse[dict]` |
| `GET /api/v1/tasks/dependencies/{project_id}` | `app/api/v1/endpoints/tasks.py` | `List[dict]` | `APIListResponse[dict]` |
| `GET /api/v1/users/org-chart` | `app/api/v1/endpoints/users.py` | `dict` | `APIResponse[dict]` |

Caller frontend actualizado para el endpoint de users org-chart:

- `frontend/src/pages/OrgChartPage.tsx` soporta ambos shapes durante transición (`r.data?.data ?? r.data`).

### Frontend callers actualizados

- `frontend/src/components/layout/NotificationCenter.jsx` (alerts)
- `frontend/src/components/layout/AlertsDrawer.jsx` (alerts)
- `frontend/src/hooks/useNotificationBadges.js` (alerts)
- `frontend/src/hooks/useAlerts.js` (alerts)
- `frontend/src/pages/AlertsPage.jsx` (alerts)
- `frontend/src/pages/NotificationsPage.jsx` (alerts)
- `frontend/src/pages/DeliverablesPage.jsx` (deliverables overview)
- `frontend/src/components/ui/EntitySelect.jsx` (sprints)
- `frontend/src/components/layout/OnboardingWizard.jsx` (sprints)
- `frontend/src/hooks/useSprints.js` (sprints)
- `frontend/src/pages/SprintPlanningPage.jsx` (sprints)

Patrón usado en todos los callers (defensive — tolera ambos shapes durante la transición):

```js
sprintsApi.list(...).then(r => r.data?.items ?? r.data ?? [])
```

`CalendarPage.jsx` y `KanbanAdvancedPage.jsx` ya usaban `unwrapList` o un fallback que
detecta `.items`, así que no requieren cambios.

## Estado a 2026-07-31 — oleada masiva completada

La migración ya no es incremental por dominio: se ejecutó en lotes grandes.

| Lote | Alcance | Estado |
|---|---|---|
| Piloto | `skills.py` | ✅ commit `2f07641` |
| Lote 1 | ~18 dominios | ✅ commit `7f8bb96` |
| Lote 2 | ~26 dominios | ✅ commit `4e2aade` |
| Lote 3 | ~108 ficheros de endpoints + 65 de tests | ✅ (este commit) |
| Lote 4 | `accounting_hub`, `currency_sync` | ✅ (este commit) |

**Cobertura: 151 de 163 ficheros de endpoints usan `app.core.responses`.**

### Exentos a propósito — no migrar

Los 12 restantes están exentos por motivos que están escritos también en el
docstring de cada fichero:

| Fichero | Motivo |
|---|---|
| `ws.py`, `collaboration/ws.py` | WebSocket: no hay body HTTP |
| `collaboration/tus.py` | Protocolo TUS: headers y status los fija la spec |
| `scim.py` | Shape impuesta por el RFC de SCIM 2.0 |
| `slack_block_kit.py` | Payload Block Kit de Slack |
| `bi_embed.py` | Contrato con embebedores externos (iframes de terceros, JS SDK); `/sdk-config` es público |
| `v2/meta.py` | Descubrimiento de versión público: consumidores externos leen `api_version` en la raíz |
| `v2/profitability.py` | Consumidor: desenvuelve el envelope de v1 y mantiene su propia shape v2 |
| `auth.py`, `projects/projects.py` | Agregadores de routers, 0 rutas propias |
| `labels.py`, `collaborative.py` | Stubs que solo lanzan 501 |

Nota: los endpoints de BI para PowerBI en `mfa.py` también son contrato externo y
devuelven la shape cruda (ver comentario inline «Contrato externo BI»).

### Cómo se hizo el fallout de tests

Los tests se arreglaron con pases dirigidos **solo a las líneas que el informe de
pytest marcaba como fallidas** (evidencia, no barrido ciego sobre el árbol):

1. `.json()["k"]` → `.json()["data"]["k"]` en la línea que falla.
2. Indirección: si falla `V["k"]`, arreglar la asignación `V = res.json()` y los
   `return r.json()` de los helpers.
3. `data` vs `items` **inferido del dict que imprime el propio error** de pytest.
4. Cola manual para los casos con lógica defensiva (`data.get("x", data)`).

## Scope total estimado (histórico)

- **~134 endpoints** en `app/api/v1/endpoints/*.py` con respuestas de lista o single-object
- **~135 archivos frontend** que consumen esos endpoints (hooks + pages + components)

## Estrategia: migración incremental por dominio

NO se hace breaking change masivo. Por cada dominio:

1. Migrar todos los endpoints del dominio al wrapper canónico (backend).
2. Actualizar todos los callers del frontend que tocan ese dominio.
3. Tests: cada test que asserts `isinstance(res.json(), list)` debe pasar a comprobar
   `res.json()["items"]` y `res.json()["meta"]`.
4. PR independiente por dominio. Que pase CI y review aislado.

### Orden propuesto (prioridad alta → baja)

| Prioridad | Dominio          | Endpoints aprox. | Por qué                                          |
|-----------|------------------|------------------|--------------------------------------------------|
| P0        | alerts           | 4                | Piloto. Hecho.                                   |
| P0        | sprints          | ~13              | Piloto parcial (1/13). Faltan 12 endpoints.      |
| P0        | deliverables     | 8                | Piloto parcial (1/8). Faltan 7 endpoints.        |
| P1        | projects         | ~15              | Core. Tocan muchos features.                     |
| P1        | tasks            | ~12              | Core. Kanban / planning / sprints depende.       |
| P1        | users            | ~10              | Auth y permissions queries.                      |
| P1        | timesheets       | ~10              | Core finanzas.                                   |
| P2        | invoices         | ~8               | Finanzas. Crítico pero menos consumidores.       |
| P2        | clients          | ~8               | CRM.                                             |
| P2        | pipeline         | ~6               | CRM / sales.                                     |
| P2        | risks            | ~7               | Project mgmt.                                    |
| P2        | okrs             | ~7               | Strategy.                                        |
| P2        | epics            | ~9               | Agile.                                           |
| P3        | resto (~40+)     | ~50              | Auth, billing, BI, integrations, etc.            |

## Template de migración por endpoint

### Backend (FastAPI)

**Antes:**

```python
@router.get("/foo", response_model=List[FooOut])
def list_foo(page: int = 1, page_size: int = 50, db: Session = Depends(get_db)):
    q = svc.get_foo_query(db)
    items, _, _ = paginate_query(q, page, page_size)
    return items
```

**Después:**

```python
from app.core.responses import APIListResponse

@router.get("/foo", response_model=APIListResponse[FooOut])
def list_foo(page: int = 1, page_size: int = 50, db: Session = Depends(get_db)):
    q = svc.get_foo_query(db)
    items, total, _ = paginate_query(q, page, page_size)
    return APIListResponse.ok(items=items, total=total, page=page, page_size=page_size)
```

Para single-object:

```python
from app.core.responses import APIResponse

@router.get("/foo/{id}", response_model=APIResponse[FooOut])
def get_foo(id: str, db: Session = Depends(get_db)):
    foo = svc.get_foo(db, id)
    if not foo:
        raise HTTPException(404, "Foo no encontrado")
    return APIResponse.ok(data=foo)
```

### Frontend (React Query)

**Antes:**

```js
useQuery({
  queryFn: () => fooApi.list().then(r => r.data),
})
```

**Después (defensive, soporta ambos shapes durante la transición):**

```js
useQuery({
  queryFn: () => fooApi.list().then(r => r.data?.items ?? r.data ?? []),
})
```

**Una vez que TODOS los endpoints están migrados, simplificar a:**

```js
useQuery({
  queryFn: () => fooApi.list().then(r => r.data.items),
})
```

### Tests

**Antes:**

```python
def test_list_foo(client, token):
    res = client.get("/api/v1/foo", headers=auth(token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)
```

**Después:**

```python
def test_list_foo(client, token):
    res = client.get("/api/v1/foo", headers=auth(token))
    assert res.status_code == 200
    payload = res.json()
    assert isinstance(payload, dict)
    assert isinstance(payload["items"], list)
    assert "meta" in payload
```

## Deprecation / versionado

Cuando la mayoría de endpoints estén migrados (estimación: ~70%+):

1. Anunciar deprecation del shape antiguo.
2. Mantener compatibilidad temporal vía header `Accept: application/vnd.contecflow.v2+json`
   o querystring `?wrapped=true` (decisión a discutir).
3. Bump a `/api/v2/` cuando el 100% esté migrado y los consumers internos hayan
   adoptado el nuevo shape.
4. Mantener `/api/v1/` con el shape antiguo durante 1-2 sprints más como red de
   seguridad.

## Checklist por dominio (template)

- [ ] Listar todos los endpoints del dominio
- [ ] Backend: migrar cada `response_model` y `return` al wrapper
- [ ] Frontend: actualizar todos los hooks/queries del dominio
- [ ] Tests backend: actualizar asserts
- [ ] Tests E2E (Playwright): smoke del flujo principal
- [ ] PR aislado por dominio
- [ ] Review + merge

## Notas

- `paginate_query` ya devuelve `(items, total, pages)` — encaja bien con
  `APIListResponse.ok(items, total, page, page_size)`.
- Para endpoints que devuelven shapes especiales como `{deliverables: [...], summary: {...}}`,
  considerar si se mantiene shape específico o se mueve `summary` a `meta` (caso a caso).
- Endpoints de acción (`POST /resolve`, `DELETE`, etc.) que devuelven `{ok: True, message: ...}`
  pueden permanecer así o migrarse a `APIResponse[StatusOut]` — decisión por dominio.
