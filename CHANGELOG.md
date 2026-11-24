# Registro de cambios

Cambios que afectan a quien implanta, configura o usa contecflow, de lo más reciente a lo más antiguo. La versión que informa la API (`VERSION`, `/health`) es la `23.9.3`; el proyecto no publica etiquetas de versión, así que los cambios se agrupan por la migración de base de datos que los acompaña (la cabeza indica en qué punto está una instalación: `alembic current`).

Para actualizar una instalación: [README §11](README.md#11-actualizar-a-una-versión-nueva) y [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md).

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
