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

## Scope total estimado

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
