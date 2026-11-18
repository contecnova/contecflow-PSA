# Inventario de la configuración del operador

**Estado medido el 18-11-2026, antes de la reorganización** (commit `a204e7f1`, `main`).

Referencia del estado ANTERIOR de todo lo que el operador configura: dónde está cada ajuste, qué endpoint y qué tabla toca, quién lo ve en el frontend, qué exige el backend, qué diseño usa y qué falla. Todo lo de aquí se ha comprobado leyendo el código (grep y AST de los decoradores `@router` y de los `Depends(...)`). Lo que no se comprobó se marca como **[no verificado]**.

Convenciones:

- **Roles back**: la dependencia de FastAPI (`app/core/deps.py:188-205`): `require_admin` = admin; `require_admin_or_hr` = admin+hr; `require_admin_or_pm` = admin+pm; `require_any_manager` = admin+pm+team_lead+hr; `require_internal_user` = los cinco internos; `require_superadmin` = solo superadmin de plataforma. El superadmin pasa siempre `RequireRole` (`deps.py:159`). `get_current_user` = cualquier sesión.
- **Roles front**: `ProtectedRoute roles=[...]` en `frontend/src/App.tsx` (si no casa, redirige a `/403`, `App.tsx:293-294`), `TAB_GROUPS[].tabs[].roles` en `SettingsPage.tsx` y `NAV_GROUPS[].items[].roles` en `components/layout/Layout.tsx`. `hasRole` del frontend NO trata al superadmin como comodín (`context/AuthContext.tsx:226-229`).
- **Diseño**: «kit» = `SeccionDeAjustes` + componentes de `frontend/src/components/ui` (`Button`, `Select`, `Switch`, `Checkbox`, `GrupoDeOpciones`, `Input`, `Tabla`, `Modal`…). «propio» = HTML suelto (`<input>`, `<textarea>`, `<select>`, `<table>`, `style={{…}}`) o contenedores con clases propias.

---

## 1. `/settings` (23 pestañas en 3 grupos)

`frontend/src/pages/SettingsPage.tsx` (152 líneas). `TAB_GROUPS` en las líneas 34-76; el render por pestaña en 127-149. La pestaña inicial sale de `?tab=<id>` (líneas 89-97); **no lee `#hash`**.

- Ruta: `ProtectedRoute roles={['admin','hr','pm']}` (`App.tsx:429-432`).
- Menú: la entrada `/settings` del grupo «configuracion» tiene `roles: ['admin']` (`Layout.tsx:291`). **hr y pm pueden abrir la ruta pero no la ven en el menú**: solo llegan por enlaces o tecleando la URL. hr vería Usuarios, Vacaciones y Departamentos; pm solo Tipos de tarea.
- Secciones: `pages/SettingsPageSections.tsx` (2 051 líneas) y `pages/settings-sections/*` (`SettingsAdvancedSections.tsx` 1 040, `TraduccionSection.tsx` 562, `MarcaSection.tsx` 83, `PuestaEnMarchaSection.tsx` 56, `SeccionDeAjustes.tsx`).
- Hay **dos objetos `settingsApi`** distintos: `services/settingsApi.ts:38` (general + departamentos) y `services/api/settings.ts:134` (log level, runtime, integraciones, marca, puesta en marcha, traducciones). Los dos llaman a `GET /settings/general`. `SettingsAdvancedSections.tsx:25-26` importa los dos (uno con alias `ajustesGeneralesApi`).

### 1.1 Pestañas

| # | Grupo | id | Componente (fichero:línea) | Endpoints (back: dependencia) | Roles front | ¿Coincide? |
|---|---|---|---|---|---|---|
| 1 | personal | `setup` | `PuestaEnMarchaSection` (`settings-sections/PuestaEnMarchaSection.tsx:23`) | `GET /settings/setup-checklist` (admin, `settings.py:45`) | admin | Sí |
| 2 | personal | `general` | `GeneralSection` (`SettingsPageSections.tsx:187`) | `GET /settings/general` (current_user, `settings.py:81`); `PATCH /settings/general/{key}` (admin, `settings.py:88`) | admin | Sí |
| 3 | personal | `session` | `SessionSecuritySection` (`:1966`) | los mismos que General; claves `idle_timeout_enabled`, `idle_timeout_minutes` | admin | Sí |
| 4 | personal | `users` | `UsersSection` (`:237`) | `GET /users` (internal_user); `GET /users/{id}` (current_user); `POST /users` (**admin**, `users.py:215`); `PATCH /users/{id}` (current_user + ABAC); `DELETE /users/{id}` y `/permanent` (**admin**); `GET /advanced-config/roles`; `GET /settings/departments`; `GET /organizations` (superadmin; solo se pide si `is_superadmin`, `:262`) | admin, **hr** | **No**: hr ve «Nuevo usuario» (`:320`), activar/desactivar y borrar, que dan 403 |
| 5 | personal | `vacations` | `VacationSection` (`:891`) | `GET /advanced-config/vacation-policies` (admin_or_hr); `POST`/`DELETE` (**admin**, `advanced_config.py:251,262`); `GET`/`PATCH /advanced-config/vacation-balances` (admin_or_hr) | admin, **hr** | **No**: hr crea o borra política y recibe 403 |
| 6 | personal | `depts` | `DepartmentsSection` (`:1516`) + `AreasSection` (`:1585`) | `/settings/departments` CRUD y `/settings/areas` CRUD (lectura current_user; escritura admin_or_hr) | admin, hr | Sí |
| 7 | personal | `offices` | `OfficesSection` (`:1388`) | `/advanced-config/offices` (GET current_user; escritura admin) | admin | Sí |
| 8 | personal | `idiomas` | `IdiomasSection` (`SettingsAdvancedSections.tsx:70`) | `GET /settings/general`; `PUT /settings/app-translations` (admin); `GET`/`POST /portal/translations` (any_manager, `client_portal.py:834-850`) | admin | Sí (el back es más laxo) |
| 9 | workspace | `task-types` | `TaskTypesSection` (`:1457`) | `GET /advanced-config/task-types` (current_user); `POST`/`PATCH`/`DELETE` (**admin**, `advanced_config.py:168-182`) | admin, **pm** | **No**: pm ve crear, editar y borrar → 403 |
| 10 | workspace | `rates` | `RateTablesSection` (`:787`) | `GET /advanced-config/rate-tables` (admin_or_hr); `POST` tabla, `POST`/`PATCH`/`DELETE` entradas, `DELETE` tabla (admin) | admin | Sí |
| 11 | workspace | `numbering` | `NumberingSection` (`:970`) | `/advanced-config/numbering` GET, PATCH, reset (admin) | admin | Sí |
| 12 | workspace | `fields` | `CustomFieldsSection` (`:1036`) | `/advanced-config/custom-fields` (GET current_user; escritura admin) | admin | Sí |
| 13 | workspace | `alert-config` | `AlertConfigSection` (`:613`) | `/advanced-config/alert-configs` GET y PATCH (admin); `/bi/alerts/rules` CRUD (internal_user); `/bi/alerts/supported-metrics` | admin | Sí |
| 14 | workspace | `metrics` | `MetricsSection` (`:1635`) | `/bi/alerts/supported-metrics`, `/bi/alerts/custom-metrics` CRUD (internal_user) | admin | Sí (el back es más laxo) |
| 15 | workspace | `branding` | `MarcaSection` (`settings-sections/MarcaSection.tsx:27`) | `GET /orgs/{org_id}/branding` (current_user); `PUT`/`DELETE` (admin, `branding.py:174,186`) | admin | Sí |
| 16 | sistema | `roles` | `RolesSection` (`:526`) | `/advanced-config/roles` (GET current_user; escritura admin); `GET /advanced-config/modules` | admin | Sí |
| 17 | sistema | `runtime-flags` | `RuntimeFlagsSection` (`SettingsAdvancedSections.tsx:1024`) | `GET /settings/runtime/{group}`, `PUT /settings/runtime/{group}/{key}` (admin, `settings.py:102,110`) | admin | Sí |
| 18 | sistema | `integrations` | `IntegrationCredentialsSection` (`:982`) | `GET /settings/integrations`, `/{provider}`, `PUT /{provider}/{key}`, `POST /{provider}/test` (admin) | admin | Sí |
| 19 | sistema | `traduccion` | `TraduccionSection` (`settings-sections/TraduccionSection.tsx:47`) | `/settings/runtime/traduccion` (admin); `/translation/glossary` (GET internal_user; escritura admin); `/translation/usage` y `/translation/test` (admin); `GET /ai-providers` (current_user); `/ai-providers/routing` GET y PUT (admin); credenciales `deepl` y `azure_translator` (admin) | admin | Sí |
| 20 | sistema | `email-inbound` | `EmailInboundSection` (`:528`), que **monta `ConfigCorreoEntrante` del Service Desk** | `/sd/inbound/messages`, `/test`, `/run` (admin, `service_desk/canal_correo.py:16-27`) | admin | Sí |
| 21 | sistema | `esign` | `ESignSettingsSection` (`SettingsPageSections.tsx:1888`) | `GET`/`PATCH /esign/config` (admin, `esign.py:234,255`) | admin | Sí |
| 22 | sistema | `log-level` | `LogLevelSection` (`SettingsAdvancedSections.tsx:441`) | `GET`/`POST /settings/log-level` (admin) | admin | Sí |
| 23 | sistema | `system-state` | `SystemStateSection` (`:664`) | `GET /settings/general` (incluye claves internas para admin) y `GET /settings/db-isolation` (admin) | admin | Sí |

