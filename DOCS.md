# Contecflow PSA - Documentacion Operativa Actual

## 1. Alcance
Este documento describe el estado actual del sistema y como usarlo hoy.
No es un historico de versiones ni un registro de auditorias antiguas.

## 2. Que es Contecflow PSA
Contecflow PSA es una plataforma para gestion integral de servicios profesionales:
- Proyectos, tareas, sprints y planificacion
- Tiempo, capacidad, recursos y ausencias
- Facturacion, gastos, revenue y rentabilidad
- CRM, clientes, contratos y portal cliente
- Service Desk ITSM (tickets, SLA, KB, CMDB, cambios, problemas)
- BI y analitica avanzada
- IA aplicada y gobierno de IA
- Seguridad enterprise (RBAC, ABAC, GRC, SCIM)

## 3. Arquitectura actual
### Backend
- FastAPI
- SQLAlchemy + Alembic
- Celery + Redis para jobs y scheduler
- Pydantic Settings para configuracion
- SQLite local / PostgreSQL productivo

Rutas principales:
- API v1: /api/v1
- API v2: /api/v2 (superficie parcial de compatibilidad)

Entradas clave:
- app/main.py
- app/worker.py
- app/core/config.py
- app/db/session.py
- app/api/v1/endpoints/
- app/services/

### Frontend
- React + Vite
- TanStack Query + Axios
- React Router
- Componentes por dominio

Entradas clave:
- frontend/src/main.jsx
- frontend/src/App.jsx
- frontend/src/services/api.js
- frontend/src/pages/
- frontend/src/components/

## 4. Estructura del repositorio
- app/: backend
- alembic/: migraciones de base de datos
- frontend/: SPA web
- tests/: test suite backend
- tests_e2e/: pruebas end-to-end
- scripts/: utilidades operativas
- reports/: reportes tecnicos activos
- uploads/: almacenamiento temporal local

## 5. Requisitos
- Python 3.12
- Node.js 20+
- npm
- Redis

Opcional:
- PostgreSQL para entorno similar a produccion

## 6. Instalacion
### Backend
1. Crear entorno virtual:
   python -m venv venv
2. Activar entorno:
   - macOS/Linux: source venv/bin/activate
   - Windows: venv\\Scripts\\activate
3. Instalar dependencias:
   pip install -r requirements.txt

### Frontend
1. Entrar en frontend:
   cd frontend
2. Instalar dependencias:
   npm install

## 7. Configuracion
### Backend
Crear .env desde .env.example.
Variables criticas:
- DATABASE_URL
- SECRET_KEY
- REDIS_URL
- CORS_ORIGINS
- claves de proveedores IA si aplica

### Frontend
Crear frontend/.env desde frontend/.env.example.

## 8. Arranque local
### Opcion script
- macOS/Linux: ./setup.sh
- Windows: setup.bat

### Opcion manual
1. API backend:
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
2. Worker Celery:
   celery -A app.worker.celery_app worker --loglevel=info
3. Beat Celery:
   celery -A app.worker.celery_app beat --loglevel=info
4. Frontend (en frontend/):
   npm run dev

## 9. Base de datos
### Migraciones
- alembic upgrade head

