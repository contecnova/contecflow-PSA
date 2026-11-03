# Contecflow PSA - Documentación

## 1. Qué es Contecflow PSA
Plataforma para gestión integral de servicios profesionales:
- Proyectos, tareas, sprints y planificación
- Tiempo, capacidad, recursos y ausencias
- Facturación, gastos, revenue y rentabilidad
- CRM, clientes, contratos y portal cliente
- Service Desk ITSM (tickets, SLA, KB, CMDB, cambios, problemas)
- BI y analítica avanzada
- IA aplicada y gobierno de IA
- Seguridad enterprise (RBAC, ABAC, GRC, SCIM)

## 2. Arquitectura
### Backend
- FastAPI
- SQLAlchemy + Alembic
- Celery + Redis para jobs y scheduler
- Pydantic Settings para configuración
- SQLite local / PostgreSQL productivo

Rutas principales:
- API v1: `/api/v1`
- API v2: `/api/v2` (superficie parcial de compatibilidad)

Entradas clave:
- `app/main.py`
- `app/worker.py`
- `app/core/config.py`
- `app/db/session.py`
- `app/api/v1/endpoints/`
- `app/services/`

### Frontend
- React + Vite
- TanStack Query + Axios
- React Router
- Componentes por dominio

Entradas clave:
- `frontend/src/main.jsx`
- `frontend/src/App.jsx`
- `frontend/src/services/api.js`
- `frontend/src/pages/`
- `frontend/src/components/`

## 3. Estructura del repositorio
- `app/`: backend
- `alembic/`: migraciones de base de datos
- `frontend/`: SPA web
- `tests/`: suite de tests backend
- `tests_e2e/`: pruebas end-to-end
- `scripts/`: utilidades operativas
- `reports/`: reportes técnicos activos
- `uploads/`: almacenamiento temporal local

## 4. Requisitos
- Python 3.12
- Node.js 20+
- npm
- Redis

Opcional:
- PostgreSQL para entorno similar a producción

## 5. Instalación
### Backend
1. Crear entorno virtual: `python -m venv venv`
2. Activar entorno:
   - macOS/Linux: `source venv/bin/activate`
   - Windows: `venv\Scripts\activate`
3. Instalar dependencias: `pip install -r requirements.txt`

### Frontend
1. `cd frontend`
2. `npm install`

## 6. Configuración
### Backend
Crear `.env` desde `.env.example`.
Variables críticas:
- `DATABASE_URL`
- `SECRET_KEY`
- `REDIS_URL`
- `CORS_ORIGINS`
- claves de proveedores IA si aplica

### Frontend
Crear `frontend/.env` desde `frontend/.env.example`.

## 7. Arranque local
### Modos de `setup.sh` / `setup.bat`
- `./setup.sh demo` — carga seed y arranca.
- `./setup.sh clean` — limpia datos y deja solo admin, luego arranca. El reset crea automáticamente una organización base y asigna el usuario admin a esa organización para cumplir la restricción multi-tenant actual.
- `./setup.sh start` — solo arranca y preserva la base de datos existente.
- `./setup.sh admin-only-start` — BD limpia conservando solo el usuario `admin` (credenciales de `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD`).
- `setup.bat` soporta `demo`, `clean`, `start demo`, `start clean` y la variable `SETUP_INIT_MODE=demo|clean` antes de `setup.bat start` para modo no interactivo.

### Opción manual
1. API backend: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
2. Worker Celery: `celery -A app.worker.celery_app worker --loglevel=info`
3. Beat Celery: `celery -A app.worker.celery_app beat --loglevel=info`
4. Frontend (en `frontend/`): `npm run dev`

### Paridad de autenticación y despliegue
- El login ahora soporta MFA por TOTP y passkeys, con un flujo de UI coherente con el patrón de Contecmind.
- El flujo incluye carga de proveedores SSO, redirección al proveedor y manejo del challenge MFA antes de completar la sesión.
- El stack de Docker local quedó versionado en `deploy/docker-compose.yml` con PostgreSQL, Redis, backend, worker y frontend para despliegues reproducibles.

## 8. Base de datos

### Migraciones: Alembic es la ÚNICA fuente de verdad

```bash
alembic upgrade head          # aplica lo pendiente (idempotente)
alembic revision -m "…"       # nueva revisión
alembic heads                 # debe devolver UNA sola cabeza
```

Auditoría 2026-08 (hallazgo 11). Antes había **dos** caminos para construir el
esquema y sólo uno estaba completo:

| Caso | Camino anterior | Problema |
|---|---|---|
| BD nueva | `Base.metadata.create_all()` + `alembic stamp head` | `stamp` marca las revisiones aplicadas **sin ejecutarlas** |
| BD existente | `alembic upgrade head` | Es el único que ejercitaba la cadena |

Consecuencia: la cadena de revisiones **no se ejecutó nunca de principio a fin**.
Al probarla sobre una base vacía producía 374 tablas frente a las 392 de los
modelos — faltaban 19, entre ellas `expenses`, `email_templates`,
`automation_rules`, `revenue_recognition_entries`, `gdpr_requests` y
`webhook_triggers`. Un despliegue que hubiera pasado por Alembic se quedaba sin
esas funcionalidades. Se cerró con la revisión `089_schema_gap_missing_tables`.

Reglas que se derivan de eso:

- **Nunca** `create_all` en el arranque ni en el despliegue. Cada modelo nuevo
  necesita su revisión. `app/db/migrate.py` ya no se usa en ningún flujo.
- `tests/test_alembic_schema_parity.py` levanta una base vacía, corre
  `upgrade head` de verdad y compara con los modelos. Es el test que faltaba.
- Una sola cabeza de migración. Dos significan ramas divergentes sin fusionar y
  `upgrade head` fallaría.