Además: `TemplatesSection` (`SettingsPageSections.tsx:1117-1387`, con `CreateTemplateModal` y `TemplateDetailModal`, unas 270 líneas) se exporta en la línea 2037 pero **no lo importa nadie** (grep en `frontend/src`). Usa `/advanced-config/templates`.

Además, el acceso a módulos: `ProtectedRoute` también cierra la ruta si `canOpen(path)` es falso (`blocked_routes`, que calcula `app/core/modulos.py:119` a partir de `module_access` del rol personalizado). Para admin y superadmin nunca se cierra nada (`modulos.py:85`).

### 1.2 Diseño de `/settings` (recuentos)

- **Usan `SeccionDeAjustes`: 19 de 23.** No lo usan: `setup` (divs con clases `u-*`), `idiomas` (`.seadse-card` propia, `SettingsAdvancedSections.tsx:210`), `branding` (`.marcsect-grid-*`), `traduccion` (`<Section>` del kit, 12 usos, en vez de `SeccionDeAjustes`).
- **Ningún fichero de `/settings` usa `<Input>` ni `<Tabla>` del kit.** Las listas (usuarios, sedes, departamentos, tarifas…) se pintan como tarjetas `div.set-item`.

| Fichero | `<input>` | `<textarea>` | `<select>` | `<table>` | checkbox HTML | `style={{` | `<Pulsable>` | Kit usado |
|---|---|---|---|---|---|---|---|---|
| `SettingsPageSections.tsx` | **78** | 3 | 0 | 0 | 0 | 5 | 42 | Button, Select, Switch, Checkbox, GrupoDeOpciones (1, en Usuarios), Modal |
| `SettingsAdvancedSections.tsx` | 8 | 0 | 0 | 0 | 0 | 8 | 6 | Button, Select, Tabs |
| `TraduccionSection.tsx` | 3 | 2 | 0 | 0 | 0 | 0 | 0 | Button (10), Select (6), Switch/Checkbox (5), Modal, Section |
| `MarcaSection.tsx` | 3 | 0 | 0 | 0 | 0 | 2 | 0 | Button (2) |
| `PuestaEnMarchaSection.tsx` | 0 | 0 | 0 | 0 | 0 | 1 | 0 | Button (1) |

`<input>` por sección en `SettingsPageSections.tsx`: Usuarios 9, Plantillas (sin usar) 16, Tipos de tarea 8, Tarifas 7, Sedes 6, General 1, Roles 4, Alertas 4, Vacaciones 4, Campos 4, Departamentos 4, Métricas 4, Numeración 3, Áreas 2, Firma 1. No hay `<select>` ni `<table>` HTML: la deuda está en los `<input>` sueltos con clase `set-input` y en los `Pulsable` de icono (editar, guardar, cancelar) en lugar de `IconButton`.

---

## 2. Pantallas de configuración fuera de `/settings`

### 2.1 Menú «configuracion» (`Layout.tsx:290-315`) y rutas sueltas