Notas operativas recientes:
- Se eliminó la duplicidad de gestión de plantillas de proyecto en UI: la administración queda centralizada en `/project-templates` y ya no aparece como pestaña independiente dentro de `Settings`.
- `/project-templates` permite crear plantillas completas desde cero (fases y tareas, riesgos y entregables) además de instanciar proyectos desde plantilla.
- `setup.sh` usa ahora modos explícitos sin menú interactivo: `./setup.sh demo` (carga seed y arranca), `./setup.sh clean` (limpia datos y deja solo admin, luego arranca), `./setup.sh start` (solo arranca y preserva la base de datos existente).
- `setup.bat` queda alineado con la misma semántica: `setup.bat demo`, `setup.bat clean`, `setup.bat start demo`, `setup.bat start clean`, y en no interactivo `SETUP_INIT_MODE=demo|clean` antes de ejecutar `setup.bat start`.
- Se añadió modo de arranque limpio para pruebas end-to-end desde cero: `./setup.sh admin-only-start`. Este flujo deja la BD sin datos funcionales y conserva solo el usuario `admin` (credenciales tomadas de `SUPERADMIN_EMAIL` y `SUPERADMIN_PASSWORD` en `.env`).
- Se añadió soporte `HEAD /api/v1/documents/file/{file_key}` en almacenamiento local para devolver metadatos (`Content-Type`, `Content-Length`, `Content-Disposition`) sin descargar el fichero, evitando warnings `405` en comprobaciones previas del navegador/UI.
- Se corrigió la serialización de `approval_request` en documentos para usar campos reales del modelo (`ApprovalDecision.decided_at`, `approver_id`, `approver`) en lugar de atributos inexistentes; desaparecen los warnings repetitivos al abrir detalles de documentos.
- Se añadió `pypdf` a dependencias backend para habilitar extracción de texto en PDFs en `ai-summary` sin `ModuleNotFoundError`.
- El cierre del cronómetro ahora permite cancelar la sesión sin guardar, cambiar la tarea final antes de imputar y forzar una imputación duplicada cuando ya existe otra para la misma tarea y fecha.
- Si se fuerza una imputación duplicada desde el cronómetro, se genera una notificación in-app al manager responsable para que revise el timesheet y pueda rechazarlo si procede.
- El módulo de tareas usa estados de workflow por proyecto cuando existen; si un proyecto no tiene workflow configurado, aplica automáticamente los estados base por defecto.
- Se añadió restablecimiento de workflow por proyecto a Scrum estándar mediante DELETE /api/v1/project-workflows/{project_id}/reset, disponible desde la página de configuración de workflows.
- Se corrigió el enrutado de Issue Types para soportar la ruta canónica /api/v1/issue-types/{project_id} (incluyendo /init), manteniendo compatibilidad con alias legado.
- Se corrigió una colisión de variable en la UI de tipos de issue que podía romper textos traducidos al listar o editar tipos.
- Se completó la localización de la página de tipos de incidencia (Issue Types) para español/inglés, incluyendo el botón de inicialización estándar y textos de selección de proyecto.
- Se añadieron mensajes de éxito y error más claros en crear/editar/eliminar/inicializar tipos de incidencia para facilitar diagnóstico en UI.
- Se robusteció el formulario de edición de tipos de incidencia para permitir guardar cambios aunque existan datos legacy con valor interno vacío (autocompletado y validación condicional en modo edición).
- La unicidad usuario+tarea+fecha deja de depender del índice SQL y pasa a controlarse desde la lógica de negocio para permitir únicamente los duplicados forzados desde el cronómetro.
- Las imputaciones duplicadas forzadas nunca sustituyen la anterior: se almacenan como registros adicionales y sus horas se acumulan en los totales semanales (suma de imputaciones).
- Se añade revisión individual de imputaciones para managers en `POST /api/v1/imputations/{imputation_id}/reject` (además de `approve`), para marcar una imputación forzada como rechazada sin borrar el histórico.
- Migración aplicada en entorno local: `alembic upgrade head` (incluye `049_drop_imputation_unique_index_for_forced_timer_overrides`).
- La vista de cronómetro (Time) y el reloj superior (topbar) resuelven nombre de proyecto/tarea por API cuando el payload activo no trae `project_name`/`task_name`, evitando mostrar UUIDs crudos.
- El heartbeat del reloj superior se unifica con el del cronómetro principal para que el efecto visual no cambie al salir de la pestaña Time.
- Ante `409` al detener cronómetro por imputación duplicada, la UI mantiene el control explícito del usuario: solo se fuerza si marca el check de duplicado en el modal.
- En TimerPage y en el widget compacto, no existe reintento forzado automático sin consentimiento explícito del usuario.
- El reloj activo de la barra superior está sincronizado con la misma query global del cronómetro (`timer-current`), por lo que aparece al iniciar y desaparece al detener/imputar sin esperar al ciclo largo de polling.
- El widget compacto del cronómetro también usa `timer-current` y actualiza esa cache en start/pause/resume/stop, asegurando consistencia instantánea entre widget, barra superior y página de Time.
- En `work-dashboard`, la gráfica "Tendencia de horas (mensual)" representa la carga horaria imputada de cada mes (anchura de barra por horas) con barra de color neutro; la variación frente al mes anterior se muestra aparte como indicador textual/porcentaje (con color de tendencia) al final de cada fila.
- En `work-dashboard`, los KPIs de tareas enlazan a `/tasks` con filtros aplicados por URL: abiertas (`status=open`) y vencidas (`status=open&overdue=1`), ambos en ámbito personal (`mine=1`) para evitar saltar al listado general sin filtrar.
- En `tasks`, cuando la vista entra con filtros rápidos por URL (`mine=1`, `overdue=1`, `status=open`), se muestran pills visibles de filtros activos con acción de quitar individual y botón de limpieza rápida.
- En `/timesheets`, las tres pestañas (`Mis timesheets`, `Pendientes`, `Equipo`) incluyen filtros en UI (estado, búsqueda y/o rango de fechas según el contexto) con contador `filtrado/total`, botón `Limpiar` y estado vacío de "Sin resultados".
- En `/imputar` (Registrar horas), los valores diarios y el total semanal del bloque "Esta semana" se formatean con un máximo de 2 decimales para evitar artefactos de coma flotante (ej. `2.969999999...`).
- Se corrigió el flujo de re-aprobación de timesheets: `sync_timesheet_from_imputations_flow` ahora siempre actualiza `total_hours`, `billable_hours` y `total_cost` independientemente del estado del timesheet. Cuando un timesheet está `approved` y el empleado añade nuevas imputaciones no aprobadas para la misma semana, el estado vuelve automáticamente a `draft` para que el empleado pueda re-enviarlo. Esto soluciona que las nuevas horas no aparecieran para aprobación ni se sumaran al total aprobado, y que el manager no viera más timesheets pendientes tras la primera aprobación.
- Las mutaciones de imputaciones ya no dejan el timesheet desfasado: crear una imputación manual, cerrar un cronómetro, editar horas o borrar una línea sincroniza inmediatamente el timesheet semanal. Si la semana ya estaba aprobada y su contenido cambia, la aprobación se invalida al momento y el timesheet vuelve a `draft` limpiando los metadatos de revisión anteriores para forzar una nueva revisión consistente.
- En `/imputar`, la marca de facturable ya es editable tanto al crear como al editar una línea el mismo día; además, las filas muestran un badge visual cuando una imputación es facturable.
- En `/imputar`, el resumen semanal "Esta semana" ya no asigna horas al día incorrecto cuando faltan días intermedios: el grid resuelve cada columna por fecha real de la semana y no por posición en el array devuelto por `by_day`.
- En backend, el listado y lectura individual de imputaciones cargan `user`, `task` y `project` con `joinedload`, evitando consultas N+1 al serializar respuestas de imputaciones y reduciendo coste en una pieza crítica del sistema.
- En `TimerPage`, el selector de tarea del modal de "Parar timer" ahora filtra por `assigned_to_me: true`, igual que el formulario de inicio y que `ImputarPage`. Los tres puntos del flujo de imputación muestran exactamente las mismas tareas asignadas al usuario.
- La state machine de tareas ahora es explícita: `cancelled` es terminal (no se puede salir), y `todo → in_review` es una transición inválida (requiere pasar por `in_progress` primero). El resto de transiciones siguen permitidas para el kanban. El mapa `_TASK_VALID_TRANSITIONS` en `task_service.py` documenta el grafo completo.
- Añadido `POST /api/v1/invoices` para crear facturas manualmente con líneas, tax_rate y datos del cliente. El endpoint calcula `subtotal`, `tax_amount` y `total` automáticamente y genera número secuencial anual (INV-YYYY-NNN).
- Añadido `GET /api/v1/invoices/{id}/pdf` que devuelve un PDF válido (ReportLab) con cabecera `%PDF`, `content-type: application/pdf` y `content-disposition: attachment; filename=factura_NNN.pdf`. Empleados y subcontratistas reciben 403.
- En `/automations`, se corrigió un fallo de render en la pestaña Workflows: `WorkflowsTab` ya inicializa `t` con `useAppT()`, evitando `ReferenceError: t is not defined` al cargar la página.
- Se corrigió una clave de traducción faltante en Tareas: `tasks.no_tasks` se añadió al bloque activo de `tasks` en `es` y `en`, eliminando el warning `[i18n-missing] tasks.no_tasks` en tiempo de ejecución.
- En `/automations`, se completaron traducciones faltantes en el bloque activo (`act_*`, `param_*`, `cat_*`) para `es` y `en`, eliminando warnings `[i18n-missing]` al abrir `WorkflowModal` y configurar pasos/acciones.
- En `/automations`, se añadió cobertura completa de `trig_*` (catálogo total de disparadores) en `es` y `en`, eliminando warnings masivos `[i18n-missing] automations.trig_*` en RuleModal y listados.
- En `/settings`, los inputs sensibles (`type=password`) de "Nuevo Usuario" y de proveedores eSign ahora están dentro de formularios reales (`<form onSubmit=...>`), eliminando el warning del navegador "Password field is not contained in a form" sin cambiar el flujo de guardado.
- En `/tasks`, se añadieron las claves de traducción faltantes `tasks.filter_status` y `common.no_results` en los diccionarios activos de `es` y `en`, eliminando warnings `[i18n-missing]` en filtros y estados vacíos de la vista.
- Se añadió exportación global de listados a Excel compatible (`.xls`) en `PageHeader`: ahora cualquier pantalla con cabecera puede exportar la lista visible (tabla HTML o grid tabular) desde el botón `📊 Exportar Excel` sin implementar lógica específica por página. En `/expenses` se mantiene el botón dedicado backend y se desactiva el export genérico para evitar duplicidad.
- El exportador global de `PageHeader` ahora soporta selección explícita del listado (`exportTargetSelector`) y prefijo de nombre (`exportFilePrefix`), además de limpieza de columnas de acción/checkbox en celdas exportadas. `TasksPage` ya usa este modo (`data-export-table="tasks-list"`) para exportar siempre la tabla correcta de la vista Lista.
- Se extendió el modo explícito de exportación a `Projects`, `Invoices`, `Approvals` y `Service Desk` usando `exportTargetSelector` + `data-export-table`, de forma que `Exportar Excel` toma de forma determinista el listado visible de cada módulo.
- El exportador global añade fallback para listas tipo tarjetas (`div` repetidos): si no hay tabla HTML ni grid tabular, exporta cada tarjeta como fila en una columna `Detalle` (caso útil para bandejas como `Approvals > Pendientes`).
- La exportación de listas permite también estado vacío: si una tabla/listado no tiene filas pero sí cabeceras visibles, se genera igualmente el `.xls` con cabeceras para mantener comportamiento consistente de `Exportar Excel`.

