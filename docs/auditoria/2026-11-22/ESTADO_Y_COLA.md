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
| 25k | **Certificaciones — módulo (fases 1, 2 y 5: §3 y §4)** | ✅ Hecho (sin probar; tests escritos en `tests/test_certificaciones.py`, se ejecutan en la prueba general): migración `212_certificaciones` (21 tablas, padre 211) y `213_certificaciones_id_semilla` (padre 212; la 212 ya estaba aplicada a la base real); biblioteca sembrada y validada, GRC ISO 27001/SOC 2 migrado, programas, declaración, matriz, pruebas, cumplimiento continuo, evidencias, auditorías/hallazgos/CAPA, auditores con acceso temporal (`/auditor/:token`), certificados, NIS2, proveedores críticos, panel y paquete firmado; capacidades, SoD, GRC, ajustes, BPM (3 procesos), docs/CERTIFICACIONES.md y README §15.9. PENDIENTE en la prueba general: rutas anónimas 104, `tests/test_guardas_de_rol.py`/capacidades con las rutas nuevas, tsc del frontend nuevo; fase 4 (certificar contecflow) sin empezar |
| 25j | **Certificaciones — contenido (fase 3)** | ✅ Hecho: `app/data/certificaciones/` con 6 marcos, 207 controles comunes (ISO 27001 93/93 Anexo A + 25 cláusulas; TISAX 63 ids con prototipos; NIS2 25; SOX 41; J-SOX 35; IEC 62443 186), 7 plantillas (6 + programa integrado de 132 tareas) y 44 plantillas de documentos; test sin ejecutar `tests/test_contenido_certificaciones.py`; docs/CERTIFICACIONES_CONTENIDO.md. PENDIENTE: verificar ids TISAX/4-2 contra textos con licencia al importar |

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

## 6. Ronda 24-11-2026 (en curso, sin subir)