| Ruta | Roles de la ruta (`App.tsx`) | Roles del menú | Qué edita | Endpoint (back: dependencia) | Diseño (kit / propio) | Problema |
|---|---|---|---|---|---|---|
| `/settings` | admin, hr, pm (:429) | **admin** | ver §1 | ver §1 | ver §1 | El menú se la oculta a hr y pm |
| `/project-templates` | admin, pm (:644) | admin, pm | Plantillas de proyecto (`project_templates`) | `/templates`: GET current_user; POST any_manager; DELETE, apply, from-project admin_or_pm | Button 11, Select 3, Input 17, textarea 3 | — |
| `/settings/approval-workflows` | admin, pm, team_lead (:603) | admin, pm, team_lead | Flujos de aprobación (`ApprovalsPage mode="config"`) | `/approvals/workflows*`: lectura current_user; **todas las escrituras admin** (`approvals.py:82-190`) | — | **pm y team_lead ven el editor; crear, editar, publicar o clonar → 403**. `ApprovalsPage` no filtra por rol |
| `/settings/policies` | admin (:604) | admin | Políticas y reglas | `/policies/*` admin (`politicas.py`) | Button 3 | — |
| `/settings/project-workflows` | admin, pm (:563) | admin, pm | Estados y transiciones por proyecto | `/project-workflows/{p}` admin_or_pm (`custom_fields.py:118-177`) | Button 12, Select 4, `<input>` 5 | — |
| `/issue-types` | admin, pm (:575) | admin, pm | Tipos de incidencia por proyecto (`issue_types`) | `/issue-types/{p}` admin_or_pm (`issue_types.py:77-124`) | Tabla 1, `<input>` 5, `style` 6 | — |
| `/custom-fields` | admin, pm (:558) | admin, pm | Campos de tarea por proyecto (`project_custom_fields`) | `/custom-fields/{p}` admin_or_pm (`custom_fields.py:41-61`) | Tabla 1, GrupoDeOpciones 1, `<input>` 4 | — |
| `/project-permissions` | admin, pm (:591) | admin, pm | Permisos por proyecto (`project_permissions`) | `/permissions/{p}` admin_or_pm | Tabla 1, Select 2 | — |
| `/ai-hub` | admin, pm (:553) | admin, pm | Proveedores de IA, enrutado, uso, gobernanza y observabilidad | `/ai-providers`: GET current_user; **todo lo demás admin**, incluido `GET /routing` (`ai_providers.py:84-318`) | Button 18, `<input>` 9 | pm: la pestaña Enrutado da 403 al cargar; crear, probar o sincronizar → 403 |
| `/esign` | admin, pm (:543) | admin, pm | Sobres de firma (no es configuración) | `POST /esign` **admin** (`esign.py:152`) | Tabla 1, `<input>` 5 | pm ve «Nueva solicitud» → 403. El enlace de credenciales va a `/settings#esign` (`ESignPage.tsx:264-265`), pero SettingsPage solo lee `?tab=` y abre la primera pestaña |
| `/m365` | admin (:546) | admin | Acciones M365 (sincronizar calendario, avisos de Teams) | `GET /m365/status` current_user; acciones admin | Input 5 | — |
| `/import` | admin, pm (:529) | admin, pm | Importación CSV | `/billing-reports/import/*` any_manager | Tabla 1 | — |
| `/mfa` | todos (:549) | todos | MFA propio | `/auth/mfa/*` | Button 7, `<input>` 2 | — |
| `/governance` | admin (:621) | admin | Gobernanza de IA por módulo | `/governance/config` (admin) | Switch 1 | — |
| `/grc` | admin (:629) | admin | Matriz de permisos `grc_role_permissions`, SoD, retención, evidencias | `/grc/*` (escritura admin); `/governance/retention/*`, `/legal-holds` (admin) | Tabla 6, Select 12, `<input>` 9, **`style` 14** | — |
| `/organizations` | admin (:550) | admin | Empresas (multi-tenant) | **todo `require_superadmin`**, también el GET (`organizations.py:53-205`) | Modal 6, `<input>` 13 | **Un admin de empresa ve la entrada y la página, pero todas las llamadas dan 403** |
| `/enterprise` | admin (:527) | admin | Webhooks entrantes, RGPD, correo, integraciones (Jira, Slack, Teams), SSO, auditoría, API keys | `/webhooks`, `/gdpr`, `/email`, `/integrations-hub/*`, `/oauth-integrations`, `/enterprise/sso`, `/bookings/api-keys` (enterprise.py: 16 admin, 31 any_manager) | Button 40, Select 7, **`<input>` 19**, textarea 4 | — |
| `/webhook-log` | admin (:634) | admin | Solo lectura de las entregas de los webhooks salientes | `/enterprise/webhooks`, `/events`, `/deliveries` (admin) | Select 3 | Los webhooks salientes (`POST /enterprise/webhooks`) **no se pueden crear desde ninguna pantalla**: el frontend no tiene esa llamada (grep) |
| `/jira-integration` | admin, pm (:643) | admin, pm | Conexión Jira de tareas | `GET`/`POST /jira/config` **admin** (`jira.py:76,89`) | `<input>` 4 | **pm abre la página y la carga da 403** |
| `/public-forms` | admin, pm (:640) | admin, pm | Formularios públicos | `/forms` admin_or_pm | Input 2 | — |
| `/developer` | admin, pm (:642) | admin, pm | Apps OAuth de desarrollador | `/developer/apps` admin_or_pm | Modal 4 | — |
| `/settings/chat-admin` | admin (:648; `/chat/admin` redirige aquí) | **no está en el menú** | Retención, retención legal, integraciones, webhooks, auditoría y eDiscovery del chat | `/collaboration/retention`, `/legal-holds`, `/audit`… (escritura admin) | Select 4, **`<input>` 13**, textarea 2, **sin `Button` del kit** | Huérfana: ningún enlace del frontend lleva a ella (grep) |
| `/sla-calendars` | admin, pm (:587) | admin, pm (grupo soporte, `Layout.tsx:261`) | Calendarios SLA y sus festivos (`sla_calendars`, `sla_calendar_holidays`) | `/cmdb/sla-calendars*` admin_or_pm | Button 14 | — |
| `/rate-cards` | admin, pm (:599) | admin, pm (grupo negocio, `:248`) | Tablas de tarifas (`rate_tables`, `rate_entries`, `rate_overrides`) | `/rate-cards*`: GET current_user; **escritura any_manager** | Tabla 1, Input 8 | El back deja escribir a team_lead y hr, que no tienen ninguna pantalla para hacerlo |
| `/user-costs` | admin, hr (:646) | admin, hr (`:249`) | Estructura de coste por país y persona | `/user-costs/*` admin_or_hr | Tabla 1, Input 14 | — |
| `/sd/workflow-designer` | admin, pm (:520) | admin, pm (`:258`) | Blueprints de flujo del Service Desk | `/sd/workflow-designer/*` any_manager | `<input>` 7, textarea 3, **sin `t(`** (`useAppT`) | 8 placeholders literales (`support_l1`, `priority == 'P1'`, `$assignee, $group`…) |

### 2.2 Pestañas de configuración dentro de módulos

