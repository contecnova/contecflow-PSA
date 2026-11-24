# Estado del trabajo y cola de encargos (23-11-2026)

Documento de continuidad: si se corta la luz o la sesión, desde aquí se retoma.
Los cambios hechos están en disco SIN subir (último commit en main: `dd130072`);
23-11-2026 ~17:00: subido a main por excepción pedida por el usuario (commit `5f9ec1f2`, sin prueba general; la prueba única sigue al final de la cola).
no se pierden con un corte, pero los agentes que estaban trabajando sí se paran
y hay que relanzarlos con el encargo de su fila.

## 0. Tabla única: hecho y por hacer (23-11-2026 ~15:00)

| # | Encargo | Estado |
|---|---|---|
| 1 | Clientes internos, índice de riesgo CMDB, flujo de demanda, Docker con Prometheus/Grafana/Alertmanager, campos al kit | ✅ Hecho y subido (`dd130072`) |
| 2 | setup.bat: frontend que no arrancaba, falso «no se pudo lanzar», esperas | ✅ Hecho y subido |
| 3 | 13 tests de la integración de esos bloques | ✅ Hecho y subido |
| 4 | Auditoría completa (6 informes en esta carpeta) | ✅ Hecho, sin subir |
| 5 | Prueba de la herramienta (suite, frontend, barrido de 744 GET) | ✅ Hecho; fallos corregidos |
| 6 | Arreglos ronda 1 (aislamiento, seguridad E/S, servicios a-l y m-z, frontend) | ✅ Hecho, sin subir |
| 7 | 55 fallos de la repetición de tests | ✅ Hecho, sin subir |
| 8 | Cambios estándar del CAB (catálogo ITIL 4) | ✅ Hecho, sin subir |
| 9 | Fuentes de Google en local | ✅ Hecho, sin subir |
| 10 | Oportunidades canceladas (estándar de mercado) | ✅ Hecho, sin subir |
| 11 | Contraseña obligatoria en primer acceso al portal; contrato en proyectos | ✅ Hecho, sin subir |
| 12 | Seguridad de cuentas y GRC (caducidad, MFA, sesiones, IP, alertas, recertificación, audit log inmutable) | ✅ Hecho, sin subir |
| 13 | Diseño (lupa, alturas, filtros de Clientes, repaso general) | ✅ Hecho, sin subir |
| 14 | Todas las rutas por capacidad; rutas públicas; sesiones sin empresa bloqueadas | ✅ Hecho, sin subir |
| 15 | Textos fijos, exportaciones, M365 por empresa, red, «probar conexión» | ✅ Hecho, sin subir |
| 16 | Frontend: aprobación del agente de IA, accesibilidad, troceo, documentación | ✅ Hecho, sin subir |
| 17 | Migraciones 196–200 | ✅ Creadas y probadas sobre copia; falta aplicarlas a la base real |
| 18 | Respaldo local (`refs/respaldos/2026-11-23`) | ✅ Hecho |
| 19 | Pendientes del informe 02 (altos restantes, medios y bajos) | ✅ Hecho: informe 02 cerrado entero (todas las filas con estado). Por verificar con credenciales reales: Jira, Xero, QuickBooks, Qualys, Tenable, OpenExchangeRates. Cambios de comportamiento: LiveKit sin claves → 503 fuera de desarrollo; antivirus activado y caído bloquea descargas; zip >300 ficheros rechazado; usuario sin empresa no ve datos en el panel |
| 20 | 10 incidencias de usuarios reales | ✅ Hecho (detalle en 06_incidencias_usuarios.md): 403 al crear ticket, traducciones del alta, aviso de cambios sin guardar en todo el kit, inglés por defecto, restablecer contraseña en app y portal, acceso al portal, enlace del buzón, SSO Azure sin 500, prueba del buzón |
| 21 | Cierre obligatorio | ✅ Hecho (24-11-2026): migraciones 196→207 aplicadas a la base real con copias en backups/; prueba global: backend suite completa (6.905 + 38 corregidos = todo en verde; fallo real de zona horaria corregido en timeutil), frontend tsc/eslint/kit/build limpios y vitest 992/992; setup.bat update probado de punta a punta (setup.sh: `bash -n`, sin Linux para ejecutarlo); subido a main |
| 22 | Ronda corta + migración `201_cadena_colaboracion_y_cronometro` | ✅ Hecho (HMAC de la cadena del chat con key_id; un solo cronómetro activo → 409; etiquetas de retención; avisos de hito; EstadoDeCuenta; ProjectsPage 1237→255 líneas). Cabeza 201, 153 revisiones. PENDIENTE para la ronda final: el llavero JWT poda claves al rotar y las filas firmadas con una clave podada quedan «unverifiable» → llavero propio de auditoría que no se pode (GRC) |
| 22b | **Menú personalizable** (feedback de usuarios): clic en el icono/nombre de la categoría → su panel (flecha despliega; con menú contraído, icono → panel y desplegable al pasar); ocultar pestañas por usuario (modo «Personalizar menú», restablecer); reordenar categorías arrastrando (y con teclado); preferencias guardadas por usuario; menú y orden por defecto por rol en Configuración; ocultar no quita permisos; ⌘K encuentra lo oculto | ✅ Hecho (paneles por categoría, Personalizar menú, reordenar con arrastre/teclado, preferencias en servidor, /settings/menu-por-defecto por rol auditado) |
| 23 | **Cola 1 — «Mi cuaderno» tipo OneNote** | ✅ Hecho (4 fases + GRC; migración 202 ya aplicada a la base real; docs/CUADERNO.md) |
| 24 | **Cola 2 — MCP para OpenCode y Claude Code** | ✅ Hecho (21 herramientas de trabajo diario con la misma capacidad que su ruta, protocolo 2025-11-25, credenciales mcp:read/mcp:write, límite por credencial, auditoría, /settings/mcp, guía docs/integraciones/MCP.md; sin migración) |
| 25 | **Cola 3 — «Del ticket al PR»** (agente de código en contenedor aislado, PR por cambios/CAB, horas, coste de IA, auditoría; módulo opcional) | ✅ Hecho (migración 203 `ticket_pr_repos`/`ticket_pr_runs`; motor detrás de interfaz con OpenCode como primero y motor simulado; contenedor efímero con red interna + proxy con lista blanca; GitHub App / GitLab por API sin credenciales en el contenedor; diff comprobado; cambio + CAB + estado `contecflow/cab`; límites, coste por proyecto, auditoría, retención; `/settings/ticket-a-pr`; docs/integraciones/TICKET_A_PR.md). Pendiente de verificar con Docker, Git y modelo reales (§11 del documento) |
| 25b | **Botones de icono iguales en toda la app** | ✅ Hecho: `IconButton variante="caja"` (32 px por defecto, cuadrado, sin estirarse; tonos neutro/peligro/acento), 198 en la app; 115 botones hechos a mano → 0 (27 excepciones justificadas); regla `contec/sin-boton-de-icono-propio` y comprobación CSS con cupo 0. Revisar a ojo filas densas (crecen a 32 px) e iconos de cabecera del chat (ahora con borde) |
| 25c | **BPM (procesos) completo y correcto**: inventario, completar lo que falte frente a un BPM profesional, errores, GRC, docs/BPM.md | ▶ En marcha |
| 25d | **README final y limpieza de documentos** | ✅ Hecho: README 4.439 líneas (técnica §1-16, funcional §17-41, común §42-45), ajustes en docs/REFERENCIA_DE_AJUSTES.md, CHANGELOG.md nuevo, 18 documentos sin valor retirados, DOCS.md fusionado. Fallos reales detectados → fila 25g |
| 25e | **Usuarios del portal** | ✅ Hecho (contraseña a mano con política, sin devolverla ni auditarla; eliminar = borrar sin historial / archivar con historial, restaurar; migración 205_portal_usuarios). PENDIENTE: integrar su párrafo en el README (parte de portal) |
| 25f | **PIR en cambios del CAB y en proyectos** | ✅ Hecho (migración 206_pir probada en copia; 4 tablas, hito go-live, programación automática, CAB, catálogo estándar, informes, bandeja, lecciones, segregación, GRC; docs/PIR.md). PENDIENTE en el cierre: el id de un participante puede quedar en la lista JSON de la PIR tras una supresión RGPD (docs/PIR.md §5) → corregir |
| 25g | **Fallos detectados al documentar** | ✅ Hecho: alias de ENVIRONMENT; modo de tareas con o sin Redis (scripts/modo_tareas.py) y puertos configurables; contraseñas y banner reales por usuario; Makefile revisado (clean ya no borra clarive.db, init-admin real); SAML completo con signxml (ACS con firma, audiencia, destino, caducidad, anti-replay; SLO); atajos G T/P/I/S; copias locales (scripts/copia_local.py, setup backup/restore); UTF-8; README §15 GRC, §29.2 portal, §34 BPM. PENDIENTE en el cierre: test de copia/restauración de SQLite; re-sincronizar códigos de error (codigos_de_error.py se pisó entre agentes) |
| 25h | **Asignación IA: «Reconstruir vectores» y «Generar perfiles» daban fallo** — medido: la operación tarda 0,8 s, pero cargar el modelo transformer la 1.ª vez por proceso tarda ~140 s y la pantalla cortaba a 30 s; además devolvía None | ✅ Hecho: precarga en segundo plano al arrancar, candado contra cargas dobles, límite de 10 min en esas dos llamadas, devuelve el nº de perfiles (requiere reiniciar el backend) |
| 25i | **contecintelligence y contecmind** | ✅ Inventario hecho (casi todo traído). ▶ En marcha lo que falta: sección de conectores en el README (se perdió en la limpieza), bucle de aprendizaje del motor semántico (corregir asignación, historial, precisión real, fallo corrected_by 52>36, reentrenamiento, quitar nombre de cliente del código), fichas lesson/expense/budget del conector, pantallas de anomalías y componentes incrustables, KBGap → tareas, Ask-the-Data con memoria. SAML lo hace 25g |

