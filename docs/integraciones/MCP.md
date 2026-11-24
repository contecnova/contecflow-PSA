# Agentes de código por MCP (OpenCode, Claude Code)

*23-11-2026.* Contecflow expone un servidor **MCP** (Model Context Protocol) para que
un desarrollador o un técnico, sin salir de su editor o su terminal, trabaje con sus
tareas, tickets, horas y cambios desde un agente de código como
[OpenCode](https://opencode.ai) o Claude Code. La misma guía, traducida (es/en/zh),
está en la aplicación: **Configuración → Integraciones → Agentes de código (MCP)**
(`/settings/mcp`).

- Código: `app/api/v1/endpoints/mcp.py` (transporte y configuración),
  `app/services/mcp_service.py` (protocolo, gobierno, registro, límites),
  `app/services/mcp_herramientas.py` (herramientas de trabajo diario).
- Pruebas: `tests/test_mcp_agentes_de_codigo_2026_11_23.py` y `tests/test_mcp_2026_11.py`.

## 1. Qué es y qué hace

| Necesidad | Herramienta MCP | Ruta REST equivalente (capacidad) |
|---|---|---|
| Mis tareas | `list_my_tasks` | `GET /tasks` (cualquier sesión) |
| Buscar tareas | `search_tasks` | `GET /tasks` |
| Detalle de una tarea | `get_task` | `GET /tasks/{id}` |
| Comentar una tarea | `add_task_comment` ✎ | `POST /tasks/{id}/comments` (`tareas.trabajar`) |
| Cambiar el estado de una tarea | `change_task_status` ✎ | `PATCH /tasks/{id}` |
| Mis tickets (mi cola) | `list_my_tickets` | `GET /sd/tickets/my-queue` |
| Buscar tickets | `search_tickets` | `GET /sd/tickets` |
| Detalle de un ticket | `get_ticket` | `GET /sd/tickets/{id}` |
| Comentar un ticket | `add_ticket_comment` ✎ | `POST /sd/tickets/{id}/comments` (`sd.trabajar`) |
| Cambiar el estado de un ticket | `change_ticket_status` ✎ | `PATCH /sd/tickets/{id}` |
| Buscar proyectos | `list_projects` | `GET /projects` |
| Imputar horas | `log_time` ✎ | `POST /imputations` (puerta `crear_imputacion_validada`) |
| Cronómetro | `get_timer`, `start_timer` ✎, `stop_timer` ✎ | `/imputations/timer/*` |
| Catálogo de cambios estándar | `list_standard_changes` | `GET /sd/standard-changes` (`sd.completo`) |
| Abrir un cambio | `open_change` ✎ | `POST /sd/changes` (`sd.administrar`) |
| Estado de un cambio | `get_change`, `list_changes` | `GET /sd/changes[/{id}]` |
| Mis notas compartidas | `search_notebook`, `get_notebook_page` | `/notebook/*` (`cuaderno.usar`) |

✎ = escribe. Las tareas y los tickets se pueden nombrar por id o por código/número
(`TSK-042`, `INC-00123`); los proyectos, por id, código o nombre; los cambios, por id o
número (`CHG00042`).

Además siguen las herramientas de NexusAgent (`get_*`, `search_*` y sus escrituras;
README, «External agents (MCP)»), que piden **además** `ia.usar`.

**Mismas reglas que la aplicación.** Cada herramienta llama al mismo servicio que su
ruta REST: transiciones de estado de tareas, tickets y cambios; la puerta de alta de
imputaciones (cierre de periodo, topes diario y semanal, duplicados, horas extra); un
solo cronómetro por persona; el tipo de cambio lo decide el servidor (estándar solo
con un modelo del catálogo que encaje; si no, normal y al CAB al enviarlo con
`submit: true`).

## 2. Activarlo (dirección)

En **Configuración → Agentes de código (MCP)** (`PATCH /api/v1/mcp/estado`, capacidad
`gobierno.administrar`; auditado):

| Ajuste | Por defecto | Qué hace |
|---|---|---|
| Servidor MCP encendido | apagado | Módulo `mcp` de la gobernanza de IA, por empresa. Apagado, todo devuelve 403 `mcp_apagado`. |
| Herramientas que escriben (`MCP_WRITE_MODE`) | `off` | `off`: no se ofrecen. `approval`: cada llamada abre una aprobación «mcp_action» y se ejecuta al aprobarla (`mcp_action_status`). `direct`: se ejecutan. |
| Herramientas de Mi cuaderno (`MCP_NOTEBOOK_ENABLED`) | apagado | Opcional. Aun encendido, cada persona decide qué cuadernos comparte con sus agentes. |
| Llamadas por minuto (`MCP_RATE_LIMIT_PER_MINUTE`) | 60 | Por credencial (o por sesión). 0: sin límite propio. |

No hay botones «Configurar» en los módulos: todo está en esa sección.

## 3. La credencial (cada persona)

En la misma sección, **Mis credenciales MCP** → *Generar credencial* (capacidad
`mcp.usar`, todos los roles):

- **Solo lectura** (`mcp:read`) o **lectura y escritura** (`mcp:write`).
- Caducidad de 1 a 365 días (90 por defecto). La clave (`nxpm_…`) se muestra **una vez**.
- Solo abre `POST /api/v1/mcp`: con ella no se llama al resto de la API ni se gestionan
  credenciales (`credenciales_delegadas.RUTAS_VEDADAS`, que incluye `/api/v1/mcp/`).
- Actúa **como su dueño** y en la **empresa en la que se creó**.
- Se revoca en la misma pantalla; una clave revocada o caducada devuelve 401.

También valen una clave de API de alcance `read`/`write`/`admin` o un token OAuth del
portal de desarrolladores con esos alcances o con `mcp:read`/`mcp:write`.

Guárdala en una variable de entorno, **nunca en un fichero del repositorio**:

```bash
# macOS / Linux (~/.zshrc, ~/.bashrc)
export CONTECFLOW_MCP_TOKEN="nxpm_…"
```

```powershell
# Windows (para el usuario)
[Environment]::SetEnvironmentVariable("CONTECFLOW_MCP_TOKEN", "nxpm_…", "User")
```

## 4. Conectar OpenCode

`opencode.jsonc` global (`~/.config/opencode/opencode.jsonc`) o del proyecto
(`opencode.jsonc` en la raíz). Servidor remoto con URL y cabeceras; OpenCode sustituye
`{env:…}` al arrancar:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "contecflow": {
      "type": "remote",
      "url": "https://<tu-servidor>/api/v1/mcp",
      "enabled": true,
      "headers": {
        "Authorization": "Bearer {env:CONTECFLOW_MCP_TOKEN}"
      }
    }
  }
}
```

Comprueba la conexión con `opencode mcp list` y, dentro de OpenCode, pide por ejemplo
«enséñame mis tickets abiertos».

## 5. Conectar Claude Code

Por la línea de órdenes (transporte HTTP; `--scope user` para todos tus proyectos,
`project` para compartirlo en `.mcp.json`, `local` solo para este):

```bash
claude mcp add --transport http --scope user contecflow https://<tu-servidor>/api/v1/mcp \
  --header "Authorization: Bearer $CONTECFLOW_MCP_TOKEN"