| Módulo | Ruta y roles | Pestaña de configuración y quién la ve | Qué edita | Endpoint (back) | Problema |
|---|---|---|---|---|---|
| Ausencias (`pages/AbsencesPage.tsx:42`) | `/absences`: todos | «Configuración»: admin, hr → `components/ausencias/admin/AdminDeAusencias.tsx` (11 subpestañas: tipos, documentos, turnos, jornadas, festivos, personas (admin+hr), horario, cuadrante, cobertura, acceso especial, ejemplos) | Tipos de ausencia, documentos, turnos, rotaciones, jornadas y fichas laborales, **festivos (`/settings/holidays`, tabla `holidays`)**, saldos (ajustes `movimientos_de_saldo`), bolsa de horas | `/absences/types|document-types|shifts|work-schedules|work-profiles` (admin_or_hr); `/rotations`, `/roster` (any_manager); `/balances` (any_manager); `/balance-adjustments` (admin_or_hr); `/special-access` POST y `/examples` (admin) | Enlaces a `/settings/policies` y `/settings/approval-workflows` que hr no puede abrir (§4). Acceso especial y ejemplos sí se cortan bien para hr (`puedeEditar={esAdmin}`, `puedeCargar={esAdmin}`) |
| Horas extra (`pages/HorasExtraPage.tsx:43`) | `/overtime`: todos | «Configuración»: admin, hr → `components/horas-extra/ConfigHorasExtra.tsx` | Configuración de horas extra, presupuestos, regularización y reglas (en Políticas) | `PUT /overtime/config`, `/overtime/budgets` (admin_or_hr); «Cargar reglas de ejemplo» → `POST /policies/examples/horas_extra` (**admin**) | hr: el enlace a Políticas y el botón de ejemplos dan 403 (§4) |
| Service Desk (`pages/ServiceDeskPage.tsx:116`) | `/service-desk`: admin, pm, employee, hr, subcontractor (el subcontractor no ve Configuración) | «Configuración» **sin filtro de rol** → `service-desk/ConfigTab.tsx:1114`, con 17 subpestañas: catálogo, SLA, reglas SLA/OLA, ciclos de vida, canales, grupos, enrutado, escalado, notificaciones, correo, monitorización, guardias, página de estado, plantillas, respuestas, anuncios, traducciones del portal | Catálogo, políticas SLA, grupos, reglas de enrutado y escalado, plantillas de aviso, buzón, guardias, página de estado | La escritura de catálogo, grupos, anuncios, enrutado, SLA y escalado es **admin** (`service_desk/misc.py:99-307`, `sla.py:35-81`); plantillas de aviso admin; guardias any_manager; correo entrante admin (incluida la lectura) | Para pm, employee y hr casi todo es de solo lectura en el back y la UI no lo indica. Solo `ConfigCanales` (3) y `ConfigSlaYCiclos` (10) comprueban el rol; `ConfigTab`, `ConfigCorreoEntrante`, `ConfigEscaladoYAvisos`, `ConfigGuardiasYMonitor` y `ConfigPaginaDeEstado`, ninguna. **Notificaciones → `RuntimeGroupEditor groupId="service_desk"`** (`ConfigEscaladoYAvisos.tsx:338`) llama a `/settings/runtime/service_desk` (admin) → 403 al cargar para quien no es admin |
| Portal de clientes (`pages/ClientPortalPage.tsx:1019`) | `/client-portal`: admin, pm | No tiene pestaña de configuración: contactos, UAT, peticiones, mensajes, documentos y wiki | — | Las traducciones del portal se editan en Settings→Idiomas (`/portal/translations`, any_manager) y la revisión de contenido en SD→Config→Traducciones del portal | La configuración del portal está repartida entre 3 sitios fuera de su módulo |
| Facturación (`pages/InvoicesPage.tsx`) | `/invoices`: admin, pm | No tiene pestaña de configuración (sin series, impuestos ni moneda) | — | — | El IVA por defecto del formulario está **fijo en 21** (`InvoicesPage.tsx:99`) y no lee `DEFAULT_TAX_RATE` (Config. dinámica → Locale, que expone `/settings/org-defaults` como `tax_rate`). La numeración de facturas sí sale de `numbering_sequences` (`billing_reports_service/facturas.py:100`) |
| AI Hub (`pages/AIHubPage.tsx:642-647`) | `/ai-hub`: admin, pm | Proveedores, Enrutado, Uso, Gobernanza, Observabilidad, Guía | `ai_providers`, enrutado por módulo, políticas de gobernanza de IA | ver §2.1 | Los conectores contecmind/contecintelligence no están aquí: credenciales en Settings→Integraciones y parámetros en Config. dinámica→Conectores |
| GRC (`pages/GrcPage.tsx:1103-1111`) | `/grc`: admin | Matriz, SoD, Violaciones, Flujos de mitigación, Auditoría, Acceso, Informe, Evidencias, **Retención** | `retention_policies`, `legal_holds` (gobernanza) | `/governance/retention/*`, `/governance/legal-holds` (admin) | Retención y retención legal duplicadas con el chat (§3) |

---

## 3. Duplicados

Tipo: **DATO** = la misma tabla o el mismo campo se edita desde más de un sitio; **PANTALLA** = dos interfaces para lo mismo; **RELACIONADO** = alcance distinto pero el usuario lo percibe como lo mismo.