Base real: migraciones 196→202 aplicadas el 23-11-2026 (~17:30, copia previa en backups/). `setup clean` arreglado (reseteo respeta el audit log inmutable reinstalando los triggers).

Decisiones para proponer al final: stylelint, CI con Postgres, cobertura de tests, único de `client_users` por empresa, `organization_id NOT NULL`.

## 1. Hecho (en disco, sin subir)

| Bloque | Resultado |
|---|---|
| Auditoría completa | Informes `01`–`05` y `04b` en esta carpeta |
| Arreglos ronda 1 | Aislamiento/auth/RLS, seguridad de entrada y salida (SSRF, subidas, secretos, Redis, CSV, copia antes de migrar), servicios a-l, servicios m-z, frontend |
| Migraciones | `196_auditoria_2026_11_22` y `197_dinero_numeric` creadas y probadas sobre copia; **no aplicadas a la base real** |
| Integración | 55 fallos de la repetición de tests arreglados (arquitectura + funcionales); frontend en verde (tsc, eslint, kit, build, vitest 855) |
| Sueltos | 500 de `/analytics/olap/portfolio-health`, firma electrónica (id UUID), lint, setup.bat (errorlevel tras `start`, esperas con ping), lupa del buscador del SD, filtros de Clientes |

## 2. En curso (ronda 2: 7 agentes; sin ejecutar tests, solo py_compile/import/eslint de lo tocado)