### Seed
- `python scripts/seed_full_data.py`
- Los usuarios por defecto viven en `app/db/seed_parts/core.py::default_seed_users()`,
  extraída para poder verificar sus propiedades de seguridad sin ejecutar el seed
  (ver `tests/test_seed_fixture_parity.py`).

Notas:
- SQLite local genera `.db-wal` y `.db-shm` durante ejecución.
- No versionar artefactos de BD local.

## 8bis. Stack Docker

Un único `docker-compose.yml` en la raíz, con la misma estrategia que contecmind
y contecweb. Los dos escenarios se distinguen con perfiles, no con ficheros
duplicados:

```bash
./setup.sh                              # crea .env, volúmenes y levanta la infra
docker compose up -d                    # DESARROLLO: postgres + redis.
                                        # La app corre en local (uvicorn) y
                                        # guarda los ficheros en uploads/.
docker compose --profile s3 up -d       # + el almacén S3 (versitygw), para
                                        # probar el camino de S3 en local
docker compose --profile app up -d      # PRODUCCIÓN: + s3, migrate, api,
                                        # worker, beat y web (nginx)
docker compose --profile observability up -d   # + prometheus y exporters
docker compose down                     # apaga, conserva los datos
docker compose down -v                  # borra SÓLO los volúmenes regenerables
```

### Decisiones de diseño, y por qué

**Puertos siempre en `127.0.0.1`.** Con `"5434:5432"` Docker publica en 0.0.0.0.
Este fichero se copia para demos y preproducciones, y ahí eso significa un
Postgres, un Redis sin contraseña y un almacén S3 accesibles desde toda la red con
credenciales de desarrollo.

**Variables críticas con `${VAR:?}`.** Un valor por defecto silencioso en una
credencial es levantar el stack con credenciales conocidas sin enterarse. Con
`:?` el `up` aborta con un mensaje claro. `setup.sh` las rellena y genera los
secretos una vez, así que en desarrollo no hay fricción.

**Volúmenes de datos `external: true`.** Un `docker compose down -v` no puede
borrarlos. Es la lección de un incidente en contecmind, donde un `down -v`
recreó los volúmenes y se perdieron los metadatos y el índice de golpe. El coste
es que compose ya no los crea, así que `setup.sh::ensure_persistent_volumes` los
crea de forma idempotente.

**Imágenes con versión fija, algunas por digest.** Con un tag móvil dos
despliegues del mismo commit pueden levantar imágenes distintas y un fallo deja
de ser reproducible.

**`beat` es un servicio aparte.** Antes iba como `worker --beat` en el mismo
contenedor: con más de una réplica del worker, varios planificadores disparaban
la misma tarea periódica — informes y correos duplicados. Beat debe ser
singleton.

**Las migraciones son un servicio del que depende la API**
(`service_completed_successfully`), así que la aplicación no arranca con un
esquema a medias.

**La API no publica puerto al host.** Quien entra es nginx; publicarla saltaría
las cabeceras de seguridad y el tope de tamaño de cuerpo.

**Un almacén S3 en el stack.** `S3Service` no tenía `endpoint_url` configurable,
así que el backend de objetos nunca se ejercitaba fuera de AWS y los documentos
caían siempre al sistema de ficheros local. Con `AWS_S3_ENDPOINT_URL` el mismo
código sirve contra el almacén local y contra AWS (o cualquier S3 compatible) en
producción.

**El almacén es versitygw, no MinIO, y va bajo perfil (27-09-2026).** MinIO
cerró su distribución pública en dos pasos: Docker Hub el 17-09 y quay.io el
27-09, que contesta «Requires authentication» hasta para `:latest`. Con MinIO en
el `up` por defecto, eso tumbaba el arranque entero, y `setup.sh`, al ver fallar
el `up`, caía a SQLite sin decir por qué. Dos cambios:

- **El servidor es versitygw** (Versity S3 Gateway, Apache-2.0, de `ghcr.io`), el
  mismo que usan contecmind y contecweb. Con su backend `posix` cada objeto es un
  fichero normal del volumen y cada bucket una carpeta: el bucket se crea con un
  `mkdir` al arrancar y el servicio `minio-init` ya no existe.
- **Va bajo los perfiles `s3` y `app`.** En desarrollo la app no lo usa, así que
  no puede tumbar lo que sí se usa. Con `--profile app` arranca solo, porque ahí
  la API y el worker guardan los documentos en él.

Las variables siguen llamándose `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`,
`MINIO_BUCKET` y `MINIO_PORT`, para no romper ningún `.env` existente. El puerto
por defecto pasa de `127.0.0.1:9000` a **`127.0.0.1:9003`**: en esta máquina
conviven los productos de la casa y contecweb publica el 9000 (contecmind, el
9002). La consola web de MinIO (9001) desaparece: versitygw no tiene.

**Pasar datos de un MinIO antiguo.** El volumen nuevo es `contecflow_s3_data`, y
no se reutiliza `contecflow_minio_data`, porque MinIO guarda los objetos en su
formato (`xl.meta` y partes), no como ficheros. versitygw montado encima no
fallaría: serviría eso como si fueran objetos. Si un despliegue tiene documentos
en MinIO, se copian de servidor a servidor mientras el antiguo sigue levantado
(la imagen en caché de esa máquina aún arranca):

```bash
docker compose --profile s3 up -d s3
aws() { docker run --rm --network host -v "$PWD/copia-s3:/copia" \
  -e AWS_ACCESS_KEY_ID="$1" -e AWS_SECRET_ACCESS_KEY="$2" \
  public.ecr.aws/aws-cli/aws-cli "${@:3}"; }
# 1) del MinIO antiguo (9000) a un directorio del host
aws <usuario-minio> <secreto-minio> s3 sync s3://contecflow-documents /copia \
  --endpoint-url http://127.0.0.1:9000
# 2) del directorio al almacén nuevo (9003)
aws "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" s3 sync /copia s3://contecflow-documents \
  --endpoint-url http://127.0.0.1:9003
```