```

O el `.mcp.json` equivalente en la raíz del proyecto (Claude Code expande `${…}` al
arrancar, así que la clave no queda en el repositorio):

```json
{
  "mcpServers": {
    "contecflow": {
      "type": "http",
      "url": "https://<tu-servidor>/api/v1/mcp",
      "headers": {
        "Authorization": "Bearer ${CONTECFLOW_MCP_TOKEN}"
      }
    }
  }
}
```

Comprueba con `claude mcp list` o `/mcp` dentro de Claude Code. Las herramientas
aparecen como `mcp__contecflow__<herramienta>`.

## 6. Ejemplos de uso

- «¿Qué tareas tengo esta semana?» → `list_my_tasks`.
- «Resume el ticket INC-00123 y añade una nota interna con lo que he probado» →
  `get_ticket`, `add_ticket_comment` (interna por defecto; `is_public: true` solo para
  una respuesta que el cliente deba ver).
- «Pasa TSK-042 a revisión e imputa 2 horas de hoy» → `change_task_status`
  (`in_review`), `log_time`.
- «Arranca el cronómetro en PRJ-007 … páralo» → `start_timer`, `stop_timer`.
- «Abre un cambio estándar para desplegar la 2.4 y dime su estado» →
  `list_standard_changes`, `open_change` (`standard_model_id`, `submit: true`), `get_change`.
- «Busca en mis notas lo que apunté sobre la caché» → `search_notebook`, `get_notebook_page`
  (solo cuadernos que hayas compartido con tus agentes).

## 7. Permisos

- **Capacidad.** Cada herramienta exige la MISMA capacidad que su ruta REST (tabla del
  §1; `Politica` en `mcp_herramientas.py`). Además: módulo cerrado por el rol
  (`modulos.modulo_cerrado`), matriz GRC (`grc_enforce.decidir`, módulo y acción de la
  ruta) y ABAC (`enforce_abac` del prefijo de la ruta y, en tareas, del recurso).
  `tools/list` solo ofrece las que la persona puede usar; `tools/call` devuelve el motivo
  con código (`mcp_herramienta_sin_capacidad`, `mcp_herramienta_modulo_cerrado`,
  `mcp_herramienta_grc`, `mcp_herramienta_ia`, `mcp_escritura_no_permitida`).
- **Alcance de datos.** El del listado de cada entidad (`task_query_for_user`,
  `scope_ticket_query`, `scope_projects_query`, `scope_change_query`): un empleado o un
  externo ve lo suyo.
- **Empresa.** La de la credencial (`TenantSession`, `TENANT_SESION_SIN_CONTEXTO=cerrar`):
  un ticket de otra empresa no existe (404) para el agente.
- **Escritura.** Solo con `MCP_WRITE_MODE` distinto de `off` **y** una credencial que
  escriba (`write`, `admin`, `mcp:write` o una sesión).
- **Mi cuaderno.** Privado por defecto. El dueño lo comparte en *Mi cuaderno →
  Compartir → «Compartir con mis agentes de código (MCP)»* (fila `notebook_shares` con
  `target_type = agents`, solo lectura, auditada). Solo se leen cuadernos **propios**
  compartidos así; nadie más gana acceso.
- La configuración la cambia `gobierno.administrar`; las credenciales, cada persona
  (`mcp.usar`).

## 8. Seguridad y GRC

- **Auditoría** (`audit_log`, canal `mcp`, con credencial —tipo e id—, empresa, IP y
  agente de usuario):
  - `MCP_CONNECT` en cada `initialize` (nombre y versión del cliente);
  - `MCP_TOOL_CALL` en cada escritura (hecha, fallida o bloqueada) y en las ejecutadas al
    aprobarse; `MCP_TOOL_APPROVAL` al pedir una aprobación;
  - `MCP_TOOL_READ` en cada lectura de notas de Mi cuaderno;
  - alta y revocación de credenciales (`api_keys`), cambios de configuración
    (`mcp_config`) y compartir un cuaderno con los agentes (`notebook`).
- **Registro de uso**: cada llamada en `ai_action_logs` (módulo `mcp`, estado, código,
  IP), con la retención del tipo `ai_action_logs` (Gobernanza → Retención) y el bloqueo
  legal de siempre.
- **Sin datos personales en los registros**: de los argumentos solo se guardan ids,
  estados y cifras; del texto libre (comentarios, descripciones, notas), su longitud. Los
  errores inesperados se registran sin argumentos.
- **Credenciales revocables y con caducidad**; solo abren MCP; nunca gestionan credenciales.
- **Origen**: si llega la cabecera `Origin` y no es de la aplicación (`ALLOWED_ORIGINS`),
  403 `mcp_origen_no_permitido` (DNS rebinding, como pide la especificación).
- Lo que devuelve una herramienta son **datos**: el agente no debe tratarlos como órdenes.
  Revisa lo que propone antes de aceptar una escritura (o usa `approval`).

## 9. Límites

- **Por credencial y minuto**: `MCP_RATE_LIMIT_PER_MINUTE` (60). Al pasarlo, HTTP 429
  con `Retry-After` y error JSON-RPC `-32000` con `data.code = mcp_limite_de_uso`.
  Ventana fija en Redis si lo hay (compartida entre procesos); si no, en memoria.
- **Diario por persona**: `max_actions_per_day` del módulo `mcp` en la gobernanza de IA
  (`ia_limite_diario`).
- **Por clave de API**: `rate_limit_per_hour` (1000) y `rate_limit_per_day` (10000).
- **Listas paginadas**: `page` y `page_size` (≤ 100); la respuesta trae `total`,
  `has_more` y `next_page`. `tools/list` pagina con `cursor`/`nextCursor` (100).
- Textos largos recortados (descripciones 4000 caracteres, comentarios 2000, notas 20000).

## 10. Protocolo

- JSON-RPC 2.0 por **Streamable HTTP** sin flujo de servidor: un mensaje por `POST`,
  respuesta `application/json`. Notificaciones y respuestas del cliente: 202. Lotes:
  400. `GET` y `DELETE`: 405 con `Allow: POST` (no hay canal SSE ni sesión: lo permite
  la especificación, y OpenCode y Claude Code siguen por POST).
- Versiones: `2025-11-25`, `2025-06-18`, `2025-03-26` (se ofrece la primera si el cliente
  pide otra). Cabecera `MCP-Protocol-Version` desconocida: 400.
- Métodos: `initialize`, `ping`, `tools/list`, `tools/call`; `resources/list`,
  `resources/templates/list` y `prompts/list` devuelven listas vacías.
- Herramientas con `title`, `inputSchema` (JSON Schema con descripciones,
  `additionalProperties: false`) y `annotations` (`readOnlyHint`, `destructiveHint`,
  `idempotentHint`, `openWorldHint`).
- Errores: de protocolo, con `error.data.code` del catálogo (`app/core/codigos_de_error.py`,
  fuente `scripts/codemods/errores_con_codigo/mcp.json`); de herramienta, como resultado
  con `isError: true` y `structuredContent.error = {code, params, message}` para que el
  modelo se corrija.

## 11. Resolución de problemas

| Síntoma | Causa y solución |
|---|---|
| 401 | Clave inválida, revocada o caducada, o falta `Authorization: Bearer`. En OpenCode/Claude Code, comprueba que la variable `CONTECFLOW_MCP_TOKEN` existe en el entorno desde el que arrancas el agente. |
| El agente intenta iniciar sesión con OAuth | Llegó un 401: es lo anterior. (En OpenCode, la autodetección de OAuth de un servidor remoto se puede desactivar con `"oauth": false` en su entrada.) |
| 403 `mcp_apagado` | Dirección debe encender el servidor en Configuración → Agentes de código. |
| 403 de alcance de credencial | La credencial no es MCP: necesita `read`, `write`, `admin`, `mcp:read` o `mcp:write` (un token de área, `projects`, `tasks`…, no abre MCP). |
| No aparece una herramienta | Tu rol no tiene su capacidad, la escritura está apagada o la credencial es de solo lectura. Mira la tabla «Herramientas disponibles» de la sección. |
| 429 `mcp_limite_de_uso` | Límite por minuto; reintenta tras `Retry-After` o pide subir `MCP_RATE_LIMIT_PER_MINUTE`. |
| 405 en `GET /api/v1/mcp` | Esperado: no hay canal SSE. El cliente debe usar transporte HTTP (POST). |
| 400 `mcp_version_no_soportada` | El cliente fija una versión del protocolo que no admitimos; actualiza el cliente o el servidor. |
| 403 `mcp_origen_no_permitido` | Se llama desde un navegador de otro origen. Los agentes de terminal no mandan `Origin`. |
| `search_notebook` no encuentra nada | El cuaderno no está compartido con tus agentes, o Mi cuaderno por MCP está apagado en la empresa. |
| `open_change` → `cab_no_configurado` | La empresa no tiene comité de cambios (`SD_CAB_GROUP_ID`): un cambio normal no puede enviarse. |