### Estado de cada frente (actualizado 23-11-2026 ~12:30)

Máximo 3 agentes a la vez (límite de 5 h: con 7 se cortaron todos a las 10:30).

| # | Estado |
|---|---|
| A | ✅ Terminado. Migración 198 creada y probada sobre copia |
| B | ✅ Terminado (M365 por empresa con `M365_PLATFORM_CREDENTIALS_ENABLED` desactivado → AVISAR en la nota de versión: las empresas que usaban los AZURE_* globales necesitan guardar su credencial; IP fijada en SMTP/IMAP y GHES, IMAP verifica certificado; «probar conexión» en todos los conectores con nivel `verificado`, tabla en docs/integraciones/pruebas_de_conexion.md; sin credenciales reales nada probado contra servicios reales). Antes: HECHO: 73 HTTPException → código (cuota `http_crudo` 0); textos fijos a-l 246→118 y m-z 284→112 (restos: prompts de IA, semillas); 10 exportadores CSV/XLSX neutralizados + test estático; plantilla de demanda del cliente → opcional (editó `195_flujo_de_demanda._sembrar_demo`: solo afecta a instalaciones nuevas). PENDIENTE: M365 por empresa, IP fijada en IMAP/SMTP y GHES, «probar conexión» de conectores, DOCS.md y docs/seguridad. ESQUEMA para la 200: claves+parámetros en `sod_rules`, `issue_types`, `workflow_states`, `workflow_transitions`, `approval_groups`; `sprint_plans.ai_reasoning_params`; `NotificationType` milestone_approved/rejected; `*_key/*_params` en `SLAEvent.note`, `Alert.title/description`, `Invoice.notes`, `RevenueEntry.description`, `review_notes` |
| C | ▶ Reanudado (47 .py compilan). HECHO: margen único en bloque (`app/services/margen_de_proyectos.py`) usado por panel, rentabilidad, evolución, EVM, BI, OLAP, lecciones e IA; 5.º resolutor de divisas unificado; altos A13, A14, A31, A33, A36, A42, A43, A49, A51, A55-A57, A63; medios M1-M16 (parciales M2, M8), M19, M22, M27, M28, M40, M95, M96, M103-M105; 4 ajustes nuevos. PENDIENTE: marcar TODAS las filas del informe 02 y su sección 0; altos A8, A22, A23 (backend), A24, A25, A50; medios M17, M18, M21, M23-M26, M29-M39, M41-M58, M60, M66-M79 (los de CAB/portal/contratos ver si ya están), M81-M93, M97-M102, M106, M107, M109; bajos restantes de §3.4 y §5. Verificar con credenciales reales: Jira Cloud (search/jql con nextPageToken), Xero (refresh), QuickBooks. ESQUEMA para migración 200: `subcontractor_invoices.approved_by VARCHAR(36)`, `approved_at TIMESTAMPTZ`; `contracts.currency VARCHAR(3)`. Tests a pasar: lista en su informe (test_margen_unico_2026_11_23, test_dashboard_extended, test_profitability_pnl, test_jira, test_horas_extra, test_clientes_internos…) |
| D | ✅ Terminado (fuentes locales @fontsource y CSP sin Google; aprobación humana del agente de IA en NexusAgentPage; a11y a `error` con 0 avisos; capacidades de /bpm, /agent-dashboard, /portfolio/intake; /search desde la paleta; token de webhook del chat visible una vez; Confirm y desenvoltorio únicos; 36 llamadas sueltas a servicios; historial del temporizador en servidor; filas de 04/04b/05 marcadas). PENDIENTE en el cierre: tsc completo (confirmar `PortalDashboardCalculos.ts`), `EstadoDeCuenta.tsx` con 3 llamadas sueltas, `ProjectsPage` sin trocear. Decisiones abiertas que listó: stylelint, CI con Postgres, `-p no:warnings`/cobertura. Antes: HECHO: Pipeline estándar de mercado (front+back, OLAP corregido), 24 componentes >800 líneas troceados, documentación al día (README cabeza 198, 12 históricos marcados). Tests del subagente cortado revisados: borrados justificados. PENDIENTE: fuentes locales, aprobación del agente de IA, tarea 5 (M16, a11y error, i18n_baseline, /search, claves audit/webhooks, token de webhook una vez), restos de tarea 4, posible error tsc en `PortalDashboardCalculos.ts`, marcar filas 04/04b/05 |
| E | ✅ Terminado. 1.425 rutas por rol → 0 (1.987 con capacidad, misma audiencia medida; 101 capacidades nuevas sin módulo); 93 rutas anónimas con credencial y contexto (docs/seguridad/rutas_anonimas.md); `TENANT_SESION_SIN_CONTEXTO=cerrar` por defecto; bajos de 01 cerrados (health sin versión, 127.0.0.1 local, Dockerfile, etc.). PENDIENTE en la integración: `DELETE /security/me/devices/{id}` no la ve el detector como acotada (test_guardas_de_rol 93 vs 94); tests con `TestSession()` a mano sin contexto lanzarán TenantIsolationError. ESQUEMA para la 200 descrito en doc 03 (A-MOD2 4 columnas de dinero, datos personales de AppSetting → tablas propias, M-MOD1, M-MOD2, B-MOD1). `.env` local con ACCESS_TOKEN_EXPIRE_MINUTES=60 (se recorta a 30): avisar al usuario |
| F | ✅ Terminado. Migración 199 creada y probada sobre copia (`comprobar_esquema` OK). Pendiente: 5 filas de ajustes de otros en README 4.2 (`SMTP_TLS_VERIFY`, `BI_TOKEN_DAILY_REQUEST_LIMIT`, `BI_DELIVERY_ALLOWED_DOMAINS`, `BI_DELIVERY_MAX_ROWS`, `OVERTIME_LEGAL_ANNUAL_CAP_HOURS`) y encabezado 685 |
| G | ✅ Terminado (Buscador e icono en Input, FiltrosDeLista, alturas 38 px, `.ds-input` muertos 22→0, listas con el tema). No pudo mirar en navegador (Chrome sin cabeza bloqueado por directiva): revisión visual en la prueba final |

