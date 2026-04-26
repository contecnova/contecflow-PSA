# Auditoría Completa — Contecflow PSA
> Fecha: Julio 2025 | Revisión: Archivo a archivo | Áreas: Seguridad · Funcionalidad · Lógica de negocio · Usabilidad

---

## Resumen Ejecutivo

| Severidad | Nº hallazgos |
|-----------|-------------|
| 🔴 CRÍTICO | 3 |
| 🟠 ALTO | 7 |
| 🟡 MEDIO | 12 |
| 🟢 BAJO / MEJORA | 10 |

**Estado general:** El codebase es técnicamente sólido para un producto PSA de nivel empresarial. La arquitectura de seguridad (MFA, JWT rotativo, RBAC/ABAC, rate limiting, SSRF guard, path-traversal guard, CSP, SOC audit) está bien diseñada. Los hallazgos críticos son puntuales y reparables sin refactorización mayor.

---

## 🔴 CRÍTICOS

### C-1 · Test de colección roto — `_is_allowed_redirect_uri` no encontrado
**Archivo:** `tests/test_auth_redirect_uri_validation.py`  
**Problema:** El test importa `_is_allowed_redirect_uri` de `app.api.v1.endpoints.auth`, pero la función vive en `app.api.v1.routers.auth_sso`. El test falla en colección — la protección de Open Redirect **no está siendo testeada** en CI aunque el código de producción sí existe.  
**Impacto:** Vulnerabilidad Open Redirect puede pasar desapercibida en regressions.  
**Acción:**
```python
# tests/test_auth_redirect_uri_validation.py — cambiar import
from app.api.v1.routers.auth_sso import _is_allowed_redirect_uri
```

---

### C-2 · Login de superadmin por contraseña env en `development` — riesgo de configuración
**Archivo:** `app/api/v1/routers/auth_core.py` línea ~91  
**Problema:** Si `ENVIRONMENT=development` y el usuario tiene `is_superadmin=True`, se permite login con `SUPERADMIN_PASSWORD` aunque la contraseña bcrypt no coincida. Si `ENVIRONMENT` se configura mal en staging/producción (error de `.env`), esta puerta trasera queda activa.  
**Impacto:** Bypass completo de autenticación para superadmin.  
**Acción:** Añadir una segunda guardia explícita verificando que la URL/hostname no sea de producción, o exigir `TESTING=0` **y** que `DATABASE_URL` no apunte a la BD de producción. Como mínimo, añadir un validador en `config.py` que rechace `ENVIRONMENT=development` si `DATABASE_URL` contiene el hostname de producción.

---

### C-3 · `joblib.load()` desde bytes de BD — deserialización no verificada
**Archivo:** `app/services/ml_trainer.py` línea ~51  
**Problema:** `joblib.load(io.BytesIO(data))` deserializa bytes almacenados en la tabla `ml_models`. Si un atacante consigue escribir en esa tabla (SQLi, compromiso de BD), puede ejecutar código arbitrario en el servidor vía pickle gadgets.  
**Impacto:** RCE si la BD es comprometida o si hay una ruta de escritura no protegida.  
**Acción:** Firmar criptográficamente los model bytes antes de guardarlos (`hmac.new(secret, model_bytes, 'sha256')`) y verificar la firma antes de `joblib.load`. Alternativamente, usar ONNX o safetensors como formato sin ejecución arbitraria.

---

## 🟠 ALTOS

### A-1 · SQL dinámico sin whitelist completa en `migrate.py`
**Archivo:** `app/db/migrate.py` línea ~191  
```python
conn.execute(text(f"ALTER TABLE {table_safe} ADD COLUMN {column} {definition}"))
```
`table_safe` pasa por `validate_table_name()` (whitelist correcta), pero `column` y `definition` **no se validan**. Son cadenas hardcodeadas en la lista `MIGRATIONS`, por lo que en la práctica no hay SQL injection — pero si alguien añade una entrada maliciosa a `MIGRATIONS` en un PR, la función lo ejecutará sin protección.  
**Acción:** Añadir regex whitelist para `column` (`^[a-z_][a-z0-9_]*$`) y `definition` (`^[A-Z]+(\\([0-9, ]+\\))?( [A-Z]+ [0-9a-z']+)*$`).

