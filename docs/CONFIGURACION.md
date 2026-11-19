# Configuración del operador

Reorganizada el 18-11-2026. El estado de antes, medido, está en
[CONFIGURACION_INVENTARIO.md](CONFIGURACION_INVENTARIO.md).

## Criterio

- **Toda** la configuración vive en **Configuración** (`/settings/:seccion`).
  En el menú hay una sola entrada. Los módulos se quedan con lo operativo y,
  para quien tiene permiso, un botón **Configurar** que lleva a su sección.
- **Cada ajuste está en un solo sitio.** Lo que estaba en dos sitios se ha
  quitado de uno (ver «Duplicados resueltos»); el otro sitio enlaza.
- **Solo ves lo que puedes usar.** Cada sección declara su **capacidad** de la
  matriz de permisos (19-11-2026; `app/core/capacidades.py`, p. ej.
  `ausencias.config`, `sd.config`, `proyectos.config`; `org.administrar` para lo
  de administración; `plataforma.empresas` solo superadmin; MFA sin capacidad),
  alineada con lo que el backend deja escribir. Una sección que daría 403 no aparece. Pedirla
  por URL lleva a `/403`. El bloqueo por ruta de cada usuario (`blocked_routes`)
  se aplica también con la ruta antigua de la pantalla.
- **Mismo aspecto.** Las secciones propias usan `SeccionDeAjustes` y el kit. Las
  pantallas de módulo montadas dentro se pintan como sección sin tocarlas: con el
  contexto `IncrustadaEnAjustes` (`components/layout/incrustacion.ts`),
  `PageShell` no añade relleno y `PageHeader` pasa a `<h2>` de tamaño de sección.
- **Guardar.** Las secciones con formulario usan borrador y botón Guardar. Tras
  cualquier escritura, el refresco global (`services/api/refrescoTrasEscritura.ts`)
  actualiza las pantallas.

## Piezas

| Pieza | Fichero |
|---|---|
| Catálogo: grupos, secciones, roles, rutas antiguas, ids retirados | `frontend/src/pages/settings/catalogoDeAjustes.tsx` |
| Pantalla: navegación agrupada, buscador y panel | `frontend/src/pages/SettingsPage.tsx` (+ `.css`) |
| Rutas `/settings`, `/settings/:seccion` y redirecciones | `frontend/src/App.tsx` (`RedirigirAAjustes`) |
| Menú (una entrada) y miga de pan con el nombre de la sección | `frontend/src/components/layout/Layout.tsx` |
| Textos (`ajustes.g_*`, `ajustes.s_<id>`, `ajustes.s_<id>_d`) | `frontend/src/i18n/langs/{es,en,zh}.mjs` |
| Test | `frontend/src/__tests__/configuracionUnica.test.ts`, `tests/test_ajustes_generales_una_fuente.py` |

- **Buscador.** Busca en el título, en la descripción (que nombra los
  subapartados, por ejemplo «turnos, jornadas, festivos») y en el grupo, sin
  distinguir acentos.
- **Pantalla estrecha.** Por debajo de 900 px, la lista lateral pasa a un
  desplegable agrupado.
- **Subpestañas.** `?sub=<id>` abre una subpestaña de la sección. Funciona en
  Ausencias, Service desk y Campos personalizados.

## Estructura

