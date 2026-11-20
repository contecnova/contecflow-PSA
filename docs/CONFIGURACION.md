# Configuración del operador

Reorganizada el 18-11-2026. El estado de antes, medido, está en
[CONFIGURACION_INVENTARIO.md](CONFIGURACION_INVENTARIO.md).

## Criterio

- **Toda** la configuración vive en **Configuración** (`/settings/:seccion`).
  En el menú hay una sola entrada. Los módulos se quedan con lo operativo y
  **no llevan botón «Configurar»** (decisión del 19-11-2026). Solo hay un enlace
  contextual «Ir a Configuración» donde una acción está desactivada o falla por
  falta de configuración (p. ej. «Invitar el bot» sin bot activado, «Traer de
  Teams, Zoom o Meet» sin conectores, sincronizar informes de Microsoft 365 sin
  secreto, agente autónomo apagado). El aviso explica qué falta y el enlace sale
  solo si el usuario tiene la capacidad de la sección (`puede('<capacidad>')`).
  El test `configuracionUnica.test.ts` exige que ningún módulo movido use
  `ajustes.configurar`.
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
| | `vacations` Vacaciones (derecho anual; máximo asignable `VACATION_MAX_DAYS_ENTITLED`, que solo edita admin) | admin, hr | pestaña |
| | `horas-extra` Horas extra | admin, hr | Horas extra → pestaña Configuración |
| Proyectos y trabajo | `project-templates` Plantillas | admin, pm | `/project-templates` |
| | `issue-types` Tipos de tarea | admin, pm | `/issue-types` (+ pestaña «Tipos tarea», retirada) |
| | `project-workflows` Flujos de estado | admin, pm | `/settings/project-workflows` |
| | `custom-fields` Campos personalizados (por proyecto / globales) | admin, pm (globales: admin) | `/custom-fields` + pestaña «Campos extra» |
| | `project-permissions` Permisos de proyecto | admin, pm | `/project-permissions` |
| | `cartera` Entrada a la cartera: criterios de puntuación y fases (stage-gate) | admin, pm (`cartera.gestionar`) | Entrada a la cartera → pestaña Configuración (19-11-2026) |
| Service desk | `sd` Service desk (17 subapartados) | admin; pm, team_lead y hr solo respuestas rápidas | Service desk → pestaña Configuración |
| | `sla-calendars` Calendarios de SLA | admin, pm | `/sla-calendars` |
| | `sd-workflows` Diseñador de flujos (abre `/sd/workflow-designer`) | admin, pm | entrada del menú Soporte |
| | `sd-agente` Agente autónomo: encendido, modo, umbrales, playbooks de serie | admin (`sd.administrar`) | Herramientas → Agente → pestaña Configuración (19-11-2026; antes la veía el equipo en solo lectura) |
| | `sd-autorresolucion` Autorresolución: umbrales, cierre automático, validación, lote | admin (`sd.administrar`) | Herramientas → Autorresolución → tarjeta Configuración (19-11-2026) |
| | `sd-voz` Agente de voz: saludo, idioma, silencio, teclas, palabras clave | admin (`sd.administrar`) | Herramientas → Voz → pestaña Configuración (19-11-2026) |
| | `cmdb-software` Software y vulnerabilidades: fuentes de avisos (OSV, NVD, GitHub, EPSS, KEV, endoflife.date) con credenciales cifradas, sincronización, SLA de remediación por severidad, licencias permitidas/prohibidas, ticket automático | admin (`software.config`) | nueva (19-11-2026), con las conexiones de escaneo SSH/WinRM/API (credenciales cifradas). Sin botón en el módulo: la CMDB avisa donde falta configuración y enlaza aquí solo a quien tiene `software.config`. Auditada (`sw_config`, `sw_scan_connection`, sin secretos) |
| Finanzas | `rates` Tarifas | admin, pm | `/rate-cards` + pestaña «Tarifas» |
| | `user-costs` Estructura de coste | admin, hr | `/user-costs` |
| | `proveedores` Proveedores: plantillas de contrato, tipos de servicio, unidades de cobro y umbrales `PROVEEDORES_*` (`proveedores.config`). La pantalla de proveedores no tiene botón «Configurar»: si a una acción le falta un catálogo, su aviso lo dice y enlaza aquí (solo a quien tiene `proveedores.config`). La aprobación por importe de estados de cuenta se diseña en `approval-workflows` (tipo «Estado de cuenta de proveedor», `supplier_statement`, revisión 191) | admin, pm | nueva (19-11-2026, revisión 189) |
| Aprobaciones y políticas | `approval-workflows` Flujos de aprobación | admin | `/settings/approval-workflows` (pm y team_lead lo veían; las escrituras son de admin) |
| | `policies` Políticas y reglas | admin | `/settings/policies` |
| IA e idiomas | `ai-hub` Proveedores de IA | admin | `/ai-hub` (pm: Enrutado y acciones daban 403) |
| | `ai-governance` Gobierno de IA por módulo | admin | `/governance` |
| | `idiomas` Idiomas | admin | pestaña |
| | `traduccion` Traducción | admin | pestaña |
| | `ia-asignacion` Asignación por IA: modo del motor, embeddings, umbrales, auto-asignación | admin, hr (`ia.asignacion_config`) | `/semantic-engine` → pestaña Configuración (19-11-2026; pm la veía y le daba 403 al guardar) |
| | `reuniones` Asistente de reuniones: consentimiento, retención de audio y transcripción, traducción, STT externo, Teams, Zoom, Meet, bot invitado y RGPD por persona | admin (`reuniones.config`) | Nueva (19-11-2026, `docs/ASISTENTE_DE_REUNIONES.md`); `/meetings-ai` queda operativo, sin botón «Configurar» (solo avisos con enlace si falta bot o conector) |
| Integraciones | `integrations` Credenciales | admin | pestaña |
| | `esign` Firma electrónica | admin | pestaña |
| | `m365` Microsoft 365 | admin | `/m365` |
| | `m365-informes` Informes de Microsoft 365: credenciales de Graph para uso y adopción | admin | Plataforma de datos → panel Office 365 → pestaña Configuración (19-11-2026) |
| | `git` Git: webhooks de GitHub y GitLab, secreto, eventos, pasos (solo lectura) | admin, pm (`proyectos.gobierno`) | `/git` → pestaña Configuración (19-11-2026) |
| | `jira` Jira | admin | `/jira-integration` (pm daba 403 al cargar) |
| | `enterprise` SSO, webhooks y OAuth | admin | `/enterprise` |
| | `webhook-log` Registro de webhooks | admin | `/webhook-log` |
| | `developer` Portal de desarrolladores | admin, pm | `/developer` |
| | `import` Importar datos | admin, pm | `/import` |
| Seguridad y GRC | `session` Sesión | admin | pestaña |
| | `mfa` Mi verificación en dos pasos | todos | `/mfa` |
| | `grc` GRC y segregación de funciones | admin | `/grc` |
| | `chat-admin` Administración del chat (y meses de retención propuestos `CHAT_RETENTION_PROPOSED_MONTHS`) | admin | `/settings/chat-admin` (no estaba en el menú) |
| Portal de clientes | `public-forms` Formularios públicos | admin, pm | `/public-forms` |
| | `portal-translations` Traducciones del portal | admin | Service desk → Configuración → Traducciones del portal |
| Alertas y métricas | `alert-config` Alertas · `metrics` Métricas | admin | pestañas |
| Sistema | `runtime-flags` Config. dinámica · `log-level` · `system-state` | admin | pestañas |