La copia va por la API de S3, no por el volumen: es lo único que lee bien los
dos formatos.

**Tres fallos de cliente que MinIO tapaba.** MinIO era permisivo; versitygw, como
AWS, no lo es. Al probar el camino completo (subir, firmar la URL y descargarla)
salieron tres, arreglados y con prueba en `tests/test_s3_clientes_firman_en_v4.py`:

1. **`S3Service` presignaba con la firma v2** (`AWSAccessKeyId=…&Signature=…`).
   boto3 solo usa la v4 en las URLs firmadas si se le pide; como las peticiones
   normales sí iban en v4, subir funcionaba y descargar daba un 400 («Please use
   AWS4-HMAC-SHA256»). AWS también rechaza la v2 en regiones y buckets nuevos.
2. **El almacén de colaboración** (`COLLAB_S3_*`), lo mismo, y además sin
   direccionamiento por ruta, que es lo único que entiende un servidor de un solo
   host.
3. **eSign leía el documento con un `boto3.client("s3")` sin configurar**: sin
   endpoint ni credenciales, preguntaba a AWS, fallaba y caía al disco, donde el
   documento no estaba. Firmar un documento guardado en S3 fallaba siempre fuera
   de AWS. Ahora usa el cliente de `S3Service`.

Y una de servidor: **versitygw comprueba la región de la firma** («the region
"eu-west-1" is wrong; expecting "us-east-1"»), como AWS. El compose le da la
misma variable que usa la app, `AWS_REGION` (defecto `eu-west-1`), para que no
puedan divergir.

**Sin métricas del almacén en Prometheus.** El job `minio` rascaba
`/minio/v2/metrics/cluster`. versitygw no expone métricas en ese formato, y un
objetivo que no contesta nunca es una alarma que se aprende a ignorar, así que se
quitó. La salud del almacén la vigila el healthcheck del compose (`/health`).

### nginx

`frontend/nginx.frontend.conf` sirve el frontend **y** hace de proxy inverso a
la API. Antes servía sólo estáticos, sin ninguna directiva `proxy_pass`: el
navegador cargaba la aplicación y ninguna llamada llegaba a destino — el
despliegue no podía funcionar.

Que la API salga por el mismo origen elimina CORS, permite cookies httpOnly sin
`SameSite=None`, y encaja con la comprobación de Origin del middleware CSRF.
Incluye negociación de WebSocket (sin ella el chat queda en reconexión perpetua),
`client_max_body_size`, y propagación de `X-Forwarded-For` — sin la cual el rate
limiting por IP contaría todas las peticiones como procedentes de nginx.

`tests/test_docker_stack.py` fija estas invariantes. **Aviso honesto:** valida la
definición del stack, no que levante. Un `docker compose --profile app up` en un
host con Docker sigue siendo imprescindible antes de publicar.

## 9. Módulos funcionales
### 9.1 Proyectos y delivery
- Proyectos, fases, miembros
- Tareas, dependencias, kanban
- Epics, sprints, planificación
- Baselines y métricas de seguimiento
- Plantillas: la administración queda centralizada en `/project-templates` (creación completa desde cero incluyendo fases, tareas, riesgos y entregables; instanciación de proyectos desde plantilla).
- Workflows por proyecto: estados de workflow propios si existen; si no, estados base por defecto. `DELETE /api/v1/project-workflows/{project_id}/reset` restablece a Scrum estándar.
- Issue Types: ruta canónica `/api/v1/issue-types/{project_id}` (incluyendo `/init`).
- State machine de tareas: `cancelled` es terminal (no se puede salir); `todo → in_review` es inválida (requiere pasar por `in_progress` primero). El grafo completo está en `_TASK_VALID_TRANSITIONS` (`task_service.py`).

### 9.2 Tiempo y recursos
- Imputaciones y timer
- Timesheets y aprobaciones
- Capacity planning y scheduler
- Ausencias, skills, carga y burnout

Reglas funcionales:
- Cronómetro: permite cancelar la sesión sin guardar, cambiar la tarea final antes de imputar y forzar una imputación duplicada cuando ya existe otra para la misma tarea y fecha. Si se fuerza, se genera notificación in-app al manager responsable.
- Unicidad usuario+tarea+fecha se controla desde la lógica de negocio (no índice SQL), permitiendo únicamente los duplicados forzados desde el cronómetro.
- Las imputaciones duplicadas forzadas nunca sustituyen la anterior: se almacenan como registros adicionales y sus horas se acumulan en los totales semanales.
- `POST /api/v1/imputations/{imputation_id}/reject` permite a managers rechazar una imputación forzada sin borrar histórico (además de `approve`).
- `sync_timesheet_from_imputations_flow` siempre actualiza `total_hours`, `billable_hours` y `total_cost` independientemente del estado. Cuando un timesheet `approved` recibe nuevas imputaciones no aprobadas, vuelve automáticamente a `draft`.
- Mutaciones de imputaciones (crear, cerrar cronómetro, editar, borrar) sincronizan inmediatamente el timesheet semanal y, si estaba aprobado y cambia, invalidan la aprobación.
- Listado y lectura de imputaciones cargan `user`, `task` y `project` con `joinedload` para evitar N+1.
- Frontend del cronómetro **no** decide elegibilidad por `user.hourly_rate` del contexto de sesión (`/auth/me` usa `UserPublic` y no transporta tarifa). La validación efectiva de tarifa vive en backend al iniciar/detener.
- El timer activo devuelve y renderiza `project_name` y `task_name`; los UUID solo como fallback si faltan.
- El reloj superior y el widget compacto comparten la query global `timer-current`; cualquier `start/pause/resume/stop` actualiza esa cache para mantener consistencia entre TimerPage, widget y topbar.
- Ante `409` al detener cronómetro por imputación duplicada, la UI requiere consentimiento explícito (check en modal). No hay reintento forzado automático.
- TimerPage filtra el selector de tarea por `assigned_to_me: true`, igual que el formulario de inicio y que ImputarPage.
- En `/imputar`, los valores diarios y total semanal se formatean con máximo 2 decimales.
- La marca de facturable es editable al crear y al editar; las filas muestran badge cuando son facturables.