| # | Duplicado | Sitios | Tipo | Cifras y detalle |
|---|---|---|---|---|
| D1 | **Tarifas** | Settings→Tarifas (`/advanced-config/rate-tables`, 6 rutas, `advanced_config.py:209-236`) y `/rate-cards` (`/rate-cards`, 12 rutas, `rate_cards.py:69-207`) | **DATO + PANTALLA** | La misma tabla `RateTable`/`rate_tables` (`app/models/advanced_config.py:196`) y `RateEntry` (`:212`); `rate_card_service.py:9-11` importa los mismos modelos. **Permisos distintos sobre la misma fila**: escritura admin en `/advanced-config` y any_manager en `/rate-cards`. Solo `/rate-cards` gestiona excepciones (`RateOverride`), duplicar y tarifa efectiva |
| D2 | **Campos personalizados** | Settings→Campos (`custom_fields`, 14 entidades, `SettingsPageSections.tsx:1025`) y `/custom-fields` (`project_custom_fields`, por proyecto, solo tareas) | **PANTALLA (+ DATO conceptual en «tarea»)** | Dos tablas distintas (`advanced_config.py:331` y `custom_fields.py:62`). Las dos definen campos de tarea. Los valores de `custom_fields` (`/advanced-config/custom-fields/values/{id}`) **no los pide ni los pinta ningún formulario del frontend** (grep): los campos por entidad se definen pero no se usan |
| D3 | **Tipos de tarea frente a tipos de incidencia** | Settings→Tipos de tarea (`task_types`) y `/issue-types` (`issue_types` por proyecto) | **PANTALLA** | Las tareas usan `issue_type_id` (`app/models/task.py`; `TasksPage.tsx:401` llama a `issueTypesApi.list`). **`task_types` no lo lee nadie** fuera de su CRUD y la semilla (grep de `TaskType` en `app/`): la pestaña edita una tabla muerta |
| D4 | **Vacaciones y saldos** | Settings→Vacaciones (`vacation_policies` + `/advanced-config/vacation-balances` → `user_vacation_balances`) y Ausencias→Configuración→Personas (`/absences/balances`, `/balance-adjustments` → `movimientos_de_saldo`) | **DATO (derecho anual) + PANTALLA (saldo) con dos cálculos distintos** | `days_entitled` (`user_vacation_balances`) solo se edita en Settings, y el motor de Ausencias lo lee como «ficha» (`app/services/ausencias/saldos.py:238-244`). El **saldo restante se muestra en los dos sitios con cálculos diferentes**: Settings resta los `working_days` de `AbsenceType.vacation` aprobadas y pendientes del año y, si no hay ficha, usa `settings.DEFAULT_VACATION_DAYS_PER_YEAR` del entorno (`advanced_config_service/tarifas_y_vacaciones.py:27-64`); Ausencias tiene en cuenta periodo, arrastre con caducidad, ajustes, bolsa, prorrateo y el valor por empresa `get_runtime_int("DEFAULT_VACATION_DAYS_PER_YEAR")` (`saldos.py:230-266`). **`vacation_policies` no lo lee nadie** fuera del CRUD y la semilla (grep de `VacationPolicy`). Además, los 23 días por defecto están fijos en el formulario (`SettingsPageSections.tsx:899`) |
| D5 | **Plantillas de proyecto** | `TemplatesSection` (exportada y sin usar, `/advanced-config/templates`), `/project-templates` (`/templates`) y `/billing-reports/templates` | **DATO (3 APIs) + PANTALLA (1 viva y 1 muerta)** | La misma tabla `project_templates` (`advanced_config.py:40`) y el mismo servicio `advanced_config_service/plantillas.py` (`templates.py:22-35` lo dice). Permisos distintos: crear es admin en `/advanced-config/templates` y any_manager en `/templates` |
| D6 | **Webhooks** | Enterprise→Webhooks (entrantes: `/webhooks`), `/webhook-log` (salientes: `/enterprise/webhooks`, solo lectura), ChatAdmin→Webhooks (`/collaboration/webhooks`) y Settings→Integraciones→«Inbound webhooks (signing secrets)» | **RELACIONADO (3 dominios) + 1 hueco** | Son tres tablas y conceptos distintos con el mismo nombre. Los salientes **no tienen alta en la UI**. Los secretos de firma están en Integraciones, lejos de las tres pantallas |
| D7 | **Credenciales e integraciones** | Settings→Integraciones (22 proveedores y 77 campos en `integration_credentials_service.py:45-241`; el tipo del frontend solo declara 17, `services/api/settings.ts:58`); AI Hub (`ai_providers`); `/jira-integration` (`/jira/config`); Enterprise→Integraciones (`/integrations-hub/jira/config`, pruebas de Slack y Teams, `/oauth-integrations`); `/m365` + Integraciones→`ms_graph`/`alm_m365` + Config. dinámica→Feature flags (`M365_*`); ChatAdmin→Integraciones (Jira, GitHub, GitLab, Google Calendar, M365); Traducción→DeepL/Azure (reutiliza `IntegrationProviderEditor`) | **DATO (Jira, IA) + PANTALLA** | **Jira**: `/jira/config` y `/integrations-hub/jira/config` escriben la misma `JiraConfig` de la organización (`integrations_hub.py:115-130`, `jira_service.configuracion_de_tareas`), con permisos distintos (GET admin frente a any_manager). `/integrations/jira/configs` (por cliente, admin_or_pm) no tiene UI (grep). **IA**: la clave Anthropic de Integraciones→`ai_providers` es el último escalón de resolución (`ai_provider_service/resolucion.py:103-118`) frente a los proveedores del AI Hub. Se configura en dos sitios y gana el AI Hub |
| D8 | **Firma electrónica** | Settings→Firma electrónica (`AppSetting esign.*`, `esign.py:234-285`) y Settings→Integraciones→`docusign`/`adobe_sign` (`IntegrationCredential`) | **DATO duplicado y divergente** | Los mismos campos (integration key, secret, account id, base URL / client id, secret, base URL) en dos almacenes. `esign_service` lee `esign.*` o el entorno (`esign_service.py:285`, `ajuste_de_firma` en `:608`); **las credenciales de Integraciones solo las usa el botón «Probar»** (`integration_test_service.py:275-276`; grep sin más lectores). Hay un tercer ajuste relacionado: Config. dinámica→ALM `ALM_ACT_ESIGN_PROVIDER` |
| D9 | **Idiomas frente a Traducción** | Settings→Idiomas (textos de la interfaz: `/settings/app-translations` y `/portal/translations`), Settings→Traducción (traducción automática), Config. dinámica→Traducción y SD→Config→Traducciones del portal | **DATO (grupo `traduccion`) + RELACIONADO** | Traducción edita el grupo runtime `traduccion` (11 claves, `TraduccionSection.tsx:36-38,177`), **el mismo que Config. dinámica→Traducción**. El enrutado de IA del módulo `translation` también se edita en AI Hub→Enrutado (`/ai-providers/routing`). Idiomas no traduce: sobrescribe literales |
| D10 | **General, Sesión, Marca, Puesta en marcha y Config. dinámica** | General y Sesión comparten `GET /settings/general` y la query `['settings-general']` (`:191`, `:1973`); Marca (`/orgs/{id}/branding`); Config. dinámica→Locale y Branding/UI | **DATO divergente** | General muestra `currency`, `timezone`, `language` y `work_hours_per_day` (`AppSetting`, `settings_service/generales.py:27-35`), pero lo que usa la aplicación es `/settings/org-defaults`, que lee **las claves runtime** `DEFAULT_CURRENCY`, `DEFAULT_TIMEZONE`, `DEFAULT_LANGUAGE` y `DEFAULT_WORKING_HOURS_PER_DAY` (`generales.py:161-177`; `hooks/useOrgSettings.ts:41-42`). **No encontré quién lea `currency`, `timezone`, `language`, `work_hours_per_day` ni `company_name` de `AppSetting`** (grep en `app/` y `frontend/src`, salvo la semilla): General edita valores sin efecto. El nombre está en 3 sitios: `company_name` (General), `app_name` (Marca) y `PROJECT_NAME` (Config. dinámica→Branding/UI, que leen `billing_reports.py:41` y `auth_mfa.py:86`). Sesión (`idle_timeout_*`) sí tiene efecto en el operador (`AuthContext.tsx:156-161`) y en el portal (`client_portal_service/autenticacion.py:105-116`). Puesta en marcha solo enlaza (`puesta_en_marcha.py:62-76`) |
| D11 | **Config. dinámica frente a pantallas dedicadas** | `RUNTIME_FLAG_GROUPS` (`app/services/settings_service/_catalogo.py:14`): **30 grupos y 343 claves**; frontend `RUNTIME_GROUPS` (`SettingsAdvancedSections.tsx:738-769`, 30) | **DATO (varios) + RELACIONADO** | (a) **SLA**: 20 claves (P1-P4 respuesta y resolución, jornada «sin política», predicción). Son el respaldo cuando no hay política (`sla_service.py:93-112,386-393`). Se solapan con SD→Config→SLA (`sla-policies`), SD→Reglas SLA/OLA y `/sla-calendars` (horario y festivos): **cuatro sitios para el horario y los tiempos del SLA**. (b) **Service Desk**: 51 claves; **el mismo editor** se monta en SD→Config→Notificaciones (DATO + PANTALLA). (c) **Traducción**: ver D9. (d) **Locale**: `DEFAULT_CURRENCY`/`LANGUAGE`/`TIMEZONE`/`WORKING_HOURS`, ver D10; `DEFAULT_VACATION_DAYS_PER_YEAR`, ver D4; `DEFAULT_TAX_RATE` no se aplica en Facturación (§2.2). (e) **Política de contraseñas** `MIN_PASSWORD_LENGTH` frente a Auditoría `COMPLIANCE_MIN_PASSWORD_LENGTH` (dos claves para el mismo umbral). (f) **IA**: el grupo `ai` (22 claves, presupuesto diario…) frente al AI Hub. (g) **Feature flags** `M365_*` frente a `/m365`. (h) **Políticas** (3 claves) frente a `/settings/policies`. (i) **Nivel de log**: no está duplicado en runtime (solo `/settings/log-level`) |
| D12 | **Festivos** | Ausencias→Festivos (`/settings/holidays` → `holidays`, `app/models/settings.py:143`, por sede) y `/sla-calendars` (`sla_calendar_holidays`, `app/models/cmdb.py:174`; el calendario «festivos generales», `service_desk/sla.py:70-72`) | **DATO (dos tablas para lo mismo)** | Un festivo de empresa se da de alta dos veces: una para ausencias y jornada, otra para el SLA. Además queda la tabla `sla_holidays` (`app/models/bookings.py:154`), que el comentario de `sla.py:70` da por retirada en la migración 174 |
| D13 | **Retención y retención legal** | GRC→Retención (`retention_policies`, `legal_holds`, `/governance/*`) y ChatAdmin→Retención / Retención legal (`collaboration_retention_policies`, `collaboration_legal_holds`, `/collaboration/*`) | **RELACIONADO (dos tablas y dos pantallas)** | Alcances distintos (todo frente al chat), pero con el mismo nombre y sin enlace entre ellas. ChatAdmin no está en el menú |
| D14 | **Permisos por rol** | Settings→Roles (`custom_roles.module_access/permissions`, cierra módulos: `modulos.py:83-94`), GRC→Matriz (`grc_role_permissions`, se aplica en `app/core/grc_enforce.py:111-113`) y `/project-permissions` (`project_permissions`) | **RELACIONADO (tres modelos)** | Dos matrices rol×módulo independientes (Roles y GRC) que deciden cosas parecidas, en pantallas distintas |
| D15 | **Alertas de BI** | Settings→Alertas (`biSmartAlertsApi` reglas) y `/alerts`→Smart (`components/bi/SmartAlertsPanel.tsx`, ruta admin, pm, hr) | **DATO + PANTALLA** | Las mismas reglas `/bi/alerts/rules`. Settings→Métricas edita las métricas personalizadas que usan esas reglas |
| D16 | **Correo entrante** | Settings→Correo entrante y SD→Config→Correo | **PANTALLA (el mismo componente)** | `EmailInboundSection` monta `ConfigCorreoEntrante` (`SettingsAdvancedSections.tsx:530`, comentario «La misma pantalla»). Las credenciales van en Settings→Integraciones→`sd_mailbox` |
| D17 | **Coste o tarifa de persona** | Settings→Usuarios (`hourly_rate`), `/user-costs` (perfiles de coste por país y persona) y `/rate-cards` (tarifa de venta por rol o persona) | **RELACIONADO** | Tres sitios para el «precio por hora» de una persona |