Son 12 grupos y 58 secciones (19-11-2026, contadas en el catálogo
`SECCIONES` de `frontend/src/pages/settings/catalogoDeAjustes.tsx`: integraciones
10; empresa, proyectos y service desk 7; IA 6; personas 5; seguridad 4;
finanzas y sistema 3; aprobaciones, portal y alertas 2. La tabla muestra las de
la reorganización y las movidas después; el «67» anterior estaba mal contado).

**Valores de negocio que eran fijos (19-11-2026, `app/services/settings_service/valores_de_negocio.py`).**
Ajustes por empresa del registro en vivo, validados al guardarlos (código
`ajuste_valor_no_valido`) y auditados como cualquier ajuste (`record_change`,
ámbito `runtime`). Las pantallas los leen en `GET /settings/org-defaults` →
`propuestas` (`usePropuestas()`):

| Clave | Por defecto | Validación | Sección |
|---|---|---|---|
| `CHANGE_CANARY_RAMP_PCT` | `1,5,25,50,100` | 2-10 enteros 1-100, crecientes, el último 100 | `sd` → Escalado y avisos (grupo `service_desk`) |
| `CHANGE_CANARY_FIRST/STEP/LAST_MINUTES` | 30 / 45 / 60 | 5-1440 (una fase acepta ≥ 5) | `sd` → Escalado y avisos |
| `CHAT_RETENTION_PROPOSED_MONTHS` | 24 | 1-120, ≥ `RETENTION_MIN_DAYS` en meses de 30 días, ≤ tope del chat de la empresa | `chat-admin` → Retención (grupo `audit`) |
| `VACATION_MAX_DAYS_ENTITLED` | 60 | 1-366, ≥ `DEFAULT_VACATION_DAYS_PER_YEAR` (y este ≤ el máximo) | `vacations` (grupo `locale`, solo admin) |
| `PERF_REMINDER_WINDOW_DAYS` | 7 | 1-90 | `runtime-flags` → Automatizaciones |
| `PERF_REMINDER_UNDATED_CYCLE_DAYS` | 30 | 1-365 | `runtime-flags` → Automatizaciones |
| `PERF_STALLED_CYCLE_DAYS` | 45 | 1-365 | `runtime-flags` → Automatizaciones |
| `PERF_STALLED_COMPLETION_PCT` | 50 | 0-100 | `runtime-flags` → Automatizaciones |