### Seed
- python scripts/seed_full_data.py

Notas:
- SQLite local puede generar .db-wal y .db-shm durante ejecucion.
- No versionar artefactos de BD local.

## 10. Modulos funcionales
### 10.1 Proyectos y delivery
- Proyectos, fases, miembros
- Tareas, dependencias, kanban
- Epics, sprints, planificacion
- Baselines y metricas de seguimiento

### 10.2 Tiempo y recursos
- Imputaciones y timer
- Timesheets y aprobaciones
- Capacity planning y scheduler
- Ausencias, skills, carga y burnout

### 10.3 Finanzas
- Facturas y lineas
- Gastos
- Revenue recognition
- Rentabilidad
- Tipos de cambio

### 10.4 CRM y clientes
- Clientes y contactos
- Pipeline comercial
- Contratos
- Portal cliente

### 10.5 Service Desk ITSM
- Tickets y SLA
- Knowledge base
- Problem management
- Change management
- CMDB y topologia
- Sugerencias IA y auto-resolucion

### 10.6 BI
- Dashboards
- Query builder
- Forecasting
- Anomalias
- ETL connectors
- Colaboracion en dashboards

Nota operativa:
- El panel Mi Trabajo debe mostrar metricas personales del usuario autenticado.
- No debe reutilizar KPIs globales de direccion para tareas, ausencias, gastos o aprobaciones.
- El frontend del cronometro no debe decidir la elegibilidad por `user.hourly_rate` del contexto de sesion: `/auth/me` usa `UserPublic` y no transporta la tarifa. La validacion efectiva de tarifa queda en backend al iniciar o detener el timer.
- El timer activo debe devolver y renderizar `project_name` y `task_name`; los UUID solo se usan como fallback si faltan esos nombres en la respuesta.
- Las metricas de tendencia de horas deben devolver datos tanto en SQLite local como en PostgreSQL.
- La variacion mensual de horas debe suavizar el porcentaje cuando el mes base es demasiado pequeno para evitar lecturas enganhosas.
- El panel lateral de detalle/edicion de tareas debe mantener padding vertical estandar para evitar recorte visual del contenido en la parte superior.
- Estandar global de modales y drawers (panel lateral / dialogo centrado):
  - Contenedor `position: fixed` (drawer: `top: 12, right: 12`; modal centrado: `inset: 0`).
  - Altura por contenido: el modal/drawer crece a la altura natural de su contenido, sin clipping.
  - Tope de seguridad: si el contenido superara la altura del viewport, el cuerpo interno scrollea con `flex: 1; overflowY: auto`. Cabecera y footer permanecen visibles (`flexShrink: 0`).
  - Recortes: ningun ancestro (`.page-content`, `PageShell`, etc.) debe aplicar `transform`, `filter`, `perspective` o `will-change` que persistan tras la animacion de entrada — esos tipos de propiedades crean un containing block que rompe `position: fixed` (el modal aparecer recortado o anclado al top de la pagina en lugar del viewport). La animacion `fadeUp` en `.page-content` se aplica sin `forwards` para no retener `transform` despues del fade.
  - Backdrop: `position: fixed; inset: 0` con click-outside para cerrar.
  - Margen exterior: 12 px (drawer) o `padding: 40px 24px` en el wrapper (modal centrado) para respetar safe zone del viewport.
- Inbox: el contador de la pestanha Notificaciones debe usar la misma fuente que la lista (`/enterprise/notifications` unread_count) para evitar desajustes visuales entre badge y contenido.

### 10.7 IA
- NexusAssist
- Motor semantico
- Gobierno de IA
- Proveedores IA multi-tenant