### 9.3 Finanzas
- Facturas y líneas
- Gastos
- Revenue recognition
- Rentabilidad
- Tipos de cambio

Endpoints relevantes:
- `POST /api/v1/invoices` crea facturas manualmente con líneas, `tax_rate` y datos del cliente. Calcula `subtotal`, `tax_amount` y `total`; genera número secuencial anual `INV-YYYY-NNN`.
- `GET /api/v1/invoices/{id}/pdf` devuelve PDF válido (ReportLab) con cabecera `%PDF`, `content-type: application/pdf` y `content-disposition: attachment; filename=factura_NNN.pdf`. Empleados y subcontratistas reciben 403.

### 9.4 CRM y clientes
- Clientes y contactos
- Pipeline comercial
- Contratos
- Portal cliente

### 9.5 Service Desk ITSM
Manual completo, de uso y de operación: [docs/SERVICE_DESK.md](docs/SERVICE_DESK.md).
- Tickets con avisos en cada paso (campana, correo y webhooks) y SLA con
  calendario por política, aviso de riesgo e incumplimiento, y escalado
- Correo entrante con hilo (IMAP, Microsoft 365 o pasarela), SMS firmado
- Catálogo con aprobación; tiempo de ticket a partes y factura
- Cambios con CAB, calendario, congelaciones y versiones
- Alertas de monitorización a incidencias y guardias
- Base de conocimiento con revisión, desvío en el portal y documentos de contecmind
- Problemas y KEDB, CMDB y topología, página de estado por organización

### 9.6 BI
- Dashboards
- Query builder
- Forecasting
- Anomalías
- ETL connectors
- Colaboración en dashboards

Reglas:
- El panel "Mi Trabajo" muestra métricas personales del usuario autenticado; no reutiliza KPIs globales de dirección para tareas, ausencias, gastos o aprobaciones.
- Las métricas de tendencia de horas devuelven datos tanto en SQLite local como en PostgreSQL.
- La variación mensual de horas suaviza el porcentaje cuando el mes base es demasiado pequeño.

### 9.7 IA
- NexusAssist
- Motor semántico
- Gobierno de IA
- Proveedores IA multi-tenant

## 10. Configuración por organización (org-defaults)
Valores por defecto centralizados en `app/core/config.py` (sobrescribibles por variables de entorno):
- `DEFAULT_CURRENCY = "EUR"`
- `DEFAULT_TIMEZONE = "Europe/Madrid"`
- `DEFAULT_LANGUAGE = "es"`
- `DEFAULT_WORKING_HOURS_PER_DAY = 8.0`
- `DEFAULT_WEEKLY_CAPACITY_HOURS = 40.0`
- `DEFAULT_VACATION_DAYS_PER_YEAR = 23`
- `DEFAULT_TAX_RATE = 21.0`

Endpoint backend: `GET /api/v1/settings/org-defaults` devuelve los valores actuales de la organización para consumo del frontend.

Hook frontend: `useOrgSettings` (`frontend/src/hooks/useOrgSettings.js`) — TanStack Query con `staleTime` de 5min y fallback a defaults.

## 11. Estándares UI
Guía de diseño completa —tokens, temas con su contraste medido, componentes,
patrones, idiomas, accesibilidad y lo que no se debe copiar—, pensada también
para las otras soluciones: [docs/GUIA_DE_DISENO.md](docs/GUIA_DE_DISENO.md).

### Apariencia y accesibilidad (para quien usa la aplicación)
Se cambia en **Perfil → Apariencia**:
- **Tema:** Freight Pro (por defecto), Oscuro clásico, Midnight, Slate, Claro,
  Alto contraste o Sistema (sigue al sistema operativo). Todos se leen bien:
  el texto cumple el contraste mínimo de accesibilidad (WCAG AA) en los seis.
- **Color de acento:** el de los botones principales y lo seleccionado. El
  texto de encima se pone blanco o negro solo, el que se lea mejor con el
  color elegido.
- **Densidad:** *Compacta* reduce un punto la letra y el margen de la página
  para ver más a la vez; *Confortable* los aumenta para leer mejor.

Con el teclado: `Tab` recorre la pantalla y un contorno del color de acento
marca dónde se está (con el ratón no aparece). En una fila de pestañas, las
flechas cambian de pestaña, e `Inicio` y `Fin` van a la primera y la última.
Los avisos que salen abajo a la derecha los lee también el lector de
pantalla; los errores, en cuanto aparecen.

Las fechas salen en el idioma de la interfaz: `02/11/2026` en español,
`11/02/2026` en inglés y `2026/11/02` en chino. Quedan pantallas que todavía
las escriben en formato español (véase la guía de diseño, apartado 15).

### Modales y drawers
- Contenedor `position: fixed` (drawer: `top: 12, right: 12`; modal centrado: `inset: 0`).
- Altura por contenido; si excede el viewport, el cuerpo interno scrollea con `flex: 1; overflow-y: auto`. Cabecera y footer permanecen visibles (`flex-shrink: 0`).
- Ningún ancestro (`.page-content`, `PageShell`, etc.) debe aplicar `transform`, `filter`, `perspective` o `will-change` persistentes — rompen `position: fixed` al crear containing block. La animación `fadeUp` en `.page-content` se aplica sin `forwards`.
- Backdrop `position: fixed; inset: 0` con click-outside para cerrar.
- Margen exterior: 12 px (drawer) o `padding: 40px 24px` en el wrapper (modal centrado).