- Diseño (kit, para todo el sistema): todos los desplegables con el mismo ancho (`--ancho-min-desplegable`); nota del selector de periodo como icono ⓘ en la misma línea; ayuda larga fuera de filas con botones (Plan de reducción); `gap` sin `display` corregido (constructor de informes, plantillas, formularios públicos); flujo acumulado alineado arriba. Reglas en `docs/GUIA_DE_DISENO.md` §8.1 bis y §9.1.
- Clientes → contactos: «desactivar contacto» con `UserX` (antes la misma papelera que «eliminar usuario del portal»); la estrella de principal con la caja estándar.
- NPS: el ranking ya no oculta los clientes sin salud calculada al calcular la de uno. Cálculo de salud (componentes con campos inexistentes y valores fijos) en manos de un agente.
- Salud del cliente ✅ hecho (sin probar; tests escritos, se ejecutan en la prueba general): un único cálculo (`compute_composite_health`) con los campos reales (hitos `is_completed`/`completed_date`/`due_date`, coste real de `margen_en_bloque` frente a `budget_amount`, `sla_resolution_breached`); componente sin datos = no puntúa y su peso se reparte (Gainsight/ChurnZero); «Calcular salud» guarda todos los componentes y audita quién; ranking sin duplicados y solo clientes activos; CSAT 1-5 fuera del NPS (resumen, listado, salud y métricas); retención nueva `client_nps_responses` y `client_health_snapshots`; pantalla NPS muestra los componentes. Detalle: README §27.4. Tests: `tests/test_salud_cliente_2026_11_24.py`.
- Los 500 de `ws/ticket`, `timer/current` y notificaciones eran del reinicio del backend (proxy de Vite sin backend); medido después: 200.
- Chat del portal completo ✅ hecho (sin probar; tests escritos, se ejecutan en la prueba general): conversaciones formales operador ↔ cliente con imágenes y adjuntos (vista previa, descarga solo por la API para participantes de la misma empresa, validación de contenido por bytes, AV/DLP, tipos y tamaño por empresa), emojis y reacciones, responder citando, editar/borrar el propio mensaje con rastro (versiones + auditoría, plazo por empresa), enlaces seguros, «escribiendo…», leído y tiempo real por los WebSocket existentes; llamadas y videollamadas **solo del operador** (capacidad `clientes.llamar`; el cliente acepta/rechaza/cuelga y `POST /portal/conversations/{id}/calls` le da siempre 403 `portal_llamada_solo_operador`), activables por empresa en Configuración › Portal › Chat del portal (grupo `portal_chat`); sin grabación (aviso al cliente). GRC: auditoría de subidas/borrados/llamadas/ediciones, retención `portal_conversation_attachments`/`_message_versions`/`_calls` con bloqueo legal, RGPD (copia y supresión). Arreglados de paso: el cliente veía mensajes del equipo pendientes de aprobación y, como «último mensaje», notas internas; el cliente podía mandar cualquier `message_type`. Migración `209_chat_del_portal_completo` (padre 208). Doc: `docs/portal/CHAT_DEL_PORTAL.md`. Tests: `tests/test_chat_del_portal_2026_11_24.py`. Pestaña «Chat» del portal (dominio colaboración) ✅ hecha también (sin probar): mismo nivel en el cliente (adjuntos validados y descarga por la API, emojis, reacciones, citas —ahora ve las respuestas en hilo del equipo—, editar/borrar con rastro y plazo, enlaces, leído, «escribiendo…», avisos del bus por el WebSocket del portal, aceptar/rechazar/colgar; `POST /portal/collaboration/calls` siempre 403); en el chat interno, con clientes en la conversación: `clientes.llamar` y ajustes `portal_chat` para llamar, mismas reglas de adjuntos, sin grabación/asistente/transcripción (409 `portal_llamada_no_se_graba`), borrado con rastro, cita y enlaces en la burbuja. Migración `210_chat_del_portal_colaboracion` (padre 209). Tests: `tests/test_chat_del_portal_colaboracion_2026_11_24.py`.
- Chat en vivo de Soporte completo y «un solo chat» ✅ hecho (sin probar; tests escritos, se ejecutan en la prueba general): el tercer chat del portal (Soporte → Chat en vivo; operador en la bandeja de canales) con imágenes y adjuntos (misma validación por contenido, AV/DLP, tipos y tamaño `portal_chat`, descarga solo por la API), emojis y reacciones, citar, editar/borrar lo propio con rastro y plazo, enlaces seguros, «escribiendo» y «leído», y llamadas/videollamadas que SOLO inicia el operador (`clientes.llamar`; el cliente 403 `portal_llamada_solo_operador`; grabar 409 `portal_llamada_no_se_graba`). Migración `211_chat_en_vivo_completo` (padre 210). GRC: auditoría `livechat.*`, retención/bloqueo legal de `sd_channel_attachments`, `sd_channel_message_versions`, `sd_channel_calls`, RGPD (antes el chat en vivo no entraba). Además, por orden del usuario, los tres chats del portal (los dos lados) usan la MISMA pantalla que el chat interno: piezas extraídas a `frontend/src/components/chat/` (lista, cabecera, fila de mensaje con barra flotante tras la hora, editor con emoji); «Con supervisión» solo al operador como indicador. Docs: `docs/portal/CHAT_DEL_PORTAL.md` §10-§11, `docs/GUIA_DE_DISENO.md` §17. Pendiente de la prueba general: recuento de `tests/test_guardas_de_rol.py` (rutas nuevas del chat en vivo).
- Métricas BI `nps_by_client`/`nps_trend`: NPS real (−100 a 100) en vez de la media de la nota 0-10 (estándar de mercado); `avg_score` se conserva. README §27.4.
- `organization_id` obligatorio: caminos sin empresa en la sesión ✅ hecho (sin probar; tests escritos, se ejecutan en la prueba general): 210 tablas en riesgo medidas (sin clave ajena NOT NULL a un padre con empresa) y revisados los contextos sin empresa (tareas, planificador de colaboración, hilos, webhooks, rutas anónimas, WebSockets, siembra, scripts, `sin_filtro_de_tenant`, inserts masivos). Arreglados: mensajes programados de colaboración por empresa, correo/SMS entrante sin empresa destinataria → se ignora (con una sola empresa, esa), agente de la CMDB y webhook de colaboración publican su empresa, Stripe, aprobación por correo de superadmin, SoD y cupos (inserts sin sellado), instantánea colaborativa, ticket del bot, caché semántica y registros accesorios (uso/acciones de IA, guardarraíles, conectores, traducción) que ya no rompen a quien llama; superadmin sin empresa elegida → 409 `empresa_requerida` (antes 500). BPM: paso nuevo en `multichannel_intake` (es/en/zh). Doc: `docs/seguridad/empresa_obligatoria.md` §6. Tests: `tests/test_empresa_en_segundo_plano_2026_11_24.py` (+2 ajustados).
- **Aparcado para después:** módulo de Certificaciones (TISAX, NIS2, ISO 27001, SOX, J-SOX, IEC 62443): punto de control tipo Licencias, plantillas de proyecto completas y certificación de contecflow. Propuesta completa en `docs/propuestas/CERTIFICACIONES.md`; pendiente de las decisiones de su §8.
- Menú lateral: pulsar el nombre de un grupo lo pliega o despliega igual que la flecha. Si está plegado, además abre su panel (`components/layout/Layout.tsx`).
- Campos con etiqueta del kit + `SelectorDeContexto` ✅ hecho (sin probar; se verifica en la prueba general): ~1.050 pares `<label>`+control suelto migrados a la prop `label` de `Select`/`Input`/`Textarea`/`DateInput`/`CampoFecha`/`Buscador`/`UserSelect`/`ClientSelect`/`ProjectSelect` (se añade `label` a `CampoFecha`, `DateInput` y los selectores de entidad), clases propias de etiqueta/ancho/alto y sus reglas CSS muertas borradas, y nuevo componente `SelectorDeContexto` (patrón de Matriz RACI) en ~30 pantallas (proyecto/cliente/unidad/sprint/periodo). Vigilante en `scripts/kit_pendientes.mjs` (`campoConEtiquetaPropia`, `selectorDeContextoAMano`, sección `campos` de `kit-pendientes.json`, cupo que solo baja; residuo: chat del portal y 5 filtros/formularios). Regla en `docs/GUIA_DE_DISENO.md` §8.9 y §9.
- **Prueba general (24-11-2026): 26 tests en rojo tras la ronda, en verde.** Código arreglado: chat del portal
  sin ciclo de imports (`visible_para_cliente` pasa a `portal_conversation_service/_comun.py`; `adjuntos` importa
  `mensajes` arriba), oyentes de borrado de ficheros del chat fuera del modelo (`app/db/portal_chat_borrado.py`,
  un modelo no importa servicios), sesión de arranque de la sincronización BPM con contexto de sistema declarado
  (`app/main.py::_sincronizar_catalogo_bpm`), dos `except Exception` silenciosos en `app/db/empresa_obligatoria.py`
  y únicos de `portal_conversation_reactions` por empresa (modelo y 209 editada antes de subirse; base de
  desarrollo reconstruida con un arreglo puntual idempotente, tabla vacía, `comprobar_esquema` OK). Tests
  adaptados al comportamiento nuevo deliberado (comentario 24-11-2026 en cada uno): listas del chat en `items`,
  empresa obligatoria (OAuth, festivos, avisos de un trabajo, plantilla BPM global sin versión), orden de siembra
  (departamentos tras la empresa), zona por defecto `DEFAULT_TIMEZONE`, reacción válida antes de buscar el
  mensaje, y contadores de guardas (+7 rutas del equipo con capacidad, +15 del cliente del portal acotadas).
  Pendiente de decidir: plantillas BPM globales frente a `bpmn_process_versions` NOT NULL
  (`docs/seguridad/empresa_obligatoria.md` §6.x).