---

## 4. Enlaces que llevan a 403 o a sitio equivocado

Se buscaron en `frontend/src` (sin tests) los literales de `/settings…`, `/settings?tab=`, `/issue-types`, `/custom-fields`, `/rate-cards`, `/sla-calendars`, `/governance`, `/grc`, `/organizations`, `/ai-hub`, `/m365`, `/webhook-log`, `/jira-integration`, `/user-costs`, `/sd/workflow-designer`, `/settings/chat-admin` en `to=`, `href=`, `navigate(` y `window.location`. Se cruzan con los roles de quien ve el enlace, los de la ruta y los del back. Los enlaces que da el back (`puesta_en_marcha.py`) solo se muestran a admin y son correctos.

| # | Origen (fichero:línea) | Quién ve el enlace | Destino (roles de la ruta) | Resultado |
|---|---|---|---|---|
| E1 | `ConfigHorasExtra.tsx:237` «Ir a políticas» | admin, hr | `/settings/policies?dominio=horas_extra` (admin) | **hr → `/403`** |
| E2 | `ConfigHorasExtra.tsx:238` «Cargar reglas de ejemplo» (botón) | admin, hr | `POST /policies/examples/horas_extra` (admin, `politicas.py:187`) | **hr → 403 del API** |
| E3 | `AdminDeAusencias.tsx:41` y `EjemplosDeAusencias.tsx:47` | admin, hr | `/settings/policies?dominio=ausencias` (admin) | **hr → `/403`** |
| E4 | `AdminDeAusencias.tsx:44` y `EjemplosDeAusencias.tsx:48` | admin, hr | `/settings/approval-workflows` (admin, pm, team_lead) | **hr → `/403`** (la ruta no admite hr). Si pudiera entrar, las escrituras son admin |
| E5 | `alm/uso/RecuperacionPanel.tsx:141` (sin filtro de rol) | `/alm`: admin, pm | `/settings/policies?dominio=licencias` (admin) | **pm → `/403`** |
| E6 | `service-desk/ConfigCorreoEntrante.tsx:66` (`window.location.href`) y `ConfigGuardiasYMonitor.tsx:165` (`<a href>`), sin filtro de rol | SD→Config: admin, pm, employee, hr | `/settings?tab=integrations` (ruta admin, hr, pm; pestaña solo admin) | **employee → `/403`**; pm y hr acaban en otra pestaña (la primera que ven) sin aviso. Además recarga la página entera |
| E7 | `service-desk/ConfigTab.tsx:580` `<a href="/sla-calendars">` | admin, pm, employee, hr | `/sla-calendars` (admin, pm) | **employee y hr → `/403`** |
| E8 | `ESignPage.tsx:264-265` «Configura las credenciales en Ajustes» | admin, pm | `/settings#esign` (pestaña solo admin) | El hash no se lee: admin cae en «Puesta en marcha» y pm en «Tipos de tarea». **Enlace roto para todos** |
| E9 | `layout/GlobalSearch.tsx:33` acción rápida «Configuración» (sin filtro de rol) | todos | `/settings` (admin, hr, pm) | **employee, team_lead y subcontractor → `/403`** |
| E10 | Menú `Layout.tsx:291` | — | `/settings` | Lo contrario: hr y pm tienen acceso pero **no ven la entrada** |
| E11 | Menú `Layout.tsx:307` «Organizaciones» | admin | `/organizations` (admin) | La página abre, pero **todas las llamadas son `require_superadmin`** → 403 para el admin de empresa |
| E12 | Menú `Layout.tsx:293` «Approval Flows (Config)» | admin, pm, team_lead | `/settings/approval-workflows` | pm y team_lead entran, pero **todas las escrituras dan 403** (admin) |
| E13 | Menú «Jira Integration» (`Layout.tsx:310`) | admin, pm | `/jira-integration` | **pm: 403 al cargar** (`GET /jira/config` admin) |
| E14 | Menú «AI Hub» (`Layout.tsx:299`) | admin, pm | `/ai-hub` | pm: Enrutado da 403 al cargar y todas las acciones dan 403 |
| E15 | Settings→Tipos de tarea, Usuarios y Vacaciones (§1.1) | pm / hr | botones de crear, editar o borrar | 403 del API |
| E16 | Menú «Service Desk» (`Layout.tsx:256`) | incluye **team_lead** | `/service-desk` (admin, pm, employee, hr, subcontractor) | **team_lead → `/403`** (fuera de configuración, pero es el mismo patrón) |
| E17 | Widget de onboarding del CAB (`cab_service/widgets_y_onboarding.py:104`) «Configura el SLA» | [no verificado quién lo ve] | `/settings` | Lleva a Ajustes, pero el SLA no está allí (está en SD→Config, `/sla-calendars` y Config. dinámica) |

Casos que están bien: `ExpensesPage.tsx:741` (enlace a Políticas solo con `hasRole('admin')`) y `PoliticasPage.tsx:65` (admin → flujos).

---