---

### A-2 · `enterprise_service.py` — `__import__` inline para evadir importación circular
**Archivo:** `app/services/enterprise_service.py` línea ~240  
```python
max_code = db.query(func.max(__import__('app.models.enterprise', ...).Subcontractor.code)).scalar()
```
Patrón de `__import__` inline — opaco, difícil de auditar, no interceptable por análisis estático de seguridad.  
**Acción:** Resolver la importación circular con una importación local al inicio de la función (`from app.models.enterprise import Subcontractor`). Es la misma solución semántica pero legible y auditable.

---

### A-3 · CORS `allow_methods=["*"]` y `allow_headers=["*"]`
**Archivo:** `app/main.py` líneas 243-244  
**Problema:** Con `allow_credentials=True` + `allow_methods=["*"]` + `allow_headers=["*"]`, cualquier origen en `ALLOWED_ORIGINS` puede hacer PUT/DELETE con cabeceras arbitrarias. En producción debería limitarse a métodos y cabeceras necesarios.  
**Acción:**
```python
allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
```

---

### A-4 · `DEFAULT_USER_PASSWORD` usado en SCIM para usuarios aprovisionados
**Archivo:** `app/services/scim_service.py` líneas 121, 211  
**Problema:** Todos los usuarios creados vía SCIM reciben `DEFAULT_USER_PASSWORD` como contraseña inicial. Si el IdP no fuerza un cambio de contraseña inmediato (password_change_required), estos usuarios quedan con una contraseña predecible conocida por el operador.  
**Acción:** Generar una contraseña aleatoria de un solo uso (`secrets.token_urlsafe(20)`) y marcar `password_change_required=True`, o configurar SSO como único método de login para usuarios SCIM (sin contraseña local).

---

### A-5 · Rate limiter con fallback in-memory en multi-worker — login sin protección real
**Archivo:** `app/services/auth_service.py` líneas 57, 224, 300  
**Problema:** Si Redis no está disponible, el login rate-limit y el lockout caen a un diccionario in-memory por proceso. En un despliegue multi-worker (Gunicorn/Uvicorn con N workers), cada worker tiene su propio diccionario: un atacante puede hacer 5 intentos fallidos × N workers = N×5 intentos sin lockout.  
**Acción:** Loguear `WARNING` claro en producción (ya lo hace — confirmar que sea visible en alertas SOC). Considerar `FAIL_ON_REDIS_UNAVAILABLE=true` para producción para que el servidor no arranque sin Redis.

---

### A-6 · `GanttChart.jsx` — `console.log` de debug en producción
**Archivo:** `frontend/src/components/GanttChart.jsx` línea 150  
**Problema:** Debug log con datos de proyectos (nombres, fechas, estado) visible en consola de producción. Puede filtrar información sensible a usuarios con DevTools.  
**Acción inmediata:**
```javascript
// Eliminar estas líneas (o envolver en: if (import.meta.env.DEV) { ... })
console.log('🔍 GanttChart DEBUG - Projects received:', ...)
```

---

### A-7 · `migrate_to_pg.py` — query dinámica sin escape
**Archivo:** `app/db/migrate_to_pg.py` línea ~62  
```python
rows = src.execute(text(f"SELECT * FROM \"{table_name}\"")).mappings().fetchall()
```
`table_name` viene de `Base.metadata.sorted_tables` (nombres de tabla del ORM), por lo que en la práctica es seguro — pero si alguien añade una tabla con nombre controlable, hay SQLi. Añadir whitelist idéntica a la de `migrate.py`.

---

## 🟡 MEDIOS

### M-1 · `organization_id nullable=True` en modelos críticos
**Archivos:** `app/models/project.py`, `app/models/user.py`, `app/models/cab.py`, `app/models/advanced_config.py`  
**Problema:** `nullable=True` permite registros huérfanos sin tenant. La lógica de `scope_projects_query` sólo filtra si `current_user.organization_id` no es None, dejando potencialmente visibles proyectos sin org para superadmin queries que no filtren.  
**Acción:** Revisar si estos nullables son intencionales (proyectos "globales" de superadmin). Si no, migrar a `nullable=False` con constraint en BD. Añadir tests de `test_tenant_isolation.py` para registros con `organization_id=NULL`.