Incidencias de usuarios reales (23-11-2026) ✅ código terminado (sin tests ejecutados; detalle y tests en `06_incidencias_usuarios.md`; la 7 exige aplicar 196-199): 1) 403 «Roles requeridos: ['admin']» al crear ticket; 3) «Entorno afectado» y «Suggested routing applied» sin traducir; 4) cerrar formulario sin avisar de cambios sin guardar (general en el kit); 5) idioma por defecto inglés en portal y app; 6) restablecer contraseña («¿olvidaste…?»); 7) no se puede entrar al portal de clientes; 8) Configuración > buzón > configurar no lleva a nada; 9) SSO Azure: 500 al guardar; 10) buzón SD: «no test probe defined for sd_mailbox».

Migración 200 ✅ (`200_esquema_pendiente_auditoria`, cabeza única, 152 revisiones; probada en copia 195→199→200→199→200 sin perder filas, integrity_check limpio; Postgres SIN probar). Contiene: aprobación de facturas de subcontrata, moneda del contrato, textos por clave (cableados en SLA, SoD, hitos, alertas, ingresos, partes, tipos de incidencia, flujos), tipos de aviso milestone_*, datos personales de AppSetting → `sd_voice_sessions` (cifrado), `sd_ticket_hold_snapshots`, `sd_dynamic_form_rules(_history)`, 3 columnas de dinero a Numeric, `org_id`→`organization_id` en 11 tablas (synonym), únicos de conectores por empresa, ON DELETE en 440 FK. PENDIENTE en la integración (frontend): etiquetas `retencion_tipo_sd_voice_sessions` / `retencion_tipo_sd_kb_gaps` en es/en/zh, e icono/color/etiqueta de los avisos `milestone_approved/rejected` (iconosDeAviso.tsx, UserProfilePanel.tsx, NotificationsPage.tsx). Quedan para más adelante con motivo: único de `client_users` por empresa (antes el login del portal debe elegir empresa) y `organization_id NOT NULL`.

