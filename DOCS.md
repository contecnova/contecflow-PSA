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