---

### M-2 · `ai_chat_service_old.py` — archivo legacy sin eliminar
**Archivo:** `app/services/ai_chat_service_old.py`  
**Problema:** Archivo nombrado explícitamente `_old`. Contiene lógica duplicada (`kb_rag_context` aparece en este archivo Y en `app/services/ai_chat/rag_service.py`). Código muerto aumenta la superficie de mantenimiento y puede contener vulnerabilidades que no se han corregido al migrar.  
**Acción:** Eliminar el archivo o moverlo a `archive/`. Asegurarse de que ningún import lo use.

---

### M-3 · APScheduler + Celery Beat corriendo simultáneamente
**Archivo:** `app/main.py` (APScheduler) + `app/worker.py` (Celery beat)  
**Problema:** Ambos sistemas programan las mismas tareas (`scheduled_reports`, `key_rotation`). En producción con Celery activo + workers web, las tareas se ejecutarán dos veces. El APScheduler usa SQLAlchemy jobstore para evitar duplicados, pero depende de que Celery NO esté ejecutando las mismas tareas.  
**Acción:** Documentar claramente en README que `ENABLE_APSCHEDULER=0` debe establecerse cuando Celery beat está activo. Añadir un check en startup que detecte ambos activos y lance `WARNING` visible.

---

### M-4 · Sin Strict-Transport-Security (HSTS)
**Archivo:** `app/main.py` security headers middleware  
**Problema:** Los headers de seguridad incluyen CSP, X-Frame-Options, X-Content-Type-Options, pero falta `Strict-Transport-Security`. En producción HTTPS, sin HSTS un atacante MITM puede downgrade a HTTP.  
**Acción:**
```python
if settings.ENVIRONMENT == "production":
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
```

---

### M-5 · `models/project.py` y `models/user.py` — `ondelete="SET NULL"` sin cascade lógico
**Archivos:** `app/models/project.py` línea 42, `app/models/user.py` línea 65  
**Problema:** Si se elimina una organización, los proyectos y usuarios quedan con `organization_id=NULL`. La aplicación no tiene lógica para tratar estos registros como "eliminados". Pueden aparecer en listados de otros tenants o en consultas globales.  
**Acción:** Cambiar a `ondelete="CASCADE"` o implementar soft-delete a nivel de organización con lógica de archivado.

---

### M-6 · Sentry con `traces_sample_rate=0.1` — puede capturar datos sensibles en traces
**Archivo:** `app/main.py` líneas ~262  
**Problema:** Performance traces con `traces_sample_rate=0.1` pueden capturar query parameters, body de requests, y valores de variables locales que contengan datos PII de usuarios.  
**Acción:** Configurar `send_default_pii=False` (ya es el default, verificar) y añadir `before_send` callback para limpiar cabeceras de autorización y cookies de los eventos.

---

### M-7 · `migrate.py` — sistema de migraciones paralelo a Alembic
**Archivo:** `app/db/migrate.py`  
**Problema:** Existe un sistema propio de `ALTER TABLE` manual además de Alembic. En producción, las migraciones se aplican dos veces: una por Alembic y otra por `migrate.py`. Si divergen, pueden generar columnas duplicadas o conflictos de tipos.  
**Acción:** Deprecar `migrate.py` y migrar todas sus entradas a ficheros Alembic. Añadir en CI un test que verifique que no hay ALTER TABLE pendientes en `migrate.py` que no existan en Alembic.

---

### M-8 · `frontend/src/components/GanttChart.jsx` — placeholder bars sin fechas no clickables
**Archivo:** `frontend/src/components/GanttChart.jsx`  
**Problema de UX:** Proyectos sin fechas muestran un placeholder SVG con "📅 Sin fechas definidas" pero no tienen acción — el usuario no sabe cómo añadir fechas.  
**Acción:** Añadir tooltip o `onClick` que abra el formulario de edición del proyecto con el campo de fechas pre-enfocado.

