# Backlog Jira - Remediacion Auditoria

Fecha: 24-04-2026
Origen: auditoria completa en AUDIT_FILE_BY_FILE.md y plan S1-S3 en AUDIT_REMEDIATION_PLAN.md

## Convenciones
- Prioridad: Highest, High, Medium
- Estimacion: Story points (SP)
- Tipos Jira: Epic, Story, Task
- Dependencias: indicadas en cada item cuando aplica

## Sprint S1 (Seguridad y Operacion)

### EPIC S1-EP1 - Hardening de arranque y migraciones
- Objetivo: eliminar riesgos operativos por migraciones en runtime y hacer startup determinista.

1. STORY S1-EP1-ST1 - Separar migraciones del startup
- Tipo: Story
- Prioridad: Highest
- SP: 8
- Archivos: app/main.py, scripts/deploy.sh, scripts/start.sh
- Criterios de aceptacion:
  - La app no ejecuta upgrade/stamp en startup.
  - Si schema incompatible, la app falla con mensaje claro.
  - Pipeline ejecuta migraciones antes del arranque de API.

2. TASK S1-EP1-T1 - Crear check de version de schema
- Tipo: Task
- Prioridad: High
- SP: 3
- Archivos: app/main.py, app/db/*
- Criterios de aceptacion:
  - Endpoint/boot check compara revision actual con esperada.
  - Log estructurado cuando hay mismatch.

3. TASK S1-EP1-T2 - Ajustar scripts de despliegue
- Tipo: Task
- Prioridad: High
- SP: 2
- Archivos: scripts/deploy.sh, scripts/clean_and_start.sh
- Criterios de aceptacion:
  - Orden fijo: migrate -> smoke -> run.
  - Rollback definido si migrate falla.

### EPIC S1-EP2 - Hardening WebSocket ticket consume
- Objetivo: reducir riesgo logico de replay/bypass en tickets websocket.

4. STORY S1-EP2-ST1 - Blindar consumo atomico de ticket
- Tipo: Story
- Prioridad: Highest
- SP: 5
- Archivos: app/api/v1/endpoints/ws.py
- Criterios de aceptacion:
  - Script Lua inmutable y versionado.
  - Validacion estricta de formato/longitud de ticket key.
  - TTL y single-use comprobados.

5. TASK S1-EP2-T1 - Suite de abuso WS
- Tipo: Task
- Prioridad: High
- SP: 3
- Archivos: tests/test_ws_ticket_store.py
- Criterios de aceptacion:
  - Test replay bloqueado.
  - Test doble consumo bloqueado.
  - Test payload invalido devuelve error controlado.

### EPIC S1-EP3 - Contrato de rutas canonicas y legacy
- Objetivo: evitar regresiones 404/405 por prefijos/aliases.

6. STORY S1-EP3-ST1 - Definir matriz canonica vs legacy
- Tipo: Story
- Prioridad: High
- SP: 5
- Archivos: app/api/v1/router.py, app/api/v1/routers/platform.py, app/api/v1/routers/delivery.py, DOCS.md
- Criterios de aceptacion:
  - Tabla oficial de rutas y aliases publicada.
  - Deprecated con fecha de retirada.
  - Cambios reflejados en documentacion.

7. TASK S1-EP3-T1 - Test de contrato API
- Tipo: Task
- Prioridad: High
- SP: 3
- Archivos: tests/test_api_versioning.py, tests/test_business_logic_v239.py
- Criterios de aceptacion:
  - Cobertura de rutas sensibles (branding, currency, baselines, approval-builder, slack block-kit).
  - Sin 404/405 inesperados.

## Sprint S2 (Refactor Backend Core)

### EPIC S2-EP1 - Modularizacion Service Desk
- Objetivo: reducir acoplamiento y complejidad en endpoint monolitico.

8. STORY S2-EP1-ST1 - Dividir service_desk por subdominios
- Tipo: Story
- Prioridad: High
- SP: 13
- Archivos: app/api/v1/endpoints/service_desk.py
- Criterios de aceptacion:
  - Nuevos modulos: tickets, kb, cmdb, sla, oncall, templates, analytics.
  - Router agregador delgado (<250 lineas aprox).
  - Sin cambios de contrato externo.

9. TASK S2-EP1-T1 - Renombrado seguro de handlers
- Tipo: Task
- Prioridad: High
- SP: 5
- Archivos: app/api/v1/endpoints/service_desk.py
- Criterios de aceptacion:
  - Sin colisiones de nombres handler/service.
  - Pruebas de regresion en verde.

### EPIC S2-EP2 - Refactor Auth por flujos
- Objetivo: bajar riesgo de regresion en autenticacion.

10. STORY S2-EP2-ST1 - Extraer flujos auth a servicios dedicados
- Tipo: Story
- Prioridad: Highest
- SP: 13
- Archivos: app/api/v1/endpoints/auth.py, app/services/*auth*
- Criterios de aceptacion:
  - Modulos separados: login/refresh/mfa/sso/sessions.
  - Endpoints de auth con responsabilidad minima.
  - Tests auth+mfa verdes.

11. TASK S2-EP2-T1 - Matriz de pruebas de seguridad auth
- Tipo: Task
- Prioridad: High
- SP: 5
- Archivos: tests/test_auth.py
- Criterios de aceptacion:
  - Replay token, one-time challenge, expiracion y revocacion cubiertos.

### EPIC S2-EP3 - Segmentacion AI Chat Service
- Objetivo: separar orquestacion/proveedor/guardrails/herramientas.

12. STORY S2-EP3-ST1 - Reestructurar ai_chat_service
- Tipo: Story
- Prioridad: High
- SP: 13
- Archivos: app/services/ai_chat_service.py
- Criterios de aceptacion:
  - Separacion por capas con interfaces claras.
  - Menor acoplamiento entre modulos.
  - Pruebas unitarias por capa.

13. TASK S2-EP3-T1 - Telemetria y limites IA
- Tipo: Task
- Prioridad: Medium
- SP: 3
- Archivos: app/services/ai_chat_service.py, app/core/config.py
- Criterios de aceptacion:
  - Logs de latencia y errores por proveedor.
  - Timeouts y fallback documentados.

## Sprint S3 (Frontend y deuda transversal)

### EPIC S3-EP1 - Descomposicion de paginas frontend monoliticas
- Objetivo: mejorar mantenibilidad y reducir riesgo de regresion UI.

14. STORY S3-EP1-ST1 - Refactor ServiceDeskPage
- Tipo: Story
- Prioridad: High
- SP: 13
- Archivos: frontend/src/pages/ServiceDeskPage.jsx
- Criterios de aceptacion:
  - Separacion en componentes y hooks por feature.
  - Sin regresion funcional (tests smoke UI).

15. STORY S3-EP1-ST2 - Refactor PortalClientePage
- Tipo: Story
- Prioridad: High
- SP: 8
- Archivos: frontend/src/pages/PortalClientePage.jsx
- Criterios de aceptacion:
  - Mismo contrato de APIs y UX funcional.

16. STORY S3-EP1-ST3 - Refactor ClientsPage y SettingsPage
- Tipo: Story
- Prioridad: Medium
- SP: 13
- Archivos: frontend/src/pages/ClientsPage.jsx, frontend/src/pages/SettingsPage.jsx
- Criterios de aceptacion:
  - Estado compartido aislado en hooks.
  - Componentes reutilizables.

### EPIC S3-EP2 - i18n y consistencia de claves
- Objetivo: evitar drift de traducciones y huecos por idioma.

17. STORY S3-EP2-ST1 - Normalizar estructura i18n por dominio
- Tipo: Story
- Prioridad: Medium
- SP: 5
- Archivos: frontend/src/i18n/appTranslations.js, frontend/src/i18n/portalTranslations.js
- Criterios de aceptacion:
  - Estructura consistente por modulo.
  - Verificador de claves faltantes en CI.

18. TASK S3-EP2-T1 - Script de verificacion i18n en pipeline
- Tipo: Task
- Prioridad: Medium
- SP: 2
- Archivos: frontend/scripts/check_portal_i18n_missing.js
- Criterios de aceptacion:
  - Pipeline falla si faltan claves obligatorias.

### EPIC S3-EP3 - Higiene de artefactos pesados
- Objetivo: reducir ruido y costo de revision.

19. STORY S3-EP3-ST1 - Politica de artefactos grandes
- Tipo: Story
- Prioridad: Medium
- SP: 3
- Archivos: frontend/npm-ls.json, frontend/package-lock.json, alembic/versions/02be3a225710_autogen_all_models.py
- Criterios de aceptacion:
  - Guia de commit para ficheros grandes.
  - Estrategia de split para migraciones autogeneradas voluminosas.

## Dependencias clave
- S1-EP1-ST1 antes de cualquier cambio de despliegue de S2.
- S1-EP3-ST1 antes de refactor de rutas en S2.
- S2-EP2-ST1 y S2-EP1-ST1 antes de S3 smoke UI completos.

## Definicion de Done (global)
- Ruff en verde.
- Tests de regresion del dominio en verde.
- Documentacion actualizada en DOCS.md.
- Sin cambios de contrato API sin versionado o alias de compatibilidad.