## 11. Seguridad y compliance
Capacidades activas:
- JWT, refresh y MFA
- RBAC y ABAC
- Aislamiento por organization_id
- Rate limiting
- Cifrado de secretos
- Auditoria de eventos
- GRC y SoD
- SCIM

Puntos de entrada:
- app/core/security.py
- app/core/deps.py
- app/core/abac.py
- app/api/v1/endpoints/grc.py
- app/api/v1/endpoints/governance.py

## 12. Testing
### Backend
- pytest
- fixtures comunes en tests/conftest.py

Comandos utiles:
- pytest -q
- pytest -q tests/test_auth.py
- pytest -q tests/test_service_desk_auto_resolution_endpoint.py

### Frontend
Comandos (en frontend/):
- npm run test
- npm run build

### E2E
- tests_e2e/
- scripts/run-ui-tests-linux-mac.sh

Nota operativa:
- La ruta /approvals tiene smoke e2e dedicado para validar CRUD real de workflows y pasos desde la UI autenticada, con limpieza del dato de prueba al final.
- La suite `tests_e2e/` depende de `playwright` y `pytest-playwright` en Python; tras instalar dependencias puede requerir `playwright install chromium` si el navegador no esta presente en la maquina.

## 13. Operacion
### Observabilidad
- Logs de aplicacion
- Sentry y OpenTelemetry si estan habilitados

### Jobs periodicos
Definidos en app/worker.py:
- Jobs de alertas
- Informes programados
- Jobs BI/ETL
- Jobs IA
- Jobs de service desk

Nota operativa:
- El cierre de APScheduler en el shutdown de la API es idempotente: solo intenta shutdown si el scheduler sigue en estado running.

### Rotacion de claves
- scripts/rotate_keys.sh

## 14. Integraciones
Integraciones soportadas segun configuracion:
- Jira
- Microsoft 365
- GitHub / GitLab
- Salesforce
- Stripe
- Twilio
- AWS S3/KMS

## 15. Troubleshooting rapido
### Backend no arranca
- Verificar entorno virtual activo
- Verificar dependencias instaladas
- Verificar DATABASE_URL

### Migraciones fallan
- alembic current
- alembic upgrade head
- revisar tabla alembic_version

### Worker falla
- Verificar REDIS_URL
- Verificar Redis activo
- Revisar logs worker/beat

### Frontend build falla
- npm install
- revisar frontend/.env
- npm run build

### Seed falla
- ejecutar migraciones primero
- revisar traceback de scripts/seed_full_data.py

## 16. Politica de limpieza del repositorio
No versionar:
- venv y entornos locales
- node_modules y dist
- caches
- archivos temporales de SQLite
- reportes temporales generados localmente
- archivos del sistema operativo

Controlado por .gitignore.

## 17. Mantenimiento de esta documentacion
Reglas:
- DOCS.md refleja estado actual.
- Evitar historicos largos de cambios internos.
- Evitar referencias a documentos retirados.
- Consolidar periodicamente para mantener claridad.

## 18. Motor de flujos de aprobacion documental (implementado)

### Descripcion
Los documentos que requieren aprobacion (`requires_approval=True`) ahora se gestionan a traves del motor de aprobaciones multi-nivel (`approval_engine`). El motor de flujos es una pieza fundamental y diferencial de la plataforma — la misma arquitectura que gestiona timesheets, gastos, facturas y compras ahora tambien rige los documentos.

### Como funciona
1. Al crear un documento con `requires_approval=True`, el sistema busca automaticamente el mejor flujo para esa categoria.
2. Busqueda: primero flujo con `trigger_conditions={"category":"<cat>"}`, luego generico `entity_type=document` + `is_default=True`.
3. Si se encuentra un flujo, se crea un `ApprovalRequest` y se notifica al primer aprobador.
4. Si no hay flujo, el usuario puede enviarlo manualmente con "Enviar para aprobacion" una vez configurado.
5. Cada decision avanza el flujo paso a paso. Al completarse todos los pasos, `Document.approval_status` se actualiza automaticamente.

### Archivos modificados
- `app/models/documents.py`: campo `approval_request_id` FK
- `alembic/versions/050_document_approval_workflow_integration.py`: migracion
- `app/services/approval_engine.py`: `find_default_workflow(category=)`, `find_document_workflow`, `_apply_entity_final_decision`
- `app/services/documents_service.py`: `_auto_create_approval_request`, `submit_for_approval`, `approve_document` via engine, `_serialize_approval_request`
- `app/schemas/documents.py`: `DocumentOut.approval_request`, `DocumentApprovalPayload.note`
- `app/api/v1/endpoints/documents.py`: nuevo `POST /{doc_id}/submit-approval`
- `frontend/src/pages/DocumentsPage.jsx`: panel de progreso, indicador de pasos, historial de decisiones
- `frontend/src/services/api.js`: `documentsApi.submitApproval`

### Configuracion de flujos por categoria de documento
En Settings > Approval Workflows: crear flujo con `entity_type=document` y `trigger_conditions={"category":"legal"}`. El motor selecciona el flujo mas especifico automaticamente.

## 19. Gobierno de flujos: separacion operacion vs configuracion

Objetivo:
- Evitar confusion entre "aprobar solicitudes" y "definir reglas de flujo".
- Centralizar toda definicion en Configuracion.

Mapa funcional:
- Approval Inbox (`/approvals`): bandeja operativa diaria para aprobar/rechazar pendientes.
- Approval Flows (Config) (`/settings/approval-workflows`): definicion de flujos de aprobacion multi-nivel (pasos, roles, tiempos, reglas).
- Project Issue Flows (Config) (`/settings/project-workflows`): definicion de estados y transiciones de tareas/incidencias por proyecto.

Compatibilidad de rutas:
- `/workflows` redirige a `/settings/project-workflows`.
- `/settings/workflows` redirige a `/settings/project-workflows`.

Regla de producto:
- Ninguna pantalla operativa debe mezclar decisiones en curso con edicion de definiciones.
- Toda definicion de comportamiento de flujo debe vivir bajo Configuracion con naming explicito.

## 20. Approval Flows (Config) - capacidades enterprise implementadas

URL principal:
- `/settings/approval-workflows`