---

### M-9 · `ProjectRiskBadge` sin `hasData` propagado desde `ProjectsPage`
**Archivo:** `frontend/src/pages/ProjectsPage.jsx`  
**Problema:** `<ProjectRiskBadge projectId={project.id} />` llama a la API aunque el proyecto no tenga tareas, generando requests innecesarios. El componente acepta `hasData` pero no se pasa.  
**Acción:**
```jsx
<ProjectRiskBadge projectId={project.id} hasData={(project.task_count ?? 0) > 0} />
```
(requiere que la API devuelva `task_count` en `ProjectSummary`, lo que ya debería estar disponible vía `team_size` o similar)

---

### M-10 · Password reset no invalida tokens anteriores
**Archivo:** `app/api/v1/routers/auth_core.py` / `app/services/auth_service.py`  
**Problema:** Si un usuario solicita múltiples resets de contraseña, los tokens anteriores siguen siendo válidos hasta su TTL (30 min). Un atacante que intercepte un token antiguo puede usarlo.  
**Acción:** Al emitir un nuevo token de reset, invalidar (o sobrescribir en Redis) los tokens anteriores del mismo usuario. Usar el patrón `setex(key=f"reset:{user_id}", value=new_jti, ttl=1800)` y verificar que el JTI coincide.

---

### M-11 · Sin paginación en algunos endpoints de listado
**Archivos varios:** Algunos endpoints devuelven `.all()` sin límite explícito cuando no se pasan parámetros de paginación.  
**Acción:** Asegurar que todos los endpoints de listado tienen `limit` máximo hardcodeado (ej. `max(min(limit, 500), 1)`). Revisar especialmente `analytics_service.py` y `capacity_service.py`.

---

### M-12 · `ai_modules_service.py` usa `_Exec` como nombre de clase interno
**Archivo:** `app/services/ai_modules_service.py` línea ~556  
**Problema menor de nomenclatura:** `_Exec` como clase record local puede confundirse con un exec dinámico en revisiones de seguridad automáticas.  
**Acción:** Renombrar a `_ExecRecord` o `_ActionRecord` para claridad.

---

## 🟢 MEJORAS / BAJO

### B-1 · Añadir `Referrer-Policy` header
**Archivo:** `app/main.py`  
```python
response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
```

---

### B-2 · `validate_https_discovery_url` — SSRF guard excelente, documentar en README
**Archivo:** `app/services/auth_service.py` líneas ~310-350  
La protección SSRF para OIDC discovery URLs es muy completa (valida IP privadas después de resolución DNS). Merece documentarse como práctica de seguridad del proyecto.

---

### B-3 · Webhook SSRF — verificar que `test_webhook_ssrf.py` cubre rangos IPv6
**Archivo:** `tests/test_webhook_ssrf.py`  
Revisar que los tests incluyen `::1` (loopback IPv6) y `fd00::/8` (ULA privado IPv6) además de rangos IPv4.

---

### B-4 · `ai_chat_service.py` vs `ai_chat/` — estructura duplicada
**Archivos:** `app/services/ai_chat_service.py` y `app/services/ai_chat/`  
Parece haber dos implementaciones del AI chat. Confirmar cuál es la activa y eliminar la otra.

---

### B-5 · `logger.debug(f"JWT decode failed...")` en main.py con f-string
**Archivo:** `app/main.py` línea ~532  
Usar `%s` formatting en lugar de f-string en logs para evitar evaluar la expresión cuando el nivel de log está desactivado:
```python
logger.debug("JWT decode failed in request logging: %s", e)
```

---

### B-6 · `frontend/src/utils/logger.js` — logger centralizado bien implementado
El logger de frontend con niveles controlables por entorno está bien hecho. No expone datos en producción.

---

### B-7 · Celery `max_retries=3` en webhooks — sin dead letter queue
**Archivo:** `app/worker.py` línea ~60  
Tras 3 reintentos, los webhooks fallidos se pierden silenciosamente. Implementar una tabla `webhook_dead_letters` o alertar por Sentry cuando se agotan los reintentos.