| Grupo | Sección (`/settings/<id>`) | Roles | Antes |
|---|---|---|---|
| Empresa y marca | `setup` Puesta en marcha | admin | pestaña |
| | `general` General (moneda, zona, idioma, jornada) | admin | pestaña (sin efecto, ver abajo) + Config. dinámica → Locale |
| | `branding` Marca | admin | pestaña |
| | `offices` Sedes | admin | pestaña |
| | `depts` Departamentos y áreas | admin, hr | pestaña |
| | `numbering` Numeración | admin | pestaña |
| | `organizations` Empresas de la plataforma | superadmin | `/organizations` (admin de empresa la veía y todo le daba 403) |
| Personas y jornada | `users` Usuarios | admin, hr (alta, baja y borrado solo admin) | pestaña |
| | `roles` Roles y permisos | admin | pestaña |
| | `ausencias` Ausencias: tipos, documentos, turnos, jornadas, festivos, personas y saldos, horario, acceso especial, ejemplos | admin, hr | Ausencias → pestaña Configuración |
| | `vacations` Vacaciones (derecho anual) | admin, hr | pestaña |
| | `horas-extra` Horas extra | admin, hr | Horas extra → pestaña Configuración |
| Proyectos y trabajo | `project-templates` Plantillas | admin, pm | `/project-templates` |
| | `issue-types` Tipos de tarea | admin, pm | `/issue-types` (+ pestaña «Tipos tarea», retirada) |
| | `project-workflows` Flujos de estado | admin, pm | `/settings/project-workflows` |
| | `custom-fields` Campos personalizados (por proyecto / globales) | admin, pm (globales: admin) | `/custom-fields` + pestaña «Campos extra» |
| | `project-permissions` Permisos de proyecto | admin, pm | `/project-permissions` |
| Service desk | `sd` Service desk (17 subapartados) | admin; pm, team_lead y hr solo respuestas rápidas | Service desk → pestaña Configuración |
| | `sla-calendars` Calendarios de SLA | admin, pm | `/sla-calendars` |
| | `sd-workflows` Diseñador de flujos (abre `/sd/workflow-designer`) | admin, pm | entrada del menú Soporte |
| Finanzas | `rates` Tarifas | admin, pm | `/rate-cards` + pestaña «Tarifas» |
| | `user-costs` Estructura de coste | admin, hr | `/user-costs` |
| Aprobaciones y políticas | `approval-workflows` Flujos de aprobación | admin | `/settings/approval-workflows` (pm y team_lead lo veían; las escrituras son de admin) |
| | `policies` Políticas y reglas | admin | `/settings/policies` |
| IA e idiomas | `ai-hub` Proveedores de IA | admin | `/ai-hub` (pm: Enrutado y acciones daban 403) |
| | `ai-governance` Gobierno de IA por módulo | admin | `/governance` |
| | `idiomas` Idiomas | admin | pestaña |
| | `traduccion` Traducción | admin | pestaña |
| Integraciones | `integrations` Credenciales | admin | pestaña |
| | `esign` Firma electrónica | admin | pestaña |
| | `m365` Microsoft 365 | admin | `/m365` |
| | `jira` Jira | admin | `/jira-integration` (pm daba 403 al cargar) |
| | `enterprise` SSO, webhooks y OAuth | admin | `/enterprise` |
| | `webhook-log` Registro de webhooks | admin | `/webhook-log` |
| | `developer` Portal de desarrolladores | admin, pm | `/developer` |
| | `import` Importar datos | admin, pm | `/import` |
| Seguridad y GRC | `session` Sesión | admin | pestaña |
| | `mfa` Mi verificación en dos pasos | todos | `/mfa` |
| | `grc` GRC y segregación de funciones | admin | `/grc` |
| | `chat-admin` Administración del chat | admin | `/settings/chat-admin` (no estaba en el menú) |
| Portal de clientes | `public-forms` Formularios públicos | admin, pm | `/public-forms` |
| | `portal-translations` Traducciones del portal | admin | Service desk → Configuración → Traducciones del portal |
| Alertas y métricas | `alert-config` Alertas · `metrics` Métricas | admin | pestañas |
| Sistema | `runtime-flags` Config. dinámica · `log-level` · `system-state` | admin | pestañas |

Son 12 grupos y 47 secciones.

**Se quedan en su módulo, porque son trabajo del día a día y no ajustes:**

- El cuadrante de turnos y el mapa de cobertura pasan de Configuración de
  ausencias a pestañas de Ausencias, para admin y RRHH.
- Las herramientas del service desk (asignación, autorresolución, correlación,
  agente).
- La bandeja de aprobaciones (`/approvals`).
- Los informes del AI Hub siguen dentro de su sección, porque son de la misma
  pantalla.

## Redirecciones (enlaces y marcadores de antes)

**Rutas que eran pantallas sueltas.** Las 19 rutas siguientes llevan a
`/settings/<id>` conservando `?query` y `#hash`:

- `/organizations`, `/project-templates`, `/issue-types`, `/custom-fields`,
  `/project-permissions`, `/sla-calendars`, `/rate-cards`, `/user-costs`
- `/ai-hub`, `/governance`, `/m365`, `/jira-integration`, `/enterprise`,
  `/webhook-log`, `/developer`, `/import`, `/mfa`, `/grc`, `/public-forms`

**Rutas que ya eran de Configuración.**

- `/settings/workflows` y `/workflows` llevan a `/settings/project-workflows`.
- `/chat/admin` lleva a `/settings/chat-admin`.
- `/settings/project-workflows`, `/settings/approval-workflows`,
  `/settings/policies` y `/settings/chat-admin` siguen siendo la misma URL.
  Ahora las sirve la pantalla de Configuración.

**Pestañas de antes.**

