# Registro de cambios

Cambios que afectan a quien implanta, configura o usa contecflow, de lo más reciente a lo más antiguo. La versión que informa la API (`VERSION`, `/health`) es la `23.9.3`; el proyecto no publica etiquetas de versión, así que los cambios se agrupan por la migración de base de datos que los acompaña (la cabeza indica en qué punto está una instalación: `alembic current`).

Para actualizar una instalación: [README §11](README.md#11-actualizar-a-una-versión-nueva) y [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md).

## Migraciones 204–212 (24-11-2026)

- **Empresa obligatoria** (208): `organization_id` NOT NULL en 463 tablas (21 exceptuadas y justificadas). Lo que no trae empresa la hereda de su proyecto, ticket o usuario; si no se puede, error con código. Correo del portal único **por empresa**: si una persona tiene cuenta en varias, elige empresa al entrar. [docs/seguridad/empresa_obligatoria.md](docs/seguridad/empresa_obligatoria.md)
- **Chats del portal al nivel del chat interno** (209–211): conversaciones formales, pestaña «Chat» y chat en vivo de Soporte con adjuntos validados, emojis, reacciones, citas, edición y borrado con rastro, «escribiendo…» y «leído». Llamadas y vídeo **solo iniciadas por el operador**, sin grabación con clientes. Un solo chat: las mismas piezas en el interno y en el portal. [docs/portal/CHAT_DEL_PORTAL.md](docs/portal/CHAT_DEL_PORTAL.md)
- **Certificaciones y cumplimiento continuo** (212 y 213): TISAX, NIS2, ISO 27001, SOX, J-SOX e IEC 62443 con biblioteca única de controles, plantillas de proyecto completas, evidencias, auditorías, auditores y certificados. [docs/propuestas/CERTIFICACIONES.md](docs/propuestas/CERTIFICACIONES.md) · [docs/CERTIFICACIONES_CONTENIDO.md](docs/CERTIFICACIONES_CONTENIDO.md) · [docs/CERTIFICACIONES.md](docs/CERTIFICACIONES.md)
  - 21 tablas `cert_*` (organization_id obligatorio, únicos por empresa); la 213 añade `cert_correspondencias.id_semilla` (corregir ids al importar el texto con licencia sin perder enlaces).
  - Biblioteca sembrada por empresa desde `app/data/certificaciones/` (validada, idempotente, puesta al día al arrancar); ISO 27001 y SOC 2 del GRC entran en ella y sus evidencias se enlazan sin copiarlas.
  - Programa desde plantilla: proyecto con tareas RACI (solo lo que aplica según el alcance; las sucesoras heredan dependencias), declaración de aplicabilidad, enlaces tarea↔control y documentos con aprobación.
  - Matriz control × norma × sede × estado, pruebas SOX, cumplimiento continuo (medidas automáticas con evidencia firmada), evidencias sobre Documentos con caducidad, auditorías, hallazgos y CAPA (tareas), auditores y empresas colaboradoras con acceso temporal de solo lectura (`/auditor/:token`, todo registrado), certificados con su ciclo y avisos, incidentes NIS2 con relojes de 24 h / 72 h / 1 mes, proveedores críticos y paquete del auditor firmado (Ed25519).
  - Capacidades `certificaciones.ver|gestionar|auditar|administrar`; SoD (implanta/evalúa, implanta/prueba, corrige/cierra, hace/verifica); auditoría, retención y bloqueo legal, RGPD de auditores externos; Configuración › Seguridad y GRC › Certificaciones; procesos BPM `cert_program`, `cert_audit_capa`, `nis2_incident`; trabajos `cert-vencimientos` y `cert-nis2-relojes`.
- **Salud del cliente** con un único cálculo y datos reales; NPS real (−100 a 100) en BI. README §27.4.
- **Diseño estándar**: campos con la etiqueta del kit (~1.200 migrados), `SelectorDeContexto` para el contexto de cada pantalla, desplegables de ancho común, un solo color para los campos sin rellenar (`--texto-campo-vacio`) y vigilantes que impiden volver atrás. [docs/GUIA_DE_DISENO.md](docs/GUIA_DE_DISENO.md)
- Calidad: `setup test-postgres`, `setup cobertura` y `setup lint-css` (manuales, sin CI ni hooks).
- Roles de sistema sembrados al arrancar en todas las empresas; catálogo BPM sembrado puesto al día al arrancar.

## Migraciones 199–203 (23-11-2026)

- **«Del ticket al PR»** (203): un agente de código propone el arreglo de un ticket como pull request, en un contenedor aislado y con aprobación humana. Módulo opcional por empresa, apagado por defecto. [docs/integraciones/TICKET_A_PR.md](docs/integraciones/TICKET_A_PR.md)
- **Servidor MCP para agentes de código** (OpenCode, Claude Code): credenciales delegadas `mcp:read` / `mcp:write`, apagado por defecto. [docs/integraciones/MCP.md](docs/integraciones/MCP.md)
- **Mi cuaderno** (202): notas personales tipo OneNote, privadas por defecto, con compartición, plantillas, IA y voz. [docs/CUADERNO.md](docs/CUADERNO.md)
- **Políticas de cuenta por empresa** (199): contraseñas, bloqueo, MFA obligatorio, inactividad, restricciones por IP, revocación al desactivar y restablecimiento de contraseña del portal. [docs/seguridad/politicas_de_cuenta.md](docs/seguridad/politicas_de_cuenta.md)
- **Cadena de colaboración con HMAC y un solo cronómetro por persona** (201); esquema pendiente de la auditoría del 22-11-2026 (200).
- Seguridad de entrada y salida (SSRF, correo con IP fijada, subidas), rutas anónimas con contexto de empresa cerrado y registro de auditoría de solo añadir.
- Documentación: el README pasa a ser el manual completo en castellano; la lista de ajustes sale a [docs/REFERENCIA_DE_AJUSTES.md](docs/REFERENCIA_DE_AJUSTES.md); se retiran los informes históricos.

## Migraciones 189–198 (19 a 22-11-2026)

- **Clientes internos** (193): showback, chargeback, portal «Mi departamento» y servicios compartidos. [docs/CLIENTES_INTERNOS.md](docs/CLIENTES_INTERNOS.md)
- **Flujo de demanda configurable** (195). [docs/FLUJO_DE_DEMANDA.md](docs/FLUJO_DE_DEMANDA.md)
- **Proveedores y externalización** (189) y **portal del proveedor** con aprobación por importe y fuentes de medición (191). [docs/PROVEEDORES_Y_EXTERNALIZACION.md](docs/PROVEEDORES_Y_EXTERNALIZACION.md)
- **CMDB de software, composición y vulnerabilidades**, con índice de riesgo. [docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md](docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md)
- **Asistente de reuniones**: Teams, Zoom, Meet, bot invitado y grabación propia. [docs/ASISTENTE_DE_REUNIONES.md](docs/ASISTENTE_DE_REUNIONES.md)
- **Cambios estándar y portal** (198).
- **Observabilidad en Docker**: `setup docker` levanta la aplicación con Prometheus, Alertmanager y Grafana con paneles. [docs/OBSERVABILIDAD.md](docs/OBSERVABILIDAD.md)
- Matriz única de permisos por capacidades; umbrales de semáforo por métrica y empresa; todos los errores con código traducible; renovación de la sesión antes de caducar; configuración única en la pantalla Configuración.

## Migraciones 179–188 (16 a 18-11-2026)

- **Horas extra y trabajo fuera de horario** aprobados por flujos (184), activados por defecto con control «avisar».
- **Turnos en el planificador y ausencias por horas** con saldos, bolsa y reglas (180).
- **Canales en tiempo real**: hilos de Slack, adjuntos de WhatsApp, chat del portal por WebSocket.
- Ajustes por empresa leídos por empresa, roles reales e idioma de salida; marca de empresa.
- **Licencias y hardware (ALM)**: uso real por conectores, recuperación de licencias, cumplimiento y software no controlado.
- Portal de clientes en 8 idiomas; traducción en tiempo real del chat; periodo libre en informes.
- Kit de componentes común en todo el frontend (reglas de ESLint que lo imponen).

## Anteriores

- **Motor de políticas común** (165) para aprobaciones, gastos (166) y ausencias (167). [docs/APPROVAL_ENGINE.md](docs/APPROVAL_ENGINE.md)
- Multiempresa con aislamiento en la sesión y RLS de PostgreSQL; Service Desk ITSM completo; BPM; BI; IA con gobernanza.