---

### B-8 · `app/db/migrate_to_pg.py` — script de migración SQLite→Postgres sin tests
Archivo de migración one-shot sin cobertura de tests. Añadir al menos un smoke test que verifique el conteo de tablas/filas tras la migración.

---

### B-9 · Dependency injection `get_db` — sin timeout configurado
**Archivo:** `app/db/session.py`  
Añadir `pool_timeout` y `connect_args={"connect_timeout": 10}` para evitar que requests lentos de BD bloqueen workers indefinidamente.

---

### B-10 · `frontend/src/pages/` — 100+ páginas JSX sin lazy loading
**Archivo:** `frontend/src/App.jsx`  
Verificar que todas las rutas usan `React.lazy()` + `Suspense`. Un bundle monolítico aumenta el TTI (Time to Interactive) inicial.

---

## Acciones Prioritarias (orden recomendado)

| # | Acción | Severidad | Esfuerzo |
|---|--------|-----------|----------|
| 1 | Corregir import de test `_is_allowed_redirect_uri` | 🔴 C-1 | 5 min |
| 2 | Eliminar `console.log` debug de `GanttChart.jsx` | 🟠 A-6 | 2 min |
| 3 | Firmar model bytes ML antes de `joblib.load` | 🔴 C-3 | 2h |
| 4 | Añadir HSTS header en producción | 🟡 M-4 | 15 min |
| 5 | Añadir `Referrer-Policy` header | 🟢 B-1 | 5 min |
| 6 | Añadir whitelist para `column`/`definition` en `migrate.py` | 🟠 A-1 | 30 min |
| 7 | Restringir CORS `allow_methods` y `allow_headers` | 🟠 A-3 | 10 min |
| 8 | Invalidar tokens de reset anteriores | 🟡 M-10 | 1h |
| 9 | Fix SCIM users con password aleatoria | 🟠 A-4 | 1h |
| 10 | Resolver `__import__` inline en `enterprise_service.py` | 🟠 A-2 | 10 min |
| 11 | Documentar ENABLE_APSCHEDULER=0 con Celery | 🟡 M-3 | 30 min |
| 12 | Eliminar `ai_chat_service_old.py` | 🟡 M-2 | 15 min |

---

## Hallazgos Positivos (puntos fuertes)

- ✅ **Autenticación MFA completa**: TOTP + WebAuthn/Passkeys con challenge tokens de un solo uso
- ✅ **JWT rotativo**: refresh token rotation con JTI por usuario
- ✅ **Rate limiting en login**: 5/min con lockout exponencial, integrado con SOC
- ✅ **SSRF guard en OIDC**: validación completa de IPs privadas post-DNS para discovery URLs
- ✅ **Path traversal guard en uploads**: `resolve()` + comprobación de prefijo en `s3_service.py`
- ✅ **MIME type whitelist en documentos**: lista explícita de tipos permitidos
- ✅ **CSP en producción**: policy estricta para el bundle Vite
- ✅ **Multi-tenancy**: `organization_id` en todos los modelos relevantes con filtrado automático
- ✅ **ABAC**: sistema de atributos + 9 archivos de tests de acceso
- ✅ **Audit log**: `audit_log()` llamado en operaciones críticas
- ✅ **Session tracking**: `UserSession` con JTI para revocación de sesiones
- ✅ **Token de cookies httpOnly**: sin tokens en localStorage (XSS-safe)
- ✅ **Singleton refresh promise en frontend**: evita race conditions en token rotation
- ✅ **1.302 tests** cubriendo 113 módulos
- ✅ **Key rotation Celery**: rotación automática de material JWT
- ✅ **Validación de contraseñas**: política configurable (longitud, mayúsculas, especiales)
- ✅ **Sentry + SQLAlchemy integration**: trazabilidad de errores en producción
- ✅ **ExceptionHandlerMiddleware**: nunca expone stack traces al cliente

---

*Generado automáticamente por auditoría de código — Contecflow PSA — Julio 2025*