## 5. Textos sin traducir

Método: (1) se comprobaron con node todas las claves `t('a.b')`, `_t`, `ta`, `th` literales de las pantallas de §1 y §2 contra `frontend/src/i18n/langs/{es,en,zh}.mjs`: **no falta ninguna clave literal en ninguno de los tres idiomas**. (2) Búsqueda heurística de texto JSX, atributos (`placeholder`, `title`, `label`, `aria-label`) y propiedades `label:`/`description:` con texto que no pasa por `t()`. (3) Textos que vienen del backend y se pintan tal cual.

**Lo grave está en los catálogos del backend, que se pintan sin traducir:**

| Origen | Cantidad | Idioma | Dónde se ve | Ejemplo |
|---|---|---|---|---|
| Etiquetas de `RUNTIME_FLAG_GROUPS` (`_catalogo.py`), que pinta `RuntimeFlagRow` con `{item.label}` (`SettingsAdvancedSections.tsx:842,847`) | **343** | todas en inglés | Config. dinámica, Traducción y SD→Notificaciones | «P1 Critical — response (h)», «Lessons — categories (CSV)», «Reports — longest period that can be requested (days)» |
| `label` de proveedor y de campo en `integration_credentials_service.py` (`{it.label}`, `:950`; pestañas `p.label`, `:1012`) | **22 proveedores + 77 campos** | inglés | Settings→Integraciones y Traducción→credenciales | «SMTP (outbound email)», «Inbound webhooks (signing secrets)», «Outbound webhook signing secret» |
| `description` de `AppSetting` y claves sin `LABEL_KEYS` | General traduce 5 claves (`SettingsPageSections.tsx:164-170`); el resto se ve como `s.key` en crudo | clave técnica | Settings→General | cualquier clave «limpia» fuera de las 5 |

**Literales en el frontend:**

| Fichero | Recuento (aprox.) | Ejemplos |
|---|---|---|
| `settings-sections/SettingsAdvancedSections.tsx` | 60 textos de respaldo en `RUNTIME_GROUPS` (30 `label` + 30 `description`, en español), usados como *fallback* de `t('settingsadvanced.rt_<id>')`. **Falta la clave `rt_informes` y `rt_informes_desc` en es, en y zh**, así que el grupo «Informes» sale en español en los tres idiomas | `label: 'Informes'`, `'Periodo libre: rango máximo…'` |
| `SettingsPageSections.tsx` | 7 etiquetas de campo de `ESIGN_PROVIDERS` en inglés (`:1809-1843`) + 2 nombres de marca | «Integration Key (Client ID)», «Account ID», «Secret Key», «Base URL», «Client ID», «Client Secret»; también «DocuSign Connect:», «Adobe Sign:» |
| `components/layout/GlobalSearch.tsx:25-34` | **16** (8 `label` + 8 `hint`, en español) | «Nueva tarea / Ir a tareas», «Configuración / Ajustes del sistema» |
| `service-desk/WorkflowDesignerPage.tsx` | 8 placeholders técnicos | `support_l1`, `priority == 'P1'`, `$assignee, $group` |
| `ChatAdminPage.tsx` | 5 nombres de producto (Jira, GitHub, GitLab, Google Calendar, Microsoft 365) | aceptables como nombres propios |
| `EnterprisePage.tsx` | 2 (`placeholder="mi-webhook"`, «Google Workspace») + la pestaña `label: 'SSO'` (`:1032`) | |
| `OrganizationsPage.tsx` | 2 (`placeholder="app.cliente.com"`) | |
| `MarcaSection.tsx` | 1 (`placeholder="#RRGGBB"`) | |
| `components/layout/NexusAssistPanel.tsx:54` | `'/settings': 'Ajustes'` (y el resto del mapa) | |
| Menú `Layout.tsx:291-314` | Las `label` del grupo están en inglés o español mezclados («Settings», «Importar datos», «Seguridad MFA», «Log Webhooks»…), pero **son respaldo**: `getNavLabel` (`:372-377`) traduce con `nav.<clave>` y las 25 rutas de configuración tienen clave en es, en y zh | — |