Capacidades nuevas:
- Templates: biblioteca de plantillas listas para crear flujos base (legal, engineering, expense high-amount) y opcion de crear un flujo completo desde cero (definicion + pasos) directamente desde la misma pestaña.
- Simulator: simulacion de seleccion de flujo y ruta de pasos antes de publicar.
- Validate: valida calidad del flujo (pasos, orden, aprobadores requeridos, consistencia).
- Publish: publicacion segura (solo publica si la validacion no tiene errores bloqueantes).
- Clone Version: clona un flujo como nueva version editable sin impactar el activo.
- Bottlenecks: analitica de cuellos de botella por paso (tiempo medio, rechazo, pendientes, riesgo de SLA, score).
   - Incluye dashboard ejecutivo con:
      - KPIs globales de riesgo (pasos criticos, pending total, tiempo medio).
      - Top workflows con mayor riesgo agregado.
      - Tendencia semanal de rechazo.
      - Recomendaciones automaticas priorizadas (high/medium) para optimizacion.

## Approval Engine v2 Enterprise (migración 060)

### Nuevos tipos de entidad soportados
invoice, contract, budget, leave, deliverable, proposal, subcontractor, scope_change, hire, price_change
(se suman a timesheet, expense, change_request, milestone, purchase, document)

### Funcionalidades v2

**Grupos de aprobadores** (`ApprovalGroup`):
- CRUD: `GET/POST /approvals/groups`, `PATCH/DELETE /approvals/groups/{id}`
- Los pasos de flujo pueden asignarse a un grupo (`approver_type=group`, `approver_group_id`).
- Autorización: el motor lee los `member_ids` JSON y valida que el usuario decisor sea miembro.

**Quórum paralelo**:
- Campo `parallel_quorum=True` + `required_approvals` en el paso.
- Varios aprobadores pueden votar en paralelo; el paso avanza cuando se alcanza el quórum.
- Prevención de doble-voto: un usuario no puede votar dos veces en el mismo paso/solicitud.

**Condición de paso** (`step_condition`):
- JSON con reglas (`amount_gt`, `amount_lt`, `department`, `category`).
- Si se define, el paso solo se activa si la condición se cumple; si no, se salta automáticamente.

**Adjunto obligatorio** (`requires_attachment`):
- Si el paso lo requiere, la decisión de aprobación debe incluir `attachment_url`.
- El campo `attachment_url` se persiste en `ApprovalDecision`.

**Recordatorio automático** (`reminder_hours`):
- Campo en el paso para configurar recordatorio antes del timeout.

**Auto-aprobación** (`auto_approval_rules`):
- Reglas JSON en el workflow (ej: `[{"condition":"amount_lt","value":100,"action":"auto_approve"}]`).
- Si la solicitud cumple las reglas, se auto-aprueba al crearla sin pasar por pasos manuales.

**Encadenamiento de flujos** (`chain_on_approval_workflow_id`):
- Al aprobarse completamente un flujo, si tiene un workflow encadenado, se crea automáticamente una nueva solicitud en ese workflow.

**SLA block** (`sla_block_on_breach`):
- Marcar entidad para bloqueo si se supera el SLA del flujo.

**Carga de aprobadores** (`/analytics/approver-load`):
- Por aprobador: pendientes, tiempo medio de respuesta, tasa de rechazo, score de carga (0-10).
- Lista de aprobadores sobrecargados (score > 7).

### Nuevas tabs en el frontend

- **Grupos**: CRUD completo de grupos de aprobadores con selección de miembros.
- **Carga**: Tabla de carga de trabajo por aprobador con score, badge de sobrecargado y selector de período.
- **Matriz**: Grid visual entidad × flujo mostrando qué flujos están activos/default por tipo de entidad.

### Archivos modificados

- `alembic/versions/060_approval_engine_v2_enterprise.py`: migración con `approval_groups` tabla + campos v2 en steps/workflows/decisions.
- `app/models/billing_reports.py`: modelo `ApprovalGroup`, campos v2 en `ApprovalWorkflow`, `ApprovalStep`, `ApprovalDecision`.
- `app/services/approval_engine.py`: lógica completa v2 (quórum, auto-aprobación, condiciones, adjuntos, chaining, grupos, serializers v2, `get_approver_load`).
- `app/api/v1/endpoints/approvals.py`: endpoints `/groups` CRUD, `/analytics/approver-load`, `decide` con `attachment_url`.
- `app/schemas/approvals.py`: `DecisionIn.attachment_url`, `StepIn` v2 fields, `WorkflowIn` v2 fields.
- `frontend/src/services/api.js`: `approvalsApi.groups.*`, `approvalsApi.approverLoad`.
- `frontend/src/pages/ApprovalsPage.jsx`: entityLabels +10 entidades, StepModal v2, WorkflowForm v2, tabs Grupos/Carga/Matriz, componentes `ApprovalGroupsTab`, `ApproverLoadTab`, `ApprovalMatrixTab`.

APIs nuevas:
- `GET /api/v1/approvals/workflow-templates`
- `POST /api/v1/approvals/workflows/from-template`
- `POST /api/v1/approvals/simulate`
- `GET /api/v1/approvals/workflows/{workflow_id}/validate`
- `POST /api/v1/approvals/workflows/{workflow_id}/publish`
- `POST /api/v1/approvals/workflows/{workflow_id}/clone-version`
- `GET /api/v1/approvals/analytics/bottlenecks?days=90`
   - Respuesta enriquecida con `summary`, `top_workflows`, `weekly_trend`, `recommendations`.
- `GET /api/v1/approvals/analytics/approver-load?days=90`
- `GET/POST /api/v1/approvals/groups`
- `GET/PATCH/DELETE /api/v1/approvals/groups/{id}`

Notas:
- `trigger_conditions` soporta reglas por categoria/departamento/importe (`amount_gt`, `amount_gte`, `amount_lt`, `amount_lte`).
- El simulador no crea solicitudes reales; solo evalua coincidencia y resolucion de aprobadores.

---

## Sistema de Asignación — Correcciones (5 problemas auditados)

### Problema 1 (Crítico): `record_routing_outcome` nunca llamado al resolver/cerrar ticket

**Antes**: El ML de routing nunca recibía retroalimentación de resultados (tiempo de resolución, CSAT). El modelo no aprendía de tickets cerrados. Solo existía un endpoint manual de backfill (`run_outcome_scan`).