### Panel lateral de tareas
- Mantener padding vertical estándar para evitar recorte visual del contenido en la parte superior.

### Inbox
- El contador de la pestaña "Notificaciones" usa la misma fuente que la lista (`/enterprise/notifications` `unread_count`) para evitar desajustes entre badge y contenido.

### Filtros con pills
- En pantallas con filtros rápidos por URL (ej. `tasks?mine=1&overdue=1&status=open`), mostrar pills visibles con acción de quitar individual y botón de limpieza rápida.
- Listados con filtros (Timesheets, etc.) muestran contador `filtrado/total`, botón `Limpiar` y estado vacío "Sin resultados".

### Exportar a Excel global
- `PageHeader` exporta cualquier tabla HTML, grid tabular o lista de cards visible mediante el botón "📊 Exportar Excel" (formato `.xls`).
- Pantallas con lista exportable real: usar `exportTargetSelector` + `data-export-table="<nombre>"` para selección determinista (Tasks, Projects, Invoices, Approvals, Service Desk, etc.).
- Pantallas sin lista exportable real (dashboards, Gantt/Kanban, herramientas, formularios, settings, integraciones): `showListExport={false}`.
- Fallback para listas tipo tarjetas: cada card como fila en columna "Detalle".
- Estado vacío con cabeceras visibles produce `.xls` con cabeceras solas.

## 12. Seguridad y compliance

### Las cuatro capas de autorización

Para saber si un endpoint está protegido hay que mirar las cuatro. Están
ordenadas de la más difícil de olvidar a la más discrecional:

| Capa | Qué protege | Fallo | Se puede olvidar |
|---|---|---|---|
| Aislamiento de tenant | Que un cliente no vea datos de otro | **cerrado** | No: es automático |
| RBAC | Qué puede hacer cada rol | cerrado | Sí: hay que escribirlo |
| Matriz GRC | Restricciones que configura el cliente | abierto (aditivo) | No: es automático |
| ABAC | Política de grano fino opcional | abierto | No: es automático |

**1. Aislamiento entre tenants** — `app/db/session.py::TenantSession`.
Filtra toda consulta ORM por organización, en `query()` (SA 1.x) y en `execute()`
(SA 2.0). Cubre 390 de 391 modelos. Es **fail-closed**: si un modelo no se puede
aislar, la consulta lanza `TenantIsolationError` en lugar de ejecutarse sin
filtro. La única exención (`Organization`, que ES el tenant) se declara en el
propio modelo con `_tenant_exempt = True` y sus rutas llevan guarda manual.

**2. RBAC** — `app/core/deps.py`. `require_admin`, `require_any_manager`,
`require_superadmin`… en la firma del endpoint, o comprobaciones de rol dentro
del servicio. Las dos formas se usan; `tests/test_abac_coverage.py` mantiene el
inventario de las rutas que sólo la tienen en el servicio.

Ojo con la distinción que causó el incidente P0-1 de la auditoría 2026-08:
`require_admin` es el administrador **de un cliente**, no de la plataforma. Todo
lo que opere entre organizaciones necesita `require_superadmin`.

**3. Matriz de permisos GRC** — `app/core/grc_enforce.py`.
Lo que un administrador prohíbe en la pantalla de GRC queda prohibido. Es
**denegación aditiva**: una fila sólo puede quitar permiso, nunca darlo, así que
no puede escalar privilegios por encima del RBAC. Sin fila, deciden las demás
capas.

Módulo y acción se **derivan de la ruta** (`app/core/grc_catalog.py`): el módulo
del primer segmento del path, la acción del método HTTP matizado por el path para
distinguir `aprobar` y `exportar`. No hay lista que mantener — un dominio nuevo
entra en la matriz el día que se añade su primera ruta. Cobertura: los 109
dominios no exentos de la API.

**4. ABAC** — `app/core/abac_dependency.py` y `abac_enforce.py`.
Política de grano fino que un cliente activa si quiere. Es **fail-open**: sin
políticas activas no restringe nada, y por diseño. `enforce_abac()` NO es un
control de autorización por sí solo, aunque el nombre lo sugiera.

### Qué NO protege qué

Errores que la auditoría 2026-08 encontró y que conviene no repetir:

- `enforce_abac()` no aísla tenants. Es fail-open. Un endpoint cuyo único control
  fuera esa llamada estaría sin proteger.
- La matriz GRC no concede permisos, sólo los quita.
- Un middleware de Starlette no puede leer el usuario autenticado: las
  dependencias de FastAPI se resuelven después. `ABACMiddleware` se borró por eso
  — comprobaba un `request.state.user` que nadie poblaba nunca.

### Otras capacidades activas
- JWT, refresh y MFA (TOTP + WebAuthn), forzado también en SSO
- SSO OIDC con verificación de firma contra JWKS, PKCE S256, `state` con HMAC de
  un solo uso y verificación de `nonce`
- Rate limiting: 116 endpoints con límite explícito, bloqueo por intentos en
  login, Redis obligatorio en producción
- CSRF en dos capas: Origin/Referer siempre + double-submit opcional
- Cifrado de secretos de integraciones
- Validación de subidas unificada: extensión, MIME, bytes mágicos y coherencia
  entre ellos, con lectura acotada por perfil (`app/core/uploads.py`)
- Auditoría de eventos y SCIM

