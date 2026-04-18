
### v23.10.1 (Abril 2026) — Bus de eventos completo, correcciones de seguridad y deuda técnica

**Sistema de eventos — cobertura completa:**
- Todos los módulos principales emiten ahora eventos de sistema tras cada acción relevante: tareas, proyectos, sprints, gastos, riesgos, aprobaciones y carteras.
- Nuevo módulo centralizado `app/core/events.py` con catálogo `EventType` (~60 tipos), funciones `emit_event()`, `emit()` (lee actor desde `db.info`) y alias legacy `emit_system_event()`.
- El actor queda disponible en toda la capa de servicios sin cambiar firmas: `get_current_user` almacena el usuario en `db.info["current_user"]` tras autenticarse.
- Los eventos se despachan síncronamente al subsistema de webhooks existente (`fire_webhook`); errores no propagan al flujo principal.

**Seguridad — aislamiento multi-tenant en Semantic Engine:**
- `semantic_engine_service.py`: usuarios sin `is_superadmin` y sin `organization_id` reciben lista vacía en lugar de ver todos los perfiles. Los superadmins conservan visibilidad global.
- El import de `User` se movió fuera del bloque condicional (`if org_id:`), eliminando el `UnboundLocalError` en producción.

**Portfolio — correcciones de routing y NameErrors:**
- Todos los endpoints del router de carteras (`portfolio.py`) registran ahora las rutas tanto con como sin `/` final (`@router.get("")` + `@router.get("/")`), resolviendo el 404 con `redirect_slashes=False`.
- Eliminados 6 `NameError` causados por referencias a `response` no definida en endpoints de cartera.
- Los endpoints de cartera emiten eventos (`PORTFOLIO_CREATED`, `PORTFOLIO_UPDATED`, `PORTFOLIO_DELETED`, `PORTFOLIO_PROJECT_ADDED`, `PORTFOLIO_PROJECT_REMOVED`).

**Frontend — correcciones ReferenceError i18n:**
- Corregido `t is not defined` en MilestoneBillingPage, ExecutiveDashboardPage, SprintChartsPage, SemanticEnginePage, WorkflowsPage, GrcPage, ProjectPermissionsPage y CustomFieldsPage. El hook `useAppT()` devuelve `_t`, no `t`.

**Logging:**
- El sondeo `GET /api/v1/auth/me` con 401 (comprobación de sesión del frontend) se registra como INFO en lugar de WARNING, eliminando falsos positivos en los logs de aplicación.

**mfa_service.py — limpieza de deuda técnica:**
- Eliminada función `remove_user_from_org` orphaned definida antes de los imports. Reimplementada correctamente después de todos los imports.
- Las llamadas a `emit_system_event` se migran a `emit_event` desde `app.core.events`.

---

### v23.9.9 (Abril 2026) — Seguridad AI, Bookings y Multi-tenant

**AI Assistant — Seguridad de datos financieros:**
- El contexto AI (`build_tenant_context`) ahora recibe siempre el objeto `User` y filtra por `organization_id` en todas las queries, evitando exposición de datos financieros a roles no autorizados y garantizando aislamiento multi-tenant.
- Solo usuarios con rol `admin`, `hr` o `is_superadmin` pueden acceder a datos financieros (costes, facturas, rentabilidad) en el contexto y herramientas AI (`get_invoices`, `get_profitability`).
- El endpoint `/ai/chat` y `prepare_chat` ya no pasan `user=None`.

**AI Tools — Control de acceso:**
- Las herramientas AI `get_invoices` y `get_profitability` ahora requieren rol `admin`, `hr` o `is_superadmin`. Otros roles reciben error de acceso denegado.

**Bookings — Validación de solapamiento:**
- `create_booking_record` ahora valida que no existan reservas solapadas para el mismo usuario y recurso en las fechas indicadas. Si existe, devuelve error 400.

**Multi-tenant — Filtros organization_id:**
- Todas las queries de contexto AI y bookings filtran por `organization_id` del usuario salvo para superadmins.

**Documentación y código:**
- Se han actualizado los comentarios y la documentación para reflejar estos cambios críticos de seguridad y lógica.
# Clarive PSA — Documentación Completa del Sistema

## 🛠️ Arquitectura de Orquestación de Servicios (Auditoría 2026)

**Cumplimiento de orquestación de servicios:**

Tras auditoría exhaustiva (abril 2026), se confirma que toda la lógica de negocio del backend está centralizada en módulos de servicios (`app/services/`). Los endpoints y routers de la API únicamente orquestan dependencias, validaciones y delegan la lógica a funciones de servicios, sin implementar reglas de negocio directas ni acceso a base de datos fuera de los servicios.

**Patrón aplicado:**
- Los endpoints (FastAPI routers) solo reciben, validan y delegan.
- Toda lógica de negocio, side effects, validaciones complejas y acceso a datos residen en módulos de servicios.
- No existen endpoints legacy, duplicados ni lógica directa en routers tras la limpieza de deuda técnica y deprecated.
- El sistema cumple estrictamente el principio de orquestación de servicios, facilitando mantenibilidad, testeo y extensibilidad.

**Ejemplo de endpoint correcto:**
```python
@router.post("/catalog/services", summary="Crear servicio")
def create_service(payload: ServiceItemIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
  s = create_service_record(db, payload)  # delega a servicio
  _commit_or_rollback(db); db.refresh(s)
  return {"id": s.id, "name": s.name}
```

**Ejemplo de módulo de servicio:**
```python
# app/services/service_desk/catalog_service.py
def create_service_record(db: Session, payload: ServiceItemIn):
  # Lógica de negocio, validaciones, acceso a modelos y side effects
  ...
```

**Resultado:**
- El backend es 100% orquestado por servicios, sin lógica de negocio directa en endpoints.
- Cumple arquitectura desacoplada, versionada y preparada para multi-tenant, CI/CD y extensiones futuras.


> **Versión actual:** 23.10.0 · **Fecha:** Mayo 2026  
> Professional Services Automation para consultoras modernas.

---


## 📦 Configuración y catálogos externalizados (v23.10+)

Desde la versión 23.10, **todos los valores de negocio, catálogos, límites, triggers, integraciones y constantes de UI** han sido externalizados a archivos JSON en el frontend y variables/env/config en el backend. Esto permite:

- Multi-tenant y personalización sin tocar código.
- Actualización de catálogos, triggers, integraciones y límites desde archivos de configuración.
- Eliminación de hardcoded business logic en frontend y backend.

### Estructura de configuración frontend

- **frontend/src/constants/constants.json**  
  Catálogos de negocio: roles, tipos de proyecto, tipos de facturación, prioridades, estados de tarea, tipos de ticket, niveles de SLA, docs de proveedores IA.

- **frontend/src/constants/business_config.json**  
  Parámetros de negocio y UI:  
  - `TIMEOUT`, `PAGINATION`, `REFETCH`, `LIMITS`
  - `INTEGRATION_CATALOG`: catálogo de integraciones externas (Slack, Teams, Jira, GitHub, etc.)
  - `AUTOMATION_TRIGGERS`, `AUTOMATION_ACTIONS`, `AUTOMATION_OPERATORS`, `AUTOMATION_ACTION_PARAMS`: motor de automatizaciones
  - `PROVIDER_META`: metadatos de proveedores IA (icono, color, nombre)
  - `ROLE_LABELS`, `ROLE_COLORS`: etiquetas y colores de roles para UI
  - `EMAIL_PROVIDER_GUIDES`: guías de configuración de email providers

- **frontend/src/constants/api.js**  
  Expone todas las constantes y catálogos como imports centralizados desde los JSON, para uso en toda la app React.

### Estructura de configuración backend

- **app/core/config.py**  
  Todas las variables de entorno y parámetros de negocio se gestionan vía `.env` y Pydantic Settings.
- **app/db/seed.py**  
  Los datos semilla (usuarios, clientes, plantillas de email) se cargan desde archivos JSON externos si existen, o usan defaults parametrizables.
- **Catálogos y constantes de negocio**  
  Todos los catálogos, triggers, límites y parámetros de negocio se pueden sobreescribir vía archivos JSON o variables de entorno.

### Ejemplo de uso en frontend

```js
// src/constants/api.js
import constants from './constants/constants.json';
import businessConfig from './constants/business_config.json';

export const ROLES = constants.ROLES;
export const INTEGRATION_CATALOG = businessConfig.INTEGRATION_CATALOG;
export const AUTOMATION_TRIGGERS = businessConfig.AUTOMATION_TRIGGERS;
// ...etc
```

### Ventajas

- **Sin hardcoded business logic**: todo configurable.
- **Fácil actualización**: solo editar JSON/config.
- **Personalización multi-tenant**: cada cliente puede tener su propio set de catálogos, triggers, límites, integraciones, etc.
- **Preparado para white-label y despliegues custom**.

## Tabla de contenidos

