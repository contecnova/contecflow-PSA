# Plan de Remediacion de Auditoria (S1-S3)

Fecha: 24-04-2026
Base: Auditoria exhaustiva archivo a archivo en AUDIT_FILE_BY_FILE.md

## 1. Resumen ejecutivo

- Estado actual validado:
  - Lint backend y tests/scritps: sin errores Ruff.
  - Suites objetivo validadas: test_business_logic_v239 y test_abac_resources en verde.
- Riesgo principal pendiente:
  - Deuda arquitectonica en modulos muy grandes y acoplados.
  - Riesgo operativo en arranque/migraciones.
  - Riesgos de seguridad de contexto (uso avanzado de Redis Lua y superficie amplia de endpoints).

## 2. Priorizacion por sprint

### Sprint S1 (Inmediato, 1-2 semanas) - Reducir riesgo operativo y seguridad

Objetivo: bajar riesgo real de incidente sin refactor profundo.

1) Arranque y migraciones
- Archivo: app/main.py
- Riesgo: medio (operativo).
- Problema: ejecucion de migraciones en startup con subprocess.
- Accion:
  - Separar migraciones del ciclo de arranque de la app.
  - Dejar la app fallar rapido si schema no esta en version esperada.
  - Mover upgrade/stamp a pipeline de despliegue o job de init.
- Verificacion:
  - Despliegues concurrentes sin carrera.
  - Startup determinista y tiempo estable.

2) WebSocket ticket consume
- Archivo: app/api/v1/endpoints/ws.py
- Riesgo: medio (seguridad logica).
- Problema: uso de Redis eval para consumo atomico.
- Accion:
  - Mantener script Lua como constante inmutable y versionada.
  - Validar longitud/formato de claves y TTL antes de evaluar.
  - Añadir pruebas de abuso (ticket replay, ticket truncado, payload invalido).
- Verificacion:
  - Tests de replay y doble consumo en verde.
  - Sin rutas de bypass en autenticacion websocket.

3) Endpoints legacy y prefijos historicos
- Archivos:
  - app/api/v1/router.py
  - app/api/v1/routers/platform.py
  - app/api/v1/routers/delivery.py
- Riesgo: medio (regresion funcional).
- Accion:
  - Documentar rutas canonicas y aliases legacy soportados.
  - Marcar aliases para deprecacion con fecha.
  - Añadir test de contrato para rutas publicas.
- Verificacion:
  - Test de contrato API verde.
  - Sin 404/405 inesperados por alias.