**Después**: Al transicionar un ticket a `resolved` o `closed`, el flag `record_routing_outcome` se añade al dict de efectos devuelto por `apply_ticket_update`. El endpoint PATCH llama a `enqueue_routing_outcome(background_tasks, ticket_id)` que, en background, persiste el resultado en `RoutingFeedback` vía `record_routing_outcome()`.

### Archivos modificados

- `app/services/service_desk/ticket_update_service.py`: retorna `"record_routing_outcome": normalized_status in ("resolved", "closed")` en el dict de efectos.
- `app/services/service_desk/semantic_feedback_service.py`: nueva función `enqueue_routing_outcome(background_tasks, ticket_id)`.
- `app/api/v1/endpoints/service_desk/tickets.py`: importa y llama `enqueue_routing_outcome` en el handler PATCH.

---

### Problema 2 (Alto): `SemAssignment` nunca persistido desde frontend → feedback loop roto

**Antes**: El frontend llamaba a `semanticApi.suggestTask()` y aplicaba la sugerencia al formulario, pero nunca llamaba a `POST /semantic/record-assignment`. La tabla `SemAssignment` quedaba vacía, haciendo que `record_reassign_feedback_bg` fuera un no-op.

**Después**:
- **TaskDetailModal** (tarea existente): `acceptSuggestion()` llama `semanticApi.recordAssignment()` inmediatamente con `task.id` y `was_accepted=true`. Fire-and-forget.
- **CreateTaskModal** (tarea nueva): se guarda la sugerencia aceptada en `pendingSuggestion` state; el `onSuccess(newTask)` de la mutación de creación llama `recordAssignment` con `newTask.id`.

### Archivos modificados

- `frontend/src/services/api.js`: añadido `recordAssignment: (data) => api.post('/semantic/record-assignment', data)` a `semanticApi`.
- `frontend/src/pages/TasksPage.jsx`: `TaskDetailModal.acceptSuggestion` → llama `recordAssignment`; `CreateTaskModal` → añade `pendingSuggestion` state, registra en `onSuccess`.

---

### Problema 3 (Alto): Dos rutas paralelas de sugerencia de tarea con comportamiento distinto

**Antes**: `POST /tasks/suggest-assignee` y `POST /semantic/suggest/task` usaban la misma lógica interna (`SemanticAssigner` + `enrich_suggestion`) pero devolvían formatos diferentes. El frontend solo usaba la ruta semántica; la ruta legacy no tenía marcadores de obsolescencia.

**Después**: `POST /tasks/suggest-assignee` marcado como deprecated (`[DEPRECATED]` en el summary de FastAPI) con cabeceras HTTP `Deprecation: true` y `Link: </api/v1/semantic/suggest/task>; rel="successor-version"` en cada respuesta.

### Archivos modificados

- `app/api/v1/endpoints/tasks.py`: summary actualizado a `[DEPRECATED]`; se añade parámetro `response: Response` para emitir headers de deprecación.

---

### Problema 4 (Medio): `IncidentAssignmentPanel` mostraba recomendación pero no permitía ejecutarla

**Antes**: El panel ML de asignación de incidencias recomendaba un agente pero no tenía botón de acción. El usuario debía ir manualmente al ticket y reasignarlo.

**Después**: Tras recibir la recomendación, aparece el botón "✓ Aplicar asignación" que llama `PATCH /sd/tickets/{ticketId}` con `assigned_to_user_id`. Al éxito, muestra confirmación inline y refresca las estadísticas de carga.

### Archivos modificados

- `frontend/src/components/servicedesk/IncidentAssignmentPanel.jsx`: añadido `applyMutation` + `applySuccess` state + botón "Aplicar asignación" en el bloque de recomendación.

---

### Problema 5 (Medio): Resultados de routing solo actualizados por backfill manual

**Antes**: `run_outcome_scan()` debía ejecutarse manualmente (vía endpoint o cron) para registrar resultados en `RoutingFeedback`.

**Después**: Resuelto automáticamente por el Fix 1. Cada cierre/resolución de ticket dispara `record_routing_outcome` en background. El backfill manual (`run_outcome_scan`) sigue disponible para datos históricos.

---

## Auditoría hardcode — Eliminación de valores quemados en el código

### Objetivo
Eliminar todos los valores de configuración quemados directamente en el código (moneda, zona horaria, idioma, horas laborales, capacidad semanal, días de vacaciones, tipo impositivo) y centralizarlos en `app/core/config.py` (backend) y en un nuevo hook de React (frontend).

### Variables de configuración centralizadas (`app/core/config.py`)
- `DEFAULT_CURRENCY = "EUR"` (sobrescribible con var de entorno)
- `DEFAULT_TIMEZONE = "Europe/Madrid"`
- `DEFAULT_LANGUAGE = "es"`
- `DEFAULT_WORKING_HOURS_PER_DAY = 8.0`
- `DEFAULT_WEEKLY_CAPACITY_HOURS = 40.0`
- `DEFAULT_VACATION_DAYS_PER_YEAR = 23`
- `DEFAULT_TAX_RATE = 21.0`

### Nuevo endpoint backend: `GET /api/v1/settings/org-defaults`
Devuelve los valores de configuración globales de la organización para consumo del frontend:
```json
{"currency":"EUR","timezone":"Europe/Madrid","language":"es","working_hours_per_day":8.0,"weekly_capacity_hours":40.0,"vacation_days_per_year":23,"tax_rate":21.0}
```
Archivo: `app/api/v1/endpoints/settings.py`

### Nuevo hook frontend: `useOrgSettings`
Archivo: `frontend/src/hooks/useOrgSettings.js`  
Fetches `/settings/org-defaults` con TanStack Query (staleTime 5min). Devuelve los valores con fallback a los defaults.