Puntos de entrada:
- `app/core/security.py` — tokens, hashing, política de contraseñas
- `app/core/deps.py` — RBAC (incluido `require_superadmin`)
- `app/core/tenancy.py` — guardas para un `org_id` que llega del cliente
- `app/db/session.py` — aislamiento automático de tenant
- `app/core/grc_enforce.py` / `grc_catalog.py` — matriz GRC
- `app/core/abac_dependency.py` / `abac_enforce.py` — ABAC
- `app/core/uploads.py` — seguridad de subidas
- `app/api/v1/endpoints/grc.py` — API de GRC y SoD

### Segregación de Funciones (SoD)
La regla nuclear se aplica en `app/services/approval_engine/requests.py`: el
solicitante no puede aprobar su propia solicitud (403). Está escrita en el código,
no sale de la tabla `SodRule`.

Limitación conocida: las reglas SoD que crea un administrador sólo se consultan
con el patrón `crear`/`aprobar` sobre la misma entidad, y sólo para registrar la
violación. Una regla entre módulos distintos ("no puede crear facturas y aprobar
gastos") todavía no se evalúa. Ver `tests/test_grc_coverage.py`.

### Rotación de claves
- `scripts/rotate_keys.sh`

### Verificación local
Este proyecto no usa CI/CD por decisión de diseño. Todos los gates están
reunidos en `scripts/ci_local.sh`:

```bash
./scripts/ci_local.sh          # todo
./scripts/ci_local.sh --fast   # sin pytest ni informativos (~2 min)
./scripts/ci_local.sh --info   # sólo los informativos
```

Distingue gates **bloqueantes** (verdes hoy; si uno falla es una regresión que
acabas de introducir) de **informativos** (deuda medida y documentada). El
`--max-warnings` de eslint está fijado en la línea base medida: al reducir deuda,
bajar ese número; nunca subirlo.

## 13. Testing
### Backend
- pytest con fixtures comunes en `tests/conftest.py`
- `pytest -q`
- `pytest -q tests/test_auth.py`

### Frontend
En `frontend/`:
- `npm run test`
- `npm run build`

### E2E
- `tests_e2e/`
- `scripts/run-ui-tests-linux-mac.sh`

Notas:
- La ruta `/approvals` tiene smoke E2E dedicado para validar CRUD real de workflows y pasos desde la UI autenticada, con limpieza del dato de prueba al final.
- La suite `tests_e2e/` depende de `playwright` y `pytest-playwright` en Python; tras instalar dependencias puede requerir `playwright install chromium`.

## 14. Operación
### Observabilidad
- Logs de aplicación
- Sentry y OpenTelemetry si están habilitados

### Jobs periódicos
Definidos en `app/worker.py`:
- Jobs de alertas
- Informes programados
- Jobs BI/ETL
- Jobs IA
- Jobs de service desk

Notas:
- El cierre de APScheduler en el shutdown de la API es idempotente: solo intenta shutdown si el scheduler sigue en estado `running`.

## 15. Integraciones
Integraciones soportadas según configuración:
- Jira
- Microsoft 365
- GitHub / GitLab
- Salesforce
- Stripe
- Twilio
- AWS S3/KMS

### E-firma (DocuSign y Adobe Sign)
Configuración accesible desde Settings → Sistema → E-firma (rol admin).

Backend:
- `GET /esign/config` y `PATCH /esign/config` persisten credenciales en `app_settings` (KV store, claves `esign.*`). Sin migración nueva.
- Secretos (`docusign_secret_key`, `adobe_sign_client_secret`) se enmascaran como `"***"` en GET; PATCH ignora el valor `"***"` para no sobreescribir.
- `GET /esign/summary/stats` consulta primero claves DB y hace fallback a env vars.

Frontend:
- `esignApi.getConfig` / `saveConfig` (`frontend/src/services/api.js`).
- `ESignSettingsSection`: tarjeta por proveedor con badge configurado/no configurado, campos secretos tipo password y botón Guardar.

### Documentos
- `HEAD /api/v1/documents/file/{file_key}` en almacenamiento local devuelve metadatos (`Content-Type`, `Content-Length`, `Content-Disposition`) sin descargar el fichero, evitando warnings `405` en comprobaciones previas del navegador.

## 16. Troubleshooting rápido
### Backend no arranca
- Verificar entorno virtual activo
- Verificar dependencias instaladas
- Verificar `DATABASE_URL`

### Migraciones fallan
- `alembic current`
- `alembic upgrade head`
- Revisar tabla `alembic_version`

### Worker falla
- Verificar `REDIS_URL`
- Verificar Redis activo
- Revisar logs worker/beat

### Frontend build falla
- `npm install`
- Revisar `frontend/.env`
- `npm run build`

### Seed falla
- Ejecutar migraciones primero
- Revisar traceback de `scripts/seed_full_data.py`

## 17. Política de limpieza del repositorio
No versionar:
- venv y entornos locales
- node_modules y dist
- caches
- archivos temporales de SQLite
- reportes temporales generados localmente
- archivos del sistema operativo

Controlado por `.gitignore`.

## 18. Mantenimiento de esta documentación
Reglas:
- `DOCS.md` refleja el estado actual.
- Evitar históricos largos de cambios internos.
- Evitar referencias a documentos retirados.
- Consolidar periódicamente para mantener claridad.

## 19. Motor de flujos de aprobación documental
### Descripción
Los documentos que requieren aprobación (`requires_approval=True`) se gestionan a través del motor multi-nivel (`approval_engine`). La misma arquitectura rige timesheets, gastos, facturas, compras y documentos.

### Cómo funciona
1. Al crear un documento con `requires_approval=True`, el sistema busca automáticamente el mejor flujo para esa categoría.
2. Búsqueda: primero flujo con `trigger_conditions={"category":"<cat>"}`, luego genérico `entity_type=document` + `is_default=True`.
3. Si encuentra flujo, crea un `ApprovalRequest` y notifica al primer aprobador.
4. Si no hay flujo, el usuario puede enviarlo manualmente con "Enviar para aprobación".
5. Cada decisión avanza el flujo paso a paso. Al completarse todos los pasos, `Document.approval_status` se actualiza automáticamente.

### Configuración por categoría
En Settings → Approval Workflows: crear flujo con `entity_type=document` y `trigger_conditions={"category":"legal"}`. El motor selecciona el flujo más específico automáticamente.

## 20. Gobierno de flujos: separación operación vs configuración
Objetivo:
- Evitar confusión entre "aprobar solicitudes" y "definir reglas de flujo".
- Centralizar toda definición en Configuración.

Mapa funcional:
- Approval Inbox (`/approvals`): bandeja operativa diaria para aprobar/rechazar pendientes.
- Approval Flows (Config) (`/settings/approval-workflows`): definición de flujos multi-nivel (pasos, roles, tiempos, reglas).
- Project Issue Flows (Config) (`/settings/project-workflows`): definición de estados y transiciones de tareas/incidencias por proyecto.

Compatibilidad de rutas:
- `/workflows` redirige a `/settings/project-workflows`.
- `/settings/workflows` redirige a `/settings/project-workflows`.

Reglas de producto:
- Ninguna pantalla operativa debe mezclar decisiones en curso con edición de definiciones.
- Toda definición de comportamiento de flujo vive bajo Configuración con naming explícito.

## 21. Approval Flows (Config) — capacidades enterprise
URL principal: `/settings/approval-workflows`

Capacidades:
- Templates: biblioteca de plantillas listas para crear flujos base (legal, engineering, expense high-amount) y opción de crear flujo completo desde cero (definición + pasos) desde la misma pestaña.
- Simulator: simulación de selección de flujo y ruta de pasos antes de publicar.
- Validate: valida calidad del flujo (pasos, orden, aprobadores requeridos, consistencia).
- Publish: publicación segura (solo publica si la validación no tiene errores bloqueantes).
- Clone Version: clona un flujo como nueva versión editable sin impactar el activo.
- Bottlenecks: analítica de cuellos de botella por paso (tiempo medio, rechazo, pendientes, riesgo de SLA, score).
  - Dashboard ejecutivo con KPIs globales de riesgo, top workflows con mayor riesgo, tendencia semanal de rechazo y recomendaciones priorizadas (high/medium).

## 22. Approval Engine v2 Enterprise
### Tipos de entidad soportados
`timesheet`, `expense`, `change_request`, `milestone`, `purchase`, `document`, `invoice`, `contract`, `budget`, `leave`, `deliverable`, `proposal`, `subcontractor`, `scope_change`, `hire`, `price_change`.

### Funcionalidades
- **Grupos de aprobadores** (`ApprovalGroup`): CRUD en `/approvals/groups`. Pasos con `approver_type=group` + `approver_group_id`. El motor valida pertenencia leyendo `member_ids`.
- **Quórum paralelo**: `parallel_quorum=True` + `required_approvals`. Varios aprobadores votan en paralelo; el paso avanza al alcanzar quórum. Prevención de doble-voto.
- **Condición de paso** (`step_condition`): JSON con reglas (`amount_gt`, `amount_lt`, `department`, `category`). Si no cumple, se salta automáticamente.
- **Adjunto obligatorio** (`requires_attachment`): la decisión debe incluir `attachment_url`, persistido en `ApprovalDecision`.
- **Recordatorio automático** (`reminder_hours`) antes del timeout.
- **Auto-aprobación** (`auto_approval_rules`): reglas JSON en el workflow; si la solicitud cumple, se auto-aprueba al crearla sin pasar por pasos manuales.
- **Encadenamiento** (`chain_on_approval_workflow_id`): al aprobarse completamente, crea automáticamente nueva solicitud en el workflow encadenado.
- **SLA block** (`sla_block_on_breach`): marca entidad para bloqueo si se supera SLA.
- **Carga de aprobadores** (`/analytics/approver-load`): pendientes, tiempo medio de respuesta, tasa de rechazo, score 0-10, lista de sobrecargados (score > 7).

### Tabs frontend
- **Grupos**: CRUD de grupos con selección de miembros.
- **Carga**: tabla por aprobador con score, badge de sobrecargado y selector de período.
- **Matriz**: grid entidad × flujo con flujos activos/default por tipo de entidad.

### APIs principales
- `GET /api/v1/approvals/workflow-templates`
- `POST /api/v1/approvals/workflows/from-template`
- `POST /api/v1/approvals/simulate`
- `GET /api/v1/approvals/workflows/{workflow_id}/validate`
- `POST /api/v1/approvals/workflows/{workflow_id}/publish`
- `POST /api/v1/approvals/workflows/{workflow_id}/clone-version`
- `GET /api/v1/approvals/analytics/bottlenecks?days=90` — respuesta con `summary`, `top_workflows`, `weekly_trend`, `recommendations`.
- `GET /api/v1/approvals/analytics/approver-load?days=90`
- `GET/POST /api/v1/approvals/groups`
- `GET/PATCH/DELETE /api/v1/approvals/groups/{id}`

Notas:
- `trigger_conditions` soporta reglas por categoría/departamento/importe (`amount_gt`, `amount_gte`, `amount_lt`, `amount_lte`).
- El simulador no crea solicitudes reales; solo evalúa coincidencia y resolución de aprobadores.

## 23. PRD MVP — Chat interno back office
### Objetivo
Canal de comunicación interno unificado para equipos de back office con mensajería en tiempo real, llamadas de voz/video y compartición de archivos, integrado con autenticación y permisos corporativos existentes.

### Alcance del MVP (in)
- Chat en canales públicos/privados.
- Mensajería directa 1:1.
- Edición y borrado de mensajes propios (ventana temporal configurable).
- Adjuntos (imágenes, PDF, Office) con vista previa básica.
- Llamadas de voz y videollamadas de grupo.
- Presencia (online/away/offline) y estados de lectura.
- Búsqueda por texto en mensajes y archivos compartidos.
- Notificaciones in-app y badge de no leídos.
- SSO corporativo + control de acceso por rol/organización.

### Fuera de alcance MVP (out)
- Grabación de llamadas con transcripción automática.
- Federación externa entre organizaciones.
- Bots avanzados y marketplace de apps.
- E2E encryption por defecto en todas las salas.
- eDiscovery legal avanzado.

### Perfiles y permisos (RBAC inicial)
- Admin sistema: configuración global, políticas de retención, auditoría.
- Manager back office: crea canales de equipo, modera miembros y permisos.
- Usuario interno: chat, llamadas, adjuntos en canales permitidos.

### Requisitos funcionales clave
- RF-01: envío/recepción de mensajes en < 500 ms en red corporativa normal.
- RF-02: entrega confiable con reintento y confirmación de estado.
- RF-03: subida de archivo hasta 100 MB por adjunto (configurable).
- RF-04: llamadas de hasta 25 participantes en MVP.
- RF-05: historial accesible por permisos del canal.
- RF-06: auditoría de acciones sensibles (borrado, cambios de permisos, expulsión).

### Requisitos no funcionales
- RNF-01: disponibilidad objetivo 99.9% mensual.
- RNF-02: cifrado TLS en tránsito y cifrado en reposo para adjuntos.
- RNF-03: trazabilidad con correlation id por evento.
- RNF-04: observabilidad (logs, métricas, alertas) desde día 1.
- RNF-05: cumplimiento de políticas de retención internas por canal.

### Arquitectura técnica recomendada
Patrón: experiencia integrada en Contecflow + motores especializados.

Componentes:
- Frontend SPA (módulo chat): canales, DM, hilos, llamadas, archivos.
- API Contecflow: permisos, metadata de canales, auditoría, políticas.
- Motor de mensajería real-time (recomendado Matrix/Synapse o equivalente).
- Motor de media WebRTC (recomendado LiveKit/Jitsi SFU).
- Almacenamiento de adjuntos (S3 compatible, URL firmada con expiración).
- Cola/event bus para eventos internos (notificaciones, auditoría, webhooks).

Flujo resumido:
1. Usuario autentica por SSO.
2. Entra a canal autorizado por RBAC/`organization_id`.
3. Mensajes vía WebSocket y persistencia en motor de chat.
4. Archivos vía upload firmado + escaneo antivirus + metadatos en DB.
5. Llamadas con sala WebRTC y TURN/STUN para redes restringidas.

### Modelo de datos mínimo
- `chat_channels`
- `chat_channel_members`
- `chat_messages`
- `chat_message_reads`
- `chat_attachments`
- `chat_calls`
- `chat_call_participants`
- `chat_audit_events`

### Seguridad y compliance
- Autenticación SSO/OIDC y sesiones con expiración.
- Aislamiento estricto por `organization_id`.
- Política DLP básica en adjuntos (MIME permitido + antivirus).
- URLs firmadas de descarga con TTL corto.
- Registro de auditoría para cambios de rol/permisos y moderación.

### Mockup funcional (desktop)
```text
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ [Contecflow Chat]  Buscar...                           [+]  [Llamada] [Video] [Perfil]   │
├──────────────────┬─────────────────────────────────────────────────┬────────────────────────┤
│ Canales          │ #operaciones                                    │ Detalle canal          │
│ - #general       │ [09:10] Marta: Cerramos reporte mensual hoy?   │ Miembros: 18           │
│ - #operaciones   │ [09:11] Oriol: Si, lo subo en 20 min           │ Archivos: 124          │
│ - #rrhh          │ [09:12] Ana: Adjunto informe.pdf               │ Enlaces fijados: 6     │
│                  │          [informe.pdf]                          │                        │
│ Mensajes directos│ ------------------------------------------------ │ Llamada activa         │
│ - Pau            │ Escribe un mensaje...              [Adjuntar]   │ [miniaturas x4]        │
│ - Ana            │                                                 │ [Silenciar][Compartir] │
└──────────────────┴─────────────────────────────────────────────────┴────────────────────────┘
```

### Plan de implementación por fases
- Fase 0 (1-2 semanas): discovery, UX, criterios de seguridad, PoC de stack.
- Fase 1 (3-4 semanas): chat canales + DM + presencia + notificaciones.
- Fase 2 (2-3 semanas): adjuntos seguros + preview + políticas básicas.
- Fase 3 (3-4 semanas): voz/video + TURN/STUN + controles de llamada.
- Fase 4 (2 semanas): hardening, observabilidad, piloto interno y rollout.

Estimación MVP: 8-12 semanas según nivel de integración y compliance.

### KPIs de éxito del MVP
- Adopción semanal (% usuarios activos de back office).
- Tiempo medio de respuesta en canal.
- Éxito de conexión en llamada (> 98%).
- Latencia p95 de envío de mensaje.
- Incidencias de seguridad/compliance (objetivo: 0 críticas).

### Riesgos técnicos y mitigación
- Red corporativa bloquea WebRTC: desplegar TURN propio y pruebas tempranas.
- Fuga de datos en adjuntos: antivirus + DLP + TTL corto en descargas.
- Sobrecarga del sistema de eventos: colas y límites por canal/usuario.
- Complejidad operativa: preferir motores maduros frente a desarrollo desde cero.

### Decisión arquitectónica pendiente
Stack final:
1. Opción A (self-hosted): Matrix + LiveKit + MinIO.
2. Opción B (SaaS): Stream/Sendbird + proveedor WebRTC gestionado.

Decidir en comité técnico con criterios de coste, soberanía de datos y esfuerzo de operación.