4) Limites y observabilidad de seguridad
- Archivos objetivo:
  - app/main.py
  - app/core/*
  - app/api/v1/endpoints/*
- Riesgo: medio.
- Accion:
  - Endurecer logging de eventos sensibles (auth, mfa, tokens, ws).
  - Confirmar que no se exponen secretos en logs.
  - Revisar timeout/retry/circuit breaker en integraciones criticas.
- Verificacion:
  - Checklist de secretos en logs sin hallazgos.
  - Alarmas basicas de error rate en endpoints criticos.

### Sprint S2 (2-4 semanas) - Reducir deuda estructural en backend

Objetivo: bajar acoplamiento y tamaño en modulos de alto riesgo arquitectonico.

1) Service Desk modularizacion
- Archivo principal: app/api/v1/endpoints/service_desk.py
- Riesgo: alto (tamano + acoplamiento).
- Accion:
  - Dividir por subdominio: tickets, kb, cmdb, templates, oncall, sla, analytics.
  - Consolidar nombres para evitar colisiones entre handlers y services.
  - Mantener router agregador delgado.
- Verificacion:
  - Cobertura de tests igual o mayor.
  - Disminucion de lineas y dependencias por modulo.

2) Auth hardening y separacion de responsabilidades
- Archivo principal: app/api/v1/endpoints/auth.py
- Riesgo: alto (superficie critica + tamano).
- Accion:
  - Extraer flows en servicios: login, refresh, mfa, sso, sesiones.
  - Mantener endpoint ligero con validacion/serializacion.
  - Asegurar pruebas para replay, one-time token y rotacion.
- Verificacion:
  - Tests de auth y mfa en verde.
  - Menor complejidad ciclomatica por archivo.

3) AI chat service segmentacion
- Archivo principal: app/services/ai_chat_service.py
- Riesgo: alto (tamano + acoplamiento).
- Accion:
  - Separar orquestacion, herramientas, prompts, proveedor, guardrails.
  - Definir interfaz unica de proveedor y telemetria.
- Verificacion:
  - Tests unitarios por modulo.
  - Menor acoplamiento import a import.

4) Plantillas y coherencia de rutas
- Archivos:
  - app/api/v1/endpoints/template.py
  - app/api/v1/endpoints/templates.py
- Riesgo: medio (duplica conceptos y rutas similares).
- Accion:
  - Unificar contrato de respuesta para create/full/documents/roles.
  - Mantener un unico source of truth para almacenamiento/validacion.
- Verificacion:
  - Tests de negocio de templates en verde.
  - Sin rutas duplicadas ambiguas.

### Sprint S3 (4-8 semanas) - Frontend y deuda transversal

Objetivo: bajar riesgo de regresion en UI y mejorar escalabilidad de mantenimiento.

1) Paginas monoliticas React
- Archivos principales:
  - frontend/src/pages/ServiceDeskPage.jsx
  - frontend/src/pages/PortalClientePage.jsx
  - frontend/src/pages/ClientsPage.jsx
  - frontend/src/pages/SettingsPage.jsx
- Riesgo: alto (tamano).
- Accion:
  - Dividir por feature slices: containers, presentational, hooks, services.
  - Extraer estado compartido y side effects a hooks dedicados.
- Verificacion:
  - Tests de componentes criticos.
  - Bundle y tiempos de render estables.

2) i18n y consistencia de traducciones
- Archivos:
  - frontend/src/i18n/portalTranslations.js
  - frontend/src/i18n/appTranslations.js
- Riesgo: medio (archivo grande y riesgo de drift).
- Accion:
  - Separar por dominio funcional e idioma.
  - Automatizar chequeo de claves faltantes en CI.
- Verificacion:
  - Script de claves faltantes en verde.

3) Limpieza de artefactos pesados en repo
- Archivos:
  - frontend/npm-ls.json
  - frontend/package-lock.json
  - alembic/versions/02be3a225710_autogen_all_models.py
- Riesgo: medio/alto de mantenibilidad.
- Accion:
  - Revisar politicas de commit para artefactos de gran tamano.
  - Evaluar split/logica incremental en migraciones gigantes.
- Verificacion:
  - Historial de diffs mas pequeno y revisable.

## 3. Plan archivo a archivo (top criticos)

1) app/main.py
- Tipo: entrypoint backend
- Problema: startup con responsabilidad excesiva
- Decision: desacoplar migracion y bootstrap
- Prioridad: S1

2) app/api/v1/endpoints/ws.py
- Tipo: endpoint realtime
- Problema: seguridad logica en consume ticket
- Decision: hardening de validaciones + tests de abuso
- Prioridad: S1

3) app/api/v1/endpoints/service_desk.py
- Tipo: endpoint dominio grande
- Problema: acoplamiento alto
- Decision: modularizacion por subdominio
- Prioridad: S2

4) app/api/v1/endpoints/auth.py
- Tipo: endpoint critico de autenticacion
- Problema: archivo monolitico
- Decision: separar servicios por flujo
- Prioridad: S2

5) app/services/ai_chat_service.py
- Tipo: servicio core IA
- Problema: tamano y responsabilidades mezcladas
- Decision: segmentar orquestacion/proveedor/guardrails
- Prioridad: S2

6) frontend/src/pages/ServiceDeskPage.jsx
- Tipo: pagina frontend
- Problema: complejidad alta
- Decision: dividir en componentes y hooks
- Prioridad: S3

7) frontend/src/pages/PortalClientePage.jsx
- Tipo: pagina frontend
- Problema: complejidad alta
- Decision: dividir por funcionalidades
- Prioridad: S3

8) frontend/src/pages/ClientsPage.jsx
- Tipo: pagina frontend
- Problema: tamano y deuda de estado
- Decision: separar estado y vistas
- Prioridad: S3

9) frontend/src/pages/SettingsPage.jsx
- Tipo: pagina frontend
- Problema: modulo extenso
- Decision: separar secciones y validacion por dominio
- Prioridad: S3

10) app/api/v1/endpoints/template.py y app/api/v1/endpoints/templates.py
- Tipo: endpoints templates
- Problema: potencial duplicidad de contrato
- Decision: unificacion de source of truth
- Prioridad: S2

## 4. Criterios de aceptacion por sprint

S1 listo cuando:
- No hay migraciones automáticas en startup de app.
- Test de websocket ticket consume incluye replay/doble consumo.
- Rutas legacy documentadas y testeadas con contrato.

S2 listo cuando:
- service_desk/auth/ai_chat divididos en modulos con responsabilidades claras.
- Cobertura y regression tests en verde.
- Reduccion medible de lineas y acoplamiento por archivo.

S3 listo cuando:
- Paginas frontend grandes segmentadas sin regresion funcional.
- i18n con chequeo automatico de claves en CI.
- Politica de artefactos grandes definida y aplicada.

## 5. Recomendacion de ejecucion

Orden sugerido:
1) Sprint S1 completo (seguridad + operacion)
2) Sprint S2 backend core
3) Sprint S3 frontend y deuda transversal

Ritmo sugerido:
- Entregas semanales con small PRs por submodulo.
- Nunca mezclar hardening de seguridad y refactor visual en el mismo PR.
- Mantener smoke tests obligatorios por cada merge.