Orden (decidido por el usuario ~16:00): el cierre (fila 21: migraciones con setup → prueba general → arreglos → subida) se hace UNA sola vez AL FINAL DE TODO, después de la fila 25. Las filas 23, 24 y 25 se hacen en orden, una detrás de otra, empezando en cuanto haya hueco (máx. 3 agentes). Mientras no se sube, se renueva el respaldo local `refs/respaldos/…` al terminar cada fila. (`200_esquema_pendiente_auditoria`, con lo pedido por B, C y E) en marcha (A, B, E, F, G terminados) (nunca más de 3 a la vez) → migración 200 (esquema pedido por B y C) → cierre.

### Alcance de cada frente

| # | Frente | Alcance |
|---|---|---|
| A | CAB estándar + portal + contratos | Catálogo de cambios estándar ITIL 4 (preaprobados, vigencia, suspensión por fallos, gestión en Configuración); cambio de contraseña obligatorio en el primer acceso al portal; `contract_amount` en alta/edición de proyecto; único de `ai_meeting_user_prefs` por empresa. **Crea la migración `198_cambios_estandar_y_portal`** |
| B | Textos, exportaciones, red | 40+ textos en castellano fijos → claves; 70 HTTPException sin código; ~30 generadores CSV/XLSX neutralizados; M365/Graph por empresa; anti DNS-rebinding en GitHub GHES, IMAP y SMTP; «probar conexión» en conectores |
| C | Pendientes del informe 02 | Todos los ⏸, medios y bajos de servicios a-l; unificar los 4 cálculos de margen sin N+1 |
| D | Frontend general | Fuentes de Google en local; Pipeline: canceladas fuera del pipeline/previsión y de la tasa de éxito (ganadas/(ganadas+perdidas)), mostradas aparte; pantalla de aprobación humana del agente de IA; trocear componentes >800 líneas; estilos en línea y colores a tokens; accesibilidad a `error`; docs desfasados (05-B); tests laxos (05-C) |
| E | Guardas y rutas | 1.421 rutas por rol → capacidades (misma audiencia); 93 rutas anónimas revisadas; `TENANT_SESION_SIN_CONTEXTO=cerrar` por defecto; resto de 01 y 03 |
| F | Seguridad de cuentas y GRC | Política de contraseñas (caducidad opcional, historial, complejidad, comprometidas), bloqueo, MFA (TOTP, por empresa/rol), sesiones (inactividad, máximo, concurrentes, cierre remoto), IP/horario, alertas, recertificación de accesos, audit log inmutable, retención/RGPD de lo nuevo; todo en Configuración → Seguridad. **Crea la migración `199_seguridad_de_cuentas`** (tras la 198) |
| G | Diseño de toda la plataforma | Icono dentro del Input del kit y `Buscador` estándar; selectores CSS `.ds-input` rotos por la migración al kit; alturas iguales (token de alto de control); filas de filtros sin recortes (patrón de Clientes: buscador, segmentado, 2 columnas con SelectRico); listas desplegables con el tema; repaso general |