### Archivos backend modificados
- `app/schemas/billing_reports.py`: `InvoiceCreate.tax_rate` y `currency` usan `settings.*`
- `app/schemas/bookings.py`: `BookingCreate.hours_per_day`, `SLAScheduleCreate.timezone`, `RecurringCreate.tax_rate` y `currency` usan `settings.*`
- `app/schemas/users.py`: `UserBase.weekly_capacity_hours` usa `settings.*`
- `app/schemas/service_desk.py`: `OnCallScheduleIn.timezone` y `currency` en asset schema usan `settings.*`
- `app/models/revenue.py`: Column defaults de `currency` en `RevenueContract` y `RevEntry` usan `settings.*`
- `app/services/imputation_service.py`: `or 40.0` → `settings.DEFAULT_WEEKLY_CAPACITY_HOURS`
- `app/services/resource_analytics.py`: `or 40.0` y `or 8` → `settings.*`
- `app/services/olap/etl.py`: `getattr(u,"weekly_capacity_hours",40.0)` y `getattr(p,"currency","EUR")` → `settings.*`
- `app/services/raci_service.py`: `or 40.0` → `settings.*`
- `app/services/billing_reports_service.py`: `or 40` → `settings.*`
- `app/services/ai_chat/context_service.py`: `or 40` → `settings.*`
- `app/services/v238_service.py`: `or 8.0` → `settings.*`
- `app/services/pipeline_service.py`: `currency="EUR"` → `settings.*`
- `app/services/project_service.py`: `"currency":"EUR"` → `settings.*`
- `app/services/cab_service.py`: `getattr(project,"currency","EUR")` × 5 → `settings.*`
- `app/services/service_desk/voice_agent_service.py`: `"language":"es-ES"` → `app_settings.DEFAULT_LANGUAGE`
- `app/services/invoice_pdf.py`: parámetro `currency` sin default hardcode; usa `settings.DEFAULT_CURRENCY` cuando no se informa
- `app/services/integrations.py`: payload Slack de factura pagada usa `settings.DEFAULT_CURRENCY` en lugar de fallback literal
- `app/api/v1/endpoints/slack_block_kit.py`: bloque `invoice_paid` usa `settings.DEFAULT_CURRENCY` como fallback
- `app/api/v1/endpoints/billing_reports.py`: `or "EUR"` → `settings.*`
- `app/api/v1/endpoints/resource_forecast.py`: `or 40` → `settings.*`
- `app/api/v1/endpoints/service_desk/voice_agent.py`: `cfg.get("language","es-ES")` → `settings.*`
- `app/worker.py`: `or "EUR"` → `settings.*`

### Archivos frontend modificados
- `frontend/src/features/bi/widgets.jsx`: `fmtCur` parametrizado; `KpiGridWidget` usa `useOrgSettings`
- `frontend/src/pages/SubcontractorsPage.jsx`: todos los `toLocaleString(...currency:'EUR')` usan `currency` del hook
- `frontend/src/pages/RevenuePage.jsx`: `fmtEur` parametrizado; componente usa `useOrgSettings`; `ObligationsPanel` recibe `currency` como prop
- `frontend/src/pages/ALMPage.jsx`: `CostCentersTab` usa `defaultCurrency` del hook para init/reset de formulario
- `frontend/src/components/dashboard/DashKit.jsx`: `fmtCur` acepta `currency` como 3er parámetro
- `frontend/src/pages/portal-client/PortalAdvancedSections.jsx`: `PortalInvoices` usa `useOrgSettings` para fallback de moneda
- `frontend/src/pages/ExpensesPage.jsx`: `fmt` y formulario `ExpenseModal` dejan de forzar `'EUR'`; usan moneda externa/hook
- `frontend/src/pages/SettingsPageSections.jsx`: `OfficesSection` usa `defaultTimezone` del hook
- `frontend/src/pages/SLACalendarsPage.jsx`: `CalendarForm` usa `defaultTimezone` del hook
- `frontend/src/pages/OrganizationsPage.jsx`: formulario de creación y edición usan `defaultTimezone` del hook
- `frontend/src/services/api.js`: añadido `settingsAdminApi.getOrgDefaults`
- `frontend/src/utils/helpers.js`: `fmtCurrency` deja de forzar `'EUR'` y acepta moneda externa

### Correcciones adicionales en esta sesión
- `app/api/v1/endpoints/analytics_extended.py`: corregido orden de argumentos en `run_analytics_drilldown` (date params deben ir antes de pagination)
- `app/api/v1/endpoints/dashboard.py`: `GET /dashboard/kpis` cambiado de `get_current_user` a `require_admin` para que usuarios PM reciban 403 correctamente
- `frontend/src/pages/RevenuePage.jsx`: corregida regresión en formatter (`const fmt = (n) => fmtEur(n, currency)`) para evitar recursión accidental
- `frontend/src/services/api.js`: `currencyApi` ahora prioriza rutas canónicas (`/currency/rates`, `/currency/convert`, `/currency/report`) y deja rutas legacy como fallback para evitar ruido 404 en desarrollo.
- `frontend/src/pages/portal-client/PortalAdvancedSections.jsx`: `PortalInvoices` deja de usar `useOrgSettings` (auth interna) y usa fallback local de moneda para portal cliente, eliminando `GET /settings/org-defaults 401`.
- `frontend/src/pages/portal-client/PortalAdvancedSections.jsx`: `PortalRoadmap` trata `403` igual que `404` al obtener `/portal/project` para mostrar estado vacío cuando el cliente no tiene proyecto asignado.
- `app/api/v1/endpoints/ws.py`: consumo de ticket WS de portal hace fallback in-memory cuando Redis no está disponible, evitando rechazos 403 en local sin Redis tras reiniciar backend.
- `frontend/src/pages/PortalClientePage.jsx`: el portal cliente unifica `Inicio` y `Estadísticas` en una sola vista (`dashboard`); se elimina la pestaña separada de estadísticas y `PortalStats` se renderiza dentro de la sección principal.
- `frontend/src/pages/portal-client/PortalAdvancedSections.jsx`: `PortalStats` normaliza tamaños, espaciados y jerarquía visual para alinearse con el estilo del dashboard general (cards, tipografía KPI y bloques de progreso/UAT).
- `frontend/src/pages/PortalClientePage.jsx` + `frontend/src/pages/portal-client/PortalContentSections.jsx`: se elimina el doble bloque visual en Home y se consolida en un único dashboard; el resumen UAT se integra dentro del mismo layout principal para evitar secciones mezcladas.
- `frontend/src/pages/portal-client/PortalContentSections.jsx` + `frontend/src/pages/PortalClientePage.jsx`: normalizada la escala tipográfica de `Inicio` y del menú lateral del portal (títulos/subtítulos y labels de navegación) para alinearla con el resto de secciones del portal.
- `frontend/src/pages/portal-client/PortalContentSections.jsx` + `frontend/src/pages/PortalClientePage.jsx`: incremento global de escala tipográfica en Home y menú lateral del portal (títulos, subtítulos, KPIs, actividad y navegación) para mejorar legibilidad con un tamaño mayor en toda la página.
- `frontend/src/pages/PortalClientePage.jsx`: `PortalMyProfile` replica la estructura del perfil de la herramienta principal con pestañas `Perfil`, `Apariencia` (temas), `Idioma` y `Seguridad`; el tema se persiste en `localStorage` (`portal_theme_mode`) y el idioma se guarda en backend portal (`/portal/auth/me`).
- `app/services/client_portal_service.py` + `frontend/src/pages/portal-client/PortalContentSections.jsx`: el Inicio del portal amplía su dashboard con métricas reales de Service Desk y SLA (tickets abiertos, pendientes de cliente, resueltos, 1ª respuesta media, resolución media, cumplimiento SLA, riesgos de breach y CSAT), además de devolver aliases KPI compatibles para entregables/UAT/tickets.
- `frontend/src/pages/portal-client/PortalContentSections.jsx`: la tarjeta `Service Desk y SLA` incrementa tamaño tipográfico, espaciado y densidad visual para mantener el mismo estilo del resto de KPIs del dashboard del portal.
- `frontend/src/pages/portal-client/PortalContentSections.jsx`: la tarjeta `Service Desk y SLA` se rediseña para abandonar la subrejilla de mini-cards y adoptar el mismo patrón limpio del dashboard principal: métricas en filas, barra de cumplimiento SLA y resumen de riesgos con jerarquía visual coherente.
- `frontend/src/pages/portal-client/PortalContentSections.jsx`: las tarjetas de detalle del Inicio del portal se reorganizan en dos filas lógicas: `Presupuesto del proyecto` + `Próximo hito`, y debajo `Pruebas UAT` + `Service Desk y SLA`.



