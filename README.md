# contecflow PSA

**contecflow** es una plataforma multiempresa de *Professional Services Automation* (PSA) e ITSM: proyectos y entrega, tiempo y recursos, CRM y finanzas, Service Desk (incidencias, peticiones, problemas, cambios, CMDB, activos, SLA/OLA/UC), BI e inteligencia artificial, portales para clientes y proveedores, y administración de varias empresas en una sola instalación, con auditoría y cumplimiento (GRC) de serie.

Este README es el **manual completo** de la solución:

- **Parte A — Implantación y configuración**, para quien instala, configura, opera y mantiene la plataforma.
- **Parte B — Uso de la aplicación**, para usuarios finales y responsables de cada área: qué es cada módulo, para quién es, cómo se usa paso a paso y consejos.
- **Común**: roles y capacidades, glosario, preguntas frecuentes e índice de la documentación.

Todo lo que aquí se describe está comprobado en el código. Las referencias largas (lista completa de ajustes, manuales detallados por módulo) están en `docs/` y se enlazan desde cada sección; el [índice de la documentación](#45-índice-de-la-documentación) las reúne.

| Dato | Valor |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy, Alembic, Celery + Redis |
| Frontend | React + TypeScript + Vite |
| Base de datos | PostgreSQL (producción, con RLS) o SQLite (desarrollo) |
| Migraciones | 157 revisiones en una sola cadena; cabeza `205_portal_usuarios` |
| Idiomas | Aplicación: español, inglés y chino. Portal de clientes: más idiomas (ver [§17](#17-primeros-pasos-entrar-navegar-menú-e-idiomas)) |
| Arranque | `setup.bat` (Windows) y `setup.sh` (Linux/macOS), también todo en Docker con observabilidad |

## Cómo leer este manual

- **Vas a instalarlo**: [Inicio rápido](#inicio-rápido) → [§2 Requisitos](#2-requisitos) → [§3 Instalación](#3-instalación-y-arranque-setupsh-y-setupbat) → [§6 Configuración](#6-configuración-y-variables-de-entorno).
- **Vas a ponerlo en producción**: [§12 Despliegue en producción](#12-despliegue-en-producción) (lista de comprobación), [§8 Seguridad](#8-seguridad), [§10 Copias](#10-copias-de-seguridad-y-restauración) y [§13 Monitorización](#13-monitorización-y-tareas-programadas).
- **Vas a usarlo**: empieza por [§17 Primeros pasos](#17-primeros-pasos-entrar-navegar-menú-e-idiomas) y ve al módulo que te toque. Si no ves una pantalla, mira [§42 Roles y capacidades](#42-roles-y-capacidades).
- **Algo falla**: [§14 Resolución de problemas](#14-resolución-de-problemas) y [§44 Preguntas frecuentes](#44-preguntas-frecuentes).

Convenciones: las pantallas se nombran como aparecen en español y con su ruta (`/service-desk`); las variables de entorno y ajustes en `MAYÚSCULAS`; las capacidades como `sd.ver`.

## Índice

- [Inicio rápido](#inicio-rápido)
- [Cómo leer este manual](#cómo-leer-este-manual)
- **Parte A — Implantación y configuración**
  - [1. Qué es contecflow y cómo está construido](#1-qué-es-contecflow-y-cómo-está-construido)
  - [2. Requisitos](#2-requisitos)
  - [3. Instalación y arranque (setup.sh y setup.bat)](#3-instalación-y-arranque-setupsh-y-setupbat)
  - [4. Docker y observabilidad](#4-docker-y-observabilidad)
  - [5. Base de datos y migraciones](#5-base-de-datos-y-migraciones)
  - [6. Configuración y variables de entorno](#6-configuración-y-variables-de-entorno)
  - [7. Multiempresa y aislamiento de datos](#7-multiempresa-y-aislamiento-de-datos)
  - [8. Seguridad](#8-seguridad)
  - [9. Integraciones y pruebas de conexión](#9-integraciones-y-pruebas-de-conexión)
  - [10. Copias de seguridad y restauración](#10-copias-de-seguridad-y-restauración)
  - [11. Actualizar a una versión nueva](#11-actualizar-a-una-versión-nueva)
  - [12. Despliegue en producción](#12-despliegue-en-producción)
  - [13. Monitorización y tareas programadas](#13-monitorización-y-tareas-programadas)
  - [14. Resolución de problemas](#14-resolución-de-problemas)
  - [15. GRC: auditoría, retención, RGPD y cumplimiento](#15-grc-auditoría-retención-rgpd-y-cumplimiento)
  - [16. Desarrollo](#16-desarrollo)
- **Parte B — Uso de la aplicación**
  - [17. Primeros pasos: entrar, navegar, menú e idiomas](#17-primeros-pasos-entrar-navegar-menú-e-idiomas)
  - [18. Mi trabajo y Mi día](#18-mi-trabajo-y-mi-día)
  - [19. Mi cuaderno](#19-mi-cuaderno)
  - [20. Proyectos y planificación](#20-proyectos-y-planificación)
  - [21. Imputaciones y partes de horas](#21-imputaciones-y-partes-de-horas)
  - [22. Ausencias](#22-ausencias)
  - [23. Personas y recursos](#23-personas-y-recursos)
  - [24. Service Desk](#24-service-desk)
  - [25. CMDB, software y vulnerabilidades](#25-cmdb-software-y-vulnerabilidades)
  - [26. Licencias y activos (ALM)](#26-licencias-y-activos-alm)
  - [27. Clientes, CRM y pipeline](#27-clientes-crm-y-pipeline)
  - [28. Clientes internos](#28-clientes-internos)
  - [29. Portal de clientes](#29-portal-de-clientes)
  - [30. Proveedores y portal de proveedores](#30-proveedores-y-portal-de-proveedores)
  - [31. Flujo de demanda](#31-flujo-de-demanda)
  - [32. Finanzas: facturación, gastos, rentabilidad y presupuestos](#32-finanzas-facturación-gastos-rentabilidad-y-presupuestos)
  - [33. BI y analítica](#33-bi-y-analítica)
  - [34. BPM: procesos](#34-bpm-procesos)
  - [35. Automatizaciones](#35-automatizaciones)
  - [36. Aprobaciones](#36-aprobaciones)
  - [37. Colaboración: chat, llamadas y reuniones](#37-colaboración-chat-llamadas-y-reuniones)
  - [38. Inteligencia artificial](#38-inteligencia-artificial)
  - [39. MCP: agentes de código externos](#39-mcp-agentes-de-código-externos)
  - [40. Del ticket al PR](#40-del-ticket-al-pr)
  - [41. Configuración: mapa de secciones](#41-configuración-mapa-de-secciones)
- **Común**
  - [42. Roles y capacidades](#42-roles-y-capacidades)
  - [43. Glosario](#43-glosario)
  - [44. Preguntas frecuentes](#44-preguntas-frecuentes)
  - [45. Índice de la documentación](#45-índice-de-la-documentación)

## Inicio rápido

Primer arranque en local (instala dependencias, crea `.env`, aplica migraciones, siembra y arranca API, worker, beat y web):

```bash
./setup.sh demo        # Linux / macOS (o Git Bash): con datos de demostración
./setup.sh clean       # base vacía salvo el usuario admin
./setup.sh start       # arranques siguientes (conserva la base)
./setup.sh stop
```

```bat
rem Windows, en la carpeta del repositorio (en PowerShell: .\setup.bat demo)
setup.bat demo
setup.bat clean
setup.bat start
setup.bat stop
```

| Qué | URL en local | URL con `setup docker` |
|---|---|---|
| Aplicación web | <http://localhost:3000> | <http://localhost:8080> |
| API | <http://localhost:8000/api/v1> | <http://localhost:8080/api/v1> (por nginx) |
| Documentación OpenAPI | <http://localhost:8000/api/v1/docs> | <http://localhost:8080/api/v1/docs> |
| Portal de clientes | <http://localhost:3000/portal> | <http://localhost:8080/portal> |

**Primer acceso.** Usuario `admin` (o su correo, `admin@company.com`) con la contraseña `SUPERADMIN_PASSWORD` del `.env`. El setup la genera al azar si falta o es débil, y la semilla la vuelve a aplicar al superadmin en cada ejecución. Los demás usuarios demo (`ana.torres`, `luis.vega`, `rrhh`…) entran con `DEFAULT_USER_PASSWORD`. El resumen final del setup muestra la de cada usuario (la de `admin` es `SUPERADMIN_PASSWORD`) y solo de los que existen; fuera de `development`/`test` no imprime contraseñas (detalle en [3.9](#39-primer-acceso-y-usuarios-demo)). La documentación OpenAPI no se publica con `ENVIRONMENT=production` salvo `EXPOSE_API_DOCS=1`.

---

# Parte A — Implantación y configuración

---

## 1. Qué es contecflow y cómo está construido

### 1.1 Qué es

contecflow es una plataforma **PSA + ITSM multiempresa**: una sola instalación sirve a varias empresas aisladas entre sí (filtro del ORM y, en PostgreSQL, políticas RLS; ver [7](#7-multiempresa-y-aislamiento-de-datos)). Módulos principales:

- Proyectos, planificación, imputaciones de horas, ausencias y recursos.
- Service Desk (incidencias, peticiones, problemas, cambios, SLA), CMDB, software y vulnerabilidades, licencias y activos (ALM).
- Clientes, CRM, pipeline comercial, portal de clientes, proveedores y flujo de demanda.
- Finanzas (facturación, gastos, rentabilidad, presupuestos), BI y analítica.
- BPM, automatizaciones y motor de aprobaciones.
- Colaboración (chat, llamadas, reuniones), inteligencia artificial, agentes MCP y del ticket al PR.

### 1.2 Arquitectura

```
                    Navegador (SPA React 18)
                           │  mismo origen: cookies httpOnly + comprobación CSRF de Origin
          ┌────────────────┴────────────────────┐
  Local: Vite :3000                      Docker: nginx «web» (127.0.0.1:8080)
  proxy /api → :8000 (con WebSocket)     /api/ → api:8000 · WebSocket (Upgrade) · /health,
          └────────────────┬────────────────────┘  /ready, /status → api · resto → index.html
                           ▼
  ┌──────────────── API FastAPI (app/main.py, uvicorn) ────────────────┐
  │ /api/v1 · /health · /ready · /status · /metrics                    │
  │ endpoints (app/api) → servicios (app/services) → modelos (app/models)│
  │ multiempresa: TenantSession + RLS · CSRF · cabeceras · limitador    │
  └───┬─────────────┬───────────────┬──────────────────┬───────────────┘
      ▼             ▼               ▼                  ▼
  PostgreSQL 16   Redis 7         Ficheros:          Servicios externos:
  (SQLite en      broker Celery,  S3 compatible      8 proveedores de IA, M365,
   desarrollo)    limitador, WS,  (versitygw) o      Jira, Slack, Stripe, Twilio,
      ▲           pub/sub         uploads/ local     DocuSign, SMTP/IMAP…
      │             ▲
  ┌───┴─────────────┴──────────┐    Observabilidad (perfil observability):
  │ Celery worker (app.worker) │    Prometheus ← /metrics (API, worker :9808,
  │ Celery beat (57 entradas)  │    beat :9809, exportadores) → Alertmanager
  └────────────────────────────┘    → Grafana (6 paneles)
```

- **Planificador**: Celery beat (recomendado y el que usan los scripts y Docker) o APScheduler dentro del proceso de la API (`ENABLE_APSCHEDULER=1`, valor por defecto del código), que replica el mismo calendario. Nunca los dos ([13.3](#133-planificador-celery-beat-o-apscheduler)).
- **Ficheros**: con `AWS_ACCESS_KEY` y `AWS_SECRET_KEY` van a S3 (en Docker, el servicio `s3`, versitygw); si no, a `uploads/` (`UPLOAD_DIR`).
- **IA**: `PROVIDER_CATALOG` (`app/services/ai_provider_service/catalogo.py`) declara 8 proveedores: `anthropic`, `openai`, `gemini`, `deepseek`, `groq`, `mistral`, `ollama` y `azure`.
- **OLAP**: fichero DuckDB (`DUCKDB_PATH`) que carga la tarea nocturna `olap_nightly_etl`.

### 1.3 Componentes y versiones

Versiones fijadas en `requirements.txt` y declaradas en `frontend/package.json`:

| Pieza | Versión |
|---|---|
| Python | ≥ 3.10 (`setup.sh`); imagen Docker `python:3.12-slim` |
| FastAPI / Pydantic / pydantic-settings | 0.135.3 / 2.12.5 / 2.14.2 |
| Uvicorn | 0.54.0 (`[standard]` fuera de Windows) |
| SQLAlchemy / Alembic | 2.0.36 / 1.13.0 |
| psycopg2-binary | 2.9.11 (imagen `postgres:16-alpine`) |
| Celery / redis-py / APScheduler | 5.6.3 / 6.4.0 / 3.11.2 (imagen `redis:7-alpine`) |
| PyJWT / bcrypt / slowapi | 2.15.0 / 4.0.1 / 0.1.9 |
| prometheus-client / instrumentator / sentry-sdk | 0.21.1 / 8.1.0 / 2.57.0 |
| boto3 / duckdb / pandas / scikit-learn | 1.42.83 / 1.3.0 / 2.2.3 / 1.5.0 |
| ML opcional (`requirements-ml.txt`) | torch, sentence-transformers, prophet, lightgbm… (lo instala el setup si existe el fichero) |
| React / TypeScript / Vite | ^18.3.1 / ^6.0.3 / ^7.1.12 (imagen `node:20-alpine`) |
| TanStack Query / react-router-dom / axios | ^5.45.0 / ^7.18.3 / ^1.21.1 |
| Tailwind / zod / Vitest / recharts | ^3.4.4 / ^4.6.7 / ^4.1.5 / ^2.12.7 |

### 1.4 Estructura del repositorio

| Carpeta / fichero | Contenido |
|---|---|
| `app/` | Backend: `main.py` (aplicación, middlewares, `/health`, arranque), `worker.py` (Celery y calendario), `api/` (endpoints y routers), `services/` (lógica de negocio), `models/`, `schemas/`, `core/` (configuración, seguridad, métricas, capacidades), `db/` (sesión, multiempresa, RLS, semillas), `integrations/` |
| `alembic/` | Migraciones (`versions/`) y `NAMING_CONVENTION.md` |
| `frontend/` | SPA (`src/`), `nginx.frontend.conf`, `vite.config.js`, scripts de i18n y lint |
| `tests/`, `tests_e2e/` | Pruebas de backend (pytest) y extremo a extremo (Playwright) |
| `scripts/` | Utilidades: migrar, comprobar esquema, rol de BD, copias, despliegue, modo Docker, semillas, auditorías, `ci_local.sh` |
| `deploy/` | `Dockerfile.backend` y `Dockerfile.frontend` |
| `ops/` | Prometheus (objetivos y reglas), Alertmanager (generador de configuración) y Grafana (aprovisionamiento y paneles) |
| `docs/` | Documentación por tema |
| `docker-compose.yml` | Único compose, con perfiles |
| `setup.sh`, `setup.bat` | Instalación y arranque (Linux/macOS y Windows) |
| `.env.example` | Plantilla de variables para el operador |
| `seed_*.json` | Datos de la semilla demo (usuarios, clientes, plantillas de correo) |
| `uploads/`, `backups/` | Ficheros locales y copias (no se versionan) |

---

## 2. Requisitos

### 2.1 Software

| Pieza | Modo local (`setup.sh` / `setup.bat`) | Modo Docker (`setup docker`, producción) |
|---|---|---|
| Python | 3.10 o superior. Si falta, `setup.sh` intenta instalar 3.12 (Homebrew, apt, dnf, yum, pacman, zypper, apk) y `setup.bat` descarga 3.12.7 | Python 3 del sistema solo para `scripts/docker_stack.py` (biblioteca estándar) |
| Node.js y npm | 18 o superior (solo se avisa por debajo); si falta, se instala (`setup.bat` descarga 20.11.0). La imagen usa Node 20 | No hace falta (se construye en la imagen) |
| Docker con Compose v2 | Opcional en `setup.sh`: si está, levanta PostgreSQL y Redis; si no, SQLite. `setup.bat` no lo levanta en modo local, pero usa el Redis de Docker si ya está en marcha | Obligatorio |
| PostgreSQL | Opcional (SQLite por defecto) | 16, en contenedor |
| Redis | Opcional. Con Redis (el de `REDIS_URL`, uno local en 6379 o el de Docker en 6381) el setup arranca Celery worker y beat; sin Redis arranca **sin Celery** y las tareas programadas las ejecuta el planificador integrado de la API (APScheduler), con aviso. Ver [3.2](#32-demo-clean-y-update-paso-a-paso-setupsh) y [13.3](#133-planificador-celery-beat-o-apscheduler) | 7, en contenedor |
| `lsof`, `curl` | `setup.sh` los usa para liberar puertos y esperar a los servicios | — |

### 2.2 Hardware

El repositorio no fija límites de CPU ni memoria en `docker-compose.yml`. Lo único configurado: Redis con `maxmemory` `REDIS_MAXMEMORY` (256 MB por defecto), Prometheus con retención `PROMETHEUS_RETENTION` (15 días) y `PROMETHEUS_RETENTION_SIZE` (5 GB), Alertmanager con `ALERTMANAGER_RETENTION` (120 h), `API_WORKERS` (4 procesos uvicorn) y `WORKER_CONCURRENCY` (4). La primera construcción de imágenes tarda varios minutos.

### 2.3 Puertos

Todos los puertos de Docker se publican solo en `127.0.0.1`.

| Puerto | Servicio | Variable |
|---|---|---|
| 3000 | Vite (web en local) | `FRONTEND_PORT` (`setup.sh`, `setup.bat`, `make`), `VITE_PORT` (Vite) |
| 8000 | API en local | `BACKEND_PORT` (`setup.sh`, `setup.bat`, `make`) |
| 5434 | PostgreSQL (Docker) | `POSTGRES_PORT` (compose), `CF_POSTGRES_PORT` (`setup.sh`) |
| 6381 | Redis (Docker) | `REDIS_PORT` (compose), `CF_REDIS_PORT` (`setup.sh` y `setup.bat`: dónde buscar el Redis de Docker; `setup.sh` también lo publica ahí) |
| 9003 | Almacén S3 (versitygw) | `MINIO_PORT` |
| 8080 | Web con nginx (Docker) | `WEB_PORT` |
| 3001 | Grafana | `GRAFANA_PORT` |
| 9090 | Prometheus | `PROMETHEUS_PORT` |
| 9093 | Alertmanager | `ALERTMANAGER_PORT` |
| 9808 / 9809 | `/metrics` del worker y de beat (solo red interna) | `CELERY_METRICS_PORT` |

---

## 3. Instalación y arranque (setup.sh y setup.bat)

`setup.sh` (Linux, macOS, Git Bash) y `setup.bat` (Windows) son la entrada única. Sin argumentos muestran la ayuda.

### 3.1 Comandos

| Comando | `setup.sh` | `setup.bat` | Qué hace |
|---|---|---|---|
| `demo` | sí | sí (alias `seed`) | Instala o actualiza, migra, carga los datos demo y arranca |
| `clean` | sí | sí (alias `zero`, `cero`, `admin-only`, `admin_only`) | Instala o actualiza, migra, **borra todos los datos** salvo admin y arranca |
| `install` | — | sí | Instala y pregunta el modo de datos (1 = demo, 2 = clean) |
| `start` | sí | sí | Solo arranca, conservando la base; antes aplica migraciones pendientes |
| `start demo` / `start clean` | — | sí | Arranca re-sembrando con ese modo |
| `stop` | sí | sí | Para API, web, worker y beat (los contenedores siguen) |
| `update` | sí | sí | Actualiza dependencias y esquema (migraciones con copia previa y comprobación); no arranca |
| `docker [demo\|clean]` | sí (alias `docker-start`, `docker-up`) | sí (mismos alias) | Todo en Docker: infraestructura, app y observabilidad |
| `docker-status` | sí | sí | Estado de los contenedores y URLs |
| `docker-stop` | sí | sí | Para todos los contenedores de todos los perfiles, sin `-v` (conserva datos) |
| `docker-clean` | sí | sí | Para Docker y borra los volúmenes **regenerables**; conserva PostgreSQL y S3. Solo en desarrollo o pruebas |
| `backup` | sí | sí | Copia local de la base (SQLite o PostgreSQL) y de `uploads/` en `backups/`, con verificación ([10.2](#102-scriptsbackupsh)) |
| `restore <carpeta>` | sí | sí | Verifica la copia, para la app, guarda una copia de lo actual y restaura (pide confirmación; [10.4](#104-restaurar)) |

En `setup.bat`, `SETUP_INIT_MODE=demo|clean` hace `start` no interactivo (CI): `set SETUP_INIT_MODE=demo && setup.bat start`.

Variables que leen los dos lanzadores: `BACKEND_PORT`, `FRONTEND_PORT`, `BACKEND_HOST`, `CF_REDIS_PORT` (y `CF_POSTGRES_PORT` en `setup.sh`) y `CONTECFLOW_TAREAS` (`auto` por defecto; `celery` o `integrado` para forzar el modo de las tareas programadas).

### 3.2 `demo`, `clean` y `update` paso a paso (`setup.sh`)

1. **`setup_backend`**
   - Busca Python 3.10+ (`python3.12` → `python3`), lo instala si falta y crea `.venv` o `venv`.
   - `pip install -r requirements.txt` solo si cambió el fichero (huella en `<venv>/.req_hash`). Igual con `requirements-ml.txt` (`.req_ml_hash`; en macOS instala además `libomp` para LightGBM). Instala `requirements-discovery.txt` si existe o, si no, `boto3` / `kubernetes` cuando el `.env` tiene `AWS_ACCESS_KEY_ID` / `KUBECONFIG` o `K8S_IN_CLUSTER=true`.
   - **`setup_docker_infra`**: si Docker responde (intenta arrancar el daemon y espera hasta 3 min), completa el `.env` (`ensure_compose_required_env`), crea los volúmenes persistentes (`ensure_persistent_volumes`), hace `docker compose up -d` (solo `postgres` y `redis`), espera a PostgreSQL (30 s) y Redis (15 s) y, si `DATABASE_URL` era SQLite o un marcador, la cambia a PostgreSQL en `127.0.0.1:5434` y `REDIS_URL` a `127.0.0.1:6381` (`patch_env_for_docker`). Si algo falla, **vuelve a SQLite** (`revert_env_to_sqlite`) y sigue.
   - Si no hay `.env`, copia `.env.example` (o escribe uno mínimo). Ojo: con Docker, el paso anterior ya ha creado un `.env` mínimo y entonces **no se copia** `.env.example`.
   - Completa el `.env` (ver [3.5](#35-qué-escribe-en-env)) y regenera `SECRET_KEY` si es corta o un marcador.
   - Migra con `scripts/migrar.py` (copia previa si hay migraciones destructivas; [5.4](#54-copia-automática-antes-de-migrar)) y comprueba el esquema real con `scripts/comprobar_esquema.py`. Si falla, **se para**: no arranca con un esquema a medias.
   - Prepara el rol de aplicación sin privilegios (`scripts/rol_de_aplicacion.py`) si la base es PostgreSQL ([5.2](#52-rol-de-aplicación-y-rls)).
   - Si la base no tiene usuarios y es SQLite, la rehace desde cero con Alembic.
   - `sync_demo_passwords` (ver [3.9](#39-primer-acceso-y-usuarios-demo)).
2. **`setup_frontend`**: instala Node si falta y ejecuta `npm install --no-fund --no-audit --prefer-offline --legacy-peer-deps` en `frontend/` solo si cambió `package.json` (huella en `node_modules/.pkg_hash`) o falta Vite.
3. **Datos**: `demo` → `prepare_demo_database` (`python -m app.db.seed`); `clean` → `prepare_admin_only_database` (`python scripts/reset_to_admin_only.py`). Ambos se niegan (salida 2) si `ENVIRONMENT` no es `development`, `dev`, `local`, `test`, `testing` o `demo`. Esos alias los acepta también la API: `Settings` los normaliza (`dev`, `local`, `demo` → `development`; `testing` → `test`), y un valor que no conoce hace que el setup se pare antes de arrancar nada ([6.3](#63-variables-imprescindibles-para-implantar)). `update` se detiene aquí.
4. **`start_services`** (también es todo lo que hace `start`):
   - Con SQLite y `sqlite3` disponible, `PRAGMA quick_check`; si falla, borra `-wal`/`-shm` y vuelve a comprobar.
   - Prepara el frontend si falta, aplica migraciones pendientes y comprueba el esquema.
   - Mata lo que escuche en `BACKEND_PORT` y `FRONTEND_PORT`.
   - **Modo de las tareas programadas** (`scripts/modo_tareas.py`, el mismo en `setup.bat`): busca un Redis que responda — el de `REDIS_URL`, uno local en 6379 o el de Docker en `CF_REDIS_PORT` (6381) con `REDIS_PASSWORD` — y, si el `.env` no tenía `REDIS_URL`, escribe el que respondió. Con Redis: modo **celery**. Sin Redis: modo **integrado**, con un aviso claro, y no se lanzan procesos que fallarían. `CONTECFLOW_TAREAS=celery|integrado` lo fuerza.
   - Arranca la API: `uvicorn app.main:app --host ${BACKEND_HOST:-127.0.0.1} --port $BACKEND_PORT --workers 1` con `ENABLE_APSCHEDULER=0 ENABLE_CELERY_BEAT=1` (celery) o `ENABLE_APSCHEDULER=1 ENABLE_CELERY_BEAT=0` (integrado: APScheduler replica todo el calendario de beat dentro de la API), y espera a `/health` (600 s).
   - **`start_background_jobs`** (solo en modo celery): Celery worker (`--concurrency=2`) y Celery beat (`--schedule /tmp/contecflow-celerybeat-schedule`). Si no siguen vivos a los 3 s, avisa.
   - Limpia la caché de Vite si cambió el código, valida JSX con `frontend/validate.cjs` si existe, arranca `npm run dev -- --port $FRONTEND_PORT` con `API_URL=http://localhost:$BACKEND_PORT`, imprime URLs, el modo de las tareas y los usuarios (`scripts/credenciales_iniciales.py`, [3.9](#39-primer-acceso-y-usuarios-demo)), y abre el navegador. `Ctrl+C` lo para todo.
5. **`stop_services`**: para worker y beat, mata los PID guardados y lo que quede en los dos puertos. Si hay contenedores en marcha, recuerda `docker compose down` (sin borrar datos).

Para abrir la API a la red local: `BACKEND_HOST=0.0.0.0 ./setup.sh start`.

### 3.3 Diferencias de `setup.bat` (Windows)

- **No levanta PostgreSQL ni Redis en Docker** en modo local: usa la `DATABASE_URL` del `.env` (SQLite por defecto). Docker solo interviene en `docker`, `docker-status`, `docker-stop` y `docker-clean`.
- El `.env` nuevo lo escribe desde cero (no copia `.env.example`). `REDIS_URL` la escribe `scripts/modo_tareas.py` al arrancar si encuentra un Redis que responda (local en 6379 o el de Docker en 6381). Si no hay ninguno, arranca en modo **integrado**: avisa en un recuadro `[AVISO]`, la API corre con `ENABLE_APSCHEDULER=1` y **no lanza** las ventanas de worker y beat. Antes (hasta el 23-11-2026) las lanzaba siempre y morían sin Redis, y no corría ninguna tarea programada.
- Fija `PYTHONUTF8=1` para que el sembrado no falle por la página de códigos de la consola.
- Instala `pip-system-certs` (certificados de Windows para Python).
- **Base nueva o sin usuarios (SQLite)**: borra el fichero, crea el esquema con `Base.metadata.create_all` y lo marca con `alembic stamp head`. Con usuarios: `scripts/migrar.py` + `scripts/comprobar_esquema.py`. Después, `apply_migrations` vuelve a migrar y comprobar.
- Puertos: respeta `BACKEND_PORT` y `FRONTEND_PORT` si están definidos (`set BACKEND_PORT=8010` antes de `setup.bat start`; 8000 y 3000 por defecto) y pasa `API_URL` al proxy de Vite. `BACKEND_HOST` también se respeta.
- Lanza cada proceso en una ventana minimizada («Contecflow Backend», «Contecflow Worker», «Contecflow Beat», «Contecflow Frontend»); `stop` las cierra por título y libera los puertos. Espera hasta 180 s a backend y frontend.
- Worker con `--pool=solo` (Celery en Windows no usa el pool por defecto), solo en modo celery.
- `backup` y `restore <carpeta>` llaman a `scripts/copia_local.py` ([10](#10-copias-de-seguridad-y-restauración)); `restore` verifica la copia antes de parar nada.

### 3.4 Modo Docker (`setup docker`)

Lo hace `scripts/docker_stack.py` (igual en los dos lanzadores): completa el `.env`, crea los volúmenes persistentes, construye y levanta infraestructura + `app` + `observability`, intenta `host-metrics` aparte, espera a la API (5 min), alinea la contraseña de Grafana y, con `demo`/`clean`, siembra dentro del contenedor `api`. Detalle en [4](#4-docker-y-observabilidad).

### 3.5 Qué escribe en `.env`

Nunca sobrescribe un valor válido; solo rellena lo que falta o es un marcador (`CHANGE_ME…`, `REPLACE_ME…`, `TODO…`, `PLACEHOLDER…`).

| Variable | Quién | Valor |
|---|---|---|
| `SECRET_KEY` | ambos | 64 hex aleatorios si falta, mide < 32 o es un marcador (`setup.bat`: `scripts/rotar_secret_key.py`) |
| `CLIENT_PORTAL_SECRET`, `WEBHOOK_SECRET` | `setup.sh` | 64 hex aleatorios si faltan (`setup.bat` añade un valor fijo de desarrollo a `CLIENT_PORTAL_SECRET` si falta) |
| `SUPERADMIN_EMAIL` | ambos | `admin@company.com` si falta |
| `SUPERADMIN_PASSWORD`, `DEFAULT_USER_PASSWORD` | ambos | Aleatorias (+ `Aa1!`) si faltan o son débiles (`setup.sh` también sustituye `contecflow2024!`) |
| `ENVIRONMENT` | ambos | `development` si falta; si el valor no es canónico ni un alias admitido, el setup se para |
| `POSTGRES_USER`, `POSTGRES_DB`, `MINIO_ROOT_USER` | `setup.sh` con Docker, `docker_stack.py` | `contecflow` |
| `POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD` | ídem | Aleatoria; si el volumen ya existe, `contecflow_dev` para no romper la autenticación |
| `REDIS_PASSWORD` | ídem | Aleatoria (Redis con `requirepass`; la app la añade a `REDIS_URL`) |
| `DATABASE_URL`, `REDIS_URL` | `setup.sh` con Docker | PostgreSQL `127.0.0.1:5434` y Redis `127.0.0.1:6381` |
| `REDIS_URL` | ambos, al arrancar (`scripts/modo_tareas.py`) | El primer Redis que responda (6379 local o el de Docker), solo si faltaba |
| `APP_DB_USER`, `APP_DB_PASSWORD`, `DATABASE_MIGRATIONS_URL` | `scripts/rol_de_aplicacion.py`, `docker_stack.py` | Rol `contecflow_app` con contraseña generada; las migraciones van con el dueño |
| `METRICS_AUTH_TOKEN`, `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD` | `docker_stack.py` | Aleatorios (`admin` como usuario) |
| `ALLOWED_ORIGINS` | `docker_stack.py` | Añade el origen de la web (`http://localhost:8080`); sin él el login da 403 por CSRF |

El `.env` contiene secretos: no se sube al repositorio. Lista completa de variables: [6](#6-configuración-y-variables-de-entorno) y `docs/REFERENCIA_DE_AJUSTES.md`.

### 3.6 Logs y PID

| Proceso | Linux / macOS (`setup.sh`) | Windows (`setup.bat`) |
|---|---|---|
| API | `/tmp/contecflow-backend.log` (PID en `/tmp/contecflow-backend.pid`) | `%TEMP%\contecflow-backend.log` y `.err.log` |
| Web (Vite) | `/tmp/contecflow-frontend.log` (`.pid`) | `%TEMP%\contecflow-frontend.log` y `.err.log` |
| Worker | `/tmp/contecflow-worker.log` (`.pid`) | `%TEMP%\contecflow-worker.log` |
| Beat | `/tmp/contecflow-beat.log` (`.pid`); calendario en `/tmp/contecflow-celerybeat-schedule` | `%TEMP%\contecflow-beat.log`; `%TEMP%\contecflow-celerybeat-schedule` |
| Docker | `docker compose logs -f api worker beat` | igual |

### 3.7 Puertos y host

`BACKEND_PORT=8010 FRONTEND_PORT=3010 ./setup.sh start` cambia los puertos en Linux/macOS; en Windows, `set BACKEND_PORT=8010` y `set FRONTEND_PORT=3010` antes de `setup.bat start`; con `make`, `make dev BACKEND_PORT=8010`. `CF_POSTGRES_PORT` y `CF_REDIS_PORT` cambian los que se escriben en `DATABASE_URL`/`REDIS_URL` y, en `setup.sh`, también dónde publica Docker PostgreSQL y Redis. Si cambias `FRONTEND_PORT`, añade el origen nuevo a `ALLOWED_ORIGINS` en un `.env` ya creado.

### 3.8 Instalación manual (sin los scripts)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # y edítalo: SECRET_KEY, contraseñas, DATABASE_URL, REDIS_URL
python scripts/migrar.py && python scripts/comprobar_esquema.py
ENVIRONMENT=development python -m app.db.seed          # o: python scripts/reset_to_admin_only.py
ENABLE_APSCHEDULER=0 ENABLE_CELERY_BEAT=1 uvicorn app.main:app --reload --port 8000
celery -A app.worker.celery_app worker --loglevel=info  # Windows: añade --pool=solo
celery -A app.worker.celery_app beat --loglevel=info
cd frontend && npm install && npm run dev               # :3000, proxy de /api a :8000
```

Sin Celery beat, arranca la API con `ENABLE_APSCHEDULER=1` (valor por defecto) para que el calendario corra dentro del proceso. No actives los dos: la API no arranca. El frontend no necesita `.env`: usa `/api/v1` y el proxy de Vite; si defines `VITE_API_URL`, debe terminar en `/api/v1`.

### 3.9 Primer acceso y usuarios demo

- El login acepta usuario o correo.
- **`admin`** (superadmin): contraseña `SUPERADMIN_PASSWORD` del `.env`. La semilla (`app/db/seed_parts/core.py`) la reaplica y reactiva la cuenta en cada ejecución, y `reset_to_admin_only.py` también. Cambiarla desde la interfaz no sobrevive a un nuevo `demo`: cámbiala también en el `.env`.
- **Correo de `admin`** en `demo`: sale de `seed_users_data.json` (`admin@company.com`), no de `SUPERADMIN_EMAIL`; en `clean` se usa `SUPERADMIN_EMAIL`.
- **Resto de usuarios demo** (`seed_users_data.json`): `ana.torres` (pm), `luis.vega` (employee), `marta.gil`, `carlos.ruiz` (pm), `sara.lope`, `diego.mora`, `elena.pardo` y `rrhh` (hr), con `DEFAULT_USER_PASSWORD`.
- **`sync_demo_passwords`** (`scripts/sincronizar_contrasenas_demo.py`, solo con `ENVIRONMENT` de desarrollo o pruebas): cuando cambian `DEFAULT_USER_PASSWORD` o `SUPERADMIN_PASSWORD` respecto a la huella SHA-256 de `<venv>/.pwd_hash`, alinea las contraseñas con la misma regla que la semilla: `admin` con `SUPERADMIN_PASSWORD` y `ana.torres`, `luis.vega` y `rrhh` con `DEFAULT_USER_PASSWORD`. Hasta el 23-11-2026 le ponía a `admin` `DEFAULT_USER_PASSWORD`, y en Windows perdía los `!` de la contraseña.
- **Resumen final del setup** (`scripts/credenciales_iniciales.py`, en `setup.sh` y `setup.bat`): lista solo los usuarios de prueba que existen y están activos (en `clean`, solo `admin`), cada uno con su contraseña real. Con `ENVIRONMENT` distinto de `development`/`test` no imprime ninguna: dice de qué variable del `.env` sale.
- **Restablecer el admin sin borrar nada**: `make init-admin` o `python scripts/reset_to_admin_only.py --solo-admin` crea o reactiva `admin` con `SUPERADMIN_EMAIL` y `SUPERADMIN_PASSWORD`, cierra sus sesiones y lo deja en la auditoría (vale en cualquier entorno).
- Primer administrador en producción (sin semilla): [12.3](#123-primer-administrador).

---

## 4. Docker y observabilidad

### 4.1 Perfiles y servicios

Un único `docker-compose.yml` (proyecto `contecflow`). Los escenarios se eligen con perfiles:

| Perfil | Servicios | Uso |
|---|---|---|
| (ninguno) | `postgres` (16-alpine), `redis` (7-alpine) | Desarrollo: la app corre en local |
| `s3` | `s3` (versitygw v1.8.0, fijado por digest) | Probar el almacén S3 en local |
| `app` | `s3`, `migrate`, `api`, `worker`, `beat`, `web` | Producción |
| `observability` | `prometheus`, `alertmanager`, `grafana`, `postgres-exporter`, `redis-exporter` | Métricas, alertas y paneles |
| `host-metrics` | `node-exporter`, `cadvisor` | Métricas de máquina y contenedores |

```bash
docker compose up -d                                  # solo infraestructura
docker compose --profile app up -d                    # + aplicación
docker compose --profile observability up -d         # + observabilidad
docker compose down                                   # apaga, conserva datos
```

Qué hace cada servicio de la aplicación:

- **`migrate`**: `alembic upgrade head && python -m app.db.rls`. `api`, `worker` y `beat` esperan a que termine bien (`service_completed_successfully`): con una migración rota la aplicación no arranca.
- **`api`**: uvicorn con `API_WORKERS` procesos (4), `METRICS_ENABLED=1`, `TRUST_PROXY_HEADERS=1`, `TRUSTED_PROXY_CIDRS` = rangos privados (ajustable con `CONTECFLOW_PROXY_CIDRS`) y `--no-proxy-headers`. **No publica puerto**: solo la alcanza nginx.
- **`worker`** (`--concurrency=${WORKER_CONCURRENCY:-4}`) y **`beat`** (singleton). El compose fija `ENABLE_APSCHEDULER=0` y `ENABLE_CELERY_BEAT=1`.
- **`web`**: nginx con el frontend construido.
- La aplicación conecta con el rol `APP_DB_USER` (`contecflow_app`); las migraciones, con el dueño `POSTGRES_USER` (`DATABASE_MIGRATIONS_URL`). Ficheros en el servicio `s3` (`AWS_S3_ENDPOINT_URL=http://s3:9000`, bucket `MINIO_BUCKET`, por defecto `contecflow-documents`).
- Variables obligatorias con `${VAR:?}` (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`): si faltan, `up` falla en vez de usar un valor por defecto.
- `ENVIRONMENT`: el compose pone `production` si no está en `.env` (`setup docker` escribe `development` cuando falta).

### 4.2 Volúmenes persistentes

| Volumen | Tipo | Contenido |
|---|---|---|
| `contecflow_postgres_data` | **externo** | Base de datos |
| `contecflow_s3_data` | **externo** | Documentos y ficheros |
| `contecflow_redis_data`, `contecflow_prometheus_data`, `contecflow_alertmanager_data`, `contecflow_grafana_data` | regenerables | Cola, series, silencios, sesiones de Grafana |

Los externos (`external: true`) no los crea ni los borra compose: un `docker compose down -v` no puede perderlos. Por eso `setup.sh` (`ensure_persistent_volumes`) y `docker_stack.py` los crean si faltan. En una máquina nueva sin los scripts:

```bash
docker volume create contecflow_postgres_data
docker volume create contecflow_s3_data
```

`docker-clean` borra solo los regenerables y lo dice. Para borrar de verdad los datos: `docker volume rm contecflow_postgres_data contecflow_s3_data`.

### 4.3 `scripts/docker_stack.py`

Lo llaman `setup.sh docker` y `setup.bat docker` (`arrancar [demo|clean]`, `estado`, `parar`). Usa solo la biblioteca estándar.

1. Comprueba Docker y, si el daemon está parado, intenta arrancarlo.
2. Completa el `.env` con lo que falta ([3.5](#35-qué-escribe-en-env)); si no hay `.env`, crea uno mínimo con secretos aleatorios.
3. Crea los volúmenes persistentes; nunca los borra.
4. `docker compose --profile app --profile observability up -d --build`. Si `migrate` falla, enseña su log y para.
5. Intenta `--profile host-metrics`; si no arranca (habitual en Docker Desktop), avisa y sigue.
6. Espera a que la API esté sana, comprueba worker, beat, web, Prometheus y Alertmanager, y alinea la contraseña del admin de Grafana con el `.env`.
7. Siembra si se pide (`demo`/`clean`); si la base no tiene usuarios, avisa. Enseña las URLs.

### 4.4 Imágenes y nginx

- `deploy/Dockerfile.backend`: `python:3.12-slim`, `pip install -r requirements.txt` (sin el stack ML), usuario sin privilegios `appuser` (uid 10001), puerto 8000. Imagen `CONTECFLOW_APP_IMAGE` (por defecto `contecflow-api:local`).
- `deploy/Dockerfile.frontend`: `node:20-alpine` (`npm ci && npm run build`) + `nginx:1.27-alpine`. Imagen `CONTECFLOW_WEB_IMAGE`.
- `frontend/nginx.frontend.conf`: sirve la SPA y hace de proxy a la API por el mismo origen (sin CORS, cookies httpOnly). Pasa `/api/`, los WebSocket (`/api/v1/ws/…`, colaboración y tiempo real de BI) con `Upgrade`, `/health`, `/ready`, `/status`, `/widget/ticket.js`. **No pasa `/metrics`**: Prometheus lo lee en `api:8000`. Límite de cuerpo 110 MB, CSP, `X-Frame-Options: DENY`, `nosniff`, caché larga para estáticos y `no-store` para `index.html`. Propaga `X-Forwarded-For/-Proto/-Host` y `X-Real-IP`.
- TLS y dominio público los pone un proxy por delante de `WEB_PORT` (no está en el compose).

### 4.5 Prometheus, Alertmanager y Grafana

| Pieza | URL | Configuración |
|---|---|---|
| Grafana | <http://localhost:3001> | `ops/grafana/provisioning/` y 6 paneles en `ops/grafana/dashboards/` (Plataforma, Negocio por empresa, Seguridad, IA, Service desk y SLA, Riesgo y vulnerabilidades). No arranca con `GRAFANA_ADMIN_PASSWORD` vacía o `admin` |
| Prometheus | <http://localhost:9090> | `ops/prometheus/prometheus.yml` (objetivos: api, worker, beat, exportadores, node, cAdvisor) y reglas en `ops/prometheus/rules/` |
| Alertmanager | <http://localhost:9093> | `ops/alertmanager/generar-config.sh` escribe la configuración en un tmpfs a partir de `ALERT_WEBHOOK_URL`, `ALERT_EMAIL_*`, `ALERT_SMTP_*` |

**`/metrics`**: se activa con `METRICS_ENABLED=1` (el contenedor `api` lo fuerza). Con `METRICS_AUTH_TOKEN` exige `Authorization: Bearer <token>`; sin token responde 401 fuera de `development`/`test`. El token también puede venir del ajuste en vivo del mismo nombre (rotación sin redesplegar). Prometheus lo lee de un fichero en tmpfs que se escribe al arrancar desde `METRICS_AUTH_TOKEN`.

Paneles aprovisionados sin edición en la interfaz: para cambiarlos se edita `ops/grafana/generar_dashboards.py` y se ejecuta `python ops/grafana/generar_dashboards.py ops/grafana/dashboards`.

**Docker Desktop (Windows/macOS)**: node-exporter mide la máquina virtual Linux de Docker, no el anfitrión; cAdvisor puede no arrancar. Si falla, los paneles de contenedores quedan vacíos y la alerta informativa `ObjetivoDeMetricasCaido` lo señala.

Métricas, alertas, cardinalidad y variables: `docs/OBSERVABILIDAD.md`.

### 4.6 Pasar los datos de un almacén S3 a otro

El almacén es versitygw sobre el volumen `contecflow_s3_data`, con cada objeto como fichero normal. No se reutiliza un volumen antiguo de MinIO (`contecflow_minio_data`): MinIO guarda los objetos en su propio formato (`xl.meta`) y versitygw montado encima serviría eso como si fueran objetos. Para traer documentos de un MinIO antiguo, se copian por la API de S3 mientras el antiguo sigue levantado:

```bash
docker compose --profile s3 up -d s3
aws() { docker run --rm --network host -v "$PWD/copia-s3:/copia" \
  -e AWS_ACCESS_KEY_ID="$1" -e AWS_SECRET_ACCESS_KEY="$2" \
  public.ecr.aws/aws-cli/aws-cli "${@:3}"; }
# 1) del MinIO antiguo (9000) a una carpeta del anfitrión
aws <usuario-minio> <secreto-minio> s3 sync s3://contecflow-documents /copia \
  --endpoint-url http://127.0.0.1:9000
# 2) de la carpeta al almacén nuevo (9003)
aws "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" s3 sync /copia s3://contecflow-documents \
  --endpoint-url http://127.0.0.1:9003
```

El mismo procedimiento sirve para cualquier S3 compatible (cambia los `--endpoint-url`). `--network host` funciona en Linux; en Docker Desktop no está comprobado. versitygw comprueba la región de la firma: `AWS_REGION` (por defecto `eu-west-1`) debe ser la misma en la app y en el servicio `s3` (el compose usa la misma variable).

---

## 5. Base de datos y migraciones

### 5.1 Motores y `DATABASE_URL`

| Motor | Uso | `DATABASE_URL` |
|---|---|---|
| SQLite | Desarrollo (por defecto en `.env.example` y en `setup.bat`) | `sqlite:///./contecflow.db` |
| PostgreSQL 16 | Producción y desarrollo con Docker | `postgresql+psycopg2://usuario:clave@host:5432/base` |

Con PostgreSQL, `DATABASE_MIGRATIONS_URL` (si existe) es la conexión del dueño del esquema que usan las migraciones. `alembic/env.py` toma la URL de `Settings`.

### 5.2 Rol de aplicación y RLS

Con PostgreSQL, la aplicación no debe conectar como dueño ni superusuario (se saltan las políticas RLS):

- `scripts/rol_de_aplicacion.py` (lo llaman `setup.sh` y `setup.bat`): si `DATABASE_URL` es PostgreSQL, crea o actualiza con `python -m app.db.rls` el rol `APP_DB_USER` (por defecto `contecflow_app`, sin superusuario ni `BYPASSRLS`) y las políticas; guarda en `.env` `APP_DB_USER`, `APP_DB_PASSWORD`, `DATABASE_MIGRATIONS_URL` (dueño) y `DATABASE_URL` con el rol. Imprime `OK`, `SKIP` o `FAIL` y nunca para el setup. `CONTECFLOW_DB_APP_ROLE=0` lo omite.
- En Docker lo hace el servicio `migrate`.
- Las políticas se reaplican en cada `alembic upgrade`, así que una tabla nueva no se queda sin política.
- En `staging`/`production` (o con `RLS_REQUIRED=1`) la API no arranca si RLS no está armado. Detalle: [7](#7-multiempresa-y-aislamiento-de-datos).

### 5.3 Migraciones con Alembic

Alembic es el único camino del esquema. La API **no migra al arrancar**; solo comprueba ([5.5](#55-comprobación-del-esquema)).

- Cadena lineal de 157 revisiones; cabeza actual **`205_portal_usuarios`**. La fuente de verdad es `python -m alembic heads`.
- **`scripts/migrar.py`** (lo usan `setup.sh`, `setup.bat` y `update`): se niega si hay dos cabezas (y dice cómo arreglarlo), hace la copia previa si toca y aplica `upgrade head`. Sale siempre con 0 o 1.
- Docker: servicio `migrate` (`alembic upgrade head` + RLS). `make migrate` ejecuta lo mismo que los lanzadores: `scripts/migrar.py` (con copia previa) y `scripts/comprobar_esquema.py`.

```bash
python scripts/migrar.py                 # lo recomendado (copia previa + una sola cabeza)
python -m alembic current                # revisión de la base
python -m alembic heads                  # debe devolver UNA cabeza
python -m alembic downgrade -1           # volver un paso (no siempre restaura: ver abajo)
```

Varias revisiones no tienen `downgrade` real (borran datos sin vuelta atrás). Para volver atrás, restaura una copia ([10](#10-copias-de-seguridad-y-restauración)). Quien escribe migraciones: `alembic/NAMING_CONVENTION.md` y [16.4](#164-añadir-un-endpoint-un-servicio-una-migración-un-ajuste-o-una-capacidad).

### 5.4 Copia automática antes de migrar

`scripts/copia_antes_de_migrar.py`, llamado por `migrar.py` antes de `upgrade head`:

1. Calcula las revisiones pendientes (de la actual a la cabeza). Una base nueva (sin revisión) no se copia.
2. Con `MIGRATION_BACKUP_MODE=destructive` (por defecto) copia solo si alguna pendiente es destructiva: su `upgrade()` contiene `op.drop_table`, `drop_column`, `DELETE FROM`, `TRUNCATE` o `DROP TABLE/COLUMN`. `always` copia siempre que haya pendientes; `off` nunca.
3. SQLite: copia consistente con la API de backup de `sqlite3` (vale con la app arrancada). PostgreSQL: `pg_dump -Fc` si está en el `PATH` (contraseña por `PGPASSWORD`); si no está, **avisa y sigue sin copia**.
4. Deja la copia en `MIGRATION_BACKUP_DIR` (por defecto `backups/`) como `antes_de_migrar_<fecha>_<revisión-origen>.db` o `.dump`.
5. Si la copia falla, **no migra** (salida 1), salvo `MIGRATION_BACKUP_MODE=off`.

Las copias contienen datos personales: mismo control de acceso y retención que la base. Restaurarlas:

```bash
# SQLite: con la app parada
cp backups/antes_de_migrar_<fecha>_<rev>.db contecflow.db      # el fichero de DATABASE_URL
# PostgreSQL
pg_restore --clean --if-exists --no-owner -d "<url del dueño>" backups/antes_de_migrar_<fecha>_<rev>.dump
```

Tras restaurar, el código sigue esperando la cabeza nueva: corrige la causa del fallo y vuelve a migrar, o vuelve también a la versión anterior del código.

### 5.5 Comprobación del esquema

- **`scripts/comprobar_esquema.py`** (después de cada migración en los setup): compara tablas y columnas de los modelos con la base real. Si falta algo, lo lista y sale con 1. Detecta bases marcadas con `alembic stamp` sin haber ejecutado las revisiones. No repara nada.
- **Al arrancar la API** (`app/main.py`): compara `alembic_version` con las cabezas del código y, si se define, con `EXPECTED_ALEMBIC_REVISION`. Con `FAIL_ON_SCHEMA_DRIFT` sin definir, aborta en `staging`/`production` y solo avisa en el resto; `FAIL_ON_SCHEMA_DRIFT=1/0` lo fuerza.
- **`scripts/paridad_postgres.py`**: paridad columna a columna (tipos, nulos, índices, claves, enums) entre un PostgreSQL migrado y los modelos. `--url <base migrada>` o `--servidor <url> --migrar`. Sale con 1 si hay diferencias reales.

### 5.6 De SQLite a PostgreSQL

```bash
python -m app.db.migrate_to_pg --sqlite-path ./contecflow.db --pg-url postgresql://u:p@host:5432/base
```

Crea las tablas desde los modelos (`create_all`), copia los datos tabla a tabla en lotes de 500 y compara recuentos. No pasa por Alembic: después marca la base con `python -m alembic stamp head`, ejecuta `scripts/comprobar_esquema.py` y prepara el rol con `scripts/rol_de_aplicacion.py`. **No verificado en ejecución.**

### 5.7 Semillas

| Orden | Qué hace |
|---|---|
| `python -m app.db.seed` | Datos demo (`setup demo`): organización «Consultora Contecflow SL», usuarios de `seed_users_data.json`, clientes de `seed_clients_data.json`, plantillas de correo y datos de proyectos, Service Desk, ITSM, ALM… Idempotente por registro |
| `python scripts/reset_to_admin_only.py` | **Borra todos los datos** y deja la organización por defecto y `admin` con `SUPERADMIN_EMAIL`/`SUPERADMIN_PASSWORD` (`setup clean`) |
| `python scripts/seed_full_data.py` | Generador más pesado (`make seed-full`; `make seed` es `python -m app.db.seed`) |

Las dos primeras se niegan (salida 2) si `ENVIRONMENT` no es de desarrollo o pruebas (`app/core/entorno.py`). Las rutas de los JSON se cambian con `SEED_USERS_DATA_PATH`, `SEED_CLIENTS_DATA_PATH` y `SEED_EMAIL_TEMPLATES_PATH`.

---

## 6. Configuración y variables de entorno

contecflow se configura en dos capas: el fichero `.env`, que se lee al arrancar, y los ajustes en vivo, que se
cambian desde la aplicación sin reiniciar. Las credenciales de las integraciones van aparte, cifradas y por empresa.

Esta sección explica cómo funcionan las capas y lista lo que hay que tocar sí o sí para implantar. La lista
completa (704 campos de `Settings` y 440 claves en vivo, con su defecto y su significado) está en
[`docs/REFERENCIA_DE_AJUSTES.md`](docs/REFERENCIA_DE_AJUSTES.md). El mapa de la pantalla de Configuración está en
[§41](#41-configuración-mapa-de-secciones) y en [`docs/CONFIGURACION.md`](docs/CONFIGURACION.md).

### 6.1 Las dos capas

| Capa | Dónde vive | Quién la cambia | Cuándo surte efecto |
|---|---|---|---|
| Entorno | `.env` → `app/core/config.py` (`Settings`, pydantic-settings) y los *mixins* de `app/core/config_groups/` | El operador del servidor | Al reiniciar API, worker y beat |
| Ajustes en vivo | Tabla `app_settings` de la base | Un administrador desde **Configuración** | En 60 s como máximo |
| Credenciales de integración | Tabla de credenciales, cifradas | Un administrador desde **Configuración → Integraciones → Credenciales de integraciones** (`/settings/integrations`) | En 60 s como máximo |

**Entorno.** `Settings` se construye una vez al importar la aplicación. Una variable desconocida se ignora
(`extra="ignore"`). Los validadores de `app/core/config.py` **impiden arrancar** si:

- `SECRET_KEY` es débil o un valor de plantilla (`CHANGE_ME_*`);
- `ENVIRONMENT` no es `development`, `test`, `staging` ni `production` ni uno de sus alias (`dev`, `local`, `demo`, `testing`, `stage`, `pre`, `preprod`, `prod`, `prd`, que se normalizan al canónico);
- `JWT_ALGORITHM` no es HS256, HS384 ni HS512;
- `DEFAULT_USER_PASSWORD`, `CLIENT_PORTAL_SECRET` o `SUPERADMIN_PASSWORD` tienen un valor de plantilla.

En `staging` y `production` exigen además `WEBHOOK_SECRET` e `INBOUND_EMAIL_SECRET` (24 caracteres o más) y
rechazan `localhost` en `ALLOWED_ORIGINS`, `FRONTEND_URL`, `BACKEND_URL`, `BASE_URL`, `WEBAUTHN_ORIGIN` y
`WEBAUTHN_RP_ID`. `app/core/comprobacion_de_produccion.py` añade otras comprobaciones de arranque: `APP_PUBLIC_URL`
en localhost, un remitente `.local` sin `SMTP_FROM`, `DOCUSIGN_DEMO=true` en producción o Adobe Sign sin región.

**Ajustes en vivo.** El catálogo es `RUNTIME_FLAG_GROUPS` (`app/services/settings_service/_catalogo.py`): 440 claves
en 32 grupos (`sla`, `service_desk`, `tenants`, `audit`, `password_policy`, `account_security`, `locale`, `tokens`,
`ai`, `storage`, `security_network`…). Se editan en **Configuración → Sistema → Config. dinámica**
(`/settings/runtime-flags`, capacidad `org.administrar`). Algunos grupos tienen pantalla propia y no salen allí:
la política de cuenta (Seguridad de cuentas), el service desk y la traducción.

Cómo se resuelve una clave (`app/services/settings_service/runtime.py`):

1. la fila de la empresa (`organization_id` = la empresa activa);
2. la fila global (`organization_id IS NULL`);
3. el valor de `settings.<CLAVE>` que viene del `.env` (o el defecto del código).

Cada lectura se guarda en caché del proceso 60 s. Al escribir, la caché se invalida en ese proceso y, si hay
`REDIS_URL`, en todos los demás por *pub/sub* (`app/core/settings_pubsub.py`). Sin Redis, los otros procesos
tardan hasta 60 s en ver el cambio.

Reglas que conviene conocer:

- **Si hay fila en la base, gana la base.** Cambiar el `.env` de una clave que ya tiene fila no hace nada.
- **No toda variable tiene ajuste en vivo.** Solo las claves del catálogo. En la referencia, la columna
  «Consumer» dice si la clave se lee en caliente (`rt`) o solo al arrancar (`static`).
- **Ajustes de plataforma.** Algunas claves solo las cambia el superadmin y solo en la fila global
  (`AJUSTES_DE_PLATAFORMA` en `runtime.py`): rotación de claves, `REFRESH_TOKEN_EXPIRE_DAYS`,
  `TRUST_PROXY_HEADERS`, `TRUSTED_PROXY_CIDRS`, `METRICS_AUTH_TOKEN`, cuarentena de baja de empresas,
  «entrar como» y cupos por defecto de empresa nuevas, entre otras. Un administrador de empresa recibe 403
  (`ajuste_solo_superadmin`).
- **Auditoría.** Cada cambio queda registrado con valor anterior y nuevo, actor, IP y navegador
  (`GET /api/v1/settings/audit-log`).

**Ajustes por empresa.** Moneda, IVA, jornada, capacidad semanal, zona horaria e idioma por defecto son por
empresa (grupo `locale`). El código los lee con `ajuste_de_empresa()` (`settings_service/por_empresa.py`), que
toma la empresa del registro (proyecto, factura, usuario…) o de la sesión. Se editan en **Configuración → Empresa y
marca → General** (`/settings/general`).

**Credenciales de integración.** Cada proveedor (SMTP, buzón del service desk, S3, Microsoft Graph, Slack, Twilio,
WhatsApp, Stripe, DocuSign, Adobe Sign, proveedores de IA, DeepL, Azure Translator, secretos de webhooks,
OpenExchangeRates, fuentes de uso de licencias, contecmind, contecintelligence, Del ticket al PR) declara sus
campos en `app/services/integration_credentials_service.py`. Los secretos se cifran antes de guardarse y la pantalla
solo muestra si están puestos, nunca el valor. Si una empresa no tiene fila, la mayoría de proveedores cae a la
variable de entorno equivalente; vaciar el campo vuelve a ella. Excepción: Microsoft 365 / Graph no cae a los
`AZURE_*` salvo con `M365_PLATFORM_CREDENTIALS_ENABLED=true` (ver [§9](#9-integraciones-y-pruebas-de-conexión)).

### 6.2 `.env.example`: la plantilla

`.env.example` es la plantilla comentada. `setup.sh` y `setup.bat` la copian a `.env` si no existe y rellenan los
secretos que faltan (ver [§3](#3-instalación-y-arranque-setupsh-y-setupbat)). Cada bloque lleva una etiqueta:

| Etiqueta | Significado |
|---|---|
| `[bootstrap]` | Solo entorno. Cambiarla exige reiniciar. |
| `[ui-managed]` | Editable en Config. dinámica o en Credenciales. El `.env` solo vale si no hay fila en la base. |
| `[keep-env]` | No es de arranque, pero se deja en el entorno (URLs públicas de proveedores). |
| `[deploy]` / `[runtime]` | Valores del despliegue o de funcionamiento con defecto razonable. |

`tests/test_env_example_sincronizado.py` obliga a mantenerla: todo campo nuevo de `Settings` tiene que estar en
la plantilla o en una de las familias que el final del fichero declara como omitidas a propósito, y toda variable
con pinta de secreto (`SECRET`, `PASSWORD`, `_TOKEN`, `_KEY`, `DSN`) tiene que estar escrita.

> **Atención:** el repositorio versiona `.env` a propósito (cabecera de `.gitignore`). Lo propio de cada máquina
> o despliegue va en `.env.local`, `.env.produccion`… (ignorados). No escribas secretos reales en `.env`.

### 6.3 Variables imprescindibles para implantar

Lo mínimo que hay que revisar en cada despliegue. Los defectos son los del código, no los de `.env.example`.

**Entorno y secretos de la aplicación**

| Variable | Defecto | Para qué |
|---|---|---|
| `ENVIRONMENT` | `production` | `development`, `test`, `staging` o `production`. Alias normalizados al arrancar (23-11-2026): `dev`, `local`, `demo` → `development`; `testing` → `test`; `stage`, `pre`, `preprod` → `staging`; `prod`, `prd` → `production`. Antes los scripts los aceptaban y la API se negaba a arrancar. Sin fijar, la app se comporta como producción. `setup.sh` y `setup.bat` escriben `development` si falta. Decide el endurecimiento: cookies `Secure`, HSTS, documentación de la API, comprobaciones de arranque |
| `SECRET_KEY` | obligatoria | Raíz del cifrado de secretos en la base y clave JWT heredada. 32 caracteres o más, sin plantilla. Genérala con `python -c "import secrets; print(secrets.token_hex(32))"` |
| `SECRET_KEY_PREVIOUS` | vacía | Claves anteriores, separadas por comas, solo para descifrar durante una rotación ([§8.13](#813-secretos-cifrados-y-rotación-de-claves)) |
| `CLIENT_PORTAL_SECRET` | obligatoria | Firma de los tokens del portal de clientes. 32 caracteres o más en staging/production |
| `KMS_PROVIDER`, `AWS_KMS_KEY_ID`, `AWS_KMS_REGION` | vacías | `aws` cifra las credenciales con AWS KMS (sobre); vacío, cifrado local con `SECRET_KEY` |

**Base de datos y Redis**

| Variable | Defecto | Para qué |
|---|---|---|
| `DATABASE_URL` | obligatoria | SQLite (`sqlite:///./contecflow.db`, desarrollo) o `postgresql+psycopg2://…` (producción). En producción, con el rol de aplicación sin privilegios ([§7.3](#73-aislamiento-en-la-base-rls-de-postgresql-database-isolation)) |
| `DATABASE_MIGRATIONS_URL` | vacía | Conexión del dueño del esquema para migraciones y RLS. Vacía: `DATABASE_URL` |
| `APP_DB_USER`, `APP_DB_PASSWORD` | vacías | Rol de aplicación sin BYPASSRLS. Los rellena `scripts/rol_de_aplicacion.py` (lo llaman los `setup`) |
| `RLS_REQUIRED` | sin fijar | Sin fijar: exigido en staging/production. `0` solo en una emergencia documentada |
| `REDIS_URL` | vacía | Broker y resultados de Celery, límite de peticiones, tickets de WebSocket, invalidación de ajustes. **Obligatoria en producción** |
| `REDIS_PASSWORD` | vacía | `requirepass` de Redis; la app la añade a `REDIS_URL` si esta no lleva credenciales. La generan los `setup` |
| `RATE_LIMIT_REQUIRE_REDIS_IN_PRODUCTION` | `true` | En producción, no arrancar si el limitador no alcanza Redis |

**URLs públicas, CORS y proxy**

| Variable | Defecto | Para qué |
|---|---|---|
| `ALLOWED_ORIGINS` | localhost:3000/5173/8000 | Lista JSON. Es a la vez la lista CORS y la de `Origin` permitidos por el CSRF. Explícita, sin `*`, sin localhost en staging/production |
| `FRONTEND_URL` | `http://localhost:5173` | URL pública de la interfaz: enlaces de correos y redirecciones |
| `BACKEND_URL` | `http://localhost:8000` | URL pública de la API. Base de las vueltas de OAuth y de la comprobación de firmas de Twilio |
| `BASE_URL` | `http://localhost:8000` | URL pública del backend en enlaces y en la metadata SAML |
| `APP_PUBLIC_URL` | vacía | Base de los enlaces del resumen de chat por correo. Vacía: `FRONTEND_URL` |
| `WEBAUTHN_RP_ID`, `WEBAUTHN_ORIGIN` | `localhost`, `http://localhost:5173` | Dominio y origen de las passkeys. Con localhost no arranca en staging/production |
| `TRUST_PROXY_HEADERS`, `TRUSTED_PROXY_CIDRS` | `false`, `127.0.0.1/32,::1/128` | Creer `X-Forwarded-*` solo si la IP que conecta es un proxy de confianza. Con `docker-compose.yml` las fuerza el servicio `api` |
| `TENANT_ENTRY_MODE`, `TENANT_ROOT_DOMAIN` | `email_selector`, vacía | Cómo entra cada persona en su empresa ([§7.1](#71-modelo-multiempresa)) |

**Arranque de la plataforma**

| Variable | Defecto | Para qué |
|---|---|---|
| `SUPERADMIN_EMAIL` | obligatoria | Correo del superadmin de plataforma que crea la siembra |
| `SUPERADMIN_PASSWORD` | obligatoria | Su contraseña. Se vuelve a aplicar en cada siembra. 16 caracteres o más fuera de los entornos locales |
| `DEFAULT_USER_PASSWORD` | obligatoria | Contraseña de los usuarios de demostración de la siembra. No la reutilices en producción |
| `ENABLE_APSCHEDULER`, `ENABLE_CELERY_BEAT` | `true`, `false` | Qué planificador corre. Nunca los dos ([§13](#13-monitorización-y-tareas-programadas)) |
| `DEFAULT_TIMEZONE`, `DEFAULT_LANGUAGE`, `DEFAULT_CURRENCY` | `Europe/Madrid`, `es`, `EUR` | Valores por defecto de empresa. La zona es también la de los planificadores |

**Correo**

| Variable | Defecto | Para qué |
|---|---|---|
| `SMTP_HOST`, `SMTP_PORT` | vacío, `587` | Servidor SMTP de salida de la plataforma |
| `SMTP_USER`, `SMTP_PASS` | vacías | Credenciales SMTP. **La contraseña es `SMTP_PASS`, no `SMTP_PASSWORD`** |
| `SMTP_FROM` | vacía | Remitente. Sin él y con remitente `.local`, staging/production no arrancan |
| `SMTP_TLS_VERIFY` | `true` | Verificar certificado y nombre del servidor. `false` solo para un relay interno autofirmado |
| `NOTIFICATION_EMAIL_FROM` | `alerts@contecflow.local` | Remitente de alertas |

Cada empresa puede tener su SMTP propio en Credenciales; el de la plataforma es el respaldo.

**Webhooks y correo entrante**

| Variable | Defecto | Para qué |
|---|---|---|
| `WEBHOOK_SECRET` | vacía | Firma HMAC de webhooks. Obligatoria (24+ caracteres) en staging/production |
| `INBOUND_EMAIL_SECRET` | vacía | Cabecera `X-Contecflow-Email-Secret` del relay de correo entrante. Mismas reglas |
| `SLACK_SIGNING_SECRET`, `GITHUB_WEBHOOK_SECRET`, `GITLAB_WEBHOOK_SECRET`, `STRIPE_WEBHOOK_SECRET`, `DOCUSIGN_CONNECT_HMAC_KEY` | vacías | Secretos globales de entrada. Cada empresa puede tener el suyo como credencial |

**Métricas y observabilidad** (detalle en [§4](#4-docker-y-observabilidad) y [`docs/OBSERVABILIDAD.md`](docs/OBSERVABILIDAD.md))

| Variable | Defecto | Para qué |
|---|---|---|
| `METRICS_ENABLED` | `false` | Publica `/metrics` (Prometheus) |
| `METRICS_AUTH_TOKEN` | vacía | Bearer de `/metrics`. Fuera de development, sin él responde 401 |
| `METRICS_TENANT_LABEL`, `METRICS_TENANT_MAX` | `slug`, `50` | Etiqueta `empresa` de las métricas (nunca un dato personal) y cuántas empresas la tienen propia |
| `SENTRY_DSN`, `OTEL_*` | vacías | Sentry y OpenTelemetry. En `.env.example` van comentadas a propósito: una variable vacía no equivale a no tenerla |

**Almacenamiento de ficheros**

| Variable | Defecto | Para qué |
|---|---|---|
| `AWS_ACCESS_KEY`, `AWS_SECRET_KEY` | vacías | Con las dos, los documentos van a S3; sin ellas, a disco local (`UPLOAD_DIR`) |
| `AWS_S3_BUCKET`, `AWS_REGION` | `contecflow-documents`, `eu-west-1` | Bucket y región |
| `AWS_S3_ENDPOINT_URL`, `AWS_S3_FORCE_PATH_STYLE` | vacías | Almacén compatible con S3 (versitygw del stack Docker, MinIO). El direccionamiento por ruta se deduce si no se fija |
| `UPLOAD_DIR` | `uploads` | Directorio de subidas sin S3 |
| `MAX_FILE_SIZE_MB` | `100` | Tope de una subida |
| `MAX_REQUEST_BODY_MB` | `110` | Tope de cualquier cuerpo de petición (413). Mayor que `MAX_FILE_SIZE_MB` |

**Inteligencia artificial** (detalle en [§38](#38-inteligencia-artificial))

| Variable | Defecto | Para qué |
|---|---|---|
| `AI_PROVIDER` | vacía | `anthropic`, `openai`, `gemini`, `deepseek`, `ollama`, `groq`, `mistral` o `azure`. Último escalón de la cadena empresa → global → `.env` |
| `AI_API_KEY`, `AI_MODEL`, `AI_BASE_URL` | vacías | Clave, modelo (vacío: el del catálogo) y URL base (solo Ollama o Azure) |
| `*_API_URL`, `OLLAMA_BASE_URL` | URLs públicas | Bases de cada proveedor. Las llamadas a estas URLs de plataforma no pasan por el guardia SSRF |

En un despliegue multiempresa, el proveedor de IA se elige por empresa en **Configuración → IA e idiomas →
Proveedores de IA** (`/settings/ai-hub`). El `.env` basta para una instalación de una sola empresa.

### 6.4 Variables que no lee `Settings`

- **Solo de Docker Compose** (las lee `docker-compose.yml`, no Python): `POSTGRES_USER`, `POSTGRES_PASSWORD`,
  `POSTGRES_DB`, `POSTGRES_PORT`, `REDIS_PORT`, `REDIS_MAXMEMORY`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`,
  `MINIO_BUCKET`, `MINIO_PORT`, `API_WORKERS`, `WORKER_CONCURRENCY`, `WEB_PORT`, `PROMETHEUS_PORT`,
  `CONTECFLOW_APP_IMAGE`, `CONTECFLOW_WEB_IMAGE`, `CONTECFLOW_PROXY_CIDRS` (se convierte en `TRUSTED_PROXY_CIDRS`
  del contenedor `api`), `GRAFANA_*`, `ALERTMANAGER_*`, `ALERT_*`. Varias llevan `${VAR:?}`: si faltan,
  `docker compose up` se para con un mensaje claro. Los `setup` las rellenan.
- **Del frontend (Vite):** `VITE_API_URL`, `VITE_WS_URL`, `VITE_PORT` y `API_URL` (destino del proxy de
  desarrollo). Se leen de `frontend/.env` (plantilla `frontend/.env.example`), **no** del `.env` de la raíz. Sin
  `VITE_API_URL`, la interfaz llama a `/api/v1` del mismo origen.
- **Del entorno del proceso:** `TESTING` y `PYTEST_CURRENT_TEST` (pruebas), `PROMETHEUS_MULTIPROC_DIR` (la pone
  compose en el servicio `api`; en `.env` va comentada porque basta con que exista para activar el modo
  multiproceso).

**Fallos típicos.**

- La app no arranca con «SECRET_KEY…», «SUPERADMIN_PASSWORD…» o «WEBHOOK_SECRET…»: un valor de plantilla o
  demasiado corto. Ejecuta de nuevo `setup` o pon un valor real.
- Cambias una variable del `.env` y no pasa nada: o no has reiniciado, o la clave tiene fila en la base. Mírala
  en Config. dinámica.
- En producción, errores CORS o 403 de CSRF en cada escritura: el dominio público no está en `ALLOWED_ORIGINS`.

---

## 7. Multiempresa y aislamiento de datos

Una instalación sirve a varias empresas (*organizaciones*). Los datos de una empresa no son visibles para otra.
El aislamiento tiene dos capas que se cubren entre sí: el filtro del ORM y la seguridad por filas (RLS) de
PostgreSQL. Además, toda sesión sin empresa conocida está cerrada por defecto.

### 7.1 Modelo multiempresa

- **Empresa.** Cada registro de negocio lleva `organization_id` (unas pocas tablas, `org_id`). La única tabla
  exenta es la de empresas.
- **Pertenencia.** Una persona tiene su empresa de ficha (`users.organization_id`) y puede pertenecer a otras
  (`user_organization_memberships`).
- **Empresa activa.** La empresa con la que se trabaja viaja en el claim `org` de los tokens. Se revalida en cada
  petición: la pertenencia tiene que seguir vigente y la empresa, activa.
- **Entrar en una empresa** (`TENANT_ENTRY_MODE`, uno por despliegue, `app/services/entrada_service.py`):

  | Modo | Cómo entra la persona |
  |---|---|
  | `email_selector` (defecto) | Correo y contraseña. Con una empresa entra directo; con varias, elige en un selector (token corto de elección, `TENANT_SELECTION_TOKEN_MINUTES`) |
  | `subdomain` | Decide el host: `<slug>.TENANT_ROOT_DOMAIN` o el dominio propio de la empresa. Quien no es miembro no entra, y un token de otra empresa no vale en ese host |
  | `org_field` | El login pide el código de la empresa |

- **Cambiar de empresa.** Quien pertenece a varias cambia desde la cabecera (`POST /api/v1/auth/switch-organization`).
  El cambio revoca el refresco anterior y emite tokens nuevos para la empresa elegida.
- **Superadmin de plataforma** (`is_superadmin`). No es un rol de empresa: no lleva empresa en su sesión y ve todas.
  Gestiona las empresas en **Configuración → Empresa y marca → Empresas de la plataforma** (`/settings/organizations`,
  capacidad `plataforma.empresas`, que nadie más tiene): alta, plan, cupos, suspensión con motivo, token SCIM de la
  empresa, baja y exportación.

### 7.2 Filtro del ORM (`TenantSession`)

`app/db/session.py` define `TenantSession`, la sesión de SQLAlchemy de toda la aplicación.

- **Filtra cada consulta.** Sobrescribe `query()` y `execute()` y, con un *listener* global (`do_orm_execute`),
  añade `organization_id = <empresa de la sesión>` a toda SELECT del ORM. Es **cerrado ante el fallo**: un modelo
  que no sabe acotar lanza `TenantIsolationError`.
- **Sella las inserciones.** Un `before_flush` rellena `organization_id` en las filas nuevas que no lo traen, con
  la empresa de la sesión.
- **Quién pone la empresa.** `get_current_user` (y sus equivalentes del portal) publica en la sesión la empresa
  activa, si es superadmin y quién es el usuario.
- **Sin filtro, a propósito.** El superadmin y los trabajos de sistema declarados (ver [§7.4](#74-sesiones-sin-contexto-de-empresa-cerradas))
  no se filtran. Un servicio que necesita leer entre empresas lo declara con `sin_filtro_de_tenant(session)`.

Interruptores (solo para aislar un problema, nunca en producción): `TENANT_AUTO_FILTER_GLOBAL=1` y
`TENANT_AUTO_STAMP_ON_INSERT=1`. Ponerlos a 0 desactiva el filtro global o el sellado.

### 7.3 Aislamiento en la base: RLS de PostgreSQL (Database isolation)

El filtro del ORM no ve el SQL escrito a mano ni algunas operaciones masivas. Por eso la base tiene su propia red:
seguridad por filas (*Row Level Security*) en PostgreSQL, en `app/db/rls.py`. En SQLite no existe.

**Tres piezas:**

1. **Políticas.** Una por tabla con `organization_id` u `org_id` (`aislamiento_por_empresa`), generadas desde los
   modelos con la misma regla que el ORM: la fila es de la empresa de la sesión, o global si el modelo admite filas
   globales, o (usuarios) de un miembro de la empresa. Las aplica cada `alembic upgrade head` (`alembic/env.py`):
   una tabla nueva no se queda sin política.
2. **Contexto.** Antes de cada sentencia y de cada *flush*, la sesión pone la variable `app.tenant` de la
   transacción con su empresa. Vacía cuando el ORM tampoco filtra (superadmin, sistema declarado). Un valor que
   no casa con ninguna empresa cuando no hay contexto, para que la base no devuelva filas.
3. **Rol de aplicación** sin superusuario ni `BYPASSRLS` (`NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE`).
   Sin él, las políticas existen pero no actúan: el dueño de las tablas se las salta.

**Cómo se crea el rol.** Lo hacen `setup.sh`, `setup.bat` y el modo Docker con un único script:

```bash
python scripts/rol_de_aplicacion.py
```

Con una `DATABASE_URL` de PostgreSQL, el script:

1. crea o actualiza el rol (`APP_DB_USER`, por defecto `contecflow_app`) llamando a `python -m app.db.rls`;
2. aplica las políticas;
3. guarda en `.env` `APP_DB_USER`, `APP_DB_PASSWORD` (generada una vez), `DATABASE_MIGRATIONS_URL` (el dueño) y
   `DATABASE_URL` con el rol de aplicación.

Imprime `OK`, `SKIP` o `FAIL` y nunca para el `setup`. `CONTECFLOW_DB_APP_ROLE=0` lo omite. Para hacerlo a mano:

```bash
python -m app.db.rls      # lee APP_DB_USER / APP_DB_PASSWORD y conecta con DATABASE_MIGRATIONS_URL
```

**Arranque.** Al arrancar, la API mide el rol con el que conecta (`rls.estado`):

- RLS armado: log `RLS armado: N tablas, rol …`.
- Desarmado en `staging`/`production` (o con `RLS_REQUIRED=1`): **la API no arranca** (`RuntimeError:
  RLS_REQUIRED…`).
- Desarmado en desarrollo: aviso `Aislamiento en la base (RLS) desarmado: <motivo>. Ver README, «Database
  isolation».`

Motivos típicos y arreglo:

| Motivo | Arreglo |
|---|---|
| «la aplicación conecta como X, que se salta RLS» | `DATABASE_URL` usa el dueño o un superusuario. Ejecuta `python scripts/rol_de_aplicacion.py` |
| «N tablas con RLS de M: falta `alembic upgrade head`» | Migra (ver [§5](#5-base-de-datos-y-migraciones)) |

`RLS_REQUIRED=0` permite arrancar sin RLS. Úsalo solo en una emergencia documentada.

### 7.4 Sesiones sin contexto de empresa cerradas

Una ruta anónima (login, webhook, formulario público, SCIM, WebSocket…) no tiene empresa en su sesión. Con
`TENANT_SESION_SIN_CONTEXTO=cerrar` (defecto), una sesión sin empresa, sin superadmin y sin contexto de sistema
declarado lanza `TenantIsolationError`, y RLS no devuelve filas. Cada ruta anónima, por tanto:

1. verifica su credencial propia (firma del webhook, token del formulario, token SCIM, ticket del WebSocket…);
2. declara un contexto de sistema con nombre mientras busca la empresa
   (`Depends(sesion_de_sistema("<motivo>"))`);
3. publica la empresa en cuanto la conoce (`publicar_empresa` o `publicar_contexto_de_tenant`). Desde ahí la sesión
   filtra, sella y corta si la empresa está desactivada.

Los trabajos de fondo y los scripts declaran su contexto con `declarar_sistema(db, motivo)` o
`fijar_contexto(db, org, motivo)` (`app/db/contexto_de_tenant.py`). `TENANT_SESION_SIN_CONTEXTO=avisar` deja
pasar sin filtro y escribe un WARNING por sitio: sirve para localizar un sitio sin declarar, no para producción.

La tabla completa ruta → credencial → empresa está en
[`docs/seguridad/rutas_anonimas.md`](docs/seguridad/rutas_anonimas.md).

### 7.5 «Entrar como» (suplantación de soporte)

El superadmin puede entrar como un usuario de una empresa para dar soporte
(`POST /api/v1/organizations/{org_id}/impersonate`):

- **Motivo obligatorio.** Sin motivo, 422.
- **Límites.** No se puede entrar como otro superadmin ni como un usuario inactivo, ni en una empresa inactiva.
  El token dura `IMPERSONATION_MAX_MINUTES` (30) y se puede apagar con `IMPERSONATION_ENABLED` (ajustes de
  plataforma).
- **Rutas vedadas** mientras se suplanta: cambio de contraseña, MFA, passkeys, cambio de empresa, claves de API,
  empresas, SSO y aplicaciones del portal de desarrolladores (403 `no_disponible_entrando_como`).
- **Rastro.** El token lleva el superadmin real (`actor_real`) y el motivo. Queda en la auditoría **de la propia
  empresa** (`IMPERSONATION_START`): su administrador ve quién entró y por qué.
- La cookie de refresco sigue siendo la del superadmin: al refrescar, recupera su propia sesión.

### 7.6 Baja de una empresa con cuarentena

`app/services/baja_de_empresa_service.py`. Solo el superadmin, desde Empresas de la plataforma:

1. **Pedir la baja** (con motivo). La empresa se suspende en el acto: nadie entra y las sesiones abiertas se
   cortan. Empieza una cuarentena de `TENANT_DELETION_QUARANTINE_DAYS` (30 días). Pedirla otra vez no reinicia
   el plazo.
2. **Durante la cuarentena** se puede deshacer (la empresa sigue suspendida) y se puede descargar todo lo suyo:
   un ZIP con un JSON por tabla (`GET /api/v1/organizations/{id}/export`).
3. **Al vencer**, la tarea diaria `purgar-empresas-caducadas` borra sus filas de todas las tablas en una sola
   transacción: o se borra todo o nada. Es el único borrado permitido del registro de auditoría
   ([§15.1](#151-registro-de-auditoría-inmutable)).

Los usuarios cuya ficha es de esa empresa pero pertenecen a otras no se borran: su ficha pasa a otra de sus
empresas. Todas las acciones quedan auditadas.

### 7.7 Límites por empresa

Cada empresa tiene `max_users` y `max_projects`. Al crearla, si no se indican, se toman
`ORG_DEFAULT_MAX_USERS` (25) y `ORG_DEFAULT_MAX_PROJECTS` (100), ajustes de plataforma. Dar de alta un usuario o un
proyecto por encima del cupo devuelve 409 (`plan_limite_usuarios` y equivalente para proyectos). El superadmin
cambia los cupos en la ficha de la empresa.

---

## 8. Seguridad

Resumen de los controles de seguridad y de lo que hay que configurar. El detalle de cada área está en
`docs/seguridad/`.

### 8.1 Autenticación y sesiones

- **JWT en cookies.** El login deja tres cookies:

  | Cookie | Contenido | Atributos |
  |---|---|---|
  | `access_token` | Token de acceso (JWT HS256 con `kid`) | httpOnly, SameSite=Lax |
  | `refresh_token` | Token de refresco | httpOnly, SameSite=Strict, solo en la ruta `/api/v1/auth` |
  | `session_expires_at` | Instante en que caduca el acceso (sin secretos) | Legible por la interfaz |

  `Secure` se activa en `staging` y `production`. La API también acepta `Authorization: Bearer <JWT>`.
- **Duración.** Acceso: `ACCESS_TOKEN_EXPIRE_MINUTES` (15), con tope `ACCESS_TOKEN_MAX_MINUTES` (30): la vida real
  es el menor de los dos. Refresco: `REFRESH_TOKEN_EXPIRE_DAYS` (30). Son ajustes en vivo del grupo `tokens`.
- **Renovación anticipada.** La interfaz lee `session_expires_at` y renueva la sesión 60 s antes de que caduque
  (`frontend/src/services/api/_core.ts`). Al volver a una pestaña dormida lo revisa. Si falla, un 401 dispara el
  refresco silencioso.
- **Firma.** Los tokens se firman con un llavero JWT guardado en la base y rotado solo ([§8.13](#813-secretos-cifrados-y-rotación-de-claves)).
  Cada proceso guarda el llavero `JWT_KEYRING_CACHE_SECONDS` (60) y un `kid` desconocido fuerza la recarga.
- **Sesión revocable.** El token lleva `sid`. En cada petición se comprueba que la sesión no está revocada, ni
  inactiva más de lo permitido, ni pasada de su tope. Revocar corta en el acto.
- **CSRF** (`app/core/csrf.py`), solo en peticiones de escritura autenticadas por cookie:
  1. siempre, `Origin` (o `Referer`) tiene que estar en `ALLOWED_ORIGINS`;
  2. con `CSRF_DOUBLE_SUBMIT=true`, además la cabecera `X-CSRF-Token` tiene que coincidir con la cookie
     `csrf_token` (doble envío).

  Las peticiones con `Authorization` y los webhooks firmados (lista de exentos del módulo) no pasan por el CSRF.
- **WebSocket.** La interfaz pide un ticket de un solo uso (`GET /api/v1/ws/ticket`, con sesión) y conecta con
  `?ticket=…`. Dura `WS_TICKET_TTL_SECONDS` (60 s) y vive en Redis. Sin Redis y con varios workers, un ticket
  emitido por uno no lo conoce otro. El JWT en la URL solo se admite fuera de producción.
- **Restablecer contraseña.** «¿Olvidaste tu contraseña?» para operadores y portal: respuesta igual exista o no
  la cuenta, enlace de un solo uso de 30 min, política de la empresa al guardar y cierre de todas las sesiones.

### 8.2 Políticas de cuenta

Por empresa, en **Configuración → Seguridad y GRC → Seguridad de cuentas** (`/settings/seguridad-cuentas`,
capacidad `seguridad.administrar`). Solo se guardan por `PUT /api/v1/security/policy`, que valida, aplica la
segregación de funciones y audita; Config. dinámica rechaza esos grupos. Detalle y valores recomendados (NIST
SP 800-63B, ISO 27001, CIS) en [`docs/seguridad/politicas_de_cuenta.md`](docs/seguridad/politicas_de_cuenta.md).

| Área | Ajustes principales (defecto) |
|---|---|
| Contraseñas | `MIN_PASSWORD_LENGTH` (8), `PASSWORD_MAX_LENGTH` (128), `PASSWORD_BLOCK_COMMON` (sí, lista local), `PASSWORD_BLOCK_PERSONAL` (sí), `PASSWORD_HISTORY_COUNT` (5), `PASSWORD_MIN_AGE_HOURS` (0), `PASSWORD_EXPIRY_DAYS` (0 = no caduca), `TEMP_PASSWORD_EXPIRY_HOURS` (72) |
| Bloqueo | `LOGIN_MAX_ATTEMPTS` (5) en `LOGIN_ATTEMPT_WINDOW_SECONDS` (900), bloqueo `LOGIN_LOCKOUT_SECONDS` (900), aviso al usuario. El bloqueo se guarda también en `users.locked_until` |
| MFA | TOTP y passkeys/WebAuthn, códigos de recuperación de un solo uso. Obligatorio para toda la empresa (`require_mfa`), por rol (`MFA_REQUIRED_ROLES`, `admin`) o por capacidad sensible (`MFA_REQUIRED_FOR_SENSITIVE`). Métodos permitidos (`MFA_ALLOWED_METHODS`), gracia (`MFA_GRACE_DAYS`, 7), recordar dispositivo (`MFA_REMEMBER_DEVICE_DAYS`, 0) |
| Sesiones | Inactividad (`idle_timeout_minutes`, aplicada en el servidor), duración máxima (`SESSION_MAX_HOURS`, 0 = sin tope), sesiones concurrentes (`SESSION_MAX_CONCURRENT`, 0 = sin tope; cierra la más antigua) |
| Acceso | Lista de IP o CIDR (`ACCESS_IP_ALLOWLIST`), horario y días (`ACCESS_HOURS`, `ACCESS_DAYS`), países bloqueados (`ACCESS_BLOCKED_COUNTRIES`, solo con país conocido) |
| Cuentas inactivas | `ACCOUNT_INACTIVE_DISABLE_DAYS` (0): la tarea diaria `seguridad-de-cuentas-diario` desactiva las cuentas sin acceso en ese plazo |

Acciones del administrador, todas auditadas: forzar el cambio de contraseña (a uno o a todos), contraseña
temporal, forzar restablecimiento con motivo, desbloquear, restablecer el MFA de otro, ver y cerrar sesiones de
la empresa. Las passkeys sin contraseña se controlan con `PASSKEY_PASSWORDLESS_ENABLED` (ajuste de plataforma).

**Revocación al desactivar.** Al desactivar a un usuario, venga de donde venga (pantalla, SCIM, recertificación,
inactividad), se revocan todas sus sesiones (`app/db/revocar_al_desactivar.py`). También al cambiar o restablecer
la contraseña y al restablecer su MFA.

**Excepción del superadmin.** No le afectan la lista de IP, el horario ni el país de ninguna empresa: es la vía de
recuperación si una empresa se deja fuera. Antes de guardar la lista de IP, la pantalla comprueba que quien guarda
queda dentro.

**Alertas.** El administrador recibe en la campana: fallos masivos (`SECURITY_ALERT_FAILED_LOGINS`, 20 en 15 min),
entrada desde IP nueva, MFA desactivado o restablecido, cambio de política y cuenta bloqueada.

### 8.3 SSO, SCIM y passkeys

- **OIDC.** Se configura por empresa en **Configuración → Integraciones → Empresa: SSO, webhooks y OAuth**
  (`/settings/enterprise`, pestaña SSO), con botón de validación (`POST /api/v1/enterprise/sso/{id}/test`).
  El flujo (`app/api/v1/routers/auth_sso.py`) verifica la firma contra el JWKS, usa PKCE S256, `state` firmado de
  un solo uso y `nonce`. Ajustes: `SSO_HTTP_TIMEOUT_SECONDS`, `SSO_CLOCK_SKEW_SECONDS`, `SSO_RATE_LIMIT`. El MFA
  obligatorio se aplica también en SSO.
- **SAML 2.0** (23-11-2026, `app/services/auth_service/saml.py` y `app/api/v1/routers/auth_saml.py`). Se configura
  en la misma pestaña SSO eligiendo **SAML 2.0**: entity ID, URL de SSO y (opcional) de logout del IdP, certificado
  X.509 de firma (PEM o base64) y atributos de correo, nombre y grupos. La pantalla muestra lo que hay que dar de
  alta en el IdP: metadata (`GET /api/v1/auth/saml/metadata`, con `BASE_URL`), ACS (`POST /auth/saml/callback`,
  HTTP-POST) y SLO (`GET /auth/saml/logout`, HTTP-Redirect).
  - **Flujo**: el botón del login pide `GET /auth/saml/{id}/login` (AuthnRequest con un ID de un solo uso); el IdP
    vuelve al ACS; el ACS valida y redirige a `/login?saml_ticket=…`; el frontend canjea el ticket (un solo uso) en
    `POST /auth/saml/canjear` y sigue el mismo camino que OIDC: alta JIT con `create_or_update_sso_user` (dominios
    permitidos, rol por grupos, límite de usuarios, nunca el superadmin), empresa del proveedor, MFA de la empresa.
  - **Controles del ACS**, todos obligatorios: XML sin DTD ni entidades; firma XML-DSig (SHA-256 o superior) de la
    respuesta o de la aserción con el certificado configurado, usando solo lo firmado; exactamente una aserción;
    emisor = entity ID; **audiencia** = entity ID del SP; **destino** (`Destination` y `Recipient`) = ACS;
    **caducidad** (`NotBefore`/`NotOnOrAfter`, holgura `SSO_CLOCK_SKEW_SECONDS`); **anti-replay**: `InResponseTo`
    = la petición pendiente, que se consume al llegar. No se admiten aserciones cifradas ni el SSO iniciado por el
    IdP (sin petición previa no hay forma de impedir la reutilización).
  - **SLO**: al cerrar sesión, si la persona entró por SAML y el IdP tiene logout, se le redirige allí con una
    LogoutRequest; una LogoutRequest del IdP (firma de la query RSA-SHA256/512 obligatoria) cierra todas sus sesiones.
  - **Auditoría**: cada login SAML (`LOGIN`, método `saml`), cada rechazo (`LOGIN_FAILED` con el motivo, sin la
    respuesta del IdP) y cada logout. Los logins OIDC también quedan ahora como `LOGIN` (método `sso`).
  - **Librería**: `signxml` (Python puro sobre `lxml` y `cryptography`). `python3-saml` y `pysaml2` exigen `xmlsec`
    nativo, que haría fallar la instalación de `setup.sh`/`setup.bat` en equipos sin `libxmlsec1`.
- **SCIM 2.0** (`/api/v1/scim/v2/{org_id}/…`: usuarios, grupos y *bulk*). La credencial es el token SCIM de la
  empresa, que genera el superadmin (`POST /api/v1/organizations/{id}/scim-token`, se muestra una vez). Hay además
  un token global opcional (`SCIM_BEARER_TOKEN`, acotado a `SCIM_ALLOWED_ORG_ID`).
- **Passkeys.** Registro en **Mi verificación en dos pasos** (`/settings/mfa`). Necesitan `WEBAUTHN_RP_ID` y
  `WEBAUTHN_ORIGIN` con el dominio real.

### 8.4 Claves de API y tokens de desarrollador

`app/core/credenciales_delegadas.py`. Además de la sesión, `get_current_user` acepta:

- **Claves de API** (`nxpm_…`), en `X-API-Key` o `Authorization: Bearer`. Se crean en **Empresa: SSO, webhooks y
  OAuth → Claves de API**.
- **Tokens del portal de desarrolladores** (**Configuración → Integraciones → Portal de desarrolladores**,
  `/settings/developer`): cada aplicación obtiene token con `client_id` y `client_secret`
  (`POST /api/v1/developer/token`); caduca a los `DEVELOPER_TOKEN_TTL_MINUTES` (60).

La credencial actúa **como su dueño** (su rol y su empresa) y sus alcances la recortan:

| Alcance | Qué abre |
|---|---|
| `read` | Solo lectura (GET, HEAD, OPTIONS) |
| `write`, `admin` | También escritura |
| `projects`, `tasks`, `timesheets`, `billing`, `expenses` | Lectura y escritura solo en esa área (tokens del portal) |
| `mcp:read`, `mcp:write` | Solo el servidor MCP (`POST /api/v1/mcp`); nada más de la API |

Una credencial delegada **nunca** gestiona credenciales: sesión, contraseña, MFA, SSO, claves de API, aplicaciones
del portal, configuración del MCP y Del ticket al PR exigen iniciar sesión (403). Los secretos se guardan como
huella SHA-256.

### 8.5 MCP para agentes de código

Servidor MCP (`POST /api/v1/mcp`) para que OpenCode o Claude Code trabajen con tareas, tickets, horas y cambios.
Se enciende por empresa en **Configuración → Integraciones → Agentes de código (MCP)** (`/settings/mcp`; ajustes,
`gobierno.administrar`). Cada herramienta pide la capacidad de su ruta REST equivalente, respeta módulos cerrados,
matriz GRC y ABAC, y queda en la auditoría (`MCP_CONNECT`, `MCP_TOOL_CALL`…). Límite por credencial:
`MCP_RATE_LIMIT_PER_MINUTE` (60). Detalle en [§39](#39-mcp-agentes-de-código-externos) y
[`docs/integraciones/MCP.md`](docs/integraciones/MCP.md).

### 8.6 Autorización en cuatro capas

Debajo de todo está el aislamiento por empresa ([§7](#7-multiempresa-y-aislamiento-de-datos)). Encima, cada petición
pasa por cuatro capas. Ninguna sustituye a otra.

1. **Rol base** (`users.role`): `admin` (Dirección), `pm`, `team_lead`, `hr`, `employee` y `subcontractor`. El
   superadmin es una marca aparte (`is_superadmin`).
2. **Capacidad por ruta** (`app/core/capacidades.py`). Cada ruta de la API declara `requiere_capacidad("x")`
   (`sd.gestionar`, `org.administrar`…) en vez de una lista de roles. La pantalla pregunta por las mismas
   capacidades, así que lo que se ve no da 403. Un **rol personalizado** solo restringe: cierra módulos (403 en
   sus rutas y fuera del menú) y nunca da algo que el rol base no tenga. Un administrador no se restringe. Las
   rutas de plataforma usan `require_superadmin`.
3. **Matriz GRC** (`app/core/grc_enforce.py`), editable en **GRC y segregación de funciones** (`/settings/grc`,
   pestaña Matriz de permisos). **Denegación aditiva**: una casilla desmarcada da 403; una marcada no concede
   nada que el rol no tuviera.
4. **ABAC** (`app/core/abac_dependency.py`, `abac_enforce.py`): políticas por atributos de la empresa. Es
   **discrecional y abierta ante el fallo**: sin políticas activas no restringe nada. Nunca es el único control de
   una ruta.

Las capas 3 y 4 se aplican dentro de `get_current_user` sobre el usuario ya resuelto (sesión, clave de API o token).
Dentro de la empresa hay además mínimo privilegio sobre personas y ajustes
(`app/services/politica_de_visibilidad.py`): un subcontratista solo ve la ficha mínima de la gente de sus
proyectos. Las herramientas del asistente de IA aplican la guarda de su ruta REST equivalente.

Matriz de capacidades por rol: [§42](#42-roles-y-capacidades) y
[`docs/seguridad/guardas_por_capacidad.md`](docs/seguridad/guardas_por_capacidad.md).

### 8.7 Segregación de funciones

- **Nadie aprueba lo suyo.** En la bandeja de aprobaciones y en las aprobaciones directas (ausencias, imputaciones,
  documentos, hitos, traspasos de presupuesto, cambios) el solicitante no puede aprobar su solicitud (403). Es una
  regla del código. Cada intento queda como violación en GRC.
- **Reglas SoD** en **GRC y segregación de funciones → Segregación SoD**: pares de operaciones incompatibles por rol,
  con riesgo y flujo de mitigación. **Violaciones** muestra las activas (`GET /api/v1/grc/sod-check`).
- **Segundo administrador en seguridad** (`SECURITY_SOD_TWO_ADMINS`, defecto no): un cambio de política de cuenta o
  un restablecimiento de MFA crea una solicitud que aplica otro administrador.
- **Forzar el restablecimiento** de la propia contraseña no está permitido.

### 8.8 Cabeceras HTTP

`security_headers_middleware` (`app/main.py`) añade a todas las respuestas:

| Cabecera | Valor |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` (`SAMEORIGIN` en la vista de documentos; la página de BI incrustado trae su propio `frame-ancestors`) |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains; preload`, **solo con `ENVIRONMENT=production`** |
| `Permissions-Policy` | `camera=(), microphone=(self), geolocation=()` |
| `Content-Security-Policy` | Restrictiva; fuentes y estilos solo del propio origen |

La documentación interactiva (`/api/v1/docs`) se apaga en producción salvo `EXPOSE_API_DOCS=true`.

### 8.9 Limitador de peticiones

`app/core/ratelimit.py` (slowapi):

- Rutas con límite propio (login 5/min, restablecer contraseña, SSO…).
- El resto: `RATE_LIMIT_DEFAULT` (`200/minute`), por ruta y por usuario; sin sesión, por IP.
- La IP real sale de `X-Forwarded-For` solo si el salto es un proxy de confianza (`TRUST_PROXY_HEADERS`,
  `TRUSTED_PROXY_CIDRS`).
- Los contadores viven en **Redis**. Sin Redis, cada worker lleva los suyos (los límites se multiplican por el
  número de workers). En producción, sin Redis la API no arranca (`RATE_LIMIT_REQUIRE_REDIS_IN_PRODUCTION`).

### 8.10 SSRF y salidas de red

`app/core/outbound_url.py` es el único guardia de las llamadas salientes que configura una empresa (webhooks,
proveedores de IA con URL propia, automatizaciones, pruebas de conexión, conectores, Salesforce, CMDB, GitHub
Enterprise…):

- **Rechaza** todo lo que no sea una IP pública: privadas, loopback, link-local (metadatos de nube), CGN,
  reservadas, `localhost`, `*.local`, `*.internal` y URLs con usuario y contraseña.
- **Permite** hosts internos legítimos (un Jira o un SMTP de la casa) solo si están en
  `OUTBOUND_PRIVATE_HOSTS_ALLOWED` (CSV).
- **Cierra el DNS rebinding.** Valida cada petición y cada redirección y comprueba la IP a la que el socket se ha
  conectado de verdad antes de enviar nada. Al paginar, un enlace `next` no puede llevarse el token a otro host.
- **Conexión fijada** (`app/core/conexion_fijada.py`) para el IMAP del service desk y el SMTP de empresa: valida el
  host, conecta a esa IP sin volver a resolver y TLS verifica el nombre configurado. Un host que no resuelve se
  rechaza.
- Los errores no devuelven el cuerpo remoto.

**Geolocalización de IP** (`GEOIP_LOOKUP_ENABLED`): apagada por defecto. Encenderla envía la IP de cada inicio de
sesión a un tercero fuera del EEE (base legal, registro de tratamientos y contrato de encargo necesarios).

Detalle en [`docs/seguridad/entrada_y_salida.md`](docs/seguridad/entrada_y_salida.md).

### 8.11 Subidas de ficheros

- **Tope global de cuerpo** (`app/core/limite_de_cuerpo.py`): `MAX_REQUEST_BODY_MB` (110) con 413, aunque la
  cabecera mienta. nginx mantiene su `client_max_body_size` (110m en el stack Docker).
- **Validación central** (`app/core/uploads.py`): todo endpoint con subida lee por trozos con tope y valida
  extensión, MIME declarado, bytes mágicos y coherencia entre ellos *antes* de procesar.
  - Admitidos: PDF, Office y OpenDocument, texto, CSV, Markdown, JSON, XML, imágenes (JPEG, PNG, GIF, WebP, SVG,
    TIFF), MP4, WebM, MP3, M4A.
  - Rechazados: ejecutables (cabeceras `MZ`, ELF, Mach-O, `#!`) y comprimidos (`.zip`, `.gz`, `.tar`, `.7z`,
    `.rar`…).
  - Topes por perfil: documentos y adjuntos, `MAX_FILE_SIZE_MB` (100); recibos y PDF, 10 MB; importación CSV,
    5 MB; importaciones de datos de terceros, 25 MB. Los adjuntos de canales (WhatsApp, Slack) no admiten SVG.
- **Antivirus** (opcional): `CLAMAV_ENABLED=true` escanea con clamd (`CLAMAV_HOST`/`CLAMAV_PORT` o
  `CLAMAV_SOCKET`) los adjuntos del chat de colaboración y de los canales del service desk. El resto de subidas no
  pasa por ClamAV.
- **Exportaciones CSV/XLSX**: un texto que empieza por `= + - @` se neutraliza (inyección de fórmulas).

### 8.12 Webhooks entrantes

Todos verifican su firma o secreto antes de tocar datos, y después fijan la empresa
([§7.4](#74-sesiones-sin-contexto-de-empresa-cerradas)): GitHub (`X-Hub-Signature-256`), GitLab
(`X-Gitlab-Token`), Jira (secreto por empresa), Stripe (`Stripe-Signature`), DocuSign Connect (HMAC), Adobe Sign
(client id), Slack (firma), Teams (JWT de Bot Framework), Twilio (firma), WhatsApp (firma de Meta), correo entrante
(secreto), disparadores propios (`X-Contecflow-Signature`). Sin secreto configurado, se rechazan.

### 8.13 Secretos cifrados y rotación de claves

**Cifrado en reposo** (`app/core/encryption.py`). Credenciales de integración, secretos TOTP, buzones, tokens de
colaboración y demás columnas sensibles se guardan como `v2:<sal>.<token>` (Fernet con clave derivada por HKDF de
`SECRET_KEY` y sal por registro). Con `KMS_PROVIDER=aws`, cifrado de sobre con AWS KMS (`kmsv1:`). Para auditar
que no queda nada en claro: `python scripts/audit_secrets_encryption.py`.

**Rotación automática.** La tarea `run-key-rotation` (diaria a las `KEY_ROTATION_RUN_HOUR`:17, por defecto 02:17 en
`DEFAULT_TIMEZONE`) rota el llavero JWT cada `JWT_KEY_ROTATION_DAYS` (30), conserva `JWT_KEY_RETENTION_COUNT` (3)
claves antiguas para verificar, y recifra los secretos de integración cada `INTEGRATION_SECRET_ROTATION_DAYS` (60).
Se apaga con `KEY_ROTATION_ENABLED=false`. Son ajustes de plataforma.

**Rotar `SECRET_KEY`** (a mano, por ejemplo tras una fuga):

```bash
bash scripts/rotate_keys.sh                          # desde la raíz, con la base accesible
venv/bin/python scripts/reencrypt_secrets.py --check # cuenta lo que aún depende de la clave vieja
```

`rotate_keys.sh`:

1. copia `.env` a `.env.bak.<fecha>` (permisos 600; contiene la clave vieja);
2. pone una clave nueva en `SECRET_KEY` y la vieja al principio de `SECRET_KEY_PREVIOUS` (la aplicación descifra
   con las dos);
3. recifra todo con la nueva (`scripts/reencrypt_secrets.py`, que recorre todas las columnas de texto de todas las
   tablas);
4. no imprime ninguna clave.

Después, reinicia API, worker y beat y prevé que los usuarios tengan que volver a iniciar sesión. Cuando
`reencrypt_secrets.py --check` diga 0 pendientes, vacía `SECRET_KEY_PREVIOUS` y borra la copia `.env.bak.*`.

Sin `.env` (secretos en un gestor), cambia la clave allí y ejecuta `scripts/reencrypt_secrets.py`.
`scripts/rotar_secret_key.py` es otra cosa: lo usa `setup.bat` para generar `SECRET_KEY` si falta o es insegura.

### 8.14 Interruptores que nunca deben llegar a producción

| Interruptor | Qué hace | Protección |
|---|---|---|
| `ENABLE_SUPERADMIN_BYPASS` | Entrada de superadmin sin contraseña, para desarrollo | Solo con `ENVIRONMENT=development` y SQLite; fuera de ahí la app no arranca. Encendido deja un aviso CRITICAL y cada uso queda en la auditoría (`SUPERADMIN_BYPASS_LOGIN`) y en el informe de cumplimiento |
| `DISABLE_CSRF_MIDDLEWARE` | Quita el CSRF | Rechazado en staging/production |
| `TENANT_AUTO_FILTER_GLOBAL=0`, `TENANT_AUTO_STAMP_ON_INSERT=0`, `TENANT_SESION_SIN_CONTEXTO=avisar` | Debilitan el aislamiento | Solo para diagnosticar |
| `RLS_REQUIRED=0` | Arranca sin RLS | Solo emergencia documentada |
| `SEED_*` | Siembra de datos de demostración | Solo desarrollo y demos |

---

## 9. Integraciones y pruebas de conexión

### 9.1 Integraciones disponibles

Casi todas se configuran **por empresa** y guardan sus secretos cifrados. Rutas de API relativas a `/api/v1`.

| Integración | Dónde se configura | Prueba de conexión |
|---|---|---|
| SMTP de salida | Credenciales de integraciones (`/settings/integrations`); respaldo `SMTP_*` | Sí: conexión con IP fijada, TLS, login y `NOOP` |
| Buzón del service desk (IMAP o Microsoft Graph) | Credenciales (`sd_mailbox`) y Service desk → Correo entrante (`/settings/sd?sub=mail`) | Sí: login y lectura de la bandeja |
| Correo entrante por relay | `INBOUND_EMAIL_SECRET` o credencial `webhooks` | Pasiva (llega el primer correo) |
| Microsoft 365 / Graph (calendario, presencia, Planner, Teams, SharePoint, OneDrive) | Credenciales (`ms_graph`); Microsoft 365 (`/settings/m365`) | Sí: token de la empresa y lectura del tenant |
| Informes de uso de Microsoft 365 | Informes de Microsoft 365 (`/settings/m365-informes`) | No comprobado |
| Slack (avisos, comandos, hilos de ticket) | Credenciales (`slack`: webhook, signing secret, bot token); ajuste en vivo `SLACK_TEAM_ID` por empresa | Sí: el webhook responde; el hub envía un mensaje |
| Microsoft Teams (avisos y bot) | Empresa: SSO, webhooks y OAuth → Integraciones; `TEAMS_BOT_*`; `TEAMS_TENANT_ID` por empresa | Sí: envía un mensaje (`/integrations-hub/teams/test`) |
| WhatsApp Business (Meta Cloud API) | Credenciales (`whatsapp`) | Sí: lee el número |
| SMS y voz (Twilio) | Credenciales (`twilio`); ajuste en vivo `TWILIO_PHONE_NUMBERS` | Sí: lee la cuenta |
| Jira (tareas y service desk) | Jira (`/settings/jira`); secreto de webhook por empresa | Sí: usuario, proyecto, búsqueda y estados |
| GitHub y GitLab (commits, PR, despliegues) | Git (`/settings/git`, solo lectura); secretos en Credenciales → webhooks; `GITHUB_*`/`GITLAB_*` para Enterprise Server o GitLab propio | Pasiva (webhooks) |
| GitHub, GitLab, Jira, Google y Microsoft 365 del chat (OAuth por usuario) | Variables `*_CLIENT_ID`, `*_CLIENT_SECRET` (una app OAuth por proveedor) | No |
| Google Calendar, Xero, QuickBooks Online | Empresa: SSO, webhooks y OAuth → Integraciones | Xero y QuickBooks: sí (`/accounting/xero/test`, `/accounting/qb/test`) |
| Salesforce | Solo por API (`/salesforce-sync/…`); no se ha encontrado pantalla | Sí (`/salesforce-sync/integrations/salesforce/test`); la sincronización de salida no está implementada |
| Stripe (cobro de facturas) | Credenciales (`stripe`), cada empresa con su cuenta | Sí: lee el saldo |
| DocuSign y Adobe Sign | Firma electrónica (`/settings/esign`) y Credenciales | Sí, parcial: comprueba la configuración; la cuenta se conecta por OAuth |
| AWS S3 | Credenciales (`aws_s3`); respaldo `AWS_*` | Sí: `head_bucket` |
| Proveedores de IA (8) | Proveedores de IA (`/settings/ai-hub`); respaldo `AI_*` | Sí, por proveedor y «probar sin guardar» |
| DeepL y Azure Translator | Traducción (`/settings/traduccion`) | Sí: traduce una palabra |
| OpenExchangeRates | Credenciales | Sí |
| contecmind y contecintelligence | Credenciales (`contecmind`, `contecintelligence`) | Sí: credencial y salud |
| Fuentes de uso de licencias (M365, Google Workspace, Okta, Jamf) | Fuentes de uso de licencias (`/settings/alm-fuentes`) | Sí |
| Fuentes de vulnerabilidades y escáneres de la CMDB | Software y vulnerabilidades (`/settings/cmdb-software`) | Sí, por fuente y por escáner |
| Reuniones: Teams, Zoom, Meet y bot | Asistente de reuniones (`/settings/reuniones`) | Sí, por conector |
| Conectores ETL de BI | Plataforma de datos → ETL | Sí |
| Del ticket al PR (Docker, GitHub App o GitLab, IA) | Del ticket al PR (`/settings/ticket-a-pr`), ver [§40](#40-del-ticket-al-pr) | Sí, por pieza |
| Alertas de monitorización entrantes | Credenciales (`monitoring`) | Pasiva |
| SSO OIDC | Empresa: SSO, webhooks y OAuth → SSO | Sí: valida la configuración |
| SCIM 2.0 | Token de la empresa (superadmin) | No |
| Webhooks salientes | Empresa: SSO, webhooks y OAuth → Webhooks; historial en Registro de webhooks (`/settings/webhook-log`) | Sí: envía una carga de prueba |

No hay integración LDAP.

### 9.2 Cómo funcionan las pruebas de conexión

`POST /api/v1/settings/integrations/{proveedor}/test` (capacidad `org.administrar`), implementado en
`app/services/integration_test_service.py`. Los módulos con pantalla propia (Jira, IA, reuniones, CMDB, ALM,
Del ticket al PR) tienen además su ruta de prueba.

- Cada prueba hace una llamada **real** al servicio con las credenciales de la empresa. Son de solo lectura, salvo
  Slack y Teams por webhook, cuya prueba es enviar un mensaje.
- Las sondas salen por el guardia SSRF ([§8.10](#810-ssrf-y-salidas-de-red)).
- La respuesta dice qué ha comprobado de verdad (`verificado`):

  | `verificado` | Significa |
  |---|---|
  | `nada` | No se llamó al servicio: falta configuración o el fallo es previo |
  | `configuracion` | Los campos están; la credencial necesita un flujo OAuth con usuario |
  | `alcance` | El servicio responde en esa dirección; la credencial no se ha validado |
  | `credencial` | El servicio aceptó la credencial |
  | `credencial_y_uso` | Además, la operación que usa el producto funciona con esos permisos |
  | `pasivo` | Solo secretos de entrada: se verifican al llegar el primer evento |

- Nunca devuelve el cuerpo remoto: solo el estado HTTP o la clase del error.
- Un proveedor nuevo en el almacén de credenciales sin su prueba hace fallar
  `tests/test_ronda2_transversal_2026_11_23.py`.

Que cada servicio acepte la llamada solo se sabe al pulsar el botón de prueba con credenciales reales. Lo que más
conviene confirmar: los permisos de aplicación de Graph (cada función pide el suyo; un permiso que falta se ve
como 403 al usarla), la búsqueda de Jira Cloud y la versión de API de Salesforce (`SALESFORCE_API_VERSION`). Tabla
por conector en [`docs/integraciones/pruebas_de_conexion.md`](docs/integraciones/pruebas_de_conexion.md).

### 9.3 Microsoft 365 por empresa

Cada empresa guarda su propia aplicación de Azure (`tenant_id`, `client_id`, `client_secret` cifrado) y Graph usa
siempre esa. Una credencial a medias cuenta como no configurada (503); nunca se completa con la de plataforma. Los
`AZURE_TENANT_ID`, `AZURE_CLIENT_ID` y `AZURE_CLIENT_SECRET` del entorno solo se usan para una empresa sin
credencial propia y solo con `M365_PLATFORM_CREDENTIALS_ENABLED=true` (instalación de una sola empresa).
`GET /api/v1/m365/status` dice si se usa la credencial de la `empresa` o la de `plataforma`.

### 9.4 Secretos de webhooks por empresa

- **Entrantes.** Credenciales → *Inbound webhooks* guarda por empresa el secreto de firma propio, el del relay de
  correo, el de GitHub y el de GitLab. Las variables globales (`WEBHOOK_SECRET`, `INBOUND_EMAIL_SECRET`,
  `GITHUB_WEBHOOK_SECRET`, `GITLAB_WEBHOOK_SECRET`) son el respaldo.
- **Jira.** El secreto es solo por empresa: se rota en la pantalla de Jira (o `POST /api/v1/jira/webhook-secret`).
  `JIRA_WEBHOOK_SECRET` ya no autentica nada; déjala vacía.
- **Slack y Teams.** El vínculo workspace → empresa es el ajuste en vivo `SLACK_TEAM_ID` (y `TEAMS_TENANT_ID`), no
  una variable de entorno. Sin signing secret (de la empresa o global), los eventos de Slack responden 503.
- **Stripe.** El secreto de firma del endpoint `https://<dominio>/api/v1/invoices/stripe/webhook`; sin él, 503.
- **Salientes.** Cada webhook saliente lleva `X-Contecflow-Event` y `X-Contecflow-Signature: sha256=<HMAC>`. Se
  entrega por Celery con reintentos y un cortacircuitos (`WEBHOOK_CB_THRESHOLD`, 5 fallos seguidos).
- Los secretos de los disparadores entrantes del CAB se guardan cifrados. Toda credencial cambiada queda en la
  auditoría de ajustes con la huella del valor cifrado, nunca con el secreto.

### 9.5 Conectores con contecmind y contecintelligence

contecflow **se conecta** a los otros dos productos de la casa en vez de duplicarlos: **contecmind** guarda los
documentos (versiones, permisos, OCR, aprobación) y **contecintelligence** pregunta a todas las fuentes de la
empresa (ERP, CRM, contecflow…) con métricas certificadas y un recibo firmado por respuesta. Sin configurarlos,
contecflow funciona igual y cada panel dice que no están configurados. Todo se hace con la **identidad de quien usa
contecflow**: lo que cada persona ve y puede hacer dentro del otro producto lo decide **ese producto**. Pantallas:
cualquier usuario interno (no subcontratados); configuración y estado: administración.

**Qué se trajo y qué se conecta.** Se **trajo** a contecflow lo que es trabajo diario del PSA y tiene que funcionar
sin los otros productos: base de conocimiento del portal y su bucle de calidad (citas, correcciones de experto,
preguntas sin respuesta, artículos caducados o contradictorios), Pregunta a los datos sobre el almacén propio (con
verificación, valores reales y banco de preguntas validadas), proveedor de IA por función con respaldo, tope diario
de gasto en IA, servidor MCP con gobierno, RLS en Postgres, cadena de auditoría firmada, explicador de accesos,
informe de cumplimiento, retención y bloqueo legal, reserva de documentos, lista de puesta en marcha y bot de Teams.
Se **conecta** lo que es del otro producto. Se descartó (no es de un PSA/ITSM): ingesta masiva de documentos,
recuperación avanzada sobre corpus grandes, «Studio», grafos de conocimiento, conectores a fuentes externas de
datos, ejecución de código, complemento de Excel. **SAML no se da por hecho** en esta comparativa (la antigua lo
marcaba «ya está» por existir `auth_saml.py`): su estado real está en la sección de seguridad.

**Dónde aparece (lo que ve el usuario).**

| Pantalla | Qué | Producto |
|---|---|---|
| Service Desk → ticket | Panel **Documentos**: enlazados, subir a la carpeta del ticket, buscar y enlazar, y **«Documentos que pueden resolverlo»** (por el asunto). Distinto de los adjuntos del ticket (lo que mandó el cliente) | contecmind |
| Proyectos → proyecto → **Documentos** | El mismo panel y **preguntar a los documentos del proyecto** (respuesta con citas numeradas y página) | contecmind |
| Contratos → contrato | El mismo panel con preguntas («¿cuándo vence?») | contecmind |
| Base de conocimiento (operador) → artículo | Documentos de origen del artículo. El portal de clientes **no** los muestra | contecmind |
| **Lecciones aprendidas** → lección; **Gastos** → gasto; **Presupuestos** → presupuesto → pestaña **Documentos** | El mismo panel (23-11-2026; antes el servidor respondía 404 `tipo_desconocido`) | contecmind |
| Búsqueda (`/search`) | Grupo **Documentos · contecmind** debajo de los resultados propios | contecmind |
| Ventana de documento | Tipo, tamaño, estado, revisión, bloqueo, extracto, **versiones con su estado**, **pedir aprobación** de una versión, descargar el original | contecmind |
| Analítica → **Preguntar a la empresa** (`/ask-company`) | Pregunta → progreso en vivo → respuesta con gráfico y tabla, la consulta usada y el **recibo firmado** (verificable). Pestaña **Métricas certificadas**: consultar con desglose, **«¿Por qué cambió?»** entre dos periodos y (23-11-2026) **Anomalías**: los puntos del periodo que se apartan de la historia de la métrica, con lo esperado y la desviación | contecintelligence |
| **Panel BI** (`/bi`) | (23-11-2026) **Métricas de toda la empresa**: cada analista añade métricas certificadas que se consultan directamente a contecintelligence con un token de lectura de pocos minutos. Solo aparece si el origen está permitido en la CSP (abajo) | contecintelligence |
| Data Explorer → Pregunta a los datos | Tras una respuesta, **«Preguntar en contecintelligence»** lleva la misma pregunta a `/ask-company` (`CONTECINTELLIGENCE_HANDOFF_ENABLED`) | contecintelligence |
| Configuración → Credenciales → **Conectores propios** | Por producto: configurado o no, llamadas, fallos, latencia p50/p95, último error, tabla por operación y **Probar** | los dos |

**Cómo se configura.**
1. **En contecmind** (su administración, `/api/v1/admin/apps`): crear una aplicación con `documents:read`,
   `documents:search` y, para subir, `documents:write`; asociar el *tenant* externo = **id de la empresa en
   contecflow** con su *tenant*.
2. **En contecintelligence** (`/api/admin/apps`): aplicación con `chat:ask`, `sources:read`, `metrics:read` y
   `receipts:read`; el mismo *tenant* externo.
3. **En contecflow**: Configuración → Credenciales → `contecmind` (URL base, client id, secreto, área opcional) y
   `contecintelligence` (URL base, client id, secreto, fuente por defecto). Cambiar una credencial olvida los
   tokens guardados. Comportamiento: Configuración → Config. dinámica → Conectores (`CONECTOR_*`, `CONTECMIND_*`,
   `CONTECINTELLIGENCE_*`, ver [`docs/REFERENCIA_DE_AJUSTES.md`](docs/REFERENCIA_DE_AJUSTES.md)).
4. **Métricas incrustadas** (opcional): `CONTECINTELLIGENCE_EMBED_ORIGINS=https://ci.miempresa.com` (CSV de
   orígenes). Solo esos orígenes se añaden al `connect-src` de la CSP que manda `app/main.py` (y la de desarrollo
   de `vite.config.js`, que lee la misma variable); con el nginx del frontend (`frontend/nginx.frontend.conf`) hay
   que añadirlos a mano en su `connect-src`. Un valor con ruta, espacios o `;` se descarta. Sin la variable, el
   token ni se pide (`incrustable: false`) y todo pasa por contecflow.

**Cómo se prueba.** Botón **Probar** del panel de conectores: «¿vivo?» y «¿listo?» por separado (contecmind
`/health` y `/health/ready`; contecintelligence `/livez` y `/readyz`), después la credencial de aplicación y luego el
canje con la identidad del administrador (empresa dada de alta). Después: abrir un ticket con el conector
configurado (panel de documentos y sugerencias), una lección / un gasto / un presupuesto (panel de documentos), y
en `/ask-company` una métrica → **Anomalías**.

**Cómo funciona (técnico).**
- contecflow es una *aplicación anfitriona* de cada producto: credencial de aplicación → token de aplicación
  (`POST {api}/oauth/token`, en caché hasta poco antes de caducar) → canje por un **token delegado de la persona**
  (`POST {api}/tokens/exchange` con `tenant` = empresa, `subject` = correo, `role`, `scopes`, `ttl_s`). El
  navegador nunca ve la credencial de aplicación.
- **Rol.** contecmind: `reader` siempre; `writer` solo para escribir y solo para `CONTECMIND_WRITER_ROLES`.
  contecintelligence: `analyst` para `CONTECINTELLIGENCE_ANALYST_ROLES`, `viewer` el resto (las métricas le dan
  403 y la pantalla lo explica).
- **Fichas.** Cada tipo de ficha se carga con **el mismo cargador que su pantalla**, en
  `app/services/conectores/fichas.py`: ticket (`get_scoped_ticket_or_404`), proyecto
  (`get_project_scoped_or_404`), contrato (solo responsables), artículo (`get_scoped_kb_article_or_404`) y, desde el
  23-11-2026, **lección** (`proyectos.usar` + la visibilidad por origen de `lecciones._puede_ver`), **gasto**
  (`gastos.trabajar` + `gastos_avanzados._gasto`: el dueño o quien lo gestiona) y **presupuesto**
  (`presupuestos.gestionar`). Quien no puede abrir la ficha no ve ni toca sus documentos.
- **Carpetas** (`carpetas_documentales`): `CONTECMIND_ROOT_FOLDER / <tipo> / <código — nombre>`, creada al primer
  subir. **Enlaces** (`enlaces_documentales`): quitar un enlace no borra el documento; todo enlace y desenlace se
  audita. **Subida**: tope `CONTECMIND_UPLOAD_MAX_MB` y `Idempotency-Key`.
- **Errores con nombre** en la cabecera `X-Conector-Codigo`: `no_configurado` (409), `no_alta` (403), `sin_permiso`
  (403), `no_encontrado` (404), `rechazado` (502), `no_responde` / `no_listo` (503).
- **Registro** (`conector_llamadas`): operación, resultado, HTTP y ms de cada llamada, incluidos los tokens
  incrustables; `purgar_registro_de_conectores` (03:05) borra lo anterior a `CONECTOR_LOG_RETENTION_DAYS`.
- **Endpoints** (`/api/v1/conectores`): `GET /estado`, `POST /{producto}/probar`; contecmind `GET /contecmind/disponible`,
  `…/buscar`, `…/documentos/{id}[/original|/aprobacion]`, `GET|POST …/fichas/{ficha}/{id}/documentos`,
  `DELETE …/documentos/{enlace}`, `GET …/sugerencias`, `POST …/subir`, `GET …/carpeta`, `POST …/preguntar`
  (`ficha`: `ticket`, `contract`, `project`, `kb_article`, `lesson`, `expense`, `budget`); contecintelligence
  `GET …/disponible`, `…/fuentes`, `POST …/preguntar[/directo]` (SSE), `GET …/metricas`,
  `POST …/metricas/consultar|explicar|anomalias`, `GET …/recibos/{id}[/verificar]`, `POST …/token` (devuelve
  `incrustable`, `origen`, `access_token`, `expires_in`, `base_url`).
- **Código**: `app/services/conectores/` (`anfitrion.py`, `contecmind.py`, `contecintelligence.py`, `fichas.py`,
  `estado.py`), `app/api/v1/endpoints/conectores.py`; pantallas `frontend/src/components/conectores/*`
  (`DocumentosDeFicha`, `AnomaliasDeMetrica`, `MetricasIncrustadas`) y `pages/PreguntarALaEmpresaPage.tsx`;
  `conectoresApi` en `frontend/src/services/api/conectores.ts`.
- **GRC.** Tablas con `organization_id` y RLS (migración `141_conectores_contec`). Sin datos personales nuevos: el
  token incrustable dura `CONECTOR_TOKEN_TTL_SECONDS` (300 s), solo lleva alcances de lectura y no se guarda.

**Qué está verificado y qué no (medido, no supuesto).**
- **Verificado contra un doble que sigue el contrato** de cada producto (canje con rol y alcances, escrituras que
  exigen `writer`, subida idempotente, el SSE real): `tests/test_conectores_contec_2026_11.py`. Contra los productos
  en marcha (05-11-2026): rutas de vida y disponibilidad, la ruta de token y su rechazo de una credencial mala.
- **No verificado de extremo a extremo** con una aplicación registrada en los productos reales: no se ha dado de
  alta ninguna desde aquí. Tampoco las fichas nuevas, las anomalías y las métricas incrustadas contra
  contecintelligence real (sus tests, `tests/test_conectores_y_semantico_2026_11_23.py`, usan dobles); la forma
  de la respuesta de anomalías sale de su código (`POST /metrics/anomalies`: `metrica`, `metodo`, `sql`, `puntos`,
  `anomalias`).
- **Límites en los otros productos** (no se cambian desde aquí): en contecmind, subir una **versión nueva** solo
  existe en `/admin/documents/{id}/control/versions` (cerrada a integraciones), y `/qa` y `/ask` sobre todo el
  corpus también están cerradas (se pregunta a la carpeta de la ficha). contecintelligence manda
  `frame-ancestors 'none'`: no se puede incrustar en un `<iframe>`, por eso el panel BI pinta sus propias tarjetas
  con el token acotado (mismo contrato que su `<ci-metric>`, que no se distribuye empaquetado). Ninguno de los dos
  analiza cláusulas de contratos.

---

## 10. Copias de seguridad y restauración

### 10.1 Qué hay que copiar

- La base de datos (PostgreSQL o el fichero SQLite).
- Los ficheros: el volumen `contecflow_s3_data` (Docker) o la carpeta `uploads/` (`UPLOAD_DIR`) en local.
- El `.env`: los secretos de integraciones guardados en la base se cifran con una clave derivada de `SECRET_KEY` (`app/core/encryption.py`); sin ella no se pueden leer. Guárdalo aparte y protegido. Por lo mismo, no cambies `SECRET_KEY` sin el procedimiento de rotación ([8](#8-seguridad)).

### 10.2 `scripts/backup.sh`

Para el stack Docker (usa los contenedores `postgres` y el volumen S3):

```bash
./scripts/backup.sh                       # deja la copia en ./backups/contecflow-<fecha>
BACKUP_DIR=/srv/copias BACKUP_KEEP=30 ./scripts/backup.sh
```

1. `pg_dump -Fc` desde el contenedor `postgres` y comprobación con `pg_restore --list`.
2. El volumen `S3_VOLUME` (por defecto `contecflow_s3_data`) en `ficheros.tar.gz`, comprobado con `tar tzf`.
3. `MANIFIESTO` con la fecha, la revisión de Alembic y la huella SHA-256 de cada pieza.
4. Retención: conserva las `BACKUP_KEEP` más recientes (14) y borra las demás.

Variables: `BACKUP_DIR`, `BACKUP_KEEP`, `S3_VOLUME`, `POSTGRES_USER`, `POSTGRES_DB` (del entorno o del `.env`). Si un paso falla, borra la copia a medias y sale con error. La copia **no se cifra**: guárdala en un destino con control de acceso (contiene datos personales).

**Instalación local (SQLite o PostgreSQL sin Docker, y `uploads/`)**: `./setup.sh backup`, `setup.bat backup` o `make backup` (los tres llaman a `scripts/copia_local.py`):

1. SQLite: copia consistente con la API de backup de `sqlite3` (vale con la app arrancada y el WAL activo) y `PRAGMA integrity_check` sobre la copia. PostgreSQL local: `pg_dump -Fc` (contraseña por `PGPASSWORD`) y `pg_restore --list`.
2. `UPLOAD_DIR` (por defecto `uploads/`) en `uploads.zip`, comprobado con `testzip`. Si hay almacenamiento S3 configurado, avisa: eso lo copia `scripts/backup.sh`.
3. `MANIFIESTO` con fecha, motor, revisión de Alembic y SHA-256 de cada pieza (mismo formato que `backup.sh`).
4. Carpeta `backups/contecflow-local-<fecha>`; retención `BACKUP_KEEP` (14). Si un paso falla, borra la copia a medias.

### 10.3 Copias automáticas

No hay ninguna tarea del worker que haga copias. Programa `scripts/backup.sh` con el cron del anfitrión, por ejemplo:

```cron
30 2 * * * cd /srv/contecflow && ./scripts/backup.sh >> /var/log/contecflow-backup.log 2>&1
```

Además: `scripts/deploy.sh` hace una copia antes de cada despliegue (y se para si falla) y `scripts/migrar.py` copia antes de las migraciones destructivas ([5.4](#54-copia-automática-antes-de-migrar)).

### 10.4 Restaurar

```bash
./scripts/restore.sh backups/contecflow-20261109-101500 --borra-lo-que-hay
```

1. Comprueba las huellas del `MANIFIESTO`: una copia dañada o alterada no se restaura.
2. Para `api`, `worker` y `beat`.
3. `pg_restore --clean --if-exists --no-owner` sobre la base.
4. Vacía el volumen S3 y descomprime los ficheros.
5. Vuelve a arrancar `api`, `worker` y `beat` e imprime la revisión de Alembic de la copia.

Sin `--borra-lo-que-hay` no hace nada. No mira `ENVIRONMENT` (es la vía de recuperación también en producción). Si el código desplegado espera una revisión más nueva que la de la copia, el servicio `migrate` la llevará a la cabeza al volver a levantar con `--profile app up -d`.

**Instalación local**: `./setup.sh restore <carpeta>`, `setup.bat restore <carpeta>` o `make restore COPIA=<carpeta>` (vale también la ruta del `MANIFIESTO`):

1. Verifica la copia entera sin tocar nada: huellas del `MANIFIESTO`, `integrity_check` de la base y `testzip` de `uploads.zip` (rechaza rutas fuera de la carpeta). Una copia dañada no se restaura.
2. Para la app (en Windows, con la base abierta no se puede reemplazar el fichero) y pide escribir `RESTAURAR`.
3. Guarda antes lo actual en `backups/contecflow-local-<fecha>-antes-de-restaurar` (no entra en la retención).
4. Restaura la base (API de backup de SQLite sobre el fichero de `DATABASE_URL`, o `pg_restore --clean --if-exists --no-owner`) y el contenido de `uploads/`, y vuelve a comprobar la integridad. El motor de la copia tiene que coincidir con el de `DATABASE_URL`.
5. `start` aplica después las migraciones que falten.

### 10.5 Prueba de restauración

Las copias locales contienen datos personales: mismo control de acceso que la base, y bórralas cuando dejen de hacer falta (la supresión RGPD no llega a ellas). Haz una prueba periódica en otro proyecto de compose o en otra máquina:

1. `./scripts/backup.sh` en producción y copia la carpeta a la máquina de pruebas (con su `.env`).
2. Crea los volúmenes externos y levanta `docker compose up -d` (solo infraestructura).
3. `./scripts/restore.sh <copia> --borra-lo-que-hay`.
4. Levanta `--profile app`, entra con un usuario real y abre un documento adjunto.
5. Comprueba que `python -m alembic current` coincide con la línea `alembic:` del `MANIFIESTO` (o con la cabeza, si migró).

---

## 11. Actualizar a una versión nueva

### 11.1 Instalación local

```bash
git pull
./setup.sh update          # Windows: setup.bat update
./setup.sh start           # Windows: setup.bat start
```

`update` reinstala dependencias de Python y npm solo si cambiaron, completa el `.env`, migra con `scripts/migrar.py` (copia previa si hay revisiones destructivas, una sola cabeza), comprueba el esquema real y prepara el rol de aplicación. `start` vuelve a aplicar las migraciones pendientes antes de arrancar, así que un `git pull` seguido de `start` tampoco deja la base atrás.

### 11.2 Docker / producción

```bash
git pull
./scripts/deploy.sh
```

`scripts/deploy.sh`: descarga las imágenes (si `CONTECFLOW_APP_IMAGE`/`CONTECFLOW_WEB_IMAGE` apuntan a un registro; con `GHCR_USER`/`GHCR_TOKEN` para ghcr.io) o las construye, hace `scripts/backup.sh` (si la base está en marcha y la copia falla, se para), `docker compose --profile app up -d` comprobando que `migrate` sale con 0, y `GET /health` por nginx. A mano: `./scripts/backup.sh && docker compose --profile app up -d --build`. Con observabilidad: `./setup.sh docker`.

### 11.3 Variables nuevas

Compara tu `.env` con `.env.example` después de cada actualización: un `.env` antiguo no tiene las variables nuevas y, en `staging`/`production`, el arranque falla diciendo cuál falta o es inválida. `tests/test_env_example_sincronizado.py` obliga a que cada campo nuevo de `Settings` esté en `.env.example` o en una familia de ajustes finos declarada fuera, y a que todo secreto esté documentado. Referencia: `docs/REFERENCIA_DE_AJUSTES.md`.

### 11.4 Antes y después

1. Copia de seguridad ([10](#10-copias-de-seguridad-y-restauración)).
2. `python -m alembic current` y `python -m alembic heads`: anota de dónde vienes.
3. Lee `CHANGELOG.md` y `docs/DESPLIEGUE.md` («B. Actualizar un entorno existente»): qué migraciones mueven o borran datos, variables nuevas y cómo volver atrás.
4. Tras el arranque: pruebas de humo de `docs/DESPLIEGUE.md` («C») y `python scripts/smoke_check.py` ([12.4](#124-comprobaciones-tras-desplegar)).
5. Para volver atrás, restaura la copia: `alembic downgrade` no recupera el estado en todas las revisiones.

---

## 12. Despliegue en producción

Guía completa: `docs/DESPLIEGUE.md`. Esta lista sale de los validadores de `Settings` (`app/core/config.py`, `app/core/config_groups/proceso_config.py`) y de las comprobaciones de arranque de `app/main.py` y `app/core/comprobacion_de_produccion.py`: con `ENVIRONMENT=production` (o `staging`) la API **se niega a arrancar** si no se cumple lo marcado como «bloquea».

### 12.1 Lista de comprobación

**Entorno y secretos**

- [ ] `ENVIRONMENT=production` (admitidos: `development`, `test`, `staging`, `production` y sus alias, que se normalizan; otro valor no arranca). El compose lo pone por defecto si falta.
- [ ] `SECRET_KEY`: ≥ 32 caracteres, ≥ 10 distintos, no un marcador ni el valor de ejemplo (bloquea siempre). Genera con `python -c "import secrets; print(secrets.token_hex(32))"`.
- [ ] `CLIENT_PORTAL_SECRET`: ≥ 32 caracteres y ≥ 10 distintos (bloquea).
- [ ] `SUPERADMIN_PASSWORD`: no un marcador ni una contraseña conocida, ≥ 16 caracteres y ≥ 8 distintos (bloquea).
- [ ] `DEFAULT_USER_PASSWORD`: no un marcador ni `contecflow2024!` (bloquea).
- [ ] `WEBHOOK_SECRET` e `INBOUND_EMAIL_SECRET`: definidos y ≥ 24 caracteres (bloquea).
- [ ] `JWT_ALGORITHM`: `HS256`, `HS384` o `HS512` (bloquea).
- [ ] `.env` fuera del repositorio, con permisos restringidos y copia aparte.

**URLs, orígenes y proxy**

- [ ] `ALLOWED_ORIGINS`: lista explícita, sin `*` ni `localhost`/`127.0.0.1` (bloquea). Debe incluir el origen público: el middleware CSRF rechaza con 403 lo que no esté.
- [ ] `FRONTEND_URL`, `BACKEND_URL`, `BASE_URL`, `WEBAUTHN_ORIGIN` con la URL pública, no `localhost` (bloquea); `WEBAUTHN_RP_ID` con el dominio real (bloquea).
- [ ] `APP_PUBLIC_URL` vacío (usa `FRONTEND_URL`) o público; remitente de correo real (`SMTP_FROM` o `NOTIFICATION_EMAIL_FROM` sin dominios de ejemplo); sin `DOCUSIGN_DEMO=true`; `ADOBE_SIGN_BASE_URL` si hay `ADOBE_SIGN_CLIENT_ID`; buses y búsqueda (`COLLAB_*`) sin `localhost` (bloquea).
- [ ] HTTPS en el proxy de delante. En `production`/`staging` las cookies de sesión y CSRF llevan `Secure` (no funcionan por HTTP) y en `production` se envía HSTS (`max-age=31536000; includeSubDomains; preload`).
- [ ] Proxy: conserva `Host` (o envía `X-Forwarded-Host`) y envía `X-Forwarded-Proto: https`. Fuera del compose, `TRUST_PROXY_HEADERS=true` y `TRUSTED_PROXY_CIDRS` con la red del proxy; si no, la IP de cliente (limitador, riesgo de sesión) será la del proxy.
- [ ] `EXPOSE_API_DOCS` sin activar (en `production` no se publican `/api/v1/docs`, `/redoc` ni `openapi.json`).

**Base de datos, Redis y planificador**

- [ ] PostgreSQL y rol de aplicación sin propietario ni `BYPASSRLS` (`APP_DB_USER`/`APP_DB_PASSWORD`; servicio `migrate` o `scripts/rol_de_aplicacion.py`). Con `RLS_REQUIRED` sin fijar se exige en `staging`/`production` (bloquea).
- [ ] Migraciones aplicadas antes de arrancar: con `FAIL_ON_SCHEMA_DRIFT` sin fijar, la deriva bloquea. Opcional: `EXPECTED_ALEMBIC_REVISION=<cabeza actual>`.
- [ ] Redis accesible y con contraseña (`REDIS_PASSWORD`). En `production` el limitador exige Redis (`RATE_LIMIT_REQUIRE_REDIS_IN_PRODUCTION`, activo por defecto; bloquea).
- [ ] Un solo Celery beat y `ENABLE_APSCHEDULER=0`, `ENABLE_CELERY_BEAT=1`. Los dos a la vez bloquean (`FAIL_ON_DUAL_SCHEDULER`); APScheduler en producción sin beat solo avisa (tareas repetidas con varios workers).
- [ ] `DISABLE_CSRF_MIDDLEWARE` sin activar (bloquea en `staging`/`production`); `ENABLE_SUPERADMIN_BYPASS` sin activar (solo arranca con `development` + SQLite).
- [ ] `TENANT_SESION_SIN_CONTEXTO=cerrar` (por defecto); `TENANT_AUTO_FILTER_GLOBAL` y `TENANT_AUTO_STAMP_ON_INSERT` activos (apagados arrancan, pero con aviso CRITICAL).

**Operación**

- [ ] `METRICS_AUTH_TOKEN` definido (sin él `/metrics` responde 401 fuera de desarrollo y Prometheus no lee).
- [ ] Copias programadas (`scripts/backup.sh` por cron) y una prueba de restauración hecha ([10.5](#105-prueba-de-restauración)).
- [ ] Alertas con receptor (`ALERT_WEBHOOK_URL` o `ALERT_EMAIL_*` + `ALERT_SMTP_*`).
- [ ] `GRAFANA_ADMIN_PASSWORD` fuerte; puertos solo en `127.0.0.1` salvo lo que publique el proxy.
- [ ] `GEOIP_LOOKUP_ENABLED` solo con base legal y contrato (envía la IP de cada inicio de sesión a un tercero); ver [15](#15-grc-auditoría-retención-rgpd-y-cumplimiento).

### 12.2 Arranque

```bash
docker volume create contecflow_postgres_data && docker volume create contecflow_s3_data
./scripts/deploy.sh                      # o: docker compose --profile app up -d
docker compose --profile observability up -d
```

### 12.3 Primer administrador

Ni la semilla ni `reset_to_admin_only.py` corren con `ENVIRONMENT=production`. En una base **recién migrada y vacía** se puede crear el admin una sola vez forzando el entorno para ese proceso:

```bash
docker compose --profile app run --rm -e ENVIRONMENT=development api python scripts/reset_to_admin_only.py
```

**Borra todos los datos**: nunca sobre una base con datos. No verificado en ejecución. Después, entra como `admin` y crea las empresas y los usuarios desde la aplicación.

Para **crear o restablecer** el admin sin borrar nada (también en producción): `python scripts/reset_to_admin_only.py --solo-admin` (o `make init-admin`). Usa `SUPERADMIN_EMAIL` y `SUPERADMIN_PASSWORD` del `.env`, que `Settings` exige fuertes fuera de desarrollo, cierra las sesiones del admin y deja la acción en la auditoría.

### 12.4 Comprobaciones tras desplegar

1. `GET /health` → 200 y `GET /ready` → 200 con `db` y `redis` en `ok`.
2. `python -m alembic current` igual a `python -m alembic heads`.
3. `curl -H "Authorization: Bearer $METRICS_AUTH_TOKEN" http://api:8000/metrics` → 200; sin cabecera → 401.
4. `python scripts/smoke_check.py`: entra como `admin` (contraseña en `SMOKE_ADMIN_PASS` o `DEFAULT_USER_PASSWORD`) y crea un ticket sin cliente. Apunta a `http://127.0.0.1:8000`: en Docker, la API no publica ese puerto; ejecútalo dentro del contenedor `api` o en local.
5. Resto (correo entrante, Stripe, Jira, Slack/Teams, Twilio, passkeys): `docs/DESPLIEGUE.md`, «C».

---

## 13. Monitorización y tareas programadas

### 13.1 Sondas de salud

| Ruta | Respuesta | Uso |
|---|---|---|
| `GET /health` | `{"status": "ok", "db": "ok"\|"error"}`; en desarrollo añade `version` y `project`. Siempre 200 (el error de base va al log, no a la respuesta) | Vida del proceso; healthcheck del compose y de `deploy.sh` |
| `GET /ready` | 200 o 503 con `checks` de `db`, `redis`, `celery_broker` y `scheduler`. En `staging`/`production` solo el `status` de cada una; en desarrollo, también el modo del planificador y el entorno | Preparación: falla si la base o Redis no responden, o si hay dos planificadores en producción |
| `GET /metrics` | Formato Prometheus, con `Bearer` | [4.5](#45-prometheus-alertmanager-y-grafana) |

### 13.2 Métricas, alertas y logs

- Métricas HTTP (tasa, errores, latencia), por empresa, de negocio (con caché), de Celery, PostgreSQL, Redis y máquina. Reglas en `ops/prometheus/rules/` con severidades `critical`, `warning` e `info`: API caída, 5xx > 5 %, p95 > 2 s, worker o beat caídos, cola atascada, PostgreSQL/Redis caídos o al límite, disco/memoria, presupuesto de IA agotado, SLA incumplidos, vulnerabilidades críticas, ráfagas de logins fallidos… Lista y umbrales: `docs/OBSERVABILIDAD.md`.
- Logs: nivel con `LOG_LEVEL` (por defecto `INFO`). En local, ficheros de [3.6](#36-logs-y-pid); en Docker, `docker compose logs`. En `staging`/`production` las trazas de errores no controlados se guardan sin datos personales en el mensaje y la respuesta lleva un `request_id` para buscarlas. Opcionales: Sentry (`SENTRY_DSN`) y OpenTelemetry (`OTEL_ENABLED` + `OTEL_EXPORTER_OTLP_ENDPOINT`).

### 13.3 Planificador: Celery beat o APScheduler

| Variable | Defecto | Efecto |
|---|---|---|
| `ENABLE_CELERY_BEAT` (alias `CELERY_BEAT`) | `0` | Declara que corre un `celery beat` aparte |
| `ENABLE_APSCHEDULER` | `1` | APScheduler dentro de la API replica todo `beat_schedule` (`_replicar_celery_beat`), con almacén de trabajos en la base |
| `FAIL_ON_DUAL_SCHEDULER` | `1` | Con los dos activos, la API no arranca |

El compose usa Celery beat (`ENABLE_APSCHEDULER=0`, `ENABLE_CELERY_BEAT=1`). `setup.sh` y `setup.bat` eligen al arrancar (`scripts/modo_tareas.py`): Celery beat si hay un Redis que responda; si no, APScheduler dentro de la API (un solo proceso), con aviso y sin lanzar worker ni beat. En modo integrado lo que se encola al momento con `.delay()` no se ejecuta. APScheduler sirve para un solo proceso; con varios procesos de API repetiría tareas. Broker y resultados de Celery: `REDIS_URL`. Zona horaria del calendario: `DEFAULT_TIMEZONE` (por defecto `Europe/Madrid`).

### 13.4 Calendario

`beat_schedule` (`app/worker.py`) tiene **57 entradas**. Resumen por área:

| Área | Entradas | Ejemplos (frecuencia) |
|---|---|---|
| Service Desk e ITSM | 13 | SLA/OLA (cada 5 min), lectura de buzones (2 min), eventos de ticket: avisos, correos, webhooks (cada minuto), detección de problemas, impacto de cambios, enrutado, predicción, KEDB, calidad de la KB, correlación de alertas, agente autónomo |
| Proyectos, tiempo y personas | 10 | Recordatorios de evaluación e imputaciones (15 min), ausencias, caducidad de externos, curva S de EVM, plazos de demanda, avisos y papelera del cuaderno, sondeo y retención de reuniones |
| BI, analítica y ML | 8 | Informes programados (cada hora), ETL OLAP nocturno, instantáneas, envíos y KPI de BI, conectores ETL, reentrenos (mensual y semanal) |
| Seguridad, GRC y plataforma | 7 | Rotación de claves, seguridad de cuentas, cumplimiento (semanal), purga de empresas caducadas, retención de datos, purga de registros de conectores y caché de traducciones |
| CMDB, licencias y activos | 7 | Descubrimiento CMDB (15 min), software diario, ALM diario, caducidad de activos, uso de licencias, altas y bajas |
| Finanzas | 4 | Facturas de iguala, reconocimiento de ingresos (diario), recordatorio de presupuestos, tipos de cambio del BCE |
| Automatizaciones y aprobaciones | 4 | Eventos y escaneo de automatizaciones, temporizadores BPMN (cada minuto), vencimiento de aprobaciones (cada hora) |
| Avisos | 2 | Motor de alertas (15 min), resumen diario de avisos |
| Integraciones | 2 | Sincronización con Jira (30 min) y del ticket al PR (5 min) |

Además hay tareas bajo demanda (entrega de webhooks con reintentos, trabajo encolado, agente en segundo plano, sincronización de un conector). Tabla completa, contexto de empresa de cada tarea, límites y uso manual: `docs/WORKER_TASKS.md`.

---

## 14. Resolución de problemas

| Síntoma | Causa | Solución |
|---|---|---|
| La API no arranca: `SECRET_KEY must be at least 32 characters long`, `must be changed from the default value` o `entropy is too low` | `SECRET_KEY` corta, marcador o poco variada | `python -c "import secrets; print(secrets.token_hex(32))"` en `.env`; los setup la regeneran solos |
| `ENVIRONMENT must be one of development, test, staging, production (alias: …), got '...'` | Valor desconocido (p. ej. `desarrollo`) | Usa `development`, `test`, `staging` o `production`, o un alias (`dev`, `local`, `demo`, `testing`, `stage`, `pre`, `preprod`, `prod`, `prd`). Desde el 23-11-2026 los alias que aceptan los scripts arrancan también la API |
| `SUPERADMIN_PASSWORD is a known weak/default value`, `must be at least 16 characters`, `WEBHOOK_SECRET must be configured in production`, `ALLOWED_ORIGINS contains localhost values` | Validadores de producción | Lista de [12.1](#121-lista-de-comprobación) |
| `Configuración de desarrollo en un entorno real; no arranca:` | `localhost` o dominios de ejemplo en `APP_PUBLIC_URL`, remitente, OpenSearch, NATS, Redis del bus, DocuSign demo… | Corrige cada línea listada |
| `Schema drift detectado…` o `No existe tabla alembic_version` | Migraciones sin aplicar (deriva bloquea en `staging`/`production`) | `python scripts/migrar.py`; luego `python scripts/comprobar_esquema.py` |
| `[ERROR] La base NO tiene el esquema de los modelos aunque Alembic diga que esta al dia` | Base marcada con `alembic stamp` sin ejecutar revisiones, o copiada de otra máquina | Copia la base, `python -m alembic stamp <última revisión aplicada de verdad>` y `python -m alembic upgrade head` |
| `[ERROR] La cadena de migraciones tiene 2 cabezas` | Dos migraciones cuelgan de la misma anterior | Encadénalas (cambia `down_revision`) o `python -m alembic merge heads` |
| `[ERROR] Las migraciones han fallado: …` | Error en una revisión | Lee el error; restaura la copia de `backups/antes_de_migrar_*` ([5.4](#54-copia-automática-antes-de-migrar)) o la de `scripts/backup.sh` y corrige antes de repetir |
| `[ERROR] No se ha podido hacer la copia previa a las migraciones` | `pg_dump` falla o no hay permiso en `backups/` | Arréglalo, o con conocimiento de causa `MIGRATION_BACKUP_MODE=off` |
| `[AVISO] … no se encuentra pg_dump en el PATH` | Cliente de PostgreSQL no instalado | Instálalo o haz `./scripts/backup.sh` antes de migrar |
| `RLS_REQUIRED: aislamiento en la base (RLS) desarmado: … Conecta con APP_DB_USER` | La app conecta como dueño o superusuario en `staging`/`production` | Ejecuta `scripts/rol_de_aplicacion.py` (o el servicio `migrate`) y usa `APP_DB_USER` en `DATABASE_URL` |
| `Dual scheduler mode detected (APScheduler + Celery Beat)` | Los dos planificadores activos | `ENABLE_APSCHEDULER=0` con beat, o `ENABLE_CELERY_BEAT=0` sin él |
| `Rate limiter backend is not available. Redis is required in production` | Redis caído o `REDIS_URL` mal en producción | Levanta Redis y revisa `REDIS_URL`/`REDIS_PASSWORD` |
| `El backend no respondió en 60 segundos` / `El puerto 8000 sigue ocupado` | Puerto ocupado o error de Python | `lsof -i :8000` (Windows: `netstat -ano`), lee `/tmp/contecflow-backend.log` o `%TEMP%\contecflow-backend.err.log`; cambia `BACKEND_PORT` |
| `Celery worker no ha arrancado (¿Redis parado?)`; tareas que no corren (SLA, buzón, avisos) | Sin Redis o sin `REDIS_URL` (en Windows el `.env` del setup no la trae) | Levanta Redis (`docker compose up -d redis`) y define `REDIS_URL`; revisa los logs del worker y beat |
| Worker de Celery falla en Windows | El pool por defecto no funciona en Windows | `--pool=solo` (lo pone `setup.bat`) |
| Docker no disponible y el setup sigue con SQLite | `setup.sh` vuelve a SQLite si Docker o el `up` fallan | Arranca Docker y repite `./setup.sh update`; mira el aviso «usando SQLite como fallback» |
| `external volume "contecflow_postgres_data" not found` | Máquina nueva sin los volúmenes externos | `docker volume create contecflow_postgres_data contecflow_s3_data` |
| `define POSTGRES_PASSWORD` (u otra) al hacer `up` | Variable obligatoria del compose ausente | `./setup.sh update` o `setup docker` la generan; o defínela en `.env` |
| Grafana no arranca: `GRAFANA_ADMIN_PASSWORD vacia o 'admin'` | Contraseña de Grafana no definida | `setup docker` la genera; o defínela |
| `node-exporter/cAdvisor no arrancaron` | Docker Desktop no expone lo que necesitan | Normal en Windows/macOS: el resto funciona y esos paneles quedan vacíos |
| `npm install falló` / `Vite no encontrado` / `Errores en JSX detectados` | Dependencias rotas o código inválido | `cd frontend && npm install --legacy-peer-deps`; borra `node_modules` si persiste; corrige lo que marque `validate.cjs` |
| Login con 403 `CSRF protection: origin not allowed` | El origen del navegador no está en `ALLOWED_ORIGINS` | Añádelo (p. ej. `http://localhost:8080` en Docker, el dominio público en producción) |
| La sesión no se mantiene por HTTP | En `staging`/`production` las cookies llevan `Secure` | Sirve por HTTPS, o usa `ENVIRONMENT=development` solo en local |
| Respuestas 429 | Limitador (`RATE_LIMIT_DEFAULT`, por defecto `200/minute`; el login tiene su propio límite por IP) | Espera o ajusta el límite; detrás de proxy, configura `TRUSTED_PROXY_CIDRS` para que no cuente a todos como la IP del proxy |
| No salen correos | Sin `SMTP_HOST` el envío se registra y no sale | Configura `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` ([9](#9-integraciones-y-pruebas-de-conexión)) |
| `ERROR: Sembrar los datos de demostración borra datos y ENVIRONMENT=…` (salida 2) | Semilla o `clean` fuera de desarrollo | Solo en desarrollo o pruebas; en producción ver [12.3](#123-primer-administrador) |
| `DEFAULT_USER_PASSWORD still has a placeholder value` | Marcador en `.env` | Pon una contraseña o ejecuta el setup |
| `setup.bat demo` deja la base sin usuarios con `UnicodeEncodeError` | Consola sin UTF-8 al sembrar | El script fija `PYTHONUTF8=1`; si lanzas la semilla a mano, haz `set PYTHONUTF8=1` |
| `SQLite quick_check falló` | Restos de un cierre brusco | El setup limpia `-wal`/`-shm`; si sigue, borra la base y migra de nuevo (solo en desarrollo) |
| No entra `admin` | `SUPERADMIN_PASSWORD` y `DEFAULT_USER_PASSWORD` difieren | Prueba las dos ([3.9](#39-primer-acceso-y-usuarios-demo)) |

---

## 15. GRC: auditoría, retención, RGPD y cumplimiento

Casi todo está en **Configuración → Seguridad y GRC → GRC y segregación de funciones** (`/settings/grc`, capacidad
`org.administrar`, rol `admin`). Sus pestañas: Matriz de permisos, Segregación SoD, Violaciones, Flujos de
mitigación, Registro de auditoría, Explicar acceso, Informe de cumplimiento, Marcos y evidencias, y Retención.

| Para quién | Qué |
|---|---|
| Dirección (`admin`, `org.administrar`) | GRC, auditoría, retención y bloqueo legal, informe de cumplimiento |
| Dirección (`seguridad.administrar`) | Políticas de cuenta y campañas de recertificación |
| Responsables (`seguridad.recertificar`: admin, PM, jefe de equipo, RRHH) | Revisar los accesos que les tocan |
| Dirección (`cab.administrar`) | Solicitudes RGPD |
| Dirección (`gobierno.administrar`, `ia.administrar`) | Gobierno de IA |
| Superadmin | Baja de empresas, exportación completa, «entrar como» |

### 15.1 Registro de auditoría inmutable

- **Qué se audita.** `audit_log()` (`app/services/audit.py`) registra usuario, acción, recurso, valores anterior y
  nuevo, IP y navegador. Lo llaman los servicios en cada acción sensible: inicios de sesión (contraseña, OIDC y SAML,
  también los rechazados por SAML), cambios de contraseña y MFA, seguridad de cuentas (políticas, bloqueos,
  restablecimientos, dispositivos de confianza), ajustes y credenciales, usuarios y roles, usuarios del portal
  (alta, contraseña puesta por un gestor —nunca su valor—, archivar, restaurar y eliminar), «entrar como», RGPD,
  retención, bloqueos legales, BPM (diseño, versiones, publicación, instancias y cada paso), Mi cuaderno (altas,
  compartidos, exportaciones, papelera y acceso excepcional, nunca el texto), MCP (conexiones, escrituras,
  aprobaciones y lecturas de notas), Del ticket al PR, restablecimiento del admin desde el `.env`
  (`reset_to_admin_only.py --solo-admin`) y configuración movida a Configuración, entre otros. No es un *hook*
  global: cada sitio lo declara.
- **Encadenado y firmado.** Cada fila lleva `seq`, `prev_hash` y `entry_hash` (cadena HMAC por empresa,
  `app/db/cadena_auditoria.py`). La exportación se firma con Ed25519.
- **Solo añadir.** Triggers en PostgreSQL y SQLite (`app/db/auditoria_inmutable.py`, migración 199) niegan el
  `UPDATE` y el `DELETE` de `audit_logs`. Excepciones: `user_id` puede pasar a NULL al borrar un usuario (no entra
  en la huella), una fila antigua sin `seq` se puede encadenar una vez, y la purga de una empresa tras su
  cuarentena abre un permiso de purga dentro de la misma transacción.
- **Sin retención.** El registro no tiene tipo de retención: se conserva mientras exista la empresa (RGPD art.
  17.3.b y e) y la supresión RGPD no lo reescribe.

Dónde se consulta:

- **GRC → Registro de auditoría** y **Empresa: SSO, webhooks y OAuth → Auditoría** (`/settings/enterprise`).
- API: `GET /api/v1/enterprise/audit-log`, `…/audit-log/chain/verify` (verifica la cadena),
  `…/audit-log/chain/export` (exportación firmada, hasta `AUDIT_EXPORT_MAX_ROWS`, 100 000 filas) y
  `…/audit-log/chain/public-key` (clave pública para verificar la firma).
- Cambios de ajustes y credenciales: `GET /api/v1/settings/audit-log`.

### 15.2 Retención y bloqueo legal

**Políticas de retención** (`app/services/retencion.py`), en **GRC → Retención**:

- Una política por empresa y tipo de registro: cuántos días se guarda. Nace apagada.
- La **vista previa** dice cuántos registros borraría hoy y cuántos salva un bloqueo, antes de activarla.
- Ninguna política puede bajar de `RETENTION_MIN_DAYS` (30).
- Tipos: los 48 de `TIPOS` en `app/db/bloqueo_legal.py` (medido el 23-11-2026):
  - Trabajo y clientes: `tickets` (cerrados), `documents` (archivados), `client_contacts` (desactivados),
    `overtime_requests` (cerradas), `demand_requests` (cerrados), `public_form_submissions`, `meetings`,
    `bpmn_instances` (BPM), `pir_reviews`.
  - IA y comunicación: `ai_conversations`, `ai_usage_logs`, `ai_voice_commands`, `ai_client_chats`,
    `ai_action_logs`, `notifications`, `email_logs`, `collaboration_audit_events`, `sd_voice_sessions`, `sd_kb_gaps`.
  - Integraciones: `connector_calls`, `webhook_deliveries`, `jira_sync_logs`, `ticket_pr_runs` (Del ticket al PR).
  - Personas: `absence_documents`, `expense_attachments`, `activity_events`, `internal_satisfaction`,
    `internal_client_roles`, `internal_charges`.
  - Seguridad de cuentas: `user_sessions`, `security_events`, `security_detections`, `login_anomalies`,
    `document_access_logs`, `password_history`, `trusted_devices`, `security_change_requests`,
    `access_review_campaigns`.
  - Mi cuaderno: `notebooks`, `notebook_pages`, `notebook_attachments`.
  - Proveedores y CMDB: `supplier_documents`, `supplier_access_grants`, `sw_config_snapshots`, `sw_findings`,
    `sw_risk_snapshots`, `sw_exploit_events`, `sw_risk_alert_log`.
- **No se retienen**, a propósito: el registro de auditoría y los datos financieros que la ley obliga a conservar.
- La tarea diaria `aplicar-retencion` (02:55) aplica las políticas activas y deja en la auditoría lo borrado por
  tipo. «Aplicar ahora» lo hace a mano.

**Bloqueo legal.** Lo que coincide con un bloqueo activo (un tipo o todos, más campo = valor; por ejemplo, el
cliente de un litigio) **no se borra ni por retención ni a mano**: un `before_flush` lo impide y el borrado manual
devuelve 409. Se crean y se levantan en la misma pestaña; quedan auditados.

**Otras purgas del worker** (ver [`docs/WORKER_TASKS.md`](docs/WORKER_TASKS.md)): `purgar-empresas-caducadas`,
`purgar-registro-de-conectores` (`CONECTOR_LOG_RETENTION_DAYS`, 30), `purgar-cache-de-traducciones`
(`TRANSLATION_CACHE_RETENTION_DAYS`, 180) y `reuniones-retencion` (audio y transcripciones, respeta el bloqueo
legal). El chat de colaboración tiene su propia retención en **Administración del chat** (`/settings/chat-admin`).

### 15.3 RGPD

**Solicitudes de los interesados.** En **Empresa: SSO, webhooks y OAuth → RGPD** (`/settings/enterprise?tab=gdpr`,
capacidad `cab.administrar`):

| Tipo | Artículo | Qué hace al procesarla |
|---|---|---|
| Acceso | 15 | Copia de sus datos (con imputaciones y tickets), descargable en JSON |
| Rectificación | 16 | Deja constancia |
| Supresión | 17 | Ejecuta la supresión (abajo) |
| Portabilidad | 20 | La misma copia, descargable |

- La solicitud exige persona o correo, y la persona tiene que ser de la empresa.
- Plazo: `COMPLIANCE_GDPR_MAX_DAYS` (30). El informe de cumplimiento cuenta las vencidas.
- Se puede rechazar con motivo.
- La copia se guarda cifrada `COMPLIANCE_GDPR_EXPORT_TTL_DAYS` (30) tras completarse; después la borra el barrido
  diario.

**Supresión** (`app/services/supresion_service.py`, un solo procedimiento):

1. La ficha del usuario se seudonimiza (HMAC con `SECRET_KEY`), se vacían sus datos de contacto, se desactiva y
   pierde la contraseña. Su `id` se queda: horas, gastos y facturas siguen cuadrando sin nadie identificable.
2. En las tablas de sus empresas, se borran las copias exactas de su correo (cualquier columna de texto) y de su
   nombre o usuario (solo columnas de identidad).
3. Se borran sus credenciales: sesiones, MFA, passkeys, tokens, claves de API, suscripciones push, historial de
   contraseñas y dispositivos de confianza.
4. Se borra del almacén analítico (`dim_user`); si no se puede, el informe lo dice.

Con un bloqueo legal activo sobre la persona, la supresión se rechaza (409) antes de tocar nada. El registro de
auditoría queda fuera a propósito.

**Otros puntos RGPD:**

- **Reuniones:** copia y supresión de una persona en el asistente de reuniones
  (`/meeting-assistant/gdpr/person`, auditadas).
- **BI:** consentimientos, máscaras de campos y solicitudes propias en Gobierno del dato (`/bi/gdpr/*`). Hay, por
  tanto, dos registros de solicitudes (el de Empresa y el de BI); el informe de cumplimiento cuenta los dos.
- **Portal de clientes:** no se ha encontrado una vía de autoservicio para que un cliente pida sus datos; las
  solicitudes se registran desde la pestaña RGPD. «Eliminar» un usuario del portal no es la supresión RGPD: sin
  historial lo borra y con historial lo archiva (conserva el historial); la supresión es una acción aparte para
  administradores ([29.2](#292-dar-acceso-a-un-cliente)).
- **BPM:** la copia y la supresión incluyen las variables de las instancias marcadas como dato personal.
- **Mi cuaderno:** la copia y la supresión incluyen los cuadernos; el acceso excepcional exige un bloqueo legal o
  una solicitud RGPD en curso, y queda auditado con el motivo ([19.4](#194-privacidad-baja-y-acceso-excepcional)).
- **MCP y Del ticket al PR:** de los argumentos y logs se guardan ids, estados y cifras, no texto libre; el log
  del contenedor de Del ticket al PR oculta los datos personales ([39](#39-mcp-agentes-de-código-externos),
  [40](#40-del-ticket-al-pr)).
- **Copias antes de migrar y copias locales** (`backups/`, también las de `setup backup`): contienen datos
  personales y quedan fuera de la supresión hasta que se borran. Bórralas cuando la versión nueva esté validada (ver [§10](#10-copias-de-seguridad-y-restauración)).

### 15.4 Informe de cumplimiento

**GRC → Informe de cumplimiento** (`GET /api/v1/grc/compliance-report`, firmado y exportable). Mide el sistema, no
declara: cobertura MFA (`COMPLIANCE_MFA_MIN_COVERAGE_PCT`, 100 %), fuerza de la política de contraseñas
(`COMPLIANCE_MIN_PASSWORD_LENGTH`, 12), contraseñas caducadas, cuentas bloqueadas, cuentas sin acceso en
`COMPLIANCE_STALE_ACCOUNT_DAYS` (90), cuentas privilegiadas y su MFA, límites de sesión, restricciones de acceso,
recertificación reciente, uso del bypass de superadmin, inmutabilidad del registro de auditoría, solicitudes RGPD
y estado de la cadena.

**GRC → Marcos y evidencias** (`/api/v1/governance/compliance/*`): controles de ISO 27001:2022 y SOC 2, evidencias
por control (con huella SHA-256 del fichero) y estado de cada control. Un control que el informe mide en
«atención» no pasa por tener evidencias.

**GRC → Explicar acceso** (`GET /api/v1/grc/access-explainer`): dado un usuario, un método y una ruta, dice si puede
y qué capa lo decide.

### 15.5 Recertificación de accesos

1. El administrador abre una campaña en **Seguridad de cuentas** (`seguridad.administrar`).
2. Por cada usuario activo se crea un elemento con la foto de su acceso (rol, rol personalizado, capacidades, MFA,
   último acceso), asignado a su responsable (`manager_id`; si no tiene, a quien abre la campaña).
3. El responsable lo revisa en **Configuración → Seguridad y GRC → Recertificación de accesos**
   (`/settings/recertificacion`) y decide «mantener», «revocar» o «modificar» con un comentario obligatorio, que es
   la evidencia.
4. Al cerrar la campaña, los «revocar» desactivan la cuenta si el administrador lo pide.
5. Se exporta en CSV o JSON.

El informe de cumplimiento marca la recertificación como vencida si la última campaña cerrada tiene más de
`ACCESS_REVIEW_INTERVAL_DAYS` (90) días.

### 15.6 Segregación de funciones

Matriz de permisos, reglas SoD, violaciones y flujos de mitigación en `/settings/grc`; ver [§8.7](#87-segregación-de-funciones). En BPM, además, `BPMN_SEGREGACION_DE_FUNCIONES` (por empresa) impide que quien diseña o publica una versión apruebe en sus instancias ([34](#34-bpm-procesos)).

### 15.7 Actividad y gobierno de IA

- **Gobierno de IA por módulo** (`/settings/ai-governance`): qué módulos de IA están activos en la empresa, su uso y
  la auditoría de llamadas (`/governance/config`, `/governance/stats`, `/governance/logs`).
- **Políticas de datos personales para IA** (`/ai-governance/*`): detección y bloqueo de PII en las peticiones y
  respuestas, con su registro.
- **Registro de acciones de IA** (`ai_action_logs`): lo que ejecutan el asistente, el agente y el MCP, con su tipo de
  retención.

Detalle en [§38](#38-inteligencia-artificial).

### 15.8 Privilegios mínimos

- Cada sección de Configuración pide la capacidad que coincide con la guarda del backend: quien no puede guardar
  no ve el formulario.
- Ocultar una pestaña del menú no quita permisos; cerrar un módulo en un rol personalizado sí (403).
- Las credenciales de plataforma de la CMDB (`CMDB_DISCOVERY_ALLOW_PLATFORM_CREDENTIALS`) son opción del operador,
  no del administrador de empresa.
- El worker solo ejecuta una lista blanca de funciones en segundo plano.
- Las credenciales delegadas no gestionan credenciales ([§8.4](#84-claves-de-api-y-tokens-de-desarrollador)).
- Las métricas no llevan datos personales (etiqueta `empresa` = slug o id).

---

## 16. Desarrollo

### 16.1 Backend por capas

`endpoints (app/api/v1/endpoints) → servicios (app/services) → modelos (app/models)`, con esquemas Pydantic en `app/schemas` y lo transversal en `app/core` y `app/db`. Reglas comprobadas por tests de arquitectura (`tests/test_auditoria_2026_11_arquitectura_c1.py`…`c4.py`, `tests/test_sin_commits_en_la_api.py`, `tests/test_auditoria_2026_11_capas_y_stripe.py`):

- Los servicios no conocen HTTP: lanzan `ErrorDeDominio` (`app/core/errores.py`) y devuelven datos; la API monta la respuesta.
- La API no hace `commit()`: solo los servicios.
- `app/services`, `app/core` y `app/db` no importan `app.main`, `app.api` ni `app.worker`; las tareas se encolan por nombre (`app/core/segundo_plano.py`).
- Los modelos no importan servicios; sin ciclos de import ni `except Exception` silenciosos.
- Un solo emisor de correo (`notification_service`).
- Las tareas de Celery son envoltorios finos que declaran su contexto de empresa (por organización, por sujeto, por fila o global) en `app/worker.py`.
- Los routers se agrupan en `app/api/v1/routers/` (`core`, `delivery`, `ai_domain`, `platform`, `framework` y los de autenticación).

### 16.2 Frontend

- React + TypeScript + Vite en `frontend/src`: rutas en `App.tsx`, páginas en `pages/`, cliente de API en `services/api/`, permisos de rutas y menú en `permisos/navegacion.tsx`.
- Kit de componentes en `components/ui` (`Modal`, `Drawer`, `DataTable`, `Pagination`, `DateInput`, `Input`, `Select`…): úsalo en vez de crear equivalentes. Reglas: `frontend/src/components/ui/DESIGN_SYSTEM.md` y `docs/GUIA_DE_DISENO.md`.
- Sin `confirm`/`alert` nativos, sin `fetch` fuera de `services/api`, sin colores hex (tokens CSS), `style` solo con propiedades personalizadas. ESLint lo vigila.
- **i18n obligatorio en es, en y zh** (`frontend/src/i18n/langs/es.mjs`, `en.mjs`, `zh.mjs`): todo texto visible va por clave con `t()`. Los gates de `ci_local.sh` impiden bajar la cobertura, añadir literales fuera de `t()`, claves sin definir, duplicadas o variables `{x}` incoherentes entre idiomas.
- Las pantallas preguntan por **capacidades** (`usePermiso('x')`), no por roles ([42](#42-roles-y-capacidades)).

### 16.3 Convenciones

- **Errores con código traducible**: en la API, `error_http(status, codigo, **params)` de `app/core/codigos_de_error.py`; en servicios, `ErrorDeDominio(..., code=...)`. La respuesta lleva `detail`, `code` y `params` y la interfaz pinta el texto en el idioma del usuario. `scripts/errores_sin_codigo.py` cuenta los que aún salen sin código.
- **Textos por clave** en frontend; nada de literales visibles.
- **Configuración solo desde `Settings`**: no leas `os.environ` fuera de `app/core/config.py` y sus grupos (`tests/test_auditoria_2026_11_config_2.py` mantiene la lista blanca de excepciones).
- Sesiones fuera de una petición (scripts, tareas): declara el contexto con `declarar_sistema(db, "motivo")` o `fijar_contexto(db, org, "motivo")`; sin contexto fallan (`TENANT_SESION_SIN_CONTEXTO=cerrar`).
- Llamadas salientes a URLs configurables con `abrir()` o `cliente_httpx()` de `app/core/outbound_url.py`.
- Cada cambio: auditoría, RGPD, retención y privilegios revisados ([15](#15-grc-auditoría-retención-rgpd-y-cumplimiento)).

### 16.4 Añadir un endpoint, un servicio, una migración, un ajuste o una capacidad

1. **Servicio**: función en `app/services/<dominio>` que recibe la sesión, valida, lanza `ErrorDeDominio` con código y hace `commit()`.
2. **Endpoint**: en `app/api/v1/endpoints/`, registrado en su router de `app/api/v1/routers/`; protege con la capacidad correspondiente; errores con `error_http`; sin lógica de negocio ni `commit()`.
3. **Modelo y migración**: modelo en `app/models/` (y en `app/models/__init__`), migración nueva numerada siguiendo `alembic/NAMING_CONVENTION.md` y colgando de la cabeza actual. Comprueba que hay una sola cabeza (`python -m alembic heads`). Nunca `create_all` en arranque ni despliegue.
4. **Ajuste**: variable en `Settings` (`app/core/config.py` o un mixin de `app/core/config_groups/`), con defecto y descripción; si es editable en caliente, entrada en `app/services/settings_service/_catalogo.py`. Añádelo a `.env.example` o a una familia declarada fuera (`tests/test_env_example_sincronizado.py`) y a `docs/REFERENCIA_DE_AJUSTES.md`.
5. **Capacidad**: en `app/core/capacidades.py`, con sus roles base y una `sonda` (una llamada real de esa pantalla); `tests/test_capacidades.py` comprueba que quien la tiene no recibe 403.
6. **Pantalla**: ruta en `App.tsx`, entrada de menú en `permisos/navegacion.tsx`, textos en es/en/zh.
7. **Tarea programada**: función en `app/worker.py` con su forma de contexto y entrada en `beat_schedule`; documéntala en `docs/WORKER_TASKS.md`.

### 16.5 Pruebas

| Qué | Cómo |
|---|---|
| Backend (pytest) | `python -m pytest tests/ -n auto --tb=short` (`make test`); un módulo: `make test-module M=test_okrs`; marcadores `slow`, `smoke`, `auth`, `crud`, `integration` |
| Paridad del esquema | `tests/test_alembic_schema_parity.py` (PostgreSQL con `PARITY_POSTGRES_URL` o `scripts/paridad_postgres.py`) |
| Extremo a extremo | `tests_e2e/` (Playwright, con su `pytest.ini`); `scripts/run-ui-tests-linux-mac.sh` / `run-ui-tests-windows.bat` |
| Frontend | `cd frontend && npm test` (Vitest), `npm run typecheck`, `npm run lint`, `npm run check:i18n` |
| Todo junto | `./scripts/ci_local.sh` (gates bloqueantes e informativos: ruff, pip-audit, pytest, tsc, vitest, build, eslint, npm audit, i18n…), `--fast` sin pytest ni cobertura, `--info` solo informativos; `make audit` |

El proyecto no usa CI/CD remoto: los gates se pasan en local con `scripts/ci_local.sh` antes de publicar.

---

# Parte B — Uso de la aplicación

---

## 17. Primeros pasos: entrar, navegar, menú e idiomas

Esta sección es para cualquier persona que use la aplicación de gestión (la de los operadores). El portal de clientes tiene su propia entrada y sus propios idiomas: ver [29. Portal de clientes](#29-portal-de-clientes).

En este manual se usan los nombres de los roles base: administración (`admin`), PM (`pm`), jefe de equipo (`team_lead`), RR. HH. (`hr`), empleado (`employee`) y externo (`subcontractor`). Lo que abre cada uno está en [42. Roles y capacidades](#42-roles-y-capacidades).

### 17.1 Iniciar sesión

**Qué es.** La pantalla de entrada (`/login`). Admite usuario y contraseña, verificación en dos pasos (MFA), passkey y, si la empresa lo tiene configurado, inicio de sesión único (SSO).

**Para quién.** Todas las personas con cuenta de operador.

**Cómo se usa.**

1. Escribe tu **Usuario o correo electrónico** y la contraseña, y pulsa el botón **Acceder a …** (lleva el nombre de la aplicación).
2. Si la empresa tiene SSO, verás botones **Continuar con …** (uno por proveedor) encima de «o con credenciales». Con SSO la contraseña la gestiona tu proveedor, no la aplicación.
3. Si tienes passkey, puedes usar **Entrar con passkey** en lugar de la contraseña.
4. Si tu cuenta pide un segundo paso, introduce el código de 6 dígitos del autenticador (o uno de tus códigos de respaldo, de 8 caracteres) y pulsa **Verificar código**. Puedes marcar **Recordar este dispositivo**. Desde ese paso también se puede **Usar mi passkey**.
5. Tras entrar, la aplicación te lleva a tu página de inicio:
   - **Panel de proyectos** (`/projects-dashboard`) si puedes ver la salud del portfolio (administración, PM, jefe de equipo);
   - si no, **Panel de equipo** (`/team-dashboard`) si gestionas personas (RR. HH.);
   - si no, **Mi panel de trabajo** («Mi día», `/work-dashboard`).

**Olvidé la contraseña.** Pulsa **¿Olvidaste tu contraseña?**, escribe tu correo o usuario y pulsa **Enviar enlace**. Si la cuenta existe, llega un correo con un enlace que abre `/reset-password`. La respuesta es la misma exista o no la cuenta, para no revelar quién tiene acceso.

**Consejos.**

- Activa MFA desde tu perfil: **Perfil › Seguridad › Activar MFA** (lleva a Configuración › «Mi verificación en dos pasos», `/settings/mfa`). Las passkeys se gestionan en la misma pestaña.
- Las reglas de contraseña, bloqueo y caducidad de sesión las fija la empresa: [docs/seguridad/politicas_de_cuenta.md](docs/seguridad/politicas_de_cuenta.md).

### 17.2 Elegir la empresa activa

La forma de elegir empresa depende de cómo esté instalada la aplicación (ajuste de instalación `TENANT_ENTRY_MODE`, ver [7. Multiempresa y aislamiento de datos](#7-multiempresa-y-aislamiento-de-datos)):

| Modo | Qué ve la persona |
|---|---|
| `email_selector` (por defecto) | Correo y contraseña. Si perteneces a varias empresas, la entrada pregunta «¿En cuál quieres entrar?». Después puedes cambiar desde el **selector de empresa** de la barra superior. |
| `subdomain` | La dirección web decide la empresa. No hay selector. |
| `org_field` | La pantalla de entrada pide el código de la **Empresa**. No hay selector. |

El selector de la barra superior solo aparece en el modo `email_selector` y si perteneces a dos o más empresas activas. Cambiar de empresa abre una sesión nueva y recarga la página: no queda nada de la empresa anterior en pantalla.

### 17.3 La pantalla: barra superior y menú lateral

**Barra superior** (de izquierda a derecha):

| Elemento | Para qué |
|---|---|
| Miga de pan | Dónde estás: categoría › pantalla › detalle (en una ficha de proyecto, su nombre). |
| **Buscar...** (`Ctrl+K`, `⌘K` en Mac) | Búsqueda global (ver 17.5). |
| **+** («Crear nuevo») | Alta rápida: tarea, horas, ticket, factura, cliente, contrato, riesgo, gasto, proyecto. Solo salen las opciones que tu rol puede abrir. |
| **Nexus** | Asistente de IA en un panel lateral (`Ctrl+I`). Ver [38. Inteligencia artificial](#38-inteligencia-artificial). |
| Micrófono | Comando de voz: imputar, crear ticket o tarea, consultar. |
| Chat | Panel flotante del chat, con contador de no leídos. Ver [37](#37-colaboración-chat-llamadas-y-reuniones). |
| Campana | Avisos sin leer (ver 17.6). |
| Calendario | Abre `/calendar` (si tu rol lo abre). |
| Cuaderno | Notas rápidas de «Mi cuaderno» desde cualquier pantalla (ver [19](#19-mi-cuaderno)). |
| Cronómetro | Solo si tienes uno en marcha: tiempo transcurrido, proyecto y tarea; lleva a `/timer`. |
| Bandeja | Solo si hay pendientes: suma de alertas y aprobaciones; lleva a `/inbox`. |
| Selector de empresa | Ver 17.2. |
| Tu nombre | Abre tu perfil (ver 17.7). El icono de al lado cierra la sesión. |

Solo hay un panel de la barra abierto a la vez: abrir uno (búsqueda, IA, chat, perfil…) cierra el anterior.

**Menú lateral.** Agrupa las pantallas en categorías:

| Categoría | Panel al que lleva su nombre |
|---|---|
| Mi trabajo | Mi panel de trabajo (`/work-dashboard`) |
| Proyectos y planificación | Panel de proyectos (`/projects-dashboard`) |
| Equipo y personas | Panel de equipo (`/team-dashboard`) |
| Clientes y finanzas | Resumen financiero (`/finance-dashboard`) |
| Soporte e ITSM | Estado del soporte (`/support-dashboard`) |
| Analítica y BI | Executive Dashboard (`/executive`) |
| IA y Automatización | (sin panel: el nombre despliega la lista) |
| Configuración | Configuración (`/settings`) |

- Pulsar el nombre o el icono de una categoría abre su panel; la flecha despliega o pliega sus pestañas. Si tu rol no abre el panel, el nombre solo despliega.
- Solo se abre una categoría a la vez (acordeón).
- Arriba del menú, **Espacio de trabajo** filtra las categorías: Todo, Trabajo, Proyectos, Equipo, Finanzas, Soporte, Analítica, IA, Config. Se recuerda en ese navegador.
- Cada persona solo ve las pantallas que su rol permite. La misma regla protege la ruta: pedir por URL una pantalla no permitida lleva a `/403`.
- `Ctrl+B` (`⌘B` en Mac) pliega o despliega el menú. Por debajo de 1280 px se pliega solo; por debajo de 1024 px se abre con el botón de menú o deslizando el dedo a la derecha.
- Toda la configuración está en una sola entrada, **Configuración** (`/settings/<sección>`), con buscador propio. Mapa completo en [41. Configuración: mapa de secciones](#41-configuración-mapa-de-secciones).

### 17.4 Menú personalizable

**Qué es.** Cada persona puede ordenar las categorías del menú, ordenar las pestañas de cada categoría y ocultar las que no usa. El administrador fija el menú de partida de cada rol.

**Para quién.** Personalizar el propio menú: cualquiera con sesión. Menú por defecto de los roles: administración (capacidad `org.administrar`).

**Cómo se usa (tu menú).**

1. Pulsa **Personalizar menú** al pie del menú lateral, o **Perfil › Apariencia › Menú lateral › Personalizar menú**.
2. Reordena las categorías arrastrándolas o con los botones subir y bajar.
3. Abre una categoría para ver sus pestañas: la casilla oculta o muestra cada una, y subir/bajar cambia su orden (las pestañas no se arrastran, a propósito: así funciona igual con teclado y en pantallas táctiles).
4. Los cambios se guardan al momento en el servidor y te siguen en cualquier equipo. Pulsa **Hecho** para salir.
5. **Restablecer** borra tu menú y vuelves al de tu rol. El pie indica si usas «tu propio menú» o «el menú de tu rol».

**Cómo se usa (menú por defecto de un rol).**

1. Ve a **Configuración › Personas y jornada › Menú por defecto** (`/settings/menu-por-defecto`).
2. Elige el rol, ordena y oculta como arriba, y pulsa **Guardar**.
3. **Volver al de fábrica** quita el menú propio del rol.

Cada cambio queda en la auditoría (antes y después, IP y navegador).

**Consejos.**

- Ocultar no quita permisos: lo oculto se sigue abriendo por URL, desde la miga de pan y con la búsqueda `Ctrl+K`. Y ocultar nunca da acceso a nada que tu rol no tenga.
- Las pantallas nuevas que lleguen con una actualización salen al final y visibles.
- Si ocultas todas las pestañas de una categoría, la categoría desaparece; se recupera desde **Personalizar menú**.

**Más detalle.** [docs/CONFIGURACION.md](docs/CONFIGURACION.md) (apartado «Menú lateral personalizable»).

### 17.5 Búsqueda global y atajos de teclado

**Búsqueda global.** `Ctrl+K` (`⌘K` en Mac) o el cuadro **Buscar...** de la barra superior.

- Busca proyectos, tareas, tickets, personas, facturas, oportunidades y páginas de tu cuaderno (solo las tuyas o las compartidas contigo).
- Sin texto, muestra accesos rápidos (nueva tarea, imputar horas, nuevo ticket, proyectos, cronómetro, calendario, gastos, configuración), filtrados por lo que tu rol puede abrir.
- Flechas arriba/abajo para moverte, `Intro` para abrir, `Esc` para cerrar. Con dos o más letras, `Intro` sin elegir resultado abre la página completa de búsqueda (`/search`, «Buscar»).

**Atajos de teclado** (pulsa `?` fuera de un campo de texto para verlos en pantalla):

| Atajo | Qué hace |
|---|---|
| `Ctrl+K` / `⌘K` | Búsqueda global |
| `Ctrl+I` / `⌘I` | Asistente de IA (Nexus) |
| `Ctrl+B` / `⌘B` | Mostrar u ocultar el menú lateral |
| `?` | Ver los atajos |
| `Esc` | Cerrar la ventana o el panel abierto |
| `G` y luego `T` | Ir a Tareas (`/tasks`) |
| `G` y luego `P` | Ir a Proyectos (`/projects`) |
| `G` y luego `I` | Ir a Imputar horas (`/imputar`) |
| `G` y luego `S` | Ir a Service Desk (`/service-desk`) |

Los atajos `G` + letra funcionan fuera de los campos de texto, sin `Ctrl`/`Alt`, con la segunda tecla en menos de 1,5 s, y solo llevan a páginas que tu rol puede abrir; la ventana de atajos solo muestra esas (`components/layout/atajosDeTeclado.ts`; hasta el 23-11-2026 se anunciaban y no hacían nada). Algunas pantallas tienen atajos propios: en el tablero de **Tareas**, `/` lleva al buscador; en el **Planificador visual**, `Esc` cancela y `Supr` borra la reserva elegida.

**Teclado y accesibilidad.** `Tab` recorre la pantalla y un contorno del color de acento marca dónde estás. En una fila de pestañas, las flechas cambian de pestaña e `Inicio`/`Fin` van a la primera y la última. Al principio de cada página hay un enlace oculto **Ir al contenido**. Con el menú plegado, las flechas entran en el desplegable de cada categoría y `Esc` vuelve al icono.

### 17.6 Campana de avisos y bandeja

- La **campana** cuenta los avisos sin leer (y, para administración, PM y RR. HH., las alertas sin leer). Al abrirla muestra los últimos 8, con **Marcar todas** y **Ver todas** (lleva a **Bandeja de entrada › Notificaciones**).
- Se actualiza en tiempo real; si la conexión en vivo no está disponible, consulta cada poco.
- Qué avisos recibes y por qué canal (aplicación o correo) se elige en **Perfil › Avisos**, con la opción de recibir cada día un resumen por correo de los avisos sin leer.
- La bandeja completa se describe en [18.2](#182-bandeja-de-entrada).

### 17.7 Perfil de usuario

Se abre pulsando tu nombre en la barra superior. Tiene cinco pestañas:

| Pestaña | Qué contiene |
|---|---|
| **Perfil** | Correo, nombre, apellidos, cargo, teléfono y URL del avatar. **Guardar perfil**. |
| **Apariencia** | Tema, color de acento, densidad y menú lateral (ver 17.8). **Guardar apariencia**. |
| **Idioma** | Idioma de la interfaz (ver 17.9). **Guardar idioma**. |
| **Seguridad** | Último acceso, estado de MFA, cambio de contraseña (no con SSO), MFA y passkeys. |
| **Avisos** | Cada tipo de aviso por aplicación y por correo, y resumen diario. |

La nueva contraseña debe tener al menos 8 caracteres y coincidir en los dos campos; la empresa puede exigir más (ver [8. Seguridad](#8-seguridad)).

### 17.8 Apariencia y accesibilidad

En **Perfil › Apariencia**:

- **Tema de color:** Freight Pro (el principal), Oscuro clásico, Midnight, Slate, Claro, **Alto contraste** o **Sistema** (sigue al sistema operativo). Se aplica al pulsarlo.
- **Color de acento:** el del tema («Acento del tema»), uno de los predefinidos o uno a medida.
- **Densidad:** Compacta, Normal o Confortable.
- Pulsa **Guardar apariencia** para que se conserve en el servidor; si no, se pierde al recargar.

La guía de diseño, con el contraste medido de cada tema, está en [docs/GUIA_DE_DISENO.md](docs/GUIA_DE_DISENO.md).

### 17.9 Idiomas

**Idiomas de la aplicación de gestión:** español, inglés y chino (`es`, `en`, `zh`). Son los únicos que se ofrecen a los operadores, completos y mantenidos.

**Idiomas del portal de clientes:** ocho (español, inglés, francés, alemán, portugués, italiano, polaco y chino). Ver [29. Portal de clientes](#29-portal-de-clientes).

**Cómo se cambia el idioma.**

1. **Perfil › Idioma**, elige el idioma y pulsa **Guardar idioma**.
2. Se guarda en el servidor (te sigue en otros equipos) y en el navegador. La navegación cambia al instante; el contenido de las páginas se traduce según se carga.

**Qué idioma se usa si no has elegido ninguno.** El último usado en ese navegador; si no hay, el del navegador si es uno de los tres; si no, inglés. El idioma por defecto de la empresa se fija en **Configuración › Empresa y marca › General**.

**Idioma de correos, PDF y textos generados.** Lo que genera el servidor (correos, respuestas de la IA, documentos) sale en este orden de preferencia: el idioma explícito del destinatario (por ejemplo, el del cliente o del ticket), tu preferencia, el idioma de la empresa, el idioma por defecto de la instalación y, en último lugar, español.

**Fechas.** Siguen el idioma de la interfaz: `02/11/2026` en español, `11/02/2026` en inglés, `2026/11/02` en chino.

**Para administración.**

- **Configuración › IA e idiomas › Idiomas**: idiomas activos del operador y del portal, y textos de la interfaz personalizados por la empresa (se aplican a todos sus usuarios).
- **Configuración › IA e idiomas › Traducción**: traducción automática de mensajes entre personas que escriben en idiomas distintos (tickets, chat, base de conocimiento). Ver [docs/SERVICE_DESK.md](docs/SERVICE_DESK.md).

### 17.10 Exportar a Excel

En las pantallas con una lista (tareas, proyectos, facturas, aprobaciones, tickets…) la cabecera tiene el botón **Exportar Excel** («Exportar la lista a Excel»). Descarga en formato `.xls` lo que se ve en ese momento, con los filtros aplicados. Si la lista está vacía, el fichero trae solo las cabeceras. Los paneles, el Gantt, los tableros y los formularios no tienen este botón.

Para exportaciones de datos completas (no solo lo visible) está **Exportación de datos** (`/exports`), ver [33. BI y analítica](#33-bi-y-analítica).

---

## 18. Mi trabajo y Mi día

La categoría **Mi trabajo** del menú reúne lo del día a día de cada persona: Mi panel de trabajo, Bandeja de entrada, Tareas, Tiempo, Asistente de reuniones, Mi cuaderno, Ausencias, Horas extra, Documentos, Gastos, Aprobaciones y Mis equipos y licencias (más los portales de proveedor y de departamento para quien los tiene). Esta sección cubre el panel, la bandeja, las tareas, el calendario y los documentos. El resto:

| Pantalla | Dónde se explica |
|---|---|
| Tiempo (`/time`) | [21. Imputaciones y partes de horas](#21-imputaciones-y-partes-de-horas) |
| Ausencias (`/absences`), Horas extra (`/overtime`) | [22. Ausencias](#22-ausencias), [21.5](#215-horas-extra-y-trabajo-fuera-de-horario) |
| Mi cuaderno (`/notebook`) | [19. Mi cuaderno](#19-mi-cuaderno) |
| Asistente de reuniones (`/meetings-ai`) | [37.3](#373-asistente-de-reuniones) |
| Gastos (`/expenses`) | [32. Finanzas](#32-finanzas-facturación-gastos-rentabilidad-y-presupuestos) |
| Aprobaciones (`/approvals`) | [36. Aprobaciones](#36-aprobaciones) |
| Mis equipos y licencias (`/my-equipment`) | [26. Licencias y activos (ALM)](#26-licencias-y-activos-alm) |

### 18.1 Mi día (Mi panel de trabajo)

**Qué es.** El resumen personal del día (`/work-dashboard`): tareas abiertas y vencidas, horas de la semana y del mes, aprobaciones que esperan tu decisión, gastos y ausencias pendientes. Solo lectura.

**Para quién.** Cualquiera con sesión. Es la página de inicio de empleados y externos.

**Cómo se usa.**

1. Revisa las tarjetas: **tareas abiertas**, **tareas vencidas**, **horas esta semana**, **horas este mes**, **aprobaciones** que te esperan y **gastos pendientes**. Cada tarjeta lleva a la lista filtrada (por ejemplo, tus tareas abiertas en `/tasks`).
2. Los dos indicadores muestran tus horas de la semana frente a tu objetivo (tu capacidad semanal; 40 h si no tienes) y el porcentaje de tareas terminadas.
3. Debajo: resumen de actividad, tendencia mensual de horas y el bloque **Pendiente en mis notas** (casillas abiertas de tu cuaderno).
4. Accesos rápidos: **Imputar horas** (`/imputar`), **Nueva tarea** (`/tasks`), **Nuevo ticket** (`/service-desk`) y **Cronómetro** (`/time`).

**Consejos.** El acceso **Cronómetro** abre `/time` en la pestaña **Registrar**; para ir directo al cronómetro usa `/timer` o el cronómetro de la barra superior.

### 18.2 Bandeja de entrada

**Qué es.** Un único sitio para lo que te llega (`/inbox`). La pestaña activa queda en la URL (`/inbox?tab=…`).

**Para quién.** Cualquiera con sesión.

| Pestaña | Contenido |
|---|---|
| **Notificaciones** | Avisos de la aplicación y alertas del sistema. Marcar uno o todos como leídos. |
| **Menciones** | Donde te han mencionado con `@`. Marcar como leídas. |
| **Aprobaciones** | Lo que espera tu decisión (lo mismo que `/approvals`, ver [36](#36-aprobaciones)). |
| **Procesos** | Tus tareas de procesos BPM (si tienes la bandeja de procesos, ver [34](#34-bpm-procesos)). |
| **Mi cuaderno** | Casillas pendientes y etiquetas de tus notas (ver [19](#19-mi-cuaderno)). |

Los contadores de las pestañas usan la misma fuente que la campana, así que no discrepan. Las rutas antiguas `/notifications` y `/mentions` llevan a su pestaña.

### 18.3 Tareas

**Qué es.** La lista y el tablero de tareas de todos tus proyectos (`/tasks`), con filtros, edición en bloque, detalle, comentarios, documentos, campos personalizados y ayudas de IA.

**Para quién.** Cualquiera con sesión ve sus tareas. Editar: administración, PM, jefe de equipo y empleado. Crear: administración, PM y jefe de equipo. Borrar y configurar el tablero (carriles, límites WIP): administración y PM.

**Vistas** (selector de la cabecera; la elegida queda en la URL, `?view=`):

| Vista | Para qué |
|---|---|
| **Kanban** (por defecto) | Columnas por estado; arrastrar una tarjeta cambia su estado. Carriles por persona o prioridad, límite WIP por columna, alta rápida por columna y filtro por sprint (con proyecto elegido). Las tareas canceladas no salen en el tablero. |
| **Lista** | Tabla con selección múltiple y edición en bloque (estado, persona, prioridad). |
| **Tabla** | Tabla editable en línea (título, estado, persona, prioridad, horas, avance, fechas); columnas a elegir. |
| **Línea temporal** | Barras por fechas, con la ruta crítica y la línea base. |
| **Calendario** | Las tareas en un mes. |
| **Carga por persona** | Horas asignadas frente al horario de cada persona (con proyecto elegido). |

Las vistas de tabla, línea temporal, calendario y carga se pueden **guardar** con sus filtros; las guardadas pueden ser personales o compartidas (compartir es de administración y PM).

**Cómo se usa.**

1. Filtra por proyecto, estado, prioridad, persona, texto, «mías» o «vencidas». Los filtros van a la URL: puedes guardar el enlace.
2. **Nueva tarea**: título, proyecto, persona, prioridad (crítica, alta, media, baja), fechas, horas estimadas, etiquetas y descripción (con editor de IA).
3. Abre una tarea para editarla. Pestañas del detalle: detalle, comentarios, documentos e **Historial** (movimientos entre columnas). Los estados disponibles son los del flujo del proyecto. **Sugerir persona** y **Estimar esfuerzo** usan la IA.
4. **Auto-planificar** (administración y PM) propone fechas a las tareas sin planificar y las aplica si aceptas.

**Estados y transiciones permitidas.**

| Desde | Puede pasar a |
|---|---|
| Backlog | Por hacer, Cancelada |
| Por hacer | En curso, Hecha, Backlog, Cancelada |
| En curso | En revisión, Por hacer, Hecha, Bloqueada, Cancelada |
| En revisión | Hecha, En curso, Cancelada |
| Bloqueada | En curso, Por hacer, Cancelada |
| Hecha | En curso (reabrir) |
| Cancelada | (estado final) |

**Consejos.**

- Lista y tablero muestran las mismas tareas, hasta 500; si hay más, un aviso dice cuántas se ven («Se muestran N de M»). Filtra por proyecto para trabajar con listas grandes.
- En la edición en bloque, las tareas cuyo salto de estado no está permitido se saltan y el aviso las cuenta.
- `/` lleva al buscador del tablero.
- Los flujos de estados, tipos y campos de cada proyecto se configuran en **Configuración › Proyectos y trabajo** (`/settings/project-workflows`, `/settings/custom-fields`).

### 18.4 Calendario

**Qué es.** Vista mensual de solo lectura (`/calendar`) con vencimientos de tareas, hitos de proyecto, inicio y fin de sprints y ausencias. Se abre desde el icono de calendario de la barra superior.

**Para quién.** Personal interno (capacidad `colaboracion.ver`).

**Cómo se usa.** Cambia de mes con las flechas y filtra por tipo (todo, tarea, hito, sprint, ausencia). No se crean ni editan eventos desde aquí.

**Consejos.** Carga como mucho 100 tareas por mes y los 20 sprints más recientes de la empresa. El calendario del chat (Google Calendar o Microsoft 365) es otro: ver [37](#37-colaboración-chat-llamadas-y-reuniones).

### 18.5 Documentos

**Qué es.** El repositorio de documentos (`/documents`): categorías, etiquetas, versiones, permisos por documento, aprobación opcional, resumen con IA y reserva para editar.

**Para quién.** Personal interno (`colaboracion.ver`). Lo que puedes hacer con cada documento depende de tu permiso en él: lector, editor o administrador.

**Cómo se usa.**

1. **Subir**: título, descripción, categoría (contrato, entregable, propuesta, procedimiento, requisitos, acta de reunión, legal, otro), etiquetas, proyecto opcional y «requiere aprobación».
2. Abre un documento: **Vista previa** (eliges versión), **Versiones** (subir una nueva) y **Metadatos**.
3. **Permisos**: da a una persona acceso de lector, editor o administrador.
4. **Aprobación**: si el documento la requiere y hay un flujo para su categoría, la solicitud se abre sola al subirlo; si no, **Enviar a aprobación** (editor). Tras un rechazo se puede reenviar.
5. **Reservar** bloquea el documento para ti: nadie más puede subir versión, editar sus datos ni archivarlo hasta que lo **Liberes** o caduque la reserva (24 h por defecto, `DOCUMENT_CHECKOUT_HOURS`). Quien administra el documento puede **Forzar liberación**.
6. **Resumen con IA**: solo con texto extraíble (PDF con texto, `.txt`, `.md`) y un proveedor de IA configurado.
7. **Borrar** archiva el documento (no se pierde).

**Consejos.** Los justificantes de ausencias no aparecen aquí: viven en la propia ausencia, con su acceso restringido (ver [22](#22-ausencias)).

---

## 19. Mi cuaderno

**Qué es.** Un cuaderno de notas tipo OneNote dentro de la aplicación (`/notebook`): cuadernos, secciones de colores, páginas y subpáginas, con texto rico, casillas de tarea, etiquetas, enlaces vivos a tareas y tickets, dibujo, voz, IA opcional y edición compartida. **Privado por defecto.**

**Para quién.** Toda persona con sesión de operador, internos y externos (capacidad `cuaderno.usar`). No es para los usuarios del portal de clientes. Configurarlo: administración (`cuaderno.config`).

### 19.1 Dónde está

- Página completa: **Mi trabajo › Mi cuaderno** (`/notebook`), con el árbol a la izquierda y el editor a la derecha.
- **Panel rápido**: icono de cuaderno de la barra superior. Notas rápidas y páginas recientes desde cualquier pantalla.
- Casillas y etiquetas pendientes: pestaña **Tareas y etiquetas** del cuaderno, pestaña **Mi cuaderno** de la bandeja y bloque **Pendiente en mis notas** de Mi día.

### 19.2 Cómo se usa

1. Crea un **cuaderno**, dentro **secciones** (pestañas de color) y en ellas **páginas**. Una página puede tener subpáginas.
2. Ordena arrastrando, o con el menú de cada elemento: Subir, Bajar, Convertir en subpágina, Sacar de la subpágina, Mover a otro cuaderno.
3. Escribe: títulos, listas, tablas, resaltado, enlaces, **casillas de tarea** (con fecha y aviso opcionales) y **etiquetas** (Pendiente, Importante, Pregunta, Idea, Llamar a…, Crítico, y las tuyas propias).
4. Se **guarda solo** a los 1,2 s de dejar de escribir. El indicador dice «Guardado · hora», «Guardando…», «Sin conexión: guardado en este equipo» o «No se pudo guardar».
5. **Enlaces vivos**: `#` busca tareas, tickets, proyectos y clientes; `@` busca personas. El enlace muestra el estado actual. Quien no tenga permiso para ver el objeto ve «Sin acceso».
6. **De nota a acción**: selecciona texto (o pon el cursor en una casilla) y pulsa el rayo. Puedes crear una tarea, un ticket, una solicitud de demanda, una idea de cartera o un recordatorio de calendario. El objeto creado enlaza a la nota y la nota al objeto. Solo salen las opciones que tu rol permite.
7. **Plantillas**: cuatro de fábrica (acta de reunión, seguimiento de cliente, 1:1, lluvia de ideas) y las que añada la empresa.
8. **Adjuntos, imágenes y dibujo** a mano alzada o con lápiz.
9. **Voz**: graba y transcribe (si la empresa lo permite). El audio no se guarda salvo que lo pidas.
10. **IA** (si la empresa la activa): resumir, extraer tareas y ordenar ideas. Solo se envía el texto de esa página y tú decides si insertas la respuesta.
11. **Desde una reunión**: en el detalle de una reunión, **Enviar a mi cuaderno** crea una página con asistentes, resumen, decisiones, preguntas y acciones como casillas.
12. **Exportar** una página, sección o cuaderno a Markdown o PDF.
13. **Papelera**: borrar manda a la papelera; desde ahí se restaura o se borra del todo. Se vacía sola pasados los días que fije la empresa (salvo bloqueo legal).

### 19.3 Compartir

- Solo el dueño comparte. Se comparte un **cuaderno entero o una sección** con una persona, un equipo o un departamento, en **lectura** o **edición**. Las notas rápidas no se comparten.
- La persona recibe un aviso. Varios pueden editar la misma página a la vez.
- Configuración decide con qué tipos de destinatario se puede compartir. No se puede compartir con otra empresa.
- El dueño puede compartir un cuaderno, en lectura, con **sus propios agentes de código** (MCP), si la empresa lo permite: ver [39. MCP](#39-mcp-agentes-de-código-externos).

| | Dueño | Compartido en edición | Compartido en lectura | Cualquier otro |
|---|---|---|---|---|
| Ver y buscar | sí | sí | sí | no |
| Escribir, adjuntar, dibujar, voz, nota→acción | sí | sí | no | no |
| Compartir, renombrar o borrar el cuaderno | sí | no | no | no |
| Exportar | sí | sí | sí | no |
| Papelera | sí | no | no | no |

### 19.4 Privacidad, baja y acceso excepcional

- **Nadie más** ve un cuaderno: ni la dirección, ni el superadministrador. Lo que no puedes ver responde como si no existiera.
- **Sin conexión**: el navegador guarda las últimas páginas abiertas y los cambios pendientes, en una base propia de cada persona y empresa. Si al volver la red la página cambió, lo escrito sin red se guarda como página nueva «(copia sin conexión)»: no se pierde nada.
- **Baja de una persona** (política en **Configuración › Personas y jornada › Mi cuaderno**, `/settings/cuaderno`): `transfer` (por defecto, pasan a su responsable con la marca «transferido de»), `trash` (a la papelera) o `keep` (se conservan). Lo compartido con ella se quita siempre.
- **Acceso excepcional** (administración, `cuaderno.acceso_excepcional`): descargar los cuadernos de una persona solo con un bloqueo legal activo que la identifique o una solicitud RGPD suya en curso, más una justificación. Queda auditado con el motivo.
- La auditoría registra altas, compartidos, exportaciones, papelera y accesos, **nunca** el texto de las notas. Copia y supresión RGPD incluyen los cuadernos. Ver [15. GRC](#15-grc-auditoría-retención-rgpd-y-cumplimiento).

**Configuración** (administración): etiquetas por defecto, plantillas, política de baja, días de papelera, IA, voz y con quién se puede compartir, en `/settings/cuaderno`.

**Más detalle.** [docs/CUADERNO.md](docs/CUADERNO.md).

---

## 20. Proyectos y planificación

La categoría **Proyectos y planificación** del menú reúne la cartera, los proyectos y todo lo que se planifica y controla en ellos. Algunas pantallas de análisis (valor ganado, cartera, burnup) están en **Analítica y BI**. Esta sección las agrupa por lo que se hace con ellas.

**Para quién**, en general:

| Capacidad | Roles | Qué abre |
|---|---|---|
| `proyectos.ver` | todos | Proyectos (`/projects`, cada uno los suyos) |
| `proyectos.trabajo` | personal interno | Sprints, RACI, Registro de cambios, UAT, Gantt, Gantt de épicas, Épicas, Dependencias, Lecciones aprendidas |
| `proyectos.panel` | administración, PM, jefe de equipo | Panel de proyectos (salud del portfolio) |
| `proyectos.gobierno` | administración, PM | Riesgos, Control de cambios, Entregables, Integración Git, Firma electrónica |
| `analitica.ver` | administración, PM | EVM — Valor ganado, Cartera de proyectos, Burnup y velocidad, Flujo acumulado, Riesgo del proyecto |
| `cartera.usar` / `cartera.gestionar` | interno / administración, PM | Proponer / decidir en Propuestas de cartera |
| `ia.ver` | administración, PM | IA de planificación de sprint |

Abrir una pantalla no siempre permite escribir en ella: crear y editar proyectos, épicas, dependencias o mover barras del Gantt es de administración y PM; sprints, RACI, UAT y registro de cambios, de los responsables (administración, PM, jefe de equipo, RR. HH.).

### 20.1 Cartera: de la idea al proyecto

**Panel de proyectos** («Salud del portfolio», `/projects-dashboard`). KPIs de la cartera: total y activos, críticos y en riesgo, riesgos abiertos, tareas vencidas, % a tiempo, consumo de presupuesto, proyectos por tipo y estado, y la lista de críticos. Solo lectura.

**Propuestas de cartera** (`/portfolio/intake`): entrada de ideas a la cartera con puntuación y fases (stage-gate).

1. Cualquier interno **propone** una iniciativa (también desde una nota del cuaderno).
2. Se **puntúa** con los criterios ponderados de la empresa.
3. Pasa por **fases**; cada fase la decide el motor de aprobaciones con su flujo (o administración/PM en pantalla si no hay flujo). Hace falta la puntuación mínima de la fase (o `PORTFOLIO_MIN_SCORE_TO_ADVANCE`).
4. Aprobada, se **convierte en proyecto** (con su plantilla si la tiene). La pantalla compara las horas pedidas por rol con las libres del equipo.

Criterios y fases: **Configuración › Proyectos y trabajo › Entrada a la cartera** (`/settings/cartera`).

**Cartera de proyectos** (`/portfolio`, en Analítica y BI): la vista de análisis de la cartera.

**Demanda** (`/demand`): el flujo de demanda configurable tiene su propia sección, [31. Flujo de demanda](#31-flujo-de-demanda).

### 20.2 Proyectos y ficha de proyecto

**Lista de proyectos** (`/projects`). Vistas: Tarjetas (por defecto), Lista (columnas ordenables), Gantt (de la cartera o de un proyecto) y Plantillas. Filtros por texto y estado.

**Crear un proyecto** (administración y PM): nombre, código, tipo, cliente, PM, fechas, presupuesto, tipo de facturación (la cuota recurrente pide día de facturación de 1 a 28) y departamento. Al elegir cliente o tipo aparecen las **lecciones aprendidas** que aplican.

**Ficha de proyecto** (`/projects/:id`): es el centro del proyecto. Pestañas:

| Pestaña | Qué contiene |
|---|---|
| Resumen | Datos del proyecto, editables en línea |
| Tareas | Las vistas de trabajo de [18.3](#183-tareas), fijas en el proyecto |
| Gantt | El Gantt del proyecto con sus paneles (ver 20.3) |
| Sprints | Los sprints del proyecto |
| Presupuesto y finanzas | Solo quien gestiona el proyecto |
| Valor ganado | KPIs y curva S (solo gestión) |
| Hitos y facturación | Hitos facturables (solo gestión) |
| Equipo | Miembros, rol y dedicación |
| Riesgos | Registro de riesgos |
| RACI, UAT | Las pantallas globales, fijas en el proyecto |
| IA | Salud y riesgo de retraso, simulación, estimación de horas, persona sugerida |
| Documentos | Documentos del proyecto |
| Lecciones | Lecciones que aplican y las propias |
| Recursos técnicos | Licencias y equipos del proyecto |

**Plantillas.** **Guardar como plantilla** en la ficha crea una plantilla desde el proyecto (fases, tareas con rol y duración, dependencias, riesgos, entregables). Al aplicarla, el proyecto nuevo sale ya planificado. Se gestionan en **Configuración › Proyectos y trabajo › Plantillas de proyecto** (`/settings/project-templates`) y en la vista Plantillas de `/projects`.

**Estados de proyecto:** planificación, activo, en espera, pausado, completado, cerrado, cancelado, archivado. Un proyecto completado, cerrado, cancelado o archivado no admite horas nuevas.

### 20.3 Planificar: Gantt, dependencias, épicas, sprints

**Gantt** (`/gantt`). Elige un proyecto (o todos; se cargan hasta 300 tareas).

1. Arrastra una barra para cambiar fechas; `Mayús`+arrastrar de una barra a otra crea una dependencia fin-inicio (administración y PM).
2. Con un proyecto elegido, debajo del gráfico:
   - **Camino crítico**: fechas tempranas y tardías, holgura total y libre, restricciones y **Replanificar**.
   - **Dependencias**: fin-inicio, inicio-inicio, fin-fin e inicio-fin, con desfase, más vínculos informativos.
   - **Líneas base**: congelar el plan, elegir la vigente y comparar con hoy o entre dos.
   - **Nivelación** (administración y PM): propone retrasar tareas no críticas dentro de su holgura para no sobrecargar a nadie; nunca alarga el proyecto.
3. **Auto-planificar** propone fechas con IA.

El calendario de cada persona sale de su horario efectivo (turnos, jornadas, festivos y ausencias, ver [22.3](#223-turnos-jornadas-y-horario-efectivo)). Días laborables de la empresa, holguras y recálculo automático: **Configuración**, grupo de proyectos (`PLANNING_WORKDAYS`, `PLANNING_CRITICAL_FLOAT_DAYS`, `PLANNING_AUTO_RECALCULATE`).

**Dependencias** (`/dependencies`): crear y borrar dependencias entre tareas de un proyecto con tipo y desfase; marca las tareas bloqueadas. Una dependencia que cerraría un ciclo se rechaza.

**Épicas** (`/epics`, «Épicas»): épicas por proyecto (título, color, prioridad, fechas, estado), vista de roadmap y ficha con el avance y sus tareas.
**Gantt de épicas** (`/epic-gantt`): el roadmap como línea temporal, con dependencias entre épicas (FS, SS, FF o «relacionada», con desfase).

**Sprints** (`/sprints`):

1. Elige proyecto y crea un sprint (nombre, objetivo, fechas).
2. Añade tareas del backlog.
3. **Iniciar** (solo uno activo por proyecto; guarda los puntos planificados).
4. **Cerrar**: cuenta los puntos hechos, calcula la velocidad y devuelve al backlog lo no terminado.
5. Anota la **retrospectiva**.

**IA de planificación de sprint** (`/sprint-planning`): propone el contenido de un sprint con las tareas «por hacer» del proyecto y una capacidad en puntos (prioridad primero, tareas pequeñas antes). Aceptar el plan añade sus tareas al sprint elegido.

**Burnup y velocidad** (`/sprint-charts`) y **Flujo acumulado** (`/cumulative-flow`), en Analítica y BI, muestran la evolución de los sprints y del flujo.

### 20.4 Ejecutar: hitos, entregables, RACI, UAT, registro de cambios, wiki, Git

- **Entregables** (`/deliverables`): entregables formales por proyecto (o vista de todos), con fecha, responsable, contacto del cliente y criterios de aceptación. Estados: planificado, en curso, en revisión, entregado, aceptado, rechazado. **Aceptar** y **Rechazar** solo sobre uno entregado.
- **Hitos y facturación**: pestaña de la ficha de proyecto y `/milestone-billing` (ver [32](#32-finanzas-facturación-gastos-rentabilidad-y-presupuestos)).
- **Matriz RACI** (`/raci`): por proyecto, elemento (entregable, hito, fase o libre) × persona × papel (R, A, C, I). Es documental: no da permisos ni dispara avisos.
- **UAT — Aceptación de usuario** (`/uat`): casos de prueba por proyecto (pasos, resultado esperado, prioridad, tarea, persona) y su ejecución (pendiente, superado, fallido, bloqueado, omitido). **Exportar para el cliente** genera el informe.
- **Registro de cambios** (`/changelog`): notas de versión por proyecto, a mano o **Generar** desde las tareas terminadas en un periodo.
- **Wiki** (`/wiki`): espacios y páginas por bloques, versiones (restaurables), etiquetas, búsqueda y edición simultánea. Leer y buscar: personal interno; crear y editar espacios y páginas: administración y PM.
- **Integración Git** (`/git`): pull/merge requests y despliegues que llegan de GitHub y GitLab por webhook. Un PR se enlaza a la tarea cuyo código (`PROY-123`) lleva en la rama o el título; al fusionarse, la tarea pasa a hecha si su estado lo permite. Webhooks y secreto: **Configuración › Integraciones › Git** (`/settings/git`). El flujo completo de ticket a PR está en [40. Del ticket al PR](#40-del-ticket-al-pr).
- **Firma electrónica** (`/esign`): ver [9. Integraciones](#9-integraciones-y-pruebas-de-conexión).

### 20.5 Controlar: riesgos, cambios, valor ganado, lecciones

- **Riesgos** (`/risks`): registro por proyecto y vista de cartera. Probabilidad (muy baja a muy alta) × impacto (despreciable a crítico) dan la puntuación y el nivel. Respuesta, plan de mitigación y contingencia, responsable, fecha de revisión, coste e impacto en plazo. Estados: identificado, en análisis, mitigando, en seguimiento, cerrado, materializado. **Riesgo del proyecto** (`/risk-scores`, Analítica y BI) da la puntuación por proyecto.
- **Control de cambios** (`/changes`): peticiones de cambio de alcance, coste o plazo. Borrador → **Enviar** → revisión (aprobada o rechazada) → **Implementar**. Pestaña de pendientes (administración y PM) y pestaña **CAB y ventanas**: los miembros votan y administración cierra (una decisión contra la mayoría o con empate pide motivo, que queda en la auditoría). Los impactos son informativos: aprobar no cambia presupuesto ni fechas.
- **EVM — Valor ganado** (`/evm` y pestaña de la ficha): presupuesto a la conclusión de la línea base vigente (o del presupuesto), valor planificado, valor ganado por el avance real de cada tarea, índices y curva S diaria (`EVM_SNAPSHOTS_ENABLED`).
- **Lecciones aprendidas** (`/lessons`):
  1. **Pendientes de capturar**: proyectos, problemas, incidentes graves y sprints cerrados sin lección. **Capturar lección** abre el formulario con los hechos medidos y, si está activa, una propuesta de la IA.
  2. Un validador la **valida** o la **archiva**.
  3. Las lecciones validadas se recomiendan donde se actúa (al crear un proyecto, en su pestaña Lecciones y en el ticket) con el motivo.
  4. Cada recomendación se valora: **Útil**, **Aplicada**, **No aplica**; la pestaña de indicadores lo mide.
  5. **Acciones de mejora** con responsable y fecha.
- **PIR del proyecto** (pestaña *PIR* de la ficha): la revisión posterior a la implantación (PMBOK). Se programa
  sola al completar el hito marcado como **puesta en marcha** (go-live) y/o al cerrar el proyecto, si es obligatoria
  para su tipo (por defecto, opcional). Compara los beneficios conseguidos con los previstos (los del caso de
  negocio), recoge la satisfacción de los interesados y crea acciones (tareas) y lecciones. Ver
  [24.8](#248-cambios-rfc-cab-y-cambios-estándar) y [docs/PIR.md](docs/PIR.md).

### 20.6 Recursos del proyecto

La planificación de personas (capacidad, previsión, planificador visual, nivelación entre proyectos) se explica en [23. Personas y recursos](#23-personas-y-recursos). Lo que mira un proyecto: la pestaña Equipo de la ficha, la vista **Carga por persona** de Tareas y la
**Nivelación** del Gantt.

**Consejos.**

- Trabaja desde la ficha del proyecto: Gantt, sprints, RACI y UAT ya vienen filtrados.
- Congela una línea base antes de replanificar; así el valor ganado y la línea temporal comparan contra lo acordado.
- Ajustes del grupo de proyectos (holguras, nivelación, valor ganado, cartera): lista completa en [docs/REFERENCIA_DE_AJUSTES.md](docs/REFERENCIA_DE_AJUSTES.md).

---

## 21. Imputaciones y partes de horas

**Qué es.** El registro de horas trabajadas por proyecto y tarea, el cronómetro y el parte semanal que se envía a aprobar. Pantalla **Tiempo** (`/time`) con tres pestañas.

**Para quién.** Imputar y enviar el parte: cualquiera con sesión. Ver y aprobar los partes del equipo: responsables (administración, PM, RR. HH.; la revisión la puede hacer también un jefe de equipo).

| Pestaña | También en | Para qué |
|---|---|---|
| **Registrar** | `/imputar` | Imputar, editar y borrar horas |
| **Cronómetro** | `/timer` | Medir el tiempo y crear la imputación al parar |
| **Semana** | `/timesheets` | Parte semanal: enviar, y aprobar o rechazar (responsables) |

La pestaña elegida no queda en la URL: para enlazar directamente usa `/timer` o `/timesheets`.

### 21.1 Imputar horas

1. Abre **Tiempo › Registrar** (o **Imputar horas** en Mi día, o **+ › horas** en la barra).
2. Elige proyecto, tarea, fecha y horas, y guarda.
3. La rejilla de la semana muestra lo imputado; cada entrada se puede editar o borrar.

**Reglas que aplica el servidor.**

- Solo se imputa en proyectos donde eres PM, miembro o persona asignada a la tarea.
- Como mucho 24 h por día.
- No en proyectos completados, cerrados, cancelados o archivados.
- No en fechas anteriores al **bloqueo de periodo**: los días que fija `DEFAULT_IMPUTATION_LOCKOUT_DAYS` (14 por defecto, por empresa).
- Hace falta una tarifa o perfil de coste vigente (salvo externos): sin ella el aviso es «sin tarifa horaria». La pone RR. HH. en **Configuración › Finanzas › Estructura de coste** (ver [23](#23-personas-y-recursos)).
- Una entrada aprobada, o de un parte enviado o aprobado, solo la cambia administración.

Cada hora guarda su coste del día (tarifa × horas, en la moneda de la empresa): cambios de salario posteriores no recalculan lo ya imputado.

### 21.2 Cronómetro

**Iniciar**, **Pausar**, **Reanudar**, **Parar** (crea la imputación) o **Cancelar** (no la crea). Mientras corre, la barra superior muestra el tiempo, el proyecto y la tarea en cualquier pantalla.

### 21.3 Parte semanal y aprobación

1. En **Semana**, revisa la semana y pulsa enviar. Una semana vacía no se envía.
2. El responsable la ve en sus pendientes y la **aprueba** o **rechaza**.
3. Un parte rechazado se corrige y se reenvía.

Estados: borrador → enviado → aprobado o rechazado; rechazado → enviado. Aprobar marca como aprobadas las horas de esa semana.

**Recordatorio.** Cada día, a la hora local de la empresa (`NOTIFICATIONS_MISSING_IMPUTATIONS_TIME`, 18:00 por defecto), se avisa a quien no ha imputado y tenía trabajo ese día según su horario.

### 21.4 Horas desde tickets

Las horas que un agente registra en un ticket del Service Desk que pertenece a un proyecto pasan a su parte si está activo el ajuste `SD_TIME_TO_TIMESHEET`. Ver [24. Service Desk](#24-service-desk).

### 21.5 Horas extra y trabajo fuera de horario

**Qué es.** Peticiones de horas extra con reglas y aprobación (`/overtime`, «Horas extra», en Mi trabajo). El módulo está **activo por defecto** con control «avisar» al imputar.

**Para quién.** Pedir: cualquiera con sesión. Pedir para el equipo, gestión y resumen: responsables (`horas_extra.gestionar`). Configurar y liquidar: administración y RR. HH. (`horas_extra.config`).

**Cómo se usa.**

1. **Pedir horas extra**: antes de hacerlas (petición previa) o después (declaración). Fecha, franja u horas, motivo, proyecto y ticket opcionales, sustituto y tipo de día (laborable, fuera de franja, festivo, no laborable, guardia). La vista previa dice qué reglas aplican.
2. Elige la compensación entre las que permita la empresa: pago, bolsa de horas o ninguna.
3. Se aprueba con el flujo configurado; sin flujo, decide su responsable, RR. HH. o administración. Quien aprueba puede autorizar menos horas de las pedidas. Nadie decide lo suyo.
4. Pestañas: **Mis horas extra**, **Por aprobar** y, para responsables, **Gestión** y **Resumen** (frente a umbrales y presupuestos).

**Control al imputar** (si imputas más que tu horario sin autorización): `ninguno`, `avisar` (aviso a ti y a tu responsable), `regularizar` (crea una declaración pendiente) o `bloquear` (no deja guardar).

Configuración: **Configuración › Personas y jornada › Horas extra** (`/settings/horas-extra`). Los límites (por ejemplo, máximo anual, diario, descanso entre jornadas) son reglas del motor de políticas; **Cargar ejemplos** crea borradores con el máximo legal español de 80 h/año pagadas.

**Consejos.** Las horas extra con compensación en bolsa alimentan la bolsa de horas de [22.2](#222-saldos-y-bolsa-de-horas).

---

## 22. Ausencias

**Qué es.** Vacaciones, permisos y bajas gobernados por reglas (`/absences`, «Ausencias»): tipos configurables, por días, medios días u horas, saldos y bolsa de horas, turnos y cupos con lista de espera, aprobación por niveles y documentos (por ejemplo, el parte de baja).

**Para quién.**

| Qué | Quién |
|---|---|
| Pedir y ver las propias | Cualquiera con sesión |
| Decidir (**Por decidir**) | Responsables: administración, PM, jefe de equipo, RR. HH. (y quien tenga un paso en el flujo, desde [Aprobaciones](#36-aprobaciones)) |
| Cuadrante y cobertura | Administración y RR. HH. (`ausencias.config`) |
| Configurar tipos, turnos, jornadas, festivos | Administración y RR. HH., en Configuración |

Pestañas de `/absences`: **Mis ausencias**, **Calendario y cobertura**, **Por decidir** y, para quien planifica, **Cuadrante** y **Cobertura**.

### 22.1 Pedir una ausencia

1. Pulsa **Pedir ausencia**.
2. Elige el tipo, las fechas y el modo que el tipo permita: **días**, **medios días** u **horas** (por horas, una franja de inicio y fin válida para cada día del rango). Añade turno, sustituto, motivo y los documentos que tengas.
3. La columna de la derecha es una **vista previa en vivo**: días u horas que cuentan con su turno, saldo antes y después, plazas libres por día y turno (y tu puesto en la lista de espera), aprobaciones necesarias, documentos que se pedirán con su plazo, cobertura y avisos o bloqueos.
4. Pulsa **Pedir** (o **Pedir y entrar en lista de espera** si no hay plaza).

**Qué puede pasar.**

- Un bloqueo de una regla, falta de sustituto obligatorio, ningún día laborable, saldo negativo o solape con otra ausencia: error y no se guarda.
- Sin plaza en el cupo: queda **en lista de espera** (o rechazada, si la regla bloquea). Al liberarse una plaza, la primera petición que cabe entera sube sola.
- Con plaza: **pendiente** y se abre la aprobación. Si el tipo no requiere aprobación, queda aprobada al momento.

**Seguimiento.** En **Mis ausencias**: estado (pendiente, aprobada, rechazada, cancelada, en espera con puesto), línea de tiempo, documentos con versiones, lo que falta entregar y su plazo.
**Editar** mientras está pendiente o en espera; **Cancelar** hasta que se rechace (una aprobada que ya empezó no se cancela).

### 22.2 Saldos y bolsa de horas

- Cada tipo descuenta de las **vacaciones**, de un **cupo propio** o de la **bolsa de horas**, en días u horas, por periodo (año, semestre, trimestre, mes o ninguno), con **arrastre** limitado, **caducidad** y **prorrateo** por fecha de alta. Se consume primero lo que caduca antes.
- Un día de vacaciones vale las horas del turno de **esa persona** ese día, no 8 fijas.
- La **bolsa de horas** se alimenta del exceso imputado sobre el horario (con factores por tipo de día, umbral y topes). Se recalcula cada día (`HOUR_BANK_RECALC_DAYS`) o con **Recalcular**.
- RR. HH. ajusta cualquier saldo con un motivo (queda auditado).

### 22.3 Turnos, jornadas y horario efectivo

El **horario efectivo** de cada persona y día es la única fuente para ausencias, capacidad, planificador y recordatorios. Se decide así, de mayor a menor prioridad:

1. un cambio puntual de ese día en el cuadrante (turno o libre);
2. su rotación de turnos;
3. la **jornada** que tenga asignada (por día de la semana, con tramos y pausa; asignable a la empresa, una sede, un departamento, un equipo, un grupo o la persona; permanente, entre fechas o cada año, como la jornada de verano);
4. la jornada de la empresa (`PLANNING_WORKDAYS`, `DEFAULT_WORKDAY_START` y sus horas semanales).

De ahí se quitan los festivos de la empresa y de **su sede** (salvo turnos que trabajan festivos), los días fuera de contrato de un externo y sus ausencias. Un turno puede ser partido y cruzar la medianoche. **La semana laboral es configurable**: no se supone de lunes a viernes.

### 22.4 Decidir

1. **Por decidir** lista las peticiones en las que te toca: con el **porqué** (las reglas que se cumplieron), el impacto en la cobertura por día y turno, quién más falta, el saldo tras la ausencia y las plazas.
2. Aprobar o rechazar es un voto en la solicitud de aprobación (varios niveles, paralelo, delegación y escalado del motor de aprobaciones).
3. Un responsable, RR. HH. o administración puede, desde el detalle: pedir otro documento con plazo, eximir de uno, **ampliar** una ausencia aprobada o **dar plaza** a una en espera.

### 22.5 Configuración y reglas (administración y RR. HH.)

En **Configuración › Personas y jornada › Ausencias** (`/settings/ausencias`):

| Pestaña | Qué se configura |
|---|---|
| Tipos | Nombre en es/en/zh, color, icono, modos (días, medios días, horas), saldo, periodo, arrastre, caducidad, visibilidad (todos, equipo o privada), flujo de aprobación, sustituto, datos de salud y documentos requeridos |
| Documentos | Tipos de documento |
| Turnos | Horario, tramos, días, equipo, sede, personas mínimas, si trabaja festivos |
| Jornadas | Jornadas laborales y a quién se aplican |
| Festivos | Festivos de la empresa y por sede |
| Personas | Ficha laboral, saldos en días y horas, ajustes, recalcular bolsa (RR. HH.) |
| Horario | Rejilla persona × día con el horario efectivo |
| Acceso especial | Quién más puede abrir documentos de categoría especial (salud) |
| Ejemplos | **Cargar ejemplo**: tres turnos, una política en borrador y un flujo inactivo |

Los días de vacaciones de cada persona están en **Configuración › Personas y jornada › Vacaciones**.

**Reglas** (motor de políticas, **Configuración › Aprobaciones y políticas › Políticas y reglas**, `/settings/policies?dominio=ausencias`): periodos bloqueados, antelación mínima, máximo de días seguidos, cobertura mínima, sustituto obligatorio, saldo, documento obligatorio, avisar, lista de espera, **cupo** (máximo N por empresa, equipo, departamento, sede, rol, turno o grupo; la plaza se asigna al pedir o al aprobar), saldo negativo permitido y redondeo de horas. Todo se elige en pantalla y se prueba con el simulador; nada se escribe a mano. Ver [36](#36-aprobaciones).

**Consejos.**

- Un tipo **privado** se ve como «Ausencia» en el calendario del equipo; el motivo y los documentos solo los ven la persona, RR. HH. y el acceso especial.
- Los documentos no frenan la ausencia: si faltan, se recuerdan, se marcan vencidos y se escalan.
- Nada de **Cargar ejemplo** se aplica hasta publicar la política, activar el flujo y elegirlo en el tipo.
- Los justificantes de salud son datos de categoría especial (RGPD art. 9): retención y bloqueo legal en [15. GRC](#15-grc-auditoría-retención-rgpd-y-cumplimiento).

---

## 23. Personas y recursos

La categoría **Equipo y personas** del menú. Las pantallas de capacidad y planificación leen el horario efectivo ([22.3](#223-turnos-jornadas-y-horario-efectivo)): capacidad = horas de su horario − ausencias − festivos.

| Pantalla | Ruta | Quién la abre |
|---|---|---|
| Panel de equipo («Capacidad del equipo») | `/team-dashboard` | responsables (`equipo.ver`) |
| Recursos | `/resources` | administración, PM, RR. HH. (`recursos.ver`) |
| Planificación de recursos | `/resources/planning` | responsables (`equipo.ver`) |
| Capacidad | `/capacity` | `recursos.ver` |
| Previsión de recursos | `/resource-forecast` | administración, PM, jefe de equipo (`recursos.prevision`) |
| Planificador visual | `/resource-scheduler` | `recursos.prevision` |
| Habilidades | `/skills` | personal interno |
| Organigrama | `/org-chart` | `recursos.ver` |
| OKRs | `/okrs` | `recursos.ver` |
| Evaluaciones de desempeño | `/performance-reviews` | `recursos.ver` |
| Formación y certificaciones | `/training` | personal interno |
| Estructura de coste | `/settings/user-costs` | administración y RR. HH. (`costes.config`) |

### 23.1 Ver al equipo

- **Panel de equipo** (`/team-dashboard`): plantilla, OKR, evaluaciones que te tocan, formación, ausentes hoy y ausencias pendientes; utilización de la semana; plantilla por departamento y rol. Solo lectura. Es la página de inicio de RR. HH.
- **Recursos** (`/resources`), cuatro pestañas:
  1. **Equipo**: tarjetas con la carga de la semana. Administración edita datos, departamento, capacidad semanal y tarifa.
  2. **Heatmap**: personas × semanas (4 a 12). **+ Reserva** crea una reserva de persona en un proyecto: firme (cuenta contra la capacidad) o tentativa (solo se muestra).
  3. **SmartMatch**: busca quién encaja por habilidades, rol, horas, fechas y tarifa máxima.
  4. **Burnout Monitor**: riesgo de agotamiento por las horas de las últimas 8 semanas.
- **Organigrama** (`/org-chart`): árbol jerárquico, posiciones y **cadenas de aprobación** (de cada persona hacia arriba por su responsable). Editar responsable, cargo y departamento: administración.

### 23.2 Planificar capacidad

- **Capacidad** (`/capacity`): horas planificadas por persona, proyecto y semana (4 a 26 semanas). Clic en una celda o **Nueva asignación**; se arrastra para mover. El servidor rechaza lo que supera la capacidad de la semana o choca con una ausencia aprobada.
- **Planificación de recursos** (`/resources/planning`): disponibilidad por semana, habilidades del equipo y quién está libre por habilidad, alertas, histórico de utilización y nivelación.
- **Previsión de recursos** (`/resource-forecast`): carga futura por persona y semana (hasta 52) y resumen ejecutivo. Las reservas tentativas se muestran aparte y no ocupan capacidad.
- **Planificador visual** (`/resource-scheduler`): crear y mover reservas con el ratón (8 a 24 semanas). Arrastra en una fila para crear; arrastra una barra para moverla; modo **Asignar**: suelta una persona en un proyecto. Una reserva firme no puede superar la capacidad. Solo con ratón (no táctil).

### 23.3 Habilidades, objetivos y desarrollo

- **Habilidades** (`/skills`): catálogo (administración y RR. HH.), perfil de cada persona (nivel básico a experto, años, certificado, historial), matriz del equipo y búsqueda para staffing. Cada persona puede añadir o mejorar sus propias habilidades.
- **OKRs** (`/okrs`): objetivos por año y periodo (T1–T4, S1, S2, anual), resultados clave medibles y **check-ins**. El avance del objetivo es la media de sus resultados clave.
- **Evaluaciones de desempeño** (`/performance-reviews`): ciclos con cuestionario, evaluaciones individuales y 360° (autoevaluación, pares, responsable, ascendente) con umbral de anonimato, panel por campaña con PDF y **planes de desarrollo**. Los ciclos los gestionan administración y RR. HH.; los recordatorios salen cada día a `NOTIFICATIONS_PERF_REMINDERS_TIME`.
- **Formación y certificaciones** (`/training`): catálogo de cursos, inscripciones y certificaciones con aviso de las caducadas o que caducan en 60 días. Cada persona registra las suyas; administración y RR. HH., las de cualquiera.

### 23.4 Estructura de coste

**Configuración › Finanzas › Estructura de coste** (`/settings/user-costs`; antes `/user-costs`). El coste real por hora de cada persona, con versiones en el tiempo: salario bruto anual, % de coste de empresa, otros costes y horas productivas al año (con valores por país cargables). Es la tarifa con la que se costea cada hora imputada. Sin perfil ni tarifa, la persona no puede imputar (salvo externos).

**Consejos.**

- Las reservas viven en Recursos y en el Planificador visual; las asignaciones de Capacidad son otra cosa y no salen en el heatmap ni en el planificador.
- Alta de externos (proveedor, responsable interno, fin de acceso): **Recursos › Nuevo externo**. Ver [30. Proveedores](#30-proveedores-y-portal-de-proveedores).

---

## 24. Service Desk

**Qué es.** La mesa de servicio de contecflow: incidencias, peticiones de servicio, cambios, problemas, errores
conocidos, incidentes mayores y base de conocimiento, con SLA, OLA y UC, canales de entrada (correo, SMS, Slack,
Teams, WhatsApp, chat del portal, monitorización) y avisos automáticos. El manual detallado, con todas las reglas,
ajustes y límites, es [docs/SERVICE_DESK.md](docs/SERVICE_DESK.md); esta sección es el recorrido de uso.

### 24.1 Roles y navegación

Todo está en el grupo **Soporte e ITSM** del menú lateral.

| Pantalla | Ruta | Capacidad que la abre | Quién la tiene por defecto |
|---|---|---|---|
| Panel de soporte | `/support-dashboard` | `soporte.panel` | Personal interno |
| Service Desk | `/service-desk` | `sd.ver` | Todos; el externo (subcontratista) solo ve sus tickets |
| CMDB | `/cmdb` | `cmdb.ver` | Dirección y PM |
| Licencias y activos | `/alm` | `alm.ver` | Dirección y PM |
| Altas y bajas de equipos | `/alm/altas-y-bajas` | `equipo.ver` | Dirección, PM, jefes de equipo y RRHH |
| Panel del agente | `/agent-dashboard` | `cmdb.gestionar` | Dirección y PM |
| Diseñador de flujos de soporte | `/sd/workflow-designer` | `sd.disenar_flujos` | Dirección y PM |

Otras capacidades del módulo: `sd.completo` (todas las pestañas y aprobaciones; personal interno), `sd.gestionar`
(análisis de cambios, colas, escalados y guardias; responsables), `sd.config` (leer la configuración y escribir
respuestas rápidas; responsables) y `sd.administrar` (canales, SLA, plantillas, agente; dirección). La lista
completa está en [42. Roles y capacidades](#42-roles-y-capacidades).

**Pestañas de Service Desk** (`/service-desk`), en este orden: **Mi cola**, **Todos** (lista o tablero Kanban),
**Mi panel**, **Conversaciones**, **Por aprobar** (solo aparece si tienes algo que aprobar), **Cambios**,
**Incidentes mayores**, **Problemas**, **Errores conocidos**, **Base de conocimiento** y **Herramientas**. El
externo ve solo *Mi cola*, *Todos* y *Por aprobar*.

**La configuración no está en el módulo**: vive en **Configuración → Service desk** (`/settings/sd`), con estas
subpestañas: Catálogo, Políticas SLA, SLA condicionales y OLA, Ciclos de vida, Canales, Grupos, Enrutamiento,
Escalado, Avisos, Correo entrante, Monitorización, Guardias, Página de estado, Plantillas, Respuestas rápidas y
Anuncios. Un responsable sin `sd.administrar` solo ve *Respuestas rápidas*. En el mismo grupo de Configuración
están además *Calendarios de SLA* (`/settings/sla-calendars`), *Agente autónomo*, *Autorresolución*, *Agente de
voz*, *Cambios estándar* y *Software y vulnerabilidades*. Los enlaces antiguos `/service-desk?tab=config`
redirigen allí.

### 24.2 El ticket: tipos, estados, prioridad y asignación

- **Tipos**: incidencia, petición de servicio, cambio, problema y consulta.
- **Estados base**: nuevo, asignado, en curso, pendiente del cliente, pendiente de un tercero, resuelto, cerrado y
  cancelado. Los dos «pendiente» paran el reloj del SLA.
- **Estados propios** (*Configuración → Service desk → Ciclos de vida*): cada tipo de ticket puede tener sus estados
  («Esperando pieza»…) apoyados en un estado base, con estado inicial y, si se quiere, solo los pasos permitidos. El
  SLA, los avisos, el portal y los informes siguen trabajando con el estado base.
- **Prioridad** (P1 crítica a P4 baja): sale de la matriz urgencia × impacto. Cambiar la urgencia o el impacto la
  recalcula, y cualquier cambio de prioridad recalcula los vencimientos del SLA desde la apertura.
- **Asignación**: a una cola (*grupo*) y, dentro de ella, a un agente. Las reglas de *Enrutamiento* asignan cola,
  prioridad o agente al entrar el ticket (solo con reglas y agentes de la empresa del ticket; las franjas horarias
  usan la zona horaria de la empresa).

#### Cómo se usa

1. **Abrir un ticket.** Botón *Nuevo ticket* en la cabecera. El formulario sugiere servicios del catálogo según lo
   que escribes (*Sugerir servicio*, *Rellenar*) y muestra los más pedidos.
2. **Trabajar tu cola.** *Mi cola* muestra lo que tienes asignado y abierto, por prioridad, de 50 en 50. *Todos*
   busca en el servidor (título, número, solicitante…) y se puede ver como lista o como tablero Kanban (el tablero
   carga como mucho 200 tickets vivos y avisa si hay más).
3. **Abrir el detalle.** Al pulsar un ticket se abre el panel lateral con:
   - acciones rápidas: *Empezar*, *Resolver* (pide el texto de resolución, que es lo que recibe el cliente),
     *Escalar*, *Pausar/Reanudar SLA*, *Dividir*, *Volver al estado anterior* (desde un «pendiente») y *Cerrar*
     (desde resuelto);
   - bloque **SLA / OLA / UC** con vencimientos y su estado (*En plazo*, *En riesgo*, *Incumplido*, *En pausa*);
   - comentarios, con la casilla **Nota interna** para escribir algo que solo ven los agentes;
   - *Sugerir respuesta* (borrador con IA y artículos relacionados), *Respuestas rápidas*, registro de tiempo,
     *Seguir* (te apunta como observador), vínculos entre tickets, documentos y tareas de cumplimiento;
   - el bloque **IA del ticket**: riesgo de incumplir el SLA, triaje propuesto (*Aplicar* / *Descartar*), posibles
     duplicados con *Fusionar en…*, propuesta de resolución y asignación inteligente (*Asignar al mejor*).
4. **Resolver y cerrar.** *Resolver* avisa al solicitante con la resolución. Al **cerrar**, el portal le pide la
   valoración (CSAT).

#### Colisión de agentes, notas internas, plantillas y fusión

- **Aviso de colisión**: en el ticket ves en tiempo real quién más lo está mirando o escribiendo.
- **Contexto del cliente**: solicitante, cliente, contrato, tickets abiertos y recientes, satisfacción y, con ALM,
  sus equipos y licencias.
- **Notas internas**: un comentario con *Nota interna* marcado nunca llega al solicitante ni al portal; avisa al
  agente y a los observadores.
- **Plantillas y respuestas rápidas**: las plantillas de ticket se definen en *Configuración → Service desk →
  Plantillas*; las respuestas rápidas, en *Respuestas rápidas* (las puede mantener cualquier responsable).
- **Fusionar**: desde *Posibles duplicados* o la acción de fusión. Solo une tickets de la misma empresa y cliente.
- **Traducción**: los mensajes del cliente se ven en tu idioma con la marca «Traducido automáticamente» y *Ver
  original*; la *Vista previa en el idioma del cliente* enseña lo que recibirá. Se activa en *Configuración →
  Traducción*.

### 24.3 Avisos

Cada cambio de un ticket avisa a quien corresponde, venga de la pantalla, el portal, el correo, un canal, un flujo,
el escalado o la monitorización:

| Momento | Quién recibe aviso |
|---|---|
| Se abre | El solicitante (acuse con el número) y el agente; sin agente, la cola |
| Se asigna / entra en una cola sin agente | El agente nuevo / los miembros de la cola |
| Respuesta pública de un agente | El solicitante, por correo |
| Respuesta del solicitante o nota interna | El agente y los observadores |
| Se resuelve | El solicitante, con el texto de la resolución |
| SLA en riesgo o incumplido, OLA o UC incumplido | El agente (o la cola) y los responsables de la cola |
| P1/P2 nuevo, SLA incumplido o escalado | Además, quien esté de guardia en la cola (también por SMS) |

Nadie recibe aviso de su propio cambio. El asunto lleva siempre el número entre corchetes (`[INC-0042]`): es lo que
hace que la respuesta del cliente vuelva al mismo ticket. Los textos se editan por idioma (español e inglés) en
*Configuración → Service desk → Avisos*, con vista previa; cada aviso se puede apagar o devolver a su texto por
defecto. Cada persona elige además qué avisos quiere en su perfil.

### 24.4 SLA, OLA, UC, calendarios y escalado

- **SLA** (*Políticas SLA*): horas de respuesta y de resolución por prioridad, y cuándo corre el reloj: 24x7, un
  calendario de servicio o un horario propio de la política. Se aplica la política del contrato; si no hay, la del
  cliente; si no, la de por defecto.
- **SLA condicionales** (*SLA condicionales y OLA*): reglas en orden por servicio, tipo, cliente, contrato y
  prioridad; la primera que encaja fija las horas y, si se quiere, el calendario.
- **Calendarios de SLA** (`/settings/sla-calendars`): jornada, zona horaria, días laborables y festivos. Varios
  clientes pueden compartir uno. Los festivos generales de la empresa cuentan en todos sus SLA.
- **En riesgo** quiere decir que se ha consumido el porcentaje de aviso (70 % por defecto) **en horas del
  calendario**. El estado se revisa cada 5 minutos y cada paso avisa una sola vez.
- **OLA**: lo que tarda cada cola con el ticket. Se fija en *Grupos* (campo *OLA (horas)*) o por prioridad. El reloj
  arranca al entrar en la cola y vuelve a empezar al cambiar de cola.
- **UC** (contrato de soporte del proveedor): corre mientras el ticket está *pendiente de un tercero*. El plazo se
  pone en el contrato de **Licencias y activos → Contratos** (*Plazo del proveedor (UC, horas)* y, opcional,
  *Respuesta del proveedor*). En el ticket se elige el contrato y se pulsa *El proveedor ha respondido*.
- **Escalado** (*Escalado*): cada regla dice cuándo (SLA en riesgo o incumplido, horas sin moverse, sin agente,
  reabierto) y qué hacer (avisar al jefe del agente, a los responsables de la cola o a unas personas, mover de cola,
  subir la prioridad). Salta una vez por ticket.

### 24.5 Buzón de entrada y canales

- **Correo entrante** (*Correo entrante*): buzón IMAP o Microsoft 365 (Graph, con permiso de aplicación
  *Mail.ReadWrite*), o una pasarela de correo por webhook. Cada correo abre un ticket; una respuesta con
  `[INC-0042]` se añade como comentario (y reabre un ticket resuelto). Las respuestas automáticas se descartan y los
  adjuntos se guardan en el ticket. La pantalla tiene *Probar conexión*, *Leer ahora* y los últimos correos
  procesados. Un remitente solo actúa como él mismo si su correo pasa SPF/DKIM/DMARC.
- **SMS** (Twilio): un SMS abre o sigue un ticket; la firma de Twilio es obligatoria. También se usa para avisar a la
  guardia.
- **Slack**: comandos (`ticket <asunto>`, `ver`, `comentar`, `asignarme`, `encurso`, `resolver`) y tarjeta con
  botones; un hilo de Slack queda atado al ticket y lo que se escribe en él entra como comentario público.
- **Microsoft Teams**: los mismos comandos que Slack.
- **WhatsApp Business**: cada conversación abre o sigue su ticket; las respuestas del agente salen por WhatsApp
  (fuera de la ventana de 24 h, solo con plantilla aprobada).
- **Chat del portal**: el asistente contesta con la base de conocimiento; *Hablar con una persona* crea el ticket y
  la conversación espera en la pestaña **Conversaciones**, donde el agente la atiende, contesta y cierra.

Las credenciales de cada canal se dan de alta en *Configuración → Integraciones*; el detalle técnico de cada uno
está en [docs/SERVICE_DESK.md](docs/SERVICE_DESK.md) (apartados 4, 16 y «Canales en tiempo real»). Slack, Teams y
WhatsApp solo se han probado con dobles, no contra los servicios reales.

### 24.6 Monitorización, correlación y guardias

- **Alertas → incidencias** (*Monitorización*): cada alerta del sistema de monitorización (Alertmanager o formato
  genérico, con token por empresa) abre una incidencia con la prioridad de su gravedad, enlazada a su CI. Si se
  repite, suma avisos en vez de abrir otra; al recuperarse se anota y, si nadie la tocó, se resuelve sola.
- **Correlación de alertas** (*Herramientas*): agrupa tickets abiertos y busca el CI raíz usando las relaciones de
  la CMDB.
- **Guardias** (*Guardias*): calendarios por cola con turnos (se introducen a mano). Arriba se ve quién está de
  guardia ahora. La guardia recibe los P1/P2 nuevos, los incumplimientos y los escalados.

### 24.7 Catálogo de servicios, aprobaciones y tareas de cumplimiento

1. En *Configuración → Service desk → Catálogo* se crean categorías y servicios. Cada servicio puede pedir
   aprobación: *Un aprobador* o *Flujo de aprobaciones* (bandeja común de Aprobaciones, con niveles y condiciones;
   ver [36. Aprobaciones](#36-aprobaciones)).
2. La petición nace *pendiente de aprobación* y no se puede empezar ni resolver hasta que se decide. El aprobador la
   ve en **Por aprobar**. Quien pidió el servicio nunca decide sobre su propia petición. Rechazar pide motivo y
   cancela el ticket.
3. Al aprobarse nacen las **tareas de cumplimiento**: cada una con su cola, persona, SLA propio y etapa. Las de la
   misma etapa nacen a la vez; las de la siguiente, al terminar la anterior. Al acabar la última, la petición se
   resuelve sola (salvo que alguna tarea se haya cancelado: entonces decide el agente).

### 24.8 Cambios (RFC), CAB y cambios estándar

Pestaña **Cambios** de Service Desk, con las vistas **Lista**, **Calendario**, **Versiones**, **Congelaciones** y
**Panel del CAB**. No confundir con **Control de cambios** (`/changes`), que son los cambios de alcance de un
proyecto (ver [20. Proyectos y planificación](#20-proyectos-y-planificación)).

1. **Crear el cambio** (*Nuevo*): tipo normal, estándar o de emergencia, CIs afectados, fechas, planes.
2. **Analizar** (panel del cambio → *Análisis del cambio*): impacto y radio de impacto en la CMDB (incluido el
   software de los CIs), matriz de riesgo, planes de vuelta atrás, pruebas y comunicaciones (*Generar*), y la
   simulación *¿Y si…?*.
3. **Enviar al CAB.** El CAB son los miembros de la cola configurada como tal (`SD_CAB_GROUP_ID`); en emergencia,
   solo sus responsables. Cada miembro vota en el panel; votar en contra pide motivo. Se aprueba al llegar al quórum
   (mayoría por defecto). El solicitante no vota su propio cambio.
4. **Vías directas** (pestaña *Aprobación*): la aprobación directa de un administrador fuera del CAB y la vía rápida
   de emergencia (responsables, con aprobadores y justificación). Ninguna la puede usar quien pidió el cambio.
5. **Programar**: solo un cambio aprobado, con inicio y fin y fuera de las congelaciones (salvo emergencia). El
   calendario marca los choques (dos cambios a la vez sobre el mismo CI): avisa, no bloquea.
6. **Implantar y cerrar**: el cambio sigue borrador → enviado → aprobado → programado → en curso → implantado →
   revisión → cerrado (con éxito o fallido). Las **versiones** agrupan cambios que salen juntos.

**Cambios estándar.** Un cambio solo es estándar si usa un **modelo preaprobado** del catálogo (*Configuración →
Service desk → Cambios estándar*, `/settings/sd-cambios-estandar`, capacidad `sd.gestionar`):

- El modelo lleva procedimiento, vuelta atrás, prueba, riesgo máximo y alcance (CIs, tipos de CI, servicios).
- Lo aprueba un miembro del CAB o un administrador que no lo haya propuesto. Editar un modelo aprobado lo devuelve
  a «propuesto».
- La aprobación caduca en la revisión periódica (365 días por defecto). Si la tasa de fallo supera el umbral (20 %
  tras 5 cierres), el modelo se suspende solo y sus cambios vuelven al CAB.
- En el alta del cambio, al elegir «Estándar» aparece el selector de modelos vigentes; sin modelo no se puede crear.
  Un estándar de bajo riesgo que encaja en su modelo se aprueba solo.

**Revisión posterior a la implantación (PIR).** Detalle en [docs/PIR.md](docs/PIR.md).

- Al implantar (o cerrar, según la configuración) un cambio normal o de emergencia se programa sola su PIR, con
  fecha de hoy + 7 días. En los estándar es opcional: se programa a mano desde la sección *PIR* del panel del cambio.
- La PIR es un cuestionario guiado por la plantilla: criterios de éxito (sí / no / parcial), resultado global,
  incidencias provocadas, marcha atrás, KPIs antes y después, acciones de mejora (nacen como tareas) y lecciones
  (van a `/lessons`). Se envía, la aprueba otra persona (quien implantó o gestionó no puede si la empresa lo exige)
  y se cierra.
- El **Panel del CAB** muestra las PIR pendientes y vencidas. Un cambio cerrado con la PIR obligatoria sin aprobar
  no cuenta como «cerrado del todo».
- En un cambio estándar, una PIR «fallo» aprobada suma un fallo a su modelo y puede suspenderlo.
- Las PIR asignadas salen en la **Bandeja** (pestaña *PIR*) y en **Mi trabajo → Revisiones PIR** (`/pir`), que
  también tiene los informes de tasa de éxito y de cumplimiento. Configuración: `/settings/pir`.

### 24.9 Problemas y errores conocidos (KEDB)

1. En **Problemas**, *Gestionar* abre el ciclo del problema: incidentes vinculados (y buscar más), causa raíz con el
   asistente y sus plantillas, *Aprobar el análisis* (administrador, con causa escrita) y crear el cambio que la
   elimina.
2. Desde el problema se publica el **error conocido** con su solución temporal, los días hasta su revisión y un
   artículo de la base. El artículo que nace así queda **en revisión** e interno.
3. **Errores conocidos** lista la KEDB, con *Marcar como revisado* y la efectividad de cada solución temporal. Los
   errores caducados se revisan solos cada día.

El sistema propone problemas a partir de incidentes repetidos (cada hora). Las plantillas de causa raíz propias se
gestionan desde la misma pestaña (administrador).

### 24.10 Base de conocimiento y su bucle de calidad

- **Artículos** (pestaña **Base de conocimiento**): borrador, en revisión, publicado y archivado. Con la revisión
  activada (`SD_KB_REQUIRE_REVIEW`), el autor *envía a revisión* y un revisor publica o devuelve con comentarios.
  Cada artículo guarda versiones y se puede volver a una anterior. Un ticket se puede convertir en artículo.
- **Portal**: mientras el cliente escribe su petición ve artículos que podrían resolverla; *Me lo ha resuelto* no
  abre el ticket y cuenta un ticket evitado.
- **Idiomas**: el panel «Versiones en otros idiomas» genera las versiones del portal; cada una queda en revisión.
- **Vista Calidad** (selector *Artículos / Calidad* de la pestaña):
  - respuestas del asistente con **citas** a artículos (`[KB-0001]`);
  - **correcciones de experto** (*Corregir* / *Responder*), que se aplican enseguida a preguntas parecidas;
  - **preguntas sin respuesta** de clientes, agrupadas, con *Responder*, *Crear artículo* o *Descartar*. Desde el
    23-11-2026 son trabajo con dueño: **Seguimiento** (responsable, plazo y estado pendiente / en curso / hecho, con
    aviso al responsable), **Convertir en tarea** (una tarea en el proyecto que elijas, asignada al responsable) y
    **Artículo que la responde**: al **publicar** ese artículo la pregunta pasa a respondida y su tarea a hecha, con
    aviso. *Crear artículo* desde la pregunta la enlaza al artículo nuevo (si se crea en borrador, se cierra al
    publicarlo). Endpoints `PATCH /sd/kb/gaps/{id}/seguimiento`, `POST …/tarea`, `PUT …/articulo` (`sd.completo`;
    la tarea, además, con las reglas de `POST /tasks`); todo auditado. Retención: tipo `sd_kb_gaps`, ahora
    bloqueable también por responsable y tarea;
  - **alertas** de artículos viejos y de artículos contradictorios (pasada diaria a las 03:10 o *Revisar ahora*).
- Cada respuesta del asistente y del chat del portal se puede valorar con pulgar arriba o abajo; un pulgar abajo
  registra la pregunta como sin respuesta.

### 24.11 Página de estado, CSAT y tiempo

- **Página de estado** (*Configuración → Service desk → Página de estado*): componentes con su estado e incidentes
  declarados con actualizaciones. La página pública es `/status?org=<slug>` (anónima, en el idioma de la empresa) y
  hay un fragmento para insertarla en una web. Cada empresa ve solo la suya.
- **CSAT**: al cerrar un ticket, el portal pide al solicitante una valoración de 1 a 5. No se envía encuesta por
  correo: un ticket que se queda en *resuelto* sin cerrar no la pide.
- **Tiempo a partes de horas**: al registrar tiempo en un ticket se puede marcar *facturable*. Si el ticket tiene
  proyecto, pasa a tus partes con las reglas de siempre (pertenecer al proyecto, tener tarifa, fecha no bloqueada,
  topes, medias horas). Si una regla lo impide, el tiempo se queda en el ticket y la pantalla dice por qué. Ver
  [21. Imputaciones y partes de horas](#21-imputaciones-y-partes-de-horas).

### 24.12 Diseñador de flujos, herramientas y paneles

- **Diseñador de flujos de soporte** (`/sd/workflow-designer`, también desde *Configuración → Service desk*): grafos
  con nodos de inicio, fin, estado, decisión, aprobación, espera, aviso, llamada HTTP y crear ticket. Se valida, se
  guardan versiones y se publica una. El nodo de inicio puede declarar *Arranca solo cuando* (se crea, cambia de
  estado, se incumple el SLA…) y una condición (`priority == p1_critical`). Un flujo no arranca dos veces sobre el
  mismo ticket.
- **Herramientas**: asignación recomendada (reglas ponderadas, sin modelo entrenado), resolución automática,
  correlación de alertas, despliegue de cambios, asistente de llamadas (clasifica turnos ya transcritos; no hay
  telefonía), cola por riesgo y agente autónomo.
- **Agente autónomo**: apagado por defecto; se enciende por empresa en *Configuración → Service desk → Agente
  autónomo*, en modo **sugerir** (deja la propuesta para *Aplicar* o *Descartar*) o **ejecutar**. Prueba primero los
  playbooks de la empresa. Un ticket que habla de seguridad siempre va a una persona.
- **Mi panel**: widgets por vista (operación, responsable, dirección). Cada persona guarda el suyo; un administrador
  puede guardar el de la empresa.
- **Panel de soporte** (`/support-dashboard`): métricas ITIL (MTTR, FCR…) y rendimiento de agentes de los últimos N
  días.
- **Panel del agente** (`/agent-dashboard`): eliges persona y periodo (7–90 días) y ves abiertos, resueltos, tiempo
  medio, cumplimiento del SLA y CSAT. El mérito es del agente asignado **ahora**.
- **Asistente del portal**: en el portal, *Autoservicio → Asistente y chat*. El cliente pregunta por sus tickets,
  busca en la base de conocimiento o pide algo del catálogo; las peticiones (y el restablecimiento de contraseña, si
  la empresa tiene ese servicio) solo se **proponen** y se crean cuando el cliente confirma. Sin IA disponible,
  funciona por palabras clave y lo dice.

#### Consejos

- Abre un ticket concreto con `/service-desk?ticket=<id>`: es el enlace de cada aviso.
- Antes de responder, mira el bloque *Posibles duplicados*: fusionar a tiempo ahorra dos conversaciones.
- Usa *Pendiente del cliente* en vez de dejar el ticket en curso: para el SLA y la respuesta del cliente lo
  reanuda sola.
- Si un cambio «estándar» te da error al crearlo, el modelo está suspendido, caducado o no cubre tus CIs: el
  mensaje dice el motivo.
- Los ajustes `SD_*` y `SLA_*` se cambian en caliente por empresa; la lista está en
  [docs/REFERENCIA_DE_AJUSTES.md](docs/REFERENCIA_DE_AJUSTES.md).

#### Más detalle

[docs/SERVICE_DESK.md](docs/SERVICE_DESK.md): ciclo de vida y avisos, SLA/OLA/UC, escalado, correo, catálogo,
cambios estándar, monitorización, KB, tareas de fondo, credenciales, ajustes y límites conocidos.

---

## 25. CMDB, software y vulnerabilidades

**Qué es.** La base de datos de configuración (CMDB): los elementos de configuración (CI), sus relaciones y su
impacto; y, encima, qué software corre en cada CI, con qué está hecho (SBOM), qué vulnerabilidades le afectan, cómo
se remedian y cuál es el índice de riesgo. Hay **una sola CMDB**: la misma que se elige en un ticket, un problema o
un cambio.

**Para quién.** `/cmdb` con `cmdb.ver` (dirección y PM). Las pestañas de software y riesgo, con `software.ver`
(dirección y PM); escribir en ellas, `software.gestionar`; aprobar excepciones y líneas base, `software.aprobar`
(dirección). Agentes, clases y descubrimiento, solo administración.

**Pestañas de la CMDB**: **Inventario**, **Topología**, **3D e impacto**, **Impacto**, **Software**, **Dónde se
usa**, **Por máquina**, **Vulnerabilidades**, **Riesgo** y, para administración, **Agentes**, **Clases**, **Clases
propias** y **Descubrimiento**.

### 25.1 CIs y relaciones

1. *Nuevo CI*: código automático (`CI-0001`), clase (servidor, base de datos, aplicación, contenedor…), estado
   (operativo, degradado, mantenimiento, retirado), entorno, criticidad, host, IP, versión y los **datos propios de
   su clase** (sistema operativo y RAM de un servidor, motor y puerto de una base de datos…).
2. **Relaciones** (icono de enlace): *depende de*, *aloja a*, *conecta con*, *tiene copia en*, *lo monitoriza*,
   *forma parte de*. Se leen desde el CI que las tiene («web-01 aloja a Portal»).
3. **Historial** (icono de lista): cada campo que cambia, quién y cuándo; lo que cambia el descubrimiento sale como
   «por el descubrimiento».
4. **Impacto**: radio de impacto de un CI y qué se rompe si se retira. Alimenta el análisis de impacto de los
   cambios, la topología, el grafo 3D y la correlación de alertas.
5. **Borrar** un CI lo oculta del inventario; los tickets, problemas y cambios que lo citan lo conservan.

En *Clases* se decide qué datos pide cada clase base; en *Clases propias*, cada empresa crea sus clases sobre una
clase base.

### 25.2 Descubrimiento y agentes

- **Descubrimiento**: proveedores AWS, Azure, GCP, Kubernetes, vSphere y SNMP, con su configuración guardada
  cifrada, lanzar uno o todos, ver sus ejecuciones y *Aprobar línea base*. Un escaneo completo retira lo que el
  proveedor ya no encuentra. Si cambia la configuración de un CI, se marca **deriva** hasta que se aprueba la línea
  base. Hay reconciliación de duplicados con *Fusionar duplicados*.
- **Agentes**: se registra un agente por servidor y se copia su token (solo se enseña una vez). Cada envío actualiza
  su CI y, si trae inventario, su software y su activo en ALM. Revocar un agente rechaza sus envíos.
- **Escaneos de software** (SSH en Linux, WinRM en Windows, API de un EDR/RMM): se configuran en *Configuración →
  Service desk → Software y vulnerabilidades* (`/settings/cmdb-software`) y se lanzan con *Escanear ahora* desde la
  pestaña Software.

Ninguno de estos conectores se ha probado contra un proveedor real: solo con respuestas simuladas.

### 25.3 Inventario de software y composición (SBOM)

1. **Software**: cuadro de mando y catálogo de productos con filtros. La ficha de un producto enseña versiones con
   fin de soporte, composición en árbol, instancias desplegadas, vulnerabilidades, licencias de ALM y grafo.
2. **Importar** sobre una versión: SBOM CycloneDX o SPDX, ficheros de dependencias (`package-lock.json`,
   `composer.lock`, `requirements.txt`, `poetry.lock`, `pom.xml`, `go.mod`, `Cargo.lock`…, también varios a la vez o
   en un zip), CSV, informes de Trivy o Grype, o *desde Activos* (las instalaciones de ALM).
3. **Dónde se usa**: buscador del tipo «nginx», «php < 8.2» o `pkg:npm/lodash`.
4. **Por máquina**: el software de un CI, sus versiones, configuración, deriva, hallazgos, activo y licencias.

Una versión que no se puede fijar queda como **versión desconocida** y sus avisos salen como «posible afectado».
Los secretos de las configuraciones leídas nunca se guardan: se enmascaran.

### 25.4 Vulnerabilidades e índice de riesgo

- **Fuentes de avisos** (todas opcionales): OSV.dev, NVD, GitHub Advisories, EPSS, KEV y endoflife.date, o un
  fichero importado si no hay red.
- **Hallazgos**: cada aviso que casa con un paquete o CPE en una versión afectada. La **prioridad** (0-100) combina
  CVSS, KEV, EPSS, criticidad, exposición y entorno, y guarda su desglose. Cada severidad tiene su **plazo de
  remediación** (15/30/90/180 días; 7 si está en KEV).
- **Gestión** (*Vulnerabilidades*): triaje, en curso, resuelto (verificado al reevaluar), mitigado, falso positivo o
  aceptado. Desde el hallazgo se abre un **ticket**, un **cambio** o una **tarea**. Una **excepción** lleva motivo,
  controles y caducidad, y la aprueba la bandeja o un administrador, nunca quien la pide.
- **Riesgo**: índice 0-100 de la empresa, un cliente (o unidad interna), un servicio, una máquina o una aplicación,
  con sus factores, tendencia y comparación; **plan de reducción** de X a Y; métricas (MTTP, densidad, SO sin
  soporte); superficies (Internet, contenedores, nube); controles compensatorios; intentos de explotación; informes
  programados.

#### Consejos

- Empieza por *Dónde se usa* cuando llega un CVE: te dice software, máquinas, servicios y clientes en una búsqueda.
- La CMDB avisa con un enlace cuando falta configuración (sin fuentes de avisos, sin conexiones de escaneo); el
  enlace solo lo ve quien tiene `software.config`.
- El análisis de impacto de un cambio ya incluye el software y los hallazgos de los CIs afectados.

#### Más detalle

[docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md](docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md) (modelo, fuentes, fórmulas
de prioridad y de riesgo, importación, escaneos, GRC y límites) y el apartado 13 de
[docs/SERVICE_DESK.md](docs/SERVICE_DESK.md) (CMDB y descubrimiento).

---

## 26. Licencias y activos (ALM)

**Qué es.** El inventario único de lo que la empresa **posee**: licencias, equipos, proveedores y contratos; quién
tiene qué y desde cuándo; lo que cuesta y a quién se imputa; si se usa de verdad; y si se cumple lo contratado. La
CMDB responde a «qué se ejecuta»; ALM, a «qué se ha comprado y quién lo tiene».

**Para quién.**

| Pantalla | Ruta | Capacidad |
|---|---|---|
| Licencias y activos | `/alm` | `alm.ver` (dirección y PM); escribir y ver lo económico, `alm.gestionar` (responsables) |
| Altas y bajas de equipos | `/alm/altas-y-bajas` | `equipo.ver`; bajas y kits, `alm.personas` (dirección, PM, RRHH) |
| Mis equipos y licencias | `/my-equipment` (menú *Mi trabajo*) | Cualquiera con sesión, cada uno lo suyo |
| Fuentes de uso de licencias | `/settings/alm-fuentes` | Administración |

### 26.1 Pestañas de `/alm`

| Grupo | Pestañas |
|---|---|
| Inventario | Resumen, Licencias, Activos, Proveedores, Contratos |
| Quién tiene qué | Asignaciones, Préstamos, Actas, Historial |
| Costes y contratos | Costes, Renovaciones, Conciliación, Centros de coste, Cumplimiento |
| Uso real | Uso, Recuperación, Ajuste de nivel, Cumplimiento, Software no controlado |

`/alm?tab=<pestaña>` abre una directamente.

### 26.2 Activos y hardware

1. **Alta del activo** (*Activos*): tipo (portátil, sobremesa, servidor, móvil, monitor, VM…), número de serie,
   precio, vida útil y, en *Ciclo de vida y CMDB*, el CI que sostiene, garantía, fin de vida, fin de leasing y
   próximo mantenimiento.
2. **Ciclo de vida**: pedido → en almacén → asignado o prestado (con fecha de devolución) → reparación → baja →
   reciclaje; también perdido o robado. El estado y el titular **no se editan**: cambian con las acciones (asignar,
   prestar, devolver, reparar, dar de baja).
3. **Actas**: al entregar o devolver un equipo a una persona se genera el acta con checklist, estado físico, fotos y
   PDF, y se firma (en la propia aplicación o con el proveedor de firma configurado).
4. **Vencen pronto**: arriba de *Activos*, lo que vence en 30, 60, 90 o 180 días. El botón de renovación abre una
   petición de servicio con el CI del activo (y cada día se abre sola para lo que vence en `SD_ASSET_REFRESH_DAYS`).

### 26.3 Licencias y asignaciones

- **Métricas de licencia**: por usuario nominal, por dispositivo, concurrente (por pico medido), por volumen y de
  sitio. Niveles (`tier`) y SKU para comparar ediciones.
- **Asignación universal**: una licencia o un equipo se asigna a una persona, un proyecto, un departamento, un
  cliente o un equipo; en modo asignación, préstamo o **bolsa** (un proyecto recibe asientos y los reparte). Nada se
  borra: se cierra, y el *Historial* dice quién tuvo qué, cuándo y por qué.
- Si la empresa tiene un flujo de aprobación para asignaciones, la asignación nace pendiente y se decide en la
  bandeja de Aprobaciones.
- La clave de licencia se guarda cifrada; verla queda en auditoría.

### 26.4 Costes, renovaciones y conciliación

- **Costes**: coste por titular y día (suscripciones repartidas por día, perpetuas y equipos amortizados, asientos
  ociosos aparte), imputado a proyecto, centro de coste y cliente. Suma en la rentabilidad del proyecto y en el EVM,
  y hay informe de refacturación con margen (es un informe: no emite facturas).
- **Renovaciones**: avisos antes del fin del preaviso; decisión de renovar, reducir o cancelar con el uso real a la
  vista. Sin decisión, una renovación automática prorroga un periodo.
- **Conciliación**: factura del proveedor frente a lo que dice el contrato y frente al gasto que la paga, con
  tolerancia; las discrepancias revisadas se aceptan con nota.

### 26.5 Uso real, conectores y recuperación

1. **Conectar fuentes** (`/settings/alm-fuentes`): Microsoft 365 / Entra ID, Intune, Google Workspace, Okta, Jamf
   Pro, los accesos y el SSO de contecflow, y el agente de inventario de la CMDB. Cada una con credenciales de la
   propia empresa, *probar*, sincronización manual o cada hora, y mapeo de productos a licencias.
2. **Uso**: cada asignación sale *en uso*, *infrautilizada*, *sin uso* o *sin datos*. Los días de ausencia aprobada
   se descuentan, e «instalado» no cuenta como «usado».
3. **Recuperación** (*harvesting*): con una política del dominio «licencias» se avisa a la persona, luego a su
   responsable, y se libera la licencia (o se pide aprobación). Se protege a quien está ausente, a la asignación
   reciente y a lo que no tiene datos. La persona puede pulsar *La sigo necesitando* en *Mis equipos y licencias*.
4. **Ajuste de nivel**: propone bajar de edición a quien no usa los servicios que justifican la superior, con el
   ahorro calculado.
5. **Cumplimiento**: posición de cada licencia según su métrica (déficit, excedente, conforme), exposición y coste
   ocioso; exportable a CSV o Excel para una auditoría.
6. **Software no controlado**: gastos de software, productos de las fuentes y aplicaciones SSO/OAuth sin licencia en
   ALM. *Alta* crea la licencia; *Descartar* lo marca como no controlado.

Ningún conector se ha probado contra un tenant real: solo con dobles.

### 26.6 Altas y bajas de equipos

`/alm/altas-y-bajas`, pestañas **Bajas**, **Devoluciones**, **Kits propuestos**, **Kits de alta**, **Peticiones** y
**Catálogo**:

- **Bajas**: al desactivar a una persona (a mano, por SCIM o por fin de contrato) se abre su expediente: se liberan
  sus licencias (al momento o N días después) y se abre una devolución con ticket por cada equipo.
- **Kits de alta**: qué licencias y equipos recibe cada perfil; al dar de alta a alguien se propone el kit y su
  responsable lo confirma con un clic. Lo que no hay en almacén se pide por compra.
- **Catálogo**: los servicios «Pedir licencia» y «Pedir equipo» del catálogo del Service Desk, con aprobación de
  varios niveles; al aprobarse, la petición da el alta en ALM o abre la compra.

#### Consejos

- Enlaza cada activo físico con su CI: así el análisis de impacto de la CMDB enseña los equipos afectados.
- Para un contrato de soporte, rellena el *Plazo del proveedor (UC, horas)*: es lo que activa el reloj UC en los
  tickets (ver [24.4](#244-sla-ola-uc-calendarios-y-escalado)).
- Antes de renovar, mira la pestaña *Uso*: la decisión de renovación guarda una foto del uso que había.

#### Más detalle

No hay documento propio en `docs/`. El enlace con el Service Desk está en el apartado 14 de
[docs/SERVICE_DESK.md](docs/SERVICE_DESK.md); los ajustes del grupo `alm`, `licencias_uso` y
`licencias_integracion`, en [docs/REFERENCIA_DE_AJUSTES.md](docs/REFERENCIA_DE_AJUSTES.md).

---

## 27. Clientes, CRM y pipeline

**Qué es.** La ficha maestra de cada cliente (de la que cuelgan proyectos, contratos, licencias, tickets y accesos
al portal), el embudo comercial de oportunidades, los contratos comerciales y el NPS con la salud del cliente.

**Para quién.** Las pantallas `/clients`, `/pipeline`, `/contracts` y `/nps` se abren con `finanzas.ver` (dirección
y PM), en el grupo **Clientes y finanzas** del menú. Gestionar el cliente y su portal pide `clientes.gestionar`;
calcular la salud, `clientes.dirigir`. Contratos con IA (`/contracts-ai`) pide `ia.ver`.

### 27.1 Clientes (`/clients`)

1. *Nuevo cliente*: nombre, nombre corto, NIF, sector, estado (en captación, activo, inactivo, perdido), datos de
   contacto y el contacto principal (elegido o nuevo). El tipo distingue **externos** de **unidades internas** (ver
   [28. Clientes internos](#28-clientes-internos)).
2. Busca y filtra por estado; cambia entre vista de lista y de tarjetas.
3. Abre un cliente. Pestañas: **Contactos** (principal, facturación, técnico, dirección, soporte…), **Proyectos**
   (vincular y desvincular), **Contratos**, **Licencias**, **Facturas** (en una unidad interna, *Coste y
   presupuesto*), **Tickets SD** (lectura) y **Portal**.
4. **Portal** tiene sus subpestañas: **Accesos** (usuarios del portal), **UAT**, **Solicitudes**, **Mensajes**,
   **Documentos** y **Configuración** (idioma por defecto del portal, máximo de usuarios, si el cliente puede editar
   su perfil y cambiar la contraseña, nivel de SLA…). Ver [29. Portal de clientes](#29-portal-de-clientes).
5. *Editar* abre la ficha. No hay botón de borrar cliente.

No hay registro de actividades comerciales en pantalla: las actividades de una oportunidad solo se manejan por API
(`/api/v1/pipeline/{id}/activities`).

### 27.2 Pipeline comercial (`/pipeline`)

1. *Nueva oportunidad*: nombre, cliente existente (o nombre de uno nuevo), valor, probabilidad, tipo de contrato,
   tarifa, inicio previsto, duración y cierre previsto.
2. **Etapas**: Lead → Cualificado → Propuesta → Negociación → Ganado; además Perdido y Cancelada. Se cambia la etapa
   desde la tarjeta; solo se ofrecen los pasos permitidos (Ganado y Cancelada son finales; una perdida puede volver
   a Lead).
3. En el detalle: *Generar propuesta* (rellena una plantilla, no usa IA), *Ver propuesta* y *Marcar enviada* (anota
   la fecha; no envía nada).
4. *Convertir a proyecto*: crea el proyecto en planificación con el presupuesto y la tarifa de la oportunidad, su
   contrato de ingresos y marca la oportunidad como ganada.

**Regla de totales** (la misma en la pantalla, la API, BI, informes y el asistente):

| Concepto | Qué cuenta |
|---|---|
| Valor del pipeline abierto | Lead, Cualificado, Propuesta y Negociación |
| Previsión ponderada (importe × probabilidad) | Solo las abiertas |
| Tasa de éxito | Ganadas / (ganadas + perdidas) |
| Sin decisión (canceladas) | Fuera del pipeline y de la tasa; se dan aparte |

Una perdida o cancelada no suma aunque conserve una probabilidad. Las ganadas no son pipeline: son contratación. El
filtro de estado (Todas, Abiertas, Ganadas, Perdidas, Canceladas) filtra el tablero y la lista, no los KPI. Detalle
en [docs/PIPELINE_COMERCIAL.md](docs/PIPELINE_COMERCIAL.md).

### 27.3 Contratos y contratos con IA

- **Contratos** (`/contracts`): contrato comercial por proyecto. El tipo decide el dato obligatorio: precio cerrado
  (importe total), tiempo y materiales (tarifa), bolsa de horas (horas) o cuota mensual (importe mensual). Estados:
  borrador, activo, vencido, cancelado. Dentro, **órdenes de trabajo** (abierta, en curso, completada, facturada).
  Las horas consumidas de una bolsa son las imputadas en el proyecto entre las fechas del contrato. Ningún contrato
  vence solo, y «facturada» en una orden es una etiqueta: no crea factura.
- **Contratos con IA** (`/contracts-ai`): se abre desde el enlace de la cabecera de la ficha del proyecto. Analiza el
  texto o el PDF de un contrato con el proveedor de IA y guarda los análisis por proyecto. Necesita un proveedor de
  IA configurado (ver [38. Inteligencia artificial](#38-inteligencia-artificial)).

### 27.4 NPS y salud del cliente (`/nps`)

1. Elige un cliente y registra una respuesta de 0 a 10; se clasifica como promotor, pasivo o detractor.
2. Consulta el resumen de NPS de N días y el histórico de salud.
3. *Calcular salud* guarda una foto; la clasificación ordena a los clientes por su última foto.

Límite: el cálculo de salud de esta pantalla usa sobre todo constantes fijas (60 % del resultado) y no el modelo de
salud configurable (`HEALTH_*`). Las encuestas del portal no alimentan el NPS.

#### Consejos

- Crea primero el cliente y luego la oportunidad eligiéndolo de la lista: la conversión a proyecto lleva cliente,
  tarifa y fechas.
- Una oportunidad perdida o cancelada no se convierte en proyecto.

#### Más detalle

[docs/PIPELINE_COMERCIAL.md](docs/PIPELINE_COMERCIAL.md). Facturación y rentabilidad, en
[32. Finanzas](#32-finanzas-facturación-gastos-rentabilidad-y-presupuestos).

---

## 28. Clientes internos

**Qué es.** Las unidades de la propia compañía (departamentos, unidades de negocio, filiales, centros de coste)
gestionadas con el mismo modelo de cliente: se les informa lo que cuestan (**showback**), se les carga sin factura
legal (**chargeback**) o se les factura con precio de transferencia (**intercompañía**), y entran con su login a un
portal interno, **Mi departamento**.

**Para quién.**

| Capacidad | Quién | Qué abre |
|---|---|---|
| `interno.portal` | Personal interno | Mi departamento (`/mi-departamento`), solo sus unidades |
| `interno.gestionar` | Dirección y PM | Clientes internos (`/internal-clients`): cuadro, costes, borradores de cargo, beneficios, adopción, papeles |
| `interno.cargos` | Dirección | Emitir, exportar y anular cargos; servicios compartidos y su reparto |

### 28.1 Dar de alta una unidad

1. En **Clientes** (`/clients`), *Nuevo cliente* con tipo **interno**: subtipo, departamento, área, centro de coste,
   empresa del grupo (para intercompañía), responsable de negocio y finanzas (modo, método de coste, tabla de
   tarifas, margen, cuenta contable).
2. **Quién es de la unidad** se deduce solo: las personas cuyo departamento coincide con el de la unidad, su centro
   de coste o su área, más el responsable y las personas designadas. No hay altas manuales.
3. Designa papeles en la ficha de la unidad: **delegado** (actúa como responsable), **finanzas** (ve costes) y
   **usuario clave** (firma UAT).

### 28.2 Coste, cargos y presupuesto

- **Coste** de la unidad por fuente: horas (a coste o a tarifa interna), proyectos a precio cerrado, peticiones del
  catálogo con precio interno, licencias y equipos (de ALM), aplicaciones propias y el **reparto de servicios
  compartidos** (por usuarios, tickets, licencias, software o porcentaje fijo).
- **Cargos** (pestaña *Cargos*): *Generar* crea el borrador del mes; luego se emite, se exporta o se anula.
  Showback: es un informe. Chargeback: nota de cargo interna sin IVA, exportable a CSV de asientos. Intercompañía:
  al emitir crea una factura real.
- **Presupuesto**: el presupuesto aprobado del año con la unidad como cliente. Un cargo que deja el consumo por
  encima del 100 % pasa a *por aprobar*; lo aprueba el responsable de la unidad (o la bandeja), nunca quien lo generó
  ni quien lo emitió.
- **Servicios compartidos** y la cuenta contable de TI: *Configuración → Finanzas → Clientes internos*
  (`/settings/clientes-internos`). Sin cuenta de TI, la exportación se niega y el cuadro avisa.

### 28.3 Pantallas

- **Clientes internos** (`/internal-clients`): pestañas **Cuadro de dirección** (coste por unidad y por fuente,
  presupuesto frente a real con semáforo, cartera), **Cargos**, **Unidad** y **Beneficios**.
- **Mi departamento** (`/mi-departamento`, menú *Mi trabajo*): **Resumen**, **Proyectos**, **Hitos** (el responsable
  firma o rechaza), **Pruebas de aceptación** (firma el usuario clave o el responsable), **Tickets y SLA**, **Coste y
  presupuesto** (solo responsable y finanzas), **Peticiones** (pedir proyecto o servicio por el
  [31. Flujo de demanda](#31-flujo-de-demanda); sin flujo configurado, va a la cartera) y **Adopción y beneficios**.
  La satisfacción (NPS o CSAT) admite una respuesta por persona y mes.
- Cartera, Rentabilidad y los paneles de proyectos tienen un filtro **externos / internos**.

#### Consejos

- Pon siempre un responsable de negocio: sin él, nadie puede aprobar un exceso de presupuesto y el informe de
  cumplimiento lo marca.
- Con método «tarifa interna», asigna la tabla de tarifas; sin ella la ficha avisa.

#### Más detalle

[docs/CLIENTES_INTERNOS.md](docs/CLIENTES_INTERNOS.md): modelo, papeles, fórmulas de coste, cargos, portal interno,
GRC, API y pruebas.

---

## 29. Portal de clientes

**Qué es.** Una aplicación aparte, sin el menú de contecflow, en la que los contactos de un cliente entran con su
correo y contraseña para seguir sus proyectos, probar, pedir, abrir tickets, hablar con el equipo y aprobar facturas.
Los usuarios del portal no son usuarios de la aplicación.

**Para quién.** Los contactos del cliente con acceso al portal (`/portal`). Lo administran quienes tienen
`clientes.gestionar` (ficha del cliente) y `finanzas.ver` (`/client-portal`).

### 29.1 Qué ve el cliente (`/portal`)

| Grupo | Sección | Qué hace |
|---|---|---|
| Resumen | Inicio | Panel de sus proyectos |
| Entrega | Hoja de ruta | Avance, hitos y entregables |
| Entrega | Pruebas UAT | Sesiones de aceptación: enviar resultados y reportar fallos |
| Entrega | Solicitudes | Pestaña *Demandas* (el [31. Flujo de demanda](#31-flujo-de-demanda)) y las peticiones de cambio clásicas (crear, decidir el presupuesto, retirar) |
| Soporte | Autoservicio | Sus tickets, nuevo ticket desde el catálogo público o formularios, comentarios, valoración CSAT, base de conocimiento y *Asistente y chat* |
| Soporte | Mensajes | Chat con el equipo y conversaciones formales |
| Documentación | Documentos | Ver y firmar con un clic (registro de firma, no firma electrónica cualificada) |
| Documentación | Wiki | Páginas publicadas para el portal |
| Documentación | Facturas | Facturas emitidas (solo con permiso de ver presupuesto); aprobar o rechazar |
| Cuenta | Notificaciones, Encuestas, Mi perfil | Avisos, encuestas, perfil, apariencia, idioma y contraseña |

Además hay un chat con IA en cada página, que solo ve los proyectos asignados al cliente. Aprobar una factura anota
la decisión del cliente y avisa al equipo; no cambia el estado de la factura.

### 29.2 Dar acceso a un cliente

1. **Clientes** → ficha del cliente → **Portal** → **Accesos**.
2. Crea el usuario: nombre, correo, contraseña (o generada por el sistema), proyectos que verá y permisos. Se aplica
   el máximo de usuarios del portal del cliente. Las credenciales se muestran una sola vez.
3. *Reenviar acceso* genera una contraseña nueva y la envía. Una contraseña generada por el sistema obliga al
   cliente a cambiarla al entrar: hasta entonces solo ve la pantalla de cambio.
4. *Forzar restablecimiento* (con motivo) cierra sus sesiones, le obliga a cambiar la contraseña y, si se pide, le
   manda el enlace.

El usuario del portal hereda la empresa de su cliente: ve solo los proyectos que se le asignan.

**Contraseña, eliminar y archivar** (`clientes.gestionar`):

- **Al dar acceso**, la contraseña se genera y se envía por correo (por defecto) o se pone a mano: mostrar u
  ocultar, generar una aleatoria, *Obligar a cambiarla en el primer acceso* (marcada por defecto) y envío opcional
  por correo al titular. Después se cambia con **Establecer contraseña**.
- Cumple la política de contraseñas de la empresa, solo se guarda con hash, nunca vuelve en la API ni queda en la
  auditoría, y al ponerla se cierran las sesiones del usuario.
- **Eliminar** lo decide el servidor: sin historial, se borra; con historial, se **archiva** (no entra, sale de las
  listas salvo con *Ver archivados*, conserva su historial y se puede **Restaurar**).
- Todo queda en `audit_log`. La supresión RGPD es una acción aparte, para administradores ([15.3](#153-rgpd)).
  Detalle en [docs/seguridad/politicas_de_cuenta.md](docs/seguridad/politicas_de_cuenta.md) §3 ter.

### 29.3 Contraseña olvidada

En la entrada del portal, *¿Olvidaste tu contraseña?* pide el correo y envía un enlace (la respuesta es la misma
exista o no la cuenta). El enlace lleva a `/portal/reset-password`, vale 30 minutos y una sola vez, aplica la
política de contraseñas de la empresa y, al guardar, cierra todas las sesiones del portal de ese cliente. Detalle
en [docs/seguridad/politicas_de_cuenta.md](docs/seguridad/politicas_de_cuenta.md).

### 29.4 Idiomas del portal

El portal está en ocho idiomas: español, inglés, francés, alemán, italiano, portugués, polaco y chino. El idioma se
elige así: la preferencia del usuario del portal, si no el idioma por defecto del portal de su cliente (ficha →
Portal → Configuración), si no el de la empresa proveedora, y si no el del navegador (o inglés). Las traducciones
del contenido (artículos de la base de conocimiento, por ejemplo) se revisan en *Configuración → Portal de clientes
→ Traducciones del portal*.

### 29.5 Estado público de un proyecto (`/portal/view/:token`)

Página de solo lectura, sin login, con el estado, los hitos y los entregables de un proyecto, a la que se llega por
un enlace firmado que caduca (`PORTAL_SHARE_LINK_EXPIRE_HOURS`, 72 h por defecto). No hay botón en la interfaz que
cree el enlace: se genera por API (`POST /api/v1/portal/share-link/{project_id}`).

### 29.6 Administración del portal (`/client-portal`)

En **Clientes y finanzas → Portal de clientes**, la gestión del portal **por proyecto** (la ficha del cliente la hace
por cliente): pestañas **Contactos**, **UAT** (crear sesiones y casos, gestionar fallos), **Solicitudes**
(responder), **Mensajes**, **Documentos** (publicar) y **Wiki** (páginas visibles en el portal).

### 29.7 Formularios públicos

*Configuración → Portal de clientes → Formularios públicos* (`/settings/public-forms`, capacidad
`portal.formularios`, dirección y PM):

1. Crea el formulario: tipo (ticket o tarea), proyecto de destino (obligatorio para tareas), cola, prioridad y
   categoría por defecto, mensaje de éxito y correos a avisar.
2. *Copiar enlace*: página propia sin login en `/intake/:token`.
3. *Copiar código para tu web*: un `<script>` que dibuja el formulario en cualquier web, en el idioma de la empresa.
4. Revisa los envíos de cada formulario. Cada envío crea el ticket o la tarea en la empresa del formulario.

#### Consejos

- Asigna al usuario del portal solo los proyectos que debe ver: el portal no muestra nada fuera de ellos.
- Las secciones del portal no se ocultan con los módulos marcados en la configuración del portal del cliente (no
  comprobado que tengan efecto).
- Las encuestas del portal solo se crean por API: sin ellas la sección *Encuestas* queda vacía.

#### Más detalle

El autoservicio, el CSAT y el asistente del portal se describen en [24. Service Desk](#24-service-desk) y en
[docs/SERVICE_DESK.md](docs/SERVICE_DESK.md). Seguridad del acceso: [8. Seguridad](#8-seguridad) y
[docs/seguridad/rutas_anonimas.md](docs/seguridad/rutas_anonimas.md).

---

## 30. Proveedores y portal de proveedores

**Qué es.** La gestión de terceros: freelances, empresas que aportan personas, empresas a las que se externaliza
trabajo y empresas que prestan un servicio gestionado (SOC, service desk externo, nóminas…). Cada caso se asigna, se
mide y se paga de forma distinta, y todos pasan por su control de riesgo (GRC). Las personas de un proveedor tienen
además su propio **Portal del proveedor**.

**Para quién.**

| Pantalla | Ruta | Capacidad |
|---|---|---|
| Subcontratistas | `/subcontractors` (*Clientes y finanzas*) | `proveedores.ver` (responsables); escribir y finanzas, `proveedores.gestionar` (dirección y PM) |
| Portal del proveedor | `/supplier-portal` (*Mi trabajo*) | `proveedores.portal`: solo personas externas marcadas como contacto del portal |
| Configuración de proveedores | `/settings/proveedores` | `proveedores.config` (dirección y PM) |

### 30.1 Tipos de proveedor y cómo se asignan

- **Freelance**: persona física. Su alta crea a la vez el proveedor, su persona y su usuario externo. Es un recurso
  más: capacidad, calendario, tarifas, tareas.
- **Empresa**, con uno o varios **modos**:
  - *aporta personas* (staff augmentation): la empresa no es asignable; sus personas sí;
  - *externalización* (outsourcing): la empresa se asigna como unidad mediante **paquetes de trabajo** (proyecto,
    fase, hito, entregable o tareas) con precio cerrado, criterios de aceptación y UAT;
  - *servicio gestionado*: servicios contratados con alcance, SLA, KPI, su cola del Service Desk e informes.
- En **Tareas**, *Externalizar a* asigna la tarea a un proveedor de outsourcing; es excluyente con el responsable.
- Ciclo de vida: alta → activo ⇄ suspendido → baja. Suspender bloquea trabajo nuevo y quita el acceso a sus personas.

### 30.2 Contratos, precios y SLA

1. En la ficha del proveedor, **Contratos y precios**: tipo de contrato, modos que cubre, fechas, renovación,
   mínimo comprometido, tope, pedido de compra, presupuesto o centro de coste.
2. Líneas de precio combinables: por recurso (hora, día, mes), precio cerrado, por unidad (ticket, dispositivo/mes,
   usuario/mes…), suscripción con exceso, gastos repercutidos y bonus; con escalados por volumen, mínimos y topes.
3. **Servicios**: SLA de respuesta y resolución y objetivo de cumplimiento. Los tickets de su cola son su consumo y
   su SLA; por debajo del objetivo se aplican **créditos** y por encima, **bonus**.
4. **Consumo y facturación**: medición (automática y manual) → previsión del periodo → **estado de cuenta** →
   conciliación con la factura del proveedor (dentro de la tolerancia, conciliado; fuera, en disputa) →
   **aprobación**. Las líneas aprobadas con proyecto suman en su coste.

### 30.3 Aprobación por importe

Con un flujo de la bandeja para el tipo «Estado de cuenta de proveedor» (*Configuración → Aprobaciones y políticas →
Flujos*, condiciones por importe en la moneda de la empresa), *Aprobar* envía el estado de cuenta a la bandeja de
Aprobaciones. Sin flujo, se aprueba directamente. En los dos casos no aprueba quien cerró el periodo ni quien
registró la factura.

### 30.4 Fuentes de medición

Para servicios cobrados por dispositivo/mes o usuario/mes, el recuento puede venir de:

- **manual**: consumo registrado o importado;
- **CMDB**: cuenta CIs con filtros (tipos, clases, entorno, fabricante, software instalado…), cada día o con
  *Medir ahora*; *Vista previa* dice cuántos contaría hoy;
- **externo**: un sistema (SIEM, consola del proveedor, MDM) manda el recuento por API o se importa.

Solo se guarda el número; un mes ya cerrado en un estado de cuenta no se toca.

### 30.5 Riesgo y cumplimiento del proveedor

Pestaña **Cumplimiento**: evaluación de riesgo (con próxima revisión), documentos con caducidad (encargado de
tratamiento RGPD, NDA, ISO 27001, SOC 2, ENS, seguros…), registro de accesos concedidos, suspender y dar de baja.
Activar un contrato sin los documentos exigidos se niega y dice qué falta. La pestaña **Rendimiento** da una
puntuación 0-100 (SLA, entregas a tiempo, rechazos, desviación de factura, documentos, riesgo).

### 30.6 Portal del proveedor (`/supplier-portal`)

1. **Dar acceso**: ficha del proveedor → **Cumplimiento** → «Portal del proveedor», marca a la persona como contacto
   del portal (necesita usuario con acceso vigente y proveedor activo).
2. **Qué ve la persona externa**: sus paquetes de trabajo, sus servicios con el SLA medido, sus informes, el consumo
   del periodo y sus estados de cuenta.
3. **Qué puede hacer**: subir informes de avance, periódicos, partes de servicio o evidencias de SLA, con ficheros
   adjuntos (pasan antivirus). Llegan a la ficha marcados «Desde el portal» y avisan al responsable interno.

Solo ve lo de su proveedor; nunca datos internos ni personas de la empresa. Con el proveedor suspendido, el portal
queda en solo lectura; con el acceso caducado, no entra.

#### Consejos

- Configura antes los catálogos (tipos de servicio, unidades de cobro, plantillas de contrato) en
  `/settings/proveedores`: si falta alguno, la acción avisa y enlaza allí.
- Enlaza cada servicio gestionado a su cola del Service Desk: sin cola no hay medición de SLA.

#### Más detalle

[docs/PROVEEDORES_Y_EXTERNALIZACION.md](docs/PROVEEDORES_Y_EXTERNALIZACION.md): modelo, reglas de asignación,
modelos de cobro, GRC de terceros, API, portal, aprobación por importe y fuentes de medición.

---

## 31. Flujo de demanda

**Qué es.** Un motor de flujos configurable por empresa para que un cliente (portal de clientes), una unidad interna
(Mi departamento) o un empleado pidan un cambio en un proyecto, una funcionalidad nueva fuera de todo proyecto o un
servicio, y la solicitud recorra las fases que la empresa defina, con responsables, decisiones, plazos, avisos y un
historial que no se puede alterar.

**Para quién.**

| Capacidad | Quién | Qué permite |
|---|---|---|
| (ninguna) | Cualquiera con sesión | `/demand`, vista *Mis solicitudes* |
| `demanda.ver` | Personal interno | Las solicitudes y decisiones de las que es responsable (*Todas las solicitudes*) |
| `demanda.gestionar` | Dirección y PM | Agendar comités, ejecutar y crear en nombre de otro |
| `demanda.config` | Dirección | *Configuración → Aprobaciones y políticas → Flujos de demanda* (`/settings/demanda`) |

### 31.1 Configurar (administración)

1. En `/settings/demanda`, pestaña **Tipos**: crea los tipos de solicitud (nombre, quién puede crearla —portal de
   clientes, portal interno, empleado, portal del proveedor—, sobre qué —proyecto, servicio, activo o nada— y qué
   flujo sigue).
2. Pestaña **Flujos**: crea un flujo o instala una **plantilla** (nueva funcionalidad con CAB y comité, cambio ITIL,
   alta de proveedor, compra por importe, acceso o permisos, iniciativa de cartera, petición a RR. HH.). El editor
   tiene: *General*, *Campos*, *Fases*, *Cierre*, *Simulador*, *Diagrama* y *JSON*.
3. **Fases y pasos**: en serie o en paralelo, condicionales, de tipo entrada, trabajo, revisión, aprobación, puerta o
   comité. El responsable de cada paso puede ser un rol, un grupo, una persona, un departamento, un comité con
   quórum, un flujo de la bandeja de Aprobaciones, el propio solicitante o un responsable dinámico (PM del proyecto,
   gestor de la cuenta, responsable de quien pide…).
4. **Al terminar**: acciones automáticas (crear proyecto, petición de cambio, propuesta de cartera, tarea, ticket,
   cambio ITSM, compra, Executive Summary en PDF y PPTX).
5. Prueba el recorrido con el **Simulador** antes de activarlo. Cada cambio sube la versión del flujo; una solicitud
   en curso sigue con la versión con la que empezó.

### 31.2 Pedir y decidir

1. **Pedir**: en `/demand` (*Nueva*), en el portal de clientes (*Solicitudes → Demandas*) o en Mi departamento
   (*Peticiones*). Se rellena el formulario del tipo y se *Envía*.
2. **Expediente**: cabecera con código, tipo, proyecto o «iniciativa independiente», estado, plazo y fase actual, y
   la línea de fases. Pestañas: ficha, historial, versiones, documentos, comentarios, comité y ejecutar.
3. **Decidir** el paso que te toca: aprobar o completar, rechazar, devolver a una fase, pedir información (vuelve al
   cliente y **para el reloj**), saltar, poner en espera; en una puerta, vía rápida o a comité. Todo menos aprobar
   exige justificación.
4. **Reglas fijas**: quien pide no decide ningún paso; se puede impedir que quien estudió vote en el comité; desde la
   fase que bloquea la ficha, el cliente solo añade comentarios y anexos; los campos críticos guardan cada versión
   (el original del cliente nunca se pierde).
5. **Plazos**: cada fase tiene sus horas; se avisa al porcentaje de aviso y al vencer, y el escalado añade otro
   decisor.

### 31.3 Métricas

La cabecera de `/demand` muestra: total, abiertas, pendientes de información, estancadas, en riesgo, vías rápidas
con umbral superado (*bypass*), horas efectivas medias, pendientes para mí, y reparto por estado y por fase. Las
horas en «pendiente de información» no cuentan.

#### Consejos

- Empieza instalando una plantilla y adáptala: los grupos que crea nacen sin miembros y hay que rellenarlos.
- Si un tipo no aparece en el portal, revisa sus canales: decide quién puede crearlo.
- El portal interno, sin ningún tipo activo en su canal, manda las peticiones a la cartera.

#### Más detalle

[docs/FLUJO_DE_DEMANDA.md](docs/FLUJO_DE_DEMANDA.md): definición del flujo en JSON, decisiones, plantillas, modelo de
datos, API, GRC y pendientes.

---

## 32. Finanzas: facturación, gastos, rentabilidad y presupuestos

Todo lo económico vive en la categoría del menú **Clientes y finanzas**, salvo **Gastos**, que está en **Mi trabajo** porque cada persona registra los suyos. Las pantallas de esta sección (salvo Gastos y Subcontratistas) las abre la capacidad `finanzas.ver`, que por defecto tienen **Dirección** (`admin`) y **Project Manager** (`pm`). Ver [§42](#42-roles-y-capacidades).

Valores comunes a todo el módulo:

- **Moneda e impuestos.** La moneda de la empresa es `DEFAULT_CURRENCY` (por defecto `EUR`) y el IVA por defecto `DEFAULT_TAX_RATE` (21). Las monedas admitidas, `SUPPORTED_CURRENCIES`. Se cambian en Configuración › General y Config. dinámica (ver [§41](#41-configuración-mapa-de-secciones)).
- **Tipos de cambio.** Las cifras en otra moneda se convierten con el tipo de su fecha. Si falta un tipo, la pantalla lo dice y esa cifra no se suma (no se convierte 1:1 en silencio).
- **Numeración.** Facturas, contratos, oportunidades y órdenes de trabajo se numeran con la secuencia de la empresa: Configuración › **Numeración** (`/settings/numbering`).
- **Datos del emisor.** Razón social, NIF, domicilio fiscal e IBAN que salen en la factura: ajustes `INVOICE_ISSUER_NAME`, `INVOICE_ISSUER_TAX_ID`, `INVOICE_ISSUER_ADDRESS`, `INVOICE_ISSUER_IBAN`.

### 32.1 Panel financiero

**Qué es.** Resumen en una página: ingresos, costes, margen, clientes activos, pipeline, facturas pendientes, coste por hora y tipos de cambio. Es el panel de la categoría: al pulsar «Clientes y finanzas» en el menú se abre aquí (`/finance-dashboard`).

**Para quién.** `finanzas.ver` (Dirección y PM). Las tarjetas de coste por hora solo las ven Dirección y RRHH (`costes.ver`); añadir un tipo de cambio, solo Dirección.

**Cómo se usa.**

1. Elige el periodo (por defecto, 90 días).
2. Lee las tarjetas. Clientes, pipeline y facturas pendientes son cifras **de hoy**, no del periodo; la tarjeta lo indica.
3. En **Tipos de cambio** puedes añadir uno (moneda origen, moneda destino y tipo).

**Consejos.** Si quieres que los tipos se descarguen solos del BCE cada día, activa `EXCHANGE_RATES_AUTO_UPDATE` (Config. dinámica). El color del margen sigue los umbrales de semáforo de la empresa (ver [§33.9](#339-umbrales-de-semáforo)).

### 32.2 Facturación (`/invoices`)

**Qué es.** Crear facturas a partir de las horas aprobadas y facturables, seguir su estado, descargar el PDF y enviarlas a la contabilidad (Xero o QuickBooks).

**Para quién.** La pantalla, `finanzas.ver`. La API de facturas la usan los responsables (`facturacion.gestionar`: Dirección, PM, jefe de equipo y RRHH); editar o borrar un borrador, Dirección o PM.

**Cómo se usa.**

1. **Nueva factura.** Elige proyecto y cliente, fechas de emisión y vencimiento, IVA (propone el de la empresa), referencia del pedido del cliente (PO) y periodo.
2. Pulsa **Generar líneas**. Se crean líneas con las imputaciones del periodo que son facturables, están aprobadas y no se han facturado todavía. La tarifa sale de las tablas de tarifas (ver [§32.8](#328-tarifas-estructura-de-coste-y-subcontratistas)), si no de la tarifa del proyecto y, si no, de la de la persona.
3. Guarda. La factura nace en **borrador** y sus horas quedan marcadas como facturadas.
4. Abre la factura (su número). Un borrador se puede **Editar** (cabecera y líneas: cantidad, unidad, precio, descuento) y **Borrar borrador** (sus horas vuelven a quedar libres). Los totales los calcula el servidor al guardar.
5. Cambia el estado: **Enviar** (borrador → enviada) y **Marcar como pagada** (enviada → pagada). Desde la ficha también se puede **Anular**.
6. **Descargar PDF** desde la fila o la ficha.
7. **Sincronización contable**: elige Xero o QuickBooks y envía en lote las facturas enviadas (hasta 100 por vez).

| Estado | Puede pasar a |
|---|---|
| Borrador | Enviada, Anulada |
| Enviada | Pagada, Vencida, Anulada |
| Vencida | Pagada, Anulada |

**Facturas que se crean solas.** Los proyectos con iguala mensual (`recurring_retainer`) generan su factura mensual en borrador el día configurado (tarea diaria del worker).

**Cobro con Stripe.** Si la empresa configura Stripe (`STRIPE_*`), la API puede crear un enlace de pago para una factura y el webhook `POST /api/v1/invoices/stripe/webhook` la marca como pagada al completarse el cobro (exige `STRIPE_WEBHOOK_SECRET` y la firma de Stripe). En la pantalla **no hay botón** de enlace de pago: se usa por API.

**Consejos.**

- Una factura emitida **no se modifica**: se anula y se hace otra. Al anular o borrar, sus horas y sus hitos vuelven a estar disponibles para facturar.
- Nada marca una factura como «vencida» por sí solo: el panel calcula las vencidas al vuelo y las pinta en rojo. La automatización `invoice_overdue` sirve para avisar (ver [§35](#35-automatizaciones)).
- Los totales de arriba suman cada factura convertida a la moneda de la empresa; si falta un tipo de cambio, la pantalla avisa y la deja fuera.
- Xero y QuickBooks necesitan su integración activa (Configuración › Credenciales de integraciones). La sincronización depende del servicio externo: no se ha probado contra cuentas reales.

### 32.3 Facturación por hito (`/milestone-billing`)

**Qué es.** Flujo de hitos de un proyecto: hito → completado → aprobado → factura en borrador.

**Para quién.** `finanzas.ver`.

**Cómo se usa.**

1. Elige el proyecto y crea un hito: nombre, fecha y **importe** o **porcentaje** (del total de los contratos del proyecto o, sin contratos, de su presupuesto).
2. **Completar** (y **Deshacer** si te equivocas) → **Solicitar aprobación** → **Aprobar** o **Rechazar** (con motivo).
3. **Generar factura**: crea una factura en borrador con una línea, que se gestiona en Facturación.

**Consejos.** Quien pide la aprobación de un hito no puede aprobarla ni rechazarla (segregación de funciones). Completar un hito reconoce ingresos si el contrato de ingresos usa el método «por hito». Desde Rentabilidad también se editan hitos, pero se facturan siempre aquí.

### 32.4 Gastos (`/expenses`)

**Qué es.** Registrar gastos contra proyectos con sus justificantes, repartirlos entre proyectos, aplicar las políticas de gastos de la empresa y llevarlos a aprobación y reembolso.

**Para quién.** Cada persona interna, sus propios gastos (`gastos.ver`). Las pestañas de pendientes y equipo, Dirección, PM y RRHH (`gastos.gestionar`); la API de revisión y reembolso admite también al jefe de equipo. Ver justificantes, reparto y vista previa de políticas de los gastos de otros: `EXPENSE_MANAGER_ROLES` (por defecto `admin,pm`).

**Cómo se usa.**

1. **Mis gastos → Nuevo.** Categoría (catálogo de la empresa, editable en Configuración › Catálogos), descripción, importe, moneda, fecha, facturable, país y ciudad, asistentes (comidas), viaje y notas.
   - **Kilometraje.** En lugar del importe, indica los **kilómetros**: el servidor calcula km × tarifa del país (y ciudad) de la tabla de referencia de uso «tarifa de kilometraje» (Políticas › Tablas de referencia) o, sin tabla, `EXPENSE_MILEAGE_RATE` (0,26 por defecto). El importe no se teclea.
   - **Subir justificante** lee la imagen o el PDF con IA (OCR) y rellena importe, moneda, comercio, fecha y categoría. Necesita un proveedor de IA (ver [§38](#38-inteligencia-artificial)); sin él, rellénalo a mano.
2. **Detalle del gasto** (pulsa su descripción): justificantes (varios, con su **tipo de documento**), **reparto entre proyectos** por porcentaje (debe sumar 100 %) y **Políticas**: qué pasará al enviarlo o, ya enviado, por qué pasó.
3. **Enviar.** Antes de guardar, una confirmación enseña qué políticas aplican: quién aprobará (los pasos del flujo más los niveles que añade cada exceso), cuánto se excede cada límite, avisos y documentos exigidos. Si una política bloquea o falta un requisito, no se puede confirmar.
4. El responsable **aprueba o rechaza** (con motivo) y después **marca como reembolsado**.

| Estado | Acción | Pasa a | Quién |
|---|---|---|---|
| Borrador | Enviar | Enviado | dueño |
| Enviado | Retirar | Borrador | dueño |
| Enviado | Aprobar / Rechazar | Aprobado / Rechazado | responsable |
| Rechazado | Editar | Borrador | dueño |
| Aprobado | Marcar reembolsado | Reembolsado | responsable |

**Políticas de gastos.** Son políticas del motor común, dominio «Gastos», en Configuración › **Políticas y reglas** (ver [§36.3](#363-motor-de-políticas-y-reglas-settingspolicies)). Pueden mirar país, ciudad, categoría, importe (convertido), importe por asistente, total del día o del viaje, kilómetros, fin de semana, festivo, proyecto, cliente, rol, departamento, equipo y grado de quien gasta. Un exceso **no bloquea por sí solo**: pide más niveles de aprobación, avisa, exige un documento o una justificación, informa a alguien o bloquea solo si la política lo dice. **Cargar ejemplos** crea políticas y tablas de muestra en borrador; nada aplica hasta publicarlas.

**Consejos.**

- **Nadie aprueba ni reembolsa su propio gasto** (segregación de funciones); el servidor responde 403.
- Si una política añadió niveles, el gasto se decide en la **bandeja de Aprobaciones**, no en la pantalla de Gastos (aquí respondería 409).
- Al aprobar se comprueba el presupuesto: con `BUDGET_CONTROL_POLICY = bloquear` un gasto que supera lo disponible no se aprueba (ver [§32.7](#327-presupuestos-budgets)).
- Un gasto facturable solo se admite en proyectos activos o en planificación.
- **Exportar** lista los gastos en Excel.

### 32.5 Rentabilidad (`/profitability`)

**Qué es.** Margen y valor ganado por proyecto: ingresos, coste, CPI/SPI, coste al terminar y una bandera de riesgo.

**Para quién.** `finanzas.ver`.

**Cómo se usa.**

1. Filtra la cartera por estado y abre un proyecto.
2. Lee las cifras:
   - **Ingresos** = tarifa × horas facturables (con tablas de tarifas, la tarifa de cada imputación). En precio cerrado sin tarifa, la suma de los hitos facturados.
   - **Coste** = personal (coste de las imputaciones) + gastos del proyecto (aprobados o reembolsados, su parte del reparto) + horas de subcontratistas, todo en la moneda de la empresa. La ficha enseña las tres partes.
   - CPI, SPI, EAC, margen al terminar y bandera de riesgo (crítico, aviso, bien).
3. Gestiona hitos desde el detalle; para facturarlos, **Facturar en Hitos** abre [Facturación por hito](#323-facturación-por-hito-milestone-billing).

**Consejos.** El CPI/SPI de esta pantalla se calcula sobre el periodo elegido y puede diferir del de EVM ([§33.6](#336-evm-cartera-burnup-flujo-acumulado-y-riesgo)). Los umbrales del semáforo son los de la empresa.

### 32.6 Reconocimiento de ingresos (`/revenue`)

**Qué es.** Ingresos reconocidos y diferidos según ASC 606 / IFRS 15, por contrato de ingresos y obligaciones de desempeño.

**Para quién.** `finanzas.ver`.

**Cómo se usa.** Tres pestañas: **Contratos ASC 606**, **Entradas contables** y una ayuda.

1. Crea un contrato de ingresos para un proyecto (valor y método) y añádele obligaciones. Métodos:

   | Método | Cómo reconoce |
   |---|---|
   | `over_time` (tiempo y materiales) y `consumption` (bolsa de horas) | horas aprobadas × tarifa |
   | `straight_line` | 1/N cada mes de la duración |
   | `milestone` | al completar los hitos enlazados |
   | `percentage_complete` | valor × tareas hechas / tareas |
   | `completed_contract` | todo el resto el mes en que cierra el proyecto |

2. **Ejecutar mes** reconoce el último mes terminado del año elegido. Además, una tarea del worker lo hace sola el día 1 de cada mes (sin repetir lo ya reconocido).
3. **Cerrar** o **reabrir** periodos: un periodo cerrado no se toca.
4. **Revertir** una entrada (no se deshace).

**Consejos.** Sin tarifa, los métodos por horas no reconocen nada (queda un aviso en el registro). Convertir una oportunidad del pipeline en proyecto crea su contrato de ingresos. Las entradas contables se listan pero **no se exportan** todavía. Este contrato no es el de la pantalla Contratos: son tablas distintas.

### 32.7 Presupuestos (`/budgets`)

**Qué es.** El presupuesto es la base económica de proyectos, departamentos y áreas: se prepara por partidas, se aprueba, y luego se sigue mes a mes contra el real, con comprometido, cierres, previsión y traspasos.

**Para quién.** La pantalla, `finanzas.ver`. Crear y editar: `BUDGET_MANAGER_ROLES` (por defecto `admin,pm,hr`). Aprobar sin flujo, abrir y cerrar campañas, reabrir un mes cerrado: `BUDGET_APPROVER_ROLES` (por defecto `admin`).

**Cómo se usa (preparar).**

1. **Nuevo presupuesto** (pestañas **Presupuestos · Campañas · Plantillas**): nombre, ámbito (proyecto, proyecto previsto, departamento o área), periodo, moneda, inflación anual, responsable y campaña. Puede partir de vacío, de una **plantilla** o de **otro presupuesto** (su plan o su real, con un ajuste %).
2. **Partidas**: cada una es un coste o un ingreso, calculado por importe, unidades × precio (con recurrencia), persona por coste cargado, horas × coste/hora o vacante. Un coste puede ser CAPEX con vida útil. Las partidas por encima de `BUDGET_JUSTIFICATION_MIN_AMOUNT` piden justificación.
3. **Estructura**: área > departamento > proyecto. Un área o departamento puede fijar un **techo** para sus hijos; con `BUDGET_CEILING_POLICY = bloquear`, un hijo que lo supera no se envía.
4. **Enviar a aprobación**. Con un flujo de aprobación de tipo `budget`, la decisión se toma en la bandeja de Aprobaciones; sin flujo, la toman `BUDGET_APPROVER_ROLES` en el propio presupuesto.
5. **Escenarios y versiones**: **Nueva versión** (reprevisión) y escenarios (optimista, pesimista…) con sus supuestos; **Comparar** dos versiones o escenarios.
6. **Supuestos**: inflación y notas; al cambiarlos se recalculan las partidas calculadas.

**Cómo se usa (seguir un presupuesto aprobado).** Aparecen tres pestañas más:

- **Control**: por tipo de partida, plan, real, comprometido, **disponible** (plan − real − comprometido), previsión al terminar y una barra de consumo. La previsión puede ser «según plan», «al ritmo real» o manual.
- **Cierre y detalle**: cierre mensual (congela el real del mes). Las desviaciones de al menos `BUDGET_VARIANCE_EXPLAIN_PCT` % y `BUDGET_VARIANCE_EXPLAIN_MIN_AMOUNT` exigen explicación antes de cerrar. Detalle de cada imputación, gasto y pedido que compone el real, y **CSV**.
- **Pedidos y traspasos**: pedidos (comprometido hasta que se facturan), **traspasos** entre partidas y **ampliaciones**. Con un flujo de tipo `budget_transfer` se aprueban en la bandeja; quien los pide no los aprueba.

El real se calcula solo, nunca se teclea: coste de las imputaciones, horas de subcontratistas, gastos aprobados o reembolsados y, como ingreso, las facturas emitidas del proyecto. El comprometido suma los pedidos y los contratos y licencias de ALM del ámbito.

**Cuadro de control** (pestaña de la página): una fila por presupuesto del año, con semáforo: rojo si consume el 100 % o la previsión supera el plan; ámbar desde el 85 %, con meses sin cerrar o desviaciones sin explicar; verde el resto.

**Consejos.**

- **El presupuesto aprobado manda**: al aprobar uno de proyecto, el presupuesto y las horas del proyecto pasan a ser los suyos, y eso es lo que usan EVM, rentabilidad y salud.
- **Control al gastar** (`BUDGET_CONTROL_POLICY`): `avisar` (por defecto) aprueba y avisa; `bloquear` responde 409; `no` no comprueba.
- Las campañas avisan cada día a los responsables con presupuestos en borrador cuando faltan `BUDGET_CAMPAIGN_REMINDER_DAYS` días o menos.
- Las alertas `budget_exceeded`, `budget_critical` y `budget_forecast_overrun` usan los umbrales de Configuración › **Alertas**.
- Todos los ajustes `BUDGET_*` están en Config. dinámica, grupo «presupuestos» (lista completa en `docs/REFERENCIA_DE_AJUSTES.md`).

### 32.8 Tarifas, estructura de coste y subcontratistas

**Tarifas** (Configuración › Finanzas › **Tarifas**, `/settings/rates`; capacidad `tarifas.config`, Dirección y PM). Tablas de tarifa de venta y de coste por perfil, con subida anual y fechas de validez. Se crean tablas, se añaden entradas (perfil, tarifa de venta, tarifa de coste, subida %, desde, hasta), se duplican y se borran. Se aplican en las líneas de factura generadas desde horas, en los ingresos de Rentabilidad y en el reconocimiento de ingresos por horas. El perfil de cada imputación es el puesto de la persona; orden de búsqueda: excepción de proyecto, excepción de cliente, tabla del cliente, tabla por defecto, tarifa del proyecto y tarifa de la persona. Las excepciones por cliente o proyecto no tienen pantalla (solo API).

**Estructura de coste** (Configuración › Finanzas › **Estructura de coste**, `/settings/user-costs`; `costes.config`, Dirección y RRHH). Perfiles de coste de cada persona con fecha de validez y costes de empresa por país. Los usan los presupuestos (partidas de persona y vacantes) y el coste por hora.

**Subcontratistas** (`/subcontractors`; `proveedores.ver`, gestores). Ficha de cada proveedor externo con sus personas, asignaciones a proyectos, horas y facturas recibidas (recibida → aprobada → pagada). El coste de sus horas cuenta en Rentabilidad, en el AC de EVM y en el real de los presupuestos. El detalle completo de proveedores, contratos y portal del proveedor está en [§30](#30-proveedores-y-portal-de-proveedores).

### 32.9 Escenarios what-if (`/scenarios`)

**Qué es.** Comprueba si la capacidad del equipo absorbe un conjunto de proyectos hipotéticos. Pese a estar en finanzas, es un modelo de **capacidad**, no económico.

**Para quién.** `finanzas.ver`.

**Cómo se usa.**

1. Crea un escenario: nombre, horizonte en semanas (12 por defecto) y proyectos (nombre, inicio, fin, horas totales).
2. **Calcular**: demanda total, capacidad semanal, pico y media de utilización y semanas sobrecargadas.

**Consejos.** La capacidad suma las horas semanales de las personas activas de los roles de `SCENARIO_CAPACITY_ROLES` (`DEFAULT_WEEKLY_CAPACITY_HOURS`, 40, si la persona no tiene las suyas). **No descuenta ausencias.** La demanda suma las reservas firmes del equipo en el horizonte.

**Más detalle.** Clientes, pipeline y contratos: [§27](#27-clientes-crm-y-pipeline) y `docs/PIPELINE_COMERCIAL.md`. Clientes internos (showback y chargeback): [§28](#28-clientes-internos) y `docs/CLIENTES_INTERNOS.md`. Flujos de aprobación de gastos, facturas y presupuestos: [§36](#36-aprobaciones).

---

## 33. BI y analítica

La categoría **Analítica y BI** reúne los cuadros e informes. Al pulsar la categoría se abre el **Panel ejecutivo** (`/executive`). Casi todas las pantallas piden `analitica.ver` (Dirección y PM); las excepciones se indican en cada una.

**Qué es IA y qué no aquí.** La narrativa del panel y «Preguntar a los datos» usan un modelo de lenguaje; las predicciones, anomalías y riesgo ML son estadística o aprendizaje automático local; alertas, Oracle y semáforos son reglas. Detalle en [§38.1](#381-qué-es-ia-real-y-qué-funciona-sin-ia).

**Almacén analítico.** Varias vistas leen un almacén DuckDB (`DUCKDB_PATH`) que se recarga cada noche (tarea `olap_nightly_etl`, 01:00). Hasta la primera carga, «Preguntar a los datos» falla; los KPI caen a la base de datos principal. El Explorador de datos enseña cuándo se cargó por última vez.

**Periodos libres.** Los informes que lo admiten tienen un selector de periodo común: accesos rápidos (hoy, 24 h, 7, 30 y 90 días, mes, trimestre, año) o un rango libre, con granularidad automática (hora, día, semana, mes) y comparación con el periodo anterior. Las fechas se pintan en la zona horaria del navegador.

### 33.1 Panel ejecutivo (`/executive`)

**Qué es.** Una página para la dirección: tarjetas de KPI, una narrativa escrita por IA, preguntas en lenguaje natural y la tabla de estado de los proyectos.

**Cómo se usa.**

1. Lee las tarjetas: **coste del mes**, **horas del mes** (con % facturable), **margen medio** de los proyectos activos, **pipeline ponderado** y **proyectos activos** (con los de riesgo alto).
2. Despliega la narrativa; el icono de refresco la regenera.
3. Escribe una pregunta en «Preguntar a los datos» o abre las preguntas de ejemplo. El resultado tiene un interruptor para ver el SQL.
4. Baja a la tabla de proyectos (estado, riesgo, presupuesto consumido, progreso).

**Consejos.** No hay KPI de ingresos aquí: están en el [Panel financiero](#321-panel-financiero). Sin proveedor de IA, la narrativa se escribe con una plantilla a partir de los KPI.

### 33.2 Explorador de datos (`/data-explorer`)

**Qué es.** Exploración libre: preguntar a los datos en lenguaje natural y dos constructores de consultas.

**Cómo se usa.**

- **Preguntar a los datos.** Escribe la pregunta. La IA genera una consulta de solo lectura, el servidor la valida (solo `SELECT`, tablas permitidas, filtro de empresa, máximo 200 filas) y la ejecuta. La respuesta dice si **responde a lo preguntado** (periodo, desglose, ranking, unidades) o si quedó sin comprobar. Si un filtro no encuentra nada, enseña los valores que sí existen y puede reintentar con ellos.
- **Banco de preguntas validadas.** Dirección o PM pueden marcar una respuesta como correcta: la misma pregunta reutiliza la consulta sin llamar a la IA, y las parecidas la usan de ejemplo.
- **Conversación (23-11-2026).** Las preguntas se encadenan: después de «¿cuántas horas imputó el equipo en septiembre?» basta «¿y en octubre?». El modelo recibe las últimas `ASK_DATA_CONTEXT_TURNS` preguntas de la conversación con su consulta (4; 0 la apaga). Debajo de la pregunta: cuántas lleva la conversación, **Nueva conversación**, **Retomar** una anterior, **Borrar conversación** y **Borrar todas**. Cada persona ve solo las suyas en su empresa. Se guarda la pregunta, la consulta, el número de filas y el error, **nunca las filas**. Retención: tipo `ask_data_conversations` (desde la última pregunta), bloqueable por conversación o persona; la supresión RGPD de la persona las borra; cada borrado se audita sin el texto. Una pregunta de seguimiento no reutiliza la validada idéntica (depende del contexto). API: `POST /analytics/ask` con `conversation_id`; `GET /analytics/ask/conversations[/{id}]`, `DELETE /analytics/ask/conversations[/{id}]` (`analitica.usar`).
- **Constructor visual de consultas**: entidad, columnas, filtros, orden, **Previsualizar** y **Guardar** como plantilla.
- **Constructor de consultas BI**: conjunto de datos, campos, filtros, agrupación y agregados, **Ejecutar** o **Guardar**.

**Consejos.** «Preguntar a los datos» necesita proveedor de IA y el almacén cargado. Los totales agrupados leen hasta `BI_EXPLORER_MAX_ROWS` filas (100 000) y avisan si el resultado es parcial. Con contecintelligence conectado, la respuesta ofrece llevar la pregunta a **Preguntar a la empresa** (`/ask-company`).

### 33.3 Informes y constructor de informes

**Informes** (`/reports`; cualquier persona interna, `colaboracion.ver`). Catálogo de métricas y explorador de gráficos.

1. **Métricas**: navega por categoría y abre una en el **Explorador**.
2. **Explorador**: métrica, periodo, tipo de gráfico (diez), filtros por proyecto, persona, departamento o top N. **Guardar**, **CSV** o **PNG**. Compara con el periodo anterior.
3. **Plantillas**: informes predefinidos. **Guardados**: los tuyos (se guardan en el servidor y te siguen a otro equipo).
4. **Programados** (solo responsables, `informes.programar`): nombre, métrica, frecuencia (diaria, semanal, mensual), destinatarios y «adjuntar PDF». Cada fila: **Pausar/Activar**, **Enviar ahora**, **PDF** y borrar. Se envían por correo; sin SMTP configurado el envío falla y lo dice.

**Constructor de informes** (`/report-builder`; `analitica.ver`). Informes tabulares sobre unas 20 entidades (proyectos, tareas, imputaciones, gastos, tickets, oportunidades, contratos, riesgos, ausencias, clientes, subcontratistas…).

1. Elige la entidad, marca columnas (ninguna = todas), añade filtros y el orden.
2. **Previsualizar** y **Exportar CSV** (hasta `REPORT_EXPORT_MAX_ROWS`, 100 000 filas; avisa si el fichero es parcial).
3. **Guardar plantilla** para reutilizarlo.

**Consejos.** Las máscaras de datos de Gobierno del dato se aplican en el constructor, el explorador y el CSV. Los informes del constructor no se programan; para un resumen semanal por correo usa un informe programado. La pestaña de presets BI del constructor apunta a tablas que no existen y no devuelve datos (pendiente).

### 33.4 Predicciones (`/predictions`)

**Qué es.** Previsión estadística de métricas, detección de anomalías, una calculadora de abandono (churn) y reglas de envío condicional de informes. **No usa modelos de lenguaje.**

**Cómo se usa.**

- **Previsión**: métrica, método (tendencia lineal, Holt, ARIMA, Prophet), periodos (1-24) y **Calcular**. Se dibujan bandas de confianza.
- **Anomalías**: elige la métrica y **Detectar** (IsolationForest o, sin la librería, z-score).
- **Predicción de churn**: escribe las siete cifras del cliente y **Predecir**. No lee datos de la base: usa lo que tecleas.
- **Envío condicional de informes**: nombre, informe, umbral % y destinatarios.

**Consejos.** Prophet y ARIMA necesitan las dependencias de `requirements-ml.txt`; sin ellas el cálculo cae a Holt. El envío condicional **guarda reglas pero ningún proceso las envía** todavía. La imagen Docker no incluye las librerías de ML opcionales.

### 33.5 Alertas (`/alerts`)

**Qué es.** Alertas operativas de un motor de reglas, más alertas «inteligentes» sobre métricas de BI. Sin IA.

**Para quién.** `alertas.ver` (Dirección, PM y RRHH). Ejecutar el motor a mano, Dirección.

**Cómo se usa.**

- **Operativas**: cada alerta tiene **Ver origen**, marcar como leída y **Resolver**. El motor corre cada día a las 08:00 (`NOTIFICATIONS_ALERTS_TIME`).

  | Regla | Salta cuando |
  |---|---|
  | Sobrecarga | la carga semanal supera el umbral de capacidad |
  | Presupuesto (aviso / crítico / previsión) | el coste o la previsión llega al % del presupuesto |
  | Tarea bloqueada | lleva bloqueada más de N días |
  | Sin imputar | una persona lleva N días sin imputar |
  | Riesgo de plazo | un proyecto activo vence en N días |

- **Inteligentes**: crea reglas sobre una métrica (umbral, tendencia, anomalía) y pulsa **Evaluar ahora**. Revisa el historial y reconoce entradas.

**Consejos.** Cada alerta se activa, se le pone umbral y gravedad en Configuración › **Alertas** (`/settings/alert-config`). Las alertas inteligentes **solo se evalúan al pulsar** «Evaluar ahora». El motor crea las alertas en la aplicación; no manda correo.

### 33.6 EVM, cartera, burnup, flujo acumulado y riesgo

**EVM — Valor ganado** (`/evm`). Cuatro tarjetas (proyectos activos y en riesgo, CPI y SPI medios, presupuesto y gastado) y una tabla por proyecto (% hecho, BAC, EV, AC, CPI, SPI, EAC). Al pulsar una fila, el detalle: PV, CV, SV, ETC, VAC, TCPI. El PV usa la **línea base vigente** del plan. Semáforo con `EVM_INDEX_GREEN_MIN` y `EVM_INDEX_RED_BELOW` (0,90 / 0,85).

**Cartera de proyectos** (`/portfolio`). Agrupa proyectos en carteras con presupuesto y fechas. **Ver dashboard**: presupuesto y gastado, en riesgo, en control, y una tabla con RAG, CPI, SPI y próximo hito. Se refresca cada minuto. No prioriza ni puntúa (eso es la entrada a la cartera, [§20](#20-proyectos-y-planificación)).

**Burnup y velocidad** (`/sprint-charts`). Elige el proyecto (velocidad: puntos planificados y completados por sprint) y un sprint (burnup: alcance, completado y objetivo). La velocidad es en puntos por semana. El alcance se muestra constante: no hay historial de cambios de alcance.

**Flujo acumulado** (`/cumulative-flow`). Diagrama de tareas por estado en el tiempo. Elige proyecto y periodo (7 a 90 días) y pulsa **Foto de hoy** para registrar el día. **Ningún proceso hace la foto solo**: el gráfico tiene solo los días en que alguien la tomó.

**Riesgo del proyecto** (`/risk-scores`). Dos vistas:

- **Riesgo basado en señales**: puntuación de 0 a 100 por proyecto (cronograma 40 %, presupuesto 30 %, alcance 15 %, recursos 15 %), niveles crítico ≥ 75, alto ≥ 50, medio ≥ 25. **Recalcular todo** la refresca. Es una heurística, no IA.
- **Predicciones ML**: modelo entrenado por empresa con sus proyectos terminados (al menos 5). **Entrenar ahora**, versiones del modelo e historial. Se reentrena el día 1 de cada mes.

Los pesos y niveles se ajustan en Config. dinámica, grupo «Riesgo del proyecto». Un proyecto sin datos no cuenta como «riesgo bajo»: se informa aparte.

**Análisis de un proyecto** (`/projects/:id/analytics`), desde la ficha del proyecto.

### 33.7 Exportación de datos y Exportar Excel

**Exportación de datos** (`/exports`; `exportar.ver`: Dirección, PM y RRHH).

1. **Imputaciones**: desde, hasta, XLSX o CSV, **Descargar**. Dirección y RRHH exportan las de todos (`exportar.todo`); el resto, las suyas.
2. **Proyectos**: XLSX o CSV; «incluir costes» solo Dirección y RRHH, importes de proyecto solo Dirección.
3. **Jira**: elige proyecto y **Sincronizar** (importa incidencias como tareas).

**Botón Exportar Excel.** En la cabecera de casi todas las listas. Descarga lo que se ve en pantalla (la tabla visible) como fichero `.xls`. Ojo: es una tabla HTML con extensión `.xls`, Excel avisa del formato y solo incluye las filas visibles (no las de otras páginas). Para datos completos usa Exportación de datos, el CSV del Constructor de informes o la exportación de cada módulo.

### 33.8 Plataforma y gobierno de datos

**Plataforma de datos** (`/data-platform`; `datos.plataforma`, Dirección).

- **Conectores ETL**: conectores predefinidos (Salesforce, HubSpot, Jira, Stripe, Xero, Google Analytics…) y **Nueva fuente REST** para cualquier API JSON. **Configurar** (secretos cifrados, nunca se vuelven a mostrar), **Probar** (extrae sin guardar), **Activar** y **Sincronizar**; **Ver registro** con cada ejecución. Un trabajo horario sincroniza los activos. Algunos conectores necesitan instalar su SDK y la pantalla dice cuál.
- **Microsoft 365**: informes de uso y adopción (la configuración está en Configuración › Informes de Microsoft 365).
- **Informes predefinidos**, **Tiempo real** (KPI en directo) y **Linaje y versiones**.

**Gobierno del dato** (`/data-governance`; Dirección). Solicitudes RGPD de BI (acceso, supresión, portabilidad), consentimientos, **máscaras** de campos (hash, ocultar, suprimir, seudonimizar), políticas, auditoría de accesos a BI (quién leyó qué y desde qué IP), linaje, clasificación de campos y **Ejecutar checks** de gobierno (almacén sin cargar o con más de 26 h, informes programados con error, sin programaciones activas). Incluye el panel de **colaboración en paneles**: comentarios, vistas compartidas, accesos, versiones y notificaciones.

**BI en Teams y SharePoint.** Una página de indicadores (ingresos, coste y horas del mes pasado, anomalías, previsión, proyectos en riesgo) se puede incrustar como pestaña de Teams o web part de SharePoint, con un token de incrustación revocable por cuadro y empresa. La configuran Dirección (API `/api/v1/m365/bi/*` y `/api/v1/bi/embed/*`); los dominios que pueden incrustarla, `BI_EMBED_FRAME_ANCESTORS` más los de la empresa. Ver [§9](#9-integraciones-y-pruebas-de-conexión).

**Consejos.** El RGPD de la plataforma (bloqueos legales, retención, supresión completa) está en [§15](#15-grc-auditoría-retención-rgpd-y-cumplimiento). La supresión sustituye las copias exactas del nombre o el correo; no reescribe menciones dentro de textos libres.

### 33.9 Umbrales de semáforo

Cada métrica con semáforo (verde, ámbar, rojo) tiene **una sola definición por empresa**, que usan igual el servidor, las pantallas y el portal. Se editan en Configuración › Config. dinámica › **Semáforos** (Dirección); riesgo, salud y EVM en sus grupos. Al guardar se valida el rango y el orden del par.

| Métrica | Aviso / crítico por defecto | Sentido |
|---|---|---|
| Presupuesto consumido | 70 % / 90 % | más es peor |
| Carga de una persona | 85 % / 100 % (infrautilizada < 50 %) | más es peor |
| Semana sobrecargada | 42 h | más es peor |
| Cumplimiento de SLA | 90 % / 75 % | menos es peor |
| Progreso de OKR | 60 % / 30 % | menos es peor |
| NPS | 50 / 0 | menos es peor |
| Margen | 50 % / 30 % | menos es peor |
| Sprint: completitud / velocidad | 80 / 50 %; 85 / 50 % | menos es peor |
| Días que faltan (contratos, licencias) | 30 / 14 días (horizonte 90) | menos es peor |
| Riesgo (0-100) | alto 50 / crítico 75 | más es peor |
| Salud de proyecto | 70 / 45 | menos es peor |
| Índices EVM (CPI/SPI) | 0,90 / 0,85 | menos es peor |

Los cambios de umbral quedan en el registro de cambios de ajustes (quién, cuándo, antes y después).

---

## 34. BPM: procesos

**Qué es.** Diseñar, publicar y ejecutar procesos de negocio en BPMN 2.0 (`/bpm`, menú **IA y automatización → BPM Procesos**). Guía completa: [docs/BPM.md](docs/BPM.md).

**Para quién.** Todo el personal interno usa los procesos y completa sus pasos (`bpm.usar`). Quien los diseña, publica y gobierna tiene `bpm.gestionar`. Cada empresa ve solo los suyos.

**Cómo se usa.**

1. **Modelar.** Editor gráfico con panel de propiedades, o importa un `.bpmn` (sin DTD ni entidades: sin XXE). Tareas de usuario y de servicio, compuertas exclusivas, inclusivas y paralelas, subprocesos, llamadas a otros procesos, temporizadores, mensajes, errores y eventos de borde.
2. **Asignar y fijar plazos.** A una persona, a quien inició, a roles, a grupos de aprobación o a colas; plazo por tarea con aviso y escalado; formularios tipados; variables con tipo y marca de dato personal.
3. **Versionar.** Borrador → publicada → retirada. Solo se publica lo ejecutable; las instancias en curso siguen en su versión (con migración opcional). **Probar** simula sin escribir nada.
4. **Ejecutar.** Bandeja (también en **Bandeja de entrada** `/inbox`, pestaña **Procesos**), instancias con su diagrama e historial; suspender, reanudar, cancelar, reasignar y reintentar. Mensajes por API con clave de negocio.

**Tareas automáticas.** Lista cerrada, sin código: ticket, cambio, demanda, aprobación, políticas, aviso y variables, con reintentos e incidentes.

**Métricas.** Duración (media, p50, p90), cuellos de botella, instancias atascadas y fuera de plazo.

**GRC.** Auditoría de cada acción; retención y bloqueo legal (tipo `bpmn_instances`); RGPD (copia y supresión de las variables marcadas como personales); segregación de funciones opcional (`BPMN_SEGREGACION_DE_FUNCIONES`: quien diseña o publica una versión no aprueba en sus instancias). Ver [15](#15-grc-auditoría-retención-rgpd-y-cumplimiento).

**Ajustes** (Configuración → Config. dinámica → Automatizaciones, por empresa): `BPMN_MAX_AUTOMATIC_STEPS` (500), `BPMN_MAX_XML_BYTES` (2.000.000), `BPMN_MAX_VARIABLES_BYTES` (65.536), `BPMN_SERVICE_RETRIES` (3), `BPMN_STUCK_HOURS` (72) y `BPMN_SEGREGACION_DE_FUNCIONES` (apagado). Migración `204_bpm`.

**Consejo.** Para reacciones automáticas a eventos (crear tareas, avisar, cambiar estados) usa [Automatizaciones](#35-automatizaciones); el BPM ordena el trabajo de las personas de principio a fin.

---

## 35. Automatizaciones

**Qué es.** Reglas «si pasa esto (disparador), y se cumple esto (condiciones), entonces haz esto (acciones)» que corren solas dentro de la empresa. Pantalla **Automatizaciones** (`/automations`), en el menú **IA y Automatización**. **No usan IA.**

**Para quién.** La pantalla, `ia.ver` (Dirección y PM). La API de reglas, los responsables (`automatizacion.gestionar`).

**Cómo se usa.**

1. Pulsa **Nueva regla**. Nombre, descripción y proyecto (vacío = todos los de la empresa).
2. Elige el **disparador**. Solo se ofrecen los que algo emite de verdad.
3. Opcional: **Añadir condición** (campo, operador, valor). Con dos o más, **Se cumplen todas** o **Basta con una**. Operadores: igual, distinto, mayor que, menor que, contiene. Una condición que no se puede evaluar cuenta como falsa.
4. Con el disparador **Programada**, aparece **Cuándo**: cinco campos (minuto, hora, día, mes, día de la semana) en la zona de la empresa, con plantillas (cada día a las 9:00, laborables a las 9:00, lunes a las 8:00, día 1 del mes, cada hora). La tarjeta enseña la próxima ejecución.
5. Añade una o más **acciones** (los parámetros obligatorios llevan `*`) y guarda.
6. En cada tarjeta: **Pausar/Activar**, **Probar** (simulación: dice qué haría cada acción, sin ejecutar nada), **Historial** (ejecuciones reales y el resultado de cada acción) y borrar.

**Ver plantillas** ofrece siete reglas de ejemplo listas para usar.

**Disparadores** (36):

| Área | Disparadores |
|---|---|
| Tareas | creada, cambio de estado, asignada, completada, bloqueada; vencida y fecha cercana (barrido periódico) |
| Proyectos | creado, cambio de estado, riesgo alto; umbral de presupuesto (barrido) |
| Sprints | iniciado, terminado |
| Horas y equipo | parte enviado, parte rechazado; parte no enviado (barrido, desde `AUTOMATIONS_TIMESHEET_WEEKDAY`); ausencia pedida, aprobada, rechazada |
| Service desk | ticket creado, resuelto, reabierto, escalado, SLA en riesgo, SLA incumplido |
| Finanzas y CRM | gasto enviado, aprobado, rechazado; cambio de etapa de oportunidad; factura enviada, pagada; factura vencida (barrido) |
| Aprobaciones | pedida, aprobada, rechazada |
| Calendario | programada (cron) |

**Acciones** (16): crear alerta; notificar a la persona del evento; notificar a un rol; enviar correo; llamar a un webhook (HTTPS, sirve para RPA: Power Automate, Zapier, Make, n8n, UiPath); mensaje a Slack o a Teams; cambiar estado o prioridad de la tarea; crear tarea; cambiar estado del proyecto; escalar ticket; cambiar estado del ticket; asignar (a una persona o al miembro de un rol con menos carga); actualizar un campo permitido (fechas admiten `+N`/`-N` días); abrir una aprobación sobre el registro del evento.

**Ejemplos.**

- «Si un ticket incumple el SLA, escálalo y avisa al rol PM».
- «Si una factura está vencida, manda un correo a administración».
- «Los lunes a las 8:00, crea una alerta de revisión semanal en el proyecto X».
- «Si un gasto supera 1 000 € (condición sobre el importe), abre una aprobación».

**Límites y comportamiento.**

- Las acciones corren **después** de guardar el cambio, en el worker: una regla nunca bloquea ni deshace el cambio que la disparó. El efecto llega en menos de un minuto.
- Los disparadores por barrido actúan **una vez por regla y elemento** (una tarea vencida avisa una vez por fecha de vencimiento).
- Una acción que falla queda registrada y las siguientes siguen. Correos, webhooks y mensajes no se pueden deshacer.
- Una acción puede disparar otra regla; la cadena se corta en `AUTOMATIONS_MAX_CHAIN_DEPTH` (3).
- Las reglas programadas tienen la precisión del barrido (`AUTOMATIONS_SCAN_MINUTES`, 15 min; solo entorno).

**Configuración** (Config. dinámica, grupo «Automatizaciones», por empresa): `AUTOMATIONS_ENABLED` (apagado: no corren, Probar sigue simulando), `AUTOMATIONS_MAX_CHAIN_DEPTH`, `AUTOMATIONS_DEADLINE_DAYS` (2), `AUTOMATIONS_TIMESHEET_WEEKDAY` (5 = viernes), `AUTOMATIONS_WEBHOOK_TIMEOUT_SECONDS` (10). El correo usa `SMTP_*`; Slack y Teams, la URL de la regla o la integración activa de la empresa.

**Consejos.** Prueba siempre con **Probar** antes de activar. Para procesos con varios pasos humanos usa BPM ([§34](#34-bpm-procesos)), no automatizaciones.

---

## 36. Aprobaciones

Contecflow tiene **un solo motor de aprobaciones** para gastos, partes de horas, ausencias, cambios de proyecto, facturas, presupuestos, traspasos de presupuesto, documentos y acciones de agentes externos (MCP). Las reglas de negocio (bloquear, pedir más niveles, avisar, exigir documentos) son **políticas**; el motor ejecuta los pasos que resultan.

### 36.1 Bandeja de aprobaciones (`/approvals`)

**Qué es.** Las solicitudes en las que te toca decidir el paso actual. También aparece dentro de la **Bandeja de entrada** (`/inbox`).

**Para quién.** Cualquier persona interna (`colaboracion.ver`): cualquiera puede ser aprobador.

**Cómo se usa.**

1. Filtra por tipo.
2. Abre una solicitud. Verás el resumen y, si viene de una política, el exceso, los niveles añadidos («paso añadido por política») y **Ver por qué**.
3. **Aprobar** o **Rechazar** con una nota (el rechazo pide motivo). Si el paso exige adjunto, súbelo.
4. Para varias a la vez, selecciónalas y apruébalas en bloque.
5. **Fuera de la oficina**: indica un delegado y las fechas. Mientras dure, tu delegado (de la misma empresa y activo) recibe y puede decidir tus aprobaciones.

**Aprobar por correo.** Cada aprobador recibe un correo con un enlace firmado para él y ese paso, válido `APPROVAL_EMAIL_LINK_HOURS` (72 h). Abre `/approvals/decide`, una página sin login con el resumen; la decisión se toma con un botón (abrir el enlace no decide nada, porque los antivirus de correo abren enlaces solos). Pasa las mismas comprobaciones que la bandeja. Si ya se decidió o el paso cambió, el enlace responde que ya no vale.

**Consejos.** **Nadie aprueba lo suyo** (segregación de funciones), sea cual sea el flujo. Los recordatorios y vencimientos los procesa una tarea cada hora.

### 36.2 Motor de aprobaciones

| Pieza | Qué hace |
|---|---|
| **Flujo** | Por tipo de entidad, con condiciones de uso (importe mayor o hasta, departamento, categoría, proyecto, excede una política). Se elige el flujo activo más específico que encaja; si no, el predeterminado. |
| **Paso** | Aprobador: persona, rol, responsable, N-ésimo responsable, cualquiera del departamento o **grupo**. Puede ser opcional, de **informar** (avisa y sigue) o con condición propia. Varios pasos con el mismo orden forman una etapa **en paralelo**. |
| **Quórum** | Un paso en paralelo avanza al alcanzar el número de aprobaciones exigido; no se vota dos veces. |
| **Auto-aprobación** | Reglas del flujo (importe, departamento, categoría) que aprueban al crear la solicitud, salvo que una política haya añadido niveles. |
| **Encadenamiento** | Al aprobarse, abre una solicitud en otro flujo. |
| **Vencimiento** | Cada paso tiene horas límite (72 por defecto) y una acción al vencer: escalar a una persona, auto-aprobar o rechazar. Antes avisa con recordatorios cada N horas. |
| **Delegación** | Un aprobador puede delegar su paso; queda registrado. |

Estados de una solicitud: **pendiente**, **aprobada**, **rechazada**, **cancelada**. Un rechazo la cierra; la decisión final se aplica a la entidad (el gasto pasa a aprobado, la ausencia se concede…).

Tipos que se abren y se aplican solos: documentos (por categoría), gastos, partes de horas, ausencias, cambios de proyecto, facturas, presupuestos, traspasos y acciones MCP. El diseñador ofrece otros tipos (hito, compra, contrato, entregable…), pero para esos la solicitud se crea a mano o por una automatización y aprobarla **no cambia nada** en la entidad.

### 36.3 Motor de políticas y reglas (`/settings/policies`)

**Qué es.** Configuración › Aprobaciones y políticas › **Políticas y reglas**. Un motor común de políticas: cada proceso registra un *dominio* (hoy **Gastos** y **Ausencias**). Una política dice a quién aplica, cuándo está en vigor y, regla a regla, qué pasa si se cumple una condición. Todo se edita en pantalla, sin JSON.

**Para quién.** Dirección (`org.administrar`).

**Cómo se usa.**

1. Pestaña **Políticas**: elige el dominio y **Nueva política**.
2. **Definición y ámbito**: nombre, prioridad, fechas y ámbito (departamentos, equipos, roles, ubicaciones, personas; vacío = toda la empresa).
3. **Reglas**: *Si se cumple* (árbol de grupos **Todas/Alguna** con condiciones del dominio) → *Entonces* (resultados) → opcional **bandas por exceso** sobre una referencia (valor fijo, otro campo o una **tabla de referencia** por país, ciudad y categoría), p. ej. «hasta 20 % → +1 nivel; más → +2».
4. **Resultados posibles**: permitir, auto-aprobar, avisar, exigir justificación, exigir adjunto, añadir aprobación (niveles o pasos concretos), notificar, bloquear, fijar un campo, etiquetar; y los propios del dominio (ausencias: cupo y lista de espera).
5. **Validar**, **Guardar borrador**, **Simulador** (reaplica la política a las últimas N entidades y enseña qué cambiaría frente a lo publicado, sin guardar ni avisar), **Publicar**, **Nueva versión**, **Versiones** y **Desactivar**.
6. **Tablas de referencia**: rejilla de valores por país, ciudad y categoría con moneda y vigencia; **Importar CSV/XLSX** solo rellena la rejilla para revisarla.
7. **Tipos de documento**: la lista de tipos de justificante de la empresa.

**Cómo se resuelven los conflictos.** Bloquear gana a todo. De los niveles pedidos, el **máximo** (no la suma). Requisitos, avisos y notificaciones se suman. Auto-aprobar solo si no hay nada más. Una condición que no se puede evaluar (p. ej., falta el tipo de cambio) no dispara la regla y añade un aviso: falla hacia la revisión humana, nunca hacia aprobar o bloquear.

**Consejos.** Carga los ejemplos del dominio (**Cargar ejemplos**) para partir de algo realista; quedan en borrador. Usa el simulador antes de publicar.

### 36.4 Configuración de flujos (`/settings/approval-workflows`)

**Qué es.** Configuración › Aprobaciones y políticas › **Flujos de aprobación**. Para Dirección (`org.administrar`).

**Pestañas.**

| Pestaña | Para qué |
|---|---|
| **Flujos** | Crear un flujo: tipo de entidad, categoría (documentos), predeterminado, flujo encadenado, condiciones de uso y reglas de auto-aprobación (con controles, sin JSON). Añadir pasos. **Validar** y **Publicar**; **Clonar versión** para cambiar uno publicado. **Diseñar gráficamente** abre un lienzo con nodos de aprobar, informar, condición (ramas Sí/No), paralelo y fin; al guardar se compila en pasos. |
| **Plantillas** | Crear un flujo desde una plantilla. |
| **Simulador** | Qué flujo y qué ruta tomaría una solicitud (eliges al solicitante en el selector de personas). |
| **Cuellos de botella** | Tiempo medio, rechazo, pendientes y riesgo de SLA por paso, con recomendaciones. |
| **Grupos** | Grupos de aprobadores. |
| **Carga** | Pendientes y tiempo de respuesta por aprobador; marca sobrecargados. |
| **Matriz** | Qué flujo está activo para cada tipo de entidad. |

**Consejos.**

- Crea un flujo **predeterminado** por cada tipo que uses y flujos más específicos con condiciones para los casos especiales.
- Guardar un diagrama sustituye los pasos del flujo también para las solicitudes pendientes en él (el diseñador dice cuántas).
- Para que los agentes externos puedan escribir con aprobación humana, crea un flujo de tipo «Acción de agente externo (MCP)» (ver [§39](#39-mcp-agentes-de-código-externos)).
- El bloqueo por incumplimiento de SLA del flujo se guarda pero hoy no se aplica.

**Más detalle.** `docs/APPROVAL_ENGINE.md` (modelo, ciclo de vida y vencimientos). Ausencias gobernadas por reglas: [§22](#22-ausencias).

---

## 37. Colaboración: chat, llamadas y reuniones

### 37.1 Chat

**Qué es.** Chat interno al estilo Teams (`/chat`): espacios, equipos y canales, conversaciones directas y de grupo, hilos, reacciones, mensajes fijados y guardados, borradores, búsqueda, presencia, adjuntos, llamadas y comandos.

**Para quién.** Personal interno (`colaboracion.ver`). La administración del chat (retención, cumplimiento) es de administración: **Configuración › Seguridad y GRC › Administración del chat** (`/settings/chat-admin`).

**Cómo se usa.**

1. **Nueva conversación** (botón de la cabecera) crea un canal o un grupo; desde una persona se abre un mensaje directo.
2. Escribe `@` para mencionar (le llega a su bandeja, pestaña Menciones).
3. Adjunta ficheros con el clip. Pasan por la validación de subidas y el antivirus si está activo.
4. Menú de cada mensaje: reaccionar, editar, borrar, fijar, guardar o **enlazar** con una tarea, un ticket, un entregable o un riesgo.
5. **Traducir**: cada mensaje se puede ver traducido a tu idioma (si la empresa tiene la traducción activa), con «Ver original».
6. **Comandos**: un mensaje que empieza por `/` ejecuta una acción, por ejemplo `/task`, `/ticket`, `/imputar 30m`, `/risk`, `/decision`, `/poll Pregunta? | A | B`, `/standup`, `/meet`, `/recap`. La lista sale del propio chat.
7. **Buscar mensajes** desde la cabecera.

El panel flotante del chat (icono de la barra superior) permite leer y responder sin salir de la pantalla; **abrir completo** lleva a `/chat`.

### 37.2 Llamadas y videollamadas

- Los botones de teléfono y vídeo de una conversación inician una llamada y abren su ventana (`/chat/call/:callId`): micrófono, cámara, compartir pantalla, subtítulos, participantes y salir.
- Las llamadas usan **LiveKit**. Sin `LIVEKIT_URL`, `LIVEKIT_API_KEY` y `LIVEKIT_API_SECRET` configurados, fuera del entorno de desarrollo la llamada responde que la integración no está configurada. Ver [9. Integraciones](#9-integraciones-y-pruebas-de-conexión).
- **Subtítulos**: cada navegador transcribe su propio audio.
- **Asistente en la llamada**: el botón **Asistente** activa el asistente de reuniones (ver 37.3) tras un aviso de grabación obligatorio. Cada participante consiente o no en un aviso dentro de la llamada; de quien dice que no, no se guarda nada. Al colgar se genera el acta y se publica en la conversación un enlace a la reunión.

### 37.3 Asistente de reuniones

**Qué es.** Convierte una reunión en resumen, decisiones, riesgos, preguntas abiertas, acciones y transcripción con hablantes (`/meetings-ai`, «Asistente de reuniones»). Las acciones se pasan a tarea o ticket con un clic.

**Para quién.**

| Capacidad | Roles | Qué permite |
|---|---|---|
| `reuniones.usar` | personal interno | Grabar, invitar el bot, traer reuniones, ver **las suyas** |
| `reuniones.ver_todas` | administración | Ver y escuchar todas las de la empresa |
| `reuniones.config` | administración | Configuración y RGPD por persona |

Una reunión la ven quien la creó, sus participantes con usuario, los responsables de sus acciones, el PM del proyecto vinculado y `reuniones.ver_todas`. El resto no sabe que existe.

**Cuatro formas de traer una reunión.**

| Vía | Cómo |
|---|---|
| **Grabar** | Desde el navegador: micrófono o audio de una pestaña, en persona o con cualquier herramienta. Antes hay que confirmar el **aviso de grabación** (queda quién y cuándo). El audio se sube y transcribe por trozos de 30 s. |
| **Invitar el bot** | Pega la URL de la llamada (Teams, Zoom, Meet, Webex): el bot entra como participante, avisa en el chat de que graba y al terminar trae la transcripción con hablantes. Exige el contrato de encargo de tratamiento del proveedor y su clave. |
| **Traer de Teams, Zoom o Meet** | Una reunión ya terminada con transcripción en la plataforma (conectores configurados). También se pueden recoger automáticamente las tuyas activándolo en **Mis preferencias**. |
| **Pegar transcripción** | Texto ya escrito. |

Además, las llamadas del chat con **Asistente** activado (37.2).

**Cómo se usa.**

1. Trae la reunión por una de las vías. Estados: programada, bot en la sala, grabando, procesando, lista, error o **esperando consentimiento**.
2. Abre la reunión: selector de idioma (el resumen y la transcripción se traducen si la empresa tiene activado el canal de reuniones en Traducción), resumen, decisiones, riesgos, preguntas abiertas, acciones, transcripción con hablante y marca de tiempo, participantes, audio y acta.
3. En las acciones, ajusta responsable y fecha y crea la **tarea** o el **ticket**; o crea todas las tareas a la vez. **Acta** genera un documento vinculado al proyecto y cliente.
4. Renombra un hablante o asígnalo a una persona (la grabación propia no separa hablantes).
5. **Preguntar** a la IA sobre la reunión y **Buscar** en todas tus reuniones.
6. **Enviar a mi cuaderno** crea una página con todo ([19](#19-mi-cuaderno)).

La reunión se vincula sola al proyecto y al cliente cuando puede (evento de calendario, correos de los asistentes externos, código de proyecto en el título); nunca pisa lo que elijas tú.

**Consentimiento y privacidad.**

- La empresa puede **exigir consentimiento**: entonces una reunión con participantes sin «sí» no se analiza. Un «no» tacha lo que dijo esa persona antes de analizar.
- Retención separada: audio 7 días y transcripción 365 días por defecto; el resumen y las acciones se conservan. Las reuniones admiten bloqueo legal y entran en la copia y la supresión RGPD.
- Escuchar o descargar audio y transcripción queda auditado.
- Nada sale a terceros sin activarlo y sin contrato: cada conector nace apagado y la transcripción con un proveedor externo exige su contrato; sin él solo se usa whisper local.
- El bot viene activado por defecto y, también por defecto, «mandar el bot a mis reuniones del calendario» está activado para cada persona interna; pero sin contrato ni clave del proveedor no se envía nada. Cada persona lo puede desactivar en **Mis preferencias**.

**Configuración** (administración): **Configuración › IA e idiomas › Asistente de reuniones** (`/settings/reuniones`): consentimiento, retención, traducción, transcripción externa, Teams, Zoom, Meet y bot.

**Consejos.**

- Con la grabación propia, confirma el aviso a todos antes de empezar: sin él no graba.
- Para que una acción se asigne sola, el nombre dicho debe casar con un participante con usuario; si no, asígnala a mano.

**Más detalle.** [docs/ASISTENTE_DE_REUNIONES.md](docs/ASISTENTE_DE_REUNIONES.md).

---

## 38. Inteligencia artificial

La IA de contecflow es **opcional**: casi todo funciona sin ella. Cuando se usa, pasa siempre por una sola puerta (`call_ai`), así que la gobernanza, el tope de gasto diario y el registro de uso se aplican a todas las funciones.

### 38.1 Qué es IA real y qué funciona sin IA

| Función | Mecanismo | ¿Necesita proveedor de IA? | Sin proveedor |
|---|---|---|---|
| NexusAssist (panel y editor) | Modelo de lenguaje | Sí | Error claro; no se guarda nada |
| NexusAgent | Modelo con llamada a herramientas | Sí, y que admita herramientas (Ollama no) | Modo solo texto, que también necesita proveedor |
| Narrativa del Panel ejecutivo | Modelo de lenguaje | Opcional | Texto de plantilla con los KPI |
| Preguntar a los datos | El modelo escribe SQL | Sí | Error (salvo tres preguntas fijas) |
| OCR de justificantes de gasto | Modelo que lee imágenes/PDF | Sí | Se rellena a mano |
| Asignación por IA | Similitud de textos (embeddings o TF-IDF) | Solo para el desempate | Funciona |
| Riesgo ML, anomalías, previsión | Aprendizaje automático y estadística locales | No | Funciona |
| NexusOracle, alertas, semáforos, riesgo por señales | Reglas y umbrales | No | Funciona |
| Automatizaciones y BPM | Reglas | No | Funciona |

**Proveedores admitidos**: Anthropic, OpenAI, Gemini, DeepSeek, Groq, Mistral, Ollama (local) y Azure. Orden de elección: el proveedor pedido, el **predeterminado de la empresa** (Proveedores de IA), uno global, el del `.env` (`AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL`, `AI_BASE_URL`). Si el elegido falla, se prueban los demás activos por su orden de respaldo. Un proveedor que falla se aparta `AI_PROVIDER_ERROR_COOLDOWN_SECONDS` (300 s) y luego se reintenta.

### 38.2 NexusAssist: el asistente

**Qué es.** Un chat con los datos de tu empresa como contexto (lo que hay en pantalla, la base de conocimiento y tus últimos mensajes), y botones «mejorar este texto» en campos de tareas y tickets.

**Para quién.** Cualquier persona con sesión. El editor en línea, el personal interno.

**Cómo se usa.**

1. Abre el panel con **Cmd+I** (Mac) o **Ctrl+I** (Windows/Linux), o con el botón del asistente.
2. Escribe la pregunta. Las conversaciones anteriores se pueden reabrir o borrar.
3. **Editor en línea**: en la descripción de una tarea o un ticket, usa las acciones de IA (mejorar, resumir…). Tras un cambio aparece **Deshacer**.

**Consejos.** Lo que ve el asistente depende de tu rol: los datos financieros solo para Dirección y RRHH; los de toda la empresa, capacidad y personas, para los responsables; el resto, solo los proyectos en los que imputa o tiene tareas. Las políticas de entrada se aplican antes de guardar: se guarda el mensaje ya redactado. NexusAssist no ejecuta acciones.

### 38.3 NexusAgent: el agente, con aprobación humana

**Qué es.** Un agente (`/nexus-agent`) que cumple instrucciones llamando a herramientas de la aplicación: lee datos y puede **escribir** (crear o cambiar tareas, crear riesgos, cambiar el estado de proyectos y tickets, reasignar tickets, enviar notificaciones).

**Para quién.** `ia.ver` (Dirección y PM).

**Cómo se usa.**

1. Escribe una instrucción o elige un **ejemplo**. **Ctrl + Intro** para ejecutar.
2. Deja o quita la transmisión en vivo y pulsa **Ejecutar agente**.
3. **Permitir que cree o cambie datos** está **desmarcado** por defecto. Así, cada escritura que el agente propone queda **pendiente de aprobación humana**: aparece en «Pendientes de tu aprobación» y en el resultado, con los datos que se enviarán. **Aprobar y ejecutar** ejecuta exactamente esa herramienta con esos argumentos, con tus permisos, y queda auditado; **Rechazar** no hace nada.
4. El **historial** guarda cada ejecución con sus pasos.

**Consejos.**

- Cada herramienta exige la **misma capacidad** que su pantalla o su ruta, la matriz GRC y el alcance de datos de quien la usa: el agente nunca hace lo que tú no podrías.
- Se corta a los 20 pasos y comprueba el tope de gasto antes de cada turno.
- Necesita un proveedor con herramientas (Anthropic, familia OpenAI o Gemini).

### 38.4 NexusOracle y otras funciones

**NexusOracle** (`/oracle`; `ia.ver`). Avisos de riesgo de retraso de proyecto, incumplimiento de SLA, agotamiento (burnout) y sobrecoste. **Son reglas, no IA**. Pulsa **Ejecutar análisis**, filtra por gravedad y marca **Reconocer**. La «probabilidad» es una puntuación con tope, no una probabilidad calibrada. Se puede apagar en Gobierno de IA (módulo `nexusoracle`).

**Asignación por IA** (`/semantic-engine`; `ia.asignacion`: Dirección, PM y RRHH). Propone la mejor persona para una tarea o un ticket comparando su texto con los perfiles y el historial de asignaciones, y corrige por carga. Se usa también en la auto-asignación al crear tareas y tickets. Pestañas: **Perfiles**, **Probar** y **Estadísticas**; botones **Reconstruir embeddings** y **Auto-generar perfiles**. La configuración (modo híbrido, solo semántico, solo IA o solo reglas; umbrales; auto-asignación) está en Configuración › **Asignación por IA** (Dirección y RRHH). Sin la librería de embeddings usa TF-IDF y la pantalla lo avisa.

**El motor aprende (23-11-2026).** Antes el bucle de aprendizaje estaba abierto: la pantalla de alta registraba cada sugerencia como acertada (la precisión salía 100 % por construcción), los tickets asignados por la IA no dejaban rastro y el historial con decaimiento (nivel 3) estaba vacío.
- Cada asignación de la IA (alta de tarea o ticket con auto-asignación, o sugerencia aceptada en pantalla) deja un `SemAssignment` **pendiente**. Se **confirma** si la persona sugerida lo resuelve o cierra, y se **rechaza** si se reasigna a otra persona, también si ya estaba confirmada. Volver a la persona sugerida no la rechaza. Si en el alta se eligió otra persona, nace rechazada. La **precisión** de *Estadísticas* es aceptadas / (aceptadas + rechazadas) reales.
- Al **resolver o cerrar** un ticket o **terminar** una tarea, su texto y quien lo resolvió van al historial (`sem_embedding_cache`), con la fecha de la resolución para el decaimiento.
- **Corregir asignación** (ficha de la tarea, junto al asignado; ficha del ticket, junto a *Reasignar*; `ia.asignacion`): eliges la persona correcta, el motor la guarda en su caché de experto (niveles 1 y 2), la sugerencia cuenta como rechazada y el elemento se reasigna. Auditado. `POST /semantic/feedback` (`item_type`, `item_id`, `correct_user_id`; `confirmed` + `original_engine_mode=llm` para confirmar una propuesta del modelo de lenguaje). Arreglado: guardaba `corrected_by = "manager_confirm:<uuid>"` en una columna de 36 caracteres con FK a usuarios; ahora `corrected_by` es el id y el tipo va en `sem_feedback.correction_kind` (`correccion` / `confirmacion_responsable`; migración 207, que corrige las filas viejas).
- Pestaña **Casos dudosos** (`ia.asignacion`): las sugerencias pendientes ordenadas por lo que más enseña revisarlas (incertidumbre 40, novedad 30, urgencia 20, poca carga 10: el priorizador de aprendizaje activo del sistema de origen); **Confirmar** o **Corregir**. `GET /semantic/review-queue`. `POST /semantic/prioritize` se mantiene para integraciones.
- **Reentrenamiento**: la tarea `app.worker.semantic_reentrenar` corre cada hora y, en cada empresa, regenera los perfiles desde su historial y sus embeddings cuando toca según `SEMANTIC_RETRAIN_INTERVAL_HOURS` (24; 0 lo apaga; en vivo por empresa).

**Otras funciones con IA**: análisis de contratos (`/contracts-ai`), asistente de reuniones ([§37](#37-colaboración-chat-llamadas-y-reuniones)), base de conocimiento del service desk ([§24](#24-service-desk)), chat del portal de clientes ([§29](#29-portal-de-clientes)), comandos de voz y Mi cuaderno ([§19](#19-mi-cuaderno)).

### 38.5 Proveedores de IA (AI Hub)

**Qué es.** Configuración › IA e idiomas › **Proveedores de IA** (`/settings/ai-hub`; la ruta antigua `/ai-hub` redirige). Para Dirección.

**Cómo se usa.**

1. **Añadir proveedor**: tipo, clave de API, URL base, modelo por defecto y temperatura. **Probar sin guardar** y **Descubrir modelos con esta clave** usan lo tecleado sin guardar nada.
2. Guarda y pulsa **Probar** (petición real). **Sincronizar modelos** lee la lista del proveedor. Marca uno como **predeterminado**.
3. **Orden de respaldo**: si el elegido falla, se prueban los demás de menor a mayor.
4. Pestaña **Por función**: proveedor y modelo para cada función (asistente, agente, borradores del service desk, autorresolución, cambios, base de conocimiento, documentos, contratos, reuniones, narrativa BI, Preguntar a los datos, desempate semántico, portal, voz…). Vacío = el predeterminado.
5. Pestañas **Uso** (llamadas, tokens y coste por módulo), **Gobierno** (registro de evaluaciones de las políticas de IA, solo lectura), **Observabilidad** y **Guía**. Botón **Diagnóstico**.

**Coste y tope de gasto.** Cada llamada apunta tokens y coste (precios del catálogo de modelos; un modelo fuera del catálogo y Ollama cuentan 0). Cada empresa fija `AI_DAILY_BUDGET_USD` (0 = sin tope). Al llegar al tope del día (desde las 00:00 UTC), la IA **deja de responder con 429** hasta el día siguiente; el portal avisa al cliente. El hub enseña el gasto de hoy frente al tope y avisa desde `AI_DAILY_BUDGET_WARN_PCT` (80 %).

**Consejos.** Las claves se guardan cifradas y nunca se devuelven. Un proveedor definido en el `.env` aparece como tarjeta «Desde .env» y se puede **importar** para editarlo como uno de la empresa. Los tiempos de espera son ajustes (grupo Timeouts).

### 38.6 Gobierno de IA (`/governance`)

**Qué es.** Configuración › IA e idiomas › **Gobierno de IA por módulo** (`/settings/ai-governance`; `/governance` redirige). Para Dirección (`gobierno.administrar`).

**Cómo se usa.**

- **Módulos**: encender o apagar cada módulo de IA y fijar su límite diario de acciones. Módulos: NexusAssist, NexusAgent, NexusOracle, Asistente de reuniones, Inteligencia de contratos, IA de base de conocimiento, IA del portal, Comandos de voz, Agentes externos (MCP), Mi cuaderno y Del ticket al PR. **MCP y Del ticket al PR están apagados** hasta que alguien los enciende; el resto, encendidos.
- **Uso**: llamadas y tokens por módulo.
- **Auditoría**: el **registro** de las últimas acciones de IA (fecha, módulo, acción).

Un módulo apagado responde 403 con el motivo; al pasar su límite diario, 429.

**Datos que salen.** Lo que se envía a un proveedor externo es el texto de la petición y su contexto. Las políticas de protección (ocultar datos personales o bloquear) se evalúan en la entrada y la salida del asistente y del agente cuando la empresa tiene políticas activas; esas políticas se gestionan hoy por API (no hay editor en pantalla y no vienen sembradas). Para no enviar nada fuera, usa un proveedor local (Ollama). Del ticket al PR oculta los datos personales del ticket antes de enviarlo al modelo ([§40](#40-del-ticket-al-pr)).

**Configuración por empresa.** Proveedores, función → modelo, tope de gasto, módulos y límites son **de cada empresa**: una empresa nunca usa el proveedor ni la clave de otra, tampoco en tareas de fondo.

**Más detalle.** Lista de ajustes de IA (`AI_*`): `docs/REFERENCIA_DE_AJUSTES.md`.

---

## 39. MCP: agentes de código externos

**Qué es.** Contecflow expone un servidor **MCP** (Model Context Protocol) en `POST /api/v1/mcp` para que un desarrollador o un técnico trabaje con sus tareas, tickets, horas y cambios desde un agente de código (OpenCode, Claude Code u otro cliente MCP), sin salir del editor o el terminal.

**Para quién.** Cualquier persona (`mcp.usar`) genera su credencial y conecta su agente; **actúa como ella**, con sus permisos. Encender el servidor y decidir si se escribe: Dirección (`gobierno.administrar`).

**Cómo se activa (Dirección).** Configuración › Integraciones › **Agentes de código (MCP)** (`/settings/mcp`):

| Ajuste | Por defecto | Qué hace |
|---|---|---|
| Servidor MCP encendido | apagado | Apagado, todo responde 403 `mcp_apagado`. |
| Herramientas que escriben (`MCP_WRITE_MODE`) | `off` | `off`: no se ofrecen. `approval`: cada escritura abre una aprobación «Acción de agente externo (MCP)» y se ejecuta al aprobarse. `direct`: se ejecutan. |
| Herramientas de Mi cuaderno (`MCP_NOTEBOOK_ENABLED`) | apagado | Aun encendido, cada persona decide qué cuadernos comparte con sus agentes. |
| Llamadas por minuto (`MCP_RATE_LIMIT_PER_MINUTE`) | 60 | Por credencial; al pasarlo, 429. |

**Cómo se conecta (cada persona).**

1. En la misma sección, **Mis credenciales MCP → Generar credencial**: solo lectura (`mcp:read`) o lectura y escritura (`mcp:write`), caducidad de 1 a 365 días (90 por defecto). La clave (`nxpm_…`) se muestra **una vez**. Solo abre `POST /api/v1/mcp`: no sirve para el resto de la API ni para gestionar credenciales.
2. Guárdala en una variable de entorno, nunca en un fichero del repositorio:

   ```bash
   export CONTECFLOW_MCP_TOKEN="nxpm_…"
   ```

3. **Claude Code**:

   ```bash
   claude mcp add --transport http --scope user contecflow https://<tu-servidor>/api/v1/mcp \
     --header "Authorization: Bearer $CONTECFLOW_MCP_TOKEN"
   ```

   **OpenCode** (`opencode.jsonc`): servidor `remote` con `"url": "https://<tu-servidor>/api/v1/mcp"` y cabecera `"Authorization": "Bearer {env:CONTECFLOW_MCP_TOKEN}"`.
4. Comprueba con `claude mcp list` u `opencode mcp list` y pide, por ejemplo, «enséñame mis tickets abiertos».

**Herramientas expuestas.** Mis tareas, buscar y ver tareas, comentar y cambiar su estado; mis tickets, buscar y ver tickets, comentar y cambiar su estado; buscar proyectos; **imputar horas** y el cronómetro (ver, arrancar, parar); catálogo de cambios estándar, **abrir un cambio**, ver cambios; buscar y leer notas de Mi cuaderno compartidas con los agentes. Además, las herramientas de NexusAgent (que piden también `ia.usar`). La sección enseña la tabla «Herramientas disponibles» de cada persona.

**Reglas.** Cada herramienta exige la **misma capacidad** que su ruta de la API y aplica las mismas reglas que la pantalla (transiciones de estado, cierre de periodo y topes de imputación, CAB). Un empleado o un externo ve solo lo suyo; la empresa es la de la credencial.

**Auditoría.** Cada conexión (`MCP_CONNECT`), cada escritura (`MCP_TOOL_CALL`), cada aprobación pedida y cada lectura de notas quedan en el registro de auditoría con la credencial, la empresa y la IP; cada llamada, en el registro de uso de IA. De los argumentos solo se guardan ids, estados y cifras; del texto libre, su longitud.

**Consejos.** Lo que devuelve una herramienta son datos, no órdenes: revisa lo que el agente propone antes de aceptar una escritura, o usa el modo `approval`. Un 401 suele ser que la variable de entorno no existe donde arrancas el agente.

**Más detalle.** `docs/integraciones/MCP.md` (configuración completa, ejemplos, protocolo, límites y resolución de problemas).

---

## 40. Del ticket al PR

**Qué es.** Desde un ticket, un bug o una tarea, un agente de código propone el arreglo como **pull request** (GitHub) o **merge request** (GitLab). El agente trabaja en un contenedor aislado, una persona aprueba su plan y el PR va unido a un cambio ITSM que pasa por el CAB. **Contecflow nunca fusiona**: el merge lo hace siempre una persona. Módulo opcional por empresa, **apagado por defecto**.

**Para quién.**

| Capacidad | Roles | Qué permite |
|---|---|---|
| `ticket_pr.ver` | internos | Ver las ejecuciones del ticket o tarea que ya ve |
| `ticket_pr.lanzar` | Dirección, PM, jefe de equipo | Lanzar, cancelar, sincronizar con el CAB |
| `ticket_pr.aprobar_plan` | Dirección, PM, jefe de equipo | Aprobar o rechazar el plan |
| `ticket_pr.config` | Dirección | Configurar el módulo |

**Requisitos.** Docker en el servidor (sin Docker no se ejecuta nada: 409 `ticket_pr_docker_no_disponible`); un repositorio en GitHub (con una GitHub App instalada solo en los repositorios permitidos) o en GitLab (token de proyecto con rol Developer); un proveedor de IA; la imagen del motor (OpenCode) con **versión fijada**; y la rama base protegida en el proveedor, exigiendo el estado `contecflow/cab`.

**Cómo se activa.** Configuración › Integraciones › **Del ticket al PR** (`/settings/ticket-a-pr`; los ajustes de la empresa se guardan en `ticket_pr.config`):

1. Encender el módulo.
2. Motor, imagen y versión; proveedor y modelo de IA.
3. Credenciales Git (cifradas, se escriben pero nunca se leen).
4. **Repositorios permitidos por proyecto**: proveedor, repositorio, rama base y orden de tests.
5. Seguridad: ficheros protegidos adicionales, hosts de salida extra, órdenes de shell permitidas, ejecutar tests, exigir que el plan lo apruebe **otra persona**, tipo de cambio.
6. Límites, plantillas de instrucción y **Probar** la conexión (Docker, imágenes, Git, modelo).

**Flujo.**

1. En el ticket o la tarea, **Proponer arreglo con IA**: elige repositorio y rama; revisa la instrucción (generada del ticket con los datos personales ocultos).
2. **Plan**: el agente lee el código en modo solo lectura y propone qué cambiará y qué ficheros. Una persona **aprueba o rechaza**.
3. **Construcción**: en otro contenedor, desde el mismo commit, aplica el cambio. Contecflow comprueba el diff (ficheros protegidos, secretos, enlaces, binarios, tamaño) y, si la empresa lo pide, ejecuta los tests. Si algo falla, la ejecución queda **Bloqueada** y no se abre PR.
4. **PR**: rama nueva `contecflow/<ticket>-<id>` y PR/MR con descripción y enlace al ticket. Se abre un **cambio** ITSM enlazado que va al **CAB**.
5. CAB aprueba → el estado `contecflow/cab` pasa a correcto y una persona fusiona. CAB rechaza → fallo.

Todo queda en el panel «Del ticket al PR» del ticket o la tarea: estado, plan, quién decidió, motivo de bloqueo, resumen del diff, tests, PR, cambio, horas del agente, tokens, coste y log del contenedor (con datos personales ocultos).

**Límites** por empresa y día: ejecuciones (`TICKET_PR_MAX_RUNS_PER_DAY`), coste (`TICKET_PR_MAX_COST_PER_DAY_USD`), a la vez (`TICKET_PR_MAX_CONCURRENT`), y el tope diario de IA de la empresa. Por ejecución: CPU, memoria, procesos, tiempo de plan y de construcción, tamaño del repositorio, ficheros cambiados y tamaño del diff (`TICKET_PR_*`).

**Seguridad.** Un contenedor efímero por fase, sin privilegios, raíz de solo lectura, sin red salvo un proxy con lista blanca (la API del modelo); **nunca ve credenciales de Git** (el código se baja y el PR se abre desde el servidor). Ficheros protegidos de fábrica: CI, `CODEOWNERS`, `.env*`, claves y certificados, `**/secrets/**`, entre otros. Quien lanza no vota su cambio en el CAB. El coste se imputa al proyecto. Las credenciales delegadas (claves de API, OAuth) no abren este módulo.

**Más detalle.** `docs/integraciones/TICKET_A_PR.md` (diseño, preparación de GitHub y GitLab, riesgos y controles, y lo que queda por verificar con Docker y Git reales).

---

## 41. Configuración: mapa de secciones

**Toda** la configuración está en **Configuración** (`/settings/<sección>`), con una sola entrada en el menú. Los módulos no tienen botón «Configurar»: si falta algo, avisan y enlazan aquí (solo a quien puede configurarlo). Solo ves las secciones de las que tienes la capacidad; pedir otra por URL lleva a `/403`. Hay un **buscador** (título, descripción y grupo, sin acentos) y, en pantalla estrecha, un desplegable agrupado. `?sub=<id>` abre una subpestaña (Ausencias, Service desk, Campos personalizados).

| Grupo | Sección (`/settings/…`) | Qué se configura | Capacidad (roles) |
|---|---|---|---|
| Empresa y marca | `setup` Puesta en marcha | Lista de pasos para dejar la empresa lista | `org.administrar` (Dirección) |
| | `general` General | Moneda, zona horaria, idioma, jornada | `org.administrar` |
| | `branding` Marca | Nombre, colores (también en los PDF); marca blanca | `org.administrar` |
| | `offices` Sedes | Oficinas | `org.administrar` |
| | `depts` Departamentos y áreas | Departamentos y áreas (también para presupuestos) | `personas.config` (Dirección, RRHH) |
| | `numbering` Numeración | Secuencias de códigos | `org.administrar` |
| | `organizations` Empresas de la plataforma | Alta y gestión de empresas | `plataforma.empresas` (solo superadmin) |
| Personas y jornada | `users` Usuarios | Altas, edición, rol personalizado (alta/baja/borrado solo Dirección) | `personas.config` |
| | `roles` Roles y permisos | Roles personalizados y sus módulos | `org.administrar` |
| | `menu-por-defecto` Menú por defecto | Orden y pestañas ocultas del menú por rol | `org.administrar` |
| | `ausencias` Ausencias | Tipos, documentos, turnos, jornadas, festivos, saldos | `ausencias.config` (Dirección, RRHH) |
| | `vacations` Vacaciones | Derecho anual | `personas.config` |
| | `horas-extra` Horas extra | Reglas y liquidación | `horas_extra.config` (Dirección, RRHH) |
| | `cuaderno` Mi cuaderno | Etiquetas, plantillas, papelera, IA, voz, acceso excepcional | `cuaderno.config` (Dirección) |
| Proyectos y trabajo | `catalogos` Catálogos | Tipos de proyecto, sectores de cliente, categorías de gasto | `proyectos.config` (Dirección, PM) |
| | `project-templates` Plantillas de proyecto | Plantillas | `proyectos.config` |
| | `issue-types` Tipos de tarea | Tipos de incidencia por proyecto | `proyectos.config` |
| | `project-workflows` Flujos de estado | Estados y transiciones de tareas | `proyectos.config` |
| | `custom-fields` Campos personalizados | Por proyecto y globales (globales, Dirección) | `proyectos.config` |
| | `project-permissions` Permisos de proyecto | Permisos dentro de cada proyecto | `proyectos.config` |
| | `cartera` Entrada a la cartera | Criterios de puntuación y fases | `cartera.gestionar` (Dirección, PM) |
| Service desk | `sd` Service desk | Canales, correo entrante, políticas SLA, SLA condicionales y OLA, plantillas… | `sd.config` (gestores; casi todo, solo Dirección) |
| | `sla-calendars` Calendarios de SLA | Horarios y festivos del SLA | `sd.disenar_flujos` (Dirección, PM) |
| | `sd-workflows` Diseñador de flujos | Abre `/sd/workflow-designer` | `sd.disenar_flujos` |
| | `sd-agente` Agente autónomo | Encendido, modo, umbrales, playbooks | `sd.administrar` (Dirección) |
| | `sd-autorresolucion` Autorresolución | Umbrales y cierre automático | `sd.administrar` |
| | `sd-voz` Agente de voz | Saludo, idioma, teclas | `sd.administrar` |
| | `sd-cambios-estandar` Cambios estándar | Catálogo de modelos preaprobados por el CAB | `sd.gestionar` (gestores) |
| | `cmdb-software` Software y vulnerabilidades | Fuentes de avisos, SLA de remediación, licencias | `software.config` (Dirección) |
| Finanzas | `rates` Tarifas | Tablas de tarifas | `tarifas.config` (Dirección, PM) |
| | `user-costs` Estructura de coste | Perfiles de coste y costes por país | `costes.config` (Dirección, RRHH) |
| | `proveedores` Proveedores | Plantillas de contrato, servicios, umbrales | `proveedores.config` (Dirección, PM) |
| | `clientes-internos` Clientes internos | Servicios compartidos y reparto de cargos | `interno.cargos` (Dirección) |
| Aprobaciones y políticas | `approval-workflows` Flujos de aprobación | [§36.4](#364-configuración-de-flujos-settingsapproval-workflows) | `org.administrar` |
| | `policies` Políticas y reglas | [§36.3](#363-motor-de-políticas-y-reglas-settingspolicies) | `org.administrar` |
| | `demanda` Flujos de demanda | Tipos de solicitud, flujos, plantillas | `demanda.config` (Dirección) |
| IA e idiomas | `ai-hub` Proveedores de IA | [§38.5](#385-proveedores-de-ia-ai-hub) | `org.administrar` |
| | `ai-governance` Gobierno de IA por módulo | [§38.6](#386-gobierno-de-ia-governance) | `org.administrar` |
| | `idiomas` Idiomas | Idiomas activos | `org.administrar` |
| | `traduccion` Traducción | Traducción automática | `org.administrar` |
| | `ia-asignacion` Asignación por IA | Modo, embeddings, umbrales | `ia.asignacion_config` (Dirección, RRHH) |
| | `reuniones` Asistente de reuniones | Consentimiento, retención, Teams/Zoom/Meet, RGPD | `reuniones.config` (Dirección) |
| Integraciones | `integrations` Credenciales de integraciones | Claves y secretos (incl. Slack) | `org.administrar` |
| | `esign` Firma electrónica | DocuSign / Adobe Sign | `org.administrar` |
| | `alm-fuentes` Fuentes de uso de licencias | Conexiones de uso real | `org.administrar` |
| | `m365` Microsoft 365 | Guía y estado de variables | `org.administrar` |
| | `m365-informes` Informes de Microsoft 365 | Credenciales de Graph | `org.administrar` |
| | `git` Git | Webhooks de GitHub/GitLab (solo lectura) | `proyectos.gobierno` (Dirección, PM) |
| | `jira` Jira | Integración con Jira | `org.administrar` |
| | `enterprise` Empresa: SSO, webhooks y OAuth | SSO, webhooks salientes, OAuth, integraciones Slack/Teams | `org.administrar` |
| | `webhook-log` Registro de webhooks | Entregas recibidas | `org.administrar` |
| | `developer` Portal de desarrolladores | Claves y apps OAuth | `integraciones.desarrollo` (Dirección, PM) |
| | `mcp` Agentes de código (MCP) | [§39](#39-mcp-agentes-de-código-externos) | `mcp.usar` (todos; ajustes, Dirección) |
| | `ticket-a-pr` Del ticket al PR | [§40](#40-del-ticket-al-pr) | `ticket_pr.config` (Dirección) |
| | `import` Importar datos | Importación masiva | `integraciones.desarrollo` |
| Seguridad y GRC | `seguridad-cuentas` Seguridad de cuentas | Contraseñas, bloqueo, MFA, sesiones, campañas de recertificación | `seguridad.administrar` (Dirección) |
| | `recertificacion` Recertificación de accesos | Lo que revisa cada responsable | `seguridad.recertificar` (gestores) |
| | `mfa` Mi verificación en dos pasos | Tu MFA | cualquiera |
| | `grc` GRC y segregación de funciones | Matriz GRC y reglas SoD | `org.administrar` |
| | `chat-admin` Administración del chat | Moderación y retención | `org.administrar` |
| Portal de clientes | `public-forms` Formularios públicos | Formularios sin login | `portal.formularios` (Dirección, PM) |
| | `portal-translations` Traducciones del portal | Revisión de textos del portal | `org.administrar` |
| Alertas y métricas | `alert-config` Alertas · `metrics` Métricas | Umbral, gravedad y activación de cada alerta | `org.administrar` |
| Sistema | `runtime-flags` Config. dinámica · `log-level` Nivel de log · `system-state` Estado del sistema | Ajustes en vivo por grupo (incluidos Semáforos), registro y estado | `org.administrar` |

**Rutas antiguas.** `/organizations`, `/project-templates`, `/issue-types`, `/custom-fields`, `/project-permissions`, `/sla-calendars`, `/rate-cards`, `/user-costs`, `/ai-hub`, `/governance`, `/m365`, `/jira-integration`, `/enterprise`, `/webhook-log`, `/developer`, `/import`, `/mfa`, `/grc` y `/public-forms` redirigen a su sección. `/settings?tab=<id>` también.

**Configuración que no está aquí, a propósito.** El portal de cada cliente (ficha del cliente → Portal → Configuración), los conectores ETL de la Plataforma de datos y la bandeja de aprobaciones. Las notificaciones personales se ven en la Bandeja de entrada (`/notifications` redirige a ella); no hay pantalla de preferencias de notificación por persona.

**Más detalle.** `docs/CONFIGURACION.md` (criterio, redirecciones y menú lateral personalizable) y `docs/REFERENCIA_DE_AJUSTES.md` (todos los ajustes).

---

# Común

---

## 42. Roles y capacidades

### 42.1 Roles base

Cada persona tiene **un rol base** (`users.role`). Las etiquetas son las que se ven en la pantalla.

| Rol (`users.role`) | Etiqueta | Para quién |
|---|---|---|
| `admin` | Dirección | Administra la empresa; ve costes |
| `pm` | Project Manager | Gestiona proyectos, clientes y finanzas |
| `team_lead` | Team Lead | Responsable de un equipo |
| `hr` | RRHH | Personas, ausencias, costes de personal |
| `employee` | Empleado | Sus tareas, horas, gastos y ausencias |
| `subcontractor` | Externo | Persona de un proveedor: trabaja como un interno, solo sobre lo suyo |

Además:

- **Superadmin de plataforma** (`users.is_superadmin`): dueño de la instalación; tiene todas las capacidades, incluida gestionar empresas (`plataforma.empresas`), que nadie más tiene.
- **Usuario del portal de clientes**: no es un usuario interno. Tiene su propio acceso en `/portal` y lo da de alta el equipo desde la ficha del cliente (ver [§29](#29-portal-de-clientes)).
- **Contacto del portal del proveedor**: un externo marcado como contacto de su proveedor (`proveedores.portal`), ver [§30](#30-proveedores-y-portal-de-proveedores).

Grupos que se repiten abajo: **internos** = Dirección, PM, Team Lead, RRHH y Empleado; **gestores** = Dirección, PM, Team Lead y RRHH; **todos** = internos y Externo.

### 42.2 Qué es una capacidad

Una **capacidad** es un permiso con nombre (`proyectos.ver`, `gastos.gestionar`, `sd.config`…) con los roles base que la tienen por defecto. Hay 192, en `app/core/capacidades.py`. La misma capacidad decide a la vez la ruta de la pantalla, la entrada del menú, los botones y la guarda de la API: **lo que se ve no da 403**.

**Cómo se asignan.** No se reparten una a una: salen del **rol base** de la persona. Para restringir a alguien, Dirección crea un **rol personalizado** en Configuración › **Roles y permisos** (marca qué módulos abre) y se lo asigna en Configuración › **Usuarios** → Editar → *Rol personalizado*. Un rol personalizado **solo quita**: un módulo cerrado hace desaparecer sus pantallas y sus capacidades y la API responde 403; nunca da algo que el rol base no tenga. A Dirección y al superadmin no se les cierra ningún módulo. Los módulos que se pueden cerrar: panel, proyectos, tareas, imputaciones, partes, recursos, capacidad, rentabilidad, pipeline, contratos, riesgos, cambios, entregables, competencias, ausencias, informes, alertas, exportaciones y configuración.

Ocultar una pestaña con «Personalizar menú» no quita permisos: la ruta se sigue abriendo por URL.

### 42.3 Qué puede hacer cada rol por defecto

Capacidades principales por área (D = Dirección, PM, TL = Team Lead, RRHH, E = Empleado, X = Externo).

| Área | Capacidad | D | PM | TL | RRHH | E | X |
|---|---|---|---|---|---|---|---|
| Plataforma | `org.administrar` administrar la empresa | ✔ | | | | | |
| | `seguridad.administrar` políticas de cuenta | ✔ | | | | | |
| | `seguridad.recertificar` revisar accesos de mi equipo | ✔ | ✔ | ✔ | ✔ | | |
| Trabajo diario | `colaboracion.ver` chat, calendario, documentos, wiki, aprobaciones, informes | ✔ | ✔ | ✔ | ✔ | ✔ | |
| | `tareas.editar` editar tareas | ✔ | ✔ | ✔ | | ✔ | |
| | `tareas.crear` crear tareas | ✔ | ✔ | ✔ | | | |
| | `gastos.ver` mis gastos | ✔ | ✔ | ✔ | ✔ | ✔ | |
| | `gastos.gestionar` gastos del equipo | ✔ | ✔ | | ✔ | | |
| | `partes.equipo` partes del equipo | ✔ | ✔ | | ✔ | | |
| | `cuaderno.usar` Mi cuaderno | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Proyectos | `proyectos.ver` proyectos (cada uno los suyos) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| | `proyectos.trabajo` sprints, RACI, Gantt, épicas, UAT | ✔ | ✔ | ✔ | ✔ | ✔ | |
| | `proyectos.panel` salud del portfolio | ✔ | ✔ | ✔ | | | |
| | `proyectos.gestionar` gestionar proyectos y EVM | ✔ | ✔ | | | | |
| | `proyectos.gobierno` riesgos, cambios, entregables, Git, firma | ✔ | ✔ | | | | |
| Personas | `equipo.ver` capacidad del equipo | ✔ | ✔ | ✔ | ✔ | | |
| | `recursos.ver` recursos, organigrama, OKR, evaluaciones | ✔ | ✔ | | ✔ | | |
| | `costes.ver` costes y tarifas de personas | ✔ | | | ✔ | | |
| | `ausencias.gestionar` ausencias del equipo | ✔ | ✔ | ✔ | ✔ | | |
| Clientes y finanzas | `finanzas.ver` clientes, pipeline, facturas, rentabilidad, presupuestos | ✔ | ✔ | | | | |
| | `proveedores.ver` proveedores | ✔ | ✔ | ✔ | ✔ | | |
| | `proveedores.portal` portal del proveedor | | | | | | ✔ |
| | `interno.portal` portal interno (Mi departamento) | ✔ | ✔ | ✔ | ✔ | ✔ | |
| Soporte | `sd.ver` service desk (el externo, sus tickets) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| | `sd.completo` service desk completo | ✔ | ✔ | ✔ | ✔ | ✔ | |
| | `sd.gestionar` colas, escalados, guardias | ✔ | ✔ | ✔ | ✔ | | |
| | `sd.administrar` canales, SLA, agente | ✔ | | | | | |
| | `cmdb.ver` CMDB · `alm.ver` licencias y activos | ✔ | ✔ | | | | |
| Análisis | `analitica.ver` panel ejecutivo, explorador, predicciones, EVM | ✔ | ✔ | | | | |
| | `alertas.ver` alertas · `exportar.ver` exportación | ✔ | ✔ | | ✔ | | |
| | `datos.plataforma` plataforma y gobierno de datos | ✔ | | | | | |
| IA | `ia.ver` NexusAgent, Oracle, automatizaciones | ✔ | ✔ | | | | |
| | `ia.asignacion` asignación por IA | ✔ | ✔ | | ✔ | | |
| | `mcp.usar` agentes de código | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| | `ticket_pr.lanzar` del ticket al PR | ✔ | ✔ | ✔ | | | |
| Gobierno | `gobierno.administrar` GRC, políticas, gobierno de IA, retención | ✔ | | | | | |

Las secciones de Configuración y su capacidad están en [§41](#41-configuración-mapa-de-secciones).

**Catálogo completo.** Las 192 capacidades, con sus roles, en `app/core/capacidades.py`; la persona recibe las suyas al entrar (`/auth/me`) y `GET /auth/capacidades` devuelve el catálogo. Qué capacidad guarda cada ruta de la API: `docs/seguridad/guardas_por_capacidad.md`.

**Matriz de permisos.** La declaración ruta → capacidad del frontend está en un único sitio (`frontend/src/permisos/navegacion.ts`), que leen las rutas, el menú y la página de inicio. Dos pruebas la vigilan: `tests/test_capacidades.py` (quien tiene la capacidad no recibe 403 en su pantalla y, en las estrictas, quien no la tiene sí) y `frontend/src/__tests__/matrizDePermisos.test.tsx` (el catálogo del frontend es igual al del backend y menú y rutas salen de la misma declaración).

**Página de inicio tras entrar.** Salud del portfolio para quien la ve (Dirección, PM, Team Lead); capacidad del equipo para RRHH; Mi día para el resto.

---

## 43. Glosario

| Término | Qué significa en contecflow |
|---|---|
| **ABAC** | Control de acceso por atributos: políticas que deciden por atributos de la persona y del recurso, además del rol. |
| **ALM** | Gestión del ciclo de vida de activos: licencias, equipos, contratos de proveedor y altas y bajas ([§26](#26-licencias-y-activos-alm)). |
| **Bloqueo legal** | Marca que impide borrar o suprimir datos afectados por un litigio o requerimiento, por encima de la retención. |
| **CAB** | Comité de cambios: aprueba los cambios ITSM normales antes de ejecutarlos. |
| **Capacidad** | (1) Permiso con nombre de la matriz de permisos ([§42](#42-roles-y-capacidades)). (2) Horas disponibles de una persona o equipo en planificación. |
| **Chargeback / showback** | Repercutir (chargeback) o solo mostrar (showback) el coste de los servicios a las unidades internas ([§28](#28-clientes-internos)). |
| **CI / CMDB** | Elemento de configuración (servidor, aplicación, servicio…) y la base de datos que los guarda con sus relaciones ([§25](#25-cmdb-software-y-vulnerabilidades)). |
| **Empresa / organización** | El inquilino: cada empresa ve solo sus datos. En la interfaz se dice «empresa»; en el código, `organization`. |
| **EVM** | Gestión del valor ganado: BAC, PV, EV, AC, CPI, SPI, EAC ([§33.6](#336-evm-cartera-burnup-flujo-acumulado-y-riesgo)). |
| **Externo** | Persona de un proveedor con rol `subcontractor`: trabaja como un interno sobre lo suyo. |
| **ITSM** | Gestión de servicios de TI: incidencias, peticiones, problemas y cambios ([§24](#24-service-desk)). |
| **KEDB** | Base de errores conocidos: problemas con su causa y solución temporal. |
| **MCP** | Model Context Protocol: protocolo con el que un agente de IA externo usa herramientas de contecflow ([§39](#39-mcp-agentes-de-código-externos)). |
| **OKR** | Objetivos y resultados clave. |
| **OLA** | Acuerdo de nivel operativo entre equipos internos que soporta un SLA. |
| **Portal** | Acceso externo: el portal de clientes (`/portal`), el del proveedor (`/supplier-portal`) y el interno (Mi departamento). |
| **PSA** | Professional Services Automation: proyectos, horas, recursos, facturación y rentabilidad en una herramienta. |
| **RACI** | Matriz de quién es Responsable, Aprobador, Consultado e Informado. |
| **RFC** | Solicitud de cambio. |
| **RLS** | Row Level Security: filtro por empresa en la propia base de datos PostgreSQL, además del de la aplicación. |
| **Rol personalizado** | Rol que restringe módulos sobre el rol base; nunca añade permisos. |
| **SBOM** | Lista de componentes de un software, para cruzarla con vulnerabilidades. |
| **SLA** | Acuerdo de nivel de servicio: tiempos de respuesta y resolución comprometidos con el cliente. |
| **SoD** | Segregación de funciones: nadie aprueba lo suyo, y la matriz GRC impide combinaciones de permisos incompatibles. |
| **Superadmin** | Dueño de la plataforma; gestiona empresas. |
| **UC** | Contrato de soporte con un proveedor que sostiene un SLA (underpinning contract). |
| **Umbral de semáforo** | Corte de aviso y crítico de una métrica, por empresa ([§33.9](#339-umbrales-de-semáforo)). |

---

## 44. Preguntas frecuentes

**No veo un módulo en el menú.** Puede ser: (1) tu rol no tiene su capacidad ([§42](#42-roles-y-capacidades)); (2) tu rol personalizado cierra ese módulo; (3) lo ocultaste: pulsa **Personalizar menú** al pie del menú y **Restablecer**; (4) es un módulo de IA apagado en Gobierno de IA. Pregunta a Dirección.

**¿Cómo cambio el idioma?** Pulsa tu nombre al pie del menú → pestaña **Idioma**: español, inglés o chino. El portal de clientes admite más idiomas. Ver [§17](#17-primeros-pasos-entrar-navegar-menú-e-idiomas).

**He olvidado mi contraseña.** En la pantalla de entrada, **¿Olvidaste tu contraseña?**: recibirás un enlace por correo que abre `/reset-password`. Las reglas de la contraseña las fija Dirección en Seguridad de cuentas.

**¿Cómo cambio mi contraseña o activo la verificación en dos pasos?** Perfil → **Seguridad**, y Configuración › **Mi verificación en dos pasos** (`/settings/mfa`).

**¿Cómo cambio de empresa?** Si perteneces a varias y la instalación entra con correo y selector, aparece **Cambiar de empresa** en la cabecera. Al cambiar, la página se recarga con una sesión nueva. En instalaciones por subdominio o código de empresa, la empresa la fija el acceso.

**¿Cómo doy acceso al portal a un cliente?** **Clientes** → ficha del cliente → **Portal** → **Accesos**: nombre, correo, contraseña y proyectos. La contraseña se ve una sola vez. Ver [§29](#29-portal-de-clientes).

**¿Por qué no puedo aprobar mi propio gasto?** Por segregación de funciones: nadie aprueba ni reembolsa lo suyo, sea cual sea el flujo. Lo decide otro responsable o tu delegado.

**Al aprobar un gasto me sale un error 409.** O una política le añadió niveles (se decide en la **bandeja de Aprobaciones**), o el presupuesto no tiene disponible y la empresa bloquea ([§32.7](#327-presupuestos-budgets)).

**Me voy de vacaciones, ¿quién aprueba lo mío?** En la bandeja de Aprobaciones, **Fuera de la oficina**: elige un delegado y las fechas ([§36.1](#361-bandeja-de-aprobaciones-approvals)).

**¿Puedo aprobar desde el correo?** Sí: el correo trae un enlace válido 72 horas que abre una página con el resumen y los botones de aprobar y rechazar.

**¿Dónde configuro el SLA?** Configuración › **Service desk** → **Políticas SLA** y **SLA condicionales y OLA**; los horarios y festivos, en **Calendarios de SLA**. Ver [§24](#24-service-desk).

**La IA no responde o da 429.** Causas: no hay proveedor configurado; la empresa llegó a su **tope de gasto diario** de IA (`AI_DAILY_BUDGET_USD`; se reinicia a las 00:00 UTC); el módulo está apagado o pasó su límite diario en Gobierno de IA. Dirección lo ve en Proveedores de IA (gasto de hoy) y en Gobierno de IA ([§38](#38-inteligencia-artificial)).

**¿Cómo exporto a Excel?** El botón **Exportar Excel** de la cabecera descarga lo que se ve en la lista. Para datos completos: **Exportación de datos** (`/exports`), el CSV del **Constructor de informes** o la exportación del propio módulo ([§33.7](#337-exportación-de-datos-y-exportar-excel)).

**¿Cómo creo una factura desde las horas?** Facturación → **Nueva factura** → **Generar líneas** ([§32.2](#322-facturación-invoices)). Solo entran horas facturables, aprobadas y sin facturar.

**Me equivoqué en una factura emitida.** No se edita: **Anúlala** y crea otra. Sus horas vuelven a estar libres.

**¿Por qué el agente no hizo el cambio que le pedí?** Sin «Permitir que cree o cambie datos», las escrituras quedan pendientes de aprobación en NexusAgent ([§38.3](#383-nexusagent-el-agente-con-aprobación-humana)).

**¿Cómo automatizo un aviso?** Automatizaciones → **Nueva regla**, elige disparador y acción, y pulsa **Probar** antes de activarla ([§35](#35-automatizaciones)).

**(Administración) ¿Cómo restrinjo lo que ve un grupo de personas?** Crea un rol personalizado en Roles y permisos, cierra los módulos y asígnalo en Usuarios ([§42.2](#422-qué-es-una-capacidad)).

**(Administración) ¿Cómo cambio el menú que ve cada rol?** Configuración › **Menú por defecto**: orden de categorías y pestañas ocultas por rol. Cada persona puede personalizar el suyo después.

**(Administración) ¿Dónde cambio un umbral de semáforo?** Config. dinámica › **Semáforos** ([§33.9](#339-umbrales-de-semáforo)).

**(Administración) ¿Cómo conecto Claude Code u OpenCode?** Enciende el servidor en Configuración › **Agentes de código (MCP)**; cada persona genera su credencial allí ([§39](#39-mcp-agentes-de-código-externos)).

**(Administración) Una sección de Configuración da /403.** No tienes su capacidad o tu ruta está bloqueada por un rol personalizado. Las secciones que darían 403 no aparecen en la lista.

**(Administración) ¿Dónde está la lista completa de ajustes?** En `docs/REFERENCIA_DE_AJUSTES.md`; en pantalla, Configuración › **Config. dinámica**.

---

## 45. Índice de la documentación

Este README es la guía principal. Los documentos siguientes amplían una parte concreta; cada uno se enlaza desde su sección.

**Implantación y operación**

| Documento | Para qué sirve |
|---|---|
| [docs/REFERENCIA_DE_AJUSTES.md](docs/REFERENCIA_DE_AJUSTES.md) | Lista completa de variables de entorno (`Settings`) y de ajustes en vivo, con su valor por defecto. La comprueba `tests/test_readme_ajustes_completo.py`. |
| [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md) | Despliegue de un entorno nuevo y actualización de uno existente, paso a paso. |
| [docs/OBSERVABILIDAD.md](docs/OBSERVABILIDAD.md) | Prometheus, Alertmanager, Grafana, métricas por empresa y alertas. |
| [docs/WORKER_TASKS.md](docs/WORKER_TASKS.md) | Tareas programadas del worker (Celery beat) una a una. |
| [docs/CONFIGURACION.md](docs/CONFIGURACION.md) | Pantalla de Configuración: grupos, secciones y menú por defecto. |
| [CHANGELOG.md](CHANGELOG.md) | Cambios por versión. |

**Seguridad e integraciones**

| Documento | Para qué sirve |
|---|---|
| [docs/seguridad/politicas_de_cuenta.md](docs/seguridad/politicas_de_cuenta.md) | Contraseñas, bloqueo, MFA, sesiones, restricciones por IP, restablecimiento. |
| [docs/seguridad/entrada_y_salida.md](docs/seguridad/entrada_y_salida.md) | Subidas de ficheros, salidas de red (SSRF), correo con IP fijada. |
| [docs/seguridad/rutas_anonimas.md](docs/seguridad/rutas_anonimas.md) | Rutas sin sesión y cómo fijan el contexto de empresa. |
| [docs/seguridad/guardas_por_capacidad.md](docs/seguridad/guardas_por_capacidad.md) | Qué capacidad exige cada ruta de la API. |
| [docs/integraciones/pruebas_de_conexion.md](docs/integraciones/pruebas_de_conexion.md) | Qué comprueba cada botón de prueba de conexión. |
| [docs/integraciones/MCP.md](docs/integraciones/MCP.md) | Servidor MCP para agentes de código. |
| [docs/integraciones/TICKET_A_PR.md](docs/integraciones/TICKET_A_PR.md) | «Del ticket al PR»: diseño, seguridad y límites. |

**Manuales por módulo**

| Documento | Módulo |
|---|---|
| [docs/SERVICE_DESK.md](docs/SERVICE_DESK.md) | Service Desk (manual detallado). |
| [docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md](docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md) | CMDB, software, vulnerabilidades e índice de riesgo. |
| [docs/CLIENTES_INTERNOS.md](docs/CLIENTES_INTERNOS.md) | Clientes internos, showback y chargeback. |
| [docs/PROVEEDORES_Y_EXTERNALIZACION.md](docs/PROVEEDORES_Y_EXTERNALIZACION.md) | Proveedores, externalización y portal del proveedor. |
| [docs/FLUJO_DE_DEMANDA.md](docs/FLUJO_DE_DEMANDA.md) | Flujo de demanda configurable. |
| [docs/PIPELINE_COMERCIAL.md](docs/PIPELINE_COMERCIAL.md) | Regla de cálculo de los totales del pipeline. |
| [docs/APPROVAL_ENGINE.md](docs/APPROVAL_ENGINE.md) | Motor de aprobaciones y motor de políticas. |
| [docs/BPM.md](docs/BPM.md) | BPM: motor de procesos. |
| [docs/CUADERNO.md](docs/CUADERNO.md) | Mi cuaderno. |
| [docs/ASISTENTE_DE_REUNIONES.md](docs/ASISTENTE_DE_REUNIONES.md) | Asistente de reuniones. |

**Desarrollo**

| Documento | Para qué sirve |
|---|---|
| [docs/GUIA_DE_DISENO.md](docs/GUIA_DE_DISENO.md) | Guía de diseño de la interfaz. |
| [frontend/src/components/ui/DESIGN_SYSTEM.md](frontend/src/components/ui/DESIGN_SYSTEM.md) | Kit de componentes del frontend y reglas de ESLint que lo imponen. |
| [frontend/kit-migracion-plan.md](frontend/kit-migracion-plan.md) | Plan generado por `frontend/scripts/kit_pendientes.mjs` (no se edita a mano). |
| [alembic/NAMING_CONVENTION.md](alembic/NAMING_CONVENTION.md) | Cómo nombrar migraciones y lista de revisiones destructivas (la comprueba un test). |
| [.github/agents/nexus.agent.md](.github/agents/nexus.agent.md) | Instrucciones del agente «Nexus» para asistentes de código. |