## 3. Cierre obligatorio de la ronda (cuando terminen TODOS)

1. Aplicar migraciones 196 → 199 con `setup.bat update` (copia automática antes de las destructivas).
2. Una sola prueba general de lo tocado: tests backend de los ficheros tocados/nuevos, frontend tsc + eslint + kit + vitest + build.
3. Comprobar arranque (`setup.bat start`: backend /health y frontend 200) y `setup.sh` (`bash -n`).
4. Arreglar lo que falle y repetir solo eso.
5. Informe consolidado de la auditoría (qué hace / qué no hace la herramienta, hallazgos y estado).
6. Commit y push a main (sin `.env` modificado).

## 4. Cola posterior (en este orden, uno detrás de otro, un agente cada uno, con su propio cierre obligatorio)

1. **«Mi cuaderno» tipo OneNote** para operadores y gestión: cuadernos → secciones → páginas; tareas con casilla, etiquetas, enlaces vivos `#ticket` / `@persona`, nota → tarea/ticket/demanda, vista de tareas y etiquetas, compartir con edición simultánea, adjuntos, dibujo, voz, IA, plantillas, sin conexión; privado por defecto con GRC completo.
2. **MCP para OpenCode y Claude Code**: dejar `/api/v1/mcp` compatible y documentado (ver tickets/tareas, imputar horas, comentar, abrir cambio) con permisos por capacidad, auditoría y límites.
3. **«Del ticket al PR»** (módulo opcional por empresa): agente de código (OpenCode servidor/SDK) en contenedor aislado contra el repo del cliente; PR por cambios/CAB; horas, coste de IA y auditoría.

## 5. Decisiones del usuario ya tomadas

- `.env` sigue versionado (hay `.env.example`); no se crea `.env.produccion`.
- Cambios estándar del CAB: catálogo de modelos preaprobados (frente A).
- Fuentes de Google: locales (frente D).
- Oportunidades canceladas: estándar de mercado (frente D).
- Sin tests mientras se trabaja; prueba general final obligatoria siempre antes de subir.