1. [Descripción general](#1-descripción-general)
2. [Arquitectura técnica](#2-arquitectura-técnica)
3. [Stack tecnológico](#3-stack-tecnológico)
4. [Módulos y funcionalidades](#4-módulos-y-funcionalidades)
5. [Modelo de datos](#5-modelo-de-datos)
6. [API — Endpoints](#6-api--endpoints)
7. [Seguridad](#7-seguridad)
8. [Variables de entorno](#8-variables-de-entorno)
9. [Instalación y arranque rápido](#9-instalación-y-arranque-rápido)
10. [Despliegue en producción (Docker)](#10-despliegue-en-producción-docker)
11. [Migraciones de base de datos](#11-migraciones-de-base-de-datos)
12. [Tests](#12-tests)
13. [CI/CD](#13-cicd)
14. [Usuarios y roles](#14-usuarios-y-roles)
15. [Portal de cliente externo](#15-portal-de-cliente-externo)
16. [Integraciones externas](#16-integraciones-externas)
17. [Novedades por versión](#17-novedades-por-versión)
18. [Guía de desarrollo](#18-guía-de-desarrollo)
19. [Flujo coordinado de Feature Requests y Control de Cambios](#19-flujo-coordinado-de-feature-requests-y-control-de-cambios)

21. [Gestión de Organizaciones y Usuarios (Multi-Tenancy)](#21-gestion-de-organizaciones-y-usuarios-multi-tenancy)
## 21. Gestión de Organizaciones y Usuarios (Multi-Tenancy)

### Endpoints principales

- `GET /organizations` — Listar organizaciones (admin)
- `POST /organizations` — Crear organización
- `GET /organizations/{org_id}` — Detalle de organización
- `PATCH /organizations/{org_id}` — Actualizar organización
- `POST /organizations/{org_id}/assign-user` — Asignar usuario a organización
- `DELETE /organizations/{org_id}/remove-user/{user_id}` — Quitar usuario de organización

### Validaciones y restricciones

- No se pueden asignar usuarios inactivos.
- No se pueden asignar usuarios ya asignados a otra organización.
- No se pueden asignar usuarios duplicados.
- No se puede superar el límite de usuarios por organización (según plan).
- No se puede quitar el último usuario de una organización.
- Todas las acciones relevantes quedan auditadas.
- Solo administradores pueden asignar/quitar usuarios.

### Orquestación y eventos

Todos los módulos del backend emiten eventos de sistema tras cada acción relevante. El bus de eventos está implementado en `app/core/events.py`.

**Cobertura por dominio:**

| Dominio | Eventos emitidos |
|---------|-----------------|
| Organización | `organization.user_assigned`, `organization.user_removed` |
| Usuario | `user.created`, `user.updated`, `user.role_changed`, `user.deactivated`, `user.activated` |
| Cartera | `portfolio.created`, `portfolio.updated`, `portfolio.deleted`, `portfolio.project_added`, `portfolio.project_removed` |
| Proyecto | `project.created`, `project.updated`, `project.status_changed`, `project.member_added`, `project.member_removed`, `project.completed` |
| Tarea | `task.created`, `task.updated`, `task.completed`, `task.assigned`, `task.deleted` |
| Sprint | `sprint.created`, `sprint.started`, `sprint.completed`, `sprint.deleted` |
| Gasto | `expense.submitted`, `expense.approved`, `expense.rejected` |
| Aprobación | `approval.requested`, `approval.approved`, `approval.rejected` |
| Riesgo | `risk.created`, `risk.updated`, `risk.mitigated`, `risk.closed` |
| Hito | `milestone.created`, `milestone.updated`, `milestone.completed`, `milestone.approved`, `milestone.invoiced` |
| Ticket | `ticket.created`, `ticket.updated`, `ticket.assigned`, `ticket.resolved`, `ticket.closed`, `ticket.escalated` |
| Financiero | `invoice.created`, `invoice.paid`, `budget.exceeded` |
| Contrato | `contract.created`, `contract.signed`, `contract.expired`, `opportunity.won`, `opportunity.lost` |
| Documento | `document.uploaded` |
| Riesgo GRC | `risk.created`, `risk.mitigated`, `risk.closed` |

**Patrón de emisión (siempre después de `db.commit()`):**

```python
from app.core.events import emit, EventType

# En un servicio — actor leído automáticamente desde db.info["current_user"]
db.commit()
emit(db, EventType.TASK_CREATED,
     {"task_id": task.id, "title": task.title, "project_id": task.project_id},
     resource_type="task", resource_id=task.id, project_id=task.project_id)
```

**Actor disponible sin cambiar firmas:**  
`get_current_user` almacena el usuario autenticado en `db.info["current_user"]`. La función `emit()` lo resuelve automáticamente si no se pasa `actor=` de forma explícita.

**Dispatch a webhooks:**  
Los eventos se envían síncronamente a los webhooks configurados via `fire_webhook`. Los errores de dispatch no propagan al flujo principal.

### Seguridad

- Todas las rutas requieren autenticación y permisos de administrador.
- El frontend previene errores comunes y refleja los mensajes del backend.

### Notas

- Para más detalles, consulta `app/core/events.py` (catálogo completo `EventType`) y los servicios en `app/services/`.
- El módulo `app/services/mfa_service.py` gestiona asignación/desvinculación de usuarios a organizaciones.

---

## 1. Descripción general

**Clarive PSA** es una plataforma integral de gestión de servicios profesionales diseñada para consultoras. Cubre todo el ciclo de vida del negocio: desde la captación de oportunidades en el pipeline hasta la facturación, pasando por gestión de proyectos, imputación de horas, service desk ITSM/ITIL y un portal de cliente externo completamente autónomo.

### Capacidades principales

| Área | Descripción |
|------|-------------|
| **Gestión de proyectos** | Proyectos, tareas Kanban/Gantt, sprints, entregables, riesgos, cambios, dependencias, milestones |
| **Recursos y RRHH** | Imputación de horas, timesheets, capacidad, skills, ausencias, formación, revisiones de desempeño |
| **Negocio** | Pipeline CRM, contratos, facturación, rentabilidad, Rate Cards, EVM, análisis financiero |
| **Service Desk ITSM** | Tickets (incidencias, solicitudes, cambios, problemas), SLA automático P1-P4, KB, CMDB |
| **BI y reporting** | 28+ métricas, exportación Excel/CSV, report builder personalizable, alertas automáticas |
| **Portal cliente** | Acceso externo en `/portal`, UAT, feature requests, mensajería, hoja de ruta, documentos |
| **Integraciones** | Azure AD/Okta/Google SSO, GitHub/GitLab, DocuSign/AdobeSign, Microsoft 365, Xero, QuickBooks |
| **IA** | AI Hub con soporte para Anthropic, OpenAI, Gemini, Mistral, DeepSeek, Groq, Ollama, Azure OpenAI |

---

## 2. Arquitectura técnica

```
┌─────────────────────────────────────────────────────────────────┐
│                         NGINX (reverse proxy)                    │
│                     puerto 80 / 443                              │
└────────────┬────────────────────────┬───────────────────────────┘
             │                        │
             ▼                        ▼
  ┌──────────────────┐    ┌──────────────────────┐
  │  Frontend React  │    │   Backend FastAPI     │
  │  (Vite + Nginx)  │    │   (uvicorn + uvloop)  │
  │  puerto 3000     │◄──►│   puerto 8000         │
  │                  │    │   /api/v1/*           │
  └──────────────────┘    └────────┬─────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
     ┌──────────────┐   ┌──────────────────┐   ┌──────────────┐
     │  SQLite      │   │  PostgreSQL 16   │   │   Redis      │
     │  (dev)       │   │  (producción)    │   │  (Celery +   │
     └──────────────┘   └──────────────────┘   │   caché)     │
                                               └──────────────┘
                                   │
                          ┌────────┴────────┐
                          │  AWS S3         │
                          │  (documentos)   │
                          └─────────────────┘
```

### Estructura de directorios

```
nexuspm_v23/
├── app/                        # Backend FastAPI
│   ├── main.py                 # Entry point, lifespan, middleware
│   ├── worker.py               # Celery worker definition
│   ├── api/v1/
│   │   ├── router.py           # Registro de todos los routers
│   │   └── endpoints/          # ~75 módulos de endpoints
│   ├── core/
│   │   ├── config.py           # Settings (pydantic-settings)
│   │   ├── security.py         # JWT, bcrypt, TOTP
│   │   ├── deps.py             # FastAPI dependencies (auth)
│   │   ├── encryption.py       # Fernet v2 per-record HKDF
│   │   └── ratelimit.py        # slowapi rate limiter
│   ├── db/
│   │   ├── base.py             # Base SQLAlchemy
│   │   ├── session.py          # Engine + SessionLocal
│   │   ├── seed.py             # Datos iniciales
│   │   └── migrate.py          # Legacy migrations (fallback)
│   ├── models/                 # ~52 modelos SQLAlchemy
│   ├── schemas/                # Pydantic schemas (service_desk, ai_chat, …)
│   └── services/               # Lógica de negocio (sla_service, ai_client, audit, S3, …)
├── frontend/                   # React 18 + Vite
│   ├── src/
│   │   ├── App.jsx             # Router principal
│   │   ├── main.jsx            # Entry point
│   │   ├── pages/              # ~90 páginas
│   │   ├── components/         # Componentes reutilizables
│   │   ├── context/            # AuthContext, ToastContext, ConfirmContext
│   │   └── services/api.js     # Axios + interceptores
│   ├── eslint.config.js        # ESLint 9 flat config (0 warnings)
│   └── vite.config.js          # Vite + PWA (PWA manifest: Clarive)
├── alembic/                    # Migraciones de BD (20 versiones)
│   ├── versions/
│   │   ├── 001_initial_tables.py              # Baseline (no-op)
│   │   ├── 002_incremental.py                 # ALTER TABLE ADD COLUMN (idempotente)
│   │   ├── 003_document_management.py         # Gestión documental
│   │   ├── 004_v24_features.py                # Timezone, facturación recurrente, OAuth apps
│   │   ├── 005_security_hardening.py          # Columnas cifradas, bloqueo imputaciones
│   │   ├── 006_webauthn_passkeys.py           # WebAuthn / passkeys
│   │   ├── 007_user_sessions_panel.py         # Panel de sesiones de usuario
│   │   ├── 008_governance_scim_policy.py      # Governance, SCIM, policies
│   │   ├── 009_abac_fine_grained_auth.py      # ABAC (Attribute-Based Access Control)
│   │   ├── 010_security_observability.py      # SOC event log, detecciones
│   │   ├── 011_ai_governance_guardrails.py    # AI Governance, guardrails, audit logs
│   │   ├── 012_sem_config_priority.py         # Umbrales semánticos por prioridad
│   │   ├── 013_sem_config_calibration.py      # Calibración motor semántico
│   │   ├── 014_ai_providers.py                # Tablas de proveedores IA multi-tenant
│   │   ├── 015_multitenant_org_isolation.py   # Aislamiento por org en proyectos
│   │   ├── 016_task_status_in_review.py       # Estado in_review en tareas
│   │   ├── 017_mfa_sso_hardening.py           # Replay protection MFA + tenant SSO
│   │   ├── 018_drop_user_refresh_token_jti.py # Limpieza de columna obsoleta
│   │   ├── 019_client_user_multiproject.py    # Portal cliente multi-proyecto
│   │   └── 020_tenant_scope_ai_providers.py   # org_id en ai_providers y rate_tables
│   └── env.py
├── tests/                      # 800+ tests (pytest)
├── tests_e2e/                  # Tests Playwright end-to-end
├── nginx/                      # Configuración nginx producción
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## 3. Stack tecnológico

### Backend

| Paquete | Versión | Uso |
|---------|---------|-----|
| FastAPI | 0.135.3 | Framework web async |
| uvicorn + uvloop | 0.29.0 | ASGI server de alto rendimiento |
| SQLAlchemy | 2.0.36 | ORM |
| Alembic | 1.13.0 | Migraciones de base de datos |
| psycopg2-binary | 2.9.11 | Driver PostgreSQL |
| Pydantic | 2.12.5 | Validación de datos y schemas |
| python-jose | 3.5.0 | JWT (access + refresh tokens) |
| PyJWT | 2.12.1 | Verificación de id_token SSO (JWKS) |
| bcrypt | 4.0.1 | Hash de contraseñas |
| cryptography | 46.0.6 | Fernet per-record encryption (HKDF) |
| pyotp | 2.9.0 | TOTP (2FA/MFA) |
| slowapi | 0.1.9 | Rate limiting |
| celery + redis | 5.6.3 / 6.4.0 | Cola de tareas asíncronas |
| APScheduler | 3.11.2 | Tareas programadas |
| boto3 | 1.42.83 | AWS S3 (almacenamiento documentos) |
| openpyxl | 3.1.2 | Exportación Excel |
| reportlab | 4.4.10 | Generación PDF |
| sentence-transformers | 5.3.0 | Embeddings para búsqueda semántica |
| sentry-sdk | 2.57.0 | Error tracking |

### Frontend

| Paquete | Versión | Uso |
|---------|---------|-----|
| React | 18.x | UI framework |
| Vite | 5.x | Build tool |
| React Router | 6.x | Routing SPA |
| @tanstack/react-query | 5.x | Server state management |
| Axios | 1.x | Cliente HTTP + interceptores |
| Recharts | 2.x | Gráficos y visualizaciones |
| Tailwind CSS | 3.x | Estilos utilitarios |
| Lucide React | — | Iconografía |
| react-window | — | Virtualización de listas largas |
| date-fns | — | Manipulación de fechas |
| vite-plugin-pwa | — | Progressive Web App |

### Infraestructura (producción)

| Componente | Tecnología |
|------------|------------|
| Reverse proxy | Nginx Alpine |
| Base de datos | PostgreSQL 16 |
| Caché / broker | Redis 7 |
| Almacenamiento | AWS S3 (o filesystem local en dev) |
| Contenedores | Docker + Docker Compose |

---

## 4. Módulos y funcionalidades

### 4.1 Gestión de proyectos

- **Proyectos**: ciclos de vida completos (presupuesto, fechas, estado, tipo, facturación)
- **Tareas Kanban**: tablero drag-and-drop, prioridades, asignación, etiquetas, checklists
- **Gantt**: vista cronológica de tareas y dependencias
- **Sprints**: planificación, velocidad, burn-down, cumulative flow
- **Entregables**: con estados de aprobación cliente (UAT)
- **Riesgos**: matriz impacto/probabilidad, mitigación, scoring
- **Control de cambios**: solicitudes formales, aprobación por roles
- **Milestones**: hitos vinculados a facturación (SOW billing)
- **OKRs**: objetivos y resultados clave a nivel empresa/equipo/individuo
- **Dependencias**: DFS de dependencias entre tareas entre proyectos
- **EVM**: Earned Value Management (CPI, SPI, EAC, ETC)
- **RACI**: matrices de responsabilidad
- **Calendario global**: vista mensual de tareas, milestones, sprints, ausencias
- **Wikis**: documentación interna por proyecto con tags y búsqueda semántica

### 4.2 Recursos y RRHH

- **Imputación de horas**: registro diario por proyecto/tarea. Timer con pausa/reanudación
- **Timesheets**: vista semanal, aprobación, lockout configurable (días retroactivos)
- **Capacidad**: heatmap de carga, forecast de disponibilidad, alertas de sobrecarga
- **Skills**: catálogo, asignación a usuarios, matching con proyectos
- **Ausencias**: solicitudes, aprobación, tipos, integración con calendario y capacidad
- **Formación**: planes de formación, cursos, valoraciones
- **Revisiones de desempeño**: ciclos de evaluación 360°
- **OrgChart**: organigrama interactivo

### 4.3 Negocio y finanzas

- **Pipeline CRM**: etapas Kanban, probabilidad, valor esperado, reporting
- **Contratos**: multitipo (T&M, precio fijo, retainer, mixto), estado, renovación
- **Facturación**: facturas vinculadas a milestones o contratos, estados de pago
- **Rate Cards**: tarifas por rol/proyecto con overrides y effective-rate calculator
- **Rentabilidad**: margen por proyecto, coste de equipo vs ingresos, burn rate
- **Gastos**: registro con justificantes, estados de aprobación
- **Revenue Recognition**: amortización de ingresos según reglas y períodos
- **Contabilidad hub**: integración Xero / QuickBooks (webhooks + sincronización)
- **Subcontratistas**: gestión de horas y costes de terceros

### 4.4 Service Desk ITSM/ITIL

- **Tipos de ticket**: Incidencia, Solicitud de servicio, Cambio, Problema, Pregunta
- **SLA automático** por prioridad P1-P4: respuesta y resolución, escalado automático L1/L2/L3
- **Base de conocimiento**: artículos KB con categorías, tags, búsqueda semántica IA
- **CMDB**: activos de TI vinculados a tickets (servidores, apps, dispositivos)
- **Gestión de Problemas**: agrupación de incidencias, RCA, estado de resolución
- **Calendarios SLA**: horarios hábiles por zona horaria, festivos
- **Internal Comments**: comentarios internos del equipo no visibles al cliente
- **NPS / CSAT**: encuestas de satisfacción vinculadas a resolución de tickets
- **Funciona con o sin proyecto vinculado**

### 4.5 BI y Análisis

- **Dashboard principal**: KPIs en tiempo real, widgets configurables
- **Executive Dashboard**: visión de negocio de alto nivel para dirección
- **Report Builder**: constructor visual de informes con 28+ métricas
- **Alertas automáticas**: umbrales configurables, notificación Slack/email
- **Exportación**: Excel y CSV para todos los módulos tabulares
- **Búsqueda global**: Cmd+K — proyectos, tareas, clientes, tickets en tiempo real
- **Búsqueda semántica**: embeddings con sentence-transformers, motor vectorial
- **Centro de notificaciones**: campana con badge, refresh cada 30s, marcar como leído

### 4.6 Empresa y gobernanza

- **Multi-organización**: soporte para múltiples empresas/tenants
- **Roles granulares**: `admin`, `pm`, `team_lead`, `hr`, `employee`, `subcontractor`
- **Permisos por proyecto**: visibilidad configurable a nivel de proyecto
- **GRC**: Governance, Risk and Compliance — políticas, controles, auditorías
- **Portfolios**: agrupación de proyectos, análisis agregado
- **Automations engine**: reglas if/then configurables (trigger + acción)
- **Webhooks**: outbound + log de llamadas
- **MFA/2FA**: TOTP con QR code (pyotp + compatible Google Authenticator)
- **Firma electrónica**: DocuSign / AdobeSign integration
- **Microsoft 365**: Calendar sync + Teams notifications (Graph API)

---

## 5. Modelo de datos

### Modelos principales

| Modelo / Archivo | Tablas principales |
|-----------------|-------------------|
| `user.py` | `users` (roles, MFA, SSO, refresh_token_jti) |
| `project.py` | `projects`, `project_phases`, `project_members` |
| `task.py` | `tasks`, `task_comments`, `task_attachments` |
| `imputation.py` | `imputations`, `timer_sessions`, `imputation_alerts` |
| `resources.py` | `deliverables`, `resource_alerts`, `resource_snapshots` |
| `financial.py` | `invoices`, `project_milestones`, `revenue_recognition_rules`, `expenses` |
| `client_portal.py` | `client_users`, `client_portal_configs`, `client_documents`, `feature_requests`, `uat_sessions`, `client_messages`, `client_surveys` |
| `service_desk.py` | `sd_tickets`, `sd_comments`, `sd_kb_articles`, `cmdb_assets`, `sla_calendars` |
| `sprints.py` | `sprints`, `sprint_items` |
| `clients.py` | `clients`, `client_contacts` |
| `contracts.py` | `contracts`, `contract_milestones` |
| `pipeline.py` | `opportunities`, `pipeline_stages` |
| `okrs.py` | `okr_objectives`, `okr_key_results`, `okr_check_ins` |
| `alert.py` | `alerts`, `alert_rules` |
| `documents.py` | `documents`, `document_versions`, `document_permissions`, `document_tags` |
| `automations.py` | `automation_rules`, `automation_logs` |
| `enterprise.py` | `organizations`, `sso_configs` |
| `performance.py` | `performance_reviews`, `review_cycles` |
| `training.py` | `training_plans`, `training_courses` |
| `esign.py` | `esign_requests`, `esign_signatures` |
| `git_integration.py` | `git_repos`, `git_commits`, `git_prs` |
| `nps.py` | `nps_surveys`, `nps_responses` |
| `portfolio.py` | `portfolios`, `portfolio_projects` |
| `semantic_engine.py` | `document_embeddings`, `embedding_configs` |

### Relaciones clave

```
Organization ─── Users ──── Projects ──── Tasks
                               │             │
                             Clients      Sprints
                               │             │
                          ClientUsers    Imputations
                    (portal access)
```

---

## 6. API — Endpoints

La API completa está disponible en `/api/v1`. Documentación interactiva en **`http://localhost:8000/api/v1/docs`** (Swagger UI) y **`/api/v1/redoc`**.

### Autenticación

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/auth/login` | Login local — emite access_token + refresh_token (cookies httpOnly + body) |
| POST | `/auth/refresh` | Renueva tokens (acepta cookie o body) |
| POST | `/auth/logout` | Cierra sesión, elimina cookies httpOnly |
| GET | `/auth/me` | Usuario autenticado actual |
| GET | `/auth/sso/providers` | Proveedores SSO activos |
| GET | `/auth/sso/{id}/authorize` | URL de autorización OIDC |
| POST | `/auth/sso/{id}/callback` | Callback OIDC — intercambio de código |
| POST | `/auth/mfa/setup` | Iniciar configuración 2FA (genera TOTP secret) |
| POST | `/auth/mfa/verify` | Verificar código TOTP |
| POST | `/auth/mfa/disable` | Deshabilitar 2FA |
| POST | `/auth/change-password` | Cambiar contraseña |

### Módulos de API

| Prefijo | Módulo | Archivo |
|---------|--------|---------|
| `/users` | Gestión de usuarios | `users.py` |
| `/projects` | Proyectos | `projects.py` |
| `/tasks` | Tareas | `tasks.py` |
| `/imputations` | Imputación de horas | `imputations.py` |
| `/timesheets` | Timesheets semanales | `timesheets.py` |
| `/resources` | Recursos y entregas | `resources.py` |
| `/capacity` | Capacidad y forecast | `capacity.py` |
| `/resource-forecast` | Forecast de recursos | `resource_forecast.py` |
| `/sprints` | Gestión de sprints | `sprints.py` |
| `/clients` | Clientes y contactos | `clients.py` |
| `/contracts` | Contratos | `contracts.py` |
| `/pipeline` | Pipeline CRM | `pipeline.py` |
| `/invoices` | Facturación | (en financial) |
| `/milestones` | Hitos SOW | `milestones.py` |
| `/rate-cards` | Rate Cards | `rate_cards.py` |
| `/profitability` | Rentabilidad | `profitability.py` |
| `/expenses` | Gastos | `expenses.py` |
| `/risks` | Riesgos | `risks.py` |
| `/changes` | Control de cambios | `changes.py` |
| `/deliverables` | Entregables | `deliverables.py` |
| `/okrs` | OKRs | `okrs.py` |
| `/service-desk` | Service Desk ITSM | `service_desk.py` |
| `/documents` | Gestión documental | `documents.py` |
| `/alerts` | Alertas automáticas | `alerts.py` |
| `/approvals` | Flujos de aprobación | `approvals.py` |
| `/automations` | Motor de automatización | `automations.py` |
| `/skills` | Habilidades | `skills.py` |
| `/absences` | Ausencias | `absences.py` |
| `/training` | Formación | `training.py` |
| `/performance` | Revisiones de desempeño | `performance.py` |
| `/analytics` | Analítica y reporting | `analytics.py` |
| `/report-builder` | Constructor de informes | `report_builder.py` |
| `/dashboard` | KPIs dashboard | `dashboard.py` |
| `/portfolio` | Portfolios | (en endpoints) |
| `/esign` | Firma electrónica | `esign.py` |
| `/git` | Integración GitHub/GitLab | `git_integration.py` |
| `/m365` | Microsoft 365 | `m365.py` |
| `/nps` | NPS / CSAT | `nps.py` |
| `/enterprise` | Config. enterprise | `enterprise.py` |
| `/settings` | Configuración global | `settings.py` |
| `/ai-providers` | Proveedores IA | `ai_providers.py` |
| `/semantic-engine` | Motor semántico | `semantic_engine.py` |
| `/accounting` | Contabilidad hub | `accounting_hub.py` |
| `/integrations` | Integraciones externas | `integrations.py` |
| `/client-portal` | Portal de cliente | `client_portal.py` |
| `/ws` | WebSocket (tiempo real) | `ws.py` |

---

## 7. Seguridad

### Autenticación y tokens

- **Access token**: JWT firmado con HS256, expiración configurable (15-60 min recomendado para producción)
- **Refresh token**: JWT con JTI único almacenado en BD, rotación en cada refresh. Expiración recomendada: 7 días
- **Almacenamiento**: `httpOnly` cookies (SameSite=Lax, Secure en producción). El servidor acepta también `Authorization: Bearer` para compatibilidad con clientes API
- **Cookie de acceso**: path `/` — se envía en todas las peticiones
- **Cookie de refresh**: path `/api/v1/auth/refresh` — solo se envía al endpoint de refresh

### Autenticación WebSocket / SSE

Los endpoints WebSocket y SSE no admiten cookies httpOnly de forma nativa en todos los entornos. Se usa un sistema de **tickets de un solo uso**:

1. El cliente autenticado llama `GET /ws/ticket` (autenticación por cookie normal)
2. El servidor genera un token opaco de 60 segundos de validez, almacenado en Redis
3. El cliente conecta a `ws://host/ws?ticket=<token>` — el ticket se consume inmediatamente
4. Las URLs de documentos se sirven directamente (same-origin cookies), sin token en URL

Este mecanismo evita exponer el JWT de acceso como query param en la URL (quedaría en logs del servidor).

### Límites de subida de ficheros

| Endpoint | Límite | Motivo |
|----------|--------|--------|
| `POST /ai/voice/transcribe` | **25 MB** | Límite de la API Whisper de OpenAI |
| `POST /expenses/{id}/receipt` | 10 MB | Tamaño práctico de justificantes |
| `POST /documents/` | `MAX_FILE_SIZE_MB` (100 MB default) | Configurable vía env |
| `POST /import/validate`, `/import/execute` | **5 MB** | Previene DoS con CSV masivos |

### Robustez del key ring JWT

El key ring interno (`app/services/key_management.py`) usa `RuntimeError` en lugar de `assert` para señalizar que las claves no están inicializadas. El motivo: Python puede ejecutarse con el flag `-O` (optimizer), que **elimina silenciosamente** todos los `assert`, dejando la aplicación en un estado inválido sin error visible.

### Cifrado de datos sensibles en BD

- **Formato v2**: `v2:<base64url(16-byte-random-salt)>.<fernet-token>`
- **Derivación de clave**: HKDF-SHA256 con salt aleatorio por registro (32 bytes). Ningún registro comparte la clave de cifrado
- **Retrocompatibilidad**: valores sin prefijo `v2:` se descifran con la clave global legacy (v1)

### Contraseñas

- bcrypt con factor de coste automático
- Longitud mínima configurable (`MIN_PASSWORD_LENGTH`, default 8)

### Rate Limiting

- `/auth/login`: 5 peticiones/minuto por IP (slowapi)
- Configurable por endpoint con `@limiter.limit()`

### MFA / 2FA

- TOTP estándar (RFC 6238) — compatible con Google Authenticator, Authy, etc.
- QR code generado via `api.qrserver.com`
- Activación/desactivación con verificación de código actual
- `mfa_challenge_token` de login con JWT corto + persistencia one-time en `mfa_challenges`
- Un challenge MFA consumido ya no puede reutilizarse para completar otro login

### SSO / OIDC

- Azure AD, Okta, Google, OIDC genérico
- Validación de `state` con HMAC-SHA256 (prevención CSRF)
- Verificación de firma del `id_token` vía JWKS (PyJWT)
- Email verificado requerido (`email_verified != false`)
- Provisioning automático de usuarios SSO solo si la configuración tiene `organization_id`
- El alta automática hereda `default_role` y el tenant definido en la configuración SSO

### Headers de seguridad

Aplicados en middleware a todas las respuestas:
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Content-Security-Policy: (configurado en nginx)
```

### CORS

- Orígenes permitidos configurados en `ALLOWED_ORIGINS`
- `allow_credentials: true` necesario para envío de cookies
- Métodos: GET, POST, PUT, PATCH, DELETE, OPTIONS

### Control de acceso

```python
# Dependencias de rol disponibles en app/core/deps.py
require_admin                  # solo admin
require_admin_or_hr            # admin o RRHH
require_admin_or_pm            # admin o PM
```

### Aislamiento multitenant y ABAC

- Todo endpoint que liste o lea datos de negocio debe filtrar por `organization_id` de forma explícita o a través de la relación con `Project.organization_id`
- Los endpoints de usuarios, tareas, mapas de carga y vistas derivadas no deben exponer registros de otras organizaciones aunque el rol sea `admin`, `pm` o `hr`
- ABAC existe como segunda capa sobre RBAC: para endpoints sensibles debe llamarse `enforce_abac(...)` además del guardado por rol
- Regla práctica: `RBAC` decide si el usuario puede entrar en el módulo; `tenant scoping` decide qué filas puede ver; `ABAC` decide si la acción concreta está permitida
require_any_manager            # admin, pm, team_lead, hr
require_internal_user          # todos menos subcontractor
get_current_client             # portal de cliente (cookie o header)
```

---

## 8. Variables de entorno

Copia `.env.example` a `.env` y personaliza los valores. **Nunca** incluyas `.env` en el repositorio.

### Obligatorias

| Variable | Descripción |
|----------|-------------|
| `SECRET_KEY` | Clave JWT. Genera con `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | SQLite (`sqlite:///./clarive.db`) o PostgreSQL (`postgresql://user:pass@host:5432/db`) |
| `SUPERADMIN_EMAIL` | Email del superadministrador inicial |
| `SUPERADMIN_PASSWORD` | Contraseña del superadministrador |
| `CLIENT_PORTAL_SECRET` | Clave de firma para tokens del portal de cliente. Generar igual que SECRET_KEY |

### Base de datos

| Variable | Default | Descripción |
|----------|---------|-------------|
| `DATABASE_URL` | — | URL de conexión |

### Seguridad y tokens

| Variable | Default | Descripción |
|----------|---------|-------------|
| `SECRET_KEY` | — | **Requerida**. Mínimo 32 caracteres |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Expiración del access token (15-60 min recomendado para producción) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Expiración del refresh token (7 días recomendado; máx. 30) |
| `WEBHOOK_SECRET` | `""` | Para verificar webhooks entrantes. Obligatorio en `staging` y `production`; mínimo 24 caracteres |
| `INBOUND_EMAIL_SECRET` | `""` | Header `X-Clarive-Email-Secret` para relay de email. Obligatorio en `staging` y `production`; mínimo 24 caracteres |
| `GITHUB_WEBHOOK_SECRET` | `""` | Secret para webhooks de GitHub |
| `GITLAB_WEBHOOK_SECRET` | `""` | Secret para webhooks de GitLab |
| `MIN_PASSWORD_LENGTH` | `8` | Longitud mínima de contraseña |
| `TRUST_PROXY_HEADERS` | `false` | Solo acepta `X-Forwarded-For`/`X-Real-IP` cuando la petición llega desde un proxy confiable |
| `TRUSTED_PROXY_CIDRS` | `127.0.0.1/32,::1/128` | CIDRs de proxies autorizados a inyectar headers de IP real |

### CORS y URLs

| Variable | Default | Descripción |
|----------|---------|-------------|
| `ALLOWED_ORIGINS` | `["http://localhost:3000","http://localhost:5173"]` | Lista JSON de orígenes CORS |
| `BASE_URL` | `http://localhost:8000` | URL base del backend |
| `FRONTEND_URL` | `http://localhost:5173` | URL del frontend |
| `VITE_API_URL` | `http://localhost:8000/api/v1` | URL de API para el frontend (variable Vite) |

### Almacenamiento

| Variable | Default | Descripción |
|----------|---------|-------------|
| `PDF_STORAGE_PATH` | `./storage/pdfs` | Ruta local para PDFs |
| `AWS_S3_BUCKET` | `nexuspm-documents` | Bucket S3 (vacío = usa filesystem local) |
| `AWS_REGION` | `eu-west-1` | Región AWS |
| `AWS_ACCESS_KEY` | `""` | Access key AWS |
| `AWS_SECRET_KEY` | `""` | Secret key AWS |
| `S3_URL_EXPIRATION_HOURS` | `24` | Expiración de URLs pre-firmadas S3 |
| `MAX_FILE_SIZE_MB` | `100` | Tamaño máximo de fichero en MB |

### Notificaciones

| Variable | Default | Descripción |
|----------|---------|-------------|
| `SLACK_WEBHOOK_URL` | `""` | Webhook de Slack para alertas |
| `NOTIFICATION_EMAIL_FROM` | `alerts@nexuspm.local` | Remitente de emails de alerta |
| `TEAMS_WEBHOOK_URL` | `""` | Webhook de Microsoft Teams |

### SSO / OAuth

| Variable | Default | Descripción |
|----------|---------|-------------|
| `ALLOW_LOCAL_LOGIN` | `true` | Habilitar login con usuario/contraseña local |
| `MICROSOFT_OAUTH_BASE` | `https://login.microsoftonline.com` | Base URL Azure AD |
| `GOOGLE_OAUTH_BASE` | `https://accounts.google.com` | Base URL Google |
| `GOOGLE_TOKEN_URL` | `https://oauth2.googleapis.com/token` | Token endpoint Google |

### Microsoft 365

| Variable | Default | Descripción |
|----------|---------|-------------|
| `AZURE_TENANT_ID` | `""` | Tenant ID Azure AD |
| `AZURE_CLIENT_ID` | `""` | Client ID app Azure |
| `AZURE_CLIENT_SECRET` | `""` | Client secret app Azure |
| `M365_CALENDAR_SYNC_ENABLED` | `false` | Activar sincronización de calendarios |
| `M365_TEAMS_NOTIFICATIONS_ENABLED` | `false` | Activar notificaciones Teams |

### Firma electrónica

| Variable | Default | Descripción |
|----------|---------|-------------|
| `DOCUSIGN_INTEGRATION_KEY` | `""` | Integration key DocuSign |
| `DOCUSIGN_SECRET_KEY` | `""` | Secret key DocuSign |
| `DOCUSIGN_ACCOUNT_ID` | `""` | Account ID DocuSign |
| `DOCUSIGN_BASE_URL` | `https://demo.docusign.net/restapi` | URL DocuSign (demo/prod) |
| `ADOBE_SIGN_CLIENT_ID` | `""` | Client ID Adobe Sign |
| `ADOBE_SIGN_CLIENT_SECRET` | `""` | Client secret Adobe Sign |
| `ADOBE_SIGN_BASE_URL` | `https://api.na1.adobesign.com/api/rest/v6` | URL Adobe Sign |

### IA (proveedores)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `NEXUS_AI_MODEL` | `claude-haiku-4-5` | Modelo IA por defecto |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1` | URL Anthropic Claude |
| `OPENAI_API_URL` | `https://api.openai.com/v1` | URL OpenAI |
| `GEMINI_API_URL` | `https://generativelanguage.googleapis.com/v1beta` | URL Gemini |
| `DEEPSEEK_API_URL` | `https://api.deepseek.com/v1` | URL DeepSeek |
| `GROQ_API_URL` | `https://api.groq.com/openai/v1` | URL Groq |
| `MISTRAL_API_URL` | `https://api.mistral.ai/v1` | URL Mistral |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL Ollama (local) |
| `AZURE_OPENAI_API_URL` | `https://YOUR_RESOURCE.openai.azure.com/openai` | URL Azure OpenAI |

### Contabilidad

| Variable | Default | Descripción |
|----------|---------|-------------|
| `XERO_API_BASE` | `https://api.xero.com/api.xro/2.0` | URL Xero |
| `QB_API_BASE` | `https://quickbooks.api.intuit.com/v3/company` | URL QuickBooks |

### Reglas de negocio

| Variable | Default | Descripción |
|----------|---------|-------------|
| `DEFAULT_TIMEZONE` | `Europe/Madrid` | Zona horaria por defecto |
| `DEFAULT_LANGUAGE` | `es` | Idioma por defecto |
| `DEFAULT_CURRENCY` | `EUR` | Moneda por defecto |
| `DEFAULT_TAX_RATE` | `21.0` | IVA por defecto (%) |
| `DEFAULT_WORKING_HOURS_PER_DAY` | `8.0` | Horas laborables/día |
| `DEFAULT_WEEKLY_CAPACITY_HOURS` | `40.0` | Capacidad semanal |
| `DEFAULT_VACATION_DAYS_PER_YEAR` | `23` | Días de vacaciones/año |
| `DEFAULT_IMPUTATION_LOCKOUT_DAYS` | `14` | Días retroactivos permitidos para imputar |

### SLA (Service Desk)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `SLA_P1_RESPONSE_HOURS` | `1.0` | SLA respuesta prioridad crítica |
| `SLA_P1_RESOLUTION_HOURS` | `4.0` | SLA resolución prioridad crítica |
| `SLA_P2_RESPONSE_HOURS` | `4.0` | SLA respuesta prioridad alta |
| `SLA_P2_RESOLUTION_HOURS` | `8.0` | SLA resolución prioridad alta |
| `SLA_P3_RESPONSE_HOURS` | `8.0` | SLA respuesta prioridad media |
| `SLA_P3_RESOLUTION_HOURS` | `24.0` | SLA resolución prioridad media |
| `SLA_P4_RESPONSE_HOURS` | `24.0` | SLA respuesta prioridad baja |
| `SLA_P4_RESOLUTION_HOURS` | `72.0` | SLA resolución prioridad baja |

### Infraestructura

| Variable | Default | Descripción |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | URL Redis (Celery + caché) |
| `SENTRY_DSN` | `""` | DSN Sentry para error tracking |
| `SENTRY_ENVIRONMENT` | `development` | Entorno para Sentry |
| `ENVIRONMENT` | `development` | `development` o `production` (afecta Secure cookie) |
| `HTTP_PORT` | `80` | Puerto HTTP (docker-compose) |
| `HTTPS_PORT` | `443` | Puerto HTTPS (docker-compose) |
| `POSTGRES_DB` | `clarive` | Nombre de BD PostgreSQL (docker) |
| `POSTGRES_USER` | `clarive` | Usuario PostgreSQL (docker) |
| `POSTGRES_PASSWORD` | — | Contraseña PostgreSQL (docker) |

### MFA / QR

| Variable | Default | Descripción |
|----------|---------|-------------|
| `QR_SERVICE_URL` | `https://api.qrserver.com/v1/create-qr-code` | Servicio de generación de QR |

---

## 9. Instalación y arranque rápido

### Prerrequisitos

- Python 3.12+
- Node.js 18+
- (Producción) PostgreSQL 16, Redis 7

### Desarrollo local (SQLite)

```bash
# 1. Clonar y entrar al directorio
git clone <repo> nexuspm_v23
cd nexuspm_v23

# 2. Copiar y configurar variables de entorno
cp .env.example .env
# Editar .env: configurar SECRET_KEY, SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD, CLIENT_PORTAL_SECRET

# 3. Backend
python3 -m venv venv
source venv/bin/activate          # macOS/Linux
# venv\Scripts\activate           # Windows

pip install -r requirements.txt

# 4. Frontend
cd frontend
npm install
cd ..

# 5. Arrancar (script unificado)
chmod +x start.sh && ./start.sh
```

El script `start.sh` lanza el backend (uvicorn en puerto 8000) y el frontend (Vite en puerto 5173) en paralelo.

### URLs de acceso (desarrollo)

| Servicio | URL |
|----------|-----|
| Frontend | http://localhost:5173 |
| Portal cliente | http://localhost:5173/portal |
| API | http://localhost:8000/api/v1 |
| Swagger UI | http://localhost:8000/api/v1/docs |
| ReDoc | http://localhost:8000/api/v1/redoc |

### Scripts disponibles

| Script | Descripción |
|--------|-------------|
| `./start.sh` | Arranca backend + frontend en modo desarrollo |
| `./setup.sh` | Configuración inicial completa (venv + npm install + seed BD) |
| `./clean_and_start.sh` | Limpia BD y reinicia con datos semilla frescos |
| `make test` | Ejecuta suite de tests backend |
| `make lint` | ESLint frontend |

---

## 10. Despliegue en producción (Docker)

### Preparación

```bash
# 1. Crear archivo de entorno de producción
cp .env.example .env
# Configurar TODOS los valores marcados como obligatorios
# Especialmente: SECRET_KEY, CLIENT_PORTAL_SECRET, DATABASE_URL (postgresql://...)
# ENVIRONMENT=production  <-- activa Secure cookie y otros ajustes de producción

# 2. Generar claves seguras
python3 -c "import secrets; print(secrets.token_hex(32))"  # para SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"  # para CLIENT_PORTAL_SECRET

# 3. (Opcional) Build de imágenes personalizadas
docker compose build

# 4. Arrancar todo el stack
docker compose up -d

# 5. Verificar estado
docker compose ps
docker compose logs backend --tail 50
```

### Servicios Docker

| Servicio | Imagen | Puerto interno | Descripción |
|----------|--------|----------------|-------------|
| `backend` | Dockerfile | 8000 | API FastAPI |
| `frontend` | frontend/Dockerfile.prod | 80 | React + Nginx |
| `nginx` | nginx:alpine | 80, 443 | Reverse proxy principal |
| `db` | postgres:16-alpine | 5432 | PostgreSQL |
| `redis` | redis:7-alpine | 6379 | Caché + broker Celery |
| `worker` | Dockerfile | — | Celery worker |

### Configuración Nginx (producción)

```nginx
# nginx/conf.d/default.conf
server {
    listen 80;
    server_name _;

    # Frontend React SPA
    location / {
        proxy_pass http://frontend:80;
    }

    # Backend API
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket
    location /ws {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Despliegue continuo (CI/CD)

Ver sección [13. CI/CD](#13-cicd) para el pipeline completo.

### Actualización de versión

```bash
# Pull de nueva versión
git pull origin main

# Reconstruir imágenes
docker compose build

# Reiniciar con zero-downtime (si hay réplicas)
docker compose up -d --no-deps backend frontend

# Aplicar migraciones (se ejecutan automáticamente al arrancar el backend)
# Si quieres ejecutarlas manualmente:
docker compose exec backend alembic upgrade head
```

---

## 11. Migraciones de base de datos

Clarive usa **Alembic** como fuente de verdad para las migraciones. Al arrancar el backend, se ejecuta automáticamente `alembic upgrade head`.

- `Base.metadata.create_all()` no se usa en runtime de aplicación
- El backend ya no hace fallback a `app.db.migrate.run()` en startup: si Alembic falla, el arranque falla también
- En tests o despliegues con init-container, las migraciones pueden omitirse con `TESTING=1` o `SKIP_STARTUP_MIGRATIONS=1`

### Cadena de migraciones

```
001_initial_tables                    → baseline (no-op, marca el punto de inicio)
002_incremental                       → ALTER TABLE ADD COLUMN (idempotente, sin perder datos)
003_document_management               → tablas de gestión documental
004_v24_features                      → timezone por usuario, facturación recurrente, formularios públicos, OAuth apps
005_security_hardening                → expansión de columnas cifradas, bloqueo de imputaciones en proyectos cerrados
006_webauthn_passkeys                 → soporte WebAuthn / passkeys
007_user_sessions_panel               → panel de sesiones activas de usuario
008_governance_scim_policy_compliance → modelos de governance, SCIM provisioning, políticas de compliance
009_abac_fine_grained_auth            → ABAC (Attribute-Based Access Control)
010_security_observability            → SOC event log, detecciones de amenazas
011_ai_governance_guardrails          → políticas de guardrails IA y audit logs
012_sem_config_priority_thresholds    → umbrales semánticos por prioridad de issue
013_sem_config_threshold_calibration  → calibración de umbrales del motor semántico
014_ai_providers                      → tablas de proveedores IA multi-proveedor y multi-tenant
015_multitenant_org_isolation         → aislamiento por organización en tabla de proyectos
016_task_status_in_review             → nuevo estado in_review en tareas
017_mfa_sso_hardening                 → replay protection MFA + tenant binding en SSO
018_drop_user_refresh_token_jti       → eliminación de columna obsoleta jti en refresh tokens
019_client_user_multiproject          → tabla puente client_user_projects (portal multi-proyecto)
020_tenant_scope_ai_providers         → org_id en ai_providers y rate_tables para aislamiento tenant
```

### Comandos útiles

```bash
# Aplicar todas las migraciones pendientes
alembic upgrade head

# Ver estado actual
alembic current

# Ver historial
alembic history --verbose

# Crear nueva migración (desde el estado del modelo SQLAlchemy)
alembic revision --autogenerate -m "descripción del cambio"

# Revertir una migración
alembic downgrade -1
```

### Crear una nueva migración

```bash
# 1. Modificar o crear el modelo en app/models/
# 2. Generar la migrations
source venv/bin/activate
alembic revision --autogenerate -m "nombre_descriptivo"

# 3. Revisar el archivo generado en alembic/versions/
# 4. Aplicar
alembic upgrade head
```

### Helper idempotente

La migración `002_incremental.py` usa un helper que previene errores si la columna ya existe:

```python
def _add_column(table: str, col: sa.Column) -> None:
    try:
        op.add_column(table, col)
    except Exception as e:
        if "duplicate column" not in str(e).lower() and "already exists" not in str(e).lower():
            raise
```

---

## 12. Tests

### Ejecución

```bash
# Activar venv primero
source venv/bin/activate

# Variables mínimas necesarias para los tests
export CLIENT_PORTAL_SECRET=test
export SECRET_KEY=test

# Ejecutar todos los tests
python -m pytest tests/ -q

# Con verbose (ver nombres de tests)
python -m pytest tests/ -v

# Un módulo concreto
python -m pytest tests/test_auth.py -v

# Con reporte de cobertura
python -m pytest tests/ --cov=app --cov-report=html

# Parar al primer fallo
python -m pytest tests/ -x
```

### Cobertura actual

- **1.182 tests totales** en la suite backend principal (8 módulos nuevos añadidos en el ciclo actual de cobertura de negocio)
- Resultado validado: **1.047+ passed, 11 skipped** (suite completa, sin regressions)
- Los 8 nuevos módulos añaden **134 tests** con cobertura de dominios previamente sin cobertura
- Tiempo de ejecución completa: ~18–20 minutos

### Módulos de test

| Archivo | Descripción |
|---------|-------------|
| `test_auth.py` | Login, logout, refresh, MFA, SSO, cookies de refresh; incluye regressions de replay MFA, IP real confiable y secretos operativos |
| `test_users.py` | CRUD usuarios, roles, permisos |
| `test_tenant_isolation.py` | Aislamiento por organización en usuarios, tareas y mapas de carga |
| `test_projects.py` | Proyectos, fases, miembros |
| `test_tasks.py` | Tareas, comentarios, asignación |
| `test_timesheets.py` | Timesheets, aprobación |
| `test_imputations.py` | Imputación de horas, timer |
| `test_service_desk.py` | Tickets, SLA, KB, CMDB |
| `test_contracts.py` | Contratos, renovación |
| `test_risks.py` | Riesgos, scoring |
| `test_okrs.py` | OKRs, check-ins |
| `test_dashboard.py` | KPIs, aggregaciones |
| `test_documents.py` | Gestión documental, S3 mock |
| `test_capacity.py` | Capacidad, forecast |
| `test_profitability.py` | Márgenes, rentabilidad |
| `test_expenses.py` | Gastos, aprobación |
| `test_alerts.py` | Alertas, notificaciones |
| `test_approvals.py` | Flujos de aprobación |
| `test_automations.py` | Motor de automatizaciones |
| `test_automations_extended.py` | Automatizaciones — cobertura extendida |
| `test_sprints.py` | Sprints, velocity |
| `test_skills.py` | Skills, asignación |
| `test_absences.py` | Ausencias, aprobación |
| `test_accounting.py` | Contabilidad hub (Xero/QuickBooks) |
| `test_changes.py` | Control de cambios |
| `test_clients.py` | Clientes y contactos |
| `test_capacity_extended.py` | Capacidad — cobertura extendida |
| `test_dashboard_extended.py` | Dashboard — cobertura extendida; incluye regression anti N+1 en rentabilidad |
| `test_deliverables.py` | Entregables y UAT |
| `test_financial_core.py` | Motor financiero central |
| `test_imputations.py` | Imputación de horas |
| `test_imputations_enhanced.py` | Imputaciones — casos avanzados |
| `test_timesheets_extended.py` | Timesheets — cobertura extendida |
| `test_milestone_billing.py` | Facturación por milestones |
| `test_pipeline.py` | Pipeline CRM |
| `test_profitability_extended.py` | Rentabilidad — cobertura extendida |
| `test_rate_cards.py` | Rate Cards |
| `test_resource_forecast.py` | Forecast de recursos |
| `test_resources.py` | Recursos y entregables |
| `test_settings.py` | Configuración global |
| `test_v24_features.py` | Features v24+ (Activity Feed, @Mentions, Health Score, CPM, etc.) |
| `test_grc.py` | ✨ **NUEVO** — GRC: matriz de permisos, reglas SoD, violaciones, audit log |
| `test_nps_customer_health.py` | ✨ **NUEVO** — NPS: respuestas, resumen, puntuación de salud del cliente |
| `test_portfolio.py` | ✨ **NUEVO** — Carteras: CRUD, EVM (CPI/SPI/health), dashboard RAG |
| `test_raci.py` | ✨ **NUEVO** — RACI matrix, burnout risk, casos UAT, changelog de proyecto |
| `test_custom_fields.py` | ✨ **NUEVO** — Campos personalizados, workflow states/transitions, permisos granulares |
| `test_webhooks.py` | ✨ **NUEVO** — Webhooks: CRUD, signing HMAC-SHA256, firing logic, delivery log |
| `test_report_builder.py` | ✨ **NUEVO** — Report Builder: schema, preview, export CSV, templates |
| `test_exchange_rates.py` | ✨ **NUEVO** — Tipos de cambio: CRUD, conversión, sync ECB (mock), FX service unit |

### Tests E2E (Playwright)

```bash
cd tests_e2e
pip install playwright
playwright install chromium

pytest test_e2e_auth.py -v
pytest test_e2e_dashboard.py -v
pytest test_e2e_projects.py -v
```

---

## 13. CI/CD

La plataforma dispone de un pipeline completo en **GitHub Actions** con cuatro ficheros de workflow:

### Workflows

| Fichero | Trigger | Descripción |
|---------|---------|-------------|
| `.github/workflows/ci.yml` | Push / PR a `main`, `develop` | Pipeline de integración continua |
| `.github/workflows/cd.yml` | Push a `main`, `develop`, tags `v*.*.*` | Despliegue continuo (GHCR + SSH) |
| `.github/workflows/security.yml` | Semanal + push / PR | Escaneo de seguridad |
| `.github/dependabot.yml` | Semanal (lunes 06:00 UTC) | Actualizaciones automáticas de dependencias |

### Pipeline CI (`.github/workflows/ci.yml`)

```
on: push/PR a main, develop

Jobs:
├── lint-python
│   └── ruff check + ruff format --check
├── lint-frontend
│   └── npm ci + npm run lint
├── test-backend
│   ├── Python 3.12 + SQLite in-memory
│   ├── TESTING=1 pytest tests/ -q --cov=app
│   └── Cobertura mínima requerida: 55%
├── build-frontend
│   └── npm run build (artefacto en dist/)
├── build-docker
│   └── docker build (build check, sin push)
├── syntax-check
│   └── python -c "import app.main" + validate imports
└── ci-ok (gate)
    └── Depende de todos los jobs anteriores
```

Variables de entorno requeridas (secrets de GitHub):
- `SECRET_KEY` — clave JWT
- `CLIENT_PORTAL_SECRET` — secreto del portal cliente
- `WEBHOOK_SECRET` — secreto para webhooks salientes

### Pipeline CD (`.github/workflows/cd.yml`)

```
on:
  push a develop → staging
  push a main / tag v*.*.* → producción

Jobs:
├── resolve-env   — determina entorno (staging / production)
├── build-and-push
│   ├── Build imagen Docker backend
│   └── Push a GHCR (ghcr.io/{owner}/contecflow-backend)
├── deploy-staging  — SSH + docker compose pull + up -d
└── deploy-production — SSH + docker compose pull + up -d + alembic upgrade
```

Secrets requeridos en GitHub:
- `GHCR_TOKEN` — token con permiso `write:packages`
- `STAGING_HOST`, `STAGING_SSH_USER`, `STAGING_SSH_KEY`
- `PROD_HOST`, `PROD_SSH_USER`, `PROD_SSH_KEY`

### Escaneo de seguridad (`.github/workflows/security.yml`)

```
Jobs:
├── gitleaks        — búsqueda de secretos en historial completo
├── pip-audit       — audit de dependencias Python (con excepciones gestionadas)
├── validate-exceptions — valida que las excepciones de vulnerabilidades tengan justificación
└── codeql          — SAST estático (python + javascript-typescript)
```

Las excepciones de vulnerabilidades se gestionan en `security/vulnerability-exceptions.json` y se validan automáticamente con `scripts/validate_vulnerability_exceptions.py`.

**Política de excepciones de vulnerabilidades:**
- Cada excepción debe incluir ticket, motivo, aprobadores y fecha de expiración.
- Las excepciones caducadas fallan el CI de inmediato.
- Las excepciones son aceptación temporal de riesgo, nunca permanentes.
- Los PRs que modifican el fichero de excepciones requieren doble aprobación.
- Se requiere un aprobador de seguridad cuando esté definido en `.github/security-approvers.txt`.

### Dependabot (`.github/dependabot.yml`)

- **github-actions**: actualizaciones semanales (lunes)
- **pip** (directorio `/`): actualizaciones semanales, parches y menores agrupados
- **npm** (directorio `/frontend`): actualizaciones semanales, parches y menores agrupados
- Las actualizaciones de versión **major** están bloqueadas (requieren revisión manual)

### Ejecutar CI localmente

```bash
# Script de CI local
./scripts/ci_local.sh

# O manualmente:
source venv/bin/activate
export TESTING=1 SECRET_KEY=test CLIENT_PORTAL_SECRET=test WEBHOOK_SECRET=test
python -m pytest tests/ -q --cov=app --cov-fail-under=55

# Lint Python
ruff check app/ tests/
ruff format --check app/ tests/

# Lint Frontend
cd frontend && npm run lint
```

### Despliegue automático

```bash
# Script de despliegue a producción
./scripts/deploy.sh

# Internamente hace:
# 1. git pull
# 2. docker compose build
# 3. docker compose up -d
# 4. docker compose exec backend alembic upgrade head
# 5. Health check
```

### Auditorías de seguridad recomendadas

```bash
# Backend (dependencias Python)
source .venv/bin/activate
pip-audit

# Frontend runtime (sin devDependencies)
cd frontend
npm audit --omit=dev --audit-level=high
```

Notas:
- El riesgo residual actual puede estar en `pip` del entorno local (herramienta de build, no dependencia runtime de la API).
- Las dependencias runtime de la aplicación se validan con `pip-audit` y `npm audit --omit=dev`.
- El stack de embeddings transformer se instala de forma opcional desde `requirements-ml.txt` (no requerido para el API HTTP por defecto).

### Limpieza pre-deploy

Antes de desplegar, usa el script oficial para eliminar artefactos locales y dejar el repo listo:

```bash
./scripts/clean_deploy_artifacts.sh
```

Opciones útiles:

```bash
# Limpieza profunda local (incluye eliminar .venv y node_modules)
./scripts/clean_deploy_artifacts.sh --full-local

# Limpiar además uploads/documents locales
./scripts/clean_deploy_artifacts.sh --purge-uploads

# Ambas opciones a la vez
./scripts/clean_deploy_artifacts.sh --full-local --purge-uploads
```

El modo por defecto elimina, entre otros:
- caches (`__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.cache`)
- reportes de test/cobertura (`playwright-report`, `test-results`, `htmlcov`, `.coverage*`, `coverage.xml`, `junit*.xml`)
- temporales y logs (`*.tmp`, `*.log`, `.DS_Store`, `npm-debug.log*`, `yarn-error.log*`)
- artefactos frontend (`frontend/dist`)
- base de datos local de desarrollo (`clarive.db`, `clarive_legacy.db`)

---

## 14. Usuarios y roles

### Roles disponibles

| Rol | Nivel | Descripción |
|-----|-------|-------------|
| `admin` | 1 | Acceso total. Gestiona usuarios, configuración, organización |
| `pm` | 2 | Project Manager. Gestiona proyectos, recursos, presupuestos |
| `team_lead` | 3 | Líder técnico. Aprueba timesheets, gestiona equipo |
| `hr` | 3 | RRHH. Gestiona ausencias, formación, revisiones de desempeño |
| `employee` | 4 | Empleado estándar. Imputa horas, ve sus proyectos |
| `subcontractor` | 5 | Externo limitado. Solo imputa horas en proyectos asignados |

### Usuarios de prueba (datos semilla)

| Usuario | Contraseña | Rol | Descripción |
|---------|------------|-----|-------------|
| `admin` | `clarive2024!` | admin | Superadministrador |
| `ana.torres` | `clarive2024!` | pm | Project Manager senior |
| `luis.vega` | `clarive2024!` | employee | Developer, L1 Helpdesk |
| `sara.lope` | `clarive2024!` | employee | DevOps, L2 técnico |
| `rrhh` | `clarive2024!` | hr | Responsable de RRHH |

### Permisos por acción (ejemplos)

| Acción | admin | pm | team_lead | hr | employee | subcontractor |
|--------|-------|----|-----------|----|----------|---------------|
| Crear usuarios | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Crear proyectos | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Ver todos los proyectos | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| Imputar horas | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Aprobar timesheets | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| Ver rentabilidad | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Gestionar ausencias | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Configuración empresa | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

⚠️ = Solo proyectos en los que tiene acceso

---

## 15. Portal de cliente externo

El portal es una experiencia completamente separada, accesible en `/portal`, para usuarios de tipo `ClientUser` (no `User`).

### Acceso y autenticación

- URL: `http://localhost:5173/portal`
- Login con email + contraseña (cuenta `ClientUser`, no `User`)
- Token httpOnly cookie `portal_access_token` (separado del token de empleados)
- Endpoint: `POST /api/v1/client-portal/auth/login`

### Funcionalidades disponibles al cliente

| Módulo | Descripción | Permiso requerido |
|--------|-------------|-------------------|
| Dashboard | KPIs del proyecto: entregables, UATs, tickets, presupuesto | — |
| Proyectos / hoja de ruta | Estado del proyecto, fases, milestones | — |
| UAT | Gestionar sesiones de pruebas de aceptación | `can_approve_deliverables` |
| Feature Requests | Solicitar nuevas funcionalidades | `can_request_changes` |
| Service Desk | Abrir y seguir tickets de soporte | — |
| Mensajería | Canal de mensajes con el equipo | — |
| Documentos | Acceso a documentos compartidos | — |
| Encuestas | Responder encuestas NPS/CSAT | — |
| Presupuesto | Ver budget y % consumido | `can_view_budget` |
| Equipo | Ver quién trabaja en el proyecto | `can_view_team` |

### Configuración del portal por proyecto

Un admin puede configurar qué funcionalidades activa para cada cliente en `ClientPortalConfig`:
- `allow_uat`, `allow_feature_requests`, `allow_service_desk`, `allow_messaging`
- `allow_documents`, `allow_surveys`, `allow_roadmap`
- `custom_logo_url`, `primary_color` (white-label)
- `allow_profile_edit` (si el cliente puede editar sus datos)

### Crear un usuario de portal

```bash
# Via API (requiere admin o pm)
POST /api/v1/client-portal/users
{
  "email": "cliente@empresa.com",
  "full_name": "Nombre Cliente",
  "password": "Password123!",
  "project_id": "<uuid del proyecto>",
  "can_approve_deliverables": true,
  "can_request_changes": true,
  "can_view_budget": false,
  "can_view_team": true
}
```

---

## 16. Integraciones externas

### Microsoft 365 / Azure AD

- **Calendar sync**: sincronización bidireccional de tareas/eventos con calendarios de Outlook
- **Teams notifications**: alertas enviadas a canales Microsoft Teams vía incoming webhook
- **Azure AD SSO**: login con cuenta corporativa Microsoft
- Requiere: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`

### GitHub / GitLab

- Webhooks de commits, pull requests, issues
- Vinculación de commits a tareas (por referencia en el mensaje de commit)
- Vista de actividad de repositorio en el proyecto
- Requiere: `GITHUB_WEBHOOK_SECRET` / `GITLAB_WEBHOOK_SECRET`

### DocuSign / AdobeSign

- Solicitud de firma sobre documentos del proyecto
- Estado de firma en tiempo real (webhook)
- Descarga de documentos firmados
- Requiere: `DOCUSIGN_*` / `ADOBE_SIGN_*`

### Contabilidad (Xero / QuickBooks)

- Sincronización de facturas con el sistema contable
- Importación de gastos
- Conciliación automática
- Requiere configuración de OAuth en el hub de contabilidad (`/accounting`)

### Slack

- Notificaciones de alertas, SLA breaches, aprobaciones pendientes
- Requiere: `SLACK_WEBHOOK_URL`

### IA (AI Hub)

Configurable desde `/settings` → IA Providers. Soporta:

| Proveedor | Variable de API key | Modelos |
|-----------|---------------------|---------|
| Anthropic | configurado en BD | Claude 3.5 Haiku, Claude 3.5 Sonnet, Claude 3 Opus |
| OpenAI | configurado en BD | GPT-4o, GPT-4o-mini, GPT-4-turbo |
| Gemini | configurado en BD | Gemini 2.0 Flash, Gemini 1.5 Pro |
| Mistral | configurado en BD | Mistral Large, Mistral 7B |
| DeepSeek | configurado en BD | DeepSeek V3, DeepSeek Coder |
| Groq | configurado en BD | Llama 3.3 70B, Mixtral 8x7B |
| Ollama | `OLLAMA_BASE_URL` | Cualquier modelo local |
| Azure OpenAI | `AZURE_OPENAI_API_URL` | GPT-4o Azure |

Las API keys se almacenan cifradas en BD (Fernet v2 HKDF).

### AWS S3

- Almacenamiento de documentos del proyecto
- Si no se configura (`AWS_ACCESS_KEY` vacío), usa el filesystem local (`uploads/documents/`)
- Compatibilidad con MinIO para entornos on-premise (cambiar `AWS_S3_BUCKET` y la URL de S3)

---

## 17. Novedades por versión

### v23.10.0 (Mayo 2026) — Tests GRC/NPS/Portfolio/RACI/Webhooks/ReportBuilder, correcciones frontend y cobertura E2E

**Nuevos módulos de test — 134 tests nuevos (8 archivos)**

`tests/test_grc.py` (16 tests): cobertura completa del módulo GRC (Governance, Risk & Compliance):
- Seed y lectura de matriz de permisos por rol
- CRUD de reglas SoD (Segregación de Funciones)
- Detección y registro de violaciones SoD (`record_sod_violation`)
- Detección de auto-aprobación (`record_self_approval_violation_for_request`)
- Comprobación de cumplimiento por usuario (`/grc/sod-check`)
- Registro de auditoría GRC (`GrcAuditLog`)

`tests/test_nps_customer_health.py` (21 tests): cobertura completa de NPS y Customer Health:
- Creación y lectura de respuestas NPS por cliente
- Clasificación automática promotor / pasivo / detractor
- Cálculo de score NPS agregado (fórmula promotores–detractores)
- Cómputo del índice de salud compuesto (`compute_composite_health`)
- Snapshots de salud y lectura histórica (`/nps/{id}/health`)
- Comportamiento con cliente inexistente (HTTP 404)

`tests/test_portfolio.py` (14 tests): cobertura completa de Portfolios y EVM:
- CRUD de portfolios (`POST/GET/PATCH/DELETE /portfolios`)
- Añadir y eliminar proyectos de un portfolio; idempotencia de duplicados
- Dashboard de portfolio (`/portfolios/{id}/dashboard`) con y sin proyectos
- Cálculo EVM rápido (`get_evm_quick`): BAC, AC, pct_complete con y sin tareas
- Color de salud EVM (green/yellow/red/grey) según CPI y SPI

`tests/test_raci.py` (14 tests): cobertura completa de RACI, burnout, UAT y Changelog:
- Matriz RACI: asignar/actualizar/eliminar entradas (roles R/A/C/I)
- Burnout risk por usuario (umbral de horas semanales)
- UAT cases: crear, listar, transición de estado (pending → passed/failed/blocked)
- Project Changelog: entradas manuales, actualización, generación automática

`tests/test_report_builder.py` (20 tests): cobertura del Report Builder:
- Schema de entidades disponibles (projects, tasks, imputations, etc.)
- Preview con filtros, columnas y paginación
- Exportación CSV
- CRUD de plantillas de informe (templates)
- Validación de entidad/columna inválida

`tests/test_webhooks.py`, `tests/test_custom_fields.py`, `tests/test_exchange_rates.py`: cobertura adicional de webhooks, campos personalizados y tipos de cambio.

**Suite total actualizada: 1181 passed, 12 skipped**

**Correcciones de bugs — frontend**

- `frontend/src/pages/ImputarPage.jsx`: eliminado atributo HTML inválido `loading={isPending}` en elemento `<button>` (no es un atributo nativo; causaba warnings en consola)
- `frontend/src/services/api.js`: añadido `/auth/me` a la lista de exclusión `isAuthFlowRequest` en el interceptor de respuesta — evita bucle infinito de reintentos cuando `/auth/me` devuelve 401

---

### v23.10.0 (Abril 2026) — Corrección de bugs críticos de seguridad y lógica de negocio

**Bug #1 — `close_sprint_flow`: tareas incompletas movidas correctamente al backlog**

- `app/services/psa_flows.py`: eliminado el `db.delete(st)` para SprintTask de tareas incompletas al cerrar un sprint. Las filas SprintTask se conservan en el sprint completado para trazabilidad histórica. La función `get_project_backlog_tasks` ya excluye sólo los sprints en estado `planning`/`active`, por lo que las tareas incompletas aparecen automáticamente en el backlog una vez el sprint pasa a `completed`. Comportamiento previo: las tareas desaparecían silenciosamente del tablero y del backlog.

**Bug #2 — `stop_timer_session`: validaciones de negocio añadidas al detener el cronómetro**

- `app/services/imputation_service.py`: añadidas tres validaciones al parar un timer:
  1. **Existencia del proyecto**: si el proyecto fue eliminado mientras el timer estaba activo se devuelve 404.
  2. **Estado del proyecto**: sólo se permite registrar tiempo en proyectos `active`, `on_hold` o `paused` (igual que al crear imputaciones manualmente).
  3. **Estado de la tarea**: si la tarea ha pasado a `done` o `cancelled` mientras el timer estaba activo se devuelve 400.
  4. **Membresía al proyecto**: re-validación de pertenencia en el momento de parar, no sólo al iniciar. Un usuario eliminado del proyecto no puede registrar el tiempo del timer.

**Bug #3 — `_is_authorized`: confirmado sin admin-bypass**

- `app/services/approval_engine.py`: verificado que no existe el bypass `if role == "admin": return True`. El admin sólo puede aprobar pasos en los que esté designado explícitamente (por user_id, por rol "admin", como manager o por departamento). Comportamiento correcto mantenido.

**Bug #4 — Tenant isolation en `get_global_kpis`**

- `app/services/dashboard_service.py`: la consulta de eficiencia promedio (`efficiency_data`) no filtraba por organización. Añadido `Task.project_id.in_(active_project_ids)` para que en entornos multi-tenant un admin de una organización sólo vea la ratio de eficiencia de sus proyectos activos.

**Bug #5 — Rentabilidad v2: revenues no normalizados a divisa base**

- `app/api/v2/endpoints/profitability.py`: reescrito el endpoint v2 para normalizar `billing_revenue` a `base_currency` mediante tipos de cambio históricos antes de calcular `gross_margin` y `margin_pct`. En v1 `internal_cost` estaba en moneda base pero `billing_revenue` en la divisa del proyecto, lo que provocaba mezcla de divisas en el margen. En v2 ambas métricas están ahora en `base_currency`. Añadido campo `revenue_normalized: true` en la respuesta.

**Bug #6 — `_fx_cache` global sin uso**

- `app/services/profitability_service.py`: el dict global `_fx_cache: dict = {}` ya tenía comentario indicando que es sólo por compatibilidad hacia atrás y que nunca se muta en producción. No se tomó acción adicional — la variable es inerte.

**Bug #7 — Approval timeout: `step_started_at` nunca se inicializaba**

- `app/services/approval_engine.py`:
  - Eliminada la definición duplicada de `process_approval_timeouts` (la primera versión, más simple, nunca se ejecutaba porque Python usa la última definición). Se mantiene la versión completa que gestiona correctamente la progresión multi-paso en `auto_approve`.
  - `create_approval_request`: se establece `step_started_at = datetime.now(timezone.utc)` al crear la solicitud — sin esto el job de timeouts nunca detectaba solicitudes vencidas (filtra `step_started_at.isnot(None)`).
  - `decide_approval_request`: se resetea `step_started_at = datetime.now(timezone.utc)` al avanzar al siguiente paso, para que el timeout del nuevo paso se mida correctamente desde su activación.
  - El job Celery Beat (`process-approval-timeouts`, cada hora) y el endpoint manual `POST /api/v1/approvals/process-timeouts` ya existían y permanecen operativos.

---

### v23.9.9 (Abril 2026) — Tests de flujo E2E, correcciones Service Desk, deuda técnica y mejoras UX

**Tests de flujo de extremo a extremo**

Creado `tests/test_platform_flows.py` con **17 tests de ciclo de vida completo** (no unitarios). Suite total: **1047 passed, 11 skipped**.

Flujos cubiertos: gastos (creación→envío→aprobación→rechazo→recall), service desk (ticket→comentar→escalar→resolver→cerrar), cola de agente, control de cambios, aprobación de entregable vía portal, CRUD de proyecto + rentabilidad, riesgos (identificar→mitigar→cerrar + puntuación multi-riesgo), portal cliente (FR completo + rechazo), OKRs (objetivo→key result→check-in), ausencias (solicitud→aprobación→bloqueo capacidad), seguridad (401 sin auth + restricciones de rol).

**Corrección de bugs — Service Desk**

- `app/api/v1/endpoints/service_desk.py`: `payload.note` → `payload.description` para coincidir con el schema `TimeLogIn`
- `app/services/service_desk/ticket_ops_service.py`: `add_ticket_time()` usa parámetro `description` en lugar de `note` al crear `TicketTimeLog`

**Correcciones de lógica de negocio**

- `app/services/imputation_service.py`: tope diario de 24 h se comprueba antes que el guard de duplicado (400 antes que 409)
- `app/services/profitability_service.py`: conversión FX usa moneda del usuario (`user.currency`) en lugar de la del proyecto
- `app/schemas/timesheets.py`: `field_validator` en `submitted_at`/`reviewed_at` coerciona `datetime → date` (Pydantic v2)
- Tests: `test_numbering_concurrency` acepta 201 al crear facturas; `test_timesheets_extended` añade `dev-test-id` como miembro de proyecto

**Multi-tenancy — aislamiento real entre tenants**

- `app/core/deps.py`: `get_current_user` escribe `db.info["is_superadmin"]`; `TenantSession` aplica `sql_false()` para usuarios sin organización (antes hacía bypass)
- `app/models/activity.py`: columna `organization_id` en `ActivityEvent`
- `app/services/activity_service.py`: `emit_activity()` estampa `organization_id`
- Migración `026_activity_event_tenant_isolation.py`

**Approval workflows — timeout y escalación automática**

- `app/services/approval_engine.py`: nueva función `process_approval_timeouts(db)` que evalúa `timeout_hours` / `on_timeout` (auto_approve / reject / escalate) y traza en `FinancialApprovalAuditLog`
- `app/worker.py`: tarea Celery Beat cada hora
- Endpoint manual `POST /api/v1/approvals/process-timeouts` (solo admin)
- Migración `027_approval_step_started_at.py` con backfill conservador

**i18n — internacionalización**

- `appTranslations.js`: bloque EN completado (459 claves en 40 módulos); FR/DE/PT/IT/PL/ZH con fallback a ES/EN
- `portalTranslations.js`: 0 claves faltantes en los 8 idiomas (252 claves añadidas por idioma)
- `ImputarPage.jsx`: 100% internacionalizada con nuevo módulo `imputa_page` en ES, EN y FR
- Modelos migrados previamente: `DeveloperPortalPage`, `IntakeFormPage`, `JiraIntegrationPage`, `LoginPage`, `ProjectTemplatesPage`, `PublicFormsPage`, `ResourceSchedulerPage`

**Mejoras de UX**

- `Badge` (componente global): valores de enum en bruto (`in_progress`, `todo`, etc.) → etiquetas legibles ("In Progress", "To Do"); `aria-label`; soporte de colores para prioridades SD (`p1_critical`–`p4_low`), `in_review`, `approved`, `rejected`, `submitted`, `pending`, `resolved`, `draft`; fallback `humanize()` para valores desconocidos
- `ImputarPage`: botones editar/eliminar con `aria-label` y `title`
- `PipelinePage`: `EmptyState` cuando no hay oportunidades (guía al nuevo tenant)
- `ExecutiveDashboardPage`: spinner de carga; KPI grid `repeat(auto-fit, minmax(180px, 1fr))` en lugar de `repeat(5, 1fr)`

**Deuda técnica**

- Eliminados `scripts/_thin_auth.py`, `scripts/_thin_cab.py`, `scripts/_thin_client_portal.py` (scripts de refactorización de un solo uso)
- `tests/test_business_logic_v239.py`: `compute_composite_health` importado desde `app.services.customer_health_service` (no desde el módulo de endpoint)
- `app/.DS_Store` desregistrado del repositorio

---

### v23.9.8 (Abril 2026) — i18n Completo, Sincronización Multi-dispositivo & Transacciones Seguras

**Sistema Internacionalización (i18n) — Expansión módulo Developer**
- Creado nuevo módulo `developer` en `frontend/src/i18n/appTranslations.js`: 49 claves traducidas completamente
- Soporte para 8 idiomas: ES, EN, FR, DE, PT, IT, PL, ZH
- `DeveloperPortalPage.jsx`: migración **100% a i18n** — 45+ strings hardcoded → `t()` calls
  - AppModal: títulos, labels, placeholders, botones (crear/editar app)
  - AppDetail: modal de credenciales (Client ID, Client Secret, endpoints)
  - Main component: encabezados, estado vacío, botones de acción
- **Patrón establecido** para migración de 6 páginas adicionales (pendientes en backlog)

**Sincronización Multi-dispositivo — Preferencias de Usuario (canónico)**
- Integración completada sobre endpoints existentes: `GET/PATCH /api/v1/users/me/preferences`
- Dashboard: `DashboardPage.jsx` ahora prioriza backend (`dashboard_widgets`) y usa `localStorage` como fallback seguro
- Idioma: `AppLangContext.jsx` persiste cambios con `PATCH /users/me/preferences` y mantiene fallback local
- Campos ya soportados por backend canónico: `dashboard_widgets`, `language`, `theme_mode`, `accent_color`, `ui_density`, `sidebar_collapsed`, `extra`
- Resultado: configuración y idioma sincronizados entre dispositivos sin romper compatibilidad

**Seguridad Transaccional — Protección de 7 endpoints críticos**
- `tasks.py`: Wrapped db.commit() en try/except(IntegrityError, Exception) para:
  - `update_task`: Previene conflictos de edición concurrente
  - `cancel_task`: Validación transaccional de estado
  - `add_comment`: Rollback explícito en fallos
  - `bulk_update_dates`: Manejo de errores parciales en operaciones masivas
  - `bulk_update_tasks`: Integridad garantizada en actualizaciones bulk
  - `cascade_reschedule`: Seguridad en traversales de grafo de dependencias
  - Background task (semantic engine): Rollback en jobs en segundo plano
- **HTTP codes mejorados**:
  - IntegrityError → 409 Conflict (violación de restricción única/FK)
  - General Exception → 503 Service Unavailable (errores transitorios)
- **Logging contextual**: todos los errores registrados con user_id, operation_type, details

**Verificación Seguridad HTTP — Nginx Headers (Production-Ready)**
- ✅ Validados todos los security headers presentes en `/nginx/conf.d/clarive.conf`:
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - Referrer-Policy: strict-origin-when-cross-origin
  - Permissions-Policy: camera/microphone/geolocation deshabilitados
  - HSTS: max-age=31536000; includeSubDomains
  - CSP: comprehensive policy (self + data: para images/fonts, WSS para real-time)
- **Conclusión**: Item 10 verificado como **production-ready**, sin cambios requeridos

**Cambios Técnicos**
- Frontend:
  - `appTranslations.js`: +392 claves (49 × 8 idiomas en módulo developer)
  - `DeveloperPortalPage.jsx`: import useAppT hook + 45 string migrations
  - Migración i18n completada en 6 páginas adicionales: `IntakeFormPage.jsx`, `JiraIntegrationPage.jsx`, `LoginPage.jsx`, `ProjectTemplatesPage.jsx`, `PublicFormsPage.jsx`, `ResourceSchedulerPage.jsx`
  - `DashboardPage.jsx`: sincronización backend de `dashboard_widgets` + fallback local
  - `AppLangContext.jsx`: persistencia de idioma en backend + fallback local
- Backend:
  - `app/api/v1/endpoints/tasks.py`: 7 endpoints with transaction safety
- Database:
  - Reutilización de tabla canónica existente `user_preferences` (modelo `UserPreference`)

**Deuda Técnica Abierta (Backlog)**
- Testing: ampliar cobertura de regresión i18n multiidioma y sincronización de preferencias en escenarios de error de red

**Estadísticas de Cobertura**
- i18n pages coverage: bloque de deuda completado (7/7 páginas migradas)
- Transaction protection: 7/7 endpoints críticos de escritura
- Security headers: 6/6 validados ✅
- Multi-device sync: Backend + Frontend completado ✅

**Deployment Notes**
- No requiere migración nueva de preferencias (se usa infraestructura canónica existente)
- Backend endpoints son backward-compatible; frontend mantiene fallback a localStorage si API no disponible
- No breaking changes; recomendado deploy backend primero, luego frontend
- Nginx configuration: sin cambios requeridos (ya está correcto)

### v23.9.7 (Abril 2026) — Seguridad portal, scheduler y coherencia UX

**Portal cliente (seguridad token):**
- Eliminado el patrón de persistir `client_token` en `localStorage` en frontend.
- Portal migrado a sesión basada en cookie `httpOnly` (`portal_access_token`) con `withCredentials`.
- `get_current_client` ahora acepta cookie segura además de cabecera Bearer para compatibilidad gradual.

**Ejecución de tareas programadas en producción:**
- `docker-compose.yml` incorpora servicios `worker` y `beat` para Celery.
- Backend principal ahora arranca con `ENABLE_APSCHEDULER=0` en compose para evitar doble scheduler.
- Añadida tarea Celery de rotación programada de claves (`run_scheduled_rotation`) para mantener cobertura funcional.

**Deuda técnica de rendimiento y consistencia:**
- Corregido N+1 en `GET /projects/{id}/members` usando `joinedload(ProjectMember.user)`.
- Homogeneizadas comprobaciones de rol en NPS a enum (`UserRole.admin`, `UserRole.pm`) en lugar de strings.
- Tests de lógica SLA desacoplados de capa HTTP: ahora importan `add_working_hours` desde `app.services.sla_service`.

**Frontend QA (nuevo baseline):**
- Integrado runner `Vitest` con scripts `npm run test` / `npm run test:watch`.
- Primer set de tests unitarios en `src/utils/helpers.test.js`.
- Menú de analítica simplificado para UX coherente: una única entrada visible de dashboard ejecutivo.

### v23.9.6 (Abril 2026) — Stabilization pass (lint/tests/docs)

**Calidad de código y test suite:**
- Corregidos errores reales de lint (`F821`) detectados por Ruff en backend:
: `app/api/v1/endpoints/advanced_config.py` (import de `datetime`)
: `app/api/v1/endpoints/auth.py` (import de `UserRole`)
: `tests/test_abac_resources.py` (eliminadas aserciones inválidas con variable `res` no definida)
- Ajustado formato en `tests/test_governance_enterprise.py` (newline final de archivo) para mantener higiene del repositorio.

**Validación ejecutada:**
- Frontend i18n: `npm run check:i18n` OK (`8` idiomas, `1461` claves)
- Frontend calidad: `npm run validate:jsx` OK y `npm run lint` OK
- Backend tests críticos: `101` tests pasando (`test_abac_resources`, `test_auth`, `test_approvals`, `test_business_logic`)

**Limpieza local:**
- Eliminados artefactos temporales de ejecución (`__pycache__`, `.pytest_cache`) para mantener workspace limpio.

**Refactoring y rendimiento backend:**
- Descomposición progresiva de endpoints legacy: routers extraídos para `currency_sync`, `salesforce_sync`, `slack_block_kit` y `currency_rates`. Los routers `v238_features` y `v239_features` han sido eliminados y ya no existen como compatibilidad temporal.
- Normalización de capa de esquemas: movidos a `app/schemas/bookings.py` y `app/schemas/billing_reports.py`; test de guardia para evitar `BaseModel` inline.
- Paginación consistente en endpoints de alto volumen: `GET /sd/problems`, `GET /sd/cmdb`, `GET /sd/changes`, `GET /bi/data/timesheets` y `POST /analytics/adhoc` ahora paginados.
- Gobernanza de índices (Alembic): migración `022_perf_composite_indexes.py` con índices compuestos para tickets, cambios, problemas, tareas, imputaciones e invoices.

### v23.9.5 (Abril 2026) — Hardening UX/Frontend/CI

**Operaciones largas con feedback explícito (frontend):**
- `ImportPage`: estado visible por fase (`validating` / `importing` / `done` / `failed`) y contador de tiempo transcurrido.
- `InvoicesPage`: generación de PDF con estado por fila (botón en espera), notificación de inicio y confirmación de éxito/fallo.
- `SemanticEnginePage`: estado operativo para reconstrucción de embeddings y auto-generación de perfiles con timer visible.

**Resiliencia de carga en rutas lazy:**
- `App.jsx`: `PageErrorBoundary` ahora se resetea por cambio de ruta (`resetKey`) evitando que un fallo puntual bloquee la navegación completa.
- Botón de recarga actualizado a `window.location.reload()` estándar.

**Aprobaciones: flujo más claro para aprobador:**
- `ApprovalsPage`: cola de trabajo con filtros por tipo de entidad, orden por antigüedad/recencia y resaltado de items urgentes (`>=24h`).
- Resumen rápido por entidad para priorizar trabajo pendiente.

**Seguridad y CI/CD:**
- `frontend/nginx.frontend.conf`: CSP y cabeceras de seguridad (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`).
- `.github/workflows/ci.yml`: escaneo de secretos en CI estabilizado con Gitleaks; Trivy fijado a versión estable (`v0.33.1`).
- `.github/workflows/secret-scanning.yml`: eliminado paso inestable de TruffleHog diferencial; Trivy fijado a `v0.33.1`.

**Auth y sesiones:**
- Eliminada la lógica dual de JTI (usuario + sesión): ahora la validación de refresh token se realiza exclusivamente por sesión.
- Nueva migración Alembic `018_drop_user_refresh_token_jti.py` para eliminar columna legacy `users.refresh_token_jti`.

**ML en despliegue:**
- `SEMANTIC_EMBEDDINGS_BACKEND` por defecto `tfidf` para mantener pods HTTP ligeros.
- Dependencias pesadas movidas a `requirements-ml.txt` para workers dedicados.

### v23.9.4 (Abril 2026) — Auditoría integral: seguridad, dependencias y compatibilidad

**Seguridad de configuración y bootstrap:**
- `setup.sh` ya no escribe claves por defecto inseguras: genera `SECRET_KEY` y `CLIENT_PORTAL_SECRET` con `python secrets.token_hex(32)` (fallback `openssl rand -hex 32`)
- `setup.bat` elimina secretos hardcoded y deja placeholders explícitos de rotación (`CHANGE_ME_run_python_secrets_token_hex_32`)
- `Settings` en `app/core/config.py` incorpora validaciones estrictas:
: `SECRET_KEY` mínimo 32 caracteres y bloqueo de valores inseguros conocidos
: `ENVIRONMENT` restringido a `development|test|staging|production`

**Dependencias críticas actualizadas (CVE + compatibilidad):**
- `fastapi`: `0.110.0 -> 0.115.12`
- `starlette`: `0.36.3 -> 0.46.2`
- `pydantic`: `2.6.4 -> 2.12.5`
- `pydantic-settings`: `2.2.1 -> 2.13.1`
- Se elimina el pin explícito de `pydantic_core` para evitar conflictos de resolución con `pydantic`

**Compatibilidad Pydantic v2 (deprecaciones):**
- Migración de `.from_orm()` a `.model_validate()` en endpoints de:
: AI Governance (`app/api/v1/endpoints/ai_governance.py`)
: ABAC (`app/api/v1/endpoints/abac.py`)
: Security Observability (`app/api/v1/endpoints/security_observability.py`)

**Ajustes de pruebas y contratos API:**
- `tests/conftest.py`: `SECRET_KEY` de tests actualizado a valor de longitud segura (>=32) para alinear con validadores de runtime
- `tests/test_business_logic_v238.py`: suite de forecast alineada al contrato real (`forecast`) y al parámetro correcto (`months`)

---

### v23.9.3 (Abril 2026) — Feature Gap Closure Sprint

**Service Desk Kanban (drag & drop operativo):**
- Corregido `dragstart` para persistir `ticket.id` en `dataTransfer` y permitir drop real por columna
- Añadido resaltado visual de columna objetivo (`dragOverCol`) para mejorar feedback de UX

**Capacidad y Resource Leveling:**
- Nuevo endpoint `GET /capacity/leveling` con detección de sobrecarga por usuario/semana
- Generación de sugerencias de redistribución a semanas con disponibilidad

**Pipeline CRM completado:**
- Nuevo `GET /pipeline/forecast` con forecast ponderado por probabilidad en buckets mensuales
- Nuevo CRUD `GET/POST/PATCH/DELETE /pipeline/stages` para etapas configurables por negocio (admin)

**Gantt con replanificación en cascada:**
- Nuevo `POST /tasks/{task_id}/cascade-reschedule` que propaga cambios de fecha por dependencias FS
- Contrato de respuesta consistente en no-op (`total_shifted = 0`)

**Automations con pasos avanzados:**
- Nuevos `ActionType.wait_step` y `ActionType.conditional_branch`
- Ejecución de ramas `if_true/if_false` con evaluación de condición y ejecución recursiva de acciones

**AI Assistant ampliado:**
- Añadidas herramientas `get_capacity_plans` y `get_git_activity` al catálogo de herramientas del agente

**Project Templates (UI + backend robusto):**
- Nueva página frontend `ProjectTemplatesPage` y ruta protegida `/project-templates`
- Endpoints de plantillas endurecidos para aceptar payloads UI (campos `phase_order`, `task_order`, `title` en entregables) ignorando campos extra no persistentes

**Moneda multi-currency:**
- Verificado soporte completo de tipos y conversión en endpoints canónicos `/currency/rates` y `/currency/convert`

**Calidad y pruebas:**
- Añadida suite `tests/test_feature_gaps.py` con cobertura de gaps funcionales
- Estado: `23 passed` en la suite específica de gaps


### v23.9.2 (Abril 2026) — UX, Branding & Accessibility Sprint

**Branding unificado — Clarive en todo el stack:**
- `vite.config.js`: PWA manifest `name`/`short_name` cambiados de `"NexusPM"` a `"Clarive"` y `description` a `"Professional Services Automation"`
- `sdk/python/nexuspm_sdk.py`: clases renombradas `NexusPMClient → ClariveClient`, `NexusPMError → ClariveError`; variable de entorno `CLARIVE_TOKEN` como primaria (con fallback a `NEXUSPM_TOKEN` para retrocompatibilidad); aliases `NexusPMClient = ClariveClient` preservados en `__all__`; docstrings actualizados

**Skeleton loaders por módulo — mejor UX en carga inicial:**
- 5 nuevos skeletons en `components/ui/Skeletons.jsx`: `SkeletonKanban`, `SkeletonGantt`, `SkeletonServiceDesk`, `SkeletonFinance`; refactorizado `SkeletonTable` con soporte de filtros y cabecera
- `App.jsx`: `SmartPageLoader` reemplaza el spinner genérico como fallback del `<Suspense>`; selecciona el skeleton adecuado según la ruta (`/dashboard` → `SkeletonDashboard`, `/projects` → `SkeletonProjects`, `/kanban-advanced` → `SkeletonKanban`, etc.)

**Sidebar con búsqueda de navegación inline:**
- `Layout.jsx`: nuevo componente `NavSearch` con input filtro debajo del Dashboard link; atajo `/` da foco al input de búsqueda del sidebar; cuando hay consulta activa los grupos de navegación se ocultan y `NavSearchResults` muestra resultados filtrados planos con badge de alertas/aprobaciones; limpiar búsqueda con botón `×` o navegar

**Accesibilidad — ARIA y gestión de foco:**
- `ShortcutsModal`: añadido `ref`, `tabIndex=-1` y enfoque automático al abrir; focus trap completo con `Tab`/`Shift+Tab` dentro del modal; backdrop usa `role="presentation"` (el dialog interno tiene `role="dialog" aria-modal="true"`)
- `NavGroup`: botón desplegable ahora incluye `aria-expanded`, `aria-controls` apuntando al panel colapsable; panel con `id` correspondiente
- `TopAppBar`: botón de búsqueda con `aria-label="Abrir búsqueda global"`; botón IA con `aria-label` y `aria-pressed={aiOpen}`
- `NavItem`: todos los links ya tenían `aria-label={displayLabel}` desde la versión anterior

**Dashboard Ejecutivo activado:**
- `ExecutiveDashboardPage.jsx` (286 líneas) conectado a la ruta `/executive` (antes redirigía a `/bi`)
- Ruta protegida para `admin` y `pm`; añadido al grupo "Analítica & BI" del sidebar
- `SmartPageLoader` usa `SkeletonDashboard` en `/executive`

**Limpieza de deuda técnica:**
- Eliminado `frontend/src/pages/ReportsHelpers.jsx` (970 líneas de código muerto, no importado en ningún sitio)
- Limpieza de `__pycache__` en todo el proyecto

---

### v23.9.1 (Agosto 2026) — Security Hardening

**Cross-tenant data isolation — Report Builder:**
- `_execute_report()` en `report_builder.py` ahora acepta `current_user` y aplica filtro `organization_id` antes de ejecutar cualquier consulta
- Modelos con `organization_id` filtran directamente; modelos con `project_id` filtran vía subquery a proyectos del tenant; la entidad `users` filtra por `organization_id`
- Superadmins no están restringidos (ven todos los tenants)
- `preview_report` y `export_report` pasan `current_user` a `_execute_report`

**Persistencia de plantillas del Report Builder (DB en lugar de memoria):**
- Eliminado el dict global `_templates` + `threading.Lock` (se reiniciaba en cada worker/deployment)
- Nuevas funciones `_load_user_templates()` y `_save_user_templates()` usando la tabla `AppSetting` con clave `report_templates:{user_id}` → valor JSON
- Los templates persisten entre reinicios y son correctamente aislados por usuario

**Tenant isolation — Service Desk:**
- `list_tickets()`: managers/admins ya no ven tickets de otros tenants; se filtra por `requester_user_id` o `assigned_to_user_id` pertenecientes a la organización del usuario activo
- `list_problems()`: añadido filtro por `owner_user_id` en la org del usuario (antes devolvía todos los problemas sin restricción)
- `list_kb_articles()`: para usuarios internos autenticados, artículos filtrados por `author_id` en la org del usuario
- Superadmins omiten todos los filtros de tenant

**SLA recalculado al cambiar prioridad de ticket:**
- `update_ticket()` en `service_desk.py`: cuando urgency/impact cambia y se recalcula `priority`, ahora también se actualizan `sla_response_due` y `sla_resolution_due` vía `_calculate_sla_due(new_priority, policy, db)`
- Solo aplica si el ticket no está ya resuelto/cerrado/cancelado

**Portal JWT key isolation:**
- `verify_client_token()` en `security.py` ahora usa exclusivamente `settings.CLIENT_PORTAL_SECRET` (HS256) en lugar de iterar todas las claves JWT de backend
- Añadida validación de campo `type == "client"` para evitar que tokens de usuarios internos sean aceptados como tokens de portal
- Tokens de clientes y de empleados son ahora completamente incompatibles criptográficamente

**DocuSign URL producción:**
- `DOCUSIGN_BASE_URL` en `config.py` cambiado de `"https://demo.docusign.net/restapi"` (sandbox) a `""` (vacío)
- Integrador debe configurar explícitamente `DOCUSIGN_BASE_URL` en variables de entorno para producción; usar `https://na.docusign.net/restapi` (NA) o `https://eu.docusign.net/restapi` (EU)
- Evita que instalaciones nuevas envíen e-signatures al entorno demo de DocuSign sin saberlo

---

### v23.9.0 (Agosto 2026) — versión actual

**Tipos de cambio en tiempo real — integración BCE:**
- `app/services/exchange_rate_service.py` — nuevo servicio con `sync_ecb_rates()` (XML BCE gratuito) y `sync_openexchangerates()` (OpenExchangeRates.org)
- `POST /currency/sync-ecb` (admin) — fuerza sincronización con el feed diario del Banco Central Europeo (~30 pares EUR-based, idempotente)
- `POST /currency/sync-openexchangerates` (admin) — alternativa con clave API `OPEN_EXCHANGE_RATES_APP_ID`
- `get_rate(db, from_c, to_c, as_of)` — lookup con fallback a fecha más cercana

**White-label / Marca blanca por tenant:**
- Nuevo modelo `OrgBranding` en `app/models/white_label.py`
- Campos: `app_name`, `tagline`, `logo_url`, `favicon_url`, colores hexadecimales, `custom_domain`, `support_email`, `welcome_message`, `hide_powered_by`, `enable_portal`, `enable_ai`, `custom_css_vars` (JSON)
- `GET /orgs/{org_id}/branding` — devuelve configuración o valores por defecto
- `PUT /orgs/{org_id}/branding` (admin) — actualiza; valida colores hex y dominio bare-hostname
- `DELETE /orgs/{org_id}/branding` (admin) — resetea a valores por defecto
- `custom_css_vars` sanitizadas: solo claves con `--` y longitud < 80

**Gantt Baselines — congelado y comparación de cronograma:**
- Nuevo modelo `GanttBaseline` en `app/models/marketplace.py` con `schedule_snapshot` (JSON de tareas con start/end/progreso)
- `GET /projects/{id}/baselines` — lista de baselines ordenados por fecha desc
- `POST /projects/{id}/baselines` (manager) — congela el cronograma actual como baseline inmutable con stats (total_tasks, completed_tasks, total_hours, budget_at_freeze)
- `GET /projects/{id}/baselines/{baseline_id}/compare` — devuelve deltas por tarea: `slip_days`, cambios de estado, horas desviadas + summary con avg_slip_days
- `DELETE /projects/{id}/baselines/{baseline_id}` (manager) — elimina baseline

**Marketplace de Integraciones — 22 conectores certificados:**
- Nuevos modelos `IntegrationConnector` + `IntegrationInstance` en `app/models/marketplace.py`
- Catálogo pre-sembrado con 22 conectores: Salesforce, HubSpot, SAP S/4HANA, NetSuite, Workday, BambooHR, Greenhouse, Jira, GitHub, GitLab, Slack, Teams, Xero, QuickBooks, DocuSign, Stripe, Azure DevOps, AWS S3, Google Workspace, Zendesk, ServiceNow, Okta
- `GET /integrations/marketplace?category=&certified_only=` — catálogo con estado de instalación por org
- `POST /integrations/instances` (admin) — instala conector; config encriptada en reposo (`encrypt_value`)
- `GET /integrations/instances` — lista instancias de la organización con estado de último sync
- `DELETE /integrations/instances/{id}` (admin) — desinstala

**CRM Bidireccional — Salesforce:**
- `POST /integrations/salesforce/sync-opportunities` — sincroniza oportunidades Salesforce ↔ Pipeline Clarive
- Soporta `inbound`, `outbound`, `bidirectional` (modo basado en instance_id)
- Mapeo de `StageName` Salesforce → stage interno (lead/qualification/proposal/negotiation/won/lost)
- Credenciales descifradas en runtime; `last_sync_status` actualizado tras cada sync

**Customer Health Score Compuesto (fórmula mejorada):**
- `GET /clients/{id}/health-composite` — score 0–100 con descomposición:
  - NPS (40%): promotores/detractores últimos 90 días, normalizado a 0-100
  - Delivery (20%): % hitos entregados a tiempo
  - Presupuesto (15%): % proyectos within-budget
  - Resolución tickets (15%): % tickets resueltos dentro de SLA (últimos 30 días)
  - Actividad portal (10%): sesiones del cliente en portal últimos 30 días
- Categorías: `excellent` (≥80), `good` (≥60), `at_risk` (≥40), `critical` (<40)

**AI Copilot Contextual Inline — 3 endpoints:**
- `GET /ai/suggestions/gantt/{project_id}` — detecta tareas vencidas (severity high/medium) y tareas estancadas (>50% tiempo elapsed, <20% progress); devuelve sugerencias de mitigación accionables
- `GET /ai/suggestions/timesheets/{user_id}` — anomalías en últimos 30 días: horas altas (>12h/día), gaps sin imputaciones (>7 días), imputaciones en proyectos cerrados
- `GET /ai/suggestions/ticket/{ticket_id}` — sugiere artículos KB por keyword matching (tfidf simple); top 5 relevantes

**Project Templates Mejoradas — documentos y roles:**
- Nuevos modelos: `TemplateDocument` y `TemplateRole` en `app/models/marketplace.py`
- `POST /templates/{id}/documents` — añade referencia documental (SOW, RFC, spec, etc.) con `is_required` y `due_week_offset`
- `POST /templates/{id}/roles` — añade rol requerido con `skill_required`, `min_seniority`, `estimated_hours`, `is_mandatory`
- `GET /templates/{id}/full` — devuelve ficha completa: fases + tareas + riesgos + entregables + documentos + roles
- `POST /projects/{id}/export-template` — convierte un proyecto existente (tareas + riesgos) en plantilla reutilizable

**Approval Workflow Visual Builder:**
- `GET /approval-workflows/builder/schema` — JSON schema del builder: tipos de nodo (start, approval_step, condition, action, end) con config_schema por nodo, tipos de arista y canvas settings
- `POST /approval-workflows/builder/validate` — valida grafo: start único, nodo end presente, nodos sin salida detectados, nodos huérfanos (warnings)

**Slack Block Kit Rich Notifications:**
- `POST /notifications/slack/block-kit` — envía notificación Block Kit al webhook configurado para el evento: `task_overdue`, `invoice_paid`, `approval_required`, `custom`
- `GET /notifications/slack/block-kit/preview?event_type=` — preview del JSON Block Kit para cualquier tipo de evento (útil para test visual en Slack Block Kit Builder)
- `_build_block_kit_message()` — construye mensajes con Header + Section fields + Actions buttons con deeplinks a la entidad

**Nuevas traducciones i18n (8 idiomas):**
- Sección `v239` añadida a ES, EN, FR, DE, PT, IT, PL, ZH en `frontend/src/i18n/appTranslations.js`
- 30+ claves: `ecb_sync`, `white_label`, `gantt_baseline`, `integration_marketplace`, `salesforce_sync`, `template_documents`, `template_roles`, `customer_health_dashboard`, `ai_copilot`, `block_kit_notify`, …

---

### v23.8.0 (Julio 2026)

**Fix: Race condition en numeración de tickets (advisory lock):**
- `_next_ticket_number()`, `_next_problem_number()`, `_next_kb_number()` en `service_desk.py` usan `pg_advisory_xact_lock()` para serializar la numeración en PostgreSQL
- Fallback gracioso en SQLite (try/except) para que los tests de CI no fallen
- Clave de bloqueo determinista: `md5(nombre) mod 2^63` → clave `bigint` reproducible

**Multi-moneda completa:**
- `ExchangeRate` (ya existía en `bookings.py`) reutilizado para gestión de tasas
- `CurrencyConversionLog` — nuevo modelo de auditoría de conversiones (`app/models/exchange_rates_log.py`)
- `GET /currency/rates` — listar tasas con filtro opciones por monedas
- `POST /currency/rates` (admin) — crear/actualizar tasa diaria (upsert)
- `GET /currency/convert?amount=&from_currency=&to_currency=` — conversión con lookup inverso
- `GET /currency/report?base_currency=EUR` — informe consolidado multimoneda de facturas/contratos
- Config: `OPEN_EXCHANGE_RATES_APP_ID`, `EXCHANGE_RATES_AUTO_UPDATE` en `app/core/config.py`

**Pipeline / CRM — Etapas configurables y previsión mensual:**
- `PipelineStageConfig` — nuevo modelo (`app/models/pipeline.py`) con color, orden, probabilidad, is_terminal, is_won
- `GET /pipeline/stage-configs` — listar etapas (fallback a defaults si no hay configuradas)
- `POST /pipeline/stage-configs` (admin) — crear etapa personalizada
- `DELETE /pipeline/stage-configs/{stage_key}` (admin) — desactivar etapa
- `GET /pipeline/forecast?months_ahead=6` — roll-up de ingresos ponderados por mes (expected_revenue × probabilidad_etapa)

**Capacity Planning — detección de conflictos y nivelación Gantt:**
- `GET /bookings/conflicts?threshold_pct=100` — detecta double-booking (% de horas sobre capacidad nominal)
- `GET /bookings/gantt-leveling` — análisis de sobrecarga + propuestas de desplazamiento automático
- Respuestas incluyen recurso afectado, periodo, porcentaje de sobrecarga y fechas sugeridas de replanificación

**Automations — triggers de campo y acciones Jira/HubSpot:**
- Nuevos valores en `TriggerType`: `custom_field_changed`, `opportunity_stage_changed`
- Nuevos valores en `ActionType`: `create_jira_issue`, `update_jira_issue`, `create_hubspot_deal`, `update_hubspot_deal`
- `GET /automations/trigger-types` — catálogo de triggers con metadata para visual builder
- `GET /automations/action-types` — catálogo de acciones incluyendo Jira/HubSpot
- `POST /automations/test-trigger` — evaluar trigger `custom_field_changed` en vivo sobre una entidad

**BI/Reporting — Motor ad-hoc, drilldown y cross-filter:**
- `POST /analytics/adhoc` — query paramétrica: métrica (hours/revenue/task_count/ticket_count), dimensiones (month/user_id/project_id/status/priority), filtros opcionales, rango de fechas
- `GET /analytics/drilldown?metric=&dimension=&value=` — filas detalladas para un valor de dimensión concreto, paginado
- `POST /analytics/cross-filter` — filtros simultáneos en múltiples dimensiones; devuelve conteos por dimensión para linked charts

**Stripe — pasarela de pago en facturas:**
- Nuevos campos en `Invoice`: `stripe_payment_intent_id`, `stripe_payment_link_url`, `stripe_payment_link_id`, `stripe_paid_at`
- `POST /invoices/{id}/payment-link` — crea Price + PaymentLink en Stripe API; almacena URL en factura
- `POST /invoices/stripe-webhook` — valida firma HMAC (`stripe-signature`), marca factura como pagada en `checkout.session.completed`
- Config: `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` en `app/core/config.py`
- Devuelve 503 si Stripe no está configurado (sin clave secreta)

**Documentos colaborativos — persistencia CRDT/Yjs:**
- `DocumentCollabSnapshot` — nuevo modelo (`app/models/document_collab.py`) con `state_vector` (LargeBinary), `clock`, `size_bytes`, `is_current`
- `POST /documents/{id}/collab/snapshot` (body: `application/octet-stream`) — guardar estado Yjs binario; incrementa clock automáticamente
- `GET /documents/{id}/collab/snapshot` — cargar snapshot más reciente (devuelve `state_vector` en base64)
- `GET /documents/{id}/collab/history` — historial de snapshots con clocks ordenados

**SCIM 2.0 — cumplimiento completo:**
- `ServiceProviderConfig`: bulk ahora `supported: true, maxOperations: 100`
- `GET /Schemas` — endpoint con User + Group schemas según RFC 7643
- `GET /ResourceTypes` — endpoint con User + Group resource types
- `GET /Users` con filtro mejorado: soporta `userName eq`, `emails.value eq`, `externalId eq`, `active eq`, `userName sw`
- `POST /Bulk` — operaciones masivas (hasta 100 ops): Create/PUT/PATCH/DELETE de usuarios; soporte `failOnErrors`
- `GET /Groups/{group_id}` — endpoint de grupo individual

**Tests:**
- `tests/test_business_logic_v238.py` (nuevo): 40 tests cubriendo todas las features anteriores
- Integración con suite existente; app imports limpios verificados

**Configuración de entorno nueva:**
```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
OPEN_EXCHANGE_RATES_APP_ID=your_app_id
EXCHANGE_RATES_AUTO_UPDATE=false
```

---

### v23.7.0 (Junio 2026)

**Fix: Resource Scheduler — drag de reservas (backend y frontend):**
- `PATCH /bookings/{id}` usaba `payload: dict = Body(...)` + `setattr` crudo sobre columnas `Date` de SQLAlchemy → falla en PostgreSQL con strings en vez de objetos `date`
- Reemplazado por `BookingUpdate(BaseModel)` con campos `Optional[date]` tipados; Pydantic coerce automáticamente string a `date` antes de llegar a SQLAlchemy
- Validación de rango: `end_date >= start_date`; devuelve 400 si no cumple
- El endpoint ahora devuelve el booking enriquecido mediante `_booking_out()`
- Frontend (`ResourceSchedulerPage.jsx`): el handler `onMove` era un no-op; reescrito con ghost element flotante que muestra las fechas destino (`inicio → fin`) durante el arrastre

**Mejora UX: Navegación contextual con Acceso Rápido:**
- Añadido `QUICK_ACCESS` por rol (`admin`, `pm`, `team_lead`, `hr`, `employee`) — 6 ítems relevantes por rol
- `FavoritesSection` muestra "⚡ Acceso rápido" con los ítems del rol cuando no hay favoritos fijados; hint "añade ★ para personalizar"
- Contadores en grupos colapsados: el encabezado muestra `{n}` ítems disponibles
- `NavGroup` acepta prop `forceOpen` para mantener el grupo activo siempre expandido

**Mejora UX: Onboarding Wizard — verificación automática:**
- `STEP_META` por paso: `action_label`, `path`, `tips[]` (3 ítems), función `verify()` asíncrona
- Verificación automática al montar el componente y al navegar: consulta endpoint relevante para marcar paso completado
- Botón "Ya lo hice ✓" con spinner (`RefreshCw`) para trigger manual de verificación
- Tips numerados paso a paso que explican exactamente qué hacer en cada pantalla

**Tests:**
- `TestResourceSchedulerBookings` (6 tests nuevos): create, patch con fechas, patch parcial, rango inválido, delete, RBAC employee-forbidden
- `tests/test_business_logic_v236.py`: 57 tests en total (51 → 57), todos passing

---

### v23.6.0 (Mayo 2026)

**Fix: enum `in_review` aceptado por backend y frontend (`app/models/task.py`, `app/schemas/schemas.py`, `app/api/v1/endpoints/tasks.py`, migración `016`):**
- `TaskStatus.in_review = "in_review"` añadido al modelo ORM *y* al schema Pydantic (ambos necesarios para pasar la validación)
- Migración `016_task_status_in_review.py`: en PostgreSQL ejecuta `ALTER TYPE taskstatus ADD VALUE IF NOT EXISTS 'in_review' BEFORE 'review'` + UPDATE de filas existentes; en SQLite sólo UPDATE
- `_TASK_VALID_TRANSITIONS` en `tasks.py`: `in_progress → {in_review, review, …}`, `in_review → {done, in_progress, review}`, `review → {done, in_progress, in_review}`
- `app/worker.py`: `"In Review": TaskStatus.in_review` (actualizado desde `TaskStatus.review`)

**Fix: import roto en `JiraIntegrationPage.jsx`:**
- `import { api } from '../api/client'` → `import api from '../services/api'` (el path anterior no existía)

**PDF de facturas — descarga desde la UI (`app/services/invoice_pdf.py`, `app/api/v1/endpoints/billing_reports.py`, `frontend/src/pages/InvoicesPage.jsx`):**
- Nuevo servicio `generate_invoice_pdf()`: genera PDF profesional con ReportLab (cabecera Clarive, tabla de líneas, totales, notas, pie)
- Endpoint `GET /invoices/{id}/pdf`: devuelve `application/pdf` con `Content-Disposition: attachment; filename="factura_{number}.pdf"`; requiere `require_any_manager`
- Frontend: botón `<Download>` por fila; descarga vía `api.get('/invoices/{id}/pdf', { responseType: 'blob' })` + `URL.createObjectURL`

**Logging configurable — backend y frontend:**
- `app/core/config.py`: campo `LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")`
- `app/main.py`: nivel de logging inicial leído desde `os.environ.get("LOG_LEVEL", "INFO")`
- `GET /settings/log-level`: devuelve nivel actual del logger `root` y del logger `clarive`
- `POST /settings/log-level`: cambia nivel en tiempo real para cualquier logger; requiere admin; 400 si nivel inválido
- `frontend/src/utils/logger.js`: logger con niveles `debug/info/warn/error/silent`; persistido en `localStorage.clarive_log_level`; expuesto como `window.__clariveLogger`
- `SettingsPage`: nueva pestaña "📋 Nivel de log" (solo admin) → slectores para nivel backend y frontend

**Pipeline CRM — drag-and-drop entre etapas (`frontend/src/pages/PipelinePage.jsx`):**
- `OppCard` reescrita con drag mouse-based (umbral 5px, mismo patrón que Kanban y ResourceScheduler)
- Ghost chip flotante con nombre de la oportunidad + resaltado de columna destino (`[data-stage-drop]`)
- Mutación `moveStage`: `api.patch('/pipeline/{id}', { stage })` con invalidación de query
- `handleStageDrop` callback con `useCallback` + `useToast` para feedback

**Onboarding Wizard — modal completo (`frontend/src/components/layout/OnboardingWizard.jsx`):**
- Reescrito de 52 → 130+ líneas; ahora es un modal de overlay (no inline card)
- 5 pasos con barra de progreso, indicador de completado, icono grande + descripción accionable
- Botones "Ir a configurar" que navegan a la página relevante + prev/next/saltar/finalizar

**Navegación — favoritos y páginas recientes (`frontend/src/components/layout/Layout.jsx`):**
- Sección "⭐ Favoritos" entre Dashboard y los grupos: muestra rutas guardadas en `localStorage.clarive_pinned_routes`
- Sección "⏱ Recientes": últimas 5 páginas visitadas (excluye `/` y `/login`); persistidas en `localStorage.clarive_recent_routes`
- Botón ☆/★ visible on-hover en cada `NavItem` para fijar/desfijar rutas
- `NavGroup` y rutas single pasan `pinned` y `onPin` hacia abajo a todos los `NavItem`

---

### v23.5.0 (Abril 2026)

**Multi-tenancy — aislamiento de datos por organización (`app/models/project.py`, `app/core/deps.py`, `app/api/v1/endpoints/projects.py`, migración `015`):**
- Campo `organization_id` (FK → `organizations.id`, `ondelete="SET NULL"`, indexado) añadido al modelo `Project`
- Migración 015 (`alembic/versions/015_multitenant_org_isolation.py`): añade columna, FK constraint, índice y backfill automático (asigna a cada proyecto la organización de su PM si existe)
- `get_current_org_id()` en `app/core/deps.py`: devuelve `None` para superadmins (ven todos los proyectos), o `current_user.organization_id` para el resto
- `list_projects()`: filtra automáticamente por `organization_id` del usuario antes de aplicar filtros de rol; superadmins ven todos
- `get_project()`: devuelve 404 si el proyecto pertenece a otra organización (cross-tenant access blocked)
- `create_project()`: asigna automáticamente `organization_id` del usuario creador al nuevo proyecto
- 3 tests nuevos en `tests/test_projects.py`: `test_project_auto_assigns_org_on_create`, `test_project_list_scoped_to_org`, `test_project_get_cross_org_returns_404`

**Branding — eliminación de referencias hardcoded a "NexusPM" (8 ocurrencias en 6 archivos):**
- `frontend/src/main.jsx`: `[NexusPM]` → `[Clarive]` en el título PWA
- `frontend/src/pages/DeveloperPortalPage.jsx`: texto "NexusPM" → "Clarive"
- `frontend/src/pages/GitPage.jsx`: texto "NexusPM" → "Clarive"
- `frontend/src/pages/JiraIntegrationPage.jsx`: 2 ocurrencias "NexusPM" → "Clarive"
- `frontend/src/pages/M365Page.jsx`: 2 ocurrencias "NexusPM" → "Clarive"
- `frontend/src/services/offlineQueue.js`: clave localStorage `'nexuspm_offline'` → `'clarive_offline'`

**Kanban DnD — corrección del conflicto click/drag (`KanbanAdvancedPage.jsx`):**
- **Bug**: el ghost de drag se creaba en `onMouseDown`, causando que cualquier click generara un drag fantasma; `onClick` disparaba incluso tras un drag real
- **Fix**: umbral de 5px — el drag sólo se activa cuando el ratón se mueve >5px desde el punto inicial; `wasDragged = useRef(false)` en `KanbanCard` previene que `onClick` dispare tras un drag real; callback `onDragStarted` propagado desde la tarjeta a la página

**Jira — sincronización periódica Celery (`app/worker.py`):**
- Nueva tarea `jira_periodic_sync` registrada en el beat schedule: `crontab(minute="*/30")` (cada 30 minutos)
- Lee configuración Jira desde el modelo `AppSetting` (claves: `jira_url`, `jira_email`, `jira_api_token`, `jira_project_key`); aborta si alguna clave falta
- Ventana de solapamiento de 65 minutos para evitar huecos entre ejecuciones
- `STATUS_MAP` usa `TaskStatus.review` (valor correcto del enum), mapea todos los estados Jira relevantes
- Crea o actualiza tareas locales via `jira_issue_key`; no usa campo `source` (no existe en el modelo `Task`)
- 4 tests en `tests/test_v235_features.py`: skip sin config, skip con config incompleta, manejo de errores HTTP, creación de tareas mock

**Resource Scheduler — vista de asignación drag-to-assign (`ResourceSchedulerPage.jsx`):**
- Nuevo toggle en el header: `📅 Planificador` (timeline original) / `🧑‍🤝‍🧑 Asignación` (nueva vista)
- Vista Asignación: panel izquierdo (160px) con chips de personas arrastrables + panel derecho con proyectos como filas de drop targets + timeline de bookings existente
- Umbral de 5px para iniciar el drag (mismo patrón que Kanban), ghost chip visual durante el arrastre
- Al soltar sobre un proyecto se abre el `BookingPanel` pre-rellenado con persona y proyecto seleccionados
- 1 test en `tests/test_v235_features.py`: `test_create_booking_via_api`

---

### v23.4.0 (Abril 2026)

**Jira Cloud — integración bidireccional (`app/api/v1/endpoints/jira.py`, nuevo, ~280 líneas):**
- `GET/POST /jira/config` — guarda/lee credenciales Jira Cloud (URL, email, API token, project key) en `AppSetting`; token enmascarado en GET
- `GET /jira/test` — verifica conectividad vía `/rest/api/3/myself` (httpx Basic Auth)
- `GET /jira/issues` — proxy de issues Jira con soporte JQL
- `POST /jira/sync` — importa issues Jira → crea/actualiza tareas NexusPM (mapeo de `jira_issue_key`, estado, prioridad, descripción ADF)
- `POST /jira/push` — exporta tareas NexusPM sin `jira_issue_key` → crea issues Jira, escribe back la clave
- `POST /jira/webhook` — recibe eventos Jira Cloud en tiempo real (`issue:updated`, `issue:deleted`); actualiza estado y prioridad de la tarea vinculada
- `GET /jira/linked` — lista todas las tareas que tienen `jira_issue_key` asignado
- `JIRA_STATUS_MAP`, `JIRA_PRIORITY_MAP` — tablas de mapeo Jira→NexusPM para estado (8 valores) y prioridad (8 valores)
- Campos `jira_issue_key`, `jira_issue_id`, `jira_synced_at` ya existían en el modelo `Task` — sin migración adicional
- **Frontend `JiraIntegrationPage.jsx`** (nuevo): formulario de config, botón de prueba de conexión, tabla de issues Jira, acciones pull/push, tabla de tareas vinculadas
- 9 tests en `tests/test_jira.py` cubriendo: save/read config, autorización, mapeos de estado/prioridad, test-connection, webhook_updates, webhook_ignores_unknown, linked_tasks

**AI Overrun Prediction — predicción de sobrecosto/retraso (`ai_modules.py` extendido):**
- `_predict_overrun_ml(cpi, spi, budget_used_pct, elapsed_pct, task_completion_pct, overdue_task_ratio, team_load_pct)` — modelo heurístico ensemble de 6 señales ponderadas: CPI crítico (+0.45), SPI crítico (+0.5), quema de presupuesto vs tiempo, gap de finalización de tareas, ratio de tareas vencidas (>40% → +0.25), sobrecarga de equipo (>110% → burnout risk)
- `POST /ai/overrun-prediction` — endpoint REST: lee datos reales de EVM (CPI, SPI, AC, PV, EV) + tareas + imputaciones del proyecto, llama al modelo, devuelve `{cost_overrun_prob, schedule_overrun_prob, cost_overrun_pct, schedule_overrun_days, confidence, signals[], recommendation}`
- 6 tests en `tests/test_business_logic.py::TestOverrunPrediction`: healthy project, CPI crítico, SPI crítico, overdue ratio, burnout signal, output structure

**Revenue Journal Entries — asientos contables ASC 606/IFRS 15 (`cab.py` extendido):**
- `GET /revenue/journal/{project_id}` — genera asientos de doble entrada por cada `RevenueRecognitionEntry` del proyecto:
  - Importe reconocido: DR Cuentas por cobrar (1100) | CR Ingresos reconocidos (4000)
  - Importe diferido: DR Tesorería (1000) | CR Ingresos diferidos (2400)
  - Devuelve `journal_lines[]` con `date, period, journal_ref, line (DR/CR), account_code, account_name, debit, credit, currency, method, pct_complete, is_locked`
- `GET /revenue/journal/{project_id}/export` — export CSV listo para importar en ERP (SAP, Sage, QuickBooks)
- Soporta todos los métodos de reconocimiento: `percentage_complete`, `time_and_material`, `straight_line`, `milestone_billing`

**Public API SDK — clientes oficiales:**
- `sdk/python/nexuspm_sdk.py` — cliente Python (sólo requiere `requests`): namespaces `projects`, `tasks`, `imputations`, `users`, `resources`, `financials`, `ai`, `jira`; manejo de errores (`NexusPMError`, `AuthError`, `NotFoundError`); soporte `NEXUSPM_TOKEN` env var
- `sdk/javascript/nexuspm_sdk.js` — cliente ES6/ESM con `fetch` nativo (Node 18+ o navegador): mismos namespaces; `AbortSignal.timeout`; compatible TypeScript via JSDoc
- `sdk/README.md` — documentación con ejemplos de uso, tabla de métodos, manejo de errores

**Responsive / tablet CSS (`index.css` extendido):**
- Tablet 769–1024px: sidebar colapsado a iconos (52px, etiquetas ocultas), reducción de padding, celdas de tabla más compactas, grids de 2 columnas → 1
- Mobile ≤768px: toque mínimo 44px para botones/links, `font-size: 16px` en inputs (previene zoom iOS), padding reducido, flex-rows verticales, botones a ancho completo — complementa el sidebar overlay ya existente

**Kanban Drag-and-Drop — corrección de stale closure (`KanbanAdvancedPage.jsx`):**
- **Bug**: `handleTaskDragStart` en `useCallback([dropTarget, ...])` capturaba `dropTarget = null` al inicio del drag; el `onUp` inner usaba esa copia congelada → el drop target siempre era `null` → no se actualizaba el estado
- **Fix**: añadido `dropTargetRef = useRef(null)` sincronizado en `handleColumnEnter`; `onUp` ahora lee `dropTargetRef.current` (siempre actualizado) en vez del valor del closure; eliminado `dropTarget` de las dependencias del `useCallback`

**Traducciones — 8 idiomas actualizados:**
- Añadidas claves `resource_scheduler` y `jira_integration` en ES/EN/FR/DE/PT/IT/PL/ZH
- `Layout.jsx`: añadido `/jira-integration` a PATH_TITLE, ROUTE_SECTION, PATH_NAV_KEY y NAV_GROUPS (Configuración, roles admin/pm)

---

### v23.3.0 (Abril 2026)

**Visual Resource Scheduler — `ResourceSchedulerPage.jsx` nuevo componente (551 líneas):**
- **Timeline grid**: filas por persona (sticky label column 200px) × columnas semanas — estilo Runn/Parallax
- **Heat-shading de utilización**: cada celda muestra el % de carga como color de fondo (disponible → sobrecargado, 6 tonos)
- **Barras de booking como spans**: cada `ResourceBooking` se renderiza como una barra de color de proyecto que abarca sus semanas
- **Drag-create bookings**: `mousedown` en celda vacía → arrastrar → `mouseup` → panel de creación → `POST /bookings`
- **Drag-to-move**: `mousedown` sobre una barra existente → arrastrar → `mouseup` → `PATCH /bookings/{id}` con nuevas fechas
- **Panel inline**: elegir proyecto, horas/día y tipo (soft/hard) al crear o editar una reserva
- **Teclado**: `Esc` cancela drag/panel · `Delete` elimina la reserva seleccionada
- **Zoom de horizonte**: botones 8s / 12s / 16s / 24s
- **Filtro por departamento** (selector dinámico desde datos del forecast)
- Ruta: `/resource-scheduler` (roles: admin, pm, team_lead)
- Usa `/resource-forecast/weeks` para utilización de fondo + `/bookings` para las barras de reserva

**`GET /resource-forecast/utilization-trend` — nuevo endpoint de tendencia:**
- `weeks_past` semanas con datos reales de `Imputation` (lo que la gente realmente imputó)
- `weeks_future` semanas proyectadas desde `ResourceBooking` + `CapacityPlan`
- Devuelve series unificadas listos para gráfico: `{team: [{week, actual_pct, planned_pct, is_future}], users: [...]}`
- Filtros: `user_id`, `department`

**SLA Working-Hours Calculator — corrección crítica en `service_desk.py`:**
- **Antes**: `_calculate_sla_due()` usaba `now + timedelta(hours=N)` en crudo — ignoraba fines de semana, festivos y horario laboral
- **Ahora**: nueva función `_add_working_hours(start_dt, hours, work_start, work_end, holidays)` completamente testeable:
  - Respeta ventana horaria configurable (default 08:00–18:00)
  - Salta automáticamente fines de semana (sábado, domingo)
  - Salta festivos cargados de `SDSLAHoliday` (por política SLA o globales)
  - Maneja solicitudes fuera de horario: las snapa al inicio del siguiente día laboral
  - Soporta horas fraccionarias (ej. SLA de 30 minutos)
- Ambos call sites actualizados: `_calculate_sla_due(..., db=db)` pasa la sesión DB para cargar festivos en tiempo real

**Tests de lógica de negocio — `tests/test_business_logic.py` nuevo (44 tests, 278 líneas):**
- `TestSLAWorkingHoursCalculation` (8 tests): mismo día, cruce de jornada, fin de semana, SLA P1 24h con fin de semana, festivo único, múltiples festivos, snap desde fuera de horario, horas fraccionarias
- `TestRevenueRecognitionMethods` (11 tests): percentage-of-completion (50%, 100%, 0%, sin tareas), T&M (tarifa única, multi, 0h), straight-line (12 meses, contrato irregular, guardia division-by-zero), milestone billing (2 aprobados, 1 facturado, ninguno aprobado)
- `TestEVMCalculations` (7 tests): SPI on-track, SPI behind, CPI on-budget, CPI over-budget, EAC exacto (proyección de coste), EAC-ETC invariante, EVM multi-fase (2 paquetes de trabajo con rendimiento diferente)
- `TestBurnoutModel` (9 tests): horas bajas, carga moderada, alta, crítica, tendencia creciente vs decreciente, semanas consecutivas, entrada de 1 semana, lista vacía, cap 0.99
- `TestResourceBookingOverlapDetection` (7 tests): solapamiento total, parcial, adyacentes sin solape, mismo día, periodos separados, contenido, frontera compartida
- 44/44 passing en < 55s → `pytest tests/test_business_logic.py -v`

---

### v23.2.0 (Abril 2026)

**Gantt v2 — `GanttChart.jsx` reescrito completo (576 líneas):**
- **Columna de etiquetas sticky** (CSS grid 2 columnas, scrollTop sincronizado) — ya no se desplazan con el timeline
- **Cabecera de dos niveles**: fila superior (mes/trimestre/año) + fila inferior (semana/día/mes), siempre visible
- **4 niveles de zoom**: Día · Semana · Mes · Trimestre (teclado `+`/`−`)
- **Milestones** como diamantes SVG (`item.is_milestone = true`)
- **Filas de grupo/fase colapsables** (`item.is_group` o `item.type = 'group'|'phase'`)
- **Avatar de assignee** en columna de etiquetas
- **Creación de dependencias por gestura**: `Shift+drag` desde el manejador derecho de una tarea → soltar sobre otra
- **Camino crítico** resaltado en ámbar (`item.is_critical = true`)
- **Barras de baseline** opcionales (`showBaseline=true`, `item.baseline_start/baseline_end`)
- **Porcentaje de progreso** mostrado fuera de la barra
- Escape cancela drag/dep activo
- `GanttPage.jsx` refactorizado para delegar el render al componente (elimina implementación de 530 líneas con `COL_W=26`)

**Kanban Avanzado v2 — `KanbanAdvancedPage.jsx` reescrito (631 líneas):**
- **Drag-and-drop real de tarjetas** (eventos nativos `mousedown/mousemove/mouseup`) — la feature #1 que faltaba; llama `PATCH /tasks/{id}` al soltar
- **Formulario de creación rápida inline** por columna (click `+ Añadir tarea` → Enter → crea tarea)
- **Barra de filtros inline**: chips de prioridad, chips de assignee, búsqueda de texto, selector de sprint
- **Swimlanes renderizadas**: agrupa tarjetas por assignee / prioridad / épica (selector en toolbar)
- **Gauge de WIP** en cabecera de columna (barra de progreso con color rojo al alcanzar límite)
- **Cards rediseñadas**: badge de subtareas (`⊞ done/total`), avatar de assignee, fecha de vencimiento (rojo = vencido), icono de prioridad, puntos de historia
- **Panel de configuración** WIP limit por columna (botón `⚙ Configurar`)
- Teclado: `/` enfoca búsqueda · `Esc` cancela drag

**GitHub Integration — nuevas capacidades:**
- `POST /git/tasks/{task_id}/branch` — genera nombre canónico de rama (`feat/PROJ-123-slug`) con prefix según tipo de issue
- **Auto-cierre de tarea** en PR mergeado: cuando GitHub envía `action=closed + merged=true`, la tarea vinculada pasa automáticamente a `status=done`

**Microsoft 365 — nuevas capacidades:**
- `GET /m365/users/presence?upns=user1@co,user2@co` — presencia en tiempo real vía `POST /communications/getPresencesByUserId` (Graph API)
- `POST /m365/planner/tasks/sync?project_id=...&plan_id=...` — push de tareas activas de NexusPM a Microsoft Planner; crea tareas nuevas, omite duplicados por título, devuelve `{created, skipped, errors}`

**IA — modelo de burnout mejorado + nuevos endpoints:**
- `_burnout_score()`: reemplaza la regresión lineal simple (`avg-35/20`) por un modelo multi-factor:
  - Promedio ponderado (semanas más recientes peso 2×)
  - Factor de tendencia (carga creciente añade hasta +0.15)
  - Coeficiente de variación (variabilidad = estrés adicional)
  - Semanas consecutivas >42h (cada una añade +0.08)
  - Umbrales severity actualizados: critical >0.75, high >0.5, medium >0.25
- `POST /ai/revenue-forecast` — regresión lineal OLS pura Python (sin numpy) sobre los últimos 12 meses de facturación, devuelve previsión para los próximos N meses + IC 80% + R²
- `POST /ai/smart-schedule` — dado un conjunto de tareas sin fechas, usa el LLM configurado (Claude/GPT) con contexto de capacidad del equipo para sugerir un calendario → `[{task_id, suggested_start, suggested_due, rationale}]`

**Correcciones y calidad:**
- 3 archivos Python con `py_compile` limpio (0 errores de sintaxis)
- Docstring de `git_integration.py` actualizado con los nuevos endpoints
- Docstring de `m365.py` actualizado con los nuevos endpoints

---

### v23.1.0 (Abril 2026)

**Auditoría de seguridad — batch 2:**
- `key_management.py`: reemplazados `assert` por `RuntimeError` en el key ring JWT
- `ai_modules.py`: límite de 25 MB en endpoint `/ai/voice/transcribe`
- URLs de proveedores IA ahora configurables: `settings.OPENAI_API_URL` y `settings.ANTHROPIC_API_URL`
- Eliminados 5× `__import__()` — sustituidos por imports explícitos
- `.env.example`: `REFRESH_TOKEN_EXPIRE_DAYS=7`, `DEFAULT_USER_PASSWORD` reemplazado por placeholder seguro

**Auditoría de seguridad — batch 1:**
- WebSocket: sistema de **tickets de un solo uso** (`GET /ws/ticket`)
- NexusAgent SSE: autenticación por cookie
- CSV import: límite de **5 MB**
- N+1 queries en `get_budget_status` → GROUP BY con agregación
- Rollbacks explícitos en `login`, `approve_milestone`, `execute_import`



### v24.0 (Abril 2026)

**Nuevas funcionalidades:**
- **Portal cliente multi-proyecto**:
  - `ClientUser` ahora soporta múltiples proyectos mediante la tabla puente `client_user_projects`
  - El dashboard del portal permite seleccionar proyecto cuando el cliente tiene acceso a más de uno
  - Endpoints de mensajes, solicitudes, UAT y documentos validados contra el conjunto de proyectos accesibles
- **ITSM IA (respuestas sugeridas)**:
  - Endpoint `POST /sd/tickets/{id}/ai-suggest` operativo con fallback seguro cuando no hay proveedor IA configurado
  - Integrado en detalle de ticket del frontend para responder más rápido desde soporte
- **BI con cross-filtering**:
  - Filtros cruzados entre widgets (tipo de proyecto, cliente y proyecto)
  - Click en "Top clientes", "Rentabilidad por proyecto" y "Top proyectos por margen" para aplicar filtros contextuales
  - Chips de filtros activos y acción rápida para limpiar filtros
- **Activity Feed**: historial de actividad por proyecto con feed cronológico
- **@Mentions**: menciones de usuarios en comentarios de tareas y tickets con notificaciones
- **Project Health Score**: puntuación automática de salud del proyecto (0-100) basada en SPI, CPI, riesgos y entregas
- **Recurring Tasks**: tareas recurrentes (diaria, semanal, mensual, personalizada)
- **CPM Critical Path**: cálculo automático del camino crítico usando Forward/Backward Pass
- **Resource Demand from Pipeline**: proyección de demanda de recursos desde oportunidades del pipeline
- **Vendor Scorecard**: evaluación de proveedores y subcontratistas con KPIs
- **What-If Simulation**: simulación de escenarios de capacidad y coste

**Internacionalización (i18n):**
- Soporte completo para **8 idiomas**: Español (es), Inglés (en), Francés (fr), Alemán (de), Portugués (pt), Italiano (it), **Polaco (pl)**, **Chino simplificado (zh)**
- **1 377 claves** de traducción para la interfaz de backoffice (`appTranslations.js`)
- Traducciones del portal de cliente en los mismos 8 idiomas (`portalTranslations.js`)
- Selector de idioma por usuario, con editor visual de traducciones para administradores

**Migraciones:**
- `004_v24_features`: timezone por usuario, facturación recurrente, formularios públicos, OAuth apps
- `005_security_hardening`: expansión de columnas cifradas MFA, bloqueo de imputaciones en proyectos cerrados
- `017_mfa_sso_hardening`: challenge MFA one-time, binding de organización en SSO y bootstrap solo con Alembic
- `019_client_user_multiproject`: nueva tabla `client_user_projects` y backfill inicial desde `client_users.project_id`

### v22 y anteriores

- Service Desk ITSM/ITIL completo (tickets, SLA, KB, CMDB, Problemas)
- Portal cliente externo (UAT, Feature Requests, Mensajería, Encuestas)
- Firma electrónica DocuSign/AdobeSign
- Integración Microsoft 365 (Calendar + Teams)
- AI Hub multi-proveedor
- Motor de automatizaciones (reglas if/then)
- OKRs (objetivos y resultados clave)
- EVM (Earned Value Management)
- Rate Cards con overrides
- Búsqueda semántica (sentence-transformers)
- Gestión documental con versionado y permisos granulares
- Timer de imputación con pausa/reanudación
- SSO OIDC (Azure AD, Okta, Google, genérico) con CSRF y JWKS validation
- MFA/2FA TOTP
- Challenge MFA de login con invalidación one-time en base de datos
- GRC (Governance, Risk, Compliance)
- Multi-organización
- Portfolios
- Revenue Recognition
- Contabilidad hub (Xero, QuickBooks)
- GitHub/GitLab integration

---

## 18. Guía de desarrollo

### Añadir un nuevo endpoint

```python
# 1. Crear o editar app/api/v1/endpoints/mi_modulo.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.deps import get_current_user, require_admin

router = APIRouter()

@router.get("/mi-recurso")
def listar(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    # 1. Aplicar scoping por tenant
    # 2. Aplicar ABAC si el recurso es sensible
    # 3. Solo después paginar o serializar resultados
    return {"items": []}

@router.post("/mi-recurso")
def crear(
    payload: dict,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin),
):
    # Solo admin puede crear
    ...
```

```python
# 2. Registrar en app/api/v1/router.py
from app.api.v1.endpoints import mi_modulo
router.include_router(mi_modulo.router, prefix="/mi-recurso", tags=["Mi Módulo"])
```

### Añadir una nueva página frontend

```jsx
// 1. Crear frontend/src/pages/MiPaginaPage.jsx
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'

export default function MiPaginaPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['mi-recurso'],
    queryFn: () => api.get('/mi-recurso').then(r => r.data),
  })

  if (isLoading) return <div>Cargando...</div>
  return <div>{JSON.stringify(data)}</div>
}
```

```jsx
// 2. Registrar en frontend/src/App.jsx
import MiPaginaPage from './pages/MiPaginaPage'
// Dentro del router:
<Route path="/mi-ruta" element={<MiPaginaPage />} />
```

### Añadir un nuevo modelo

```python
# 1. Crear o editar app/models/mi_modelo.py
from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base
import uuid

class MiModelo(Base):
    __tablename__ = "mi_tabla"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nombre = Column(String(200), nullable=False)
    proyecto_id = Column(String, ForeignKey("projects.id"), nullable=True)
```

```python
# 2. Importar en app/db/base.py para que alembic lo detecte
from app.models.mi_modelo import MiModelo  # noqa
```

```bash
# 3. Generar migración
alembic revision --autogenerate -m "add_mi_tabla"
alembic upgrade head
```

### Cifrar datos sensibles

```python
from app.core.encryption import encrypt_value, decrypt_value

# Al guardar:
mi_modelo.api_key = encrypt_value("sk-live-xxxxx")

# Al leer:
api_key_plano = decrypt_value(mi_modelo.api_key)
```

### Convenciones de código

- **Python**: tipado estático donde posible, docstrings opcionales, Ruff para linting (`ruff.toml`)
- **React**: componentes funcionales, hooks, sin class components
- **ESLint**: configuración flat (`eslint.config.js`), 0 errores y 0 advertencias en `main`
- **Variables no usadas en React**: prefijar con `_` (ej. `_unusedVar`)
- **Catches vacíos**: usar `/* noop */` para documentar la intención
- **Imports**: React no necesita importarse en JSX (React 17+ transform)

### Limpieza para deploy

Existe un script de limpieza de artefactos locales en:

- `scripts/clean_deploy_artifacts.sh`

Uso recomendado antes de empaquetar o desplegar:

```bash
# Limpieza segura (caches, logs, cobertura, DB local)
./scripts/clean_deploy_artifacts.sh

# Incluye limpieza de uploads locales de pruebas
./scripts/clean_deploy_artifacts.sh --purge-uploads

# Limpieza profunda local (también elimina .venv y frontend/node_modules)
./scripts/clean_deploy_artifacts.sh --full-local

# Limpieza total local
./scripts/clean_deploy_artifacts.sh --full-local --purge-uploads
```

Notas:

- El script no toca archivos tracked de Git.
- `--full-local` obliga a reinstalar dependencias para volver a desarrollar (`pip install -r requirements.txt` y `npm install` en `frontend/`).

### Variables de entorno en frontend

```bash
# .env (frontend)
VITE_API_URL=http://localhost:8000/api/v1

# Uso en código
const API = import.meta.env.VITE_API_URL || '/api/v1'
```

### WebSocket (tiempo real)

```javascript
// Paso 1: obtener ticket de un solo uso (60s de validez)
const { data } = await api.get('/ws/ticket')  // requiere sesión activa
const ticket = data.ticket

// Paso 2: conectar con el ticket como query param
const ws = new WebSocket(`ws://${window.location.host}/ws?ticket=${ticket}`)
ws.onmessage = (event) => {
  const data = JSON.parse(event.data)
  // Manejar evento
}
```

El ticket se consume al conectar y no puede reutilizarse, evitando que el JWT quede expuesto en logs del servidor.

### Celery (tareas asíncronas)

```bash
# Arrancar worker (requiere Redis)
celery -A app.worker worker --loglevel=info

# Arrancar beat (tareas programadas)
celery -A app.worker beat --loglevel=info
```

### Logging

```python
import logging
logger = logging.getLogger(__name__)

# Niveles: DEBUG, INFO, WARNING, ERROR, CRITICAL
logger.info("Operación completada")
logger.warning(f"Atención: {detalle}")
logger.error(f"Error: {e}", exc_info=True)
```


---

## 19. Flujo coordinado de Feature Requests y Control de Cambios

### Mejoras visuales y de usabilidad planificadas

- Mostrar badge con estado CR junto al estado FR, con tooltip explicativo y borde lateral coloreado.
- Al hacer clic en el badge CR, mostrar modal con detalles del Change Request (descripción, impacto, fechas).
- Notificación toast cuando el estado CR cambia mientras el usuario visualiza la FR (implementado: el backend emite evento WebSocket).
- Filtro de FRs por estado CR en la vista de equipo.
- Notificación por email o sistema interno cuando una CR vinculada cambia de estado relevante.

### Ciclo de vida y reglas de negocio

**Objetivo:** Garantizar que el ciclo de vida de las solicitudes de funcionalidad (FR) y su integración con Control de Cambios (ChangeRequest) es coherente, auditable y seguro.

#### Estados y transiciones de la Feature Request (FR)

- `new` → `reviewing` → `estimated` → `approved` → `in_development` → `done`
- El paso de `estimated` a `approved` solo lo puede hacer el cliente (aprobación explícita).
- Solo al aprobar el cliente, se crea el ChangeRequest asociado (registro en Control de Cambios).
- El paso a `in_development` (ya sea desde backoffice o API) solo cambia el estado de la FR, pero **no crea ni modifica ChangeRequest** si no está aprobada.


#### Lógica backend (sincronización bidireccional)

- Cuando el equipo responde y estima (`status: estimated`), no se crea ChangeRequest.
- Cuando el cliente aprueba (`/decide`, `approved: true`), se crea el ChangeRequest (si no existe) y se vincula a la FR.
- Cuando la FR pasa a `in_development`, `done` o `rejected`, el CR asociado (si existe) se actualiza automáticamente al estado correspondiente (`approved`, `implemented`, `rejected`).
- Cuando el CR cambia a `approved`, `implemented` o `rejected`, la FR asociada se sincroniza automáticamente al estado correspondiente (`in_development`, `done`, `rejected`).
- Si se intenta iniciar desarrollo sin aprobación previa, el backend impide la creación de ChangeRequest y solo actualiza el estado de la FR.

#### Garantía automática

- Hay tests automáticos que aseguran que nunca se crea un ChangeRequest si el cliente no ha aprobado.
- El ciclo de vida es coherente, auditable y seguro para equipo y cliente.

#### Referencias

- [app/api/v1/endpoints/client_portal.py](app/api/v1/endpoints/client_portal.py)
- [tests/test_portal_feature_requests.py](tests/test_portal_feature_requests.py)
- [tests/test_portal_feature_requests_cr_control.py](tests/test_portal_feature_requests_cr_control.py)

---

## 20. Internacionalización y traducciones

El portal de cliente y todos los flujos de Feature Request (FR) y Change Request (CR) han sido revisados para asegurar que **todas las claves de traducción están presentes en los 8 idiomas soportados** (es, en, fr, de, pt, it, pl, zh). No faltan claves en ningún idioma y la experiencia es completamente multilingüe.

_Última revisión: [fecha de hoy]_

---

*Documentación generada: Abril 2026 — Clarive PSA v23.10.1*