- `/settings?tab=<id>` lleva a `/settings/<id>`.
- Los ids retirados se traducen con `IDS_ANTIGUOS`: `task-types` → `issue-types`,
  `email-inbound` → `sd?sub=mail`, `fields` → `custom-fields`.
- `/settings` a secas abre la primera sección visible.

**Pestañas de módulo.**

- `/absences?tab=config` lleva a `/settings/ausencias`.
- `/overtime?tab=config` lleva a `/settings/horas-extra`.
- `/service-desk?tab=config[&sub=x]` lleva a `/settings/sd[?sub=x]`.

**Enlaces del backend.** Los de `app/services/puesta_en_marcha.py` apuntan ya a
las secciones nuevas.

## Duplicados resueltos

| Qué | Antes | Ahora |
|---|---|---|
| Moneda, zona, idioma y jornada | General escribía `app_settings.currency/timezone/language/work_hours_per_day`, que no leía nadie. Lo efectivo eran las claves `DEFAULT_*` de Config. dinámica → Locale. | **Una sola fuente**: las claves `DEFAULT_*`. `GET/PATCH /settings/general/{alias}` lee y escribe la clave de ejecución (`ALIAS_DE_EJECUCION`, `app/services/settings_service/generales.py`; valida el tipo, 422 si no cuadra, y audita como Config. dinámica). La migración **185_ajustes_generales_una_fuente** copia el valor que cada empresa puso en General a su clave `DEFAULT_*` si no tenía una, y borra las filas del alias. El arranque ya no las siembra. General se edita con el kit (Select y Input) y Guardar. Config. dinámica oculta esas cuatro claves. |
| Tarifas | Ajustes → Tarifas (`/advanced-config/rate-tables`) y `/rate-cards` escribían la misma tabla `rate_tables` | Una pantalla, la de `/rate-cards` (con excepciones y duplicar). `/advanced-config/rate-tables` queda `deprecated` en la API. |
| Tipos de tarea | Pestaña «Tipos tarea» (`task_types`, sin lector) y `/issue-types` | Solo Tipos de tarea (issue types por proyecto). `/advanced-config/task-types` queda `deprecated`. |
| Vacaciones | Políticas de vacaciones (`vacation_policies`, sin lector) y un saldo calculado con otra fórmula que Ausencias | La sección solo edita el derecho anual (`days_entitled`) y enlaza al saldo de Ausencias → Personas y saldos. `/advanced-config/vacation-policies` queda `deprecated`. |
| Correo entrante | Mismo componente en Ajustes → Email-to-ticket y en Service desk | Solo en Service desk (`/settings/sd?sub=mail`). |
| Avisos del service desk y traducción en Config. dinámica | Los grupos `service_desk` y `traduccion` se editaban también en sus pantallas | Config. dinámica ya no los lista. |
| Campos personalizados | `/custom-fields` y la pestaña «Campos extra», sin relación | Una sección con dos pestañas. Son dos alcances (dos tablas): no se fusionan. |
| Plantillas | `TemplatesSection` exportada sin uso | Borrada. Queda Plantillas de proyecto. |

**Relacionado pero de alcance distinto** (se agrupa, no se fusiona):

- La retención de GRC frente a la del chat.
- Los tres tipos de webhooks: Empresa, Registro y chat.
- Gobierno de IA por módulo frente a AI Hub → Gobierno.
- Los festivos de Ausencias frente a los Calendarios de SLA.
- Las horas SLA de Config. dinámica, que son el respaldo cuando no hay política,
  frente a las políticas SLA del service desk.

El nombre `company_name` de General no tiene lector. Ya no se muestra, y General
enlaza a Marca.

## 403 corregidos

- **RRHH:**
  - Ya no ve los enlaces a Políticas y Flujos ni «Cargar reglas de ejemplo» en
    Ausencias y Horas extra. En su lugar ve un aviso.
  - Ya no ve Alta, Desactivar ni Borrar usuario.
  - Ya no ve crear ni borrar políticas de vacaciones. La pestaña se ha retirado.
- **pm:** ya no ve:
  - Tipos de tarea (la pestaña retirada).
  - El editor de flujos de aprobación.
  - AI Hub y Jira.
- **pm, team_lead y hr en el service desk:** solo ven Respuestas rápidas.
- **Empresas:** solo las ve el superadmin.
- **Enlaces rotos:**
  - `/settings#esign` ahora lleva a `/settings/esign`.
  - `/settings?tab=integrations` (en Service desk) ahora lleva a
    `/settings/integrations`.