- Burbujas en todos los chats («como WhatsApp o Teams») ✅ hecho (sin probar; se verifica en la prueba general): `FilaDeMensaje` con `propio` (derecha, acento suave) / ajeno (izquierda, avatar y nombre), hora y ✓/✓✓ dentro de la burbuja, agrupación, separadores de día, mensajes de sistema en pastilla, barra de acciones al lado de la burbuja; extendida al hilo del interno, panel flotante, chat de la llamada y asistentes de IA (NexusAssist, asistente y widget de IA del portal, Nexus Agent, Preguntar a la empresa) con `EditorDeChat`; CSS propio sin uso borrado; vigilante `comprobarChatUnico` ampliado (`OTROS_CHATS`, `propio`/`esBot` obligatorio). Claves nuevas `chat.pensando` y `chat.tu` (es/en/zh). Doc: `docs/GUIA_DE_DISENO.md` §17.1, `docs/portal/CHAT_DEL_PORTAL.md` §11.1, README §37.1, `DESIGN_SYSTEM.md`.
## 7. Programa de estabilidad de diseño (medido el 24-11-2026, en cola tras «campos al kit»)

Medición estática de `frontend/src` (sin contar `components/ui`), script en el scratchpad `medir_diseno.py`:

| Patrón | Medido | Estándar a imponer |
|---|---|---|
| Campos con etiqueta hecha a mano | 417 desplegables + 508 de texto/fecha/área | Prop de etiqueta del kit (agente en curso) |
| Selector de contexto arriba | Mínimo 23 pantallas, 4 formas distintas | `SelectorDeContexto` del kit, patrón Matriz RACI (agente en curso) |
| Cabecera de página | 44 `*Page.tsx` sin `PageHeader`, 15 `<h1>` a mano | `PageHeader` siempre |
| Tarjetas | 252 clases CSS propias con fondo, borde y radio; 8 o más rellenos distintos | `Card` con relleno único por tamaño |
| Modales | 17 anchos distintos (460 a 880) | 3 tamaños: `sm` 480, `md` 620, `lg` 760 (+ `xl` excepcional) |
| Iconos | 12 tamaños (10 a 36) | Tamaño fijado por contexto (botón xs/sm/md, fila, estado vacío) |
| Botones | `xs` 350 / `sm` 547 / `md` 8 / `lg` 7 usados sin regla | Regla por contexto (cabecera, barra, fila, tarjeta) |
| Radios | `8px` 554, `12px` 157, `4px` 108, `20px` 64, `7px`, `5px`, `3px`, `2px`… | Tokens `--radius-*` |
| Espaciado (`gap`) | 15 valores literales (2 a 20 px) | Escala `--space-*` |
| Colores literales en CSS | 256 | Tokens de color |
| Alto de control a mano | 85 | `--alto-control-*` |
| Estilos en línea | 390 en 145 ficheros | Clases y tokens |
| Pastillas propias | 30 | `StatusBadge` |
| «Cargando…» a mano | 45 | `Spinner` / esqueleto del kit |