## Settings → E-firma (nueva sección)

### Descripción
Sección de configuración de credenciales para proveedores de firma electrónica (DocuSign y Adobe Sign) accesible desde Settings → Sistema → E-firma (solo rol admin).

### Backend
- `app/api/v1/endpoints/esign.py`: añadidos endpoints `GET /esign/config` y `PATCH /esign/config` que persisten las credenciales en la tabla `app_settings` (KV store existente, sin nueva migración).
- Helper `_get_esign_setting` / `_set_esign_setting` para leer/escribir por clave `esign.*`.
- Secretos (`docusign_secret_key`, `adobe_sign_client_secret`) se enmascaran como `"***"` en la respuesta GET; PATCH ignora el valor `"***"` para no sobreescribir con el placeholder.
- `GET /esign/summary/stats` ahora consulta primero las claves DB y hace fallback a env vars para determinar `docusign_configured` / `adobe_configured`.

### Frontend
- `frontend/src/services/api.js`: `esignApi` ampliado con `getConfig` y `saveConfig`.
- `frontend/src/pages/SettingsPageSections.jsx`: nuevo componente `ESignSettingsSection` con dos tarjetas (DocuSign / Adobe Sign), badge de estado configurado/no configurado, campos de credenciales (secretos tipo password), botón Guardar por proveedor, y nota sobre modo manual.
- `frontend/src/pages/SettingsPage.jsx`: importado `ESignSettingsSection`; añadida pestaña `{ id: 'esign', label: 'E-firma', roles: ['admin'] }` en el grupo Sistema.
- `frontend/src/pages/ESignPage.jsx`: el texto estático "Configura las credenciales en Settings → E-firma para habilitar las integraciones." reemplazado por un enlace clicable a `/settings`.


## Exportar a Excel: limpieza global por pantalla

### Descripción
Se ha aplicado `showListExport={false}` a todas las pantallas que no tienen una lista exportable real (dashboards, vistas Gantt/Kanban, herramientas, formularios, configuración, integraciones). El botón "Exportar lista a Excel" solo queda visible en las pantallas con tablas o listas de datos exportables.

### Páginas con export desactivado (55 pantallas)
AIHubPage, ALMPage, AgentDashboardPage, AlertsPage, BPMPage, CalendarPage, ChangelogPage, ChangesPage, ClientPortalPage, DataExplorerPage, DataGovernancePage, DataPlatformPage, DeveloperPortalPage, EnterprisePage, EpicGanttPage, EpicsPage, ExportsPage, GanttPage, GovernancePage, ImportPage, ImputarPage, InboxPage, InternalCommentsPage, JiraIntegrationPage, KanbanAdvancedPage, MFAPage, MeetingsAIPage, MentionsPage, MilestoneBillingPage, NPSPage, NexusAgentPage, NotificationsPage, OKRsPage, OraclePage, OrganizationsPage, PerformanceReviewsPage, PipelinePage, PredictionsPage, ProfitabilityPage, ProjectTemplatesPage, ReportBuilderPage, RiskScoresPage, ScenariosPage, SearchPage, SemanticEnginePage, SettingsPage, SprintChartsPage, SprintPlanningPage, SprintsPage, TimesheetsPage, UATPage, WikiPage, WorkflowsPage, WorkflowDesignerPage (service-desk).

### Páginas con export habilitado (listas reales)
ProjectsPage, InvoicesPage, ApprovalsPage, ServiceDeskPage, TasksPage, AbsencesPage, AutomationsPage, BudgetsPage, CMDBPage, CapacityPage, ClientsPage, ContractsPage, CumulativeFlowPage, CustomFieldsPage, DeliverablesPage, DependenciesPage, DocumentsPage, ESignPage, EVMPage, ExpensesPage (export backend), BIPage, BIProjectDetailPage, GitPage, GrcPage, IssueTypesPage, M365Page, OrgChartPage, PortfolioPage, ProjectPermissionsPage, PublicFormsPage, RACIPage, RateCardsPage, ReportsPage, ResourceForecastPage, ResourcesPage, RevenuePage, RisksPage, SkillsPage, SubcontractorsPage, TimerPage, TrainingPage, UserCostsPage, WebhookLogPage.