**Se quedan en su módulo, porque son trabajo del día a día y no ajustes:**

- El cuadrante de turnos y el mapa de cobertura pasan de Configuración de
  ausencias a pestañas de Ausencias, para admin y RRHH.
- Las herramientas del service desk (asignación, autorresolución, correlación,
  agente, voz) en su parte operativa: cifras, ejecutar, valorar, registro y
  propuestas del agente, playbooks y sesiones de llamada. Su configuración salió
  el 19-11-2026 (`sd-agente`, `sd-autorresolucion`, `sd-voz`).
- Asignación IA: perfiles, prueba y estadísticas, y «Reconstruir embeddings» y
  «Auto-generar perfiles» (son acciones, no ajustes).
- Git: pull requests y despliegues. Entrada a la cartera: las propuestas.
  Plataforma de datos: informes y adopción de Office 365 y «Sincronizar».

**Configuración que no es global y por eso no se mueve:**

- **Portal de cada cliente** (`pages/clients/ClientsPageTabs.tsx`, ficha del
  cliente → Portal → subpestaña Configuración): es un dato de ese cliente (qué
  ve su portal), no un ajuste de la empresa. Vive con el cliente, como sus
  contactos o contratos.
- **Microsoft 365** (`pages/M365Page.tsx`, pestaña Configuración): la página
  entera ya está montada dentro de Configuración (`/settings/m365`); su pestaña
  es una guía y el estado de las variables de entorno de la instalación, no un
  formulario. No se unifica con `m365-informes`: aquella son variables de
  entorno (calendario, hitos, Teams) y esta credenciales de Graph por empresa
  guardadas cifradas (`bi_o365_service`) para los informes de uso. Son dos
  almacenes distintos y pueden ser dos aplicaciones de Entra distintas. Por
  eso son dos secciones seguidas en Integraciones.
- **Conectores y fuentes con su propio «Configurar»** (Plataforma de datos →
  ETL `BiEtlPanel`, ALM → Uso → Fuentes `FuentesPanel`): cada uno configura esa
  conexión concreta (un objeto que se da de alta y de baja), igual que una
  integración OAuth. Se quedan junto a su lista.
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
- `/git?tab=config` lleva a `/settings/git` (19-11-2026).
- `/portfolio/intake?tab=config` lleva a `/settings/cartera` (19-11-2026).
- `/semantic-engine?tab=config` (o `?tab=overview`, el id que tenía) lleva a
  `/settings/ia-asignacion` (19-11-2026).
- Las pestañas de los paneles (Office 365 en Plataforma de datos; Agente, Voz y
  Autorresolución en Service desk → Herramientas) no tenían URL propia: no hay
  nada que redirigir. Ya no llevan botón «Configurar»; solo el aviso con enlace
  cuando falta configurar (ver «Criterio»).

**GRC de lo movido el 19-11-2026.** Cada sección pide la capacidad que coincide
con la guarda del backend (mínimo privilegio): quien no puede guardar ya no ve
el formulario (antes el equipo veía la configuración del agente en solo lectura
y pm la de Asignación IA, con 403 al guardar). Auditoría: Entrada a la cartera
(`portfolio_criterion`, `portfolio_gate`) y Agente autónomo
(`sd_autonomous_agent`) ya se auditaban. **No se auditaban** Voz, Autorresolución
e informes de Microsoft 365; desde ahora sí: `sd_voice_config`,
`sd_auto_resolution_config` y `bi_o365_config` con antes y después (el secreto de
Graph nunca: `get_config` solo da `secret_puesto`, y `metadata.secreto_cambiado`
dice si se cambió). Git es solo lectura (el secreto se pone en Credenciales).
Test: `tests/test_configuracion_movida_auditada.py`.

**Secciones cuya API vive fuera de /settings (cierre del 19-11-2026).** Costes
(`costes.config`, `/user-costs`), Portal de desarrolladores e Importación
(`integraciones.desarrollo`, `/developer`) y Formularios públicos
(`portal.formularios`, `/forms`) ya no llevan el módulo `settings` en la
capacidad: su API guarda con `requiere_capacidad` y esas rutas no están bajo
/settings, así que con módulo un rol personalizado que cierra Ajustes habría
perdido rutas que hoy tiene. La sección se ve igual que antes: la tapa
`puedeVerSeccion` por la ruta `/settings/<sección>` (`blocked_routes`). Tarifas e
Importación siguen apareciendo solo a dirección y PM (`tarifas.config`,
`integraciones.desarrollo`); su API escribe con `tarifas.gestionar` e
`integraciones.importar` (gestores), los mismos roles que sus `require_*` de antes.
Calendarios SLA: la sección y su API piden `sd.disenar_flujos` (dirección y PM).
El derecho de vacaciones de una persona (Personas → Vacaciones) queda auditado
(`vacation_balance`, antes y después, quién). Test:
`tests/test_guardas_por_capacidad_cierre_2026_11_19.py`.

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