| Enlaces a Configuración desde otras pantallas | 28 en 25 ficheros, solo unos 5 comprueban permiso | Componente `AvisoDeConfiguracion` del kit: con permiso, aviso + enlace; sin permiso, aviso + «Pídeselo a tu administrador», sin enlace (decidido por el usuario el 24-11-2026) |

Orden (un agente detrás de otro, máximo 3 a la vez):
0. `AvisoDeConfiguracion` (los 28 enlaces).
   Con él, los restos de «campos al kit»:
   - 14 campos con etiqueta propia y 1 selector de contexto en el chat del portal y el chat global;
   - campos dinámicos de `AltaDeTarea` y `DetalleDeTarea`;
   - `type="month"`, que falta en el `Input` del kit (`BudgetsPage`, `FormularioDePartida`).
1. Cabeceras.
2. Tarjetas.
3. Modales.
4. Iconos y botones.
5. Tokens (radios, espacio, color, altos, estilos en línea).
6. Pastillas, cargas y vacíos.

Cada paso:
- deja su vigilante con cupo en `scripts/kit_pendientes.mjs`, que solo puede bajar;
- documenta la regla en `docs/GUIA_DE_DISENO.md`;
- no ejecuta pruebas: la prueba general es al final.
- Cerrados los dos pendientes de «empresa obligatoria»: el superadmin sin empresa recibe 409 `empresa_requerida` al encolar trabajo, y los procesos BPM sembrados sin editar se ponen al día solos al arrancar.
- Roles y permisos vacío para el superadmin: los roles de sistema solo se sembraban al abrir la pantalla con una sesión con empresa. Ahora se siembran al arrancar en todas las empresas activas (`semillas.sembrar_roles_de_sistema_en_todas`).