Pantallas sin literales detectados (todo pasa por `t()`): WebhookLog, M365, Jira, CustomFields, IssueTypes, ProjectTemplates, RateCards, UserCosts, Governance, PublicForms, Developer, Import, MFA, ProjectPermissions, Workflows, Approvals, Políticas, SLACalendars, AIHub, SD→Config*, Ausencias→admin/*, ConfigHorasExtra. En `zh`, algunas claves tienen el mismo texto que en `es` (es decir, sin traducir de verdad): AIHub 8, M365 4, ESign 3, Enterprise 2, WebhookLog 1.

---

## 6. Tabla resumen

| Ajuste | Dónde se edita hoy | Endpoint / campo | Roles front | Roles back | Diseño | Problema |
|---|---|---|---|---|---|---|
| Moneda, zona, idioma, jornada | Settings→General **y** Config. dinámica→Locale | `AppSetting currency/timezone/language/work_hours_per_day` frente a runtime `DEFAULT_*` (lo que lee `/settings/org-defaults`) | admin | admin | kit + `<input>` | General edita valores que nadie lee (D10) |
| Nombre de la empresa o producto | General (`company_name`), Marca (`app_name`), Config. dinámica (`PROJECT_NAME`) | 3 almacenes | admin | admin | mixto | 3 sitios; `company_name` sin lector (D10) |
| Cierre de sesión por inactividad | Settings→Sesión | `AppSetting idle_timeout_*` | admin | admin | kit | Afecta también al portal y no se dice |
| Usuarios | Settings→Usuarios | `/users` | admin, hr | crear y borrar: admin | kit + 9 `<input>` | hr → 403 (E15) |
| Políticas de vacaciones | Settings→Vacaciones | `vacation_policies` | admin, hr | escritura admin | kit | Tabla sin lector (D4); hr → 403 |
| Derecho anual de vacaciones | Settings→Vacaciones | `user_vacation_balances.days_entitled` | admin, hr | admin_or_hr | kit | El saldo se muestra con otro cálculo que en Ausencias (D4) |
| Ajustes de saldo y bolsa | Ausencias→Config→Personas | `/absences/balance-adjustments` | admin, hr | admin_or_hr | kit | — |
| Departamentos y áreas | Settings→Departamentos | `/settings/departments`, `/settings/areas` | admin, hr | admin_or_hr | kit | — |
| Sedes | Settings→Sedes | `/advanced-config/offices` | admin | admin | kit + 6 `<input>` | — |
| Festivos | Ausencias→Festivos **y** `/sla-calendars` | `holidays` frente a `sla_calendar_holidays` | admin, hr / admin, pm | admin_or_hr / admin_or_pm | kit | Dos tablas (D12) |
| Tipos de tarea | Settings→Tipos de tarea | `task_types` | admin, pm | escritura admin | kit + 8 `<input>` | Sin lector (D3); pm → 403 |
| Tipos de incidencia | `/issue-types` | `issue_types` | admin, pm | admin_or_pm | Tabla + `style` 6 | Duplica el concepto de D3 |
| Campos por entidad | Settings→Campos | `custom_fields` | admin | admin | kit | Valores sin UI (D2) |
| Campos de tarea por proyecto | `/custom-fields` | `project_custom_fields` | admin, pm | admin_or_pm | Tabla | D2 |
| Tarifas | Settings→Tarifas **y** `/rate-cards` | `rate_tables`/`rate_entries` | admin / admin, pm | admin / any_manager | kit + 7 `<input>` / Tabla + Input | D1: la misma tabla con permisos distintos |
| Numeración | Settings→Numeración | `numbering_sequences` | admin | admin | kit | — |
| Alertas y reglas de BI | Settings→Alertas **y** `/alerts`→Smart | `alert_configs`, `/bi/alerts/rules` | admin / admin, pm, hr | admin / internal_user | kit | D15 |
| Métricas personalizadas | Settings→Métricas | `/bi/alerts/custom-metrics` | admin | internal_user | kit | — |
| Marca (colores, nombre) | Settings→Marca | `/orgs/{id}/branding` | admin | admin | propio (sin SeccionDeAjustes) | — |
| Roles personalizados | Settings→Roles **y** GRC→Matriz | `custom_roles` frente a `grc_role_permissions` | admin | admin | kit / Tabla | D14 |
| Configuración dinámica | Settings→Config. dinámica | runtime: 30 grupos, 343 claves | admin | admin | kit | 343 etiquetas en inglés; duplica SLA, SD, Traducción y Locale (D11) |
| Credenciales de integración | Settings→Integraciones | `integration_credentials`: 22 proveedores, 77 campos | admin | admin | kit | Etiquetas en inglés; DocuSign/Adobe sin lector real (D8) |
| Traducción automática | Settings→Traducción **y** Config. dinámica→Traducción | runtime `traduccion` + glosario + `/ai-providers/routing` | admin | admin | `<Section>` (no SeccionDeAjustes) | D9 |
| Idiomas (textos de la interfaz) | Settings→Idiomas | `/settings/app-translations`, `/portal/translations` | admin | admin / any_manager | propio (`.seadse-card`) | — |
| Correo entrante | Settings→Correo entrante **y** SD→Config→Correo | `/sd/inbound/*` | admin / SD (sin filtro) | admin | el mismo componente | D16; no-admin → 403 |
| Firma electrónica | Settings→Firma **y** Settings→Integraciones | `AppSetting esign.*` frente a `IntegrationCredential docusign/adobe_sign` | admin | admin | kit | D8; enlace `/settings#esign` roto (E8) |
| Nivel de log | Settings→Nivel de log | `/settings/log-level` | admin | admin | kit | — |
| Estado del sistema | Settings→Estado | `/settings/general`, `/settings/db-isolation` | admin | admin | kit | — |
| Puesta en marcha | Settings→Puesta en marcha | `/settings/setup-checklist` | admin | admin | propio | — |
| Plantillas de proyecto | `/project-templates` (+ `TemplatesSection` muerta) | `project_templates` por 3 APIs | admin, pm | any_manager / admin_or_pm / admin | kit | D5 |
| Flujos de aprobación | `/settings/approval-workflows` | `/approvals/workflows` | admin, pm, team_lead | escritura admin | — | pm y team_lead → 403 (E12) |
| Políticas y reglas | `/settings/policies` | `/policies` | admin | admin | kit | Enlaces desde hr y pm → `/403` (E1-E5) |
| Flujos de estado de proyecto | `/settings/project-workflows` | `/project-workflows` | admin, pm | admin_or_pm | kit | — |
| Permisos de proyecto | `/project-permissions` | `project_permissions` | admin, pm | admin_or_pm | kit | D14 |
| Proveedores y enrutado de IA | `/ai-hub` (+ Integraciones→`ai_providers`) | `ai_providers`, routing | admin, pm | admin | kit + 9 `<input>` | pm → 403 (E14); clave en dos sitios (D7) |
| Gobernanza de IA | `/governance` (+ AI Hub→Gobernanza) | `/governance/config`, `/ai-governance/policies` | admin / admin, pm | admin | kit | Dos pantallas de «gobernanza de IA» |
| Jira | `/jira-integration` **y** Enterprise→Integraciones | `JiraConfig` (`/jira/config` y `/integrations-hub/jira/config`) | admin, pm / admin | admin / any_manager | `<input>` 4 | D7; pm → 403 (E13) |
| M365 | `/m365` + Integraciones→`ms_graph` + Feature flags | — | admin | admin | Input | Repartido en 3 sitios |
| Webhooks | Enterprise (entrantes), `/webhook-log` (salientes, solo lectura), ChatAdmin (chat) | 3 dominios | admin | admin | mixto | Salientes sin alta en la UI (D6) |
| SSO, RGPD, API keys, correo | `/enterprise` | `/enterprise/sso`, `/gdpr`, `/bookings/api-keys`, `/email` | admin | admin / any_manager | 19 `<input>`, 4 textarea | — |
| Empresas | `/organizations` | `/organizations` | admin | **superadmin** | 13 `<input>` | Admin de empresa → 403 (E11) |
| Retención y retención legal | `/grc`→Retención **y** `/settings/chat-admin` | `retention_policies`/`legal_holds` frente a `collaboration_*` | admin | admin | Tabla / 13 `<input>` | D13; ChatAdmin sin menú |
| SLA (tiempos y horario) | SD→Config→SLA, Reglas SLA/OLA, `/sla-calendars`, Config. dinámica→SLA | `sla-policies`, `sla_calendars`, runtime `SLA_*` | SD sin filtro / admin, pm / admin | admin / admin_or_pm / admin | kit | 4 sitios (D11a); enlace a calendarios → `/403` (E7) |
| Notificaciones del Service Desk | SD→Config→Notificaciones **y** Config. dinámica→Service Desk | runtime `service_desk` (51 claves) | SD sin filtro / admin | admin | el mismo editor | D11b; no-admin → 403 al cargar |
| Horas extra | Horas extra→Configuración | `/overtime/config`, `/overtime/budgets` | admin, hr | admin_or_hr | kit | Enlace y ejemplos → 403 para hr (E1, E2) |
| Ausencias (tipos, turnos, jornadas…) | Ausencias→Configuración | `/absences/*` | admin, hr | admin_or_hr / any_manager | kit | Enlaces → `/403` para hr (E3, E4) |
| Coste por persona | `/user-costs` (+ `hourly_rate` en Usuarios) | `/user-costs/*` | admin, hr | admin_or_hr | Tabla + Input | D17 |
| IVA por defecto | Config. dinámica→Locale `DEFAULT_TAX_RATE` | runtime | admin | admin | kit | Facturación lo ignora (21 fijo) |
| Formularios públicos, apps de desarrollador, importación, MFA | `/public-forms`, `/developer`, `/import`, `/mfa` | `/forms`, `/developer/apps`, `/billing-reports/import`, `/auth/mfa` | admin, pm / todos | admin_or_pm / any_manager / propio | kit | — |
| Blueprints del Service Desk | `/sd/workflow-designer` | `/sd/workflow-designer/*` | admin, pm | any_manager | 7 `<input>` | 8 placeholders sin traducir |
